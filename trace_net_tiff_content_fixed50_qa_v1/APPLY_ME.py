#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path.cwd()
PATCH_ROOT = Path(__file__).resolve().parent
FILES_ROOT = PATCH_ROOT / "files"

for src in FILES_ROOT.rglob("*"):
    if not src.is_file():
        continue
    rel = src.relative_to(FILES_ROOT)
    dst = ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {dst.as_posix()}")
