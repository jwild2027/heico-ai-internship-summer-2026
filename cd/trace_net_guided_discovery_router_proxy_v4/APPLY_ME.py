#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PATCH = Path(__file__).resolve().parent
FILES = [
    ("scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v4.py", "scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v4.py"),
    ("scripts/operations/router/launch_trace_net_router_stack_v2.py", "scripts/operations/router/launch_trace_net_router_stack_v2.py"),
    ("tests/unit/test_trace_net_guided_discovery_router_proxy_v4.py", "tests/unit/test_trace_net_guided_discovery_router_proxy_v4.py"),
    ("tests/unit/test_trace_net_router_stack_launcher_v2.py", "tests/unit/test_trace_net_router_stack_launcher_v2.py"),
    ("docs/trace_net_guided_discovery_router_proxy_v4_README.md", "docs/trace_net_guided_discovery_router_proxy_v4_README.md"),
    ("docs/trace_net_router_stack_launcher_v2_README.md", "docs/trace_net_router_stack_launcher_v2_README.md"),
]

def main():
    for src_rel, dst_rel in FILES:
        src = PATCH / src_rel
        dst = ROOT / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() == dst.resolve():
            continue
        shutil.copy2(src, dst)
        print(f"copied {dst_rel}")
    print("TRACE-Net router proxy v4 and stack launcher v2 patch applied")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
