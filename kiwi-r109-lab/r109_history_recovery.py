#!/usr/bin/env python3
"""R109 real Android Kiwi history export. Frozen official MV2 V0.4.58.

Only drives the *existing* UI / original DOM event handlers; NEVER crafts a
synthetic history export and NEVER modifies the installed extension. Any PASS
requires a genuine post-restart Android download and independent ZIP parity.
"""
import hashlib, json, pathlib, re, time, urllib.request, traceback
from datetime import datetime
from xml.etree import ElementTree as ET
from r108_restart_history import (baseline, getpid, ui_nodes, touch, evidence_gate,
                                  report_json, pulled_history_zip)
from r108_offline_recovery_parity import verify as replay_verify
PKG='com.kiwibrowser.browser'
PORT=19222

def probe_cdp(run,out):
    """Probe supported Android DevTools socket, never assume Kiwi enables it."""
    rc,unix=run(['adb','shell','cat','/proc/net/unix'],timeout=25)
    (out/'r109_android_unix_socket_names.txt').write_text('\n'.join(
        line for line in unix.splitlines() if 'devtools_remote' in line or 'webview_devtools_remote' in line),encoding='utf-8')
    candidates=['chrome_devtools_remote']
    candidates += list(dict.fromkeys(re.findall(r'@?(\w+devtools_remote\w*)',unix)))
    result={'unix_rc':rc,'candidate_sockets':candidates,'attempts':[]}
    for sock in candidates[:7]:
        run(['adb','forward','--remove','tcp:'+str(PORT)],timeout=10)
        rc,msg=run(['adb','forward','tcp:'+str(PORT),'localabstract:'+sock],timeout=18)
        att={'socket':sock,'forward_rc':rc,'message':msg[:200]}
        if rc!=0:
            result['attempts'].append(att);continue
        for path in ('/json/list','/json'):
            try:
                with urllib.request.urlopen('http://127.0.0.1:'+str(PORT)+path,timeout=3) as resp:
                    payload=json.loads(resp.read())
                if isinstance(payload,list):
                    found=[t for t in payload if 'chrome-extension://' in (t.get('url') or '') and 'panel.html' in (t.get('url') or '')]
                    att.update({'targets':len(payload),'extension_targets':len(found),'http_path':path})
                    result['attempts'].append(att)
                    if found:
                        result['found_target']={'title':found[0].get('title'),
                            'url':found[0].get('url'),'type':found[0].get('type')}
                        result['_websocket_url']=found[0].get('webSocketDebuggerUrl')
                        result['socket']=sock
                        return result
                    break
            except Exception as exc:
                att.setdefault('errors',[]).append(type(exc).__name__+': '+str(exc)[:140])
        result['attempts'].append(att)
    return result

def cdp_eval(wsurl,expression,timeout=20):
    """Run on current formal panel DOM; use Chromium's own event handlers."""
    import websocket
    ws=websocket.create_connection(wsurl,timeout=timeout,suppress_origin=True)
    try:
        ws.send(json.dumps({'id':8109,'method':'Runtime.evaluate','params':{
            'expression':expression,'returnByValue':True,'awaitPromise':True}}))
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            x=json.loads(ws.recv())
            if x.get('id')==8109:
                if x.get('error'):raise RuntimeError(str(x['error']))
                result=x['result']
                if result.get('exceptionDetails'):raise RuntimeError(str(result['exceptionDetails']))
                return result['result'].get('value')
        raise TimeoutError('CDP Runtime.evaluate response timed out')
    finally:ws.close()

PREPARE_JS='''(async()=>{
  const a=document.getElementById('simple-advanced');
  if(!document.body.classList.contains('legacy-expanded'))a.click();
  const history=document.getElementById('capture-history');
  if(!history.open)history.querySelector('summary').click();
  history.scrollIntoView({block:'start'});
  await new Promise(resolve=>setTimeout(resolve,2500));
  return {url:location.href,advanced:document.body.classList.contains('legacy-expanded'),
    opened:history.open, rows:[...document.querySelectorAll('.r39-history-row')].map(r=>({
      details:r.querySelector('.source-desc')?.textContent, title:r.querySelector('.source-name')?.textContent,
      buttons:[...r.querySelectorAll('button')].map(b=>b.textContent)})),
    scrollTop:document.scrollingElement?.scrollTop};
})()'''

def cdp_match_and_export(wsurl,pre):
    # Require frozen task's exact localized calendar date, second and request count.
    dt=datetime.fromisoformat(pre['startedAt'].replace('Z','+00:00'))
    marker=f'{dt.year}年{dt.month}月{dt.day}日 {dt.hour:02}:{dt.minute:02}:{dt.second:02}'
    count=len(pre['requests'])
    expected=f'已结束 · 请求 {count}'
    js='''(()=>{
      const expected=%s, marker=%s;
      const rows=[...document.querySelectorAll('#capture-history-list .r39-history-row')]
        .filter(r=>{const text=r.querySelector('.source-desc')?.textContent||'';
          return text.includes(expected) && text.includes(marker);});
      if(rows.length!==1)return {clicked:false,reason:'Expected exactly 1 historical task',
        matches:rows.length,all:document.querySelectorAll('#capture-history-list .r39-history-row').length};
      const controls=[...rows[0].querySelectorAll('button')].filter(x=>x.textContent.trim()==='导出');
      if(controls.length!==1)return {clicked:false,reason:'Expected exactly 1 export button',buttons:controls.length};
      const b=controls[0];b.scrollIntoView({block:'center'});
      const rect=b.getBoundingClientRect();
      const detail=rows[0].querySelector('.source-desc')?.textContent||'';
      b.click();  // original V0.4.58 click listener calls exportHistoricalTask(captureSessionId)
      return {clicked:true,route:'cdp_original_button_click',historicalDescription:detail,
          buttonBounds:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
    })()''' %(json.dumps(expected,ensure_ascii=False),json.dumps(marker,ensure_ascii=False))
    return cdp_eval(wsurl,js)

def fallback_ui_click_history(run,snapshot,pre,output):
    """ADB only: scroll the outer page, then nested #capture-history-list.
    Never tap offscreen 0,0 or an unidentified row. Save a screenshot/XML per move.
    """
    expected=f'已结束 · 请求 {len(pre["requests"])}'
    dt=datetime.fromisoformat(pre['startedAt'].replace('Z','+00:00'))
    started_at=f'{dt.year}年{dt.month}月{dt.day}日 {dt.hour:02}:{dt.minute:02}:{dt.second:02}'
    actions=[];xml=snapshot('r109_ui_initial_panel')
    # In normal mode, the original history is hidden behind advanced UI.
    if '展开高级工具' in xml:
        expanded=touch(xml,['展开高级工具'],run,snapshot,'r109_ui_advanced_expanded')
        if not expanded:return {'clicked':False,'reason':'Formal advanced toggle was not clickable','actions':actions}
        xml=expanded['xml']
        actions.append({'mode':'expanded_original_advanced_button','hit':expanded['hit']})
    for i in range(42):
        rows=ui_nodes(xml)
        labels=[n for n in rows if '历史观察记录与恢复' in n.get('text','')]
        if labels:
            clicked=touch(xml,['历史观察记录与恢复'],run,snapshot,'r109_open_history_'+str(i))
            if clicked:
                xml=clicked['xml'];actions.append({'step':i,'mode':'opened_history','hit':clicked['hit']});break
        # Scroll root page on inner right-hand PAD; avoid nested 380px source list.
        x=1030 if i%3!=2 else 795
        rc,_=run(['adb','shell','input','swipe',str(x),'1480',str(x),'405','480'])
        time.sleep(1.4);xml=snapshot('r109_outer_scroll_'+str(i))
        actions.append({'step':i,'mode':'outer','x':x,'history_label_detected':bool(labels)})
    else:
        return {'clicked':False,'reason':'History details not reached','actions':actions}
    time.sleep(4);xml=snapshot('r109_history_loaded')
    for i in range(48):
        # Use parent chain from UI XML; do not accidentally match concatenated list.
        matched=find_exact_ui_export(xml,expected,started_at=started_at)
        if matched:
            x,y,label=matched
            run(['adb','shell','input','tap',str(x),str(y)])
            time.sleep(3);xml=snapshot('r109_export_tapped')
            actions.append({'step':i,'mode':'clicked_verified_history_export','tap':[x,y]})
            return {'clicked':True,'route':'adb_real_visible_button','match':label,'actions':actions,'xml':xml}
        # When row is offscreen, move root panel first; afterwards nested list.
        x=1028 if i<14 else 820
        start_y=1490;end_y=425
        run(['adb','shell','input','swipe',str(x),str(start_y),str(x),str(end_y),'430'])
        time.sleep(1.0);xml=snapshot('r109_history_scroll_'+str(i))
        actions.append({'step':i,'mode':'outer' if i<14 else 'list','x':x,
                        'expected_text_present':expected in xml})
    return {'clicked':False,'reason':'No unique real visible export button','actions':actions}

def find_exact_ui_export(xml,expected,started_at=None):
    """Match original WebView flattened task siblings, not a fictitious row subtree.

    R108 authentic Android Uiautomator dumps put all history rows under one
    android.view.View scrollable=true: title, detail, 查看, 导出, 长会话分卷,
    清空此任务 repeated per row. Row descendants do NOT contain their buttons.
    """
    try:root=ET.fromstring(xml[xml.index('<?xml'):])
    except (ValueError,ET.ParseError):return None
    parents={child:parent for parent in root.iter() for child in parent}
    matches={}
    for detail in root.iter('node'):
        desc=detail.attrib.get('text','')
        if expected not in desc or len(desc)>140 or '127.0.0.1' in desc:continue
        if started_at and started_at not in desc:continue
        # UIAutomator often nests a duplicate TextView; locate the nearest
        # scrollable container with direct sequential task children.
        anc=detail
        while anc is not None and anc.attrib.get('scrollable')!='true':
            anc=parents.get(anc)
        if anc is None:continue
        children=list(anc)
        positions=[i for i,c in enumerate(children) if (expected in c.attrib.get('text','')
                   and len(c.attrib.get('text',''))<140
                   and (not started_at or started_at in c.attrib.get('text','')))]
        for i in positions:
            following=children[i+1:i+7]
            # Each real row uses four button siblings, starting with 查看.
            # Require this exact order, not the next export globally.
            labels=[n.attrib.get('text') for n in following[:4]]
            if labels != ['查看','导出','长会话分卷','清空此任务']:continue
            b=following[1]
            if b.attrib.get('clickable')!='true':continue
            m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',b.attrib.get('bounds',''))
            if not m:continue
            x1,y1,x2,y2=map(int,m.groups());x=(x1+x2)//2;y=(y1+y2)//2
            if not(x2>x1 and y2>y1 and 80<x<1010 and 100<y<1770):continue
            matches[(id(anc),i)]=(x,y,desc)
    return next(iter(matches.values())) if len(matches)==1 else None

def execute(original_zip,run,snapshot,state,out,fixture_url,type_internal_url):
    record={'stage':'R109','scope':'unaltered MV2 V0.4.58 actual Android Kiwi','gates':{},'cdp':{},
            'source_altered':False,'media_persistence_covered':False}
    def gate(key,ok,detail):
        evidence_gate(record,key,ok,detail)
        state['gates'][key]={'status':record['gates'][key]['status'],'detail':str(detail)[:1500]}
    try:
        pre=baseline(original_zip)
        gate('R109_01_formal_pre_restart_36_requests',len(pre['requests'])>=36 and len(pre['bodies'])>=36 and bool(pre['endedAt']),
             {'session':pre['session'],'requests':len(pre['requests']),'body_files':len(pre['bodies']),'ended':pre['endedAt']})
        old=getpid(run)
        rc,_=run(['adb','shell','am','force-stop',PKG]);time.sleep(3)
        stopped=getpid(run)
        gate('R109_02_real_force_stop',rc==0 and bool(old) and not stopped,{'old':old,'stopped':stopped})
        rc,_=run(['adb','shell','monkey','-p',PKG,'-c','android.intent.category.LAUNCHER','1']);time.sleep(12)
        new=getpid(run)
        gate('R109_03_new_original_kiwi_process',rc==0 and bool(new) and not(set(old)&set(new)),{'old':old,'new':new})
        xml=snapshot('r109_real_kiwi_restarted')
        # Match the actual installed ID from the genuine Kiwi extension manager.
        manager=(out/'extension_after_import.xml').read_text(encoding='utf8')
        m=re.search(r'ID:\s*([a-p]{32})',manager)
        if not m:raise ValueError('Formal ID not confirmed in real manager')
        extension_id=m.group(1)
        # R109 / V8.10.1 route switch after repeated direct URL failures:
        # use the ORIGINAL Kiwi Extensions > Details > Extension options.
        from r109_panel_entry_v8101 import open_original_panel,page_ok
        xml,entry=open_original_panel(run,snapshot,type_internal_url,extension_id,fixture_url)
        record['original_panel_entry']=entry
        panel_valid=page_ok(xml)
        gate('R109_04_original_extension_panel_opens',panel_valid,
             {'extension_id':extension_id,'bytes_ui_xml':len(xml),
              'entry_route':entry.get('selected_route'),
              'manager_id_matched':entry.get('matched_installed_id',False)})
        if not panel_valid:
            record['unexecuted']=['R109_05_cdp_discovery','R109_06_original_history_export_clicked',
                'R109_07_historic_zip_real_adb_pull','R108_11_same_original_capture_session',
                'R108_12_no_request_loss_or_duplication','R108_13_cdp_body_byte_identity']
            raise RuntimeError('Real original Kiwi options panel navigation failed; see manager/option screenshots')
        # Try a trusted direct Android CDP session, but only if the unchanged
        # browser actually exposes its own web debugging socket.
        cdp=probe_cdp(run,out)
        ws=cdp.pop('_websocket_url',None)
        record['cdp']=cdp
        # CDP is an optional instrumentation route, not a mandatory browser feature.
        if ws:
            gate('R109_05_android_cdp_discovery',True,{'socket':cdp.get('socket'),'targets':cdp.get('found_target')})
        else:
            record['gates']['R109_05_android_cdp_discovery']={
                'status':'NOT_AVAILABLE','detail':'No authentic Kiwi extension CDP target; use native UI fallback'}
            state['gates']['R109_05_android_cdp_discovery']={
                'status':'NOT_RUN','detail':'Optional test path not available; no claim of CDP support'}

        chosen=None;last_xml=xml
        if ws:
            try:
                prep=cdp_eval(ws,PREPARE_JS,timeout=25)
                record['cdp']['prepare']=prep
                if prep.get('advanced') and prep.get('opened') and prep.get('rows'):
                    chosen=cdp_match_and_export(ws,pre)
                    record['cdp']['selection']=chosen
                    last_xml=snapshot('r109_cdp_original_export_pressed')
            except Exception as e:
                record['cdp']['error']=repr(e)
        if not chosen or not chosen.get('clicked'):
            # Public socket unavailable is NOT a product failure. Fallback to
            # real touch, but never fake the result.
            ui=fallback_ui_click_history(run,snapshot,pre,out)
            record['ui_fallback']={k:v for k,v in ui.items() if k!='xml'}
            chosen=ui
            last_xml=ui.get('xml',last_xml)
        gate('R109_06_original_history_export_clicked',bool(chosen and chosen.get('clicked')),
             {k:v for k,v in (chosen or {}).items() if k not in ('xml','actions')})
        if chosen and chosen.get('clicked'):
            historical,meta=pulled_history_zip(last_xml,run,snapshot,out)
            gate('R109_07_historic_zip_real_adb_pull',bool(historical and meta.get('crc_error') is None),meta)
            if historical:
                proof=replay_verify(original_zip,historical,out/'r109_pre_post_export_parity.json')
                for key,g in proof['gates'].items():gate(key,g['status']=='PASS',g['details'])
                record['zip_parity_summary']=proof['summary']
        else:
            record['unexecuted']=['R109_07_historic_zip_real_adb_pull','R108_11_same_original_capture_session',
                 'R108_12_no_request_loss_or_duplication','R108_13_cdp_body_byte_identity','R108_14_task_remains_closed']
    except Exception as e:
        gate('R109_99_error',False,repr(e))
        record['traceback']=traceback.format_exc()[-3600:]
    finally:
        report_json(out/'r109_actual_history_recovery_status.json',record)
        print('R109_ACTUAL_HISTORY_RECOVERY',json.dumps({k:g['status'] for k,g in record['gates'].items()}),flush=True)
    return record
