#!/usr/bin/env python3
"""Kiwi R135: REAL Android G3, upgraded R135 MV2 ZIP, controlled HTTP only.

Requires adb, true official Kiwi x64 APK, Android 11 emulator, CDP port forward,
R135 production extension imported through Kiwi's own UI. Tests run >=300s.
No legacy gate is PASS on missing, stale, or substituted evidence.
"""
import hashlib, http.server, json, os, re, socketserver, subprocess, sys, threading, time, traceback, urllib.request, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
try: import websocket
except Exception: websocket=None
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'out'; OUT.mkdir(exist_ok=True)
PKG='com.kiwibrowser.browser'
EXT=ROOT/'assets/Kiwi_R135_test.zip'
EXPECTED_SHA='ba6a377eb24729e92844cb48d5e19eedd725709ad7e4f210114aec061652dbb8'
PORT=18764; CDP_PORT=18766
SAMPLES=29; INTERVAL=15
state={'run':'R135_G3_ANDROID11_R135_420S', 'environment':{},'gates':{},'errors':[], 'originals':{'R122-07':'FAIL','R122-08':'FAIL'}}
def run(args,timeout=75):
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
  return p.returncode,(p.stdout or '')+'\n'+(p.stderr or '')
 except Exception as e:return -1,repr(e)
def gate(name,passed,detail=None):
 state['gates'][name]={'status':'PASS' if passed else 'FAIL','evidence':detail}
 print(('PASS' if passed else 'FAIL'),name,json.dumps(detail,ensure_ascii=False,default=str)[:330],flush=True)
 return passed
def xml_snap(name):
 run(['adb','shell','uiautomator','dump','/sdcard/r132.xml'],timeout=45)
 _,x=run(['adb','shell','cat','/sdcard/r132.xml'],timeout=20)
 (OUT/(name+'.xml')).write_text(x,encoding='utf8')
 with (OUT/(name+'.png')).open('wb') as f:
  try:subprocess.run(['adb','exec-out','screencap','-p'],stdout=f,timeout=25)
  except Exception as e:state['errors'].append('screenshot:'+repr(e))
 return x
def tap_match(xml,keys,label,exact=False):
 try:r=ET.fromstring(xml[xml.find('<?xml'):]);nodes=list(r.iter('node'))
 except Exception:return None
 choices=[]
 for n in nodes:
  a=n.attrib
  if a.get('enabled')=='false':continue
  labels=[a.get('text','').strip(),a.get('content-desc','').strip()]
  labels=[x for x in labels if x]
  val=' | '.join(dict.fromkeys(labels))
  if not labels:continue
  if exact:
   if not any(k.casefold()==item.casefold() for k in keys for item in labels):continue
  elif not any(k.casefold() in item.casefold() for k in keys for item in labels):continue
  m=re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',a.get('bounds',''))
  if not m:continue
  x1,y1,x2,y2=map(int,m.groups())
  if x2<=x1 or y2<=y1:continue
  choices.append(((x1+x2)//2,(y1+y2)//2,val,a.get('clickable')=='true'))
 if not choices:return None
 choices.sort(key=lambda x:(not x[3],len(x[2])))
 x,y,val,_=choices[0];run(['adb','shell','input','tap',str(x),str(y)])
 print('R132_UI_TAP',label,val,flush=True);time.sleep(2)
 return xml_snap(label)
def _checksum():
 if not EXT.is_file():return gate('G0_EXTENSION_EXISTS',False,'missing binary')
 sha=hashlib.sha256(EXT.read_bytes()).hexdigest()
 with zipfile.ZipFile(EXT) as z:
  bad=z.testzip();mf=json.loads(z.read('manifest.json'))
 return gate('G0_R135_ZIP',sha==EXPECTED_SHA and bad is None and mf.get('version_name')=='rc15-r135' and len(z.namelist())==104,{'sha256':sha,'zipCRC':bad,'manifestVersion':mf.get('version_name'),'count':len(z.namelist())})
class Fixture(http.server.BaseHTTPRequestHandler):
 hits=0; lock=threading.Lock()
 def do_GET(self):
  with Fixture.lock:Fixture.hits+=1; n=Fixture.hits
  if self.path.startswith('/pulse'):
   data=json.dumps({'ok':True,'seq':n,'path':self.path}).encode();mime='application/json'
  else:
   data=b'''<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>R132_KIWI_ANDROID_FIXTURE_READY</h1><div id="count">0</div><script>let seq=0;setInterval(()=>{fetch('/pulse?seq='+(++seq)+'&t='+Date.now(),{cache:'no-store'}).then(()=>document.querySelector('#count').textContent=String(seq)).catch(()=>{})},600);</script></body></html>''';mime='text/html'
  self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  with (OUT/'fixture_http.jsonl').open('a') as f:f.write(json.dumps({'n':n,'url':self.path,'unix':time.time()})+'\n')
 def log_message(self,*args):pass
class ThreadHTTP(socketserver.ThreadingMixIn,http.server.HTTPServer):daemon_threads=True;allow_reuse_address=True
def cdp_targets():
 with urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json',timeout=10) as r:return json.load(r)
class CDP:
 def __init__(self,url):
  self.ws=websocket.create_connection(url,timeout=12,suppress_origin=True)
  self.seq=0
 def eval(self,expr,timeout=12,awaitPromise=True):
  self.seq+=1;n=self.seq;self.ws.settimeout(timeout)
  self.ws.send(json.dumps({'id':n,'method':'Runtime.evaluate','params':{'expression':expr,'returnByValue':True,'awaitPromise':awaitPromise,'userGesture':True}}))
  t=time.monotonic()
  while time.monotonic()-t<timeout:
   res=json.loads(self.ws.recv())
   if res.get('id')!=n:continue
   if 'error' in res:raise RuntimeError('CDP_PROTOCOL:'+str(res['error'])[:500])
   obj=res.get('result',{});
   if obj.get('exceptionDetails'):raise RuntimeError('CDP_JS:'+str(obj['exceptionDetails'])[:600])
   return obj.get('result',{}).get('value')
  raise TimeoutError('CDP_RESPONSE_TIMEOUT')
 def close(self):
  try:self.ws.close()
  except Exception:pass

def select_targets():
 items=cdp_targets()
 ext=[x for x in items if (x.get('url') or '').startswith('chrome-extension://')]
 bg=[x for x in ext if '_generated_background_page' in x.get('url','') or x.get('type')=='background_page']
 return items,ext,bg

def import_extension():
 rc,out=run(['adb','shell','getprop','sys.boot_completed'])
 if not gate('A0_REAL_ANDROID_BOOT',rc==0 and out.strip()=='1',out.strip()):return False
 rc,out=run(['adb','shell','getprop','ro.build.version.release']);state['environment']['androidRelease']=out.strip()
 rc,out=run(['adb','shell','getprop','ro.product.cpu.abi']);state['environment']['abi']=out.strip()
 apk=ROOT/'kiwi-official-x64.apk'
 if not gate('A1_OFFICIAL_KIWI_APK',apk.is_file() and apk.stat().st_size>15_000_000,{'size':apk.stat().st_size if apk.exists() else 0}):return False
 rc,out=run(['adb','install','-r',str(apk)],timeout=240)
 if not gate('A2_OFFICIAL_KIWI_INSTALL',rc==0 and 'Success' in out,out[-350:]):return False
 rc,out=run(['adb','shell','monkey','-p',PKG,'-c','android.intent.category.LAUNCHER','1']);time.sleep(9)
 xml=xml_snap('kiwi_launch')
 if not gate('A3_KIWI_OPEN',rc==0 and PKG in xml,out[:170]):return False
 for i in range(8):
  x=tap_match(xml,['skip','no thanks','not now','continue','next','get started','start browsing','accept','agree','done','got it','跳过','继续','开始'],'onboarding_'+str(i))
  if not x:break
  xml=x
 xml=xml_snap('before_extensions')
 menu=tap_match(xml,['More options','更多选项'],'kiwi_overflow_menu')
 if not menu:return gate('A4_KIWI_NATIVE_EXTENSIONS',False,'overflow not found')
 xml=tap_match(menu,['Extensions','扩展程序'],'extensions_via_native_menu',exact=True)
 if not xml:return gate('A4_KIWI_NATIVE_EXTENSIONS',False,'menu row not found')
 if 'kiwi://extensions' in xml and 'from .zip' not in xml.lower():
  # Acknowledges Kiwi's own navigation interstitial, based on R103 AVD UI trace.
  ack=tap_match(xml,['OK','确定','Continue','继续'],'warning_ack',exact=True)
  if not ack:
   run(['adb','shell','input','tap','540','1683']);time.sleep(4);ack=xml_snap('warning_ack_position_fallback')
  xml=ack
 if not gate('A4_KIWI_EXT_MANAGER',('from .zip' in xml.lower() or 'Extensions' in xml or 'extensions' in xml),xml[:220]):return False
 staged=ROOT/'Kiwi_R103_Production_MV2.zip';staged.write_bytes(EXT.read_bytes())
 rc,out=run(['adb','push',str(staged),'/sdcard/Download/Kiwi_R103_Production_MV2.zip'])
 if not gate('A5_REAL_ZIP_STAGED',rc==0,{'bytes':staged.stat().st_size,'adb':out[:140]}):return False
 picker=tap_match(xml,['from .zip','.crx','.user.js'],'extension_file_picker')
 if not picker:return gate('A6_REAL_KIWI_IMPORT',False,'import button not exposed')
 xml=picker
 roots=tap_match(xml,['Show roots','浏览'],'file_picker_roots')
 if roots:xml=roots
 dl=tap_match(xml,['Downloads','下载'],'file_picker_downloads',exact=True)
 if dl:xml=dl
 ls=tap_match(xml,['List view'],'file_picker_list_view')
 if ls:xml=ls
 item=tap_match(xml,['Kiwi_R103_Production_MV2.zip'],'file_picker_target')
 if item:xml=item
 if ('com.android.documentsui' in xml.lower() or 'com.google.android.documentsui' in xml.lower()):
  for key in (20,23,66):
   run(['adb','shell','input','keyevent',str(key)]);time.sleep(1)
   xml=xml_snap('picker_key_'+str(key))
   if 'documentsui' not in xml.lower():break
 consent=tap_match(xml,['Add extension','Install extension','Add','安装扩展','添加扩展'],'extension_confirm')
 if consent:xml=consent
 time.sleep(6);xml=xml_snap('extension_after_import')
 # The initial extension management page is authoritative; opening Details/
 # Options may navigate away and invalidate subsequent UI assertions.
 # Run 43559322367 proved the actual extension was installed but old harness
 # looked at the overflow menu instead, reporting false FAIL.
 imported=('网站数据观察与导出' in xml and 'rc15-r135' in xml and 'background page' in xml.lower())
 ext_id=re.search(r'ID:\s*([a-p]{32})',xml)
 return gate('A6_REAL_KIWI_IMPORT',imported,{
  'productionNameVisible':'网站数据观察与导出' in xml,
  'versionVisible':'rc15-r135' in xml,
  'backgroundPageVisible':'background page' in xml.lower(),
  'extensionId':ext_id.group(1) if ext_id else None,
  'pickerStillOpen':'documentsui' in xml.lower()})
def _status_expr(tab_id):
 return '''(async()=>new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('R122_STATUS_CALLBACK_TIMEOUT')),6000);try{chrome.runtime.sendMessage({type:'R121_STATUS',tabId:''' + str(int(tab_id)) + '''},r=>{clearTimeout(t);const e=chrome.runtime.lastError;if(e){reject(Error('R122_RUNTIME_LAST_ERROR:'+e.message));return;}if(!r||typeof r!=='object'){reject(Error('R122_INVALID_STATUS_RESPONSE'));return;}resolve(r)})}catch(e){clearTimeout(t);reject(e)}}))()'''
def _direct_expr(tab_id):
 return '''(()=>{let x={statusValid:false,storageValid:false,available:false};try{const bg=chrome.extension&&chrome.extension.getBackgroundPage&&chrome.extension.getBackgroundPage();const p=bg&&bg.KiwiR131ReadOnly;if(!p)return {...x,reason:'missing_facade'};x.available=p.protocol==='r131-direct-v1';const r=p.status('''+str(int(tab_id))+'''),s=p.storage();x.statusValid=!!(r&&r.ok&&r.capture&&r.passive);x.storageValid=!!(s&&s.ok&&s.storage&&typeof s.storage.hydrated==='boolean');x.mode=r&&r.capture&&r.capture.mode;x.activeCount=r&&r.capture&&r.capture.activeCount;x.time=Date.now();return x}catch(e){return {...x,error:String(e)}}})()'''
def _r133_expr(tab_id):
 return """KiwiStatusBridgeR133.read(chrome,"""+str(int(tab_id))+""",{originalMessage:()=>Promise.reject(Error('NO_SYNTHETIC_ACK'))}).then(r=>({ok:r.ok===true,path:r.r131Path,ageMs:r.r133AgeMs,mode:r.capture&&r.capture.mode,activeCount:r.capture&&r.capture.activeCount,storageValid:Number.isFinite(r.capture&&r.capture.storage&&r.capture.storage.usage)&&typeof(r.capture&&r.capture.storage&&r.capture.storage.pressure)==='boolean',observedAt:r.r133ObservedAt}))"""

def _port_expr(tab_id):
 return """KiwiStatusBridgeR133.read(chrome,"""+str(int(tab_id))+""",{direct:()=>({ok:false,reason:'R133_FORCE_PORT_TEST'}),originalMessage:()=>Promise.reject(Error('PORT_UNAVAILABLE'))}).then(r=>({ok:r.ok===true,path:r.r131Path,ageMs:r.r133AgeMs,storageValid:Number.isFinite(r.capture&&r.capture.storage&&r.capture.storage.usage)}))"""


SCREEN_PALETTE=[(244,35,48),(39,221,62),(49,71,246),(251,219,35),(204,44,210),(39,221,229)]
def proof_pixels(png_path):
 """Read actual adb screencap pixels; one row must contain all six strips."""
 from PIL import Image
 im=Image.open(png_path).convert('RGB');w,h=im.size
 for y in range(10,min(h//2,780),3):
  hits=[]
  for i,color in enumerate(SCREEN_PALETTE):
   x=int(w*(i+.5)/6);pixel=im.getpixel((min(w-1,x),y))
   hits.append(all(abs(pixel[j]-color[j])<=30 for j in range(3)))
  if all(hits):return {'ok':True,'pixelRow':y,'width':w,'height':h,'paletteMatched':6}
 return {'ok':False,'width':w,'height':h,'reason':'palette_not_on_actual_android_screen'}
def screen_marker_js():
 colors=['#f42330','#27dd3e','#3147f6','#fbdb23','#cc2cd2','#27dde5']
 # DOM-only temporary UI marker created strictly during G3 screenshot capture.
 # It does not dispatch synthetic visibility/focus events.
 return "(()=>{const old=document.getElementById('r135-actual-screen-proof');if(old)old.remove();const p=document.createElement('div');p.id='r135-actual-screen-proof';p.style.cssText='position:fixed;top:0;left:0;width:100vw;height:84px;display:flex;z-index:2147483647;pointer-events:none';"+''.join("{const d=document.createElement('div');d.style.cssText='flex:1;background:"+c+"';p.appendChild(d);}" for c in colors)+"document.documentElement.appendChild(p);return {present:!!document.getElementById(p.id),hidden:document.hidden,visibilityState:document.visibilityState}})()"
def adb_screen(path):
 with open(path,'wb') as out:
  p=subprocess.run(['adb','exec-out','screencap','-p'],stdout=out,stderr=subprocess.PIPE,timeout=30)
 if p.returncode!=0:raise RuntimeError('adb screenshot failed: '+p.stderr.decode(errors='replace')[:150])
 return proof_pixels(path)

def _mem(raw):
 for pat in (r'TOTAL PSS:\s*([\d,]+)',r'^\s*TOTAL\s+([\d,]+)\s'):
  m=re.search(pat,raw,re.M)
  if m:return int(m.group(1).replace(',',''))
 return None

def main():
 if websocket is None:return gate('P0_CDP_PYTHON_DEP',False,'pip install websocket-client')
 if not _checksum():return
 if not import_extension():return
 proc=ThreadHTTP(('0.0.0.0',PORT),Fixture);threading.Thread(target=proc.serve_forever,daemon=True).start()
 rc,out=run(['adb','reverse',f'tcp:{PORT}',f'tcp:{PORT}'])
 if not gate('G3_ADB_REVERSE',rc==0,out[:150]):return
 rc,out=run(['adb','forward',f'tcp:{CDP_PORT}','localabstract:chrome_devtools_remote'])
 if not gate('G3_REAL_CDP_FORWARD',rc==0,out[:150]):return
 time.sleep(2)
 items,ext,bg=select_targets()
 (OUT/'cdp_targets_before.json').write_text(json.dumps(items,indent=2))
 if not gate('G3_REAL_EXTENSION_CONTEXT',bool(ext),[{'type':x.get('type'),'url':x.get('url')} for x in ext]):return
 usable=bg or [x for x in ext if x.get('type')=='page']
 if not usable:return
 browser=CDP(usable[0]['webSocketDebuggerUrl'])
 bgid=re.search(r'chrome-extension://([^/]+)',usable[0]['url']).group(1)
 try:
  manifest=browser.eval('chrome.runtime.getManifest()',timeout=8)
  verified=manifest and manifest.get('version_name')=='rc15-r135' and manifest.get('version')=='0.4.59'
 except Exception as e:
  verified=False;manifest={'error':repr(e)}
 if not gate('G3_AUTHENTIC_R135_EXTENSION',bool(verified),{'id':bgid,'manifest':{k:manifest.get(k) for k in ('name','version','version_name','error')}}):return
 fixture_url=f'http://127.0.0.1:{PORT}/'
 def tab_create(url):
  js='new Promise((yes,no)=>chrome.tabs.create({url:'+json.dumps(url)+',active:true},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:r.id,url:r.url})))'
  return browser.eval(js,timeout=15)
 fixture=tab_create(fixture_url);panel=tab_create('chrome-extension://'+bgid+'/panel.html')
 time.sleep(4)
 _,_,_=select_targets(); targets=cdp_targets()
 panel_matches=[x for x in targets if (x.get('url') or '').startswith('chrome-extension://'+bgid+'/panel.html')]
 if not gate('G3_REAL_R135_PANEL',bool(panel_matches),{'panel_tab_id':panel.get('id'),'panel_urls':[x['url'] for x in panel_matches]}):return
 panel_cdp=CDP(panel_matches[0]['webSocketDebuggerUrl'])
 run(['adb','shell','am','start','-a','android.intent.action.VIEW','-d',fixture_url,PKG]);time.sleep(4)
 if not gate('G3_REAL_HTTP_FIXTURE',Fixture.hits>=2,{'initialHits':Fixture.hits,'fixtureTab':fixture}):return
 # We use panel CDP as the R122 asynchronous message host, not a local stub.
 samples=[];t0=time.monotonic();start_hits=Fixture.hits
 for i in range(SAMPLES):
  wait=t0+i*INTERVAL-time.monotonic()
  if wait>0:time.sleep(wait)
  row={'sample':i,'elapsedSec':round(time.monotonic()-t0,3),'unix':time.time(),'fixtureHits':Fixture.hits}
  rc,pids=run(['adb','shell','pidof',PKG],timeout=12);row['pidofRc']=rc;row['pids']=pids.strip()
  rc,mem=run(['adb','shell','dumpsys','meminfo',PKG],timeout=25);row['pssKiB']=_mem(mem) if rc==0 else None
  try:
   status=panel_cdp.eval(_status_expr(fixture['id']),timeout=11)
   cap=status.get('capture',{}) if isinstance(status,dict) else {}
   store=cap.get('storage',{}) if isinstance(cap,dict) else {}
   row['cdpOk']=isinstance(status,dict) and isinstance(status.get('capture'),dict) and isinstance(status.get('passive'),dict)
   row['mode']=cap.get('mode');row['automatic']=cap.get('automatic');row['paused']=cap.get('paused');row['activeCount']=cap.get('activeCount')
   row['storageUsage']=store.get('usage');row['storagePressure']=store.get('pressure')
   row['storageValid']=type(row['storageUsage']) is int and type(row['storagePressure']) is bool
   row['statusTimestamp']=(status.get('r124') or {}).get('respondedAt')
  except Exception as e:
   row['cdpOk']=False;row['storageValid']=False;row['originalError']=repr(e)[:450]
  # User-facing R133 status must remain fresh even when the legacy callback stalls.
  try:
   row['r133Service']={'ok':True,'value':panel_cdp.eval(_r133_expr(fixture['id']),timeout=8)}
  except Exception as e:
   row['r133Service']={'ok':False,'error':repr(e)[:350]}
  if i in (0,12,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28):
   for name,expr in [ ('direct',_direct_expr(fixture['id'])),('microtask','Promise.resolve().then(()=>({ok:true,ts:Date.now()}))'),('timer','new Promise(r=>setTimeout(()=>r({ok:true,ts:Date.now()}),0))'),('port',_port_expr(fixture['id']))]:
    try:row[name]={'ok':True,'value':panel_cdp.eval(expr,timeout=5)}
    except Exception as e:row[name]={'ok':False,'error':repr(e)[:230]}
  try:
   row['r134Panel']=panel_cdp.eval('window.KiwiR134PanelRecovery&&window.KiwiR134PanelRecovery.diagnostics()',timeout=7,awaitPromise=False)
  except Exception as e:row['r134Panel']={'error':repr(e)[:180]}
  # R135: issue REAL asynchronous requests WITHOUT timeout/Promise wait.
  # A CDP synchronous probe can run on a hidden tab even if timers are clamped.
  # Later independent synchronous reads determine whether native ACK arrived.
  if i in (20,22,24):
   try:row['r135Start']=panel_cdp.eval('window.KiwiR135Probe.start('+str(int(fixture['id']))+')',timeout=7,awaitPromise=False)
   except Exception as e:row['r135StartError']=repr(e)[:260]
  if i>=20:
   try:row['r135Diagnostics']=panel_cdp.eval('window.KiwiR135Probe.diagnostics()',timeout=7,awaitPromise=False)
   except Exception as e:row['r135DiagnosticsError']=repr(e)[:260]
  samples.append(row)
  (OUT/'R135_live_samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2))
  print('R135_REAL_ANDROID_SAMPLE',json.dumps({k:row.get(k) for k in ('sample','elapsedSec','cdpOk','storageValid','mode','activeCount','fixtureHits','originalError')}),flush=True)
 elapsed=time.monotonic()-t0
 valid_duration=elapsed>=420 and samples[-1]['elapsedSec']>=419
 enough_hits=Fixture.hits-start_hits>=100
 statuses=all(s.get('cdpOk') is True for s in samples)
 storages=all(s.get('storageValid') is True for s in samples)
 passed_duration=gate('R135_REAL_420S_AND_HTTP',valid_duration and enough_hits,{'elapsed':round(elapsed,1),'httpDelta':Fixture.hits-start_hits,'samples':len(samples)})
 r133_live=all((x.get('r133Service') or {}).get('ok') and (x.get('r133Service') or {}).get('value',{}).get('ok') and (x.get('r133Service') or {}).get('value',{}).get('storageValid') and (x.get('r133Service') or {}).get('value',{}).get('ageMs',99999)<=10000 and (x.get('r133Service') or {}).get('value',{}).get('path') in ('background-direct','background-port') for x in samples)
 gate('R135_LIVE_FRESH_STATUS_ALL_SAMPLES',valid_duration and r133_live,{'fresh':sum(bool((x.get('r133Service') or {}).get('value',{}).get('storageValid')) for x in samples),'samples':len(samples)})
 gate('R122-07_REAL_ANDROID_300S',valid_duration and enough_hits and statuses,{'statusOK':sum(bool(s.get('cdpOk')) for s in samples),'n':len(samples)})
 gate('R122-08_REAL_ANDROID_300S',valid_duration and enough_hits and storages and statuses,{'storageOK':sum(bool(s.get('storageValid')) for s in samples),'n':len(samples)})
 boundary=[s for s in samples if s['elapsedSec']>=239]
 gate('R131_DIRECT_DIAGNOSTIC',bool(boundary) and all((s.get('direct') or {}).get('ok') and (s.get('direct') or {}).get('value',{}).get('statusValid') and (s.get('direct') or {}).get('value',{}).get('storageValid') for s in boundary),{'boundarySamples':len(boundary)})
 fully_observed=all(s.get('mode')=='debugger' and isinstance(s.get('activeCount'),int) and s['activeCount']>=1 for s in samples)
 gate('G3_AUTO_CDP_ALL_SAMPLES',fully_observed,{'debuggerSamples':sum(s.get('mode')=='debugger' for s in samples),'connectedSamples':sum(isinstance(s.get('activeCount'),int) and s.get('activeCount')>=1 for s in samples)})
 pss_valid=all(isinstance(s.get('pssKiB'),int) and s['pssKiB']>0 and s.get('pidofRc')==0 and bool(s.get('pids')) for s in samples)
 gate('G3_ANDROID_PROCESS_PSS',pss_valid,{'pssSamples':sum(isinstance(s.get('pssKiB'),int) and s.get('pssKiB')>0 for s in samples)})
 hidden_callbacks=[]
 for row in samples:
  if row['elapsedSec']<300:continue
  for x in ((row.get('r135Diagnostics') or {}).get('entries') or []):
   if x.get('id') and x.get('channel') in ('message','port'):
    hidden_callbacks.append({'sample':row['sample'],'elapsedSec':row['elapsedSec'],'id':x['id'],'channel':x['channel'],'finished':x.get('finished') is True,'response':x.get('response',{}),'latencyMs':x.get('latencyMs')})
 (OUT/'R135_native_callbacks_after_300.json').write_text(json.dumps(hidden_callbacks,ensure_ascii=False,indent=2))
 gate('R135_REAL_NATIVE_CALLBACK_PROBE',len(hidden_callbacks)>=2 and any(x.get('sample')>=21 for x in hidden_callbacks),{'records':len(hidden_callbacks),'startedSamples':sum('r135Start' in x for x in samples)})
 # A callback is acknowledged only with its real fresh response; pending and
 # CDP Promise timeout are NOT interchangeable.
 acked={c:[x for x in hidden_callbacks if x['channel']==c and x['finished'] and x.get('response',{}).get('valid')] for c in ('message','port')}
 state['r135NativeAcknowledgements']={k:len(v) for k,v in acked.items()}
 gate('R135_HIDDEN_NATIVE_MESSAGE_ACK',len(acked['message'])>=1,{'validAckRecords':len(acked['message'])})
 gate('R135_HIDDEN_NATIVE_PORT_ACK',len(acked['port'])>=1,{'validAckRecords':len(acked['port'])})
 state['outcome']='G3_FULL_PASS' if passed_duration and statuses and storages and r133_live and fully_observed and pss_valid else ('G3_FUNCTIONAL_PASS_LEGACY_FAIL' if passed_duration and r133_live and pss_valid else 'G3_FAIL_OR_INCOMPLETE')
 state['samples']=samples
 # R134: activate the actual panel tab; no synthetic visibility events.
 recovery={'beganAt':time.time(),'steps':[]}
 def rec(label,fn):
  try:
   v=fn();recovery['steps'].append({'name':label,'ok':True,'value':v});return v
  except Exception as e:
   recovery['steps'].append({'name':label,'ok':False,'error':repr(e)[:300]});return None
 pre=rec('beforeForeground',lambda:panel_cdp.eval('({hidden:document.hidden,visibilityState:document.visibilityState,diag:window.KiwiR134PanelRecovery&&window.KiwiR134PanelRecovery.diagnostics()})',timeout=8,awaitPromise=False))
 rec('activateActualPanelTab',lambda:browser.eval('new Promise((yes,no)=>chrome.tabs.update('+str(panel['id'])+',{active:true},t=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:t.id,active:t.active})))',timeout=12))
 time.sleep(3)
 after=rec('afterForeground',lambda:panel_cdp.eval('({hidden:document.hidden,visibilityState:document.visibilityState,diag:window.KiwiR134PanelRecovery&&window.KiwiR134PanelRecovery.diagnostics()})',timeout=10,awaitPromise=False))
 rec('visibleFreshStatus',lambda:panel_cdp.eval(_r133_expr(fixture['id']),timeout=8))
 rec('visibleOriginalR121Message',lambda:panel_cdp.eval(_status_expr(fixture['id']),timeout=15))
 time.sleep(3)
 last=rec('finalForegroundDiagnostics',lambda:panel_cdp.eval('window.KiwiR134PanelRecovery&&window.KiwiR134PanelRecovery.diagnostics()',timeout=8,awaitPromise=False))
 rec('visibleTimer',lambda:panel_cdp.eval('new Promise(r=>setTimeout(()=>r({ok:true,at:Date.now()}),0))',timeout=10))
 recovery['completedAt']=time.time()
 (OUT/'R135_foreground_recovery.json').write_text(json.dumps(recovery,ensure_ascii=False,indent=2))
 fromHidden=bool(pre and pre.get('hidden') is True)
 reallyVisible=bool(after and after.get('hidden') is False and after.get('visibilityState')=='visible')
 visibleDirect=any(x['name']=='visibleFreshStatus' and x['ok'] and isinstance(x.get('value'),dict) and x['value'].get('ok') and x['value'].get('ageMs',100000)<=10000 for x in recovery['steps'])
 legacyAck=any(x['name']=='visibleOriginalR121Message' and x['ok'] and isinstance(x.get('value'),dict) and x['value'].get('ok') and x['value'].get('capture') for x in recovery['steps'])
 visibilityRecorded=bool(last and last.get('wakeCount',0)>=1 and (last.get('lastDirect') or {}).get('ok'))
 gate('R134_REAL_HIDDEN_TO_VISIBLE',fromHidden and reallyVisible,{'hiddenBefore':pre and pre.get('hidden'),'hiddenAfter':after and after.get('hidden'),'visibilityState':after and after.get('visibilityState')})
 gate('R134_VISIBLE_NEW_FRESH_STATUS',reallyVisible and visibleDirect and visibilityRecorded,{'visibleFresh':visibleDirect,'wakeCount':last and last.get('wakeCount')})
 gate('R134_VISIBLE_ORIGINAL_R121_ACK',reallyVisible and bool(legacyAck),{'legacyRecovered':bool(legacyAck),'legacyStats':last and {'acknowledged':last.get('legacyAcknowledged'),'pending':last.get('legacyPending'),'failed':last.get('legacyFailed')}})
 # Screen proof is separate from DOM visibility and tabs.update active flag.
 proof={'tests':[], 'activation':rec('r135ChromeTabsCurrent',lambda:browser.eval('new Promise(r=>chrome.tabs.get('+str(panel['id'])+',t=>r({id:t.id,index:t.index,windowId:t.windowId,active:t.active})))',timeout=10))}
 rec('r135InjectTemporaryScreenMarker',lambda:panel_cdp.eval(screen_marker_js(),timeout=8,awaitPromise=False))
 time.sleep(2)
 rec('r135AdbActivity',lambda:run(['adb','shell','dumpsys','activity','activities'],timeout=25)[1][-3500:])
 try: proof['tests'].append({'method':'after-tabs-update','pixels':adb_screen(OUT/'R135_actual_android_screen_after_tabs_update.png')})
 except Exception as e:proof['tests'].append({'method':'after-tabs-update','error':repr(e)})
 if not proof['tests'][-1].get('pixels',{}).get('ok'):
  # Explicit fallback cannot be claimed as success of tabs.update alone.
  t=proof['activation'] or {}
  if t.get('windowId') is not None and t.get('index') is not None:
   rec('r135ChromeTabsHighlight',lambda:browser.eval('new Promise((yes,no)=>chrome.tabs.highlight({windowId:'+str(t['windowId'])+',tabs:'+str(t['index'])+'},w=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:w.id,focused:w.focused})))',timeout=12))
   rec('r135ChromeWindowFocus',lambda:browser.eval('new Promise((yes,no)=>chrome.windows.update('+str(t['windowId'])+',{focused:true},w=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:w.id,focused:w.focused})))',timeout=12))
   time.sleep(2)
   try:proof['tests'].append({'method':'after-highlight-window-focus','pixels':adb_screen(OUT/'R135_actual_android_screen_after_fallback.png')})
   except Exception as e:proof['tests'].append({'method':'after-highlight-window-focus','error':repr(e)})
 proof['best']=next((x for x in proof['tests'] if x.get('pixels',{}).get('ok')),None)
 (OUT/'R135_actual_screen_verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
 gate('R134_UI_01_REAL_ANDROID_SCREEN',bool(proof['best']) and reallyVisible,{'screenMatched':bool(proof['best']),'method':proof['best'] and proof['best']['method'],'tabsUpdateActive':next((x.get('value',{}).get('active') for x in recovery['steps'] if x['name']=='activateActualPanelTab'),None)})
 rec('r135RemoveTemporaryMarker',lambda:panel_cdp.eval("(()=>{document.getElementById('r135-actual-screen-proof')?.remove();return true})()",timeout=8,awaitPromise=False))
 panel_cdp.close();browser.close()

def finish():
 try:
  rc,txt=run(['adb','logcat','-d','-v','time'],timeout=55)
  (OUT/'adb_logcat_tail.txt').write_text(txt[-500000:],encoding='utf8')
 except Exception as e:state['errors'].append('logcat:'+repr(e))
 state['environment']['releaseTag']='14310011181';state['environment']['abiTarget']='x86_64';state['environment']['zipSha256']=EXPECTED_SHA
 (OUT/'R135_G3_verdict.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,default=str))
 print('R135_VERDICT',json.dumps({k:v['status'] for k,v in state['gates'].items()}),flush=True)
if __name__=='__main__':
 try: main()
 except Exception as e:
  state['errors'].append(repr(e));(OUT/'R135_exception.txt').write_text(traceback.format_exc());print('R135_EXCEPTION',repr(e),flush=True)
 finally:finish()
 # Gate failure exits nonzero; artifacts always uploaded.
 sys.exit(0 if state.get('outcome')=='G3_FULL_PASS' else 1)
