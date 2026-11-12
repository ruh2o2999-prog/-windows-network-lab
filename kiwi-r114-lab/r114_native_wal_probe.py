#!/usr/bin/env python3
"""R114 true Android Kiwi extension-origin Dedicated Worker / OPFS WAL.
R114-01: native worker, SyncAccessHandle, flush/restart. NOT webpage appendBuffer.
R114-03 scoped: already-ended WAL verified after force-stop.
R114-04 scoped: actual WAL payload CRC corruption fails closed.
Every gate is independently recorded; G5/512MiB/Worker MSE remain open.
"""
import base64, hashlib, json, os, pathlib, re, time, traceback
from r109_history_recovery import cdp_eval, probe_cdp
from r109_panel_entry_v8101 import open_original_panel, page_ok
from r108_restart_history import getpid
PKG='com.kiwibrowser.browser'
FIXTURE_SHA='1062cc5384f83cb737baa37b60ea9d852096aa900c0e06a5cb29df8d0e58c031'
def dump(p,d): pathlib.Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
# Actual Worker is provided by the installed extension, never by this test harness.
# No mocked Worker/storage object is inserted in the page.
RPC="""function call(action,params={}){return new Promise((resolve,reject)=>{
 const reqId=++num,t=setTimeout(()=>reject(Error(action+' timed out')),20000);
 const on=ev=>{const m=ev.data;if(!m||m.reqId!==reqId)return;
  clearTimeout(t);worker.removeEventListener('message',on);resolve(m);};
 worker.addEventListener('message',on);worker.postMessage({...params,action,reqId});
});}"""
def first_js(job,b64):
 return '''(async()=>{const id=%s,encoded=%s;
 if(!location.href.startsWith('chrome-extension://')||!location.pathname.endsWith('/panel.html'))throw Error('Not genuine installed extension panel');
 if(typeof chrome==='undefined'||!chrome.runtime?.getURL||!navigator.storage?.getDirectory)throw Error('Extension/OPFS origin unavailable');
 const workerUrl=chrome.runtime.getURL('mse-opfs-fast-r100-worker.js');
 const worker=new Worker(workerUrl);let num=0;
 %s
 const data=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
 const pageUrl='http://127.0.0.1:18764/r114-user-fixture',blobUrl='blob:http://127.0.0.1:18764/r114-authorized-player';
 const init=await call('init',{id,pageUrl,blobUrl,tabId:114,playerId:'r114-synthetic-control',maxBytes:2097152});
 const rejected=await call('append',{id,blobUrl:'blob:http://other.invalid/unauthorized',mime:'video/mp4',trackId:'track-1',appendIndex:1,partIndex:0,partCount:2,data:'AQID'});
 let chunks=[];for(let index=0;index<2;index++){
  const part=data.slice(index*65536,(index+1)*65536);let str='';for(let o=0;o<part.length;o+=8192)str+=String.fromCharCode(...part.slice(o,o+8192));
  chunks.push(await call('append',{id,blobUrl,trackId:'track-1',mime:'video/mp4;codecs="avc1.42e01e,mp4a.40.2"',appendIndex:1,partIndex:index,partCount:2,data:btoa(str)}));
 }
 const end=await call('end',{id,ended:true});worker.terminate();
 return {origin:location.origin,workerUrl,nativeOPFS:!!navigator.storage.getDirectory,init,rejected,chunks,end,bytes:data.length};
})()'''%(json.dumps(job),json.dumps(b64),RPC)
def after_js(job,mutation_job):
 return '''(async()=>{const id=%s,mutId=%s,worker=new Worker(chrome.runtime.getURL('mse-opfs-fast-r100-worker.js'));let num=0;
 %s
 const status=await call('status',{id}),assembled=await call('assemble',{id});
 const top=await navigator.storage.getDirectory(),root=await top.getDirectoryHandle('kiwi_mse_r100');
 const exports=await root.getDirectoryHandle('exports'),file=await(await exports.getFileHandle(id+'.mp4')).getFile(),bytes=await file.arrayBuffer();
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
 const afterEnd=await call('append',{id,blobUrl:'blob:http://127.0.0.1:18764/r114-authorized-player',mime:'video/mp4',trackId:'track-1',appendIndex:2,partIndex:0,partCount:1,data:'AQID'});
 const init=await call('init',{id:mutId,pageUrl:'http://127.0.0.1:18764/r114-tamper',blobUrl:'blob:http://127.0.0.1:18764/r114-tamper-player',tabId:114,maxBytes:65536});
 const append=await call('append',{id:mutId,blobUrl:'blob:http://127.0.0.1:18764/r114-tamper-player',trackId:'track-1',mime:'video/mp4',appendIndex:1,partIndex:0,partCount:1,data:'AQIDBAUGBwgJCg=='});
 const release=await call('release',{id:mutId});worker.terminate();
 const directory=await root.getDirectoryHandle('job_'+mutId),handle=await directory.getFileHandle('capture.wal'),f=await handle.getFile();
 const arr=new Uint8Array(await f.arrayBuffer());const originalByte=arr[32];arr[32]^=255;
 const writer=await handle.createWritable();await writer.write(arr);await writer.close();
 const w2=new Worker(chrome.runtime.getURL('mse-opfs-fast-r100-worker.js'));
 const damaged=await new Promise((ok,no)=>{const timer=setTimeout(()=>no(Error('WAL rescan timed out')),20000);w2.onmessage=e=>{if(e.data?.reqId===909){clearTimeout(timer);ok(e.data);}};w2.postMessage({action:'status',id:mutId,reqId:909});});w2.terminate();
 return {status,assembled,fileSize:file.size,hash,afterEnd,init,append,release,damaged,originalByte,changedByte:arr[32],estimated:await navigator.storage.estimate()};
})()'''%(json.dumps(job),json.dumps(mutation_job),RPC)
def execute(run,snapshot,state,out,fixture_url,type_internal_url,native_extensions_menu):
 out=pathlib.Path(out);report={'stage':'R114','scope':'Android11 Kiwi official real extension-origin Worker WAL, not webpage MSE or 512MiB','gates':{},'errors':[]}
 def gate(name,ok,details):
  status='PASS' if ok else 'FAIL';v={'status':status,'detail':details};report['gates'][name]=v
  state['gates'][name]={'status':status,'detail':json.dumps(details,ensure_ascii=False)[:1700]}
  print('R114_'+status+' '+name+' '+json.dumps(details,ensure_ascii=False)[:300],flush=True)
  if not ok:raise AssertionError(name)
 try:
  asset=pathlib.Path('kiwi-r112-lab/fixtures/r93_synthetic_h264_aac_fmp4.b64');data=base64.b64decode(asset.read_text(),validate=True)
  assert len(data)==116985 and hashlib.sha256(data).hexdigest()==FIXTURE_SHA
  gate('R114_01_pinned_synthetic_fixture',True,{'bytes':len(data),'sha256':FIXTURE_SHA})
  package=pathlib.Path(os.environ['R103_PRODUCTION_ZIP']); import zipfile
  with zipfile.ZipFile(package) as z:
   assert 'mse-opfs-fast-r100-worker.js' in z.namelist() and 'mse-wal-adapter-r113.js' in z.namelist()
  gate('R114_02_R113_worker_present_in_actual_installed_candidate',True,{'packageSha256':hashlib.sha256(package.read_bytes()).hexdigest()})
  xml=(out/'extension_after_import.xml').read_text(encoding='utf8');m=re.search(r'ID:\s*([a-p]{32})',xml)
  gate('R114_03_original_installed_extension_id',bool(m),{'id':m.group(1) if m else None})
  recdir=out/'r114_wal_native';recdir.mkdir(exist_ok=True)
  info=probe_cdp(run,recdir);ws=info.get('_websocket_url')
  gate('R114_04_extension_CDP_session',bool(ws),{'target':info.get('found_target')})
  job='r114wal'+os.environ.get('GITHUB_RUN_ID','local114');mutId='r114crc'+os.environ.get('GITHUB_RUN_ID','local114')
  b=cdp_eval(ws,first_js(job,base64.b64encode(data).decode()),timeout=150);report['before_restart']=b
  gate('R114_05_native_extension_worker_sync_access_write_flush',b.get('nativeOPFS') and b.get('init',{}).get('ok') is True and b.get('rejected',{}).get('code')=='IDENTITY' and len(b.get('chunks',[]))==2 and b['chunks'][-1].get('bytes')==len(data) and b.get('end',{}).get('state')=='staged-unverified',{'workerUrl':b.get('workerUrl'),'byteCount':b.get('bytes'),'lastAppend':b.get('chunks',[])[-1] if b.get('chunks') else None,'end':b.get('end')})
  before=getpid(run);rc,_=run(['adb','shell','am','force-stop',PKG]);time.sleep(3);stopped=getpid(run)
  gate('R114_06_browser_process_force_stopped',bool(before) and not stopped and rc==0,{'before':before,'afterStop':stopped})
  rc,_=run(['adb','shell','monkey','-p',PKG,'-c','android.intent.category.LAUNCHER','1']);time.sleep(12);after=getpid(run)
  gate('R114_07_new_real_Kiwi_process',rc==0 and bool(after) and not(set(before)&set(after)),{'before':before,'after':after})
  xml,openres=open_original_panel(run,lambda label:snapshot('r114_'+label),type_internal_url,m.group(1),fixture_url,native_extensions_menu)
  gate('R114_08_same_extension_panel_reloaded',page_ok(xml),{'route':openres.get('selected_route'),'extensionId':m.group(1)})
  again=probe_cdp(run,recdir);ws2=again.get('_websocket_url')
  gate('R114_09_new_CDP_session',bool(ws2),{'target':again.get('found_target')})
  r=cdp_eval(ws2,after_js(job,mutId),timeout=150);report['after_restart']=r
  gate('R114_10_reassembled_real_native_OPFS_SHA',r.get('status',{}).get('state')=='staged-unverified' and r.get('status',{}).get('parts')==2 and r.get('fileSize')==len(data) and r.get('hash')==FIXTURE_SHA and r.get('assembled',{}).get('verifiedPlayback') is False,{'status':r.get('status'),'sha':r.get('hash'),'fileSize':r.get('fileSize')})
  gate('R114_11_finalized_recording_write_rejected',r.get('afterEnd',{}).get('code')=='NOT_RECORDING',{'code':r.get('afterEnd',{}).get('code')})
  gate('R114_12_real_WAL_CRC_tamper_detected',r.get('damaged',{}).get('state')=='damaged' and r.get('damaged',{}).get('damage',{}).get('code')=='WAL_CRC',{'rescan':r.get('damaged'),'byteBefore':r.get('originalByte'),'byteAfter':r.get('changedByte')})
  report['result']='SUB_PASS_SCOPED'
 except Exception as e:
  report['result']='FAIL';report['errors'].append(repr(e));report['traceback']=traceback.format_exc()[-7000:]
  if not any(x['status']=='FAIL' for x in report['gates'].values()):
   state['gates']['R114_99_exception']={'status':'FAIL','detail':repr(e)};report['gates']['R114_99_exception']={'status':'FAIL','detail':repr(e)}
 finally:
  dump(out/'r114_native_kiwi_wal_status.json',report)
  print('R114_RESULT '+json.dumps({'status':report['result'],'gates':{k:v['status'] for k,v in report['gates'].items()}},ensure_ascii=False),flush=True)
 return report
