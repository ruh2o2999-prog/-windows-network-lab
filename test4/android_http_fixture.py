#!/usr/bin/env python3
"""V813 TEST4: actual official Kiwi browser UI + host HTTP fixture on Android 11/16 AVD.
Does not install private extensions or equate public Kiwi with user's app business.
"""
import hashlib,http.server,json,os,re,subprocess,threading,time,xml.etree.ElementTree as ET
from pathlib import Path
OUT=Path("out");OUT.mkdir(exist_ok=True)
PKG="com.kiwibrowser.browser";PORT=18737;API=os.getenv("TEST4_API","unknown")
state={"schema":"test4-android-http-fixture-v1","api":API,"gates":{},"scope":"official Kiwi APK UI+HTTP fixture, NOT private Android product G5"}
def sh(*cmd,timeout=60):
 try:
  p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
  return p.returncode,(p.stdout or "")+"\n"+(p.stderr or "")
 except Exception as e:return -1,repr(e)
def gate(n,x,detail):
 state["gates"][n]={"status":"PASS" if x else "FAIL","detail":str(detail)[-750:]}
 print(("PASS" if x else "FAIL"),n,flush=True)
def snap(n):
 sh("adb","shell","uiautomator","dump","/sdcard/window.xml",timeout=35)
 _,x=sh("adb","shell","cat","/sdcard/window.xml",timeout=35)
 (OUT/(n+".xml")).write_text(x,encoding="utf8")
 with (OUT/(n+".png")).open("wb") as f:
  try:subprocess.run(["adb","exec-out","screencap","-p"],stdout=f,stderr=subprocess.DEVNULL,check=True,timeout=25)
  except Exception as e:state.setdefault("errors",[]).append(repr(e))
 return x
def tap_named(xml,names):
 try:root=ET.fromstring(xml[xml.index("<?xml"):])
 except Exception:return None
 for name in names:
  for v in root.iter("node"):
   at=v.attrib
   if at.get("text","").strip().lower()!=name.lower() or at.get("clickable")!="true":continue
   b=list(map(int,re.findall(r"\d+",at.get("bounds",""))))
   if len(b)!=4:continue
   x=(b[0]+b[2])//2;y=(b[1]+b[3])//2
   rc,t=sh("adb","shell","input","tap",str(x),str(y));time.sleep(3)
   return (name,x,y,rc)
 return None
events=[]
class H(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  events.append({"path":self.path,"user_agent":self.headers.get("User-Agent",""),"address":self.client_address[0]})
  payload=b"TEST4_ANDROID_BROWSER_NETWORK_RESPONSE_OK"
  self.send_response(200);self.send_header("Content-Type","text/plain");self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(("0.0.0.0",PORT),H)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 _,v=sh("adb","shell","getprop","sys.boot_completed");gate("android_boot",v.strip()=="1",v)
 _,v=sh("adb","shell","getprop","ro.build.version.sdk");gate("api_version",v.strip()==API,v)
 apk=Path("kiwi-official-x64.apk")
 if not apk.exists():raise RuntimeError("official APK missing")
 _,v=sh("adb","install","-r",str(apk),timeout=240);gate("official_apk_install","Success" in v,v)
 _,v=sh("adb","shell","monkey","-p",PKG,"-c","android.intent.category.LAUNCHER","1");time.sleep(5)
 xml=snap("initial_welcome")
 gate("kiwi_foreground",PKG in xml,"package in UI XML")
 onboarding=[]
 for i in range(7):
  if "Welcome to Kiwi Browser" not in xml and not any(k in xml for k in ['text="Continue"','text="Not now"','text="Skip"']):break
  tapped=tap_named(xml,["Skip","Not now","No thanks","Continue","Get started","Start browsing","Done"])
  if not tapped:break
  onboarding.append(tapped);xml=snap("onboarding_"+str(i))
 state["onboarding_actions"]=onboarding
 done="Welcome to Kiwi Browser" not in xml and PKG in xml
 gate("past_welcome_screen",done,"welcome_remaining="+str("Welcome to Kiwi Browser" in xml))
 token="V813TEST4API"+API
 link=f"http://10.0.2.2:{PORT}/test4?token={token}"
 _,intent=sh("adb","shell","am","start","-a","android.intent.action.VIEW","-d",link,PKG)
 for i in range(18):
  time.sleep(2)
  if any(token in e["path"] for e in events):break
 xml=snap("after_http_fixture")
 hits=[e for e in events if token in e["path"] and ("Mozilla" in e["user_agent"] or "Chrome" in e["user_agent"])]
 gate("real_browser_http_get",len(hits)>0,{"intent":intent[:300],"hits":hits})
 (OUT/"server_hits.json").write_text(json.dumps(events,ensure_ascii=False,indent=2))
 sh("adb","shell","am","force-stop",PKG)
 _,txt=sh("adb","shell","monkey","-p",PKG,"-c","android.intent.category.LAUNCHER","1")
 time.sleep(5);xml=snap("relaunch")
 gate("relaunch_after_force_stop",PKG in xml and "Events injected: 1" in txt,txt)
 state["limits"]=["Only official Kiwi public APK used","No private Kiwi extension/Clash/Douyin app installed","Server saw actual GET only when real_browser_http_get PASS","No user product G5"]
except Exception as e:state.setdefault("errors",[]).append(repr(e))
finally:
 server.shutdown()
 state["status"]="PASS" if state["gates"] and all(x["status"]=="PASS" for x in state["gates"].values()) and not state.get("errors") else "FAIL"
 (OUT/"test4_fixture_status.json").write_text(json.dumps(state,ensure_ascii=False,indent=2))
 print("TEST4_ANDROID_HTTP_FIXTURE",state["status"],flush=True)
 raise SystemExit(0 if state["status"]=="PASS" else 2)
