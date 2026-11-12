#!/usr/bin/env python3
"""G4 R115: real Android Kiwi native UI + synthetic webpage SourceBuffer.appendBuffer.
No mocks, no media from third-party websites. Browser download is independently
checked and NEVER reported complete merely because an anchor was clicked.
"""
import os,json,re,time,hashlib,base64,pathlib,subprocess,urllib.request,traceback,zipfile
from r109_history_recovery import cdp_eval,probe_cdp
OUT_NAME='r115_native_mse_endtoend_status.json';PKG='com.kiwibrowser.browser';PORT=19222
EXPECTED='1062cc5384f83cb737baa37b60ea9d852096aa900c0e06a5cb29df8d0e58c031'
URL='http://127.0.0.1:18765/r115/mse.html'
def targets():
 for endpoint in ('/json/list','/json'):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{PORT}'+endpoint,timeout=4) as h:return json.loads(h.read())
  except Exception:pass
 return []
def evaluate_page(match,script,timeout=30):
 for t in targets():
  if match in (t.get('url') or '') and t.get('webSocketDebuggerUrl'):
   return cdp_eval(t['webSocketDebuggerUrl'],script,timeout=timeout)
 raise RuntimeError('Real Android Kiwi CDP target unavailable: '+match)
def write(path,data):pathlib.Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def execute(run,snapshot,state,out,fixture_url,type_internal_url,native_extensions_menu):
 out=pathlib.Path(out);record={'stage':'R115','scope':'real Android11 Kiwi synthetic webpage MSE appendBuffer → extension R100 WAL; original panel interface and download receipts independent','gates':{},'errors':[],'not_claimed':['Android16','512MiB','DRM','multi-track','unrestricted 3rd-party media','complete playback acceptance']}
 srv=None
 def gate(key,ok,detail):
  status='PASS' if ok else 'FAIL';record['gates'][key]={'status':status,'detail':detail};state['gates'][key]={'status':status,'detail':json.dumps(detail,ensure_ascii=False,default=str)[:1650]}
  print('R115_'+status+' '+key+' '+json.dumps(detail,ensure_ascii=False,default=str)[:300],flush=True)
  if not ok:raise AssertionError(key)
 try:
  fixture=pathlib.Path('kiwi-r112-lab/fixtures/r93_synthetic_h264_aac_fmp4.b64');media=base64.b64decode(fixture.read_text(),validate=True)
  gate('R115_01_fixed_real_av_fixture',len(media)==116985 and hashlib.sha256(media).hexdigest()==EXPECTED,{'bytes':len(media),'sha':EXPECTED})
  package=pathlib.Path(os.environ['R103_PRODUCTION_ZIP']);z=zipfile.ZipFile(package)
  gate('R115_02_real_installed_candidate_identity',z.testzip() is None and {'mse-store-router-r115.js','mse-wal-adapter-r113.js','mse-page-r94.js'}.issubset(z.namelist()),{'sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'members':len(z.namelist())})
  # Public synthetic fixture server; no private source or user data served.
  media_path=out/'r115_fixture_h264_aac_fmp4.mp4';media_path.write_bytes(media)
  srv=subprocess.Popen(['python3','kiwi-r115-lab/r115_fixture_server.py','--fixture',str(media_path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  for _ in range(40):
   try:
    with urllib.request.urlopen(URL,timeout=1) as h:
     if b'R115_MSE_FIXTURE_READY' in h.read():break
   except Exception:time.sleep(.25)
  else:raise RuntimeError('R115 localhost fixture server unavailable')
  rc,rev=run(['adb','reverse','tcp:18765','tcp:18765'])
  gate('R115_03_android_reverse_real_fixture',rc==0,{'rc':rc,'info':rev[:200]})
  info=probe_cdp(run,out/'r115_cdp_probe' if False else out);ws=info.get('_websocket_url')
  gate('R115_04_genuine_installed_panel_cdp',bool(ws),{'target':info.get('found_target')})
  panel=cdp_eval(ws,'''(async()=>{if(!location.href.startsWith('chrome-extension://')||!location.pathname.endsWith('panel.html'))throw Error('No original panel');
   if(typeof KiwiMseStoreRouterR115==='undefined')throw Error('Router not loaded in original panel');
   let tab=await new Promise((ok,no)=>chrome.tabs.create({url:"'''+URL+'''",active:true},t=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):ok(t)));
   return {tabId:tab.id,url:tab.url,routerLoaded:true,extensionId:chrome.runtime.id};})()''',timeout=35)
  gate('R115_05_actual_panel_origin_created_controlled_tab',panel.get('routerLoaded') and panel.get('tabId')>0, panel)
  tab_id=panel['tabId'];page=None
  for _ in range(36):
   try:
    page=evaluate_page('/r115/mse.html','''({href:location.href,fixture:!!document.querySelector('#r115-video'),info:window.r115Info,
      nativeMSE:!!window.MediaSource,pageHook:!!window.__kiwiMsePageR94,diagHook:!!window.__kiwiMseProbeR93})''')
    if page.get('info',{}).get('status') in ('READY','UNSUPPORTED_CODEC','NO_MSE','SOURCE_BUFFER_FAIL','BOOT_FAILED'):break
   except Exception:pass
   time.sleep(1)
  gate('R115_06_real_page_Main_world_MSE_and_sourcebuffer',page and page.get('info',{}).get('status')=='READY' and page.get('pageHook') and page.get('diagHook') and str(page['info'].get('blobUrl','')).startswith('blob:http://127.0.0.1:18765/'),page)
  # Original panel JavaScript is closure-scoped. CDP MUST use exposed native DOM
  # controls, not inject calls to private functions (R115 first-run test error).
  navigation=cdp_eval(ws,'''(async()=>{
    const tabs=await new Promise((ok,no)=>chrome.tabs.query({},x=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):ok(x)));
    const mine=tabs.filter(t=>(t.url||'').startsWith(location.origin+'/panel.html'));
    if(!mine.length)throw Error('No genuine extension panel tab');
    const panel=mine.sort((a,b)=>(b.lastAccessed||0)-(a.lastAccessed||0))[0];
    const to=location.origin+'/panel.html?tabId='+'''+str(tab_id)+''';
    setTimeout(()=>chrome.tabs.update(panel.id,{url:to,active:true}),400);
    return {panelId:panel.id,target:to,tabId:'''+str(tab_id)+'''};
  })()''',timeout=30)
  record['panel_navigation']=navigation
  time.sleep(5)
  newpanel=probe_cdp(run,out);ws=newpanel.get('_websocket_url')
  gate('R115_07_panel_original_tabId_route_reinitialized',bool(ws) and newpanel.get('found_target',{}).get('url','').endswith('tabId='+str(tab_id)),
      {'tabId':tab_id,'route':newpanel.get('found_target'),'planned':navigation})
  ui=None
  for n in range(15):
   ui=cdp_eval(ws,'''(()=>{
    const d=document.getElementById('media-security-details');if(d&&!d.open)d.open=true;
    const b=document.getElementById('media-security-refresh');if(b)b.click();
    const sel=document.getElementById('mse-r94-player');
    return {siteUrl:document.getElementById('site-url')?.textContent||'',
      players:sel?[...sel.options].map(x=>({value:x.value,label:x.textContent})):[],
      diag:document.getElementById('mse-r95-diag')?.textContent||'',pageReady:document.readyState};
   })()''',timeout=25)
   if any(x.get('value')==page['info']['blobUrl'] for x in ui.get('players',[])):break
   time.sleep(2)
  record['panel_players']=ui
  gate('R115_07b_original_UI_refresh_detected_MSE_player',ui and URL==ui.get('siteUrl') and
      any(x.get('value')==page['info']['blobUrl'] for x in ui.get('players',[])),ui)
  # Click ORIGINAL button event handler, scoped to actual selected playback tab.
  clicked=cdp_eval(ws,'''(()=>{const sel=document.getElementById('mse-r94-player');sel.value='''+json.dumps(page['info']['blobUrl'])+''';
   const b=document.getElementById('mse-r94-start');if(!b||b.disabled)throw Error('Original UI start button missing');
   window.confirm=()=>true;b.click();return {clicked:true,player:sel.value,label:b.textContent};})()''')
  active=None
  def status_js():
   return '''(async()=>await new Promise((ok,no)=>chrome.runtime.sendMessage({type:'MSE_R94_STATUS',tabId:'''+str(tab_id)+'''},r=>{
    if(chrome.runtime.lastError)no(Error(chrome.runtime.lastError.message));else ok(r);
   })))()'''
  for _ in range(25):
   time.sleep(1)
   active=cdp_eval(ws,status_js())
   if any(x.get('tabId')==tab_id and x.get('armed') for x in active.get('active',[])):break
  gate('R115_08_original_ui_button_authorized_and_armed',active and any(x.get('tabId')==tab_id and x.get('armed') for x in active.get('active',[])),{'clicked':clicked,'active':active.get('active') if active else None,'statusUI':cdp_eval(ws,"document.getElementById('mse-r94-status').textContent")})
  task=next(x for x in active['active'] if x.get('tabId')==tab_id)
  push=evaluate_page('/r115/mse.html','''(async()=>await window.r115Push())()''',timeout=80)
  gate('R115_09_real_MSE_SourceBuffer_append_and_sourceended',push.get('ok') and push.get('bytes')==len(media) and push.get('appendCalls')==1,push)
  finalized=None
  for _ in range(30):
   time.sleep(1)
   finalized=cdp_eval(ws,status_js())
   if any(x.get('id')==task['id'] and x.get('state')=='staged-unverified' for x in finalized.get('tasks',[])):break
  match=next((x for x in (finalized or {}).get('tasks',[]) if x.get('id')==task['id']),None)
  gate('R115_10_real_page_bridge_background_flush_and_end',bool(match) and match.get('bytes')==len(media) and match.get('state')=='staged-unverified' and match.get('backend')=='R100-WAL-worker',{'matched':match,'jobId':task['id']})
  # Refresh actual panel saved-job selector to validate routing and old R94 retention.
  jobs=None
  for _ in range(12):
   jobs=cdp_eval(ws,'''(()=>{document.getElementById('mse-r94-refresh').click();
    return [...document.getElementById('mse-r94-jobs').options].map(x=>({value:x.value,label:x.textContent}));})()''')
   if any(x.get('value','').endswith('|'+task['id']) for x in jobs):break
   time.sleep(1)
  record['panel_saved_task_options']=jobs
  gate('R115_11_original_panel_displays_true_backend_and_task',any(x.get('value')=='R100-WAL-worker|'+task['id'] for x in jobs),jobs)
  check=cdp_eval(ws,'''(async()=>{const id='''+json.dumps(task['id'])+''',store=KiwiMseWalAdapterR113.create({chromeApi:chrome});
    const assembled=await store.assemble(id),verify=await KiwiMp4VerifyR94.verify(assembled.file,{requireAudio:true});
    const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',await assembled.file.arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join('');
    await assembled.remove();return {backend:'R100-WAL-worker',bytes:assembled.file.size,sha256:digest,verify};})()''',timeout=90)
  record['panel_assembly']=check
  gate('R115_11b_original_MSE_MP4_byte_identity',check.get('backend')=='R100-WAL-worker' and check.get('bytes')==len(media) and check.get('sha256')==EXPECTED and check.get('verify',{}).get('ok') is True,check)
  # Real export button click, then confirm browser receipt separately.
  button=cdp_eval(ws,'''(()=>{const sel=document.getElementById('mse-r94-jobs');
   sel.value='''+json.dumps('R100-WAL-worker|'+task['id'])+''';
   document.getElementById('mse-r94-export').click();
   return {clicked:true,selectedKey:sel.value};})()''')
  receipt=None
  for _ in range(45):
   time.sleep(1)
   receipt=cdp_eval(ws,'''({status:document.getElementById('mse-r94-status').textContent,jobs:[...document.getElementById('mse-r94-jobs').options].map(x=>x.value)})''')
   st=receipt.get('status','')
   if ('浏览器已报告文件保存完成' in st or '暂存仍保留' in st or '导出失败' in st or '失败' in st):break
  record['export_button']={'button':button,'ui':receipt}
  gate('R115_12_original_panel_export_button_executed',button.get('clicked') and receipt and ('下载' in receipt.get('status','') or '文件保存' in receipt.get('status','') or '暂存' in receipt.get('status','')),record['export_button'])
  # G4 download completion is intentionally distinct: leave open if only an unverified fallback.
  receipt_state='complete' if '浏览器已报告文件保存完成' in receipt.get('status','') else ('retained-unverified' if '暂存仍保留' in receipt.get('status','') else 'unknown')
  record['download_completion']={'state':receipt_state,'rawStatus':receipt.get('status')}
  if receipt_state!='complete':
   state['gates']['R115_13_real_download_completion']={'status':'NOT_RUN','detail':str(record['download_completion'])}
   record['gates']['R115_13_real_download_completion']={'status':'NOT_RUN','detail':record['download_completion']}
  else:
   gate('R115_13_real_download_completion',True,record['download_completion'])
  record['result']='SUB_PASS_SCOPED' if receipt_state=='complete' else 'PARTIAL'
 except Exception as e:
  record['result']='FAIL';record['errors'].append(repr(e));record['traceback']=traceback.format_exc()[-6500:]
  if not any(v['status']=='FAIL' for v in record['gates'].values()):
   state['gates']['R115_99_exception']={'status':'FAIL','detail':repr(e)}
   record['gates']['R115_99_exception']={'status':'FAIL','detail':repr(e)}
 finally:
  if srv:
   srv.terminate()
   try:srv.wait(timeout=5)
   except Exception:srv.kill()
  write(out/OUT_NAME,record)
  print('R115_RESULT',json.dumps({'result':record['result'],'gates':{k:v['status'] for k,v in record['gates'].items()}},ensure_ascii=False),flush=True)
 return record
