#!/usr/bin/env python3
"""V8.10.1 GUI automation route-B native Windows smoke ONLY.
Test a disposable message box, not the actual business installer or Excel.
"""
import ctypes
import json
import os
import subprocess
import sys
import time

from pywinauto import Desktop

title = "PUB010-PYWINAUTO-UIA-SMOKE"
child = (
    "import ctypes,sys;"
    "r=ctypes.windll.user32.MessageBoxW(None,'Controlled test-only modal',"
    "'PUB010-PYWINAUTO-UIA-SMOKE',0);"
    "sys.exit(0 if r==1 else 5)"
)
p = subprocess.Popen([sys.executable, "-c", child])
errors = []
result = {"product": "工作平台发布器 V2.11.2.9 RC1",
          "scope": "Test-only native Windows MessageBox; NOT real product installer",
          "backend": None, "popup_owner_pid_verified": False, "passed": False}
try:
    deadline = time.monotonic() + 18
    clicked = False
    while time.monotonic() < deadline and not clicked:
        if p.poll() is not None:
            raise RuntimeError("controlled child exited before automating popup")
        for backend in ("uia", "win32"):
            try:
                window = Desktop(backend=backend).window(title=title)
                if not window.exists(timeout=0.3):
                    continue
                dialog = window.wrapper_object()
                owner_pid = int(dialog.element_info.process_id)
                if owner_pid != p.pid:
                    raise RuntimeError("popup PID mismatch; refusing interaction")
                buttons = [b for b in dialog.descendants(control_type="Button")
                           if b.is_visible() and b.is_enabled()]
                # UIA may expose the title-bar Close control as well as dialog OK.
                # Never invoke every visible Button or assume the first is safe.
                named_ok = [b for b in buttons if b.window_text().strip().casefold()
                            in ("ok", "确定")]
                if len(named_ok) != 1:
                    errors.append({"backend": backend, "visible_buttons": len(buttons),
                                   "button_names": [b.window_text()[:30] for b in buttons]})
                    continue
                buttons = named_ok
                result["popup_owner_pid_verified"] = True
                result["backend"] = backend
                # UIA invokes the actual provider, win32 click_input is the fallback.
                if backend == "uia":
                    buttons[0].invoke()
                else:
                    buttons[0].click_input()
                clicked = True
                break
            except Exception as exc:
                errors.append({"backend": backend, "type": type(exc).__name__,
                               "reason": str(exc)[:200]})
        if not clicked:
            time.sleep(0.3)
    if not clicked:
        raise RuntimeError("Neither UI Automation nor Win32 backend found one safe OK button")
    try:
        code = p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Popup did not close after button invocation")
    if code != 0:
        raise RuntimeError("Controlled popup returned non-OK: %s" % code)
    result["passed"] = True
    print("PUB010_V8101_PYWINAUTO_NATIVE_MESSAGEBOX_PASS")
except Exception as exc:
    result["error"] = str(exc)
    raise
finally:
    result["errors"] = errors[-12:]
    if p.poll() is None:
        p.kill()
        p.wait(timeout=10)
    os.makedirs("out", exist_ok=True)
    with open("out/pub010_v8101_pywinauto_smoke.json", "w", encoding="utf8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=True))
