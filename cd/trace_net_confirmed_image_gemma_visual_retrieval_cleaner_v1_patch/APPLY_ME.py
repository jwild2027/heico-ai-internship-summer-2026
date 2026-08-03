#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
REPO = Path.cwd()

FILES = [
    "scripts/benchmark/visual/build_trace_net_confirmed_image_gemma_visual_retrieval_cleaner_v1.py",
    "tests/unit/test_trace_net_confirmed_image_gemma_visual_retrieval_cleaner_v1.py",
    "docs/trace_net_confirmed_image_gemma_visual_retrieval_cleaner_v1_README.md",
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

print("TRACE-Net confirmed image Gemma visual retrieval cleaner v1 patch applied.")
