#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Original P0-50 SOURCE-ONLY mode-three native Windows probe.

No Office license is installed on hosted Windows Server 2022. This probe
independently verifies source-only manifest/WSH preflight and drives the REAL
Win32 publisher in mode 3. A missing real Excel COM is recorded as BLOCKED,
not as a mode-three product success. Never publishes private files or paths.
"""
import argparse, ctypes, hashlib, json, os, subprocess, time, zipfile
from pathlib import Path
from ctypes import wintypes
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent/'p050_native_20261113'))
from native_p050_gui import pid_windows, u, setctrl, getctrl, command, click_modal, sha

PUBLISHER_SHA='17f0de94a5fc18d615ba5e9fb9051faf6ed21b994d8ad132a70e18f682d2f2a7'
# Placeholder replaced by workflow's explicit expected fixture SHA via argument.
WM_COMMAND=0x0111;WM_CLOSE=0x0010;BM_CLICK=0x00F5;BM_GETCHECK=0x00F0
CB_SETCURSEL=0x014E;CB_GETCURSEL=0x0147;CBN_SELCHANGE=1
MODE_THREE=3


def digest_bytes(b):return hashlib.sha256(b).hexdigest()

def ensure(label,cond):
    if not cond:raise AssertionError('P051_ASSERT_'+label)

def classify(txt):
    low=txt.casefold()
    if 'cannot start excel' in low or 'excel.application' in low or 'com error=429' in low:return 'MICROSOFT_EXCEL_COM_MISSING'
    if 'vbproject' in low or 'vba project' in low:return 'VBPROJECT_ACCESS_FAILURE'
    if 'manifest' in low or '清单' in low:return 'MANIFEST_FAILURE'
    if 'wscript' in low or 'cscript' in low or 'windows script host' in low:return 'WSH_FAILURE'
    if 'excel' in low:return 'EXCEL_STAGE_UNKNOWN'
    return 'UNCLASSIFIED'

def extract_verified(archive,out):
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        ensure('ZIP_CRC',z.testzip() is None)
        seen=set()
        for i in z.infolist():
            name=i.filename
            if i.is_dir():continue
            parts=name.replace('\\','/').split('/')
            ensure('SAFE_ZIP_RELATIVE',bool(name) and not name.startswith(('/','\\')) and not any(x in ('','.','..') for x in parts) and ':' not in name and '\\' not in name)
            ensure('CASEFOLD_UNIQUE',name.casefold() not in seen)
            seen.add(name.casefold())
            dest=out.joinpath(*parts);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read(i))
    return len(seen)

def run_native_publisher(publisher,source,output,report,seconds=165):
    r={'stage':'WIN2022_NATIVE_MODE3_SOURCE_ONLY','mode_selected':None,'main_window':False,
       'clicked_generate':False,'modal_title_hashes':[],'modal_categories':[],
       'excel_com_absent_on_host':True,'generated_exe_present':False,
       'mode3_excel_business_success':False,'native_started':False}
    proc=None;start=time.monotonic();seen=set();main=None
    try:
        proc=subprocess.Popen([str(publisher)])
        r['native_started']=True
        while time.monotonic()-start<30:
            main=next((h for h,c,_ in pid_windows(proc.pid) if c=='WorkPlatformPublisher' and all(u.GetDlgItem(h,k) for k in (103,105,106,107,112,115,119,122,125))),None)
            if main:break
            time.sleep(.10)
        ensure('PUBLISHER_GUI_READY',main is not None)
        r['main_window']=True
        setctrl(main,103,str(source));setctrl(main,105,'P055_Mode3_Integrated')
        setctrl(main,121,'P055_Mode3_Integrated')
        setctrl(main,106,'P051-probe');setctrl(main,107,str(output))
        install_target=output.parent/'P055_Native_Application'
        # Preset 2 = custom local installation path.
        u.SendMessageW(u.GetDlgItem(main,119),CB_SETCURSEL,2,0)
        command(main,119 | (CBN_SELCHANGE<<16))
        setctrl(main,115,str(install_target));command(main,115 | (0x0300<<16))
        u.SendMessageW(u.GetDlgItem(main,125),CB_SETCURSEL,MODE_THREE,0)
        command(main,125 | (CBN_SELCHANGE<<16))
        r['mode_selected']=int(u.SendMessageW(u.GetDlgItem(main,125),CB_GETCURSEL,0,0))
        ensure('MODE_THREE_ACTUALLY_SELECTED',r['mode_selected']==3)
        # Full verification must remain enabled: no emergency hash bypass.
        r['full_verification_checkbox_checked']=int(u.SendMessageW(u.GetDlgItem(main,122),BM_GETCHECK,0,0))==1
        ensure('FULL_VERIFICATION_NOT_BYPASSED',r['full_verification_checkbox_checked'])
        ensure('NO_PREEXISTING_INSTALLER_OUTPUT',not output.exists())
        command(main,112);r['clicked_generate']=True
        last_status=''
        while time.monotonic()-start<seconds:
            if proc.poll() is not None:break
            last_status=getctrl(main,113)
            for h,cl,title in pid_windows(proc.pid):
                if cl!='#32770' or not title:continue
                token=hashlib.sha256(title.encode('utf-8')).hexdigest()[:12]
                if token not in r['modal_title_hashes']:r['modal_title_hashes'].append(token)
                if title=='Excel 工程构建失败' or title=='自动识别失败':
                    # Text is only read in memory to classify; never exported.
                    body_parts=[]
                    for child_id in (65535,0,1001):
                        value=getctrl(h,child_id)
                        if value:body_parts.append(value)
                    category=classify(' '.join(body_parts) + ' '+last_status + ' '+title)
                    r['modal_categories'].append(category)
                    r['build_error_modal_seen']=True
                    try: click_modal(h,1)
                    except RuntimeError:pass
                    return r
                if 'P055离线模式三' in title:
                    r['experimental_p055_explicit_confirmation_seen']=True
                    click_modal(h,6)
                    continue
                if title=='确认免附加校验打包':
                    r['unexpected_emergency_confirmation']=True
                    raise AssertionError('FULL_VERIFY_WAS_UNEXPECTEDLY_DISABLED')
                if title=='生成完成':
                    r['build_success_modal_seen']=True
                    return r
                if title in ('安装资源与依赖预览','发布包内容预览','自动识别结果'):
                    r['modal_categories'].append('POST_BUILD_OR_CONFIRMATION_DIALOG')
                    if title=='自动识别结果':click_modal(h,6)
                    elif title=='安装资源与依赖预览' and u.GetDlgItem(h,6701):click_modal(h,6701)
                    else:click_modal(h,6)
            time.sleep(.12)
        r['process_exit_code_before_termination']=proc.poll()
        r['last_status_category']=classify(last_status)
        r['timeout_or_exit_before_terminal_modal']=True
        return r
    finally:
        r['generated_exe_present']=output.is_file() and output.stat().st_size>200000
        if proc and proc.poll() is None:
            if main:u.PostMessageW(main,WM_CLOSE,0,0)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def sanitized_publisher_diagnostics(exe):
    import re
    logs=sorted(exe.parent.glob('错误日志_*.txt'))
    if not logs:return {'log_found':False}
    txt=logs[-1].read_text(encoding='utf-16',errors='replace')
    probes={
        'entered_p055_native_stage':'P055离线VBA工程真实源码构建',
        'p055_engine_missing':'P055发布器内嵌构建引擎不存在',
        'p055_engine_hash_failure':'P055内嵌引擎SHA-256不一致',
        'p055_engine_extract_failure':'P055内嵌引擎解压失败',
        'p055_python_missing':'未找到可用python.exe',
        'p055_python_error':'P055_OFFLINE_BUILD_FAILED',
        'p055_python_step_error':'P055_OFFLINE_STEP_FAILED',
        'p055_python_input_error':'P055_OFFLINE_INVALID_MANIFEST',
        'p055_contract_stage':'构建后 build.mode',
        'p055_unverified_release_declined':'用户拒绝将尚未通过真实Excel业务验收',
        'existing_excel_com_stage':'受控 Excel 工程构建（无需 PowerShell）',
    }
    hits={code:needle in txt for code,needle in probes.items()}
    # Names and private paths are never exported; only controlled error types.
    error_tags=sorted(set(re.findall(r'P055_OFFLINE_[A-Z0-9_]{4,90}',txt)))
    exception_kinds=sorted(set(re.findall(r'(?<![A-Za-z])(?:FileNotFoundError|ModuleNotFoundError|RuntimeError|ValueError|KeyError|PermissionError|AssertionError|TypeError|UnicodeDecodeError|OSError|BadZipFile)(?=:)',txt)))
    # UTF-16 test log SHA proves the exact redacted classification has a stable source.
    return {'log_found':True,'last_log_sha256':hashlib.sha256(logs[-1].read_bytes()).hexdigest(),
            'classification':hits,'error_tags':error_tags[:12],
            'exception_kinds':exception_kinds,'log_bytes':logs[-1].stat().st_size}

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--input',required=True,type=Path)
    a.add_argument('--fixture-sha',required=True)
    a.add_argument('--report-dir',required=True,type=Path)
    x=a.parse_args();root=x.input.resolve();out=x.report_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    publisher=root/'publisher_p055.exe';source=root/'p055_sourceonly.zip'
    ensure('PUBLISHER_SHA',sha(publisher)==PUBLISHER_SHA)
    ensure('SOURCEONLY_ZIP_SHA',sha(source)==x.fixture_sha)
    extracted=root/'P051_Extracted_Input'
    count=extract_verified(source,extracted)
    ensure('SOURCE_ONLY_56_FILES',count==56)
    ensure('NO_EXISTING_XLSM',not any(extracted.rglob('*.xlsm')))
    cscript=Path(os.environ['SystemRoot'])/'System32'/'cscript.exe'
    ensure('NATIVE_WINDOWS_SCRIPT_HOST',cscript.is_file())
    preflight=subprocess.run([str(cscript),'//nologo',str(extracted/'windows/02_finalize_manifest.js'),str(extracted),'--preflight'],capture_output=True,text=True,errors='replace',timeout=90)
    status={'native_windows':True,'original_real_p050_business_source':True,'source_has_no_xlsm':True,
            'zip_count':count,'source_zip_sha256':x.fixture_sha,
            'publisher_sha256':PUBLISHER_SHA,'wsh_preflight_executed':True,
            'wsh_preflight_exit_code':preflight.returncode,
            'wsh_preflight_marker_seen':'MANIFEST_PREFLIGHT_OK' in (preflight.stdout+preflight.stderr),
            'excel2013_license_installed':False}
    (out/'source_preflight.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    ensure('WSH_PREFLIGHT_REAL_SOURCE',status['wsh_preflight_exit_code']==0 and status['wsh_preflight_marker_seen'])
    r=run_native_publisher(publisher,source,out/'P055_Install.exe',out/'publisher_mode3.json')
    (out/'p055_native_error_fingerprint.json').write_text(json.dumps(sanitized_publisher_diagnostics(publisher),indent=2),encoding='utf-8')
    result={'stage':'P0-51-native-source-to-XLSM','source_preflight_passed':True,
            'mode_three_selected':r['mode_selected']==3,'full_verification_kept':r['full_verification_checkbox_checked'],
            'build_error_modal_seen':r.get('build_error_modal_seen',False),
            'installed_microsoft_excel':False,'generated_installer':r['generated_exe_present'],
            'business_XLSM_generated_and_verified':False,
            'stage_status':'P055_PUBLISHER_MODE3_NATIVE_INTEGRATION_TEST_PENDING',
            'formal_PUB_Items_closed':0}
    (out/'p051_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('P055_NATIVE_MODE3_INTEGRATION_'+('EXE_CREATED' if result['generated_installer'] else 'NO_EXE'))
    # The no-Office run cannot mark the product passed, but the WSH preflight
    # and actual native GUI mode selection must be proven to count as evidence.
    ensure('REAL_MODE3_UI_SELECTED',result['mode_three_selected'])
    ensure('NO_FALSE_XLSM_SUCCESS',not result['business_XLSM_generated_and_verified'])
    ensure('P055_PUBLISHER_GENERATED_INSTALLER_EXE',result['generated_installer'])

if __name__=='__main__':main()