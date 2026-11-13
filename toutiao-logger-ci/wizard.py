#!/usr/bin/env python3
"""Actual device UI wizard smoke: popup -> skip tour -> app picker -> record -> share."""
import json,pathlib,re,subprocess,time,xml.etree.ElementTree as ET
D=pathlib.Path("out/toutiao-logger-v02")
D.mkdir(parents=True,exist_ok=True)
result={"tests":{},"screens":[],"notes":[]}
PKG="io.github.shiaho777.logsleuth.app"
def run(*args,timeout=60):
    p=subprocess.run(["adb",*args],capture_output=True,text=True,errors="replace",timeout=timeout)
    return p.returncode,p.stdout+p.stderr
def step(label,ok,detail=""):
    result["tests"][label]={"passed":bool(ok),"detail":str(detail)[:600]}
    (D/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
def ui(name):
    run("shell","uiautomator","dump","/sdcard/wizard.xml",timeout=60)
    code,txt=run("exec-out","cat","/sdcard/wizard.xml")
    (D/(name+".xml")).write_text(txt,errors="replace")
    p=subprocess.run(["adb","exec-out","screencap","-p"],capture_output=True,timeout=30)
    if p.stdout.startswith(b"\x89PNG"): (D/(name+".png")).write_bytes(p.stdout)
    result["screens"].append(name)
    try:
        root=ET.fromstring(txt)
        nodes=[n.attrib for n in root.iter("node")]
    except Exception: nodes=[]
    return nodes
def textset(nodes):
    return [x.get("text","") or x.get("content-desc","") for x in nodes if x.get("text") or x.get("content-desc")]
def find(nodes,terms,exact=True):
    terms=[s.lower() for s in terms]
    for n in nodes:
        val=(n.get("text","") or n.get("content-desc","")).strip().lower()
        if val and (val in terms if exact else any(t in val for t in terms)):
            m=re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",n.get("bounds",""))
            if m:
                a,b,c,d=map(int,m.groups())
                return ((a+c)//2,(b+d)//2,n)
    return None
def tap(nodes,terms,label,exact=True):
    p=find(nodes,terms,exact)
    if not p:
        step(label,False,"not on visible screen: "+str(textset(nodes)[:35]))
        return False
    run("shell","input","tap",str(p[0]),str(p[1]))
    time.sleep(3)
    step(label,True,"tapped "+(p[2].get("text") or p[2].get("content-desc") or ""))
    return True
try:
    # Dismiss Android 13+ runtime popup, and bypass historical onboarding tour.
    code,grant=run("shell","pm","grant",PKG,"android.permission.POST_NOTIFICATIONS")
    nodes=ui("00_before_navigation")
    if find(nodes,["Allow","允许"]):
        tap(nodes,["Allow","允许"],"notification_dialog_tapped")
    nodes=ui("01_notifications_checked")
    if find(nodes,["Allow one-time access","允许一次性访问","Allow access"],exact=False):
        tap(nodes,["Allow one-time access","允许一次性访问","Allow access"],"android15_log_access_confirmation",exact=False)
        nodes=ui("01b_log_access_granted")
    if find(nodes,["Skip","跳过"]):
        tap(nodes,["Skip","跳过"],"tutorial_skip")
    nodes=ui("02_home")
    step("stream_main_loaded",bool(find(nodes,["Logs","日志"]) and find(nodes,["Report","报告"])),str(textset(nodes)[-25:]))
    if tap(nodes,["Report","报告"],"open_report_tab"):
        nodes=ui("03_report_pick_app")
        # Search for the public logger itself; do not use or upload private Toutiao data.
        p=None
        for a in nodes:
            if a.get("class","").endswith("EditText"):
                m=re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",a.get("bounds",""))
                if m:
                    x1,y1,x2,y2=map(int,m.groups())
                    p=((x1+x2)//2,(y1+y2)//2)
                    break
        if p:
            run("shell","input","tap",str(p[0]),str(p[1]))
            run("shell","input","text","LogSleuth")
            run("shell","input","keyevent","4")
            time.sleep(3)
        nodes=ui("04_report_app_filtered")
        step("report_app_picker",bool(find(nodes,[PKG],exact=False)),str(textset(nodes)[:24]))
        # Try the package name first, then the app label.
        if not tap(nodes,[PKG],"select_report_target",exact=False):
            if tap(nodes,["LogSleuth"],"select_report_target_label"):
                pass
        nodes=ui("05_report_app_selected")
        if tap(nodes,["Next","下一步","Continue"],"report_next"):
            nodes=ui("06_report_record_ready")
            if tap(nodes,["Start recording","开始录制","Start record"],"start_in_app_recording"):
                time.sleep(3)
                run("shell","log","-p","e","-t","TT935_REPORT_MARKER","CI_REPORT_RECORDING_STARTED")
                nodes=ui("07_recording_active")
                visible=" / ".join(textset(nodes)[-30:])
                step("recording_state_visible",("Recording" in visible or "recording" in visible or "录制" in visible),visible)
                if tap(nodes,["Stop & share","Stop and share","停止并分享","停止并导出"],"stop_in_app_recording",exact=False):
                    nodes=ui("08_share_stage")
                    has_zip=bool(find(nodes,["ZIP"],exact=True))
                    step("share_zip_option",has_zip,str(textset(nodes)[-25:]))
                    if has_zip and tap(nodes,["ZIP"],"invoke_zip_share"):
                        nodes=ui("09_android_share_sheet")
                        labels=textset(nodes)
                        step("android_share_sheet",bool(find(nodes,["Nearby Share","Bluetooth","Gmail","分享","Sharing","Copy","复制"],exact=False)),str(labels[-35:]))
except Exception as e:
    result["notes"].append("exception:"+repr(e))
finally:
    _,logs=run("logcat","-d","-v","threadtime",timeout=75)
    (D/"logcat-last.txt").write_text(logs[-1500000:],errors="replace")
    result["notes"].append("Any missing gate stays FAIL/NOT_RUN; do not infer a successful ZIP export without bytes.")
    (D/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print("WIZARD_TEST_RESULT="+json.dumps(result,ensure_ascii=False))
