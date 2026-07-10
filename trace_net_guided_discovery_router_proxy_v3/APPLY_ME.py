#!/usr/bin/env python3
"""Apply TRACE-Net guided discovery router proxy v3 patch."""
from __future__ import annotations

import shutil
from pathlib import Path

PATCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PATCH_ROOT.parent

FILES = [
    "scripts/serve_trace_net_guided_discovery_router_proxy_v3.py",
    "tests/unit/test_trace_net_guided_discovery_router_proxy_v3.py",
    "docs/trace_net_guided_discovery_router_proxy_v3_README.md",
]

for rel in FILES:
    src = PATCH_ROOT / rel
    dst = REPO_ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"applied {rel}")

print("TRACE-Net guided discovery router proxy v3 patch applied.")
