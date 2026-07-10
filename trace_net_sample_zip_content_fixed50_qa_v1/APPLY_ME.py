#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PATCH = Path(__file__).resolve().parent / "files"

for src in PATCH.rglob("*"):
    if src.is_dir():
        continue
    rel = src.relative_to(PATCH)
    dst = ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {dst.relative_to(ROOT)}")

print("APPLY COMPLETE: trace_net_sample_zip_content_fixed50_qa_v1")
