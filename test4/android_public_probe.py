#!/usr/bin/env python3
"""V8.13-TEST4 Android genuine emulator smoke: official Kiwi public APK; never a private project G5."""
import os,json,subprocess,time,re,hashlib
from pathlib import Path
OUT=Path("out"); OUT.mkdir(exist_ok=True)
PACKAGE="com.kiwibrowser.browser"
st={"schema":"v813-test4-real-android-v1","api_requested":os.getenv("TEST4_API","unknown"),
    "source":"official Kiwi x64 GitHub release via existing download_kiwi.py",
    "scope":"public app environment smoke; not private plugin or final product functionality","gates":{}}
def call(*cmd,timeout=120):
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        return r.returncode,(r.stdout or "")+"\n"+(r.stderr or "")
    except Exception as e:return -1,repr(e)
def gate(name,good,detail):
    st["gates"][name]={"status":"PASS" if good else "FAIL","detail":str(detail)[-750:]}
    print(name,st["gates"][name]["status"],flush=True)
def snapshot(tag):
    with (OUT/(tag+".png")).open("wb") as f:
        try:subprocess.run(["adb","exec-out","screencap","-p"],stdout=f,timeout=30,check=True)
        except Exception as e: st.setdefault("errors",[]).append(repr(e))
    rc,txt=call("adb","shell","uiautomator","dump","/sdcard/uidump.xml",timeout=50)
    rc,xml=call("adb","shell","cat","/sdcard/uidump.xml")
    (OUT/(tag+".xml")).write_text(xml,encoding="utf8")
def main():
    rc,boot=call("adb","shell","getprop","sys.boot_completed")
    gate("android_boot",rc==0 and boot.strip()=="1",boot)
    rc,api=call("adb","shell","getprop","ro.build.version.sdk")
    st["actual_api"]=api.strip()
    gate("api_matches",rc==0 and api.strip()==os.getenv("TEST4_API"),api)
    apk=Path("kiwi-official-x64.apk")
    gate("official_apk_present",apk.exists() and apk.stat().st_size>15000000,"size="+str(apk.stat().st_size if apk.exists() else 0))
    if not apk.exists():return
    st["official_apk_sha256"]=hashlib.sha256(apk.read_bytes()).hexdigest()
    rc,txt=call("adb","install","-r",str(apk),timeout=240)
    gate("app_install",rc==0 and "Success" in txt,txt)
    if rc:return
    rc,pkg=call("adb","shell","pm","path",PACKAGE)
    gate("package_registered",rc==0 and "package:" in pkg,pkg)
    rc,launch=call("adb","shell","monkey","-p",PACKAGE,"-c","android.intent.category.LAUNCHER","1",timeout=80)
    time.sleep(8)
    rc,activity=call("adb","shell","dumpsys","activity","activities",timeout=60)
    launched=rc==0 and PACKAGE in activity and "Events injected" in launch
    gate("app_launch",launched,launch+" "+activity[-400:])
    snapshot("launch")
    rc,net=call("adb","shell","am","start","-a","android.intent.action.VIEW","-d","https://example.com",PACKAGE)
    time.sleep(6)
    snapshot("network")
    gate("browser_https_request_dispatched",rc==0,net)
    rc,stop=call("adb","shell","am","force-stop",PACKAGE)
    rc,second=call("adb","shell","monkey","-p",PACKAGE,"-c","android.intent.category.LAUNCHER","1",timeout=90)
    time.sleep(5)
    rc,after=call("adb","shell","dumpsys","activity","activities",timeout=60)
    gate("relaunch_after_force_stop",rc==0 and PACKAGE in after and "Events injected" in second,second+" "+after[-300:])
    snapshot("relaunch")
    st["limits"]=["No private APK/plugin installed","No network response body was independently checked","No product end-to-end G5","No exact Win7 compatibility implication"]
try:main()
except Exception as e:
    st.setdefault("errors",[]).append(repr(e))
finally:
    st["status"]="PASS" if all(x["status"]=="PASS" for x in st["gates"].values()) else "FAIL"
    (OUT/"test4_android_status.json").write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding="utf8")
    print("TEST4_ANDROID",st["status"],flush=True)
    raise SystemExit(0 if st["status"]=="PASS" else 2)
