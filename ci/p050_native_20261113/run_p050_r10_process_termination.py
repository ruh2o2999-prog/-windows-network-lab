#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R10: original P050 + original RC1 on native Windows, forced termination.

This is a *test driver*, not a replacement installer. It never modifies the
original publisher or its generated package. Original XLSM/EXE/ZIP and private
paths stay off public CI artifacts. Results are scoped to the observed phase.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import signal
import struct
import subprocess
import time
import zipfile
from pathlib import Path
import winreg

from native_p050_gui import build, install, pid_windows, u, command

PUBLISHER_SHA = '7296ac884482caa4c31eef914099d19c3726dec658a891cdc9868890a8a19a90'
P050_SHA = 'a357affc922bcd43e59aa9ffd40652b51259c13af0f81cf1316008deb9720abc'
PHASE_OFFSET = 8 + 2048 * 2 + 128 * 2  # WFRECOVERYV2, MAXP=2048, Windows WCHAR=2
MARKER = '__WF_fresh_recovery_v2.bin'
ABORTED = '__WF_中断部署暂存'
DATE_RE = re.compile(r'^\d{8}_\d{6}(?:_\d{1,4})?$')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for piece in iter(lambda: f.read(1024 * 1024), b''):
            h.update(piece)
    return h.hexdigest()


def check(tag, passed):
    if not passed:
        raise AssertionError('R10_ASSERT_' + tag)


def inventory(folder, skip_root_bak=False, skip_marker=False):
    out = {}
    folder = Path(folder)
    for p in folder.rglob('*'):
        rel = p.relative_to(folder).as_posix()
        if skip_root_bak and rel.split('/')[0].casefold() == 'bak':
            continue
        if skip_marker and (p.name.startswith('__WF_') or p.name.startswith('._wf_new_')):
            continue
        check('REPARSE_BLOCK', not p.is_symlink())
        if p.is_file():
            out['file:' + rel] = sha(p)
        elif p.is_dir():
            out['dir:' + rel] = ''
        else:
            raise AssertionError('R10_UNEXPECTED_FILE_TYPE')
    return out


def phase_from_marker(path):
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return None
    if len(data) != PHASE_OFFSET + 8 or data[:8] != b'WFREC02\0':
        return None
    value = struct.unpack_from('<I', data, PHASE_OFFSET)[0]
    return value if value in (0, 1, 2) else None


def find_marker(root):
    b = root / 'bak'
    if not b.exists():
        return None
    for archive in b.iterdir():
        if archive.is_dir() and DATE_RE.fullmatch(archive.name):
            marker = archive / MARKER
            phase = phase_from_marker(marker)
            if phase is not None:
                return archive, phase
    return None


def kill_in_phase(exe, root, desired, report, timeout=150):
    p = subprocess.Popen([str(exe)])
    start = time.monotonic()
    clicked = False
    hit = None
    observations = {'marker_phase_seen': {}, 'kill_requested': False}
    try:
        while time.monotonic() - start < timeout:
            if p.poll() is not None:
                raise RuntimeError('INSTALLER_EXITED_BEFORE_INJECTION')
            for hwnd, classname, _ in pid_windows(p.pid):
                if classname == 'WorkPlatformInstaller' and u.GetDlgItem(hwnd, 203) and u.GetDlgItem(hwnd, 205):
                    if not clicked:
                        command(hwnd, 203)
                        clicked = True
                    break
            if clicked:
                found = find_marker(root)
                if found:
                    archive, current = found
                    observations['marker_phase_seen'][str(current)] = True
                    # PRE_DEPLOY: archive contains old tree; root has only backup + stage.
                    # DEPLOY: new top-level synthetic entries have actually appeared.
                    canary_live = sum(1 for _ in root.glob('CI_R10_user_extra_*.bin'))
                    canary_backup = sum(1 for _ in archive.glob('CI_R10_user_extra_*.bin'))
                    if current == desired and canary_backup >= 1000 and (desired == 0 or canary_live > 0):
                        hit = (archive, current, canary_live, canary_backup)
                        check('PROCESS_RUNNING_AT_KILL', p.poll() is None)
                        # TerminateProcess is intentionally abrupt: no WM_CLOSE, no normal cleanup.
                        kh = ctypes.windll.kernel32
                        kh.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                        kh.TerminateProcess.restype = ctypes.c_int
                        check('FORCED_TERMINATEPROCESS', kh.TerminateProcess(int(p._handle), 0xDEAD) != 0)
                        observations['kill_requested'] = True
                        break
            time.sleep(.006)
        if hit is None:
            observations['injector_failure'] = 'TRANSACTION_PHASE_NOT_INTERCEPTED'
            observations['process_exit_code'] = p.poll()
            report.write_text(json.dumps(observations, indent=2), encoding='utf8')
        check('CHECKPOINT_OBSERVED', hit is not None)
    finally:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=15)
    archive, phase, live_count, backed_count = hit
    check('MARKER_PERSISTS_AFTER_KILL', phase_from_marker(archive / MARKER) == desired)
    observations.update({'native_exe_sha256': sha(exe), 'phase_at_termination': phase,
                         'canary_live_at_termination': live_count,
                         'canary_backup_at_termination': backed_count,
                         'process_exit_code': p.returncode,
                         'marker_persisted_after_kill': True})
    report.write_text(json.dumps(observations, indent=2), encoding='utf8')
    return archive, observations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--report-dir', type=Path, required=True)
    ap.add_argument('--verify-module', type=Path, required=True)
    ap.add_argument('--phase', choices=['backup', 'deploy'], default='deploy')
    ap.add_argument('--extra-files', type=int, default=1800)
    args = ap.parse_args()
    check('EXTRA_FILES_SAFE', 1000 <= args.extra_files <= 2500)
    private = args.input.resolve()
    out = args.report_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    pub = private / 'publisher_v211210_original.exe'
    source = private / 'p050_original_34.zip'
    check('ORIGINAL_PUBLISHER_SHA', sha(pub) == PUBLISHER_SHA)
    check('ORIGINAL_P050_SHA', sha(source) == P050_SHA)
    with zipfile.ZipFile(source) as f:
        check('ORIGINAL_34_CRC', len(f.namelist()) == 34 and f.testzip() is None)
    spec = importlib.util.spec_from_file_location('verify_payload', args.verify_module)
    vp = importlib.util.module_from_spec(spec); spec.loader.exec_module(vp)
    target = private / ('P050_R10_App_' + args.phase)
    old = private / ('P050_R10_Old34_' + args.phase + '.exe')
    new = private / ('P050_R10_New28_' + args.phase + '.exe')
    office = private / 'Office16'; office.mkdir(exist_ok=True)
    fake = office / 'EXCEL.EXE'; fake.write_bytes(b'CI TEST ONLY - NOT A REAL OFFICE PRODUCT')
    key = r'Software\Microsoft\Windows\CurrentVersion\App Paths\excel.exe'
    reg = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key)
    previous = None
    try:
        try:
            previous = winreg.QueryValueEx(reg, '')[0]
        except FileNotFoundError:
            pass
        winreg.SetValueEx(reg, '', 0, winreg.REG_SZ, str(fake))
        build(pub, source, old, target, False, out / 'build_old.json')
        build(pub, source, new, target, True, out / 'build_new.json')
        vr_old = vp.verify(old, source_zip=source)
        vr_new = vp.verify(new, source_zip=source)
        check('BUILD_OLD34', vr_old['passed'] and vr_old['payload_bytes_verified'] == 34)
        check('BUILD_NEW28', vr_new['passed'] and vr_new['payload_bytes_verified'] == 28 and vr_new['qa_proof_count'] == 6)
        install(old, out / 'install_old.json', 34)
        check('OLD_INSTALLED', vp.verify(old, source_zip=source, installed_dir=target)['passed'])
        # Isolated disposable runner only. The many user-owned files amplify the
        # backup/preservation/commit window without touching publisher/installer code.
        canaries = {}
        for i in range(args.extra_files):
            name = 'CI_R10_user_extra_%04d.bin' % i
            content = ('R10-PRESERVE-%04d|' % i).encode() + bytes([i % 251]) * 32
            (target / name).write_bytes(content)
            canaries[name] = hashlib.sha256(content).hexdigest()
        (target / 'Data').mkdir(exist_ok=True)
        user_data = target / 'Data' / 'R10_USER_DATA_CANARY.bin'
        user_data.write_bytes(b'CI-R10-PRIVATE-USER-PRESERVATION')
        original = inventory(target, skip_root_bak=True)
        desired = 0 if args.phase == 'backup' else 1
        archive, evidence = kill_in_phase(new, target, desired, out / 'kill_event.json')
        # The original prior to termination MUST be intact in the timestamped backup.
        # For phase0/phase1 the original moved tree is expected to be complete.
        actual = inventory(archive, skip_marker=True)
        for k, v in original.items():
            check('DATED_BACKUP_ORIGINAL_' + hashlib.sha256(k.encode()).hexdigest()[:8], actual.get(k) == v)
        before_restart = inventory(target)
        restart_failed = False
        try:
            install(new, out / 'restart_install.json', 28)
        except Exception:
            restart_failed = True
        marker_after = phase_from_marker(archive / MARKER)
        aborted_stage = (archive / ABORTED).is_dir()
        after_restart = inventory(target)
        if not restart_failed:
            check('AUTORECOVER_NO_PENDING', marker_after is None)
            check('AUTORECOVER_OLD_WORKTREE_PROTECTED', all(
                (target / k).is_file() and sha(target / k) == v for k, v in canaries.items()))
        else:
            # Fail-closed is safer than overwrite, but is NOT successful recovery.
            check('FAILCLOSED_NO_DATA_CHANGED', before_restart == after_restart)
            check('FAILCLOSED_PENDING_PRESERVED', marker_after == desired)
            check('FAILCLOSED_ARCHIVE_RETAINED', archive.is_dir())
        summary = {
            'phase': 'P050-R10-windows-process-termination',
            'status': 'AUTO_RECOVERED' if not restart_failed else 'FAIL_CLOSED_NOT_AUTO_RECOVERED',
            'acceptance_R10_full_auto_recovery': not restart_failed,
            'observation_phase': args.phase,
            'native_process_terminated_inside_transaction': True,
            'phase_marker_after_kill': desired,
            'old_34_and_extra_user_files_preserved_in_date_backup': True,
            'restart_installer_succeeded': not restart_failed,
            'restart_attempt_byte_preserving_if_blocked': restart_failed,
            'abandoned_stage_preserved': aborted_stage,
            'date_backup_name_valid': bool(DATE_RE.fullmatch(archive.name)),
            'original_publisher_sha256': PUBLISHER_SHA,
            'original_p050_sha256': P050_SHA,
            'office_installed': False,
            'win7_excel2013_tested': False,
            'formal_pub_items_closed': 0,
            'source_code_or_production_exe_modified': False,
            'r10_known_scope': 'real Windows process termination; power outage and Win7 remain separate',
        }
        check('DATE_BACKUP_NAME', summary['date_backup_name_valid'])
        (out / 'p050_r10_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
        print('P050_R10_NATIVE_MEASURED_' + summary['status'])
    finally:
        try:
            if previous is None:
                try: winreg.DeleteValue(reg, '')
                except FileNotFoundError: pass
            else: winreg.SetValueEx(reg, '', 0, winreg.REG_SZ, previous)
        finally:
            winreg.CloseKey(reg)

if __name__ == '__main__':
    main()