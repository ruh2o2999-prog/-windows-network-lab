#!/usr/bin/env python3
# coding: utf-8
"""Read-only independent audit of the WFBND260/WFEND260 V6 installer payload.
Not a Windows installer emulator, not a substitute for executing the installer.
Uses documented binary layout from the V2.11.2.0 source as an historical protocol
reference; checks newer versions only when their V6 format remains compatible.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import unicodedata
import zipfile

HEADER_SIZE=2168
ENTRY_SIZE=48
FOOTER_SIZE=24
MAX_COUNT=4096
MAX_REL_UTF16=2048
MIN_PE_E_LFANEW=0x40
HEADER_MAGIC=b'WFBND260'
FOOTER_MAGIC=b'WFEND260'
QA_CANDIDATES={'RUN_P043_ALL_WIN7.cmd','RUN_P043_WIN7.cmd','RUN_P046_ALL_WIN7.cmd','RUN_P047_ALL_WIN7.cmd','RUN_P050_ALL_WIN7.cmd','RUN_P050_FORM_ONLY.cmd'}
WIN_BAD=re.compile(r'[<>:"/\\|?*\x00-\x1f]')
DEV_NAME=re.compile(r'^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$',re.I)

class AuditFailure(ValueError): pass

def validate_rel_path(s):
    if not s or s.startswith('/') or '\\' not in s and '/' not in s and s in ('..','.'): raise AuditFailure('relative path invalid')
    s=s.replace('\\','/')
    if s.startswith('/') or not s or s.endswith('/') or s.startswith('//'): raise AuditFailure('absolute or empty path')
    parts=s.split('/')
    if len(parts)>11:raise AuditFailure('over 10 nested levels')
    for part in parts:
        if not part or part in ('.','..') or part.strip()!=part or part.endswith('.') or WIN_BAD.search(part) or DEV_NAME.fullmatch(part):
            raise AuditFailure('Win32 unsafe relative component: '+repr(part))
    if unicodedata.normalize('NFC',s)!=s: raise AuditFailure('non canonical Unicode path')
    return '/'.join(parts)

def key_name(s):return unicodedata.normalize('NFC',s).casefold()

def sha_stream(file,size=None):
    digest=hashlib.sha256()
    while size is None or size:
        data=file.read(min(size,1048576) if size is not None else 1048576)
        if not data:
            if size is not None:raise AuditFailure('truncated payload content')
            break
        digest.update(data)
        if size is not None:size-=len(data)
    return digest.hexdigest()

def validate_pe(f):
    f.seek(0)
    if f.read(2)!=b'MZ':raise AuditFailure('missing MZ')
    f.seek(0x3c)
    pe_offset=struct.unpack('<I',f.read(4))[0]
    if not (MIN_PE_E_LFANEW <= pe_offset <= 4*1024*1024):raise AuditFailure('PE header offset out of bounds')
    f.seek(pe_offset)
    if f.read(4)!=b'PE\x00\x00':raise AuditFailure('missing PE signature')
    file_header=f.read(20)
    if len(file_header)!=20:raise AuditFailure('PE file header truncated')
    machine=struct.unpack_from('<H',file_header)[0]
    if machine!=0x8664:raise AuditFailure('not x64 PE')
    return pe_offset

def audit_exe(path):
    result=[];seen=set()
    with open(path,'rb') as f:
        pe_offset=validate_pe(f)
        f.seek(0,os.SEEK_END)
        file_length=f.tell()
        if file_length<FOOTER_SIZE+HEADER_SIZE:raise AuditFailure('PE too small for V6 payload')
        f.seek(file_length-FOOTER_SIZE)
        magic,start,length=struct.unpack('<8sQQ',f.read(FOOTER_SIZE))
        end=file_length-FOOTER_SIZE
        if magic!=FOOTER_MAGIC:raise AuditFailure('bad V6 footer magic')
        if start<=pe_offset or start+length!=end or length<HEADER_SIZE:raise AuditFailure('inconsistent footer offset or length')
        f.seek(start)
        hdr=f.read(HEADER_SIZE)
        if len(hdr)!=HEADER_SIZE or hdr[:8]!=HEADER_MAGIC:raise AuditFailure('bad V6 header')
        version,mode,count,flags=struct.unpack_from('<IIII',hdr,8)
        if version!=6 or mode not in (1,2,3) or not (1<=count<=MAX_COUNT):raise AuditFailure('invalid version/mode/file count')
        product=hdr[2008:2168].decode('utf-16le',errors='strict').split('\0')[0]
        if not product:raise AuditFailure('missing productId')
        excel=hdr[296:816].decode('utf-16le',errors='strict').split('\0')[0]
        for i in range(count):
            if f.tell()+ENTRY_SIZE>end:raise AuditFailure('entry truncated at index %d'%i)
            data=f.read(ENTRY_SIZE)
            chars,sz,digest=struct.unpack('<I4xQ32s',data)
            if not (1<=chars<=MAX_REL_UTF16) or sz>1024**3: raise AuditFailure('out-of-bounds filename/content at index %d'%i)
            if f.tell()+chars*2+sz > end:raise AuditFailure('entry contents exceed footer at index %d'%i)
            name=f.read(chars*2).decode('utf-16le','strict')
            name=validate_rel_path(name)
            casekey=key_name(name)
            if casekey in seen:raise AuditFailure('duplicate case-insensitive filename: '+name)
            seen.add(casekey)
            actual=sha_stream(f,sz)
            if actual!=digest.hex():raise AuditFailure('payload SHA256 mismatch at '+name)
            result.append(dict(relative_path=name,size_bytes=sz,sha256=actual))
        if f.tell()!=end:raise AuditFailure('unconsumed trailing bytes in payload')
    return {'pe_offset':pe_offset,'payload_start':start,'payload_length':length,'total_bytes':file_length,'mode':mode,'flags':flags,'entry':excel,'product_id':product,'count':count,'files':sorted(result,key=lambda x:key_name(x['relative_path']))}

def audit_zip(path,exclude_six=False):
    rows=[];seen=set()
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():continue
            name=validate_rel_path(info.filename)
            key=key_name(name)
            if key in seen:raise AuditFailure('ZIP duplicate/colliding path')
            seen.add(key)
            if ((info.external_attr>>16)&0o170000)==0o120000:raise AuditFailure('ZIP symlink entry')
            if exclude_six and name in QA_CANDIDATES:continue
            with z.open(info) as stream: digest=sha_stream(stream)
            rows.append(dict(relative_path=name,size_bytes=info.file_size,sha256=digest))
    return rows

def compare(actual,reference):
    amap={key_name(x['relative_path']):x for x in actual}
    rmap={key_name(x['relative_path']):x for x in reference}
    missing=sorted(rmap.keys()-amap.keys())
    unexpected=sorted(amap.keys()-rmap.keys())
    drift=[]
    for k in amap.keys()&rmap.keys():
        a,r=amap[k],rmap[k]
        if (a['relative_path']!=r['relative_path'] or a['size_bytes']!=r['size_bytes'] or a['sha256'].lower()!=r['sha256'].lower()):drift.append(k)
    return {'matched':len(amap.keys()&rmap.keys())-len(drift),'missing':missing,'unexpected':unexpected,'mismatch':sorted(drift),'passed':not(missing or unexpected or drift)}

def audit_directory(dir):
    root=Path(dir).resolve(strict=True)
    if not root.is_dir():raise AuditFailure('install path is not a folder')
    rows=[];seen=set()
    for current,ds,fs in os.walk(root,followlinks=False):
        for child in ds:
            if (Path(current)/child).is_symlink():raise AuditFailure('directory link in install tree: '+child)
        for child in fs:
            p=Path(current)/child
            if p.is_symlink() or not p.is_file():raise AuditFailure('file link/unexpected type in install tree: '+str(p))
            if not p.resolve().is_relative_to(root):raise AuditFailure('escaped install root')
            name=validate_rel_path(p.relative_to(root).as_posix())
            key=key_name(name)
            if key in seen:raise AuditFailure('case collision in installed tree')
            seen.add(key)
            with p.open('rb') as f:digest=sha_stream(f)
            rows.append(dict(relative_path=name,size_bytes=p.stat().st_size,sha256=digest))
    return rows

def run(args):
    report={'exe':str(args.exe),'evidence':'V6 PE payload static readback, NOT actual Windows install'}
    try:
        data=audit_exe(args.exe)
        report['pe']={k:v for k,v in data.items() if k!='files'}
        if args.source_zip:
            reference=audit_zip(args.source_zip,args.exclude_six_qa_cmd)
            report['source_zip_vs_exe']=compare(data['files'],reference)
        if args.installed_dir:
            report['exe_vs_disk']=compare(audit_directory(args.installed_dir),data['files'])
        report['passed']=all(v['passed'] for k,v in report.items() if k in ('source_zip_vs_exe','exe_vs_disk'))
    except (AuditFailure,ValueError,OSError,zipfile.BadZipFile,UnicodeDecodeError,struct.error) as exc:
        report['passed']=False; report['error']=str(exc)
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not args.quiet: print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 2

def main():
    p=argparse.ArgumentParser(description='对真实 Windows PE 安装器附加的 V6 包做独立只读回读；不执行安装。')
    p.add_argument('--exe',required=True)
    p.add_argument('--source-zip')
    p.add_argument('--exclude-six-qa-cmd',action='store_true')
    p.add_argument('--installed-dir')
    p.add_argument('--report-json')
    p.add_argument('--quiet',action='store_true')
    raise SystemExit(run(p.parse_args()))
if __name__=='__main__':main()