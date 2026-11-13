#!/usr/bin/env python3
# Native P050 encrypted-only Windows CI: no workbook content in logs or evidence.
import argparse, hashlib, importlib.util, json, os, shutil, sys, time, zipfile
from pathlib import Path
import winreg
from native_p050_gui import build,install

PUBLISHER_SHA='7296ac884482caa4c31eef914099d19c3726dec658a891cdc9868890a8a19a90'
P050_SHA='a357affc922bcd43e59aa9ffd40652b51259c13af0f81cf1316008deb9720abc'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ensure(name,cond):
    if not cond:raise RuntimeError('FAILED_'+name)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--report-dir',type=Path,required=True)
    ap.add_argument('--verify-module',type=Path,required=True);a=ap.parse_args()
    root=a.input.resolve();out=a.report_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    publisher=root/'publisher_v211210_original.exe';src=root/'p050_original_34.zip'
    ensure('ORIGINAL_PUBLISHER_SHA',sha(publisher)==PUBLISHER_SHA)
    ensure('ORIGINAL_P050_SHA',sha(src)==P050_SHA)
    with zipfile.ZipFile(src) as z:
        ensure('P050_34_NAMES',len(z.namelist())==34 and z.testzip() is None)
    sp=importlib.util.spec_from_file_location('original_verify_payload',a.verify_module)
    vp=importlib.util.module_from_spec(sp);sp.loader.exec_module(vp)
    target=root/'P050_App_Install';old=root/'P050_Original_34_Setup.exe';new=root/'P050_Excluded_28_Setup.exe'
    # This registry marker exercises only presence-dependent installer file handling.
    # It is NOT Microsoft Excel and is NEVER used to claim macro execution.
    marker=root/'CI_OFFICE_PRESENCE_MARKER.exe';marker.write_bytes(b'CI TEST ONLY: NOT MICROSOFT EXCEL')
    key=r'Software\Microsoft\Windows\CurrentVersion\App Paths\excel.exe';reg=winreg.CreateKey(winreg.HKEY_CURRENT_USER,key)
    before=None
    try:
        try:before=winreg.QueryValueEx(reg,'')[0]
        except FileNotFoundError:pass
        winreg.SetValueEx(reg,'',0,winreg.REG_SZ,str(marker))
        b1=build(publisher,src,old,target,False,out/'build_old.json')
        o=vp.verify(old,source_zip=src);ensure('OLD_34_PUBLISHER_PAYLOAD',o['passed'] and o['payload_bytes_verified']==34 and o['qa_proof_count']==0)
        b2=build(publisher,src,new,target,True,out/'build_new.json')
        n=vp.verify(new,source_zip=src)
        ensure('NEW_28_PUBLISHER_PAYLOAD',n['passed'] and n['payload_bytes_verified']==28 and n['qa_proof_count']==6)
        install(old,out/'install_old.json',34)
        old_verify=vp.verify(old,source_zip=src,installed_dir=target)
        ensure('OLD_NATIVE_34_ON_DISK',old_verify['passed'])
        qas=n['qa_proof_entries'];ensure('EXACT_6_QA',len(qas)==6)
        # Data is user-created, and one QA test file is user modified: both must survive upgrade.
        user_data=target/'Data'/'CI_USER_DATA_PRESERVE.bin';user_data.parent.mkdir(parents=True,exist_ok=True)
        user_data.write_bytes(b'P050-CI-DATA-CANARY-20261113')
        user_sha=sha(user_data)
        edited=target/qas[0];ensure('QA_FILE_EXISTS',edited.is_file())
        with edited.open('ab') as f:f.write(b'\r\nREM CI USER EDIT MUST BE PRESERVED\r\n')
        edited_sha=sha(edited)
        install(new,out/'install_new.json',28)
        backup_root=target/'bak';candidates=[]
        if backup_root.is_dir():
            for c in backup_root.iterdir():
                if c.is_dir() and all((c/q).is_file() for q in qas):candidates.append(c)
        ensure('DATED_BACKUP_FOUND',bool(candidates))
        latest=max(candidates,key=lambda p:p.stat().st_mtime)
        final=vp.verify(new,source_zip=src,installed_dir=target,backup_dir=latest)
        ensure('FINAL_ALL_SHA_AND_BACKUP',final['passed'])
        ensure('EDITED_QA_BYTE_EXACT',sha(edited)==edited_sha and len(final['qa_edited_retained'])==1)
        ensure('USER_DATA_BYTE_EXACT',sha(user_data)==user_sha)
        # All 34 names remain in dated backup, with exactly one intentional user edit.
        source_map=vp._check_zip(src)
        ensure('BACKUP_ALL_34_NAMES',all((latest/v[0]).is_file() for v in source_map.values()))
        for key,(name,_,digest) in source_map.items():
            expected=edited_sha if name.casefold()==qas[0].casefold() else digest
            ensure('BACKUP_ORIGINAL_OR_EDITED_HASH',sha(latest/name)==expected)
        
        summary={'test':'P050-V211210-REAL-NATIVE-34-TO-28','status':'PASS',
          'actual_windows_installer_2_runs':True,'original_publisher_sha256':PUBLISHER_SHA,
          'original_p050_sha256':P050_SHA,'old_count':34,'new_count':28,
          'excluded_qa_count':6,'user_modified_qa_retained':True,'user_data_retained':True,
          'real_excel_macro_tested':False,'test_only_office_path_shim':True,
          'native_ui_build_2_runs':True,'installer_exe_sha256':[sha(old),sha(new)],
          'archive_found':True,'independent_source_and_landing_sha':True,
          'issue_closure_scope':'native source/install/upgrade files ONLY; not Win7/Office/G5'}
        (out/'p050_real_windows_native_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
        print('P050_REAL_34_TO_28_NATIVE_ACCEPTANCE_PASS')
    finally:
        if before is None:
            try:winreg.DeleteValue(reg,'')
            except FileNotFoundError:pass
        else:winreg.SetValueEx(reg,'',0,winreg.REG_SZ,before)
        winreg.CloseKey(reg)
if __name__=='__main__':main()