#!/usr/bin/env python3
"""R108 after R107 formal ZIP: same real Android Kiwi; force-stop preserves data.
No official MV2 source edits. Each gate is based on raw ADB/UI/ZIP evidence.
R108 completed-task recovery is distinct from unexpected mid-capture recovery.
"""
import hashlib, json, re, time, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

API_ROUTES=('/r104/api/alpha.json','/r104/api/beta.txt','/r104/api/expected-404','/r104/api/tiny.svg')
def h(b):return hashlib.sha256(b).hexdigest()
def controlled(url):return isinstance(url,str) and any(x in url for x in API_ROUTES)
def signature_rows(tr):
    return sorted((str(r.get('requestEventId','')),str(r.get('nativeRequestId','')),
                   str(r.get('url','')),str(r.get('statusCode',r.get('status',''))))
                   for r in tr.get('requests',[]) if controlled(r.get('url')))
def baseline(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        tr=json.loads(z.read('Trace/trace.json'))
        names=z.namelist()
        idxname=[n for n in names if n.endswith('cdp_response_index.json')]
        assert len(idxname)==1
        idx=json.loads(z.read(idxname[0]))
        bodies={}
        for r in idx:
            if controlled(r.get('url')) and r.get('bodyPath') in names:
                bodies[(str(r.get('key')),str(r.get('requestId')),str(r.get('url')))] =h(z.read(r['bodyPath']))
        return {'session':tr['captureSessionId'],'requests':signature_rows(tr),'total_requests':len(tr.get('requests',[])),
                'bodies':bodies,'fullzip_sha':h(Path(path).read_bytes()),
                'entries':len(names),'index_count':len(idx),'startedAt':tr.get('startedAt'),
                'endedAt':tr.get('endedAt')}
def report_json(path,v):
    path.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True),encoding='utf8')
def getpid(run):
    _,result=run(['adb','shell','pidof','com.kiwibrowser.browser'],timeout=15)
    return sorted({x for x in re.findall(r'\d+',result) if x})
def ui_nodes(xml):
    try:r=ET.fromstring(xml[xml.index('<?xml'):])
    except (ValueError,ET.ParseError):return []
    return [n.attrib for n in r.iter('node')]
def touch(xml,keywords,run,snapshot,label):
    matches=[]
    for n in ui_nodes(xml):
        if n.get('enabled')=='false':continue
        value=(n.get('text','')+' '+n.get('content-desc','')).strip()
        if not value or not any(x in value for x in keywords):continue
        bounds=re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',n.get('bounds',''))
        if not bounds:continue
        a,b,c,d=map(int,bounds.groups())
        if c<=a or d<=b:continue
        if n.get('clickable')=='true':matches.insert(0,((a+c)//2,(b+d)//2,value))
        else:matches.append(((a+c)//2,(b+d)//2,value))
    if not matches:return None
    x,y,title=matches[0]
    run(['adb','shell','input','tap',str(x),str(y)])
    time.sleep(2.5)
    return {'xml':snapshot(label),'hit':title,'bounds':[x,y]}
def swipe(run,snapshot,label):
    run(['adb','shell','input','swipe','795','1330','795','430','390'])
    time.sleep(1.4)
    return snapshot(label)
def click_matching_historical_export(xml,expected,run,snapshot):
    """Never export an arbitrary task. Match stopped exact count in same row."""
    try:root=ET.fromstring(xml[xml.index('<?xml'):])
    except (ValueError,ET.ParseError):return None
    parents={c:p for p in root.iter() for c in p}
    candidates=[]
    for n in root.iter('node'):
        label=n.attrib.get('text','')+' '+n.attrib.get('content-desc','')
        if expected not in label or '已结束' not in label:continue
        anc=n
        for depth in range(1,8):
            anc=parents.get(anc)
            if anc is None:break
            buttons=[x for x in anc.iter('node') if x.attrib.get('text','')=='导出'
                     and x.attrib.get('clickable')=='true']
            if not buttons:continue
            for x in buttons:
                m=re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',x.attrib.get('bounds',''))
                if m:
                    a,b,c,d=map(int,m.groups())
                    if c>a and d>b:candidates.append(((a+c)//2,(b+d)//2,label,depth))
            if candidates:break
    if len(candidates)!=1:return {'error':'Matching export controls: '+str(len(candidates))}
    x,y,txt,depth=candidates[0]
    run(['adb','shell','input','tap',str(x),str(y)])
    time.sleep(5)
    return {'xml':snapshot('r108_exact_history_export_trigger'),
            'label':txt,'tap':[x,y],'hierarchy_depth':depth}
def pulled_history_zip(xml,run,snapshot,out):
    """Browser-side Downloads dialog and actual adb pull are separate gates."""
    if 'Choose where to download' in xml or 'text="Download"' in xml:
        x=touch(xml,['Download'],run,snapshot,'r108_historic_download_confirm')
        if x:xml=x['xml']
    for i in range(24):
        rc,msg=run(['adb','shell','ls','-1','/sdcard/Download'],timeout=20)
        files=[x.strip() for x in msg.splitlines() if '历史观察_' in x and x.strip().endswith('.zip')]
        if files:
            path='/sdcard/Download/'+files[-1]
            target='/tmp/r108-real-post-restart-historical.zip'
            rc,msg=run(['adb','pull',path,target],timeout=75)
            if rc==0 and Path(target).is_file():
                with zipfile.ZipFile(target) as z:
                    integrity=z.testzip();names=z.namelist()
                manifest={'original':files[-1],'bytes':Path(target).stat().st_size,
                          'sha256':h(Path(target).read_bytes()),
                          'members':len(names),'crc_error':integrity,'pulled':True}
                report_json(out/'r108_historical_real_download_manifest.json',manifest)
                return Path(target),manifest
        time.sleep(1.5)
    return None,{'error':'No actual history ZIP found after trigger and download confirmation'}
def evidence_gate(state,name,success,detail):
    state['gates'][name]={'status':'PASS' if success else 'FAIL','detail':detail}
    print(('PASS' if success else 'FAIL')+' '+name+': '+str(detail)[:330],flush=True)
    return success
def execute(formal_zip,run,snapshot,state,OUT,fixture_url,open_internal=None):
    result={'scope':'Kiwi Android 11 AVD, frozen MV2 V0.4.58, prior stopped task',
            'original_history_task_recovery':'NOT_VERIFIED','mid_capture_crash':'NOT_RUN',
            'original_zip_not_public':True,'gates':{},'debug':{}}
    try:
        pre=baseline(formal_zip)
        result['baseline']={'session':pre['session'],'requests':len(pre['requests']),
                            'bodies':len(pre['bodies']),'all_requests':pre['total_requests'],'sha256':pre['fullzip_sha'],
                            'entries':pre['entries'],'startedAt':pre['startedAt'],
                            'endedAt':pre['endedAt']}
        evidence_gate(result,'R108_01_pre_restart_frozen_baseline',
                      len(pre['requests'])>=36 and len(pre['bodies'])>=36 and bool(pre['endedAt']),
                      result['baseline'])
        old=getpid(run);result['debug']['pid_before']=old
        evidence_gate(result,'R108_02_browser_process_seen',bool(old),old)
        # Android official adb: force-stop does not clear IndexedDB/profile data.
        rc,out=run(['adb','shell','am','force-stop','com.kiwibrowser.browser'],timeout=35)
        time.sleep(3)
        killed=getpid(run);result['debug']['pid_after_force_stop']=killed
        evidence_gate(result,'R108_03_real_force_stop',rc==0 and not killed,
                      {'command':'am force-stop (no pm clear)','rc':rc,'before':old,'after':killed,'output':out[:150]})
        rc,msg=run(['adb','shell','monkey','-p','com.kiwibrowser.browser',
                    '-c','android.intent.category.LAUNCHER','1'],timeout=50)
        time.sleep(11)
        new=getpid(run);restart_ui=snapshot('r108_real_browser_cold_relaunch')
        result['debug']['pid_after_cold_launch']=new
        evidence_gate(result,'R108_04_new_browser_process',
                      bool(new) and not set(new).intersection(old),
                      {'before':old,'after':new,'rc':rc,'monkey':msg[:150]})
        # Navigate only controlled synthetic page; no user site/tokens.
        rc,msg=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
                    '-d',fixture_url,'com.kiwibrowser.browser'],timeout=45)
        time.sleep(9)
        xml=snapshot('r108_fixture_after_cold_restart')
        evidence_gate(result,'R108_05_reopened_real_kiwi_fixture',
                      'R104_NETWORK_FIXTURE_READY' in xml or '127.0.0.1' in xml,
                      {'intent_rc':rc,'uri':fixture_url,'ui_text_length':len(xml)})
        if not any(x in xml for x in ('网站数据工具','展开网站数据工具','网站数据观察与导出')):
            time.sleep(7);xml=snapshot('r108_wait_extension_after_cold_start')
        visible=any(x in xml for x in ('展开网站数据工具','网站数据观察与导出快捷入口','网站数据工具侧边栏'))
        evidence_gate(result,'R108_06_formal_extension_ui_still_installed',visible,
                      {'marker_present':visible})
        # R108 second route: navigate to the *existing* full-size formal
        # extension panel, not a test-only plugin or modified source.
        extension_id=None
        try:
            manager=(OUT/'extension_after_import.xml').read_text(encoding='utf-8')
            match=re.search(r'ID:\s*([a-p]{32})',manager)
            extension_id=match.group(1) if match else None
        except Exception as e:
            result['debug']['extension_id_source_error']=repr(e)
        result['debug']['formal_extension_id']=extension_id
        if extension_id and open_internal:
            xml=open_internal('chrome-extension://'+extension_id+'/panel.html',
                              'r108_original_full_screen_panel')
            evidence_gate(result,'R108_06b_original_full_panel_navigated',
                          '网站数据观察与导出' in xml or '展开高级工具' in xml,
                          {'extension_id':extension_id,'xml_bytes':len(xml)})
        else:
            if '展开网站数据工具' in xml or '网站数据观察与导出快捷入口' in xml:
                clicked=touch(xml,['展开网站数据工具','网站数据观察与导出快捷入口'],
                              run,snapshot,'r108_sidebar_open')
                if clicked:xml=clicked['xml']
            else:xml=snapshot('r108_sidebar_current')
        # Expand the real formal panel's existing advanced controls.
        expanded=None
        for i in range(5):
            expanded=touch(xml,['展开高级工具'],run,snapshot,'r108_advanced_'+str(i))
            if expanded:
                xml=expanded['xml'];break
            xml=swipe(run,snapshot,'r108_scroll_to_advanced_'+str(i))
        evidence_gate(result,'R108_07_advanced_ui_opened',bool(expanded),
                      {'clicked':expanded and expanded['hit']})
        # Normal fragment navigation inside the SAME formal extension page
        # should scroll the long advanced UI straight to its existing anchor.
        if expanded and extension_id and open_internal:
            xml=open_internal('chrome-extension://'+extension_id+'/panel.html#capture-history',
                              'r108_history_fragment_anchor')
            result['debug']['anchor_history_visible']=[
                {'text':n.get('text'),'bounds':n.get('bounds')}
                for n in ui_nodes(xml) if '历史观察记录与恢复' in n.get('text','')]
        # Existing panel contains <details>历史观察记录与恢复（高级）.
        opened=None
        for i in range(15):
            opened=touch(xml,['历史观察记录与恢复'],run,snapshot,'r108_history_open_'+str(i))
            if opened:
                xml=opened['xml'];break
            xml=swipe(run,snapshot,'r108_scroll_to_history_'+str(i))
        evidence_gate(result,'R108_08_history_details_ui_reached',bool(opened),
                      {'clicked':opened and opened['hit'],'last_xml_bytes':len(xml)})
        # The UI asynchronously asks background CAPTURE_TASK_LIST.
        time.sleep(4);xml=snapshot('r108_history_after_async_load')
        request_marker='请求 '+str(pre['total_requests'])
        history_visible=(('观察任务' in xml and ('已结束' in xml or '开始时间' in xml)) or
                         ('历史任务' in xml and '请求 ' in xml))
        result['debug']['history_text_samples']=[x for x in re.findall(r'text="([^"]+)"',xml)
              if '观察' in x or '请求' in x or '历史' in x][:50]
        evidence_gate(result,'R108_09_history_rows_accessible',history_visible,
                      {'matches':result['debug']['history_text_samples'][:18]})
        # Find the exact archived row by the baseline request count, not arbitrary new tasks.
        match_xml=xml
        for i in range(15):
            if request_marker in match_xml:break
            match_xml=swipe(run,snapshot,'r108_search_history_request_count_'+str(i))
        exact=(request_marker in match_xml)
        evidence_gate(result,'R108_10_original_history_count_visible',exact,
                      {'expected':request_marker,'found':exact})
        # A historical row's '导出' button is only actionable if the
        # exact original task has been independently identified in UI.
        # A wrong-task export is expressly forbidden.
        if exact:
            chosen=click_matching_historical_export(match_xml,request_marker,run,snapshot)
            result['debug']['history_export_control']=(
                {k:v for k,v in chosen.items() if k!='xml'} if chosen else None)
            clicked=bool(chosen and 'xml' in chosen)
            evidence_gate(result,'R108_11_exact_original_history_export_clicked',clicked,
                          result['debug']['history_export_control'])
            if clicked:
                historical,manifest=pulled_history_zip(chosen['xml'],run,snapshot,OUT)
                evidence_gate(result,'R108_12_real_history_zip_download_adb_pull',
                              historical is not None and manifest.get('crc_error') is None,manifest)
                if historical:
                    from r108_offline_recovery_parity import verify as compare_history
                    detailed=compare_history(formal_zip,historical,
                            OUT/'r108_formal_original_before_after_parity.json')
                    for k,v in detailed['gates'].items():
                        evidence_gate(result,k,v['status']=='PASS',v['details'])
                    result['original_history_task_recovery']=(
                        'PASS' if detailed['summary']['failed']==0 else 'FAIL')
        result['debug']['final_xml']='r108_search_history_request_count_*.xml'
    except Exception as e:
        result['exception']=repr(e)
        evidence_gate(result,'R108_99_unhandled_test_error',False,repr(e))
    finally:
        report_json(OUT/'r108_restart_history_status.json',result)
        for k,v in result['gates'].items():
            state['gates'][k]={'status':v['status'],'detail':str(v['detail'])[:1700]}
        print('R108_RESTART_HISTORY_RESULTS',json.dumps({k:v['status'] for k,v in result['gates'].items()}),flush=True)
    return result
