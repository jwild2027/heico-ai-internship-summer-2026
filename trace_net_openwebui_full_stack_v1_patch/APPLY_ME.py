#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
REPO = Path.cwd()

FILES = [
    "scripts/launch_trace_net_openwebui_full_stack_v1.py",
    "scripts/check_trace_net_openwebui_connection_v1.py",
    "tests/unit/test_trace_net_openwebui_full_stack_launcher_v1.py",
    "tests/unit/test_trace_net_openwebui_connection_check_v1.py",
    "docs/trace_net_openwebui_full_stack_v1_README.md",
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

print("TRACE-Net OpenWebUI full stack v1 patch applied.")
