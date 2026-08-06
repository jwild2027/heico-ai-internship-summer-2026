#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
FILES = HERE / "files"

for src in FILES.rglob("*"):
    if src.is_file():
        rel = src.relative_to(FILES)
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"wrote {dst}")

print("TRACE-Net TIFF content Gemma evidence-pack router v3 patch applied.")
