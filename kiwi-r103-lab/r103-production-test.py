#!/usr/bin/env python3
"""R103: install actual production MV2 ZIP on real Kiwi Android; preserve each gate and failure."""
import json, os, re, subprocess, time, zipfile, hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

OUT=Path('out'); OUT.mkdir(exist_ok=True)
PKG='com.kiwibrowser.browser'
state={'test':'Kiwi Android R103 production MV2','source':'official Kiwi GitHub release 14310011181',
       'environment':'Android x86_64 AVD via reactivecircus/android-emulator-runner',
       'gates':{},'errors':[],'note':'This is the exact R100 formal MV2 ZIP, not Canary; never report full A7 without all gates'}

def run(args,timeout=95):
    try:
        p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
        return p.returncode,(p.stdout or '')+'\n'+(p.stderr or '')
    except Exception as e:
        return -1,repr(e)

def log_gate(name,ok,detail):
    state['gates'][name]={'status':'PASS' if ok else 'FAIL','detail':str(detail)[:1700]}
    print(('PASS' if ok else 'FAIL')+' '+name+': '+str(detail)[:220],flush=True)
    return ok

def snapshot(label):
    run(['adb','shell','uiautomator','dump','/sdcard/window.xml'],timeout=35)
    _,xml=run(['adb','shell','cat','/sdcard/window.xml'],timeout=20)
    (OUT/(label+'.xml')).write_text(xml,encoding='utf-8')
    with (OUT/(label+'.png')).open('wb') as f:
        try: subprocess.run(['adb','exec-out','screencap','-p'],stdout=f,stderr=subprocess.DEVNULL,timeout=25)
        except Exception as e: state['errors'].append('screenshot:'+repr(e))
    return xml

def clickable(xml,keys):
    """Locate only a genuinely clickable visible widget (not matching passive disclaimer text)."""
    try: root=ET.fromstring(xml[xml.find('<?xml'):] if '<?xml' in xml else xml)
    except Exception:return None
    exact=[]; partial=[]
    for n in root.iter('node'):
        attr=n.attrib
        if attr.get('clickable')!='true' or attr.get('enabled')=='false': continue
        val=(attr.get('text','')+' '+attr.get('content-desc','')).strip().lower()
        if not val:continue
        if not any(k.lower() in val for k in keys):continue
        m=re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',attr.get('bounds',''))
        if not m:continue
        a,b,c,d=map(int,m.groups());hit=((a+c)//2,(b+d)//2,val)
        (exact if any(val==k.lower() for k in keys) else partial).append(hit)
    return (exact or partial or [None])[0]

def tap_target(xml,keys,label):
    target=clickable(xml,keys)
    if not target:return None
    x,y,txt=target;run(['adb','shell','input','tap',str(x),str(y)]);time.sleep(2)
    print('TAP '+label+': '+txt[:130],flush=True)
    return snapshot(label)

def tap_text_any(xml,keys,label):
    """Use exact on-screen text of a menu row even when only its parent is clickable."""
    try:r=ET.fromstring(xml[xml.find('<?xml'):] if '<?xml' in xml else xml)
    except Exception:return None
    choices=[]
    for n in r.iter('node'):
        a=n.attrib;title=a.get('text','').strip();desc=a.get('content-desc','').strip()
        value=title or desc
        if a.get('enabled')=='false':continue
        if not any(title.lower()==k.lower() or desc.lower()==k.lower() for k in keys):continue
        m=re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',a.get('bounds',''))
        if m:
            x1,y1,x2,y2=map(int,m.groups());choices.append(((x1+x2)//2,(y1+y2)//2,value))
    if not choices:return None
    x,y,val=choices[0]
    rc,msg=run(['adb','shell','input','tap',str(x),str(y)])
    time.sleep(4)
    print('MENU_TAP '+label+' '+val,flush=True)
    return snapshot(label)

def is_extension_manager_page(xml):
    """A menu label alone is not proof of navigation; require manager-specific content."""
    low=xml.lower()
    # Kiwi overflow lists both New Incognito tab and Recent tabs, unlike the manager.
    if 'new incognito tab' in low and 'recent tabs' in low:return False
    return 'extensions' in low and any(marker in low for marker in [
        'developer mode','load from', 'install extension', 'extensions installed',
        'chrome://extensions', 'extensions from', 'extension id', 'extension management'])

def find_extensions_via_kiwi_menu(xml):
    menu=tap_target(xml,['More options','更多选项'],'kiwi_overflow_menu')
    if not menu:return None,False
    chosen=tap_text_any(menu,['Extensions','扩展程序','Extensions & Themes','扩展'],'extensions_via_native_menu')
    return (chosen,True) if chosen else (menu,False)

def type_internal_url(url,label):
    """Open internal pages inside Kiwi, never Android implicit VIEW for chrome://."""
    xml=snapshot('before_omni_'+label)
    if PKG not in xml:
        run(['adb','shell','monkey','-p',PKG,'-c','android.intent.category.LAUNCHER','1'])
        time.sleep(3)
        xml=snapshot('kiwi_refocused_'+label)
    if PKG not in xml:
        print('OMNIBOX_ABORT: Kiwi not foreground',flush=True)
        return xml
    target=clickable(xml,['Search or type web address','Search or type URL','Search or type',
                           'Address bar','搜索或输入网址','地址栏'])
    if target:
        x,y,_=target
    else:
        # Fallback Android x64 AVD screenshot evidence, no blind taps outside Kiwi.
        x,y=540,115
    run(['adb','shell','input','tap',str(x),str(y)])
    time.sleep(1)
    run(['adb','shell','input','text',url])
    run(['adb','shell','input','keyevent','66'])
    time.sleep(8)
    print('OMNIBOX_NAV '+label+' '+url+' '+str((x,y)),flush=True)
    return snapshot('omni_'+label)

def picker_diagnostic(xml):
    """R102: preserve actual DocumentsUI tap result and foreground evidence."""
    def is_picker(v):
        return 'com.google.android.documentsui' in v or 'com.android.documentsui' in v
    if not is_picker(xml):return xml
    bounds=None
    try:
        tree=ET.fromstring(xml[xml.index('<?xml'):])
        for n in tree.iter('node'):
            if n.attrib.get('text')=='Kiwi_R103_Production_MV2.zip':
                bounds=n.attrib.get('bounds');break
    except (ValueError,ET.ParseError):pass
    log_gate('A5c_documentsui_file_visible',bool(bounds),str(bounds))
    if not bounds:return xml
    x1,y1,x2,y2=map(int,re.findall(r'\d+',bounds))
    hits=[
        ('title_center',((x1+x2)//2,(y1+y2)//2)),
        ('row_left_icon',(max(75,x1-90),(y1+y2)//2)),
        ('row_right_body',(max(x2-80,x1+35),(y1+y2)//2)),
    ]
    progress=[]
    for label,(x,y) in hits:
        rc,out=run(['adb','shell','input','tap',str(x),str(y)])
        time.sleep(2.5)
        xml=snapshot('r102_picker_'+label)
        _,activities=run(['adb','shell','dumpsys','activity','activities'],timeout=35)
        now_picker=is_picker(xml)
        progress.append({'method':label,'x':x,'y':y,'adb_rc':rc,
                         'documentsui_foreground':now_picker,
                         'kiwi_visible':PKG in xml,
                         'activity_tail':activities[-700:]})
        print('R102_PICKER_STEP',json.dumps(progress[-1]),flush=True)
        if not now_picker:break
    if is_picker(xml):
        # Try Android keyboard focus route without inventing a file-selection result.
        for key in [20,23,66]:
            rc,_=run(['adb','shell','input','keyevent',str(key)])
            time.sleep(1.5)
            xml=snapshot('r102_picker_key_'+str(key))
            step={'method':'key_'+str(key),'adb_rc':rc,
                  'documentsui_foreground':is_picker(xml),'kiwi_visible':PKG in xml}
            progress.append(step)
            print('R102_PICKER_STEP',json.dumps(step),flush=True)
            if not is_picker(xml):break
    state['r102_picker_trace']=progress
    log_gate('A5d_documentsui_returned_to_kiwi',not is_picker(xml),
             'Document selector result: '+json.dumps(progress[-2:],ensure_ascii=False)[:900])
    return xml

def canary():
    """Read one-time decrypted formal extension; never write it to public out/ artifacts."""
    source=Path(os.environ.get('R103_PRODUCTION_ZIP','/tmp/kiwi-r103-production.zip'))
    if not source.is_file():raise FileNotFoundError('Formal MV2 binary not supplied to ephemeral runner')
    with zipfile.ZipFile(source) as z:
        if z.testzip() is not None:raise RuntimeError('Formal MV2 ZIP CRC failure')
        manifest=json.loads(z.read('manifest.json'))
    if manifest.get('manifest_version')!=2 or manifest.get('version')!='0.4.58':
        raise RuntimeError('Wrong formal extension: version or MV2 mismatch')
    state['formal_package_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    state['formal_extension_name']=manifest['name']
    state['formal_extension_version']=manifest['version']
    state['formal_package_bytes']=source.stat().st_size
    # Sanitize public status artifact: no extension JS/HTML is ever included.
    return source

def main():
    rc,txt=run(['adb','shell','getprop','sys.boot_completed'])
    log_gate('A0_android_boot',rc==0 and txt.strip()=='1',txt)
    gms_rc,gms_text=run(['adb','shell','pm','path','com.google.android.gms'])
    log_gate('A0b_google_play_services',gms_rc==0 and 'package:' in gms_text,gms_text)
    apk=Path('kiwi-official-x64.apk')
    if not apk.is_file():
        log_gate('A1_official_apk_present',False,'official APK not downloaded')
        return
    log_gate('A1_official_apk_present',apk.stat().st_size>15_000_000,'bytes='+str(apk.stat().st_size))
    rc,txt=run(['adb','install','-r',str(apk)],timeout=180)
    installed=rc==0 and 'Success' in txt
    log_gate('A2_install_official_kiwi',installed,txt)
    if not installed:return
    _,pkg=run(['adb','shell','pm','list','packages',PKG])
    log_gate('A2b_package_registered',PKG in pkg,pkg)
    rc,txt=run(['adb','shell','monkey','-p',PKG,'-c','android.intent.category.LAUNCHER','1'])
    time.sleep(10)
    xml=snapshot('kiwi_launch')
    _,activity=run(['adb','shell','dumpsys','activity','activities'],timeout=35)
    blocker='won\'t run without Google Play services' in xml or 'Google Play services' in xml
    launch_ok=PKG in activity and 'Events injected: 1' in txt and not blocker
    log_gate('A3_kiwi_running',launch_ok,txt[:350]+' active='+str(PKG in activity)+' blocking_play_services_dialog='+str(blocker))
    if blocker:
        state['errors'].append('Official Kiwi blocked by Google Play Services dialog; test must switch system-image target')
        return
    # Complete actual Kiwi onboarding, only clicking widgets marked clickable=true in UI XML.
    for i in range(8):
        node=clickable(xml,['skip','no thanks','not now','continue','next','get started',
                            'start browsing','accept','agree','done','got it',
                            '跳过','不用了','以后再说','继续','开始使用','接受','完成'])
        if not node:break
        x,y,txt2=node
        rc,detail=run(['adb','shell','input','tap',str(x),str(y)])
        print('ONBOARDING_TAP',i,repr(txt2[:90]),'at',x,y,'rc',rc,flush=True)
        time.sleep(3)
        xml=snapshot('onboarding_'+str(i))
    usable=PKG in xml and 'Welcome to Kiwi Browser' not in xml and            'won\'t run without Google Play services' not in xml
    log_gate('A3b_onboarding_complete',usable,'Kiwi foreground and no onboarding blocker='+str(usable))
    if not usable:return
    # Enter Kiwi's own Extensions screen using its native menu, then acknowledge
    # the one-time extension-security interstitial seen in the authentic AVD screenshot.
    via_menu,menu_clicked=find_extensions_via_kiwi_menu(xml)
    log_gate('A4a_native_kiwi_extensions_entry_clicked',bool(menu_clicked),
             'Kiwi native Extensions menu row clicked='+str(menu_clicked))
    interstitial=bool(via_menu and 'text="kiwi://extensions"' in via_menu)
    log_gate('A4b_kiwi_extensions_internal_url',interstitial,
             'Native menu navigated browser URL bar to kiwi://extensions')
    reachable=False
    if interstitial:
        # R101 fifth-run screenshot at 1080x1920: native OK button spans
        # x=451..631, y=1636..1735. This is the warning acknowledgement,
        # NOT an extension installation or a permission grant for any website.
        run(['adb','shell','input','tap','540','1683'])
        time.sleep(7)
        xml=snapshot('extensions_after_warning_ack')
        state['gates']['A4c_manager_visual_verification']={
            'status':'PENDING_VISUAL',
            'detail':'Security warning acknowledged; inspect captured PNG for real manager widgets before declaring A4 PASS'}
        reachable=True
    else:
        xml=snapshot('extensions_internal_route_failed')
        log_gate('A4_extension_manager_reachable',False,'native Kiwi extensions route not reached')
    ext=canary()
    rc,txt=run(['adb','push',str(ext),'/sdcard/Download/Kiwi_R103_Production_MV2.zip'])
    log_gate('A7a_formal_binary_staged',rc==0,txt)
    if reachable:
        # Actual R101 sixth-run screenshot: Developer mode already ON.
        # Never toggle it off; select the existing import-zip button.
        has_install=clickable(xml,['from .zip','.crx','.user.js']) is not None
        log_gate('A4d_real_manager_install_button_clickable',has_install,
                 'Kiwi HTML accessibility exposes + (from .zip/.crx/.user.js), clickable=true')
        if has_install:
            picker=tap_target(xml,['from .zip','.crx','.user.js'],'extension_file_picker')
            if picker:
                xml=picker
                # Android DocumentsUI defaults to Recent, which does not index
                # sideloaded .zip files. Navigate the actual storage root.
                roots=tap_target(xml,['Show roots'],'file_picker_roots')
                if roots:
                    xml=roots
                    dl=tap_target(xml,['Downloads','下载'],'file_picker_downloads')
                    if not dl:
                        dl=tap_text_any(xml,['Downloads','下载'],'file_picker_downloads_row')
                    if dl:xml=dl
                # DocumentUI results are checked against the real picker activity.
                list_view=tap_target(xml,['List view'],'file_picker_list_view')
                if list_view:xml=list_view
                xml=picker_diagnostic(xml)
                if 'com.google.android.documentsui' not in xml:
                    consent=tap_target(xml,['Add extension','Install extension','Add','安装扩展','添加扩展'],'extension_confirm')
                    if consent:xml=consent
                    time.sleep(6)
                    xml=snapshot('extension_after_import')
                else:
                    snapshot('extension_after_import')
                    state['errors'].append('R102: DocumentsUI still foreground; no file result delivered to Kiwi; see per-tap evidence')
    formal_name=state.get('formal_extension_name','')
    imported=bool(formal_name and formal_name in xml and ('Details' in xml or 'Remove' in xml))
    log_gate('A7b_formal_extension_installed',imported,
             'Formal extension named '+formal_name+' visible in Kiwi manager with Details/Remove='+str(imported))
    snapshot('r103_formal_manager_final')
    # Use real website to check browser networking separately from extension gate.
    rc,txt=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
                '-d','https://example.com/',PKG])
    time.sleep(10);xml=snapshot('example_com')
    online=('example.com' in xml and 'Connection is secure' in xml)
    log_gate('A6_https_real_page',online,'Kiwi URL bar example.com with secure icon='+str(online)+' '+txt[:180]+'; screenshot saved')
    time.sleep(3)
    xml=snapshot('r102_canary_live_content_script')
    marker='R102_KIWI_CONTENT_SCRIPT_ACTIVE'
    # Formal plugin owns a closed shadow DOM sidebar; do not substitute canary marker.
    sidebar_hint=('展开网站数据工具' in xml or '网站数据观察与导出快捷入口' in xml or
                  '网站数据工具侧边栏' in xml or '展开网站数据' in xml)
    log_gate('A7c_formal_sidebar_in_real_webpage',sidebar_hint,
             'Kiwi on example.com exposes actual formal sidebar accessibility label='+str(sidebar_hint))
    if sidebar_hint:
        opened=tap_target(xml,['展开网站数据工具','网站数据观察与导出快捷入口'],'r103_sidebar_open')
        if not opened:
            opened=tap_text_any(xml,['数据'],'r103_sidebar_open_text')
        if opened:
            xml=opened
            has_panel=any(k in xml for k in ['网站数据工具侧边栏','开始观察','导出','当前网页'])
            log_gate('A7d_formal_sidebar_opened',has_panel,'Kiwi actually rendered sidebar or panel: '+str(has_panel))
            # Attempt only actual exposed buttons, and retain UI XML after each action.
            begin=tap_target(xml,['开始观察','开始记录','开始采集'],'r103_start_observe')
            if begin:
                xml=begin
                time.sleep(3)
                stopped=tap_target(xml,['结束观察','停止观察','结束记录'],'r103_stop_observe')
                if stopped:xml=stopped
                exported=tap_target(xml,['导出','导出zip','导出压缩包'],'r103_export_zip')
                if exported:xml=exported
                log_gate('A7e_observe_export_ui_interaction',bool(stopped and exported),
                         'Actual start, stop, export button actions submitted; must check ZIP contents independently')
            else:
                state['gates']['A7e_observe_export_ui_interaction']={'status':'NOT_RUN','detail':'No accessible start-observe control in Kiwi UI; inspect r103_sidebar_open XML'}
        else:
            log_gate('A7d_formal_sidebar_opened',False,'Could not operate production sidebar edge')
    else:
        state['gates']['A7d_formal_sidebar_opened']={'status':'NOT_RUN','detail':'sidebar content script not observed in real Android page'}
    # Android Kiwi asks "Choose where to download" on the first export.
    # Do not confuse the dialog with completed filesystem persistence.
    confirm=None
    if 'Choose where to download' in xml or 'text="Download"' in xml:
        confirm=tap_target(xml,['Download'],'r103_download_confirm')
        if confirm:xml=confirm
    rc,dl=run(['adb','shell','ls','-la','/sdcard/Download'])
    (OUT/'r103_download_directory.txt').write_text(dl,encoding='utf-8')
    downloaded=False; zip_ok=False; zip_metadata={}; rawfile=None
    if confirm:
        for attempt in range(15):
            rc,names=run(['adb','shell','ls','-1','/sdcard/Download'])
            candidates=[x.strip() for x in names.splitlines() if x.strip().lower().endswith('.zip') and
                        x.strip()!='Kiwi_R103_Production_MV2.zip']
            if candidates:
                original=candidates[0]; target='/tmp/r103-export-recovered.zip'
                prc,pout=run(['adb','pull','/sdcard/Download/'+original,target],timeout=50)
                if prc==0 and Path(target).is_file():
                    downloaded=True
                    try:
                        with zipfile.ZipFile(target) as z:
                            bad=z.testzip();members=z.namelist()
                            has_requests=any(x.lower().endswith('requests.json') for x in members)
                            has_har=any(x.lower().endswith('.har') for x in members)
                            has_trace=any(x.lower().endswith('trace.json') for x in members)
                            zip_ok=bad is None and len(members)>=5 and has_requests and has_har and has_trace
                            zip_metadata={'filename':original,'bytes':Path(target).stat().st_size,
                                'sha256':hashlib.sha256(Path(target).read_bytes()).hexdigest(),
                                'entries':len(members),'crc_error':bad,'has_requests_json':has_requests,
                                'has_har':has_har,'has_trace_json':has_trace,
                                'members':members[:150], 'download_pull':pout[:160]}
                    except Exception as e:
                        zip_metadata={'error':repr(e)}
                    break
            time.sleep(2)
    (OUT/'r103_export_zip_manifest.json').write_text(json.dumps(zip_metadata,ensure_ascii=False,indent=2))
    log_gate('A7f_export_zip_content_verified',bool(downloaded and zip_ok),
             'Kiwi Download confirmation, real Android adb pull, CRC+requests/HAR/Trace='+
             json.dumps(zip_metadata,ensure_ascii=False)[:900])
    state['gates']['A7g_mse_opfs_video_parity']={'status':'NOT_RUN','detail':'R94-04 and media parity require independent Android samples and evidence; remain open'}

if __name__=='__main__':
    # Export exact Python test harness into the run's evidence artifact.
    (OUT/'r103_ci_test_harness.py').write_bytes(Path(__file__).read_bytes())
    try:main()
    except Exception as e:
        state['errors'].append(repr(e));print('EXCEPTION',repr(e),flush=True)
    finally:
        try:
            _,txt=run(['adb','logcat','-d','-v','time'],timeout=45)
            (OUT/'adb_logcat_tail.txt').write_text(txt[-400000:],encoding='utf-8')
        except Exception as e: state['errors'].append('logcat:'+repr(e))
        (OUT/'status.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        failed=[k for k,v in state['gates'].items() if v['status']=='FAIL']
        print('R101_RESULTS',json.dumps({k:v['status'] for k,v in state['gates'].items()}),flush=True)
        raise SystemExit(1 if failed or state['errors'] else 0)
