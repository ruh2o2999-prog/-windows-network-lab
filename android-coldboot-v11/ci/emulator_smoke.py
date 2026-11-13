#!/usr/bin/env python3
"""Actual Android emulator startup, public APK install, app-level HTTPS and screenshot/logcat."""
import datetime,hashlib,json,pathlib,re,subprocess,sys,time,xml.etree.ElementTree as ET
ROOT=pathlib.Path("out/coldboot_v11")
ROOT.mkdir(parents=True,exist_ok=True)
APK=pathlib.Path("android-coldboot-v11/fixture/app/build/outputs/apk/debug/app-debug.apk")
PKG="org.example.reversefixture"
R={"schema":"NET_DEVICE_APP_REUSE_v11","timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
   "apk_sha256":hashlib.sha256(APK.read_bytes()).hexdigest(),"gates":{}}
def run(name,args,timeout=100):
 try:
  p=subprocess.run(["adb",*args],capture_output=True,timeout=timeout)
  data=(p.stdout+p.stderr).decode("utf-8",errors="replace")
  (ROOT/(name+".log")).write_text(data[-500000:],encoding="utf-8")
  return p.returncode,data
 except Exception as e:
  return 97,str(e)
def gate(id,ok,msg):
 R["gates"][id]={"passed":bool(ok),"detail":str(msg)[:350]}
 (ROOT/"NET_emulator_and_app.json").write_text(json.dumps(R,ensure_ascii=False,indent=2))
try:
 _,boot=run("boot",["shell","getprop","sys.boot_completed"])
 _,rel=run("android_release",["shell","getprop","ro.build.version.release"])
 _,abi=run("abi",["shell","getprop","ro.product.cpu.abilist"])
 R["android"]={"release":rel.strip(),"abi":abi.strip()}
 gate("NET-D01-device-boot",boot.strip()=="1",boot.strip())
 _,dns=run("net_dns",["shell","getprop","net.dns1"])
 _,route=run("net_routes",["shell","ip","route"])
 _,connectivity=run("connectivity",["shell","dumpsys","connectivity"])
 R["android_network_observed"]={"dns1":dns.strip(),"routes":route[-2000:],"dumpsys_excerpt":connectivity[-3000:]}
 gate("NET-D02-device-routing",bool(route.strip()) and "default" in route,route[:350])
 code,install=run("install",["install","-r",str(APK)],timeout=180)
 gate("REUSE-D01-install",code==0 and "Success" in install,install)
 code,launch=run("start",["shell","am","start","-W","-n",PKG+"/.MainActivity"])
 gate("REUSE-D02-activity-start",code==0 and ("Status: ok" in launch or "LaunchState" in launch),launch)
 started=time.monotonic()
 net_text=""
 for _ in range(40):
  time.sleep(2)
  _,logs=run("network_app_logcat",["logcat","-d","-s","COLDBOOT_NET_V11:I","*:S"],timeout=35)
  text=' '.join([x for x in logs.splitlines() if 'COLDBOOT_NET_V11' in x][-3:])
  if 'EXAMPLE_' in text and 'GITHUB_' in text:
   net_text=text
   break
 R["app_logcat_reached"]=net_text
 gate("NET-D03-app-https-example","EXAMPLE_HTTPS_OK" in net_text,net_text)
 gate("NET-D04-app-https-github","GITHUB_HTTPS_OK" in net_text,net_text)
 code,xml=run("ui_dump",["shell","uiautomator","dump","/sdcard/window.xml"],timeout=65)
 _,xml=run("ui_read",["exec-out","cat","/sdcard/window.xml"])
 (ROOT/"ui.xml").write_text(xml)
 gate("REUSE-D03-real-ui", "PUBLIC_FIXTURE_V11" in xml, xml[-350:])
 try:
  p=subprocess.run(["adb","exec-out","screencap","-p"],capture_output=True,timeout=40)
  if p.returncode==0 and p.stdout.startswith(b"\x89PNG"):(ROOT/"screen.png").write_bytes(p.stdout)
  gate("REUSE-D04-screenshot",p.returncode==0 and p.stdout.startswith(b"\x89PNG"),len(p.stdout))
 except Exception as e:gate("REUSE-D04-screenshot",False,repr(e))
 _,cr=run("fatal_excerpt",["logcat","-d","-v","threadtime","-s","AndroidRuntime:E","libc:E","*:S"],timeout=50)
 gate("REUSE-D05-no-app-fatal",not (PKG in cr and ("FATAL EXCEPTION" in cr or "Fatal signal" in cr)),"Check fatal_excerpt.log")
except Exception as e:
 R["exception"]=repr(e)
finally:
 (ROOT/"NET_emulator_and_app.json").write_text(json.dumps(R,ensure_ascii=False,indent=2))
 print("NET_EMULATOR_RESULT="+json.dumps(R,ensure_ascii=False))
 if any(not x["passed"] for x in R["gates"].values()):sys.exit(7)
