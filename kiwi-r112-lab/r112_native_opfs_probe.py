#!/usr/bin/env python3
"""R112: real Kiwi Android MV2 extension-origin OPFS, process restart and recovery.

Uses the UNMODIFIED production mse-journal-r94.js loaded in the original panel.
CDP is a test transport into the genuine installed Kiwi extension page, not a fake
DOM or replacement journal. Input is a locally generated synthetic H.264/AAC fMP4.
DO NOT claim playback->CDP requestId attribution, >=512 MiB, MSE page capture,
or Android16 OEM coverage from this scoped test.
"""
from __future__ import annotations
import base64, hashlib, json, os, pathlib, re, subprocess, sys, time, traceback
from r109_history_recovery import cdp_eval, probe_cdp
from r109_panel_entry_v8101 import open_original_panel, page_ok
from r108_restart_history import getpid

PKG='com.kiwibrowser.browser'

def sha(b): return hashlib.sha256(b).hexdigest()
def dump(p,o): pathlib.Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')

def synth_media(out):
    path=out/'r112_controlled_fmp4_av.mp4'
    args=['ffmpeg','-nostdin','-y','-loglevel','error',
      '-f','lavfi','-i','testsrc2=size=160x90:rate=15',
      '-f','lavfi','-i','sine=frequency=440:sample_rate=32000',
      '-t','2','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
      '-c:a','aac','-b:a','64k',
      '-movflags','frag_keyframe+empty_moov+default_base_moof',str(path)]
    p=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if p.returncode: raise RuntimeError('R112 controlled ffmpeg failed '+p.stderr[-700:])
    probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_name,codec_type',
      '-of','json',str(path)],capture_output=True,text=True,timeout=20)
    if probe.returncode:raise RuntimeError('R112 media ffprobe failed '+probe.stderr[-450:])
    streams=json.loads(probe.stdout)['streams']
    if not {'audio','video'}.issubset({r.get('codec_type') for r in streams}):
        raise RuntimeError('R112 fixture does not contain both real audio and video streams')
    data=path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':sha(data),'streams':streams,'base64':base64.b64encode(data).decode('ascii')}

def begin_js(job,encoded):
    return '''(async()=>{
      const id=%s, encoded=%s;
      if(!location.href.startsWith('chrome-extension://')||!location.pathname.endsWith('/panel.html'))
        throw Error('Not the genuine installed extension panel');
      if(typeof KiwiMseJournalR94==='undefined'||typeof navigator.storage?.getDirectory!=='function')
        throw Error('Genuine extension OPFS or media journal unavailable');
      const bytes=Uint8Array.from(atob(encoded),x=>x.charCodeAt(0));
      const digest=async x=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',x)))
        .map(b=>b.toString(16).padStart(2,'0')).join('');
      const j=KiwiMseJournalR94.create({navigator,sharded:true});
      const pageUrl='http://127.0.0.1:18764/r112-authorized-fixture';
      const blobUrl='blob:http://127.0.0.1:18764/r112-media';
      await j.init({id,pageUrl,blobUrl,tabId:112,playerId:'r112-controlled-not-playback',maxBytes:2*1048576});
      let wrongIdentity=null;
      try{await j.add({id,blobUrl:'blob:http://other.invalid/nope',trackId:'track-1',
        mime:'video/mp4',appendIndex:1,partIndex:0,partCount:1,data:new Uint8Array([1,2,3])});}
      catch(e){wrongIdentity=e.code||String(e);}
      const mime='video/mp4;codecs="avc1.42e01e,mp4a.40.2"';
      let part=0;
      for(let offset=0;offset<bytes.length;offset+=32768){
        part++;
        await j.add({id,blobUrl,trackId:'track-1',mime,
          appendIndex:part,partIndex:0,partCount:1,data:bytes.slice(offset,offset+32768)});
      }
      const ended=await j.end(id,true);
      return {stage:'written',id,origin:location.origin,opfs:true,bytes:bytes.length,
        sha256:await digest(bytes),ended,wrongIdentity,quota:await navigator.storage.estimate()};
    })()''' %(json.dumps(job),json.dumps(encoded))

def recovered_js(job):
    return '''(async()=>{
      const id=%s;
      if(!location.href.startsWith('chrome-extension://')||!location.pathname.endsWith('/panel.html'))
        throw Error('Not genuine restored extension panel');
      if(typeof KiwiMseJournalR94==='undefined'||typeof navigator.storage?.getDirectory!=='function')
        throw Error('Original OPFS API missing after Kiwi restart');
      const j=KiwiMseJournalR94.create({navigator,sharded:true});
      const jobs=await j.list(),status=await j.status(id),assembled=await j.assemble(id);
      const data=await assembled.file.arrayBuffer(),buf=new Uint8Array(data);
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buf)))
        .map(b=>b.toString(16).padStart(2,'0')).join('');
      let blocked=null;
      try{await j.add({id,blobUrl:status.blobUrl,trackId:'track-1',mime:'video/mp4',
        appendIndex:status.appendCalls+1,partIndex:0,partCount:1,data:new Uint8Array([1,2,3])});}
      catch(e){blocked=e.code||String(e);}
      return {stage:'recovered',origin:location.origin,id,status,foundInList:jobs.some(x=>x.id===id),
        reconstructedBytes:buf.length,reconstructedSha256:digest,
        outputState:assembled.state,verifiedPlayback:assembled.verifiedPlayback,
        endWriteRejected:blocked,quota:await navigator.storage.estimate()};
    })()''' %json.dumps(job)

def execute(run,snapshot,state,out,fixture_url,type_internal_url,native_extensions_menu):
    out=pathlib.Path(out); record={'stage':'R112','test':'original R94 media journal, Android11 Kiwi extension OPFS with process restart',
      'scope':'2-second synthetic playable A/V fMP4; NOT >=512MiB, not MSE ingest, not player/CDP identity',
      'package_modified':False,'gates':{},'errors':[]}
    def gate(name,ok,detail):
      record['gates'][name]={'status':'PASS' if ok else 'FAIL','detail':detail}
      state['gates'][name]={'status':'PASS' if ok else 'FAIL','detail':json.dumps(detail,ensure_ascii=False)[:1700]}
      print(('PASS ' if ok else 'FAIL ')+name+': '+str(detail)[:280],flush=True)
      if not ok:raise AssertionError(name)
    try:
      fixture=synth_media(out); recorded={k:v for k,v in fixture.items() if k!='base64'}
      record['fixture']=recorded
      gate('R112_01_controlled_real_av_media',fixture['bytes']>10000 and len(fixture['streams'])>=2,recorded)
      mngr=(out/'extension_after_import.xml').read_text(encoding='utf8')
      m=re.search(r'ID:\s*([a-p]{32})',mngr)
      gate('R112_02_installed_extension_id',bool(m),{'extensionId':m.group(1) if m else None})
      extension_id=m.group(1)
      r112_probe_dir=out/'r112_cdp_evidence';r112_probe_dir.mkdir(exist_ok=True)
      cdp=probe_cdp(run,r112_probe_dir);ws=cdp.get('_websocket_url')
      gate('R112_03_original_panel_cdp_available',bool(ws),
        {'socket':cdp.get('socket'),'target':cdp.get('found_target')})
      job='r112av'+os.environ.get('GITHUB_RUN_ID','local112')
      gate('R112_04_unique_job_id',bool(re.fullmatch('[a-zA-Z0-9_-]{8,72}',job)),{'job':job})
      w=cdp_eval(ws,begin_js(job,fixture['base64']),timeout=75)
      record['before_restart']=w
      gate('R112_05_real_opfs_original_module_write',w.get('stage')=='written' and
        w.get('sha256')==fixture['sha256'] and w.get('bytes')==fixture['bytes'] and
        w.get('ended',{}).get('state')=='staged-unverified' and w.get('ended',{}).get('layoutVersion')==2,
        {k:v for k,v in w.items() if k!='quota'})
      gate('R112_06_wrong_media_identity_rejected',w.get('wrongIdentity')=='IDENTITY',
           {'code':w.get('wrongIdentity')})
      old=getpid(run)
      rc,_=run(['adb','shell','am','force-stop',PKG]);time.sleep(3)
      stopped=getpid(run)
      gate('R112_07_real_kiwi_force_stop',rc==0 and bool(old) and not stopped,{'pidBefore':old,'pidAfterStop':stopped})
      rc,_=run(['adb','shell','monkey','-p',PKG,'-c','android.intent.category.LAUNCHER','1']);time.sleep(12)
      new=getpid(run)
      gate('R112_08_new_kiwi_process',rc==0 and bool(new) and not(set(old)&set(new)),{'pidBefore':old,'pidAfter':new})
      snap,entry=open_original_panel(run,lambda label:snapshot('r112_'+label),type_internal_url,extension_id,fixture_url,native_extensions_menu)
      record['restored_panel_entry']=entry
      gate('R112_09_original_panel_after_restart',page_ok(snap),
        {'route':entry.get('selected_route'),'extensionId':extension_id,'uiXmlBytes':len(snap)})
      restored=probe_cdp(run,r112_probe_dir);ws2=restored.get('_websocket_url')
      gate('R112_10_restored_panel_cdp',bool(ws2),{'target':restored.get('found_target')})
      rec=cdp_eval(ws2,recovered_js(job),timeout=75)
      record['after_restart']=rec
      status=rec.get('status',{})
      gate('R112_11_original_opfs_persistence',rec.get('foundInList') and status.get('state')=='staged-unverified' and
        status.get('ended') and status.get('bytes')==fixture['bytes'] and status.get('layoutVersion')==2,
        {'state':status.get('state'),'bytes':status.get('bytes'),'parts':status.get('parts'),
         'layout':status.get('layoutVersion'),'jobFound':rec.get('foundInList')})
      gate('R112_12_post_restart_reassemble_byte_sha',rec.get('reconstructedSha256')==fixture['sha256'] and
        rec.get('reconstructedBytes')==fixture['bytes'] and rec.get('verifiedPlayback') is False,
        {'expectedSha256':fixture['sha256'],'actualSha256':rec.get('reconstructedSha256'),
         'bytes':rec.get('reconstructedBytes'),'verifiedPlayback':rec.get('verifiedPlayback')})
      gate('R112_13_ended_job_write_protected',rec.get('endWriteRejected')=='NOT_RECORDING',
        {'errorCode':rec.get('endWriteRejected')})
      record['result']='SUB_PASS'
    except Exception as exc:
      record['result']='FAIL';record['errors'].append(repr(exc));record['traceback']=traceback.format_exc()[-4500:]
      if not any(x['status']=='FAIL' for x in record['gates'].values()):
         record['gates']['R112_99_unhandled_exception']={'status':'FAIL','detail':repr(exc)}
         state['gates']['R112_99_unhandled_exception']={'status':'FAIL','detail':repr(exc)}
    finally:
      dump(out/'r112_real_kiwi_opfs_restart_status.json',record)
      print('R112_ANDROID_ORIGINAL_OPFS',json.dumps({k:x['status'] for k,x in record['gates'].items()}),flush=True)
    return record
