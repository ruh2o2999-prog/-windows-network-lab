#!/usr/bin/env python3
"""R109 route switch: enter unchanged MV2 panel through Kiwi Extensions > Details > Extension options.

After >3 UI/omnibox failures, do not treat direct chrome-extension URL as
primary. Verify the actual installed id and unchanged, real panel UI.
"""
import re,time
from r108_restart_history import touch,ui_nodes
PKG='com.kiwibrowser.browser'
def page_ok(xml):
    return ('网站数据观察与导出' in xml and '开始观察' in xml
            and ('展开高级工具' in xml or '收起高级工具' in xml))
def installed_extension(xml,extension_id):
    if not extension_id or not re.fullmatch(r'[a-p]{32}',extension_id):return False
    return ('ID: '+extension_id in xml
            and '网站数据观察与导出' in xml and 'Details' in xml)
def target_safe(xml,terms):
    result=[]
    for n in ui_nodes(xml):
        text=(n.get('text','')+' '+n.get('content-desc','')).strip()
        if any(t in text for t in terms):
            m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',n.get('bounds',''))
            if not m:continue
            x1,y1,x2,y2=map(int,m.groups())
            if x2>x1 and y2>y1 and y2>100 and x1<1080:
                result.append((text,[x1,y1,x2,y2]))
    return result
def open_original_panel(run,snapshot,type_internal_url,extension_id,fixture_url):
    evidence={'route':'Kiwi Extensions manager > Details > Extension options (original manifest options_page)',
              'form':'unchanged MV2 extension','attempts':[]}
    def rec(stage,xml):
        evidence['attempts'].append({'stage':stage,'ui_bytes':len(xml),
             'panel_verified':page_ok(xml),
             'safe_options_nodes':target_safe(xml,['Extension options','扩展选项','Options'])[:8]})
    # Exact prior R108 Android successful precondition, not the unreliable
    # post-force-stop direct extension URL used by R109.
    rc,msg=run(['adb','shell','am','start','-a','android.intent.action.VIEW',
         '-d',fixture_url,PKG],timeout=45)
    time.sleep(8)
    fixture_xml=snapshot('r109_restore_controlled_fixture_after_restart')
    evidence['fixture']={'android_intent_rc':rc,
        'reopened_controlled_fixture':('127.0.0.1' in fixture_xml or 'R104_NETWORK_FIXTURE_READY' in fixture_xml),
        'response':msg[:220]}
    if rc!=0 or not evidence['fixture']['reopened_controlled_fixture']:
        return fixture_xml,evidence
    manager=type_internal_url('kiwi://extensions/','r109_original_extensions_manager_after_restart')
    rec('manager_after_cold_start',manager)
    evidence['matched_installed_id']=installed_extension(manager,extension_id)
    if not evidence['matched_installed_id']:
        return manager,evidence
    detail=touch(manager,['Details'],run,snapshot,'r109_original_extension_details')
    if not detail:
        evidence['details_button']='not clickable';return manager,evidence
    xml=detail['xml'];rec('original_extension_details',xml)
    evidence['details_button']=detail['hit']
    for step in range(18):
        if any(s in xml for s in ('Extension options','扩展选项','扩展程序选项')):
            option=touch(xml,['Extension options','扩展选项','扩展程序选项'],run,snapshot,
                         'r109_original_options_click_'+str(step))
            if option:
                xml=option['xml'];rec('clicked_original_options',xml)
                if page_ok(xml):
                    evidence['selected_route']='original_options_ui'
                    return xml,evidence
        # Desktop options page control may be below visible viewport;
        # scroll the original Kiwi details page and retain screenshots.
        x=960
        run(['adb','shell','input','swipe',str(x),'1450',str(x),'410','440'],timeout=15)
        time.sleep(0.9)
        xml=snapshot('r109_original_detail_scroll_'+str(step))
        rec('details_scrolled_'+str(step),xml)
    # Strong fallback: after proven original installed and the fixture primed,
    # use R108 proven exact original panel path once. Never call this a
    # successful manager route if the panel fails to open.
    url='chrome-extension://'+extension_id+'/panel.html'
    xml=type_internal_url(url,'r109_original_panel_after_manager_prime')
    rec('fallback_original_panel_after_manager_prime',xml)
    if page_ok(xml):
        evidence['selected_route']='R108_fixture_primed_original_panel'
        return xml,evidence
    return xml,evidence
