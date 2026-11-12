#!/usr/bin/env python3
"""R109 fail-closed UI replay: actual R108 offscreen XML + synthetic on-screen tree.
No Android product PASS is claimed here.
"""
import json,sys,zipfile,io,hashlib,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    import r108_restart_history
except ModuleNotFoundError:
    shim=types.ModuleType('r108_restart_history')
    for name in ('baseline','getpid','ui_nodes','touch','evidence_gate','report_json','pulled_history_zip'):
        setattr(shim,name,lambda *args,**kwargs: None)
    sys.modules['r108_restart_history']=shim
try:
    import r108_offline_recovery_parity
except ModuleNotFoundError:
    shim=types.ModuleType('r108_offline_recovery_parity')
    shim.verify=lambda *args,**kwargs: None
    sys.modules['r108_offline_recovery_parity']=shim
from r109_history_recovery import find_exact_ui_export,PREPARE_JS
f='/mnt/data/Kiwi_R108_第二轮_真实历史出现_按钮定位失败证据_Run43197003529.zip'
if Path(f).is_file():
    with zipfile.ZipFile(f) as z:
        xml=z.read('r108_history_after_async_load.xml').decode()
        # Real offscreen button bounds [0,0] must never be clicked.
        assert find_exact_ui_export(xml,'已结束 · 请求 36') is None
        print('R109_REAL_OFFSCREEN_XML_FAIL_CLOSED=PASS')
else:
    print('R109_REAL_XML fixture not mounted on CI; synthetic structural safety tests remain')

def doc(rows):
    return ('<?xml version="1.0" encoding="utf-8"?>'
     '<hierarchy><node text="Root" bounds="[0,0][1080,1920]">'
     +''.join(rows)+'</node></hierarchy>')

def row(detail, buttonBounds, include=True):
    buttons=(f'<node text="导出" clickable="true" bounds="{buttonBounds}"/>' if include else '')
    return (f'<node text="Row" bounds="[80,200][980,650]">'
            f'<node text="{detail}" bounds="[100,230][900,280]"/>{buttons}'
            '</node>')
expected='已结束 · 请求 36'
a=doc([row('2026年11月12日 10:08:55 · 已结束 · 请求 36 · 下载 0','[390,500][650,570]'),
       row('2026年11月12日 10:08:12 · 已结束 · 请求 22 · 下载 0','[390,690][650,750]')])
assert find_exact_ui_export(a,expected)[:2]==(520,535)
assert find_exact_ui_export(a,expected) is not None
assert find_exact_ui_export(doc([row(expected,'[0,0][0,0]')]),expected) is None
assert find_exact_ui_export(doc([row('进行中 · 请求 36','[390,500][650,570]')]),expected) is None
assert find_exact_ui_export(doc([row(expected,'[390,500][650,570]'),row(expected,'[390,800][650,870]')]),expected) is None
print('R109_XML_ACCESSIBILITY_REGRESSION=PASS five fail-closed conditions')
