#!/usr/bin/env python3
"""PROBE evidence-only reconciler for real production MV2 browser export.
The host-side HTTP server is the independent ground truth.
Never report full success for ZIP members' presence alone.
"""
import json, hashlib, zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

FIXTURE_PREFIX="/probe/api/"
ROUTES={"/probe/api/alpha.json":200, "/probe/api/beta.txt":200,
        "/probe/api/expected-404":404, "/probe/api/tiny.svg":200}

def _paths(text):
    # This counts deterministic probe paths only; no user or private URLs are copied.
    return {route for route in ROUTES if route in text}

def _urls(value):
    output=[]
    if isinstance(value,dict):
        for k,v in value.items():
            if k.lower() in ("url","requesturl","request_url","href") and isinstance(v,str) and FIXTURE_PREFIX in v:
                output.append(v)
            output+=_urls(v)
    elif isinstance(value,list):
        for x in value:output+=_urls(x)
    return output

def reconcile(zip_path, server_log_path, start_ns, end_ns, out_path):
    report={"phase":"PROBE_formal_MV2_controlled_network_capture","gates":{},
            "start_ns":start_ns,"end_ns":end_ns,"note":"Only synthetic PROBE fixture paths are retained"}
    def gate(n,ok,details):
        report["gates"][n]={"status":"PASS" if ok else "FAIL","details":details}
    if not Path(zip_path).is_file():
        gate("PROBE_NET_01_export_file_present",False,"formal browser export ZIP missing")
        out_path.write_text(json.dumps(report,indent=2))
        return report
    with zipfile.ZipFile(zip_path) as z:
        members=z.namelist(); bad=z.testzip()
        gate("PROBE_NET_01_export_file_present",bad is None,{"entries":len(members),"crc_error":bad,
              "sha256":hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()})
        def target(suffix):
            return next((x for x in members if x.lower().endswith(suffix.lower())),None)
        reqfile=target("requests.json");harfile=target(".har");tracefile=target("trace.json")
        gate("PROBE_NET_02_three_export_structures_present",bool(reqfile and harfile and tracefile),
             {"requests":reqfile,"har":harfile,"trace":tracefile})
        parsed={}; urls={}
        for kind,member in (("requests",reqfile),("har",harfile),("trace",tracefile)):
            try: parsed[kind]=json.loads(z.read(member)) if member else None
            except Exception as e: parsed[kind]=None;report.setdefault("errors",[]).append(kind+":"+repr(e))
            urls[kind]=_urls(parsed[kind]) if parsed[kind] is not None else []
        gate("PROBE_NET_03_all_json_parse",all(v is not None for v in parsed.values()),
             {"requests_valid":parsed["requests"] is not None,"har_valid":parsed["har"] is not None,
              "trace_valid":parsed["trace"] is not None})
        har_entries=(parsed["har"] or {}).get("log",{}).get("entries",[]) if isinstance(parsed["har"],dict) else []
        har_urls=[entry.get("request",{}).get("url","") for entry in har_entries if isinstance(entry,dict)]
        har_routes=_paths("\n".join(har_urls))
        request_routes=_paths("\n".join(urls["requests"]))
        trace_routes=_paths("\n".join(urls["trace"]))
        report["export_route_counts"]={
            "requests":dict(Counter(urlsplit(x).path for x in urls["requests"] if FIXTURE_PREFIX in x)),
            "har":dict(Counter(urlsplit(x).path for x in har_urls if FIXTURE_PREFIX in x)),
            "trace":dict(Counter(urlsplit(x).path for x in urls["trace"] if FIXTURE_PREFIX in x))}
        gate("PROBE_NET_04_requests_json_routes",request_routes==set(ROUTES),
             {"observed":sorted(request_routes),"missing":sorted(set(ROUTES)-request_routes)})
        gate("PROBE_NET_05_har_routes",har_routes==set(ROUTES),
             {"observed":sorted(har_routes),"missing":sorted(set(ROUTES)-har_routes)})
        har_404=[entry for entry in har_entries if isinstance(entry,dict) and
                 "/probe/api/expected-404" in entry.get("request",{}).get("url","") and
                 entry.get("response",{}).get("status")==404]
        gate("PROBE_NET_06_har_404_response_status",bool(har_404),
             {"404_entries":len(har_404)})
        gate("PROBE_NET_07_trace_routes",trace_routes==set(ROUTES),
             {"observed":sorted(trace_routes),"missing":sorted(set(ROUTES)-trace_routes)})
        gate("PROBE_NET_08_3way_fixture_coverage",
             request_routes==har_routes==trace_routes==set(ROUTES),
             {"requests":sorted(request_routes),"har":sorted(har_routes),"trace":sorted(trace_routes)})
    hits=[]
    if Path(server_log_path).exists():
        for line in Path(server_log_path).read_text().splitlines():
            try:
                v=json.loads(line)
                if start_ns<=v.get("time_ns",0)<=end_ns and v.get("path") in ROUTES:
                    hits.append(v)
            except Exception:pass
    counts=Counter(x["path"] for x in hits)
    gate("PROBE_NET_09_independent_server_requests_during_observation",
         all(counts[x]>=2 for x in ROUTES),
         {"during_observe":dict(counts),"expected_routes":sorted(ROUTES)})
    gate("PROBE_NET_10_server_200_404_status",bool(hits) and all(x["status"]==ROUTES[x["path"]] for x in hits),
         {"events":len(hits),"expected_status":ROUTES})
    report["host_route_counts"]=dict(counts)
    report["summary"]={"passed":sum(v["status"]=="PASS" for v in report["gates"].values()),
                       "failed":sum(v["status"]=="FAIL" for v in report["gates"].values())}
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report
