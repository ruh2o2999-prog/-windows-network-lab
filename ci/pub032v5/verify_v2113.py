#!/usr/bin/env python3
"""Strict V2.11.3 product GUI output audit against entirely synthetic P0-50-shape input.
This program does NOT claim real business application/Excel/installer acceptance.
"""
import argparse,hashlib,json,sys,pathlib,zipfile
from audit_v6_payload import audit_exe, audit_zip, compare, AuditFailure
p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--source-zip',required=True);p.add_argument('--expected',required=True);p.add_argument('--report',required=True)
a=p.parse_args()
report={'scope':'Real V2.11.3 publisher GUI created EXE / V6 static payload readback, SYNTHETIC 34 files only', 'P050_real_bytes_tested':False, 'v21128_tested':False}
try:
    expect=json.loads(pathlib.Path(a.expected).read_text(encoding='utf8'))
    assert expect['expected_count']==34 and expect['genuine_P050_content_used'] is False
    files=audit_exe(a.exe);source=audit_zip(a.source_zip)
    source_cmp=compare(source,expect['files']);bundle_cmp=compare(files['files'],expect['files']);bundle_src=compare(files['files'],source)
    assert files['count']==34 and files['mode']==3, 'Not full 34-file multi-directory deployment'
    assert files['entry'].replace('\\','/')=='wf_p042_candidate.xlsm',f"Wrong workbook entry: {files['entry']}"
    assert source_cmp['passed'] and bundle_cmp['passed'] and bundle_src['passed'], 'Mismatch source/expected/installer'
    report.update({'passed':True,'publisher_generated_real_exe_sha256':hashlib.sha256(pathlib.Path(a.exe).read_bytes()).hexdigest(),
                   'installer_34_file_count':files['count'],'mode':files['mode'],'workbook_entry':files['entry'],'source_vs_expected':source_cmp,'exe_vs_expected':bundle_cmp,'exe_vs_source':bundle_src,
                   'four_chinese_templates':{name:next((x['sha256'] for x in files['files'] if x['relative_path']==name),None) for name in [
                       'DataTemplates/万芳人事数据.xlsx','DataTemplates/万芳员工任职合同历史.xlsx','DataTemplates/万芳员工扩展档案.xlsx','DataTemplates/招聘简报协调事项.xlsx']}})
    assert all(report['four_chinese_templates'].values())
except Exception as e:
    report.update({'passed':False,'error':repr(e)})
pathlib.Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False))
sys.exit(0 if report['passed'] else 3)