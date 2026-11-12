#!/usr/bin/env python3
"""R104 strict *business* reconciliation. No success from URL-set coverage alone.

Host ground truth is independent server-received traffic. Only controlled /r104/api/
URLs are retained in reports. Unknown export schemas must fail closed.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import zipfile

PREFIX="/r104/api/"
ROUTES={
    "/r104/api/alpha.json":200,
    "/r104/api/beta.txt":200,
    "/r104/api/expected-404":404,
    "/r104/api/tiny.svg":200
}

def signature(url):
    if not isinstance(url,str): return None
    split=urlsplit(url)
    if split.path not in ROUTES:return None
    seq=parse_qs(split.query).get("seq",[])
    if len(seq)!=1 or not seq[0].isdigit():return None
    return (split.path, int(seq[0]))

def event_records(tree,kind=None):
    """Extract one request per row, never duplicate Trace timeline events.

    Frozen formal MV2 V0.4.58 trace-core.js KiwiTrace.view() exposes
    top-level requests and timeline; timeline can repeat a request URL.
    Reject unknown/ambiguous root structures rather than silently merging.
    """
    if kind=='trace':
        if not isinstance(tree,dict):return []
        has_requests=isinstance(tree.get('requests'),list)
        has_legacy=isinstance(tree.get('traceEvents'),list)
        if has_requests==has_legacy:return []
        tree=tree['requests'] if has_requests else tree['traceEvents']
    elif kind=='har':
        if not isinstance(tree,dict) or not isinstance(tree.get('log'),dict) or not isinstance(tree['log'].get('entries'),list):return []
        tree=tree['log']['entries']
    elif kind=='requests':
        if not isinstance(tree,list):return []
    result=[]
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
            return
        if not isinstance(value,dict):return
        url=value.get("url") or value.get("requestUrl") or value.get("request_url")
        req=value.get("request")
        if not url and isinstance(req,dict):url=req.get("url")
        sig=signature(url)
        if sig:
            response=value.get("response")
            status=value.get("status",value.get("statusCode",value.get("responseStatus")))
            if status is None and isinstance(response,dict):
                status=response.get("status",response.get("statusCode"))
            try: status=int(status) if status is not None else None
            except (TypeError,ValueError):status=None
            result.append((sig,status))
            return
        for child in value.values():walk(child)
    walk(tree)
    return result

def count_events(events):
    return collections.Counter(pair for pair,_ in events)

def _rows(counter):
    return [{"path":s[0],"seq":s[1],"count":v} for s,v in sorted(counter.items())]

def verify(zip_file,server_log,start_ns,end_ns,report_path):
    gates={};observed={}
    def gate(k,pass_condition,detail):
        gates[k]={"status":"PASS" if pass_condition else "FAIL","detail":detail}
    try:
        file_path=Path(zip_file)
        with zipfile.ZipFile(file_path) as z:
            bad=z.testzip()
            names=z.namelist()
            gate("STRICT_01_zip_integrity",bad is None and bool(names),
                 {"crc_error":bad,"entries":len(names),"sha256":hashlib.sha256(file_path.read_bytes()).hexdigest()})
            targets={}
            for kind,suffix in (("requests","requests.json"),("har",".har"),("trace","trace.json")):
                choices=[n for n in names if n.lower().endswith(suffix)]
                targets[kind]=choices[0] if len(choices)==1 else None
            gate("STRICT_02_export_structures",all(targets.values()),
                 {"present":{k:bool(v) for k,v in targets.items()}})
            for kind,target in targets.items():
                if not target:
                    observed[kind]=None
                    continue
                try:observed[kind]=event_records(json.loads(z.read(target)),kind=kind)
                except (ValueError,UnicodeError) as e:
                    observed[kind]=None
            gate("STRICT_03_all_three_json_parsed",all(v is not None for v in observed.values()),
                 {"parsed":{k:v is not None for k,v in observed.items()}})
    except (OSError,zipfile.BadZipFile,RuntimeError) as e:
        gate("STRICT_01_zip_integrity",False,{"reason":type(e).__name__})
        observed={k:None for k in ("requests","har","trace")}
    truth=[]
    try:
        for line in Path(server_log).read_text(encoding="utf8").splitlines():
            try:row=json.loads(line)
            except ValueError:continue
            ns=row.get("time_ns")
            if not isinstance(ns,int) or not start_ns<=ns<=end_ns:continue
            sig=signature(row.get("url",""))
            if sig is None:continue
            truth.append((sig,row.get("status")))
    except OSError:pass
    truth_count=count_events(truth)
    all_routes={x[0] for x in truth_count}
    seq_groups=collections.defaultdict(set)
    for path,seq in truth_count:seq_groups[seq].add(path)
    complete=sorted(seq for seq,r in seq_groups.items() if r==set(ROUTES))
    gate("STRICT_04_independent_server_truth",
         len(truth)>=8 and len(complete)>=2 and all_routes==set(ROUTES) and
         all(row_status==ROUTES[sig[0]] for sig,row_status in truth),
         {"events":len(truth),"full_sequences":complete,"routes":sorted(all_routes)})
    for kind in ("requests","har","trace"):
        events=observed.get(kind)
        name={"requests":"STRICT_05_requests_exact","har":"STRICT_06_har_exact","trace":"STRICT_07_trace_exact"}[kind]
        if not events or not truth_count:
            gate(name,False,{"reason":"Missing structured export events or independent ground truth",
                             "events":len(events or []),"host_events":len(truth)})
            continue
        export_count=count_events(events)
        missing=truth_count-export_count
        extra=export_count-truth_count
        # HAR/requests must include status to prove 200 vs expected 404.
        statuses_ok=all(status==ROUTES[sig[0]] for sig,status in events) if kind!="trace" else True
        ok=not missing and not extra and statuses_ok
        gate(name,ok,{"host_events":sum(truth_count.values()),"export_events":sum(export_count.values()),
                      "missing":_rows(missing),"extra":_rows(extra),
                      "http_statuses_complete":statuses_ok if kind!="trace" else "NOT_APPLICABLE"})
    gate("STRICT_08_three_way_exact_parity",
         all(gates.get(k,{}).get("status")=="PASS" for k in
             ("STRICT_04_independent_server_truth","STRICT_05_requests_exact",
              "STRICT_06_har_exact","STRICT_07_trace_exact")),
         {"meaning":"exact (path,seq) multiplicities in all three exports match host"})
    report={"test":"R104_full_event_network_capture","gates":gates,
            "host_events":len(truth),"validated_window_ns":[start_ns,end_ns],
            "status":{"passed":sum(v["status"]=="PASS" for v in gates.values()),
                      "failed":sum(v["status"]=="FAIL" for v in gates.values())},
            "response_bodies":"NOT_VERIFIED","timing_parity":"NOT_VERIFIED",
            "warning":"No PASS from presence-only; schema adapters require proof on real export"}
    report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True,type=Path)
    p.add_argument("--server-log",required=True,type=Path)
    p.add_argument("--start-ns",type=int,required=True)
    p.add_argument("--end-ns",type=int,required=True)
    p.add_argument("--out",required=True,type=Path)
    x=p.parse_args()
    result=verify(x.zip,x.server_log,x.start_ns,x.end_ns,x.out)
    print(json.dumps(result["status"]))
    raise SystemExit(int(result["status"]["failed"]>0))
