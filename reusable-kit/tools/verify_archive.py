#!/usr/bin/env python3
"""Verify ZIP bytes, members, CRC and optional trusted SHA256 (not business semantics)."""
import argparse, hashlib, json, zipfile
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument("zip",type=Path)
ap.add_argument("--expected-sha256",default="")
args=ap.parse_args()
p=args.zip
digest=hashlib.sha256(p.read_bytes()).hexdigest()
with zipfile.ZipFile(p) as z:
    bad=z.testzip()
    members=z.namelist()
report={"filename":p.name,"bytes":p.stat().st_size,"sha256":digest,"entries":len(members),
        "crc_error":bad,"trusted_sha_match":(digest==args.expected_sha256 if args.expected_sha256 else None)}
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if bad is None and members and (not args.expected_sha256 or digest==args.expected_sha256) else 1)
