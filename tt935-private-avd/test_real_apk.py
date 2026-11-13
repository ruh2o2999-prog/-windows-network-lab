#!/usr/bin/env python3
"""Run the REAL private signed Toutiao APK on a real Android emulator.
No app plaintext, signed-download URL, or private key in committed code/artifacts.
Do not sign in with an account or interact with user data.
"""
import datetime,hashlib,json,pathlib,re,subprocess,time,xml.etree.ElementTree as ET
APK=pathlib.Path("/tmp/tt935-v041-private.apk")
OUT=pathlib.Path("out/tt935-v041-real-avd");OUT.mkdir(parents=True,exist_ok=True)
PKG="com.ss.android.article.news"
R={"tested_apk":"REAL TT935 V0.4.1 signed APK (private encrypted transport)",
   "sha256":hashlib.sha256(APK.read_bytes()).hexdigest(),"android":{},"steps":{},"images":[]}
def adb(*args, timeout=80):
 try:
  p=subprocess.run(["adb",*args],capture_output=True,timeout=timeout)
  return p.returncode,(p.stdout+p.stderr).decode("utf-8",errors="replace")
 except Exception as e:return 99,str(e)
def save(name,txt): (OUT/name).write_text(str(txt),encoding="utf-8",errors="replace")
def record(name,ok,detail):
 R["steps"][name]={"pass":bool(ok),"detail":str(detail)[:650]}
 (OUT/"result.json").write_text(json.dumps(R,ensure_ascii=False,indent=2))
def snapshot(label):
 _,out=adb("shell","uiautomator","dump","/sdcard/uix.xml",timeout=85)
 code,xml=adb("exec-out","cat","/sdcard/uix.xml",timeout=55)
 save(f"{label}.xml",xml)
 nodes=[]
 try:
  r=ET.fromstring(xml)
  nodes=[e.attrib for e in r.iter("node") if e.attrib.get("text") or e.attrib.get("content-desc")]
 except Exception as e:R.setdefault("errors",[]).append(f"{label} XML parse: "+str(e))
 p=subprocess.run(["adb","exec-out","screencap","-p"],capture_output=True,timeout=40)
 if p.returncode==0 and p.stdout.startswith(b"\x89PNG"):
  (OUT/f"{label}.png").write_bytes(p.stdout);R["images"].append(label+".png")
 save(f"{label}-texts.txt","\n".join((n.get("text") or n.get("content-desc") or "") for n in nodes))
 return nodes
def press_dialog(nodes):
 # Only positive consent/continue/acknowledgement, never dangerous permissions.
 targets=["同意","确认","确定","知道了","我知道了","继续使用","继续","Allow","OK","Agree","Continue","接受","已阅读并同意"]
 for target in targets:
  for n in nodes:
   v=(n.get("text") or n.get("content-desc") or "").strip()
   if v.lower()!=target.lower():continue
   b=re.findall(r"\d+",n.get("bounds",""))
   if len(b)==4:
    a,b1,c,d=map(int,b)
    adb("shell","input","tap",str((a+c)//2),str((b1+d)//2))
    time.sleep(3)
    return target
 return None
try:
 _,release=adb("shell","getprop","ro.build.version.release")
 _,abi=adb("shell","getprop","ro.product.cpu.abilist")
 _,boot=adb("shell","getprop","sys.boot_completed")
 R["android"]={"release":release.strip(),"abi":abi.strip()}
 record("EMULATOR-BOOT",boot.strip()=="1",R["android"])
 code,install=adb("install","-r",str(APK),timeout=185)
 save("install.log",install)
 record("TT05-REAL-INSTALL",code==0 and "Success" in install,install)
 if code!=0:raise RuntimeError("install failed: "+install[:200])
 _,perms=adb("shell","dumpsys","package",PKG,timeout=70)
 # Only preserve named policy statuses, never dump all app data.
 banned=["android.permission.ACCESS_FINE_LOCATION","android.permission.ACCESS_COARSE_LOCATION","android.permission.CAMERA","android.permission.RECORD_AUDIO"]
 reported={x: (bool(re.search(r"^\s*"+re.escape(x)+r"\s*:",perms,re.M))) for x in banned}
 R["permission_not_declared"]=reported
 record("TT13-NO-FOUR-PRIVILEGED-PERMS",not any(reported.values()),reported)
 code,start=adb("shell","monkey","-p",PKG,"-c","android.intent.category.LAUNCHER","1",timeout=55)
 save("launch.log",start)
 record("TT05-LAUNCH-INTENT",code==0 and "Events injected: 1" in start,start)
 for j in range(4):
  time.sleep(7)
  n=snapshot(f"screen_{j:02d}")
  clicked=press_dialog(n)
  if clicked:R.setdefault("dialogs_tapped",[]).append({"round":j,"value":clicked})
 n=snapshot("home_before_scroll")
 # Non-interactive visual capture of feed after several seconds of actual online load.
 adb("shell","input","swipe","540","1640","540","550","450")
 time.sleep(12)
 snapshot("home_after_scroll")
 adb("shell","input","swipe","540","1650","540","560","450")
 time.sleep(8)
 snapshot("home_second_scroll")
 _,activities=adb("shell","dumpsys","activity","activities",timeout=50)
 save("activity_sanitized.log","\n".join(x[:400] for x in activities.splitlines() if PKG in x)[:8000])
 _,logs=adb("logcat","-d","-v","threadtime",timeout=90)
 all_lines=logs.splitlines()
 fatal_keywords=("FATAL EXCEPTION","Fatal signal","SIGABRT","tombstoned","crash_dump32","crash_dump64","linker","houdini","native bridge","JNI DETECTED ERROR","Abort message","Caused by:","com.ss.android.article.news")
 lines=[x[:650] for x in all_lines if any(t.lower() in x.lower() for t in fatal_keywords)]
 save("filtered_fatal_logs.txt","\n".join(lines[-280:])[-135000:])
 _,crash=adb("logcat","-b","crash","-d","-v","threadtime",timeout=60)
 save("crash_buffer.log",crash[-160000:])
 _,native=adb("shell","getprop","ro.dalvik.vm.native.bridge",timeout=25)
 save("native_bridge.txt",native)
 _,tombstones=adb("shell","ls","-lt","/data/tombstones",timeout=30)
 save("tombstone_list.txt",tombstones)
 _,pid=adb("shell","pidof",PKG,timeout=30)
 save("process_status.txt",pid)
 R["process_pid_after_capture"]=pid.strip()
 record("TT06-NO-FATAL-EXCEPTION-IN-FILTERED-LOGS",not any("FATAL EXCEPTION" in x or "Fatal signal" in x for x in lines),f"{len(lines)} crash/context lines, crash buffer bytes={len(crash)}, process_pid={pid.strip()}")
 # Rendering and placement MUST be reviewed visually, not automatically marked PASS.
 record("TT10-TOP5-VISUAL-REVIEW",False,"PENDING_HUMAN_SCREENSHOT_REVIEW: inspect PNG and matching XML, no positional assumptions")
 record("TT12-FEED-ADS-VISUAL-REVIEW",False,"PENDING_HUMAN_SCREENSHOT_REVIEW: inspect PNG and app-specific ad markers")
 record("TT08-LOGIN-DATA",False,"NOT_RUN: isolated emulator has no user's private login data")
except Exception as e:
 R.setdefault("errors",[]).append(repr(e))
finally:
 R["final_result"]="PARTIAL: installation/screenshot data available; TT10/TT12 only pass after visual review"
 (OUT/"result.json").write_text(json.dumps(R,ensure_ascii=False,indent=2))
 print("TT935_REAL_AVD_RESULT="+json.dumps({k:v for k,v in R.items() if k not in ["images"]},ensure_ascii=False))
