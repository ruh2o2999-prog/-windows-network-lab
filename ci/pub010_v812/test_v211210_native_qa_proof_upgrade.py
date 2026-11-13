#!/usr/bin/env python3
"""V8.12: native Windows EXE installer 34->28 analogous QA exclusion proof test.
Uses V2.11.2.9 original installer and V2.11.2.10 candidate installer *PEs*.
Payloads are hand-built synthetic 9 files -> 3 files, six real QA names and
correct SHA-256 source proof. This is NOT the 34->28 original P0-50 full gate.
"""
import hashlib,json,os,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pub032v21129"))
from native_installer_uia import run
TMP=Path(os.environ["RUNNER_TEMP"])
DATA=TMP/"pub027_v812_qa_proof"
OLD=DATA/"v812_old_9files.exe"
NEW=DATA/"v812_new_3files_qa6proof.exe"
manifest=DATA/"fixture_manifest.json"
ROOT=Path(os.environ["LOCALAPPDATA"])/"Programs"/"PUB027_V812_Synthetic"
OUT=Path("out")
REPORT=OUT/"pub027_v812_native_qa_proof_upgrade.json"
result={"standard":"V8.12","candidate":"V2.11.2.10 RC1",
        "scope":"Two real Windows installer PE stubs; hand-built synthetic 9->3 file manifests, NOT publisher-generated P0-50",
        "real_windows_executable":True,"true_excel_macros_tested":False,
        "source_archive_not_modified":True,"cases":[],"passed":False}
created_root=False

def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def require_files(table):
    for name,expected in table.items():
        p=ROOT/name
        if not p.is_file() or sha_file(p)!=expected["sha256"]:
            raise AssertionError("File missing or changed: "+name)
def gui(exe,label):
    dest=OUT/("pub027_v812_"+label+".json")
    try:
        run(exe,label,dest,60)
    finally:
        if dest.is_file():
            r=json.loads(dest.read_text(encoding="utf8"))
            result["cases"].append({"case":label,"exit_code":r.get("exit_code"),
                "real_gui_command":r.get("install_button_sent"),
                "failure_modal":r.get("failure_modal_seen"),
                "driver_error":r.get("driver_failure")})
    case=result["cases"][-1]
    if case["exit_code"]!=0 or case["failure_modal"] or not case["real_gui_command"]:
        raise AssertionError("Actual synthetic installer did not report clean success: "+label)
def backup_contains_any_exact(name,contents_hex):
    b=ROOT/"bak"
    if not b.is_dir():return False
    for p in b.iterdir():
        if not p.is_dir():continue
        f=p/name
        if f.is_file() and sha_file(f)==contents_hex:
            return True
    return False

try:
    OUT.mkdir(exist_ok=True)
    m=json.loads(manifest.read_text(encoding="utf8"))
    if ROOT.exists():
        raise RuntimeError("Refusing to touch existing installation target")
    if sha_file(OLD)!=m["old"]["sha256"] or sha_file(NEW)!=m["new"]["sha256"]:
        raise RuntimeError("Encrypted source bundle does not match byte-pinned manifests")
    assert len(m["old"]["payload_files"])==9
    assert len(m["new"]["payload_files"])==3
    qa=m["new"]["omitted_proof_sha256"]
    assert len(qa)==6
    result["fixture_sha256_verified"]=True
    result["real_old_stub_sha256"]=m["old_exe_stub_sha256"]
    result["real_new_stub_sha256"]=m["new_exe_stub_sha256"]
    created_root=True
    gui(OLD,"install_old_9_files")
    require_files(m["old_file_expected_sha256"] if False else
                  {n:{"sha256":v} for n,v in m["old_file_expected_sha256"].items()})
    userfile=ROOT/"personal_user_note.txt"
    userfile.write_bytes(b"MY-SYNTHETIC-PRIVATE-NOTE-PRESERVE")
    note_sha=sha_file(userfile)
    datafile=ROOT/"Data"/"keep_user.dat"
    data_sha=sha_file(datafile)
    gui(NEW,"upgrade_new_3_files_with_exclusion_proof")
    require_files({n:{"sha256":v} for n,v in m["new_file_expected_sha256"].items() if not n.startswith(("Data/","Data\\"))})
    if sha_file(datafile)!=data_sha or sha_file(userfile)!=note_sha:
        raise AssertionError("Old Data or user note changed during upgrade")
    # This list counts QA files STILL PRESENT in the live install root.
    # The previous assertion was inverted (it expected six present!).
    remaining=[n for n in qa if (ROOT/n).exists()]
    result["qa_exact_six_checked"]=len(qa)
    result["qa_remaining_in_live_root"]=len(remaining)
    result["qa_remaining_names"]=remaining
    if remaining:
        raise AssertionError("Six SHA-pinned QA exclusions left unexpected live files: "+str(len(remaining)))
    if not all(backup_contains_any_exact(n,h) for n,h in qa.items()):
        raise AssertionError("Original QA content not retained in a dated backup")
    result["exact_six_omitted_from_live"]=True
    result["all_six_in_dated_backup"]=True
    result["user_data_unchanged"]=True

    # Reintroduce original six files, then simulate user editing one.
    gui(OLD,"reintroduce_old_9_files")
    require_files({n:{"sha256":v} for n,v in m["old_file_expected_sha256"].items() if n in qa})
    edited=sorted(qa)[0]
    with (ROOT/edited).open("ab") as f:f.write(b"\r\nREM synthetic user modification\r\n")
    edited_sha=sha_file(ROOT/edited)
    gui(NEW,"upgrade_modified_qa_untouched")
    present=[n for n in qa if (ROOT/n).exists()]
    if present!=[edited]:raise AssertionError("Edited QA preservation selection wrong")
    if sha_file(ROOT/edited)!=edited_sha:
        raise AssertionError("User-edited QA was overwritten or changed")
    if sha_file(datafile)!=data_sha or sha_file(userfile)!=note_sha:
        raise AssertionError("Data/user note changed after edited-QA upgrade")
    result["user_edited_qa_file_retained_byte_exact"]=True
    result["modified_qa_name"]=edited
    result["remaining_five_excluded"]=True
    result["all_originals_preserved_by_backup"]=True
    result["passed"]=True
    print("PUB027_V812_V211210_NATIVE_QA_SHA_PROOF_UPGRADE_PASS")
except Exception as exc:
    result["error"]=type(exc).__name__+": "+str(exc)[:180]
    raise
finally:
    OUT.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding="utf8")
    if created_root and ROOT.exists():
        shutil.rmtree(ROOT,ignore_errors=True)
