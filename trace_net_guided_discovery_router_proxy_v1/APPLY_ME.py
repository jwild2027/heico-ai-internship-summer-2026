#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FILES = [
    (ROOT / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v1.py", REPO / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v1.py"),
    (ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v1.py", REPO / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v1.py"),
    (ROOT / "docs" / "trace_net_guided_discovery_router_proxy_v1_README.md", REPO / "docs" / "trace_net_guided_discovery_router_proxy_v1_README.md"),
]

for src, dst in FILES:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"copied {src.relative_to(ROOT)} -> {dst.relative_to(REPO)}")

print("APPLY_DONE trace_net_guided_discovery_router_proxy_v1")
