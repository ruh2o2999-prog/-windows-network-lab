#!/usr/bin/env python3
"""R121 official Kiwi Android 11 targeted G4. Real native install/panel and
network I/O, localhost synthetic site only. Does not perform active scanning."""
import json, time, re, traceback, urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from r109_history_recovery import cdp_eval,probe_cdp
OUT=Path("out")
class Fixture(BaseHTTPRequestHandler):
 hits=0
 def do_GET(self):
  Fixture.hits+=1
  if self.path=="/": body=b'<!doctype html><title>R121 real Kiwi passive header check</title><h1>R121_FIXTURE</h1><script>let n=0;setInterval(()=>fetch("/echo?seq="+(++n),{cache:"no-store"}),220)</script>';mime="text/html"
  elif self.path.startswith("/echo"):body=b'{"r121":"fixture"}';mime="application/json"
  else:body=b'';mime="text/plain"
  self.send_response(200);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers()
  if body:self.wfile.write(body)
 def log_message(self,*args):pass
def execute(run,snapshot,state,type_internal_url,tap_target,tap_text_any):
 report={"gates":{},"errors":[],"scope":"Android11 API30 official Kiwi synthetic localhost only","uncovered":["Android16 ARM64","256MiB real disk pressure","24h soak","YouTube 403"]};ws=None
 def gate(k,ok,e):
  status="PASS" if ok else "FAIL";report["gates"][k]={"status":status,"evidence":e}
  state["gates"][k]={"status":status,"detail":json.dumps(e,ensure_ascii=False,default=str)[:1500]}
  print("R121_G4_"+status+" "+k+" "+json.dumps(e,ensure_ascii=False,default=str)[:600],flush=True)
  return ok
 try:
  OUT.mkdir(exist_ok=True)
  host=ThreadingHTTPServer(("127.0.0.1",18766),Fixture)
  Thread(target=host.serve_forever,daemon=True).start()
  rc,m=run(["adb","reverse","tcp:18766","tcp:18766"])
  if not gate("R121-01_adb_localhost",rc==0,{"rc":rc,"msg":m[:100]}):return
  xml=snapshot("r121_installed_manager")
  ids=re.findall(r"ID:\s*([a-p]{32})",xml)
  extid=ids[0] if ids else ""
  gate("R121-02_installed_extension_id",bool(extid),{"id":extid})
  detail=tap_target(xml,["Details","详情"],"r121_extension_details")
  xml=detail or xml
  # On real Kiwi 137 details page the off-screen Extension options node
  # appears in UI XML with bounds [0,0][0,0]. Do not mistake it for a click.
  # Scroll the genuine details page until the actual physical bounds are valid.
  import xml.etree.ElementTree as ET
  opened=False;trace=[]
  for i in range(16):
   visible=False;bounds=None
   try:
    tree=ET.fromstring(xml[xml.find("<?xml"):])
    for node in tree.iter("node"):
     a=node.attrib;label=(a.get("text","")+" "+a.get("content-desc","")).strip()
     if ("Extension options" in label or "扩展程序选项" in label or "扩展选项" in label) and a.get("clickable")=="true":
      m=re.match(r"\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]",a.get("bounds",""))
      if m:
       x1,y1,x2,y2=map(int,m.groups())
       bounds=[x1,y1,x2,y2];visible=x2>x1+15 and y2>y1+15 and y1>200 and y2<1870
       if visible:break
   except Exception as exc:trace.append({"i":i,"parseError":repr(exc)})
   trace.append({"i":i,"visible":visible,"bounds":bounds})
   if visible:
    nextxml=tap_target(xml,["Extension options","扩展程序选项","扩展选项"],"r121_real_visible_options")
    if nextxml:
     xml=nextxml;opened=True;break
   run(["adb","shell","input","swipe","810","1510","810","460","440"])
   time.sleep(1)
   xml=snapshot("r121_scrolled_details_"+str(i))
  report["native_options_trace"]=trace
  gate("R121-03a_native_visible_options",opened,{"trace":trace[-8:]})
  info=probe_cdp(run,OUT);ws=info.get("_websocket_url")
  if not ws and extid:
   type_internal_url("chrome-extension://"+extid+"/panel.html","r121_panel_fallback")
   info=probe_cdp(run,OUT);ws=info.get("_websocket_url")
  if not gate("R121-03_genuine_panel_CDP",bool(ws),{"cdp":info.get("found_target"),"nativeOptions":bool(detail)}):return
  ui=cdp_eval(ws,"({href:location.href,text:document.body.innerText.slice(0,600),hasAuto:!!document.getElementById('r121-mode')})")
  gate("R121-04_real_R121_UI",ui.get("hasAuto") and "chrome-extension://" in ui.get("href",""),ui)
  tab=cdp_eval(ws,"(async()=>new Promise((ok,no)=>chrome.tabs.create({url:'http://127.0.0.1:18766/',active:true},t=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):ok({id:t.id,windowId:t.windowId}))))()",timeout=30)
  tid=tab["id"];gate("R121-05_real_tab_created",tid>0,tab)
  probe="(async()=>new Promise((ok,no)=>chrome.runtime.sendMessage({type:'R121_STATUS',tabId:"+str(tid)+"},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):ok(r))))()"
  seen=[];v=None
  for i in range(30):
   time.sleep(1.5)
   v=cdp_eval(ws,probe,timeout=20)
   c=v.get("capture",{});p=v.get("passive",{})
   seen.append({"mode":c.get("mode"),"findings":len(p.get("findings",[])),"activeCount":c.get("activeCount"),"lastError":c.get("lastError"),"degraded":c.get("degraded")})
   if c.get("mode")=="debugger" and len(p.get("findings",[]))>=2:break
  report["observations"]=seen
  c=v.get("capture",{});p=v.get("passive",{})
  gate("R121-06_automatic_enhanced_without_click",c.get("mode")=="debugger",{"last":seen[-5:],"capture":c})
  codes=[x.get("code") for x in p.get("findings",[])]
  gate("R121-07_passive_safety_no_active_requests",p.get("observedDocuments",0)>=1 and "CSP_NOT_OBSERVED" in codes and "NOSNIFF_NOT_OBSERVED" in codes and p.get("activeRequestsSent")==0,p)
  limits=c.get("limits",{})
  gate("R121-08_resource_cap_live_status",limits.get("maxEnhancedTabs")==2 and limits.get("maxCdpBodyBytes")==2097152 and limits.get("maxCdpSessionBytes")==50331648,{"limits":limits,"storage":c.get("storage")})
  gate("R121-09_real_network_requests",Fixture.hits>=20,{"requests":Fixture.hits})
  gate("R121-10_bounded_active_count",c.get("activeCount",999)<=2,{"activeCount":c.get("activeCount")})
  for n in ("R121-11_actual_256MiB_storage_pressure","R121-12_24h_soak","R121-13_Android16"):
   report["gates"][n]={"status":"NOT_RUN","evidence":"not asserted by this targeted Android11 test"}
  host.shutdown()
 except Exception as e:
  report["errors"].append(repr(e));report["traceback"]=traceback.format_exc()
  state["gates"]["R121-99_exception"]={"status":"FAIL","detail":repr(e)}
  print("R121_G4_EXCEPTION",repr(e),flush=True)
 finally:
  OUT.mkdir(exist_ok=True)
  (OUT/"r121_real_android_g4.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
 return report
