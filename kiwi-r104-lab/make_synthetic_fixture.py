#!/usr/bin/env python3
"""Create public synthetic MV2 fixture, never reading the user's private plugin."""
import argparse,io,json,random,zipfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
r=random.Random(104)
a.out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(a.out,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('manifest.json',json.dumps({'manifest_version':2,'version':'0.0.0','name':'R104 Public Dummy'}))
    z.writestr('filler.bin',r.randbytes(530000))
print('PUBLIC_SYNTHETIC_ONLY',a.out.stat().st_size)
