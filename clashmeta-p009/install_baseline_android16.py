#!/usr/bin/env python3
"""P009: install and launch the exact P004 official, unmodified CMFA APK in API36.
The P004 artifact is retrieved by GitHub Actions on the same public repository.
Never present this baseline as the protected security build.
"""
import glob
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
root=pathlib.Path("p009-evidence")
root.mkdir(exist_ok=True)
report={"stage":"P0-09", "baseline":"official unchanged CMFA 215e017ae88ac2a1edf24fdb520512c1423c89f4",
        "android_target":"API36 x86_64", "G5":"BLOCKED", "notes":["Not private enhanced build","Not a real-IP leak test"]}
def record(key,cmd,timeout=65):
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,errors="replace",timeout=timeout)
        data={"code":p.returncode,"stdout":p.stdout[-18000:],"stderr":p.stderr[-10000:],"command":cmd}
    except Exception as exc:data={"code":None,"error":repr(exc),"command":cmd}
    (root/(key+".json")).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    return data
def fail(message):
    report["result"]="FAIL"
    report["failure"]=message
    (root/"RESULT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("P009_FAIL",message)
    raise SystemExit(2)
release=record("api",["adb","shell","getprop","ro.build.version.sdk"])
if release["code"]!=0 or release["stdout"].strip()!="36":fail("API36 required")
abi=record("abi",["adb","shell","getprop","ro.product.cpu.abi"])
if abi["code"]!=0:fail("ADB ABI not available")
report["guest_abi"]=abi["stdout"].strip()
entries=list(pathlib.Path("p009-baseline").rglob("*.apk"))
if not entries:fail("Baseline artifact contains no APK")
paths=sorted(str(p) for p in entries)
report["candidate_apks"]=[{"path":x,"size":os.path.getsize(x)} for x in paths]
# Prefer emulator-native ABI, else universal. Do not force ARM-only APK.
preferred=[p for p in entries if "x86_64" in p.name.lower()]
if not preferred:preferred=[p for p in entries if "universal" in p.name.lower()]
if not preferred:preferred=[p for p in entries if "arm" not in p.name.lower()]
if not preferred:fail("No x86_64/universal artifact suitable for emulator")
apk=sorted(preferred,key=lambda x:x.stat().st_size)[-1]
report["selected_apk"]=str(apk)
h=hashlib.sha256()
with apk.open("rb") as f:
    for c in iter(lambda:f.read(1024*1024),b""):h.update(c)
report["apk_sha256"]=h.hexdigest()
known=list(pathlib.Path("p009-baseline").rglob("apk-hashes.txt"))
if not known:fail("The P004 provenance SHA256 manifest is missing")
manifest=known[0].read_text(errors="replace")
match=[line for line in manifest.splitlines() if apk.name in line and report["apk_sha256"] in line]
if not match:fail("APK sha256 mismatch vs original P004 build evidence")
report["original_manifest_line"]=match[0]
sdk=os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "/usr/local/lib/android/sdk"
aapt=sorted(pathlib.Path(sdk).glob("build-tools/*/aapt"),reverse=True)
if not aapt:fail("Android aapt missing")
badging=record("apk_badging",[str(aapt[0]),"dump","badging",str(apk)],timeout=90)
if badging["code"]!=0:fail("aapt failed on official APK")
pkgmatch=re.search(r"package: name='([^']+)'",badging["stdout"])
launchmatch=re.search(r"launchable-activity: name='([^']+)'",badging["stdout"])
if not pkgmatch:fail("No Android package in APK")
package=pkgmatch.group(1)
report["package"]=package
report["launchable_activity"]=launchmatch.group(1) if launchmatch else None
install=record("adb_install",["adb","install","-r",str(apk)],timeout=180)
report["install_succeeded"]=install["code"]==0 and "Success" in install["stdout"]
if not report["install_succeeded"]:fail("Actual API36 ADB install failed")
resolve=record("resolve_launcher",["adb","shell","cmd","package","resolve-activity","--brief",package])
if launchmatch:
    launch=record("launch",["adb","shell","am","start","-W","-n",package+"/"+launchmatch.group(1)],timeout=95)
else:
    launch=record("launch",["adb","shell","monkey","-p",package,"-c","android.intent.category.LAUNCHER","1"],timeout=95)
report["launch_command_success"]=launch["code"]==0 and ("Error" not in launch.get("stdout",""))
time.sleep(8)
process=record("pid",["adb","shell","pidof",package])
report["process_alive_after_8s"]=process["code"]==0 and bool(process["stdout"].strip())
record("activity",["adb","shell","dumpsys","activity","activities"],timeout=75)
record("vpn_state",["adb","shell","settings","get","secure","always_on_vpn_app"])
record("vpn_lockdown",["adb","shell","settings","get","secure","always_on_vpn_lockdown"])
record("logcat",["adb","logcat","-d","-t","1800"],timeout=80)
record("uia_dump",["adb","shell","uiautomator","dump","/sdcard/p009_ui.xml"],timeout=75)
record("ui_pull",["adb","pull","/sdcard/p009_ui.xml",str(root/"ui.xml")],timeout=45)
record("screenshot",["adb","shell","screencap","-p","/sdcard/p009_screen.png"])
record("screenshot_pull",["adb","pull","/sdcard/p009_screen.png",str(root/"screen.png")])
report["result"]="PASS_BASELINE_INSTALL_LAUNCH" if report["launch_command_success"] and report["process_alive_after_8s"] else "PARTIAL_APK_INSTALLED_LAUNCH_NOT_PROVEN"
(root/"RESULT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print("P009_RESULT",json.dumps(report,ensure_ascii=False))
if report["result"]!="PASS_BASELINE_INSTALL_LAUNCH":raise SystemExit(3)
