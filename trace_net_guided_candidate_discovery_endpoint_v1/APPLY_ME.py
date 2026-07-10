#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
DEST = ROOT.parent

for src in FILES.rglob("*"):
    if src.is_dir():
        continue
    rel = src.relative_to(FILES)
    dst = DEST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"copied {rel}")

print("APPLY_DONE trace_net_guided_candidate_discovery_endpoint_v1")
