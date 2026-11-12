#!/usr/bin/env python3
"""R109 V8.10.1: real manager-vs-error-page route assertions.
Static tests do NOT prove actual Android historical ZIP success.
"""
import sys,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:import r108_restart_history
except ModuleNotFoundError:
    shim=types.ModuleType("r108_restart_history")
    shim.touch=lambda *_a,**_k:None
    shim.ui_nodes=lambda *_a,**_k:[]
    sys.modules["r108_restart_history"]=shim
from r109_panel_entry_v8101 import installed_extension,page_ok,target_safe
real_id="ooebifnejfkfdbiigafmkimbohlbnloo"
real_manager='''<?xml version="1.0"?><hierarchy><node text="Extensions"
><node text="网站数据观察与导出" bounds="[300,715][660,780]"/>
<node text="ID: ooebifnejfkfdbiigafmkimbohlbnloo" bounds="[346,945][924,1000]"/>
<node text="Details" clickable="true" bounds="[128,1113][325,1199]"/>
</node></hierarchy>'''
assert installed_extension(real_manager,real_id)
assert not installed_extension(real_manager,'a'*32)
assert not installed_extension(real_manager,'invalid-id')
fail_page='Your file couldn’t be accessed ERR_FILE_NOT_FOUND kiwi-extension://'+real_id
assert not page_ok(fail_page)
assert not page_ok(real_manager)
valid_page='''<?xml version="1.0"?><hierarchy><node text="网站数据观察与导出"/>
<node text="开始观察"/><node text="展开高级工具"/></hierarchy>'''
assert page_ok(valid_page)
assert target_safe(real_manager,['Details'])
assert not target_safe('<hierarchy><node text="Extension options" bounds="[0,0][0,0]"/></hierarchy>',['Extension options'])
print("R109_V8101_REAL_MANAGER_AND_ERROR_PAGE_REGRESSIONS PASS=7 SCOPE=STATIC_ONLY")

# Reproduce the real Run43223192968 confusion: the omnibox treated
# kiwi://extensions/ as a Google search; the chosen route MUST not type it.
import r109_panel_entry_v8101 as panel_module
original_sleep=panel_module.time.sleep
original_touch=panel_module.touch
try:
    panel_module.time.sleep=lambda _:None
    details='''<?xml version="1.0"?><hierarchy><node text="Extension options"
    clickable="true" bounds="[320,580][750,650]"/></hierarchy>'''
    panel_module.touch=lambda xml,keys,run,snapshot,label: {
        'xml':details if 'Details' in keys else valid_page,
        'hit':'Details' if 'Details' in keys else 'Extension options'}
    calls=[]
    def native_menu(xml):
        calls.append('kiwi_native_overflow')
        return real_manager,True
    def block_omnibox(url,label):
        raise AssertionError('NO OMNIBOX INTERNAL SEARCH SHOULD OCCUR: '+url)
    actual, evidence=panel_module.open_original_panel(
        lambda args,timeout=30:(0,'ok'),lambda label:'127.0.0.1:18764 R104_NETWORK_FIXTURE_READY',
        block_omnibox,real_id,'http://127.0.0.1:18764/',native_menu)
    assert page_ok(actual) and evidence['native_menu_navigated']
    assert evidence['selected_route']=='original_options_ui' and calls==['kiwi_native_overflow']
finally:
    panel_module.time.sleep=original_sleep
    panel_module.touch=original_touch
print('R109_NATIVE_KIWI_MENU_NOT_GOOGLE_SEARCH_REGRESSION=PASS STATIC_ONLY')
