#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
REPO = Path.cwd()

FILES = [
    "scripts/build_trace_net_confirmed_image_page_summary_v1.py",
    "tests/unit/test_trace_net_confirmed_image_page_summary_v1.py",
    "docs/trace_net_confirmed_image_page_summary_v1_README.md",
]

for rel in FILES:
    src = ROOT / rel
    dst = REPO / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        print(f"already in place {rel}")
        continue
    shutil.copy2(src, dst)
    print(f"wrote {rel}")

print("TRACE-Net confirmed image page summary v1 patch applied.")
