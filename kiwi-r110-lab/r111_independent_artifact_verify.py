#!/usr/bin/env python3
"""Verify actual Android R111 before/after ZIPs after CMS decryption, off runner.

The receiver private key is a local argument and must never be uploaded to CI.
No false PASS from a public manifest alone; independent SHA and R108 36-body
parity are checked against the genuine recovered file bytes.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys, zipfile
from tempfile import TemporaryDirectory

EXPECTED_NAMES = {
    'r111_secure_raw_exports/R111_android_real_before.zip.p7m',
    'r111_secure_raw_exports/R111_android_real_historical.zip.p7m',
    'r111_secure_raw_exports/R111_加密证据归档清单.json',
    'r111_secure_raw_exports/R111_独立双ZIP复核.json',
    'r103_export_zip_manifest.json',
    'r108_historical_real_download_manifest.json',
    'r109_pre_post_export_parity.json',
    'formal_package_provenance.json',
}

def sha_file(p):
    h = hashlib.sha256()
    with open(p,'rb') as f:
        for block in iter(lambda:f.read(65536), b''):h.update(block)
    return h.hexdigest()

def verify(artifact, private_key, certificate, output, verifier):
    artifact, private_key, certificate, output = map(Path,(artifact,private_key,certificate,output))
    if not private_key.is_file():raise ValueError('Local receiver PRIVATE key missing')
    if not artifact.is_file():raise ValueError('Actual Android GitHub artifact missing')
    with zipfile.ZipFile(artifact) as outer:
        names=set(outer.namelist())
        if outer.testzip() or not EXPECTED_NAMES.issubset(names) or len(outer.namelist())!=len(names):
            raise ValueError('Actual Android artifact incomplete, corrupt, or duplicated entries')
        manifest=json.loads(outer.read('r111_secure_raw_exports/R111_加密证据归档清单.json'))
        if manifest.get('result')!='PASS':raise ValueError('R111 business archive did not pass')
        if manifest.get('receiver_public_cert_sha256')!=sha_file(certificate):
            raise ValueError('Artifact recipient certificate fingerprint differs')
        rawmeta=[json.loads(outer.read(x)) for x in (
            'r103_export_zip_manifest.json','r108_historical_real_download_manifest.json')]
        with TemporaryDirectory(prefix='r111-private-') as tmp:
            td=Path(tmp); recovered=[]
            for tag,mt,expected in zip(('before','historical'),rawmeta,
                (manifest['before_original_export'],manifest['after_original_historical_export'])):
                encname='r111_secure_raw_exports/R111_android_real_'+tag+'.zip.p7m'
                encrypted=td/(tag+'.p7m');encrypted.write_bytes(outer.read(encname))
                info=manifest['encrypted_archive'][tag]
                if sha_file(encrypted)!=info['ciphertext_sha256'] or encrypted.stat().st_size!=info['ciphertext_bytes']:
                    raise ValueError('Public ciphertext SHA/byte count mismatch')
                target=td/(tag+'.zip')
                cmd=['openssl','cms','-decrypt','-binary','-inform','DER',
                    '-in',str(encrypted),'-recip',str(certificate),
                    '-inkey',str(private_key),'-out',str(target)]
                result=subprocess.run(cmd,capture_output=True,text=True)
                if result.returncode or not target.is_file():
                    raise ValueError('CMS private-key decryption failed')
                digest=sha_file(target)
                if digest!=expected['sha256'] or digest!=mt['sha256'] or target.stat().st_size != expected['bytes']:
                    raise ValueError('Decrypted actual Android ZIP SHA/size mismatch')
                with zipfile.ZipFile(target) as src:
                    if src.testzip() or len(src.namelist())!=expected['entries']:
                        raise ValueError('Decrypted actual Android ZIP CRC or entries mismatch')
                recovered.append(target)
            sys.path.insert(0,str(Path(verifier).resolve().parent))
            from r108_offline_recovery_parity import verify as parity_verify
            proof=parity_verify(*recovered,td/'proof.json')
            if proof['summary']!={'passed':5,'failed':0}:
                raise ValueError('Independent post-decryption parity failed')
            # Save raw bytes only into a private user-selected destination, NEVER public CI artifact.
            output.mkdir(parents=True,exist_ok=True)
            for tag,p in zip(('before','historical'),recovered):
                (output/('R111_真实Android_'+tag+'.zip')).write_bytes(p.read_bytes())
            conclusion={'status':'PASS','run_id':manifest['runner_id'],
                'source_plugin_sha256':json.loads(outer.read('formal_package_provenance.json'))['sha256'],
                'before_sha256':rawmeta[0]['sha256'],
                'after_sha256':rawmeta[1]['sha256'],
                'gates':proof['gates'],'result':'Both original Android export ZIPs independently decrypted, CRC checked, and 36/36 request/body parity proved',
                'private_archives_saved_in':str(output)}
            (output/'R111_离线独立复核.json').write_text(json.dumps(conclusion,ensure_ascii=False,indent=2),encoding='utf8')
            return conclusion

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('artifact','private-key','certificate','output','verifier'):p.add_argument('--'+k,required=True)
    a=p.parse_args()
    try:
        result=verify(a.artifact,a.private_key,a.certificate,a.output,a.verifier)
        print(json.dumps({k:v for k,v in result.items() if k!='gates'},ensure_ascii=False,indent=2))
    except Exception as e:
        print('R111_INDEPENDENT_VERIFY_FAIL '+str(e),file=sys.stderr)
        sys.exit(1)
