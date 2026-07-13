#!/usr/bin/env python3
"""Add per-question progress output to the 180-question benchmark runner."""
from pathlib import Path

repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run this from the repository root.")

target = repo / "scripts/run_trace_net_router_followup_retrieval_benchmark_v1.py"
text = target.read_text(encoding="utf-8")

old_parser = '    parser.add_argument("--limit", type=int, default=0)\n    parser.add_argument("--min-question-count", type=int, default=150)\n    return parser\n'
new_parser = '    parser.add_argument("--limit", type=int, default=0)\n    parser.add_argument("--min-question-count", type=int, default=150)\n    parser.add_argument(\n        "--no-progress",\n        action="store_true",\n        help="Disable per-question progress lines.",\n    )\n    return parser\n'
old_loop = '    results = [\n        evaluate_record(row, retrieval_state=retrieval_state)\n        for row in rows\n        if isinstance(row, Mapping)\n    ]\n'
new_loop = '    valid_rows = [row for row in rows if isinstance(row, Mapping)]\n    total = len(valid_rows)\n    results = []\n    for index, row in enumerate(valid_rows, 1):\n        query = str(row.get("query") or "")\n        question_id = str(row.get("question_id") or f"q{index:03d}")\n        category = str(row.get("category") or "unknown")\n        retrieval_expectation = str(row.get("retrieval_expectation") or "not_checked")\n        if not args.no_progress:\n            print(\n                f"[{index}/{total}] RUNNING {question_id} "\n                f"category={category} retrieval={retrieval_expectation} "\n                f"query={query[:140]}",\n                flush=True,\n            )\n        result = evaluate_record(row, retrieval_state=retrieval_state)\n        results.append(result)\n        if not args.no_progress:\n            retrieval = result.get("retrieval")\n            direct_count = (\n                int(retrieval.get("direct_evidence_count") or 0)\n                if isinstance(retrieval, Mapping)\n                else 0\n            )\n            print(\n                f"[{index}/{total}] {result.get(\'quality_status\')} "\n                f"route={result.get(\'actual_execution_route\')} "\n                f"tunnel={result.get(\'actual_tunnel\')} "\n                f"followups={result.get(\'follow_up_question_count\')} "\n                f"direct_evidence={direct_count}",\n                flush=True,\n            )\n'

if old_parser in text:
    text = text.replace(old_parser, new_parser, 1)
elif "--no-progress" not in text:
    raise SystemExit("Could not add --no-progress argument.")

if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)
elif "[{index}/{total}] RUNNING" not in text:
    raise SystemExit("Could not replace benchmark evaluation loop.")

target.write_text(text, encoding="utf-8", newline="\n")
print("updated scripts/run_trace_net_router_followup_retrieval_benchmark_v1.py")

test_src = Path(__file__).resolve().parent / "tests/unit/test_trace_net_router_benchmark_progress_v1.py"
test_dst = repo / "tests/unit/test_trace_net_router_benchmark_progress_v1.py"
test_dst.parent.mkdir(parents=True, exist_ok=True)
test_dst.write_text(test_src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
print("applied tests/unit/test_trace_net_router_benchmark_progress_v1.py")
print("status=TRACE_NET_ROUTER_BENCHMARK_PROGRESS_V1_PATCH_APPLIED")
