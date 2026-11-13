#!/usr/bin/env python3
"""Perform actual APKTool/Baksmali/JADX analysis, iterate ALL classesN.dex."""
import hashlib,json,pathlib,subprocess,sys,zipfile
apk=pathlib.Path("android-coldboot-v11/fixture/app/build/outputs/apk/debug/app-debug.apk")
root=pathlib.Path("out/coldboot_v11");root.mkdir(parents=True,exist_ok=True)
tools=pathlib.Path("out/android_reverse_offline_v1/tools")
jadx=pathlib.Path("out/jadx-extracted/bin/jadx")
def cmd(name,args):
 p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
 (root/(name+".log")).write_text(p.stdout)
 return p.returncode
with zipfile.ZipFile(apk) as z:
 assert z.testzip() is None
 names=sorted((x for x in z.namelist() if x.startswith("classes") and x.endswith(".dex")))
 assert names,"APK must include DEX"
 for n in names:(root/n).write_bytes(z.read(n))
r={"schema":"REUSE_STATIC_V11","apk_sha256":hashlib.sha256(apk.read_bytes()).hexdigest(),
   "apk_bytes":apk.stat().st_size,"dex_names":names,"steps":{},"target_class_locations":[]}
r["steps"]["apk_zip_crc"]="PASS"
r["steps"]["apktool_decode"]="PASS" if cmd("apktool_decode",["java","-jar",str(tools/"apktool_3.0.3.jar"),"d","-f","-s","-o",str(root/"decoded_resources"),str(apk)])==0 and (root/"decoded_resources/AndroidManifest.xml").exists() else "FAIL"
dex_smali=False;dex_java=False
for n in names:
 dex=root/n
 label=n.replace(".","_")
 smali=root/("smali_"+label)
 c=cmd("baksmali_"+label,["java","-jar",str(tools/"baksmali-3.0.10-fat-release.jar"),"disassemble",str(dex),"-o",str(smali)])
 is_smali=(c==0 and (smali/"org/example/reversefixture/MainActivity.smali").exists())
 if is_smali:dex_smali=True;r["target_class_locations"].append(n)
 java=root/("java_"+label)
 c=cmd("jadx_"+label,["bash",str(jadx),"--no-res","-d",str(java),str(dex)])
 if c==0 and (java/"sources/org/example/reversefixture/MainActivity.java").exists():dex_java=True
r["steps"]["baksmali_target_class"]="PASS" if dex_smali else "FAIL"
r["steps"]["jadx_target_java"]="PASS" if dex_java else "FAIL"
(root/"REUSE_static.json").write_text(json.dumps(r,indent=2))
print(json.dumps(r))
if "FAIL" in r["steps"].values():sys.exit(6)
