#!/usr/bin/env python3
"""Use actual upstream JADX, Baksmali and Apktool on a newly built public APK."""
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
 dex=z.read("classes.dex");(root/"fixture_classes.dex").write_bytes(dex)
r={"schema":"REUSE_STATIC_V11","apk_sha256":hashlib.sha256(apk.read_bytes()).hexdigest(),"apk_bytes":apk.stat().st_size,"steps":{}}
r["steps"]["apk_zip_crc"]="PASS"
r["steps"]["apktool_decode"]="PASS" if cmd("apktool_decode",["java","-jar",str(tools/"apktool_3.0.3.jar"),"d","-f","-s","-o",str(root/"decoded_resources"),str(apk)])==0 and (root/"decoded_resources/AndroidManifest.xml").exists() else "FAIL"
r["steps"]["baksmali"]="PASS" if cmd("baksmali_real",["java","-jar",str(tools/"baksmali-3.0.10-fat-release.jar"),"disassemble",str(root/"fixture_classes.dex"),"-o",str(root/"smali")])==0 and (root/"smali/org/example/reversefixture/MainActivity.smali").exists() else "FAIL"
r["steps"]["jadx"]="PASS" if cmd("jadx_real",["bash",str(jadx),"--no-res","-d",str(root/"java"),str(root/"fixture_classes.dex")])==0 and (root/"java/sources/org/example/reversefixture/MainActivity.java").exists() else "FAIL"
out=root/"REUSE_static.json";out.write_text(json.dumps(r,indent=2))
print(json.dumps(r))
if "FAIL" in r["steps"].values():sys.exit(6)
