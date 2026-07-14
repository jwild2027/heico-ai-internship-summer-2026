#!/usr/bin/env python3
"""Apply TRACE-Net full user-query Gemma benchmark v1."""
from pathlib import Path
import shutil

patch = Path(__file__).resolve().parent
repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run this from the repository root.")

files = [
    "scripts/serve_trace_net_full_gemma_user_query_canary_v1.py",
    "scripts/run_trace_net_full_user_query_gemma_benchmark_v1.py",
    "tests/unit/test_trace_net_full_gemma_user_query_canary_v1.py",
    "tests/unit/test_trace_net_full_user_query_gemma_benchmark_v1.py",
    "docs/trace_net/TRACE_NET_FULL_USER_QUERY_GEMMA_BENCHMARK_V1.md",
]
for rel in files:
    src = patch / rel
    dst = repo / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("applied", rel)

print("status=TRACE_NET_FULL_USER_QUERY_GEMMA_BENCHMARK_V1_PATCH_APPLIED")
