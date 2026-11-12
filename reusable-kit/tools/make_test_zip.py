#!/usr/bin/env python3
"""Create deterministic, PUBLIC synthetic ZIP for crypto round-trip testing."""
import argparse, json, random, zipfile
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument("--out",required=True,type=Path)
args=ap.parse_args()
args.out.parent.mkdir(parents=True,exist_ok=True)
rng=random.Random(20261112)
with zipfile.ZipFile(args.out,"w",compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr("metadata.json",json.dumps({"kind":"synthetic-test-data","safe_to_publish":True}))
    z.writestr("random_test_bytes.bin",rng.randbytes(530000))
print("SYNTHETIC_ZIP_BYTES",args.out.stat().st_size)
