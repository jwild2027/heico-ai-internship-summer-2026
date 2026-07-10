from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PATCH = Path(__file__).resolve().parent
FILES = [
    "scripts/serve_trace_net_guided_discovery_router_proxy_v5.py",
    "scripts/launch_trace_net_router_stack_v3.py",
    "tests/unit/test_trace_net_guided_discovery_router_proxy_v5.py",
    "tests/unit/test_trace_net_router_stack_launcher_v3.py",
    "docs/trace_net_guided_discovery_router_proxy_v5_README.md",
    "docs/trace_net_router_stack_launcher_v3_README.md",
]


def main() -> int:
    for rel in FILES:
        src = PATCH / rel
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {rel}")
    print("TRACE-Net router proxy v5 and stack launcher v3 patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
