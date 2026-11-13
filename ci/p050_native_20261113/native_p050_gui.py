#!/usr/bin/env python3
# coding: utf-8
"""P0-50 original input, V2.11.2.10 native Windows GUI acceptance.
Runs only in isolated CI runner. Outputs no original workbook bytes/paths.
No Office automation is claimed. All dialogs are PID scoped and exact-allowlisted.
"""
import argparse, ctypes, hashlib, json, os, subprocess, time
from pathlib import Path
from ctypes import wintypes

WM_COMMAND=0x111;WM_SETTEXT=0x000C;WM_GETTEXT=0x000D;BM_SETCHECK=0x00F1;BM_CLICK=0x00F5;BST_UNCHECKED=0
CB_SETCURSEL=0x014E;CBN_SELCHANGE=1;ID_BUILD=112;ID_SOURCE_MODE=125
u=ctypes.windll.user32
u.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];u.FindWindowW.restype=wintypes.HWND
u.GetDlgItem.argtypes=[wintypes.HWND,ctypes.c_int];u.GetDlgItem.restype=wintypes.HWND
u.IsWindowEnabled.argtypes=[wintypes.HWND];u.IsWindowEnabled.restype=wintypes.BOOL
u.IsWindow.argtypes=[wintypes.HWND];u.IsWindow.restype=wintypes.BOOL
u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
u.GetClassNameW.argtypes=[wintypes.HWND,ctypes.c_wchar_p,ctypes.c_int]
u.GetWindowTextW.argtypes=[wintypes.HWND,ctypes.c_wchar_p,ctypes.c_int]
u.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
u.SendMessageW.restype=wintypes.LPARAM
u.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
u.PostMessageW.restype=wintypes.BOOL
ENUM=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
u.EnumWindows.argtypes=[ENUM,wintypes.LPARAM]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def text(hwnd):
    b=ctypes.create_unicode_buffer(1000);u.GetWindowTextW(hwnd,b,len(b));return b.value

def pid_windows(pid):
    result=[]
    @ENUM
    def cb(h, _):
        owner=wintypes.DWORD(0);u.GetWindowThreadProcessId(h,ctypes.byref(owner))
        if owner.value==pid:
            b=ctypes.create_unicode_buffer(96);u.GetClassNameW(h,b,len(b))
            result.append((h,b.value,text(h)))
        return True
    u.EnumWindows(cb,0)
    return result

def setctrl(hwnd,cid,value):
    ch=u.GetDlgItem(hwnd,cid)
    if not ch:raise RuntimeError('MISSING_CHILD_'+str(cid))
    data=ctypes.create_unicode_buffer(str(value))
    u.SendMessageW(ch,WM_SETTEXT,0,ctypes.cast(data,ctypes.c_void_p).value)

def getctrl(hwnd,cid):
    child=u.GetDlgItem(hwnd,cid)
    if not child:return ''
    b=ctypes.create_unicode_buffer(500)
    u.SendMessageW(child,WM_GETTEXT,len(b),ctypes.cast(b,ctypes.c_void_p).value)
    return b.value

def command(hwnd,id):
    if not u.PostMessageW(hwnd,WM_COMMAND,id,0):raise RuntimeError('COMMAND_POST_FAILED_'+str(id))

def click_modal(hwnd, id):
    """Drive native HWND child button using the proven BM_CLICK route.

    Windows can publish a MessageBox caption before the IDOK/IDYES child
    control is fully created. That initialization race is NOT a product error.
    Wait a bounded interval for the exact button, require it enabled, then
    send BM_CLICK and independently require the dialog to disappear.
    """
    begin=time.monotonic();child=None
    while time.monotonic()-begin < 5:
        if not u.IsWindow(hwnd):raise RuntimeError('EXPECTED_MODAL_GONE_BEFORE_BUTTON_'+str(id))
        candidate=u.GetDlgItem(hwnd,id)
        if candidate and u.IsWindowEnabled(candidate):
            child=candidate;break
        time.sleep(.06)
    if not child:raise RuntimeError('NATIVE_EXPECTED_BUTTON_NOT_READY_'+str(id))
    if not u.PostMessageW(child,BM_CLICK,0,0):raise RuntimeError('NATIVE_BM_CLICK_POST_FAILED_'+str(id))
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        if not u.IsWindow(hwnd):return True
        time.sleep(.06)
    raise RuntimeError('NATIVE_BM_CLICK_NO_DIALOG_CLOSE_'+str(id))

def build(publisher,source,output,dir_target,remove_qa,report,timeout=185):
    r={'phase':'publisher','real_windows_native':True,'real_original_source':True,
       'publisher_sha256':sha(publisher),'source_zip_sha256':sha(source),'exclude_qa':remove_qa,
       'ui_main_found':False,'qa_dialog_seen':False,'qa_choice_sent':False,
       'qa_button_close_ack':False,
       'messages_seen':[],'exit_code':None,'generated_sha256':None,'generated_bytes':None,
       'complete':False,'no_office_business_claim':True}
    p=None; started=time.monotonic();last_progress=started
    try:
        p=subprocess.Popen([str(publisher)])
        main=None
        while time.monotonic()-started<25:
            main=next((h for h,c,t in pid_windows(p.pid) if c=='WorkPlatformPublisher'),None)
            if main:break
            time.sleep(.25)
        if not main:raise RuntimeError('NO_NATIVE_PUBLISHER_WINDOW')
        r['ui_main_found']=True
        setctrl(main,103,str(source));setctrl(main,105,'P050_CI_RealInput')
        setctrl(main,121,'P050_CI_RealInput');setctrl(main,106,'2.11.2.10-CI')
        setctrl(main,107,str(output))
        # Existing workbook + sibling runtime files, not build-from-source.
        u.SendMessageW(u.GetDlgItem(main,125),CB_SETCURSEL,2,0)
        u.SendMessageW(u.GetDlgItem(main,119),CB_SETCURSEL,2,0)
        command(main,125|(CBN_SELCHANGE<<16));command(main,119|(CBN_SELCHANGE<<16))
        setctrl(main,115,str(dir_target));command(main,115|(0x0300<<16))
        # The CI runner has no licensed Microsoft Excel; optional VBA gate disabled.
        u.SendMessageW(u.GetDlgItem(main,122),BM_SETCHECK,BST_UNCHECKED,0)
        if source.exists() and not output.exists():command(main,ID_BUILD)
        else:raise RuntimeError('INVALID_BUILD_INPUT_OR_EXISTING_OUTPUT')
        seen=set();sent=[]
        while time.monotonic()-started<timeout:
            if p.poll() is not None:raise RuntimeError('PUBLISHER_EXITED_BEFORE_OUTPUT')
            if output.exists() and output.stat().st_size>140000:
                # Wait for renderer / payload close and stable size.
                size=output.stat().st_size;time.sleep(1)
                if output.stat().st_size==size and not next((h for h,c,t in pid_windows(p.pid) if c=='#32770'),None):
                    r['complete']=True; r['generated_bytes']=size;r['generated_sha256']=sha(output);break
            for h,cl,title in pid_windows(p.pid):
                if cl!='#32770':continue
                key=(h,title)
                if key in seen:continue
                # Special native resource-preview dialog: button 6701/6702.
                if u.GetDlgItem(h,6701) and u.GetDlgItem(h,6702):
                    r['qa_dialog_seen']=True
                    id=6702 if remove_qa else 6701
                    if remove_qa and not bool(u.IsWindowEnabled(u.GetDlgItem(h,6702))):
                        raise RuntimeError('EXCLUSION_NOT_AVAILABLE_FOR_REAL_INPUT')
                    click_modal(h,id);r['qa_choice_sent']=True;r['qa_button_close_ack']=True;seen.add(key);sent.append('qa_'+str(id));r['messages_seen']=sent[:];continue
                # The resource preview sets its caption before creating child buttons.
                # Do not misclassify the short initialization interval as unknown.
                if title == '安装资源与依赖预览':
                    continue
                # Known message-box prompts. Response only to exact expected category.
                if title in ('确认免附加校验打包','资源分类','发布包内容预览','自动识别结果','生成完成'):
                    if title in ('确认免附加校验打包','自动识别结果'):id=6
                    elif title=='生成完成':id=1
                    elif title=='资源分类':id=6 if remove_qa else 7
                    else:id=6
                    click_modal(h,id);seen.add(key);sent.append('modal_'+title);r['messages_seen']=sent[:]
                elif title:
                    # Unknown modal is a blocker: no blind Yes-click.
                    raise RuntimeError('UNEXPECTED_NATIVE_MODAL_'+hashlib.sha256(title.encode()).hexdigest()[:12])
            time.sleep(.24)
        if not r['complete']:
            r['output_exists_after_timeout']=output.exists()
            r['output_size_after_timeout']=output.stat().st_size if output.exists() else None
            r['native_dialogs_after_timeout']=[{'class':cl,'title_sha12':hashlib.sha256(title.encode()).hexdigest()[:12],
                                                 'has_keep':bool(u.GetDlgItem(h,6701)),
                                                 'has_exclude':bool(u.GetDlgItem(h,6702))}
                                                for h,cl,title in pid_windows(p.pid) if cl=='#32770']
            # Only a bounded generic category; private status strings must not leak to a public artifact.
            status=getctrl(main,113)
            r['native_status_sha12']=hashlib.sha256(status.encode()).hexdigest()[:12]
            r['native_status_length']=len(status)
            raise TimeoutError('PUBLISHER_GENERATED_EXE_NOT_CONFIRMED')
        r['messages_seen']=sent
        if not r['qa_dialog_seen'] or not r['qa_choice_sent']:
            raise RuntimeError('NO_EXPLICIT_QA_CONSENT_DIALOG')
    except Exception as e:r['failure']=type(e).__name__+':'+str(e)[:135];raise
    finally:
        if p and p.poll() is None:
            u.PostMessageW(next((h for h,c,t in pid_windows(p.pid) if c=='WorkPlatformPublisher'),0),0x0010,0,0)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        r['exit_code']=p.returncode if p else None
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(r,ensure_ascii=True,indent=2),encoding='utf-8')
    return r

def install(exe,report,expected_count,timeout=145):
    r={'phase':'installer','native':True,'installer_sha256':sha(exe),'expected_count':expected_count,
       'main_window_seen':False,'install_clicked':False,'status_success_seen':False,
       'modal_failure':False,'exit_code':None,'complete':False}
    p=None;started=time.monotonic()
    try:
        p=subprocess.Popen([str(exe)])
        while time.monotonic()-started<timeout:
            if p.poll() is not None:
                r['exit_code']=p.returncode;break
            windows=pid_windows(p.pid)
            main=next((h for h,c,t in windows if c=='WorkPlatformInstaller'),None)
            if main:
                r['main_window_seen']=True
                if not r['install_clicked']:
                    command(main,203);r['install_clicked']=True
                status=getctrl(main,205)
                if '安装成功' in status or '完成' in status and '成功' in status:
                    r['status_success_seen']=True
                    command(main,203)
            for h,c,title in windows:
                if c=='#32770' and title:
                    r['modal_failure']=True
                    if title=='工作平台 · 安装失败':click_modal(h,1)
                    else:raise RuntimeError('UNKNOWN_INSTALL_DIALOG_'+hashlib.sha256(title.encode()).hexdigest()[:12])
            time.sleep(.28)
        if p.poll() is None:raise TimeoutError('NATIVE_INSTALLER_DID_NOT_EXIT')
        if p.returncode!=0:raise RuntimeError('INSTALLER_EXIT_'+str(p.returncode))
        if not r['main_window_seen'] or not r['install_clicked']:
            raise RuntimeError('NATIVE_INSTALL_UI_NOT_DRIVEN')
        r['complete']=True
    except Exception as e:r['failure']=type(e).__name__+':'+str(e)[:130];raise
    finally:
        if p and p.poll() is None:p.kill();p.wait(timeout=5)
        r['exit_code']=p.returncode if p else None
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(r,ensure_ascii=True,indent=2),encoding='utf-8')
    return r

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='phase',required=True)
    a=sub.add_parser('build');a.add_argument('--publisher',type=Path,required=True);a.add_argument('--source',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True);a.add_argument('--target',type=Path,required=True);a.add_argument('--qa',choices=['keep','exclude'],required=True);a.add_argument('--report',type=Path,required=True)
    a=sub.add_parser('install');a.add_argument('--exe',type=Path,required=True);a.add_argument('--expected-count',type=int,required=True);a.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    if args.phase=='build':build(args.publisher.resolve(),args.source.resolve(),args.output.resolve(),args.target.resolve(),args.qa=='exclude',args.report.resolve())
    else:install(args.exe.resolve(),args.report.resolve(),args.expected_count)
if __name__=='__main__':main()