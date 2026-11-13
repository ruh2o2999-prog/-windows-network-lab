#!/usr/bin/env python3
"""Download official Android reverse-engineering releases and smoke-test them.
PUBLIC tools + PUBLIC fixture only. Do NOT upload a private target APK.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,zipfile
BASE=Path("out/android_reverse_offline_v1")
TOOLS=BASE/"tools"
EVID=BASE/"evidence"
TOOLS.mkdir(parents=True,exist_ok=True);EVID.mkdir(exist_ok=True)
RELEASES={
 "jadx-1.5.6.zip":("https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip",72646741,None),
 "apktool_3.0.3.jar":("https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar",15478013,None),
 "baksmali-3.0.10-fat-release.jar":("https://github.com/baksmali/smali/releases/download/3.0.10/baksmali-3.0.10-fat-release.jar",4447943,"37ae4a41a8886e15c20b8362fa4250f96bbdb55e1a608199ad8b5dff068b588f"),
 "smali-3.0.10-fat-release.jar":("https://github.com/baksmali/smali/releases/download/3.0.10/smali-3.0.10-fat-release.jar",5384623,"32fa0e88a6c397b3922201adf5f3e534fbaed5a663c71d0c558c3ddce0af844a"),
}
def cmd(label,args,timeout=180):
 try:
  p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,check=False)
  (EVID/(label+".log")).write_text(p.stdout)
  return {"returncode":p.returncode,"output_tail":p.stdout[-1800:],"command":args}
 except Exception as e:
  return {"returncode":99,"error":str(e),"command":args}
report={"schema":"android-toolchain-v1","created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"downloads":{},"tests":{}}
def persist(): (EVID/"test_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
for name,(url,expected_size,expected_hash) in RELEASES.items():
 path=TOOLS/name
 p=cmd("fetch_"+name,["curl","-fL","--retry","4","--retry-all-errors","--connect-timeout","20","--max-time","240",url,"-o",str(path)],timeout=265)
 if p["returncode"]!=0:raise RuntimeError(f"{name} download failed: {p}")
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 row={"source":url,"size":path.stat().st_size,"sha256":digest,"valid_size":path.stat().st_size==expected_size,
      "valid_pinned_sha256":(digest==expected_hash if expected_hash else None)}
 report["downloads"][name]=row;persist()
 if not row["valid_size"] or row["valid_pinned_sha256"] is False:raise RuntimeError(f"official artifact mismatch: {name}: {row}")
with zipfile.ZipFile(TOOLS/"jadx-1.5.6.zip") as z:
 assert z.testzip() is None
 z.extractall("out/jadx-extracted")
jadx=Path("out/jadx-extracted/bin/jadx")
assert jadx.is_file()
for label,args in [
 ("java_version",["java","-version"]),
 ("jadx_version",["bash",str(jadx),"--version"]),
 ("apktool_version",["java","-jar",str(TOOLS/"apktool_3.0.3.jar"),"--version"]),
 ("baksmali_help",["java","-jar",str(TOOLS/"baksmali-3.0.10-fat-release.jar"),"--help"]),
 ("smali_help",["java","-jar",str(TOOLS/"smali-3.0.10-fat-release.jar"),"--help"])
]:
 res=cmd(label,args,timeout=90);report["tests"][label]=res;persist()
# Build a single-class fixture ourselves, proving smali -> dex -> baksmali -> JADX.
smali_src=Path("out/fixture/com/example/Proof.smali")
smali_src.parent.mkdir(parents=True,exist_ok=True)
smali_src.write_text(".class public Lcom/example/Proof;\n.super Ljava/lang/Object;\n\n.method public static answer()I\n    .registers 1\n    const/16 v0, 0x2a\n    return v0\n.end method\n")
dex=Path("out/smoke-proof.dex")
res=cmd("smali_assemble",["java","-jar",str(TOOLS/"smali-3.0.10-fat-release.jar"),"assemble","out/fixture","-o",str(dex)],timeout=120)
report["tests"]["smali_assemble"]=res;persist()
if dex.exists() and dex.read_bytes()[:4]==b"dex\n":
 res=cmd("baksmali_disassemble",["java","-jar",str(TOOLS/"baksmali-3.0.10-fat-release.jar"),"disassemble",str(dex),"-o","out/fixture-disassembled"],timeout=120)
 report["tests"]["baksmali_disassemble"]=res
 report["tests"]["baksmali_roundtrip"]= {"passed": Path("out/fixture-disassembled/com/example/Proof.smali").is_file()}
 res=cmd("jadx_decompile_dex",["bash",str(jadx),"--no-res","-d","out/fixture-java",str(dex)],timeout=160)
 report["tests"]["jadx_decompile_dex"]=res
 report["tests"]["jadx_java_output"]= {"passed":Path("out/fixture-java/sources/com/example/Proof.java").is_file()}
 persist()
# APKTool real decode on public LogSleuth APK, not private Toutiao APK.
apk=Path("out/public-LogSleuth-0.4.1.apk")
res=cmd("download_public_test_apk",["curl","-fL","--retry","4","--retry-all-errors","https://github.com/shiaho777/LogSleuth/releases/download/v0.4.1/LogSleuth-0.4.1.APK","-o",str(apk)],timeout=200)
report["tests"]["download_public_test_apk"]=res;persist()
if apk.is_file() and apk.stat().st_size>2000000:
 res=cmd("apktool_public_apk_decode",["java","-Xmx2g","-jar",str(TOOLS/"apktool_3.0.3.jar"),"decode","--force","--no-src","--output","out/public-apk-decoded",str(apk)],timeout=240)
 report["tests"]["apktool_public_apk_decode"]=res
 report["tests"]["apktool_manifest_xml"]={"passed":Path("out/public-apk-decoded/AndroidManifest.xml").is_file()}
 persist()
report["summary"]={"tool_files":len(RELEASES),"smoke_roundtrip":report["tests"].get("baksmali_roundtrip",{}).get("passed",False),"jadx_java":report["tests"].get("jadx_java_output",{}).get("passed",False),"apktool_manifest":report["tests"].get("apktool_manifest_xml",{}).get("passed",False)}
persist()
print(json.dumps({"summary":report["summary"],"downloads":report["downloads"]},indent=2))
if not all(report["summary"][x] for x in ["smoke_roundtrip","jadx_java","apktool_manifest"]):
 raise SystemExit("TOOLCHAIN_SMOKE_INCOMPLETE")
