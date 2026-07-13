#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent
FILES = [
    (ROOT / "scripts" / "launch_trace_net_router_stack_v1.py", DEST / "scripts" / "launch_trace_net_router_stack_v1.py"),
    (ROOT / "tests" / "unit" / "test_trace_net_router_stack_launcher_v1.py", DEST / "tests" / "unit" / "test_trace_net_router_stack_launcher_v1.py"),
    (ROOT / "docs" / "trace_net_router_stack_launcher_v1_README.md", DEST / "docs" / "trace_net_router_stack_launcher_v1_README.md"),
]

for src, dst in FILES:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"copied {src.relative_to(ROOT)} -> {dst.relative_to(DEST)}")

print("Applied trace_net_router_stack_launcher_v1")
