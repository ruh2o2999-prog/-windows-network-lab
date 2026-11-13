#!/usr/bin/env python3
"""Original P050 Windows native failure->restore->retry evidence. No private paths in output."""
import argparse, hashlib, importlib.util, json, time, zipfile
from pathlib import Path
import winreg
from native_p050_gui import build, install

PUBLISHER_SHA = '7296ac884482caa4c31eef914099d19c3726dec658a891cdc9868890a8a19a90'
P050_SHA = 'a357affc922bcd43e59aa9ffd40652b51259c13af0f81cf1316008deb9720abc'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def ensure(key, passed):
    if not passed:
        raise AssertionError('FAILED_' + key)

def inventory(root):
    """Exclude backups and installer internals; include every user-visible program byte."""
    out = {}
    for p in root.rglob('*'):
        rel = p.relative_to(root).as_posix()
        parts = rel.split('/')
        if parts[0].casefold() == 'bak' or parts[0].startswith('._wf_new_'):
            continue
        if p.is_symlink():
            raise AssertionError('UNEXPECTED_REPARSE_ITEM')
        if p.is_dir():
            out['dir:' + rel] = ''
        elif p.is_file():
            out['file:' + rel] = sha(p)
        else:
            raise AssertionError('UNEXPECTED_INVENTORY_TYPE')
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--report-dir', type=Path, required=True)
    ap.add_argument('--verify-module', type=Path, required=True)
    args = ap.parse_args()
    root = args.input.resolve()
    out = args.report_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    publisher = root / 'publisher_v211210_original.exe'
    source = root / 'p050_original_34.zip'
    ensure('ORIGINAL_PUBLISHER_SHA', sha(publisher) == PUBLISHER_SHA)
    ensure('ORIGINAL_P050_SHA', sha(source) == P050_SHA)
    with zipfile.ZipFile(source) as z:
        ensure('P050_COUNT_CRC', len(z.namelist()) == 34 and z.testzip() is None)
    spec = importlib.util.spec_from_file_location('verify_payload', args.verify_module)
    vp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vp)
    target = root / 'P050_R9_App_Install'
    old = root / 'P050_R9_Original_34_Setup.exe'
    new = root / 'P050_R9_Excluded_28_Setup.exe'
    office = root / 'Office16'
    office.mkdir(parents=True, exist_ok=True)
    fake = office / 'EXCEL.EXE'
    fake.write_bytes(b'CI TEST ONLY - THIS IS NOT EXCEL')
    key = r'Software\Microsoft\Windows\CurrentVersion\App Paths\excel.exe'
    reg = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key)
    previous = None
    try:
        try:
            previous = winreg.QueryValueEx(reg, '')[0]
        except FileNotFoundError:
            pass
        winreg.SetValueEx(reg, '', 0, winreg.REG_SZ, str(fake))
        build(publisher, source, old, target, False, out/'build_old.json')
        build(publisher, source, new, target, True, out/'build_new.json')
        old_check = vp.verify(old, source_zip=source)
        new_check = vp.verify(new, source_zip=source)
        ensure('OLD_PACKAGE_BYTES', old_check['passed'] and old_check['payload_bytes_verified'] == 34)
        ensure('NEW_PACKAGE_BYTES', new_check['passed'] and new_check['payload_bytes_verified'] == 28)
        ensure('NEW_QA_PROOF', new_check['qa_proof_count'] == 6)
        install(old, out/'install_old.json', 34)
        ensure('OLD_INSTALLED_SHA', vp.verify(old, source_zip=source, installed_dir=target)['passed'])
        template = target/'DataTemplates'/'万芳人事数据.xlsx'
        ensure('TEMPLATE_EXISTS', template.is_file())
        original_template_hash = sha(template)
        saved_template = root/'_CI_R9_OUTSIDE_INSTALL_SAVED_TEMPLATE.xlsx'
        saved_template.write_bytes(template.read_bytes())
        template.unlink()
        template.mkdir()
        (template/'CI_R9_DIRECTORY_COLLISION_SENTINEL.bin').write_bytes(b'CI-R9-FAILURE-PROBE')
        # A directory where the new payload requires a file fails during the
        # real installer's preservation phase, after the dated backup begins.
        # This change is isolated to the disposable Windows runner.
        before = inventory(target)
        install_failed = False
        try:
            install(new, out/'install_expected_failure.json', 28)
        except Exception:
            install_failed = True
        ensure('INJECTED_NATIVE_INSTALL_FAILURE', install_failed)
        failure = json.loads((out/'install_expected_failure.json').read_text(encoding='utf8'))
        observed_code = failure.get('native_error_code')
        ensure('EXPECTED_NATIVE_FAILURE_3061', observed_code == 3061)
        ensure('RESTORED_LIVE_TREE_BYTE_IDENTICAL', inventory(target) == before)
        ensure('COLLISION_DIRECTORY_RESTORED', (template/'CI_R9_DIRECTORY_COLLISION_SENTINEL.bin').is_file())
        # The template source is restored outside the installer to return the
        # disposable test tree to its true original 34-file snapshot.
        (template/'CI_R9_DIRECTORY_COLLISION_SENTINEL.bin').unlink()
        template.rmdir()
        template.write_bytes(saved_template.read_bytes())
        ensure('ORIGINAL_TEMPLATE_REPAIRED_BYTE_EXACT', sha(template) == original_template_hash)
        ensure('ORIGINAL_34_LIVE_AFTER_FAILURE', vp.verify(old, source_zip=source, installed_dir=target)['passed'])
        (target/'Data').mkdir(exist_ok=True)
        data = target/'Data'/'CI_R9_USER_DATA_CANARY.bin'
        data.write_bytes(b'CI-R9-PRESERVE-USER-DATA')
        data_hash = sha(data)
        qas = new_check['qa_proof_entries']
        qa = target/qas[0]
        ensure('ORIGINAL_QA_PRESENT', qa.is_file())
        with qa.open('ab') as f:
            f.write(b'\r\nREM CI R9 USER MODIFIED\r\n')
        qa_hash = sha(qa)
        install(new, out/'install_retry_new.json', 28)
        backed = target/'bak'
        candidates = [p for p in backed.iterdir() if p.is_dir() and all((p/q).is_file() for q in qas)]
        ensure('RETRY_BACKUP_FOUND', bool(candidates))
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        after = vp.verify(new, source_zip=source, installed_dir=target, backup_dir=latest)
        ensure('RETRY_NEW_SHA_AND_BACKUP', after['passed'])
        ensure('USER_DATA_RETRY_BYTE_EXACT', sha(data) == data_hash)
        ensure('QA_USER_EDIT_RETRY_BYTE_EXACT', sha(qa) == qa_hash)
        summary = {
            'phase': 'P050-R9-native-fault-restore-and-retry',
            'status': 'PASS', 'source_original_p050_sha256': P050_SHA,
            'publisher_original_sha256': PUBLISHER_SHA,
            'old_count': 34, 'new_count': 28,
            'native_injected_failure_observed': True,
            'native_failure_code': observed_code,
            'failed_attempt_live_tree_restored_byte_identical': True,
            'successful_retry': True,
            'user_data_and_edited_qa_byte_exact': True,
            'real_office_installed': False,
            'win7_excel2013_tested': False,
            'power_loss_or_process_kill_tested': False,
            'formal_pub_items_closed': 0,
            'scope': 'windows-2022 native exception rollback for deterministic path-type collision only',
        }
        (out/'p050_r9_summary.json').write_text(json.dumps(summary,ensure_ascii=True,indent=2),encoding='utf8')
        print('P050_R9_NATIVE_ROLLBACK_AND_RETRY_PASS')
    finally:
        try:
            if previous is None:
                try:
                    winreg.DeleteValue(reg, '')
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(reg, '', 0, winreg.REG_SZ, previous)
        finally:
            winreg.CloseKey(reg)

if __name__ == '__main__':
    main()