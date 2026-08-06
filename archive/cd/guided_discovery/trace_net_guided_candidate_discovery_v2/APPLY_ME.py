#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "files"
REPO = ROOT.parent

FILES = [
    "scripts/operations/retrieval/run_trace_net_guided_candidate_discovery_v2.py",
    "tests/unit/test_trace_net_guided_candidate_discovery_v2.py",
    "docs/trace_net_guided_candidate_discovery_v2_README.md",
]

for rel in FILES:
    src = SRC / rel
    dst = REPO / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {rel}")

print("APPLY_DONE trace_net_guided_candidate_discovery_v2")
