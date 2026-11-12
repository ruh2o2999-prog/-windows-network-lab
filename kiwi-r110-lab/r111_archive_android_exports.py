#!/usr/bin/env python3
"""R111: fail-closed private archiving of TWO genuine Kiwi Android export ZIPs.

The original archive bytes are NEVER placed in public GitHub artifacts. The
archive may run only after real R110 Android business gates pass. The receiver
private key is generated outside GitHub and is NEVER committed or logged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

REQUIRED_GATES = (
    'A7f_export_zip_content_verified',
    'R109_01_formal_pre_restart_36_requests',
    'R109_02_real_force_stop',
    'R109_03_new_original_kiwi_process',
    'R109_04_original_extension_panel_opens',
    'R109_06_original_history_export_clicked',
    'R109_07_historic_zip_real_adb_pull',
    'R108_11_same_original_capture_session',
    'R108_12_no_request_loss_or_duplication',
    'R108_13_cdp_body_byte_identity',
    'R108_14_task_remains_closed',
    'R108_15_original_zip_independently_readable',
)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_zip(path, recorded):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Original Android export ZIP missing: {path}')
    size = path.stat().st_size
    if not (100 < size < 50_000_000):
        raise ValueError(f'Unexpected real Android ZIP byte count: {size}')
    actual = sha_file(path)
    if recorded.get('sha256') != actual or recorded.get('bytes') != size:
        raise ValueError('Raw ZIP mismatches the independent Android download manifest')
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if z.testzip() is not None or len(names) != len(set(names)):
            raise ValueError('ZIP CRC error or duplicate member')
        if len(names) != recorded.get('entries', recorded.get('members')):
            raise ValueError('ZIP member count mismatches Android manifest')
        total = 0
        for info in z.infolist():
            name = info.filename
            if name.startswith('/') or name.startswith('../') or '/..' in '/' + name or '\\' in name:
                raise ValueError('Path traversal in original export ZIP')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symlink in original ZIP')
            total += info.file_size
            if total > 70_000_000:
                raise ValueError('Uncompressed archive size limit exceeded')
    return {'sha256': actual, 'bytes': size, 'entries': len(names)}


def run_archive(before, after, out, cert, expected_cert_sha, status, before_manifest,
                after_manifest, run_id, verifier_module):
    out = Path(out)
    before, after, cert = map(Path, (before, after, cert))
    expected_cert_sha = expected_cert_sha.lower().strip()
    if not (len(expected_cert_sha) == 64 and all(c in '0123456789abcdef' for c in expected_cert_sha)):
        raise ValueError('Expected pinned certificate SHA256 is invalid')
    if sha_file(cert) != expected_cert_sha:
        raise ValueError('Receiver certificate is NOT the pinned independent trusted certificate')
    proc = subprocess.run(['openssl', 'x509', '-noout', '-in', str(cert)], capture_output=True, text=True)
    if proc.returncode:
        raise ValueError('Invalid receiver X509 certificate')
    gates = load_json(status)['gates']
    incomplete = {g: gates.get(g, {}).get('status', 'NOT_RUN') for g in REQUIRED_GATES
                  if gates.get(g, {}).get('status') != 'PASS'}
    if incomplete:
        raise ValueError('Authentic Android G4 gates not all PASS: ' + json.dumps(incomplete))
    before_meta = verify_zip(before, load_json(before_manifest))
    after_meta = verify_zip(after, load_json(after_manifest))
    sys.path.insert(0, str(Path(verifier_module).resolve().parent))
    from r108_offline_recovery_parity import verify
    out.mkdir(parents=True, exist_ok=True)
    parity_path = out / 'R111_独立双ZIP复核.json'
    parity = verify(before, after, parity_path)
    expected = {
        'R108_11_same_original_capture_session',
        'R108_12_no_request_loss_or_duplication',
        'R108_13_cdp_body_byte_identity',
        'R108_14_task_remains_closed',
        'R108_15_original_zip_independently_readable',
    }
    if set(parity['gates']) != expected or any(g['status'] != 'PASS' for g in parity['gates'].values()):
        parity_path.unlink(missing_ok=True)
        raise ValueError('Independent original pre/post ZIP business parity failed')
    # All checks above occur BEFORE writing ciphertext. Never copy raw export into out/.
    encrypted = {}
    for tag, source in (('before', before), ('historical', after)):
        enc = out / ('R111_android_real_' + tag + '.zip.p7m')
        proc = subprocess.run([
            'openssl', 'cms', '-encrypt', '-binary', '-outform', 'DER',
            '-aes-256-cbc', '-in', str(source), '-out', str(enc), str(cert)
        ], capture_output=True, text=True)
        if proc.returncode:
            enc.unlink(missing_ok=True)
            raise RuntimeError('OpenSSL receiver encryption failed: ' + proc.stderr[:400])
        encrypted[tag] = {'file': enc.name, 'ciphertext_sha256': sha_file(enc),
                          'ciphertext_bytes': enc.stat().st_size}
    report = {
        'scope': 'R111 controlled localhost synthetic content, REAL Android Kiwi output',
        'result': 'PASS', 'runner_id': str(run_id), 'receiver_public_cert_sha256': expected_cert_sha,
        'before_original_export': before_meta, 'after_original_historical_export': after_meta,
        'encrypted_archive': encrypted, 'parity': parity['summary'],
        'disclosure': 'Original Android ZIP byte streams exist ONLY as CMS ciphertext in CI artifact; receiver private key is outside CI.',
    }
    (out / 'R111_加密证据归档清单.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for key in ('before', 'after', 'out', 'cert', 'expected-cert-sha', 'status',
                'before-manifest', 'after-manifest', 'verifier'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID', 'LOCAL'))
    a = p.parse_args()
    try:
        result = run_archive(a.before, a.after, a.out, a.cert,
                             a.expected_cert_sha, a.status, a.before_manifest,
                             a.after_manifest, a.run_id, a.verifier)
        print('R111_REAL_EXPORT_ARCHIVE', json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as e:
        print('R111_REAL_EXPORT_ARCHIVE_FAIL', str(e), file=sys.stderr, flush=True)
        sys.exit(1)
