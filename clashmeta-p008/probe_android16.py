#!/usr/bin/env python3
"""P0-08 public-only Android 16 emulator environment diagnostics.
No Clash Meta private source, APK, VPN app, or user network configuration.
This checks whether API 36 AVD can boot and expose ADB / VPN Settings.
"""
import json, os, pathlib, subprocess, time
out=pathlib.Path("p008-evidence");out.mkdir(exist_ok=True)
def run(label,argv,timeout=60,required=False):
    t=time.time()
    try:
        p=subprocess.run(argv,capture_output=True,text=True,errors="replace",timeout=timeout)
        result={"command":argv,"code":p.returncode,"duration_s":round(time.time()-t,2),"stdout":p.stdout[-15000:],"stderr":p.stderr[-7000:]}
    except Exception as e:
        result={"command":argv,"code":None,"duration_s":round(time.time()-t,2),"exception":repr(e)}
    (out/f"{label}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    if required and result.get("code")!=0:raise RuntimeError(f"{label} failed")
    return result
run("devices",["adb","devices","-l"],required=True)
sdk=run("api_level",["adb","shell","getprop","ro.build.version.sdk"],required=True)
version=run("release",["adb","shell","getprop","ro.build.version.release"],required=True)
run("fingerprint",["adb","shell","getprop","ro.build.fingerprint"],required=True)
run("abi",["adb","shell","getprop","ro.product.cpu.abi"],required=True)
run("vpn_settings_action",["adb","shell","am","start","-a","android.settings.VPN_SETTINGS"],required=False)
run("always_on_setting",["adb","shell","settings","get","secure","always_on_vpn_app"],required=False)
run("lockdown_setting",["adb","shell","settings","get","secure","always_on_vpn_lockdown"],required=False)
run("connectivity_dumpsys",["adb","shell","dumpsys","connectivity"],timeout=90,required=False)
run("pm_vpn_related",["adb","shell","pm","list","packages"],required=False)
run("ui_dump",["adb","shell","uiautomator","dump","/sdcard/p008_vpn.xml"],timeout=60,required=False)
run("pull_ui",["adb","pull","/sdcard/p008_vpn.xml",str(out/"p008_vpn.xml")],required=False)
run("screenshot",["adb","shell","screencap","-p","/sdcard/p008_screen.png"],required=False)
run("pull_screenshot",["adb","pull","/sdcard/p008_screen.png",str(out/"p008_screen.png")],required=False)
api=sdk.get("stdout","").strip();release=version.get("stdout","").strip()
summary={"target":"Android 16 virtual environment, API 36","actual_api":api,"release":release,"api36_assertion":api=="36","no_private_source_uploaded":True,"not_tested":["ClashMeta APK", "VPN TUN", "Lockdown enforcement", "physical network IP leak", "Android 16 real hardware"]}
(out/"RESULT.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print("P008_RESULT",json.dumps(summary))
if api!="36":raise SystemExit("P008 environment mismatch, not Android 16 API36")
