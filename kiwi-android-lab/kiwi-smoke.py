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
    rc,txt=run(['adb','push',str(ext),'/sdcard/Download/Kiwi_R101_Canary_MV2.zip'])
    log_gate('A5a_canary_staged',rc==0,txt)
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
                chosen=tap_target(xml,['Kiwi_R101_Canary_MV2.zip','Kiwi R101 Canary'],'file_pick_direct')
                if not chosen:
                    child=tap_target(xml,['Downloads','下载','Internal storage','内部存储'],'file_downloads')
                    if child:xml=child
                    chosen=tap_target(xml,['Kiwi_R101_Canary_MV2.zip','Kiwi R101 Canary'],'file_pick_after_downloads')
                if chosen:
                    xml=chosen
                    consent=tap_target(xml,['Add extension','Install extension','Add','安装扩展','添加扩展'],'extension_confirm')
                    if consent:xml=consent
                    time.sleep(6)
                    xml=snapshot('extension_after_import')
                else:
                    state['errors'].append('DocumentsUI file picker did not expose the staged Canary in current listing; see screenshot and XML')
    imported='Kiwi R101 Probe' in xml
    log_gate('A5b_canary_install_verified',imported,'name visible in extension management UI='+str(imported))
    # Use real website to check browser networking separately from extension gate.
    rc,txt=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
                '-d','https://example.com/',PKG])
    time.sleep(10);xml=snapshot('example_com')
    online=('example.com' in xml and 'Connection is secure' in xml)
    log_gate('A6_https_real_page',online,'Kiwi URL bar example.com with secure icon='+str(online)+' '+txt[:180]+'; screenshot saved')
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
