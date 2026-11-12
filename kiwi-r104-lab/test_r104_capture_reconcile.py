#!/usr/bin/env python3
"""R104 10-gate reconciler synthetic regression: positive + known negatives."""
import json, tempfile, zipfile, sys
from pathlib import Path
from r104_capture_reconcile import reconcile,ROUTES

BASE="http://127.0.0.1:18764"
def run_one(root,kind):
    root.mkdir(parents=True,exist_ok=True)
    url=lambda r: BASE+r+"?seq=1"
    reqs=[{"url":url(r),"status":s} for r,s in ROUTES.items()]
    entries=[{"request":{"url":url(r)},"response":{"status":s}} for r,s in ROUTES.items()]
    trace={"events":[{"url":url(r)} for r in ROUTES]}
    if kind=="missing_requests":reqs=reqs[:-1]
    if kind=="wrong_404":
        for e in entries:
            if 'expected-404' in e["request"]["url"]:e["response"]["status"]=200
    if kind=="missing_trace_url":trace["events"]=trace["events"][:-1]
    zfile=root/"captured.zip"
    with zipfile.ZipFile(zfile,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr("current/Network/requests.json",json.dumps(reqs))
        z.writestr("current/Network/network.har",json.dumps({"log":{"entries":entries}}))
        z.writestr("Trace/trace.json",json.dumps(trace))
    lines=[]
    for seq in (1,2):
        for path,status in ROUTES.items():
            if kind=="host_missing" and path=="/r104/api/beta.txt":continue
            if kind=="host_status_wrong" and path=="/r104/api/expected-404":status=200
            lines.append({"time_ns":1000+seq,"path":path,"url":path+"?seq="+str(seq),"status":status})
    host=root/"host.jsonl"
    host.write_text("\n".join(json.dumps(x) for x in lines))
    return reconcile(zfile,host,1000,2000,root/"out.json")

results={}
with tempfile.TemporaryDirectory(prefix="kiwi_r104_reconcile_") as tmp:
    root=Path(tmp)
    good=run_one(root/"positive","positive")
    assert good["summary"]=={"passed":10,"failed":0},good
    results["positive_10_of_10"]="PASS"
    tests=[
        ("missing_requests","R104_NET_04_requests_json_routes"),
        ("wrong_404","R104_NET_06_har_404_response_status"),
        ("missing_trace_url","R104_NET_07_trace_routes"),
        ("host_missing","R104_NET_09_independent_server_requests_during_observation"),
        ("host_status_wrong","R104_NET_10_server_200_404_status")]
    for name,expected_fail in tests:
        report=run_one(root/name,name)
        assert report["gates"][expected_fail]["status"]=="FAIL",(name,report)
        assert report["summary"]["failed"]>=1,report
        results[name+"_correctly_rejected"]="PASS"
print("R104_RECONCILER_SYNTHETIC_VALIDATION",json.dumps(results,sort_keys=True),flush=True)
