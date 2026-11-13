#!/usr/bin/env python3
"""Read-only V6 publisher installation-EXE payload verifier.

Reads the documented WFHEADER/WFENTRY/WFEND layout from actual C source.
Does NOT execute EXE, VBS, CMD or PowerShell. Both input and output files
are opened read-only; separate Windows installation tests remain necessary.
"""
import argparse
import hashlib
import json
import struct
import zipfile
import re
from pathlib import Path, PureWindowsPath

HEADER_SIZE=2168
ENTRY_SIZE=48
END_SIZE=24
MAGIC_END=b'WFEND260'
MAGIC_BUNDLE=b'WFBND260'
QA_FLAG=128
QA_MAGIC=b'WFQAEX01'
QA_MAX_COUNT=48
QA_ENTRY_SIZE=552

class InvalidPayload(ValueError):pass

def _normal(path):
    path=path.replace('/','\\')
    p=PureWindowsPath(path)
    if not path or path.startswith(('\\','/')) or p.is_absolute() or ':' in path or any(x in ('','.','..') for x in path.split('\\')):
        raise InvalidPayload('invalid relative name: '+repr(path))
    return path.replace('\\','/')

def _qa_name_ok(name):
    """Conservative companion to production wf_qa_metadata_name_ok.

    QA omission is restricted to top-level stage-test batch launchers; this is
    not a generic obsolete-file deletion mechanism.
    """
    if not (13 <= len(name) < 260) or '/' in name or '\\' in name or ':' in name or '..' in name:
        return False
    if not re.match(r'(?i)^RUN_P[0-9]{2,4}_[^/\\:]+\.(cmd|bat)$', name):
        return False
    return name.casefold().endswith(('_win7.cmd','_win7.bat','_form_only.cmd','_form_only.bat'))

def _qa_proof_from_stream(file, flags, mode, payload_names, body_end):
    if not (flags & QA_FLAG):
        return {}
    if mode != 3:
        raise InvalidPayload('QA exclusion proof requires multifile mode')
    pos=file.tell()
    if pos + 16 > body_end:
        raise InvalidPayload('truncated QA proof header')
    magic,version,count=struct.unpack('<8sII',file.read(16))
    if magic!=QA_MAGIC or version!=1 or not (1 <= count <= QA_MAX_COUNT):
        raise InvalidPayload('invalid QA proof header')
    if file.tell() + QA_ENTRY_SIZE * count > body_end:
        raise InvalidPayload('truncated QA proof entries')
    results={}
    for _ in range(count):
        raw=file.read(QA_ENTRY_SIZE)
        name=raw[:520].decode('utf-16le').split('\x00',1)[0]
        digest=raw[520:].hex()
        if not _qa_name_ok(name) or not any(raw[2*i:2*i+2]==b'\x00\x00' for i in range(260)):
            raise InvalidPayload('invalid QA proof path or missing terminator')
        key=name.casefold()
        if key in results or key in payload_names or digest=='00'*32:
            raise InvalidPayload('duplicate/contained/zero-hash QA proof entry')
        results[key]=(name,digest)
    return results

def _check_zip(z):
    seen={}
    with zipfile.ZipFile(z) as f:
        for item in f.infolist():
            if item.is_dir():continue
            key=_normal(item.filename)
            if key.casefold() in seen:raise InvalidPayload('ZIP duplicate relative path: '+key)
            raw=f.read(item)
            seen[key.casefold()]=(key,len(raw),hashlib.sha256(raw).hexdigest())
    return seen

def _check_frozen_tsv(path):
    """Read a verified publisher run's UTF-16LE exact inventory.

    Each path, byte size, and SHA-256 is an immutable expectation from the
    packaging attempt, not a historical version pin or a VBA quality gate.
    """
    p=Path(path)
    raw=p.read_bytes()
    if not raw.startswith(b'\xff\xfe'):
        raise InvalidPayload('frozen manifest must use UTF-16LE BOM')
    rows={}
    for line in raw.decode('utf-16').splitlines():
        if not line or line.startswith('#'):continue
        parts=line.split('\t')
        if len(parts)!=3:raise InvalidPayload('invalid snapshot record: '+line[:60])
        name,size,digest=parts
        key=_normal(name).casefold()
        if key in rows:raise InvalidPayload('duplicate snapshot record: '+name)
        if not size.isdecimal() or len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest):
            raise InvalidPayload('invalid size or SHA-256 in snapshot: '+name)
        rows[key]=(_normal(name),int(size),digest)
    if not rows:raise InvalidPayload('frozen snapshot is empty')
    return rows

def verify(exe,source_zip=None,installed_dir=None,expected_manifest=None,backup_dir=None):
    exe=Path(exe)
    with exe.open('rb') as file:
        file.seek(0,2);length=file.tell()
        if length < HEADER_SIZE+END_SIZE:raise InvalidPayload('no V6 payload footer')
        file.seek(length-END_SIZE)
        marker,start,body_size=struct.unpack('<8sQQ',file.read(END_SIZE))
        if marker!=MAGIC_END or start+body_size+END_SIZE!=length or body_size<HEADER_SIZE:
            raise InvalidPayload('invalid V6 payload offset or length')
        file.seek(start);header=file.read(HEADER_SIZE)
        if header[:8]!=MAGIC_BUNDLE:raise InvalidPayload('bad payload header')
        version,mode,count,flags=struct.unpack_from('<IIII',header,8)
        if version!=6 or mode not in (2,3) or not (1<=count<=4096):raise InvalidPayload('unsupported payload metadata')
        entry=header[296:816].decode('utf-16le').split('\0',1)[0]
        expected={}
        for i in range(count):
            at=file.tell()
            if at+ENTRY_SIZE>length-END_SIZE:raise InvalidPayload('entry beyond footer')
            meta=file.read(ENTRY_SIZE)
            chars=struct.unpack_from('<I',meta,0)[0]
            size=struct.unpack_from('<Q',meta,8)[0]
            sha=meta[16:48].hex()
            if not (1<=chars<=800) or size>1024**3:raise InvalidPayload('invalid entry dimensions')
            name=_normal(file.read(chars*2).decode('utf-16le'))
            key=name.casefold()
            if key in expected:raise InvalidPayload('duplicate payload entry: '+name)
            digest=hashlib.sha256()
            remain=size
            while remain:
                piece=file.read(min(remain,1024*1024))
                if not piece:raise InvalidPayload('truncated payload stream')
                digest.update(piece);remain-=len(piece)
            if digest.hexdigest()!=sha:raise InvalidPayload('corrupt payload bytes: '+name)
            expected[key]=(name,size,sha)
        proof=_qa_proof_from_stream(file, flags, mode, expected, length-END_SIZE)
        if file.tell()!=length-END_SIZE:raise InvalidPayload('payload has unexpected trailing bytes')
    if mode==3 and entry and _normal(entry).casefold() not in expected:
        raise InvalidPayload('main workbook entry absent from multifile payload')
    if mode==2 and count!=1:raise InvalidPayload('single-workbook mode has more than one file')
    missing=[];different=[];additional=[];bad_qa_source=[]
    if source_zip:
        source=_check_zip(source_zip)
        for k,v in source.items():
            if k not in expected:
                if k in proof:
                    if proof[k][1]!=v[2]:bad_qa_source.append(v[0])
                else:missing.append(v[0])
            elif (v[1],v[2])!=(expected[k][1],expected[k][2]):different.append(v[0])
        additional=[v[0] for k,v in expected.items() if k not in source]
        for key,(name,_) in proof.items():
            if key not in source:bad_qa_source.append(name)
    missing_snapshot=[];modified_snapshot=[];extra_snapshot=[]
    if expected_manifest:
        snapshot=_check_frozen_tsv(expected_manifest)
        for k,v in snapshot.items():
            if k not in expected:missing_snapshot.append(v[0])
            elif (v[1],v[2])!=(expected[k][1],expected[k][2]):modified_snapshot.append(v[0])
        extra_snapshot=[v[0] for k,v in expected.items() if k not in snapshot]
    installed_bad=[];old_qa_remaining=[];edited_qa_retained=[];qa_unsafe=[];backup_missing=[];backup_edits_not_preserved=[];backup_seen=0
    if installed_dir:
        root=Path(installed_dir)
        for _,(name,sz,sha) in expected.items():
            target=root.joinpath(*name.split('/'))
            # No symlink traversal when validating an installed Windows tree.
            try:
                current=root
                if root.is_symlink():raise OSError('install root is a link')
                for part in name.split('/'):
                    current=current/part
                    if current.is_symlink():raise OSError('linked deployment path')
                good=(target.is_file() and target.stat().st_size==sz and
                      hashlib.sha256(target.read_bytes()).hexdigest()==sha)
            except (OSError,ValueError):good=False
            if not good:installed_bad.append(name)
    # Verify the unchanged old QA files disappear from the live tree; edits
    # must survive and remain byte-identical to the dated backup when supplied.
    if backup_dir and not installed_dir:
        raise InvalidPayload('backup verification requires installed_dir')
    for key,(name,source_digest) in proof.items():
        live=Path(installed_dir)/name if installed_dir else None
        prior=Path(backup_dir)/name if backup_dir else None
        if prior:
            if prior.is_symlink() or not prior.is_file():
                backup_missing.append(name)
                continue
            backup_seen+=1
            before_digest=hashlib.sha256(prior.read_bytes()).hexdigest()
            if before_digest==source_digest:
                if live and (live.exists() or live.is_symlink()):
                    old_qa_remaining.append(name)
            else:
                if live is None or live.is_symlink() or not live.is_file():
                    backup_edits_not_preserved.append(name)
                elif hashlib.sha256(live.read_bytes()).hexdigest()!=before_digest:
                    backup_edits_not_preserved.append(name)
                else:
                    edited_qa_retained.append(name)
        elif live and (live.exists() or live.is_symlink()):
            if live.is_symlink() or not live.is_file():qa_unsafe.append(name)
            elif hashlib.sha256(live.read_bytes()).hexdigest()==source_digest:
                old_qa_remaining.append(name)
            else:edited_qa_retained.append(name)
    return {'payload_bytes_verified':count,'payload_mode':mode,'main_entry':entry,
            'payload_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
            'qa_proof_count':len(proof),
            'qa_proof_entries':[v[0] for v in proof.values()],
            'qa_proof_source_mismatch':sorted(bad_qa_source),
            'qa_remaining_unchanged_live':sorted(old_qa_remaining),
            'qa_edited_retained':sorted(edited_qa_retained),
            'qa_unsafe_live':sorted(qa_unsafe),
            'qa_backup_missing':sorted(backup_missing),
            'qa_backup_entries_verified':backup_seen,
            'qa_backup_edited_not_preserved':sorted(backup_edits_not_preserved),
            'missing_from_payload':missing,'different_from_input':different,
            'new_generated_files':additional,
            'missing_or_altered_after_install':installed_bad,
            'missing_from_snapshot':missing_snapshot,
            'altered_from_snapshot':modified_snapshot,
            'unexpected_in_payload':extra_snapshot,
            'passed':not any((missing,different,installed_bad,missing_snapshot,modified_snapshot,extra_snapshot,bad_qa_source,old_qa_remaining,qa_unsafe,backup_missing,backup_edits_not_preserved))}

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('installer_exe',help='Windows publisher generated INSTALLER EXE (not publisher itself)')
    a.add_argument('--source-zip',help='original ZIP for complete source-to-payload comparison')
    a.add_argument('--installed-dir',help='installed application root for on-disk verification')
    a.add_argument('--manifest',help='V2.11.2.8 frozen UTF-16LE deployment snapshot TSV')
    a.add_argument('--backup-dir',help='dated backup directory from an actual Windows upgrade')
    p=a.parse_args()
    try:
        result=verify(p.installer_exe,p.source_zip,p.installed_dir,p.manifest,p.backup_dir)
    except Exception as error:
        result={'passed':False,'error':str(error)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['passed'] else 2)