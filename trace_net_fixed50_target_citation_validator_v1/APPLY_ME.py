#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
DEST = Path.cwd()
FILES = [
    "scripts/validate_trace_net_fixed50_target_citation_v1.py",
    "tests/unit/test_trace_net_fixed50_target_citation_validator_v1.py",
    "docs/trace_net_fixed50_target_citation_validator_v1_README.md",
]

for rel in FILES:
    src = ROOT / rel
    dst = DEST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"copied {rel}")

print("done")
