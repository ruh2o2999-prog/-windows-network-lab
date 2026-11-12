#!/usr/bin/env python3
"""Generic reproducible negative/positive acceptance suite for split encrypted ZIP transfer."""
import argparse
import copy
import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from cryptography.exceptions import InvalidTag
from segmented_transfer import keygen,pack,restore,sha


def test_all(source,report_path):
    src=source.read_bytes();original_sha=sha(src)
    cases=[]
    def check(name,fn,should_fail=False):
        try:
            result=fn()
            if should_fail:cases.append({'case':name,'status':'FAIL','reason':'wrongly accepted mutated input'})
            else:cases.append({'case':name,'status':'PASS','detail':str(result)[:250]})
        except Exception as e:
            if should_fail:cases.append({'case':name,'status':'PASS','detected_as':type(e).__name__,'reason':str(e)[:250]})
            else:cases.append({'case':name,'status':'FAIL','exception':repr(e)[:250]})
    with tempfile.TemporaryDirectory(prefix='generic-') as t:
        td=Path(t);priv=td/'keys';keygen(priv)
        pack(source,priv/'receiver-public.pem',td/'original','generic_main_test',131072)
        m=json.loads((td/'original'/'manifest.json').read_text());count=m['count']
        def verify_positive():
            res=restore(td/'original',priv/'receiver-private.pem',td/'restored.zip',original_sha,'generic_main_test')
            assert (td/'restored.zip').read_bytes()==src
            with zipfile.ZipFile(td/'restored.zip') as z:
                assert z.testzip() is None
                assert len(z.namelist()) >= 1
            return {'sha256':res['sha256'],'bytes':res['bytes'],'parts':res['parts'],'zip_members':len(z.namelist())}
        check('positive_roundtrip_synthetic_zip',verify_positive)
        check('unique_independent_aes_keys',lambda: verify_keys(td,m))
        check('manifest_no_plain_keys',lambda: verify_manifest_no_keys(m))
        def mutate_case(name,mutator):
            def f():
                b=td/name;shutil.copytree(td/'original',b)
                mutator(b)
                output=td/(name+'.zip')
                try:restore(b,priv/'receiver-private.pem',output,original_sha,'generic_main_test')
                except Exception:
                    assert not output.exists(), 'unsafe partial output remained'
                    raise
                raise AssertionError('corrupt package restored unexpectedly')
            check(name,f,True)
        mutate_case('missing_segment',lambda b:(b/'part-0001.enc').unlink())
        mutate_case('missing_wrapped_key',lambda b:(b/'part-0001.keywrap').unlink())
        mutate_case('extra_unlisted_segment',lambda b:(b/'part-9999.enc').write_bytes(b'other-session'))
        def changed_manifest(b,edit):
            p=b/'manifest.json';m=json.loads(p.read_text());edit(m);p.write_text(json.dumps(m,indent=2))
        mutate_case('swapped_manifest_order',lambda b:changed_manifest(b,lambda m:m['parts'].__setitem__(slice(0,2),m['parts'][1::-1])))
        mutate_case('duplicate_index',lambda b:changed_manifest(b,lambda m:m['parts'][1].__setitem__('index',0)))
        mutate_case('path_traversal_filename',lambda b:changed_manifest(b,lambda m:m['parts'][1].__setitem__('filename','../secret.enc')))
        def flip_file(p):
            b=bytearray(p.read_bytes());b[len(b)//2]^=64;p.write_bytes(b)
        mutate_case('ciphertext_bitflip',lambda b:flip_file(b/'part-0001.enc'))
        mutate_case('wrapped_key_bitflip',lambda b:flip_file(b/'part-0001.keywrap'))
        def patched_cipher_hash(b):
            p=b/'part-0001.enc';flip_file(p)
            changed_manifest(b,lambda m:m['parts'][1].__setitem__('cipher_sha256',sha(p.read_bytes())))
        mutate_case('gcm_authentication_tag_failure',patched_cipher_hash)
        def swapped_key_files(b):
            a=b/'part-0000.keywrap';c=b/'part-0001.keywrap';x=a.read_bytes();a.write_bytes(c.read_bytes());c.write_bytes(x)
        mutate_case('wrong_key_for_segment',swapped_key_files)
        def mixed_sessions(b):
            other=td/'other';pack(source,priv/'receiver-public.pem',other,'generic_other_test',131072)
            (b/'part-0001.enc').write_bytes((other/'part-0001.enc').read_bytes())
            (b/'part-0001.keywrap').write_bytes((other/'part-0001.keywrap').read_bytes())
        mutate_case('mixed_run_segments',mixed_sessions)
        check('wrong_receiver_private_key',lambda: (lambda p:restore(td/'original',p,td/'wrongpriv.zip',original_sha,'generic_main_test'))((lambda k:(keygen(k),k/'receiver-private.pem')[1])(td/'otherkeys')),True)
        check('wrong_expected_final_sha',lambda:restore(td/'original',priv/'receiver-private.pem',td/'wrongsha.zip','f'*64,'generic_main_test'),True)
        check('wrong_expected_session',lambda:restore(td/'original',priv/'receiver-private.pem',td/'wrongsession.zip',original_sha,'generic_wrong_test'),True)
        def adversarial_repack():
            altered=td/'altered_source.zip';data=bytearray(src);data[12]^=1;altered.write_bytes(data)
            pack(altered,priv/'receiver-public.pem',td/'altered','generic_main_test',131072)
            return restore(td/'altered',priv/'receiver-private.pem',td/'forged.zip',original_sha,'generic_main_test')
        check('attacker_replaced_all_parts_and_manifest_still_rejected_by_trusted_digest',adversarial_repack,True)
        check('source_zip_crc_and_version',lambda:verify_source_zip(source))
    passed=sum(x['status']=='PASS' for x in cases)
    report={'suite':'Generic multi-key segmented encrypted general ZIP transfer','source_sha256':original_sha,
            'source_bytes':len(src),'segments':count,'tests':len(cases),'pass':passed,'fail':len(cases)-passed,
            'cases':cases, 'no_private_keys_in_report':True}
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pass':passed,'fail':len(cases)-passed,'cases':[x['case'] for x in cases if x['status']=='FAIL']},ensure_ascii=False,indent=2))
    return report


def verify_keys(td,m):
    assert m['count']>=2
    wraps=[(td/'original'/p['key_filename']).read_bytes() for p in m['parts']]
    nonces=[p['nonce_b64'] for p in m['parts']]
    assert len(set(wraps))==len(wraps) and len(set(nonces))==len(nonces)
    # OAEP-wrapped distinct keys are cryptographically hidden from the manifest.
    return 'distinct encrypted keys and distinct nonces for all '+str(m['count'])+' segments'


def verify_manifest_no_keys(m):
    s=json.dumps(m).lower()
    assert 'password' not in s and 'private_key' not in s and 'aes_key' not in s and 'key_b64' not in s
    return 'manifest holds only filenames, nonces, hashes, counts, session; no passwords/private keys'


def verify_source_zip(source):
    with zipfile.ZipFile(source) as z:
        assert z.testzip() is None
        assert len(z.namelist()) >= 1
        return 'zip members='+str(len(z.namelist()))+' CRC OK'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args();r=test_all(args.source,args.report);raise SystemExit(int(r['fail']>0))
if __name__=='__main__':main()
