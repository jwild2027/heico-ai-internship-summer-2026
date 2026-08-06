#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
TARGET = Path.cwd()

if not FILES.exists():
    raise SystemExit(f"Missing files directory: {FILES}")

for src in FILES.rglob("*"):
    if src.is_dir():
        continue
    rel = src.relative_to(FILES)
    dst = TARGET / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {dst}")

print("apply_status=PASS")
