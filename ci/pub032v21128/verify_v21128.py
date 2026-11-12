#!/usr/bin/env python3
"""Independent read-only audit of real V2.11.2.8 publisher EXE, 34-file P0-50 test fixture."""
import argparse,hashlib,json,sys,pathlib,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"pub032v5"))
from audit_v6_payload import audit_exe,audit_zip,compare,QA_CANDIDATES
parser=argparse.ArgumentParser()
parser.add_argument("exe");parser.add_argument("source");parser.add_argument("expected")
parser.add_argument("report");parser.add_argument("--exclude-six-qa-cmd",action="store_true")
args=parser.parse_args()
exe,source,expected_path,report_path=args.exe,args.source,args.expected,args.report
report={"product":"工作平台发布器 V2.11.2.8","scope":"Real Windows publisher EXE V6 member readback; no claim that installer ran"}
try:
    expected=json.loads(pathlib.Path(expected_path).read_text("utf8"))
    assert expected["version"]=="V2.11.2.8"
    assert expected["original_P050_test_fixture"] is True and expected["expected_count"]==34
    reference=[{"relative_path":name,"size_bytes":v["size"],"sha256":v["sha256"]} for name,v in expected["files"].items()]
    original=audit_zip(source)
    packed=audit_exe(exe)
    source_against_ref=compare(original,reference)
    reference_output=[row for row in original if not(args.exclude_six_qa_cmd and row["relative_path"] in QA_CANDIDATES)]
    exe_against_source=compare(packed["files"],reference_output)
    expected_count=28 if args.exclude_six_qa_cmd else 34
    assert packed["count"]==expected_count and packed["mode"]==3 and packed["entry"].replace("\\","/")=="wf_p042_candidate.xlsm"
    assert source_against_ref["passed"] and exe_against_source["passed"]
    kept={row["relative_path"] for row in packed["files"]}
    if args.exclude_six_qa_cmd:
        assert len(QA_CANDIDATES)==6
        assert not(kept & QA_CANDIDATES),"At least one QA CMD unexpectedly retained"
        assert "RUN_WANFANG_WORKBENCH.cmd" in kept,"Actual runtime entry CMD missing"
    templates={r["relative_path"]:r["sha256"] for r in packed["files"] if r["relative_path"].startswith("DataTemplates/")}
    assert len(templates)==4
    report.update({"passed":True,"count":packed["count"],"mode":packed["mode"],"entry":packed["entry"],
        "installer_bytes":pathlib.Path(exe).stat().st_size,
        "installer_sha256":hashlib.sha256(pathlib.Path(exe).read_bytes()).hexdigest(),
        "source_vs_expected":source_against_ref,"exe_vs_selected_source":exe_against_source,"qa_six_excluded":args.exclude_six_qa_cmd,"excluded_qa_names":sorted(QA_CANDIDATES) if args.exclude_six_qa_cmd else [],
        "templates_count":len(templates),"templates_sha256":templates})
except Exception as err:
    report.update({"passed":False,"error":repr(err)})
pathlib.Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k not in ["templates_sha256"]},ensure_ascii=True))
raise SystemExit(0 if report["passed"] else 3)
