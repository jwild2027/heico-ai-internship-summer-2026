#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FILES = [
    "scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py",
    "scripts/operations/router/launch_trace_net_router_stack_v4.py",
    "tests/unit/test_trace_net_guided_discovery_router_proxy_v6.py",
    "tests/unit/test_trace_net_router_stack_launcher_v4.py",
    "docs/trace_net_guided_discovery_router_proxy_v6_README.md",
    "docs/trace_net_router_stack_launcher_v4_README.md",
]


def main() -> int:
    for rel in FILES:
        src = ROOT / rel
        dst = REPO / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {rel}")
    print("TRACE-Net router proxy v6 and stack launcher v4 patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
