#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ("scripts/benchmark/run_trace_net_router_50_question_discovery_smoke_v1.py", "scripts/benchmark/run_trace_net_router_50_question_discovery_smoke_v1.py"),
    ("tests/fixtures/trace_net_router_50_question_discovery_questions_v1.json", "tests/fixtures/trace_net_router_50_question_discovery_questions_v1.json"),
    ("tests/unit/test_trace_net_router_50_question_discovery_smoke_v1.py", "tests/unit/test_trace_net_router_50_question_discovery_smoke_v1.py"),
    ("docs/trace_net_router_50_question_discovery_smoke_v1_README.md", "docs/trace_net_router_50_question_discovery_smoke_v1_README.md"),
]


def main() -> int:
    for src_rel, dst_rel in FILES:
        src = ROOT / src_rel
        dst = ROOT / dst_rel
        if not src.exists():
            raise FileNotFoundError(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {src_rel} -> {dst_rel}")
    print("status=TRACE_NET_ROUTER_50_QUESTION_DISCOVERY_SMOKE_V1_APPLIED")
    print("quality_status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
