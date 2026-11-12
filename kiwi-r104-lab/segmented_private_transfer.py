#!/usr/bin/env python3
"""R104: Per-segment AES-256-GCM + independent RSA-OAEP wrapped keys.

Public CI/repository receives ONLY manifest.json, .enc, .keywrap, cert.
Private key remains with ephemeral receiver. Manifest is metadata, NOT a secret.
Pin --expected-sha256 and --expected-session in receiver's trusted workflow.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION='kiwi-segmented-aesgcm-r104-v1'
HEX64=re.compile(r'^[0-9a-f]{64}$')
SESSION=re.compile(r'^[A-Za-z0-9_-]{6,80}$')


def sha(b): return hashlib.sha256(b).hexdigest()

def write_private_key(key, p):
    p.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    p.chmod(0o600)


def keygen(out):
    out.mkdir(parents=True,exist_ok=True)
    priv=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    write_private_key(priv,out/'receiver-private.pem')
    (out/'receiver-public.pem').write_bytes(priv.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    return {'key_size':3072,'private_path':str(out/'receiver-private.pem'),'public_path':str(out/'receiver-public.pem')}


def load_public(path):
    data=path.read_bytes()
    if b'BEGIN CERTIFICATE' in data: return x509.load_pem_x509_certificate(data).public_key()
    return serialization.load_pem_public_key(data)


def aad(session,index,total,total_sha,total_bytes):
    return json.dumps({'v':VERSION,'session':session,'index':index,'total':total,'sha256':total_sha,'bytes':total_bytes},sort_keys=True,separators=(',',':')).encode()


def pack(source,public_path,out,session,segment_size=131072):
    if not SESSION.fullmatch(session):raise ValueError('invalid session ID')
    if segment_size<4096 or segment_size>64*1024*1024:raise ValueError('segment size outside 4KiB..64MiB')
    src=source.read_bytes(); digest=sha(src); total=max(1,(len(src)+segment_size-1)//segment_size)
    pub=load_public(public_path)
    if not isinstance(pub,rsa.RSAPublicKey) or pub.key_size<3072:raise ValueError('need RSA-3072+ public key')
    if out.exists() and any(out.iterdir()):raise FileExistsError('output directory must be empty')
    out.mkdir(parents=True,exist_ok=True)
    records=[]; keys_for_test=[]
    for i in range(total):
        plain=src[i*segment_size:(i+1)*segment_size]
        key=AESGCM.generate_key(bit_length=256); nonce=os.urandom(12)
        encrypted=AESGCM(key).encrypt(nonce,plain,aad(session,i,total,digest,len(src)))
        wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
        name=f'part-{i:04d}.enc'; keyname=f'part-{i:04d}.keywrap'
        (out/name).write_bytes(encrypted)
        (out/keyname).write_bytes(wrapped)
        records.append({'index':i,'filename':name,'key_filename':keyname,'nonce_b64':base64.b64encode(nonce).decode(),
                        'plain_bytes':len(plain),'plain_sha256':sha(plain),'cipher_bytes':len(encrypted),
                        'cipher_sha256':sha(encrypted),'keywrap_sha256':sha(wrapped)})
        keys_for_test.append(sha(key))
    manifest={'schema':VERSION,'session':session,'segment_size':segment_size,'count':total,
              'source_bytes':len(src),'source_sha256':digest,'algorithms':{'payload':'AES-256-GCM','wrap':'RSA-OAEP-SHA256','nonce':'random-96-bit'},'parts':records}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'session':session,'parts':total,'source_sha256':digest,'source_bytes':len(src),
            'unique_keys':len(set(keys_for_test))==total,'bundle':str(out)}


def _load_manifest(bundle):
    m=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    if m.get('schema')!=VERSION:raise ValueError('wrong manifest schema')
    session=m.get('session');count=m.get('count')
    if not isinstance(session,str) or not SESSION.fullmatch(session):raise ValueError('invalid manifest session')
    if type(count) is not int or not 1<=count<=10000:raise ValueError('invalid count')
    if not isinstance(m.get('source_bytes'),int) or m['source_bytes']<0:raise ValueError('invalid source size')
    if not HEX64.fullmatch(m.get('source_sha256','')):raise ValueError('invalid source sha256')
    if not isinstance(m.get('parts'),list) or len(m['parts'])!=count:raise ValueError('missing/extra manifest parts')
    expected={'manifest.json'}
    for i,part in enumerate(m['parts']):
        if type(part.get('index')) is not int or part['index']!=i:raise ValueError('part sequence invalid/duplicated')
        for label,ext in [('filename','enc'),('key_filename','keywrap')]:
            desired=f'part-{i:04d}.{ext}'
            if part.get(label)!=desired:raise ValueError('part filename/order invalid')
            expected.add(desired)
        for k in ['plain_sha256','cipher_sha256','keywrap_sha256']:
            if not HEX64.fullmatch(part.get(k,'')):raise ValueError('invalid part checksum')
        if not isinstance(part.get('plain_bytes'),int) or part['plain_bytes']<0:raise ValueError('invalid part size')
        if not isinstance(part.get('cipher_bytes'),int) or part['cipher_bytes']!=part['plain_bytes']+16:raise ValueError('invalid encrypted size')
        if len(base64.b64decode(part.get('nonce_b64',''),validate=True))!=12:raise ValueError('invalid GCM nonce')
    if {p.name for p in bundle.iterdir() if p.is_file()}!=expected:raise ValueError('missing or extra files in bundle')
    if sum(x['plain_bytes'] for x in m['parts'])!=m['source_bytes']:raise ValueError('manifest total size mismatch')
    return m


def restore(bundle,private_path,out,expected_sha,expected_session):
    if not HEX64.fullmatch(expected_sha):raise ValueError('trusted expected_sha256 required')
    if not SESSION.fullmatch(expected_session):raise ValueError('trusted expected_session required')
    m=_load_manifest(bundle)
    if m['session']!=expected_session:raise ValueError('session does not match trusted session')
    if m['source_sha256']!=expected_sha:raise ValueError('source hash does not match trusted hash')
    key=serialization.load_pem_private_key(private_path.read_bytes(),password=None)
    if not isinstance(key,rsa.RSAPrivateKey):raise ValueError('receiver key is not RSA')
    out.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.r104-reassembly-',dir=out.parent)
    digest=hashlib.sha256();written=0
    try:
        with os.fdopen(fd,'wb') as f:
            for part in m['parts']:
                encrypted=(bundle/part['filename']).read_bytes()
                wrapped=(bundle/part['key_filename']).read_bytes()
                if len(encrypted)!=part['cipher_bytes'] or sha(encrypted)!=part['cipher_sha256']:raise ValueError('cipher data corrupted or wrong segment')
                if sha(wrapped)!=part['keywrap_sha256']:raise ValueError('wrapped key corrupted or wrong segment')
                k=key.decrypt(wrapped,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
                nonce=base64.b64decode(part['nonce_b64'],validate=True)
                plain=AESGCM(k).decrypt(nonce,encrypted,aad(m['session'],part['index'],m['count'],m['source_sha256'],m['source_bytes']))
                if len(plain)!=part['plain_bytes'] or sha(plain)!=part['plain_sha256']:raise ValueError('part plaintext mismatch')
                f.write(plain);digest.update(plain);written+=len(plain)
            f.flush();os.fsync(f.fileno())
        if digest.hexdigest()!=expected_sha or written!=m['source_bytes']:raise ValueError('final hash/size mismatch')
        os.replace(temporary,out)
        return {'session':m['session'],'parts':m['count'],'sha256':digest.hexdigest(),'bytes':written,'output':str(out)}
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='cmd',required=True)
    k=sub.add_parser('keygen');k.add_argument('--out',required=True,type=Path)
    p=sub.add_parser('pack');p.add_argument('--source',required=True,type=Path);p.add_argument('--public-key',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--session',required=True);p.add_argument('--segment-size',type=int,default=131072)
    r=sub.add_parser('restore');r.add_argument('--bundle',required=True,type=Path);r.add_argument('--private-key',required=True,type=Path);r.add_argument('--output',required=True,type=Path);r.add_argument('--expected-sha256',required=True);r.add_argument('--expected-session',required=True)
    a=ap.parse_args()
    if a.cmd=='keygen':result=keygen(a.out)
    elif a.cmd=='pack':result=pack(a.source,a.public_key,a.out,a.session,a.segment_size)
    else:result=restore(a.bundle,a.private_key,a.output,a.expected_sha256,a.expected_session)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
