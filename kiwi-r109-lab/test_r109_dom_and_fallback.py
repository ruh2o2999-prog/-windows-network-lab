#!/usr/bin/env python3
"""R109 WebView flat-history regression: based on genuine R108 UIAutomation tree.
No synthetic/test-only PASS may substitute Android task history export.
"""
import sys,types,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:import r108_restart_history
except ModuleNotFoundError:
    shim=types.ModuleType('r108_restart_history')
    for name in ('baseline','getpid','ui_nodes','touch','evidence_gate','report_json','pulled_history_zip'):
        setattr(shim,name,lambda *a,**kwargs:None)
    sys.modules['r108_restart_history']=shim
try:import r108_offline_recovery_parity
except ModuleNotFoundError:
    shim=types.ModuleType('r108_offline_recovery_parity');shim.verify=lambda *a,**kw:None
    sys.modules['r108_offline_recovery_parity']=shim
from r109_history_recovery import find_exact_ui_export

def child(text,bounds='[0,0][0,0]',clickable=False):
    return f'<node text="{text}" clickable="{str(clickable).lower()}" bounds="{bounds}"/>'

def task(time,status,count,bounds='[0,0][0,0]',button_bounds='[0,0][0,0]'):
    return (child('http://127.0.0.1:18764/',bounds)
      +child(f'{time} · {status} · 请求 {count} · 下载 0',bounds)
      +child('查看',button_bounds,True)
      +child('导出',button_bounds,True)
      +child('长会话分卷',button_bounds,True)
      +child('清空此任务',button_bounds,True))

def doc(tasks):
    return ('<?xml version="1.0"?><hierarchy><node text="WebView" scrollable="false">'
       '<node text="history_container" scrollable="true">'+tasks+'</node>'
       '</node></hierarchy>')

prefix=task('2026年11月12日 10:09:55','进行中',34)
target=task('2026年11月12日 10:08:55','已结束',36,
            bounds='[85,540][965,860]',button_bounds='[420,760][640,840]')
other=task('2026年11月12日 10:08:39','已结束',22)
xml=doc(prefix+target+other)
assert find_exact_ui_export(xml,'已结束 · 请求 36',started_at='2026年11月12日 10:08:55')[:2]==(530,800)
assert find_exact_ui_export(doc(prefix+task('2026年11月12日 10:08:55','已结束',36)+other),'已结束 · 请求 36') is None
assert find_exact_ui_export(doc(prefix+task('2026年11月12日 10:08:55','进行中',36)+other),'已结束 · 请求 36') is None
assert find_exact_ui_export(doc(prefix+target+target+other),'已结束 · 请求 36') is None
assert find_exact_ui_export(xml,'已结束 · 请求 36',started_at='2026年11月12日 10:07:55') is None
print('R109_FLATTENED_UI_WEBVIEW_HISTORY_REGRESSION=PASS 5 scenarios')

# Additional independent exact previous Android UI XML: here both the row
# and button were *offscreen*, so no coordinates may be clicked.
real=Path('/mnt/data/Kiwi_R108_第二轮_真实历史出现_按钮定位失败证据_Run43197003529.zip')
if real.exists():
    with zipfile.ZipFile(real) as z:raw=z.read('r108_history_after_async_load.xml').decode()
    assert find_exact_ui_export(raw,'已结束 · 请求 36') is None
    r=ET.fromstring(raw[raw.index('<?xml'):]);parent={c:p for p in r.iter() for c in p}
    n=next(n for n in r.iter('node') if '已结束 · 请求 36' in n.get('text','') and len(n.get('text',''))<140)
    flattened=parent[n];buttons=list(flattened)
    assert len(buttons)==30 and buttons[15].get('text')=='导出'
    buttons[15].set('bounds','[420,760][640,840]')
    visible='<?xml version="1.0"?>'+ET.tostring(r,encoding='unicode')
    assert find_exact_ui_export(visible,'已结束 · 请求 36',started_at='2026年11月12日 10:08:55')[:2]==(530,800)
    print('R109_ACTUAL_R108_XML_REPLAY_OFFSCREEN_AND_VISIBLE=PASS')
else:
    print('R109_REAL_ANDROID_XML_REPLAY=NOT_RUN: fixture not present on this CI runner')
