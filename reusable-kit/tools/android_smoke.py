#!/usr/bin/env python3
"""Reusable real Android APK install / boot / UI evidence probe (not functional acceptance)."""
import argparse, json, hashlib, subprocess, time
from pathlib import Path
def call(args,timeout=150):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    return p.returncode,(p.stdout or "")+"\n"+(p.stderr or "")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--apk",required=True,type=Path)
    ap.add_argument("--package",required=True)
    ap.add_argument("--out",type=Path,default=Path("out"))
    ap.add_argument("--url",default="")
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    state={"package":a.package,"gates":{},"functional_business_verified":False}
    def gate(k,ok,e):
        state["gates"][k]={"status":"PASS" if ok else "FAIL","evidence":str(e)[:1000]}
        print(k,state["gates"][k]["status"],flush=True)
    rc,out=call(["adb","shell","getprop","sys.boot_completed"])
    gate("ANDROID_BOOTED",rc==0 and out.strip()=="1",out)
    if not a.apk.is_file():
        gate("APK_PRESENT",False,"Missing "+str(a.apk))
    else:
        state["apk_sha256"]=hashlib.sha256(a.apk.read_bytes()).hexdigest()
        gate("APK_PRESENT",True,"bytes="+str(a.apk.stat().st_size))
        rc,out=call(["adb","install","-r",str(a.apk)],240)
        gate("APK_INSTALL",rc==0 and "Success" in out,out)
        rc,out=call(["adb","shell","pm","path",a.package])
        gate("PACKAGE_REGISTERED",rc==0 and "package:" in out,out)
        rc,out=call(["adb","shell","monkey","-p",a.package,"-c","android.intent.category.LAUNCHER","1"])
        time.sleep(5)
        gate("LAUNCH_INTENT",rc==0 and "Events injected" in out,out)
        if a.url:
            rc,out=call(["adb","shell","am","start","-a","android.intent.action.VIEW","-d",a.url,a.package])
            time.sleep(6)
            gate("BROWSER_VIEW_INTENT",rc==0,out)
        call(["adb","shell","uiautomator","dump","/sdcard/universal_smoke.xml"],40)
        rc,xml=call(["adb","shell","cat","/sdcard/universal_smoke.xml"],40)
        (a.out/"ui.xml").write_text(xml,encoding="utf8")
        with (a.out/"screen.png").open("wb") as f:
            subprocess.run(["adb","exec-out","screencap","-p"],stdout=f,timeout=30)
        gate("UI_EVIDENCE",rc==0 and "<hierarchy" in xml,"XML and screenshot saved")
    (a.out/"smoke_status.json").write_text(json.dumps(state,indent=2,ensure_ascii=False))
    return 0 if all(g["status"]=="PASS" for g in state["gates"].values()) else 1
if __name__=="__main__":raise SystemExit(main())
