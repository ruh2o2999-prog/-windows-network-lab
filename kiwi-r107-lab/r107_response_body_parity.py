#!/usr/bin/env python3
"""R107 independent *formal* Kiwi MV2 response byte audit.
The server's body SHA-256 is computed from actual response bytes before send.
The browser archive's CDP binary chunks are separately hashed and compared.
No URL-set-only, page-reported body, HAR metadata, or synthetic index passes.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import urllib.parse
import zipfile

ROUTES={
    "/r104/api/alpha.json":200,
    "/r104/api/beta.txt":200,
    "/r104/api/expected-404":404,
    "/r104/api/tiny.svg":200,
}
def signature(url):
    if not isinstance(url,str): return None
    p=urllib.parse.urlsplit(url)
    if p.path not in ROUTES:return None
    values=urllib.parse.parse_qs(p.query).get("seq")
    if not values or len(values)!=1 or not values[0].isdigit():return None
    return p.path,int(values[0])
def sha(data):return hashlib.sha256(data).hexdigest()

def verify(export_zip,server_jsonl,start_ns,end_ns,report_path,controlled_zip=None,min_events=36):
    gates={};details={};truth=[];indexed=[];refs=[]
    def gate(name,condition,info):
        gates[name]={"status":"PASS" if condition else "FAIL","detail":info}
        return condition
    def count(rows):return collections.Counter(x["signature"] for x in rows)
    try:
        for line in pathlib.Path(server_jsonl).read_text(encoding="utf-8").splitlines():
            try:r=json.loads(line)
            except ValueError:continue
            ns=r.get("time_ns")
            if not isinstance(ns,int) or not start_ns<=ns<=end_ns:continue
            sig=signature(r.get("url"))
            if sig is not None:
                truth.append({"signature":sig,"status":r.get("status"),"bytes":r.get("bytes"),
                              "sha256":r.get("body_sha256"),"time_ns":ns})
    except OSError:pass
    tc=count(truth)
    seqs=collections.defaultdict(set)
    for path,seq in tc:seqs[seq].add(path)
    full=[seq for seq,paths in seqs.items() if paths==set(ROUTES)]
    strong=(len(truth)>=min_events and len(full)>=min_events//4 and
            len(tc)==len(truth) and all(r["status"]==ROUTES[r["signature"][0]] and
            isinstance(r["sha256"],str) and len(r["sha256"])==64 and
            isinstance(r["bytes"],int) for r in truth))
    gate("R107_01_independent_server_bytes",strong,
         {"server_events":len(truth),"complete_sequences":sorted(full),
          "unique_signatures":len(tc),"sha256_from_server_response_bytes":True})
    archive_ok=False;index_ok=False;missing=[];unmatched=[];invalid=[];source_mismatch=[]
    zip_fingerprint=None;zip_members=0;filtered_bytes={}
    try:
        export_path=pathlib.Path(export_zip)
        zip_fingerprint=sha(export_path.read_bytes())
        with zipfile.ZipFile(export_path) as z:
            archive_ok=z.testzip() is None
            zip_members=len(z.namelist())
            names=z.namelist()
            if names.count("Network/cdp_response_index.json")!=1:
                raise ValueError("Missing/ambiguous original CDP response index")
            rows=json.loads(z.read("Network/cdp_response_index.json"))
            if not isinstance(rows,list):raise ValueError("CDP index not a list")
            index_ok=True
            for row in rows:
                if not isinstance(row,dict):continue
                sig=signature(row.get("url"))
                if sig is None:continue
                src=row.get("source")
                unique=row.get("key")
                rid=row.get("requestId")
                if src!="cdp-network-getResponseBody" or not isinstance(rid,str) or not rid or not isinstance(unique,str):
                    source_mismatch.append({"signature":sig,"reason":"Untrusted/non-CDP source or missing requestId/key"})
                body_path=row.get("bodyPath")
                item={"signature":sig,"status":row.get("status"),"requestId":rid,
                      "key":unique,"tabId":row.get("tabId"),"session":row.get("captureSessionId"),
                      "instance":row.get("captureInstanceId"),"cdpSessionId":row.get("cdpSessionId"),
                      "redirectOrdinal":row.get("redirectOrdinal"),
                      "bodyStatus":row.get("bodyStatus"),"path":body_path,
                      "declaredSha":row.get("sha256"),"declaredBytes":row.get("capturedBytes"),
                      "source":src,"exportVerified":row.get("exportVerified"),
                      "rawWireBytes":row.get("rawWireBytes")}
                if (not isinstance(body_path,str) or body_path not in names or
                        not body_path.startswith("Network/cdp_responses/") or
                        names.count(body_path)!=1):
                    missing.append(sig)
                    item["actualSha"]=None;item["actualBytes"]=None
                else:
                    b=z.read(body_path)
                    filtered_bytes[body_path]=b
                    item["actualSha"]=sha(b);item["actualBytes"]=len(b)
                indexed.append(item)
    except (OSError,ValueError,zipfile.BadZipFile,TypeError) as e:
        invalid.append(str(e))
    gate("R107_02_real_export_zip_and_original_index",archive_ok and index_ok and zip_members>=10,
         {"crc_ok":archive_ok,"index_present":index_ok,"members":zip_members,
          "zip_sha256":zip_fingerprint,"errors":invalid})
    ic=count(indexed)
    missed=tc-ic;extra=ic-tc
    gate("R107_03_exact_request_multiset",strong and not missed and not extra and
         len(indexed)==len(truth),
         {"server":len(truth),"cdp":len(indexed),
          "missing":[{"path":p,"seq":s,"n":n} for (p,s),n in missed.items()],
          "extra":[{"path":p,"seq":s,"n":n} for (p,s),n in extra.items()]})
    ids=[(r["session"],r["instance"],r["cdpSessionId"],r["requestId"],r["redirectOrdinal"])
         for r in indexed]
    single_session=len({(r["session"],r["instance"],r["tabId"]) for r in indexed})==1
    unique_ids=len(ids)==len(set(ids)) and len({r["key"] for r in indexed})==len(indexed)
    gate("R107_04_cdp_request_identity",len(indexed)>=min_events and single_session and unique_ids and
         not source_mismatch and all(r["redirectOrdinal"]==0 for r in indexed),
         {"unique_request_ids":unique_ids,"one_capture_session":single_session,
          "non_cdp_sources":source_mismatch[:10]})
    for item in indexed:
        target=[r for r in truth if r["signature"]==item["signature"]]
        if len(target)!=1:
            invalid.append({"signature":item["signature"],"reason":"server duplicate/missing"})
            continue
        r=target[0]
        match=(item["bodyStatus"]=="captured_complete" and
               item["exportVerified"] is True and
               item["rawWireBytes"] is False and
               item["status"]==r["status"] and
               item["actualSha"]==r["sha256"]==item["declaredSha"] and
               item["actualBytes"]==r["bytes"]==item["declaredBytes"])
        if not match:
            invalid.append({"signature":item["signature"],"status":item["status"],"serverStatus":r["status"],
                            "declared":item["declaredSha"],"actual":item["actualSha"],
                            "server":r["sha256"],"actualBytes":item["actualBytes"],
                            "expectedBytes":r["bytes"],"bodyStatus":item["bodyStatus"]})
    valid=not invalid and not missing and not source_mismatch and len(indexed)>=min_events
    gate("R107_05_cdp_binary_sha256_matches_independent_server",valid,
         {"checked":len(indexed),"mismatches":invalid[:15],"missing_paths":missing[:15]})
    bad404=[r for r in indexed if r["signature"][0]=="/r104/api/expected-404" and r["status"]!=404]
    n404=sum(x["signature"][0]=="/r104/api/expected-404" for x in indexed)
    gate("R107_06_404_body_and_status_exact",n404>=min_events//4 and not bad404 and valid,
         {"http404_bodies":n404,"mismatches":bad404[:10]})
    gate("R107_07_no_url_only_or_page_report_substitution",
         valid and all(r["source"]=="cdp-network-getResponseBody" and r["actualBytes"] is not None for r in indexed),
         {"all_real_binary_body_paths":len(indexed),"source":"CDP Network.getResponseBody; not raw compressed wire bytes"})
    overall=all(g["status"]=="PASS" for g in gates.values())
    if controlled_zip and overall:
        allowed={r["path"] for r in indexed}
        restricted=[{"key":r["key"],"captureSessionId":r["session"],"captureInstanceId":r["instance"],
                     "cdpSessionId":r["cdpSessionId"],"tabId":r["tabId"],
                     "requestId":r["requestId"],"redirectOrdinal":r["redirectOrdinal"],
                     "url":"http://127.0.0.1:18764"+r["signature"][0]+"?seq="+str(r["signature"][1]),
                     "status":r["status"],"source":r["source"],
                     "sha256":r["declaredSha"],"capturedBytes":r["declaredBytes"],
                     "bodyPath":r["path"],"bodyStatus":r["bodyStatus"],
                     "exportVerified":True,"rawWireBytes":False} for r in indexed]
        out=pathlib.Path(controlled_zip);out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("Network/cdp_response_index.json",json.dumps(restricted,ensure_ascii=False,indent=2))
            for path in sorted(allowed):z.writestr(path,filtered_bytes[path])
            z.writestr("R107/independent_server_controlled_only.json",json.dumps(truth,ensure_ascii=False,indent=2))
        details["synthetic_only_repro_zip"]={"path":out.name,"bytes":out.stat().st_size,"sha256":sha(out.read_bytes())}
    report={"scope":"formal MV2 V0.4.58 + actual Android Kiwi, controlled localhost fixture only",
            "gates":gates,"summary":{"passed":sum(x["status"]=="PASS" for x in gates.values()),
                                      "failed":sum(x["status"]=="FAIL" for x in gates.values())},
            "raw_wire_equivalence":"NOT_CLAIMED","response_scope":"browser-visible decoded body",
            "full_original_export_not_uploaded_publicly":True,
            "repro":details}
    out=pathlib.Path(report_path);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True)
    p.add_argument("--server-log",required=True)
    p.add_argument("--start-ns",type=int,required=True)
    p.add_argument("--end-ns",type=int,required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--controlled-zip")
    p.add_argument("--min-events",type=int,default=36)
    a=p.parse_args()
    v=verify(a.zip,a.server_log,a.start_ns,a.end_ns,a.out,a.controlled_zip,a.min_events)
    print("R107_RESPONSE_BODY_PARITY",json.dumps(v["summary"]))
    raise SystemExit(int(v["summary"]["failed"]>0))
