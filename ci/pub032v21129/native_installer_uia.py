#!/usr/bin/env python3
# coding: utf-8
"""V8.10.1: REAL V2.11.2.9 Win32 installer GUI driver. Only Windows CI.
The optional Excel path shim tests presence-gate/filesystem behavior, NOT Office.
No private test data or original paths are printed to public workflow logs.
"""
import argparse,ctypes,json,re,subprocess,time,os
from pathlib import Path
from pywinauto import Desktop

def native_snapshot(u, pid):
    """Read-only PID-scoped Win32 window inspection; never log paths or private text."""
    WINENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)
    u.EnumWindows.argtypes = [WINENUM, ctypes.c_ssize_t]
    u.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
    u.SendMessageW.restype = ctypes.c_ssize_t
    result = dict(win32_windows=0, main_seen=False, failure_dialog_native=False,
                  main_button_enabled=False, status_error=None, status_phase=None)
    def read_text(h):
        buf = ctypes.create_unicode_buffer(800)
        u.SendMessageW(h, 0x000D, len(buf), ctypes.cast(buf, ctypes.c_void_p))
        return buf.value
    def each(hwnd, extra):
        owned = ctypes.c_uint(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owned))
        if int(owned.value) != int(pid):
            return True
        result["win32_windows"] += 1
        name = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(hwnd, name, len(name))
        cls = name.value
        if cls == "WorkPlatformInstaller":
            result["main_seen"] = True
            btn = u.GetDlgItem(hwnd, 203)
            result["main_button_enabled"] = bool(btn and u.IsWindowEnabled(btn))
            status = u.GetDlgItem(hwnd, 205)  # actual installer.c ID_STATUS
            text = read_text(status) if status else ""
            found = re.search(r"WF-(\d{3,5})", text)
            if found:
                result["status_error"] = int(found.group(1))
            for token in ("备份", "正在部署", "正在检查", "安装成功", "安装失败"):
                if token in text:
                    result["status_phase"] = token
                    break
        elif cls == "#32770":
            caption = ctypes.create_unicode_buffer(128)
            u.GetWindowTextW(hwnd, caption, len(caption))
            if caption.value == "工作平台 · 安装失败":
                result["failure_dialog_native"] = True
        return True
    callback = WINENUM(each)
    u.EnumWindows(callback, 0)
    return result

def run(exe,case,out,timeout):
    u=ctypes.windll.user32
    u.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p]
    u.FindWindowW.restype=ctypes.c_void_p
    u.GetWindowThreadProcessId.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint)]
    u.GetDlgItem.argtypes=[ctypes.c_void_p,ctypes.c_int]
    u.GetDlgItem.restype=ctypes.c_void_p
    u.IsWindowEnabled.argtypes=[ctypes.c_void_p]
    u.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    u.PostMessageW.restype=ctypes.c_int
    report=dict(case=case,real_win32_exe=True,main_window_seen=False,install_button_sent=False,
                failure_modal_seen=False,modal_uia_ok=False,WF_error=None,exit_code=None,
                office_test_shim_only=bool(os.getenv("PUB010_TEST_OFFICE_SHIM")),
                genuine_excel_macro_not_tested=True)
    p=None
    try:
        if not exe.is_file() or exe.stat().st_size<100000:
            raise RuntimeError("Missing/improbably small generated EXE")
        p=subprocess.Popen([str(exe)])
        start=time.monotonic();modal_start=None;closed=None
        snapshot_last_at=-20
        report["v812_diag_scope"]="PID-only native windows and status codes; no paths/data"
        report["native_window_snapshots"]=[]
        while time.monotonic()-start<timeout:
            code=p.poll()
            if code is not None:
                report["exit_code"]=code;break
            elapsed=time.monotonic()-start
            if elapsed-snapshot_last_at>=15:
                try:
                    snapshot=native_snapshot(u,p.pid)
                    snapshot["elapsed_sec"]=round(elapsed,1)
                    report["native_window_snapshots"].append(snapshot)
                    report["native_window_snapshots"]=report["native_window_snapshots"][-8:]
                    if snapshot["failure_dialog_native"]:
                        report["failure_modal_native_seen"]=True
                    if snapshot["status_error"] is not None:
                        report["last_native_status_error"]=snapshot["status_error"]
                except Exception as diag_exc:
                    report["native_snapshot_error"]=type(diag_exc).__name__
                snapshot_last_at=elapsed
            hwnd=u.FindWindowW("WorkPlatformInstaller","工作平台安装向导")
            if hwnd:
                other_pid=ctypes.c_uint(0)
                u.GetWindowThreadProcessId(hwnd,ctypes.byref(other_pid))
                if int(other_pid.value)!=p.pid:raise RuntimeError("Found foreign process window; fail closed")
                report["main_window_seen"]=True
                if not report["install_button_sent"]:
                    button=u.GetDlgItem(hwnd,203)
                    if button and u.IsWindowEnabled(button):
                        if not u.PostMessageW(hwnd,0x111,203,0):raise RuntimeError("Failed ID_INSTALL")
                        report["install_button_sent"]=True
            try:
                dlg=Desktop(backend="uia").window(title="工作平台 · 安装失败",process=p.pid)
                present=dlg.exists(timeout=0.1)
            except Exception:present=False
            if present and not report["modal_uia_ok"]:
                report["failure_modal_seen"]=True
                if modal_start is None:modal_start=time.monotonic()
                dialog=dlg.wrapper_object()
                named=[];n_other=0
                for btn in dialog.descendants(control_type="Button"):
                    if not btn.is_visible() or not btn.is_enabled():continue
                    label=btn.window_text().strip()
                    if label.casefold() in ("ok","确定"):named.append(btn)
                    else:n_other+=1
                if len(named)==1:
                    info=" ".join(x.window_text() for x in dialog.descendants(control_type="Text"))
                    found=re.findall(r"WF-(\d{3,5})",info)
                    report["WF_error"]=int(found[0]) if found else None
                    report["dialog_other_button_count"]=n_other
                    named[0].invoke()
                    report["modal_uia_ok"]=True
                    closed=time.monotonic()
                elif time.monotonic()-modal_start>10:
                    raise RuntimeError("No unique named OK/确定 in failure dialog; fail closed")
            if report["modal_uia_ok"] and hwnd and time.monotonic()-closed>0.5:
                button=u.GetDlgItem(hwnd,203)
                if button and u.IsWindowEnabled(button):
                    u.PostMessageW(hwnd,0x111,203,0)
            time.sleep(0.3)
        if p.poll() is None:
            try:
                report["timeout_native_snapshot"]=native_snapshot(u,p.pid)
            except Exception as diag_exc:
                report["timeout_snapshot_error"]=type(diag_exc).__name__
            raise TimeoutError("Actual installer did not exit; read sanitized native status+modal snapshot")
        report["exit_code"]=p.returncode
        if not report["install_button_sent"]:raise RuntimeError("Real install command was never sent")
        print("PUB010_WIN32_ACTUAL",case,"exit",p.returncode,"WF",report["WF_error"],"modal",report["failure_modal_seen"])
    except Exception as error:
        report["driver_failure"]=type(error).__name__+": "+str(error)[:160]
        raise
    finally:
        if p and p.poll() is None:
            p.kill();p.wait(timeout=10)
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding="utf8")
        print("PUB010_UIA_REPORT",out.name)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--exe",required=True);ap.add_argument("--case",required=True)
    ap.add_argument("--report",required=True);ap.add_argument("--timeout",type=int,default=100)
    a=ap.parse_args()
    run(Path(a.exe).resolve(strict=True),a.case,Path(a.report),a.timeout)
if __name__=="__main__":main()
