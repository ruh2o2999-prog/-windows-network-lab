#!/usr/bin/env python3
"""V8.12 native-only test for sanitized PID-scoped modal diagnostics."""
import ctypes,json,os,subprocess,sys,time
from pathlib import Path
from pywinauto import Desktop
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pub032v21129"))
from native_installer_uia import native_snapshot, acknowledge_owned_failure_modal
out=Path("out/pub010_v812_modal_snapshot_smoke.json")
p=None
result={"scope":"Controlled Win32 MessageBox only; not product installer","passed":False}
try:
    child="import ctypes,sys; rc=ctypes.windll.user32.MessageBoxW(None,'SYNTHETIC-ERR-WF-3060','工作平台 · 安装失败',0); sys.exit(0 if rc==1 else 4)"
    p=subprocess.Popen([sys.executable,"-c",child])
    u=ctypes.windll.user32
    u.GetWindowThreadProcessId.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint)]
    u.GetDlgItem.argtypes=[ctypes.c_void_p,ctypes.c_int]
    u.GetDlgItem.restype=ctypes.c_void_p
    u.IsWindowEnabled.argtypes=[ctypes.c_void_p]
    deadline=time.monotonic()+16
    snap={}
    while time.monotonic()<deadline:
        if p.poll() is not None:raise RuntimeError("Controlled dialog exited unexpectedly")
        snap=native_snapshot(u,p.pid)
        if snap["failure_dialog_native"]:break
        time.sleep(0.25)
    if not snap.get("failure_dialog_native"):
        raise RuntimeError("PID-scoped Win32 modal could not be observed")
    result["pid_scope_pass"]=True
    result["windows_observed"]=snap["win32_windows"]
    other=native_snapshot(u,p.pid+200000)
    if other["failure_dialog_native"]:
        raise RuntimeError("Cross-process window was mistaken for an owned modal")
    result["foreign_pid_rejected"]=True
    # Exercise the exact known-error modal fallback used by the product driver.
    # Never click a foreign PID or a different dialog caption.
    if not acknowledge_owned_failure_modal(u,p.pid):
        raise RuntimeError("Native PID/title/IDOK Button validation or BM_CLICK failed")
    if p.wait(timeout=7)!=0:raise RuntimeError("Native IDOK click did not close the controlled dialog")
    result["native_pid_scoped_idok_bm_click_pass"]=True
    result["passed"]=True
    print("PUB010_V812_WIN32_MODAL_IDOK_BMCLICK_PASS")
except Exception as e:
    result["error"]=type(e).__name__+": "+str(e)[:180]
    raise
finally:
    if p and p.poll() is None:p.kill();p.wait(timeout=7)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding="utf8")
    print(json.dumps(result,ensure_ascii=True))
