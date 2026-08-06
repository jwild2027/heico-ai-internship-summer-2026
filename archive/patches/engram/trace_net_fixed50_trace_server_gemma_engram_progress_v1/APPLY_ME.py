from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
REPO = Path.cwd()

for src in FILES.rglob("*"):
    if src.is_dir():
        continue
    rel = src.relative_to(FILES)
    dst = REPO / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {dst}")

print("PATCH_APPLIED trace_net_fixed50_trace_server_gemma_engram_progress_v1")
