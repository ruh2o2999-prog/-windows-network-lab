#!/usr/bin/env python3
"""Isolated public-APK smoke test. No private user APK or personal log is uploaded."""
import hashlib,json,os,pathlib,re,subprocess,time,xml.etree.ElementTree as ET
OUT=pathlib.Path("out/toutiao-logger-v01")
OUT.mkdir(parents=True,exist_ok=True)
APK=pathlib.Path("out/LogSleuth-0.4.1.APK")
PKG="io.github.shiaho777.logsleuth.app"
res={"source":"LogSleuth v0.4.1 public GitHub release","package":PKG,"gates":{},"warnings":[]}
def cmd(args,timeout=120):
    try:
        p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,check=False)
        return p.returncode,p.stdout
    except Exception as e:return 99,str(e)
def save(name,txt):
    (OUT/name).write_text(str(txt),encoding="utf-8",errors="replace")
def gate(name,ok,detail=""):
    res["gates"][name]={"passed":bool(ok),"detail":detail[:800] if isinstance(detail,str) else detail}
    (OUT/"result.json").write_text(json.dumps(res,ensure_ascii=False,indent=2))
def adb(*args,timeout=120):return cmd(["adb",*args],timeout=timeout)
try:
    res["apk_sha256"]=hashlib.sha256(APK.read_bytes()).hexdigest()
    res["apk_size"]=APK.stat().st_size
    ver=adb("shell","getprop","ro.build.version.release")[1].strip()
    abi=adb("shell","getprop","ro.product.cpu.abilist")[1].strip()
    boot=adb("shell","getprop","sys.boot_completed")[1].strip()
    res["system"]={"android_release":ver,"abi":abi,"boot_completed":boot}
    gate("g1_android_boot",boot=="1",str(res["system"]))
    code,install=adb("install","-r",str(APK),timeout=180)
    save("install.txt",install)
    gate("g2_real_apk_install",code==0 and "Success" in install,install)
    code,grant=adb("shell","pm","grant",PKG,"android.permission.READ_LOGS")
    save("read_logs_permission.txt",grant)
    gate("g3_read_logs_permission",code==0 and "Exception" not in grant,grant or "pm grant returned success")
    code,launch=adb("shell","am","start","-W","-n",PKG+"/.MainActivity",timeout=60)
    save("launch.txt",launch)
    time.sleep(12)
    gate("g4_app_cold_launch",code==0 and ("Status: ok" in launch or "LaunchState" in launch),launch)
    code,ui=adb("shell","uiautomator","dump","/sdcard/window.xml",timeout=65)
    save("uiautomator.txt",ui)
    code,xml=adb("exec-out","cat","/sdcard/window.xml")
    save("initial_ui.xml",xml)
    try:
        root=ET.fromstring(xml)
        texts=[n.attrib.get("text","") for n in root.iter("node") if n.attrib.get("text","")]
        desc=[n.attrib.get("content-desc","") for n in root.iter("node") if n.attrib.get("content-desc","")]
        res["visible_texts"]=texts[:80]
        res["visible_descriptions"]=desc[:40]
        gate("g5_real_ui_hierarchy",bool(texts or desc)," / ".join((texts+desc)[:20]))
    except Exception as e:
        gate("g5_real_ui_hierarchy",False,str(e))
    code,png=cmd(["adb","exec-out","screencap","-p"])
    # subprocess text mode corrupts binary; redo with bytes
    p=subprocess.run(["adb","exec-out","screencap","-p"],capture_output=True,timeout=45)
    if p.returncode==0 and p.stdout.startswith(b"\x89PNG"):
        (OUT/"initial_screen.png").write_bytes(p.stdout)
    gate("g6_real_screenshot",p.returncode==0 and p.stdout.startswith(b"\x89PNG"),f"{len(p.stdout)} bytes")
    # A genuinely emitted log line, used as a host-side baseline. Not evidence that the app read it.
    adb("shell","log","-p","e","-t","TT935_CI_MARKER","HELLO_FROM_EMULATOR_PUBLIC_TEST")
    _,logs=adb("logcat","-d","-v","threadtime",timeout=60)
    save("full_logcat.txt",logs[-1200000:])
    gate("g7_real_system_log_event","HELLO_FROM_EMULATOR_PUBLIC_TEST" in logs, "Present in emulator system Logcat (not yet viewer export)")
    crashes=[x for x in logs.splitlines() if any(t in x for t in ("FATAL EXCEPTION", "Fatal signal", "ANR in "+PKG))]
    res["fatal_log_lines"]=crashes[-20:]
    gate("g8_no_app_fatal_crash",not any(PKG in x for x in crashes)," / ".join(crashes[-5:]) or "No target process fatal line")
    # Save actual app foreground information for independent review
    _,top=adb("shell","dumpsys","activity","activities",timeout=40)
    save("activity_dumpsys.txt",top[-30000:])
except Exception as e:
    res["warnings"].append("smoke harness exception: "+repr(e))
finally:
    (OUT/"result.json").write_text(json.dumps(res,ensure_ascii=False,indent=2))
    print(json.dumps({"gates":res["gates"],"system":res.get("system",{}),"warnings":res["warnings"]},ensure_ascii=False))
