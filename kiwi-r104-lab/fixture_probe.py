#!/usr/bin/env python3
"""R104 AVD fixture transport proof. This does NOT claim the private production plugin captured the traffic."""
import json, subprocess, sys, time, hashlib
from pathlib import Path
from collections import Counter

OUT=Path("out");OUT.mkdir(exist_ok=True)
PORT=18764
URL=f"http://127.0.0.1:{PORT}/"
PKG="com.kiwibrowser.browser"
REPORT={"task":"R104_Android_real_http_ground_truth","phase":"controlled_fixture_only",
        "production_plugin_tested":False,"gates":{},"errors":[]}
def cmd(a,timeout=60):
    try:
        p=subprocess.run(a,text=True,capture_output=True,timeout=timeout)
        return p.returncode,(p.stdout or "")+"\n"+(p.stderr or "")
    except Exception as ex:return -1,str(ex)
def gate(name,ok,detail):
    REPORT["gates"][name]={"status":"PASS" if ok else "FAIL","detail":str(detail)[:1500]}
    print(("PASS " if ok else "FAIL ")+name+" "+str(detail)[:160],flush=True)
def snap(name):
    cmd(["adb","shell","uiautomator","dump","/sdcard/r104.xml"])
    rc,xml=cmd(["adb","shell","cat","/sdcard/r104.xml"])
    (OUT/(name+".xml")).write_text(xml,encoding="utf-8")
    with (OUT/(name+".png")).open("wb") as f:
        subprocess.run(["adb","exec-out","screencap","-p"],stdout=f,stderr=subprocess.DEVNULL,timeout=45)
    return xml
p=None
try:
    with (OUT/"r104_fixture_server_stdout.txt").open("w") as logfile:
        p=subprocess.Popen([sys.executable,"-u","kiwi-r104-lab/controlled_fixture_server.py",
            "--port",str(PORT),"--log",str(OUT/"r104_fixture_received.jsonl")],
            stdout=logfile,stderr=subprocess.STDOUT)
    ready=False
    for _ in range(30):
        rc,out=cmd([sys.executable,"-c",f"import urllib.request;print(urllib.request.urlopen('{URL}',timeout=2).status)"],timeout=5)
        if rc==0 and '200' in out:
            ready=True;break
        time.sleep(.4)
    gate("R104-A0_host_fixture_running",ready,"Python ThreadingHTTPServer binds localhost")
    if not ready:raise RuntimeError("fixture server inaccessible")
    rc,out=cmd(["adb","reverse",f"tcp:{PORT}",f"tcp:{PORT}"],timeout=30)
    gate("R104-A1_adb_reverse_created",rc==0,out)
    if rc!=0:raise RuntimeError("ADB reverse failed")
    rc,out=cmd(["adb","shell","am","start","-a","android.intent.action.VIEW",
                "-d",URL,PKG],timeout=30)
    gate("R104-A2_kiwi_open_intent",rc==0,"Kiwi Android VIEW "+out[:350])
    time.sleep(20)
    xml=snap("r104_real_kiwi_controlled_fixture")
    kiwi_foreground=(PKG in xml)
    gate("R104-A3_kiwi_foreground",kiwi_foreground,"Kiwi package in uiautomator XML="+str(kiwi_foreground))
    # UI accessibility may omit web body. The host request log and browser screenshot are primary facts.
    text_visible=("R104_NETWORK_FIXTURE_READY" in xml or "R104_NETWORK_TICK" in xml)
    REPORT["ui_fixture_text_seen"]=text_visible
    path=OUT/"r104_fixture_received.jsonl"
    lines=[json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    expected={"/r104/api/alpha.json":200,
              "/r104/api/beta.txt":200,
              "/r104/api/expected-404":404,
              "/r104/api/tiny.svg":200}
    events={k:[x for x in lines if x.get("path")==k] for k in expected}
    summary={k:len(v) for k,v in events.items()}
    gate("R104-A4_http_requests_really_received",all(len(v)>=2 for v in events.values()),
         "Independent host HTTP log route counts: "+json.dumps(summary))
    gate("R104-A5_status_codes_match_known_truth",
         all(v and all(e["status"]==expected[k] for e in v) for k,v in events.items()),
         "All expected 200/404 status values matched server records")
    seqs={}
    for k,v in events.items():
        seqs[k]=sorted({x["url"].split("seq=")[-1] for x in v if "seq=" in x["url"]})
    inter=set(seqs[next(iter(seqs))])
    for v in seqs.values():inter &= set(v)
    gate("R104-A6_same_sequence_cross_four_routes",len(inter)>=2,
         "All four known endpoints appeared with >=2 common browser-issued seq IDs: "+str(sorted(inter)[:10]))
    REPORT["host_received_counts"]=summary
    REPORT["common_sequences"]=sorted(inter)[:25]
    REPORT["total_requests_received"]=len(lines)
    REPORT["sha256_received_server_log"]=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    REPORT["gates"]["R104-A7_production_requests_vs_har_trace"]={
        "status":"NOT_RUN","detail":"Controlled network substrate only; formal MV2 plugin export comparison is a separate gate"}
except Exception as e:
    REPORT["errors"].append(repr(e)); print("R104_FIXTURE_EXCEPTION",repr(e),flush=True)
finally:
    if p:
        p.terminate()
        try:p.wait(timeout=8)
        except Exception:p.kill()
    (OUT/"r104_fixture_status.json").write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding="utf-8")
    failures=[name for name,v in REPORT["gates"].items() if v["status"]=="FAIL"]
    print("R104_FIXTURE_RESULTS",json.dumps({n:v["status"] for n,v in REPORT["gates"].items()}),flush=True)
    if failures or REPORT["errors"]:raise SystemExit(1)
