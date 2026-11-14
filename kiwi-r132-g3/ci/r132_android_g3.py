#!/usr/bin/env python3
"""Kiwi R132: REAL Android G3, same frozen R131 MV2 ZIP, controlled HTTP only.

Requires adb, true official Kiwi x64 APK, Android 11 emulator, CDP port forward,
R131 production extension imported through Kiwi's own UI. Tests run >=300s.
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
EXT=ROOT/'assets/Kiwi_R131_frozen.zip'
EXPECTED_SHA='ce1624f9c315aae91a34f009c3e13e885e1d0c9471ddcc7ef75e6658778d728c'
PORT=18764; CDP_PORT=18766
SAMPLES=21; INTERVAL=15
state={'run':'R132_G3_ANDROID11_R131_FROZEN_300S', 'environment':{},'gates':{},'errors':[], 'originals':{'R122-07':'FAIL','R122-08':'FAIL'}}
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
 return gate('G0_R131_FROZEN_ZIP',sha==EXPECTED_SHA and bad is None and mf.get('version_name')=='rc12-r131' and len(z.namelist())==101,{'sha256':sha,'zipCRC':bad,'manifestVersion':mf.get('version_name'),'count':len(z.namelist())})
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
  self.ws=websocket.create_connection(url,timeout=12,origin='http://localhost')
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
 bg=[x for x in ext if x.get('type') in ('background_page','page') and ('_generated_background_page' in x.get('url','') or x.get('type')=='background_page')]
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
 imported=('网站数据观察与导出' in xml and 'rc12-r131' in xml and 'background page' in xml.lower())
 ext_id=re.search(r'ID:\s*([a-p]{32})',xml)
 return gate('A6_REAL_KIWI_IMPORT',imported,{
  'productionNameVisible':'网站数据观察与导出' in xml,
  'versionVisible':'rc12-r131' in xml,
  'backgroundPageVisible':'background page' in xml.lower(),
  'extensionId':ext_id.group(1) if ext_id else None,
  'pickerStillOpen':'documentsui' in xml.lower()})
def _status_expr(tab_id):
 return '''(async()=>new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('R122_STATUS_CALLBACK_TIMEOUT')),6000);try{chrome.runtime.sendMessage({type:'R121_STATUS',tabId:''' + str(int(tab_id)) + '''},r=>{clearTimeout(t);const e=chrome.runtime.lastError;if(e){reject(Error('R122_RUNTIME_LAST_ERROR:'+e.message));return;}if(!r||typeof r!=='object'){reject(Error('R122_INVALID_STATUS_RESPONSE'));return;}resolve(r)})}catch(e){clearTimeout(t);reject(e)}}))()'''
def _direct_expr(tab_id):
 return '''(()=>{let x={statusValid:false,storageValid:false,available:false};try{const bg=chrome.extension&&chrome.extension.getBackgroundPage&&chrome.extension.getBackgroundPage();const p=bg&&bg.KiwiR131ReadOnly;if(!p)return {...x,reason:'missing_facade'};x.available=p.protocol==='r131-direct-v1';const r=p.status('''+str(int(tab_id))+'''),s=p.storage();x.statusValid=!!(r&&r.ok&&r.capture&&r.passive);x.storageValid=!!(s&&s.ok&&s.storage&&typeof s.storage.hydrated==='boolean');x.mode=r&&r.capture&&r.capture.mode;x.activeCount=r&&r.capture&&r.capture.activeCount;x.time=Date.now();return x}catch(e){return {...x,error:String(e)}}})()'''
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
  verified=manifest and manifest.get('version_name')=='rc12-r131' and manifest.get('version')=='0.4.59'
 except Exception as e:
  verified=False;manifest={'error':repr(e)}
 if not gate('G3_AUTHENTIC_R131_EXTENSION',bool(verified),{'id':bgid,'manifest':{k:manifest.get(k) for k in ('name','version','version_name','error')}}):return
 fixture_url=f'http://127.0.0.1:{PORT}/'
 def tab_create(url):
  js='new Promise((yes,no)=>chrome.tabs.create({url:'+json.dumps(url)+',active:true},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:r.id,url:r.url})))'
  return browser.eval(js,timeout=15)
 fixture=tab_create(fixture_url);panel=tab_create('chrome-extension://'+bgid+'/panel.html')
 time.sleep(4)
 _,_,_=select_targets(); targets=cdp_targets()
 panel_matches=[x for x in targets if (x.get('url') or '').startswith('chrome-extension://'+bgid+'/panel.html')]
 if not gate('G3_REAL_R131_PANEL',bool(panel_matches),{'panel_tab_id':panel.get('id'),'panel_urls':[x['url'] for x in panel_matches]}):return
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
  if i in (0,12,14,15,16,17,18,19,20):
   for name,expr in [ ('direct',_direct_expr(fixture['id'])),('microtask','Promise.resolve().then(()=>({ok:true,ts:Date.now()}))'),('timer','new Promise(r=>setTimeout(()=>r({ok:true,ts:Date.now()}),0))')]:
    try:row[name]={'ok':True,'value':panel_cdp.eval(expr,timeout=5)}
    except Exception as e:row[name]={'ok':False,'error':repr(e)[:230]}
  samples.append(row)
  (OUT/'R132_live_samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2))
  print('R132_REAL_ANDROID_SAMPLE',json.dumps({k:row.get(k) for k in ('sample','elapsedSec','cdpOk','storageValid','mode','activeCount','fixtureHits','originalError')}),flush=True)
 elapsed=time.monotonic()-t0
 valid_duration=elapsed>=300 and samples[-1]['elapsedSec']>=299
 enough_hits=Fixture.hits-start_hits>=100
 statuses=all(s.get('cdpOk') is True for s in samples)
 storages=all(s.get('storageValid') is True for s in samples)
 passed_duration=gate('R132_REAL_300S_AND_HTTP',valid_duration and enough_hits,{'elapsed':round(elapsed,1),'httpDelta':Fixture.hits-start_hits,'samples':len(samples)})
 gate('R122-07_REAL_ANDROID_300S',valid_duration and enough_hits and statuses,{'statusOK':sum(bool(s.get('cdpOk')) for s in samples),'n':len(samples)})
 gate('R122-08_REAL_ANDROID_300S',valid_duration and enough_hits and storages and statuses,{'storageOK':sum(bool(s.get('storageValid')) for s in samples),'n':len(samples)})
 boundary=[s for s in samples if s['elapsedSec']>=239]
 gate('R131_DIRECT_DIAGNOSTIC',bool(boundary) and all((s.get('direct') or {}).get('ok') and (s.get('direct') or {}).get('value',{}).get('statusValid') and (s.get('direct') or {}).get('value',{}).get('storageValid') for s in boundary),{'boundarySamples':len(boundary)})
 fully_observed=all(s.get('mode')=='debugger' and isinstance(s.get('activeCount'),int) and s['activeCount']>=1 for s in samples)
 gate('G3_AUTO_CDP_ALL_SAMPLES',fully_observed,{'debuggerSamples':sum(s.get('mode')=='debugger' for s in samples),'connectedSamples':sum(isinstance(s.get('activeCount'),int) and s.get('activeCount')>=1 for s in samples)})
 pss_valid=all(isinstance(s.get('pssKiB'),int) and s['pssKiB']>0 and s.get('pidofRc')==0 and bool(s.get('pids')) for s in samples)
 gate('G3_ANDROID_PROCESS_PSS',pss_valid,{'pssSamples':sum(isinstance(s.get('pssKiB'),int) and s.get('pssKiB')>0 for s in samples)})
 state['outcome']='G3_PASS' if passed_duration and statuses and storages and fully_observed and pss_valid else 'G3_FAIL_OR_INCOMPLETE'
 state['samples']=samples
 panel_cdp.close();browser.close()

def finish():
 try:
  rc,txt=run(['adb','logcat','-d','-v','time'],timeout=55)
  (OUT/'adb_logcat_tail.txt').write_text(txt[-500000:],encoding='utf8')
 except Exception as e:state['errors'].append('logcat:'+repr(e))
 state['environment']['releaseTag']='14310011181';state['environment']['abiTarget']='x86_64';state['environment']['zipSha256']=EXPECTED_SHA
 (OUT/'R132_G3_verdict.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,default=str))
 print('R132_VERDICT',json.dumps({k:v['status'] for k,v in state['gates'].items()}),flush=True)
if __name__=='__main__':
 try: main()
 except Exception as e:
  state['errors'].append(repr(e));(OUT/'R132_exception.txt').write_text(traceback.format_exc());print('R132_EXCEPTION',repr(e),flush=True)
 finally:finish()
 # Gate failure exits nonzero; artifacts always uploaded.
 sys.exit(0 if state.get('outcome')=='G3_PASS' else 1)
