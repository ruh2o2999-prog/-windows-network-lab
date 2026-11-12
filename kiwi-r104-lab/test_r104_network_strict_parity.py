#!/usr/bin/env python3
"""R104 strict reconciler regressions: missing count, duplicates, seq and statuses."""
import copy
import json
from pathlib import Path
import tempfile
import zipfile
from r104_network_strict_parity import verify,ROUTES

BASE="http://127.0.0.1:18764"
WIN=(1000,2000)

def dataset():
    source=[];har=[];trace=[];host=[]
    for seq in (1,2):
        for route,status in ROUTES.items():
            url=f"{BASE}{route}?seq={seq}"
            source.append({"url":url,"status":status})
            har.append({"request":{"url":url},"response":{"status":status}})
            trace.append({"data":{"url":url},"cat":"net"})
            host.append({"time_ns":1100+seq,"url":route+f"?seq={seq}",
                         "path":route,"status":status})
    return {"requests":source,"har":har,"trace":trace,"host":host}

def run_case(root,name,variant):
    d=dataset()
    if variant=="missing_one_request":d["requests"].pop()
    elif variant=="wrong_404":
        for x in d["har"]:
            if "expected-404" in x["request"]["url"]:
                x["response"]["status"]=200;break
    elif variant=="trace_missing":d["trace"].pop()
    elif variant=="wrong_seq":d["requests"][1]["url"]=d["requests"][1]["url"].replace("seq=1","seq=9")
    elif variant=="har_duplicate":d["har"].append(copy.deepcopy(d["har"][0]))
    elif variant=="missing_server":d["host"].pop()
    elif variant=="outside_window":
        for x in d["host"]:x["time_ns"]=999
    elif variant=="missing_status":d["requests"][0].pop("status")
    elif variant=="unknown_schema":d["requests"]=[{"ambiguous":{"uri":e["url"]}} for e in d["requests"]]
    elif variant=="unrelated_noise":
        d["requests"].append({"url":"http://example.invalid/private","status":299})
        d["har"].append({"request":{"url":"https://third.invalid/other"},"response":{"status":200}})
        d["trace"].append({"data":{"url":"http://third.invalid/a"}})
    folder=root/name;folder.mkdir(parents=True)
    p=folder/"export.zip";host=folder/"received.jsonl"
    with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("current/Network/requests.json",json.dumps(d["requests"]))
        z.writestr("current/Network/network.har",json.dumps({"log":{"entries":d["har"]}}))
        z.writestr("Trace/trace.json",json.dumps({"traceEvents":d["trace"]}))
    host.write_text("\n".join(json.dumps(x) for x in d["host"])+"\n",encoding="utf8")
    return verify(p,host,*WIN,folder/"report.json")

CASES={
    "positive_exact_8_events":(None,None),
    "unrelated_noise_ignored":("unrelated_noise",None),
    "missing_one_request":("missing_one_request","STRICT_05_requests_exact"),
    "wrong_404":("wrong_404","STRICT_06_har_exact"),
    "trace_missing":("trace_missing","STRICT_07_trace_exact"),
    "wrong_seq":("wrong_seq","STRICT_05_requests_exact"),
    "har_duplicate":("har_duplicate","STRICT_06_har_exact"),
    "missing_server":("missing_server","STRICT_04_independent_server_truth"),
    "outside_window":("outside_window","STRICT_04_independent_server_truth"),
    "missing_status":("missing_status","STRICT_05_requests_exact"),
    "unknown_schema":("unknown_schema","STRICT_05_requests_exact")
}
out={}
with tempfile.TemporaryDirectory(prefix="r104_strict_") as t:
    for name,(variant,must_fail) in CASES.items():
        r=run_case(Path(t),name,variant)
        if must_fail:
            assert r["gates"][must_fail]["status"]=="FAIL",(name,r["gates"])
            assert r["gates"]["STRICT_08_three_way_exact_parity"]["status"]=="FAIL",name
        else:
            assert r["status"]=={"passed":8,"failed":0},(name,r)
        out[name]="PASS"
print("R104_STRICT_NETWORK_REGRESSIONS",json.dumps(out,ensure_ascii=False))
Path("out").mkdir(exist_ok=True)
Path("out/r104_strict_regression_results.json").write_text(json.dumps(
    {"suite":"R104 exact-network parity synthetic regression",
     "passed":len(out),"failed":0,"tests":out,
     "formal_production_export_tested":False},ensure_ascii=False,indent=2)+"\\n",encoding="utf8")
