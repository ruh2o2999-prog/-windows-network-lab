#!/usr/bin/env python3
"""R101: install and probe the *real* Kiwi Android APK, preserving failed gates."""
import json, os, re, subprocess, time, zipfile, hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

OUT=Path('out'); OUT.mkdir(exist_ok=True)
PKG='com.kiwibrowser.browser'
state={'test':'Kiwi Android R101','source':'official Kiwi GitHub release 14310011181',
       'environment':'Android x86_64 AVD via reactivecircus/android-emulator-runner',
       'gates':{},'errors':[],'note':'R99 production extension not installed; independent canary only'}

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
    try: root=ET.fromstring(xml[xml.find('<?xml'):] if '<?xml' in xml else xml)
    except Exception:return None
    for n in root.iter('node'):
        val=(n.attrib.get('text','')+' '+n.attrib.get('content-desc','')).lower()
        if any(k.lower() in val for k in keys):
            m=re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',n.attrib.get('bounds',''))
            if m:
                a,b,c,d=map(int,m.groups());return ((a+c)//2,(b+d)//2,val.strip())
    return None

def tap_target(xml,keys,label):
    target=clickable(xml,keys)
    if not target:return None
    x,y,txt=target;run(['adb','shell','input','tap',str(x),str(y)]);time.sleep(2)
    print('TAP '+label+': '+txt[:130],flush=True)
    return snapshot(label)

def type_internal_url(url,label):
    """Navigate browser internal URL via its own omnibox; Android VIEW cannot resolve chrome://."""
    xml=snapshot('before_omni_'+label)
    target=clickable(xml,['Search or type web address','Search or type URL','Search or type','Address bar','搜索或输入网址','地址栏'])
    if target:
        x,y,_=target
    else:
        x,y=540,115  # 1080px Android AVD: fallback, with screenshot evidence
    rc,msg=run(['adb','shell','input','tap',str(x),str(y)])
    time.sleep(1)
    run(['adb','shell','input','text',url])
    run(['adb','shell','input','keyevent','66'])
    time.sleep(8)
    print('OMNIBOX_NAV '+label+' '+url+' '+str((x,y)),flush=True)
    return snapshot('omni_'+label)

def canary():
    path=OUT/'Kiwi_R101_Canary_MV2.zip'
    manifest={'manifest_version':2,'name':'Kiwi R101 Probe','version':'0.0.1',
              'description':'Authorized local emulator environment probe only',
              'permissions':['storage'],'content_scripts':[{'matches':['https://example.com/*'],
              'js':['probe.js'],'run_at':'document_idle'}]}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        z.writestr('probe.js',"console.log('Kiwi R101 Probe loaded');")
    state['canary_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    return path

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
    # Dismiss optional first-run screens based on *actual* accessible node labels.
    for i in range(3):
        node=clickable(xml,['accept','agree','continue','get started','start browsing','同意','继续','开始使用'])
        if not node:break
        xml=tap_target(xml,[node[2]],'onboarding_'+str(i)) or xml
    rc,txt=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
                '-d','kiwi://extensions/',PKG])
    time.sleep(8)
    xml=snapshot('extensions_initial')
    reachable=('Extensions' in xml or 'extension' in xml.lower() or '扩展' in xml)
    log_gate('A4_extension_manager_reachable',reachable,'am-start='+txt[:300]+' html/ui markers='+str(reachable))
    if not reachable:
        rc,txt=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
                    '-d','chrome://extensions/',PKG])
        time.sleep(7);xml=snapshot('extensions_fallback')
        reachable=('Extensions' in xml or 'extension' in xml.lower() or '扩展' in xml)
        log_gate('A4b_chrome_extensions_fallback',reachable,txt[:300])
        if not reachable:
            xml=type_internal_url('chrome://extensions/','internal_extensions')
            reachable=('Extensions' in xml or 'extension' in xml.lower() or '扩展' in xml)
            log_gate('A4c_omnibox_extension_manager',reachable,'browser-internal chrome://extensions omnibox navigation')
    ext=canary()
    rc,txt=run(['adb','push',str(ext),'/sdcard/Download/Kiwi_R101_Canary_MV2.zip'])
    log_gate('A5a_canary_staged',rc==0,txt)
    if reachable:
        next_xml=tap_target(xml,['Developer mode','开发者模式'],'developer_mode')
        if next_xml:xml=next_xml
        next_xml=tap_target(xml,['from .zip','Load','加载','安装扩展'],'install_selector')
        if next_xml:
            xml=next_xml
            file_ui=tap_target(xml,['Downloads','下载'],'file_downloads')
            if file_ui:xml=file_ui
            picked=tap_target(xml,['Kiwi_R101_Canary_MV2.zip','Kiwi_R101_Canary'],'file_pick')
            if picked:xml=picked
            time.sleep(5);xml=snapshot('extension_after_import')
    imported='Kiwi R101 Probe' in xml
    log_gate('A5b_canary_install_verified',imported,'name visible in extension management UI='+str(imported))
    # Use real website to check browser networking separately from extension gate.
    rc,txt=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
                '-d','https://example.com/',PKG])
    time.sleep(10);xml=snapshot('example_com')
    online=('Example Domain' in xml)
    log_gate('A6_https_real_page',online,'Example Domain UI visible='+str(online)+' '+txt[:180])
    state['gates']['A7_R99_production_extension']={'status':'NOT_RUN',
        'detail':'private 370KB R99 MV2 ZIP is not included in this external runner; it is not the canary'}

if __name__=='__main__':
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
