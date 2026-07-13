#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = Path(__file__).resolve().parent

FILES = [
    (PATCH_DIR / "scripts" / "run_trace_net_router_exact_normal_ask_smoke_v1.py", ROOT / "scripts" / "run_trace_net_router_exact_normal_ask_smoke_v1.py"),
    (PATCH_DIR / "tests" / "fixtures" / "trace_net_router_exact_normal_ask_questions_v1.json", ROOT / "tests" / "fixtures" / "trace_net_router_exact_normal_ask_questions_v1.json"),
    (PATCH_DIR / "tests" / "unit" / "test_trace_net_router_exact_normal_ask_smoke_v1.py", ROOT / "tests" / "unit" / "test_trace_net_router_exact_normal_ask_smoke_v1.py"),
    (PATCH_DIR / "docs" / "trace_net_router_exact_normal_ask_smoke_v1_README.md", ROOT / "docs" / "trace_net_router_exact_normal_ask_smoke_v1_README.md"),
]

for src, dst in FILES:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote={dst}")

print("status=TRACE_NET_ROUTER_EXACT_NORMAL_ASK_SMOKE_V1_APPLIED")
