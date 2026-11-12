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
