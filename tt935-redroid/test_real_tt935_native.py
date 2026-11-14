#!/usr/bin/env python3
"""TT935 D01 native ARM ReDroid real APK smoke. No accounts or signing keys in artifacts."""
from __future__ import annotations
import hashlib,json,pathlib,subprocess,time,re,sys,xml.etree.ElementTree as ET
APP=pathlib.Path("/tmp/tt935-v045-private.apk")
BASE=pathlib.Path("out/tt935-d01-redroid-real-apk");BASE.mkdir(parents=True,exist_ok=True)
PKG="com.ss.android.article.news";ADB=["adb","-s","127.0.0.1:5555"]
EXPECTED="de6fb9acb39636d64ff9960f1f1e2d815e27a65d5a6ba28e2ca8f7e66232ed31"
R={"target":"genuine private V0.4.5 R1 APK in native ARM64 ReDroid Android11","sha256_expected":EXPECTED,"gates":{},"screens":[],"notes":["fresh app sandbox, no user login/state imported"]}
def run(name,args,timeout=90):
 try:
  p=subprocess.run([*ADB,*args],capture_output=True,timeout=timeout)
  data=(p.stdout+p.stderr).decode("utf-8",errors="replace")
  (BASE/(name+".log")).write_text(data[-180000:],encoding="utf-8")
  return p.returncode,data
 except Exception as e:
  (BASE/(name+".log")).write_text(repr(e))
  return 98,repr(e)
def gate(key,ok,note):
 R["gates"][key]={"pass":bool(ok),"detail":str(note)[:500]}
 (BASE/"result.json").write_text(json.dumps(R,ensure_ascii=False,indent=2))
def screenshot(label):
 c,xml=run("ui_dump_"+label,["shell","uiautomator","dump","/sdcard/tt935-ui.xml"],timeout=100)
 c,xml=run("ui_read_"+label,["exec-out","cat","/sdcard/tt935-ui.xml"],timeout=40)
 # Capture only a list of visible strings, no full private UI database.
 try:
  node=ET.fromstring(xml)
  texts=[(e.attrib.get("text") or e.attrib.get("content-desc") or "") for e in node.iter("node")]
  texts=[t[:160] for t in texts if t]
  (BASE/(label+"-visible-texts.txt")).write_text("\n".join(texts[-100:]))
 except Exception as e: R.setdefault("capture_errors",[]).append(f"XML {label}: {e!r}")
 try:
  p=subprocess.run([*ADB,"exec-out","screencap","-p"],capture_output=True,timeout=45)
  if p.returncode==0 and p.stdout.startswith(b"\x89PNG"):
   (BASE/(label+".png")).write_bytes(p.stdout);R["screens"].append(label+".png")
 except Exception as e: R.setdefault("capture_errors",[]).append(f"PNG {label}: {e!r}")
def collect_crash():
 _,out=run("crash_buffer",["logcat","-b","crash","-d","-v","threadtime"],timeout=55)
 _,log=run("logcat_full_temp",["logcat","-d","-v","threadtime"],timeout=80)
 matches=[l[:900] for l in log.splitlines() if any(x in l.lower() for x in
  ("com.ss.android.article.news","metasec_ml","jni_onload","fatal exception","fatal signal",
   "signal 6 (sigabrt)","crash_dump","tombstoned","ndk_translation","unsatisfiedlinkerror","androidruntime"))]
 (BASE/"filtered_fatal_context.log").write_text("\n".join(matches[-300:])[-100000:],encoding="utf-8")
 (BASE/"logcat_full_temp.log").unlink(missing_ok=True)
 return out,matches
try:
 assert APP.is_file()
 digest=hashlib.sha256(APP.read_bytes()).hexdigest()
 gate("D01-00-ENCRYPTED-APK-VERIFIED",digest==EXPECTED,digest)
 if digest!=EXPECTED:raise RuntimeError("SHA mismatch; do not install")
 _,boot=run("boot",["shell","getprop","sys.boot_completed"])
 _,abi=run("abi",["shell","getprop","ro.product.cpu.abilist"])
 _,bridge=run("native_bridge",["shell","getprop","ro.dalvik.vm.native.bridge"])
 _,ver=run("android_release",["shell","getprop","ro.build.version.release"])
 R["device"]={"boot":boot.strip(),"abi":abi.strip(),"native_bridge":bridge.strip(),"android":ver.strip()}
 gate("D01-01-TRUE-ARM32-ENV",boot.strip()=="1" and "armeabi-v7a" in abi and "x86" not in abi and bridge.strip() in ("0",""),R["device"])
 if not R["gates"]["D01-01-TRUE-ARM32-ENV"]["pass"]:raise RuntimeError("not native arm compatible")
 c,msg=run("install",["install","-r",str(APP)],timeout=230)
 gate("D01-02-REAL-APK-INSTALL",c==0 and "Success" in msg,msg)
 if not R["gates"]["D01-02-REAL-APK-INSTALL"]["pass"]:raise RuntimeError("install error")
 _,p=run("package_abi",["shell","dumpsys","package",PKG],timeout=65)
 abi_lines=[x.strip() for x in p.splitlines() if "primaryCpuAbi=" in x or "secondaryCpuAbi=" in x or "versionName=" in x]
 R["installed_package_summary"]=abi_lines[:12]
 gate("D01-03-PACKAGE-ABI-ARM",any("armeabi-v7a" in x for x in abi_lines),abi_lines[:5])
 perms=["ACCESS_FINE_LOCATION","ACCESS_COARSE_LOCATION","CAMERA","RECORD_AUDIO"]
 # Match *declared* permissions, not incidental AppOps or system descriptions.
 declared=p.split("requested permissions:")[-1].split("install permissions:")[0] if "requested permissions:" in p else ""
 present={x:("android.permission."+x in declared) for x in perms}
 gate("C01-C03-NO-SENSITIVE-DECLARED",not any(present.values()),present)
 _,widgets=run("widgets",["shell","dumpsys","appwidget"],timeout=65)
 found=[x[:260] for x in widgets.splitlines() if PKG in x]
 gate("G02-NO-REGISTERED-WIDGETS",len(found)==0,f"matching provider lines={len(found)}")
 # ReDroid has no physical navigation keys. Monkey exits before injecting events.
 # Launch the actual MAIN/LAUNCHER activity discovered by reading V0.4.5 AndroidManifest.xml.
 component=PKG+"/.activity.MainActivity"
 c,launch=run("launch",["shell","am","start","-W","-n",component],timeout=105)
 good=(c==0 and "Error:" not in launch and ("Status: ok" in launch or "Starting:" in launch or "Activity not started" in launch))
 gate("D01-04-EXPLICIT-ACTIVITY-START",good,launch[-850:])
 time.sleep(8);screenshot("initial")
 for i in range(3):
  run(f"foreground_{i}",["shell","dumpsys","activity","activities"],timeout=60)
  time.sleep(10);screenshot(f"after_{i}")
 _,pid=run("pidof",["shell","pidof",PKG],timeout=30)
 R["process_alive_after_40sec"]=bool(pid.strip())
 crash,context=collect_crash()
 is_crash= any(("FATAL EXCEPTION" in l or "Fatal signal" in l or "SIGABRT" in l or "SIGSEGV" in l) for l in context)
 gate("D01-05-PROCESS-ALIVE-AND-NO-CRASH",bool(pid.strip()) and not is_crash,
  f"pid={pid.strip()}, crash_lines={len(context)}, crash_buffer_bytes={len(crash)}")
 gate("A01-A03-FEED-VISUAL",False,"NOT VERIFIED: screenshots require actual home and article rendered")
 gate("E01-USER-LOGIN-STATE",False,"NOT RUN: no user private login data brought into emulator")
except Exception as e:
 R.setdefault("errors",[]).append(repr(e))
finally:
 R["run_exit"]="PASS_INSTALL_AND_STABILITY" if R["gates"].get("D01-05-PROCESS-ALIVE-AND-NO-CRASH",{}).get("pass") else "FAIL_OR_PARTIAL"
 (BASE/"result.json").write_text(json.dumps(R,ensure_ascii=False,indent=2))
 print("TT935_D01_REDDROID_REAL_RESULT="+json.dumps(R,ensure_ascii=False))
 if not R["gates"].get("D01-02-REAL-APK-INSTALL",{}).get("pass"):sys.exit(8)
 if not R["gates"].get("D01-05-PROCESS-ALIVE-AND-NO-CRASH",{}).get("pass"):sys.exit(7)
