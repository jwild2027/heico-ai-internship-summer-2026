from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_hybrid_retrieval_v2 import quality_report, read_json, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Hybrid Retrieval v2 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-queries-with-results", type=int, default=1)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-exact-hit-groups", type=int, default=1)
    parser.add_argument("--min-semantic-groups", type=int, default=1)
    parser.add_argument("--require-opensearch-quality-pass", action="store_true")
    parser.add_argument("--require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report = read_json(args.report_path)
    q = quality_report(
        report,
        min_queries=args.min_queries,
        min_queries_with_results=args.min_queries_with_results,
        min_groups=args.min_groups,
        min_exact_hit_groups=args.min_exact_hit_groups,
        min_semantic_groups=args.min_semantic_groups,
        require_opensearch_quality_pass=args.require_opensearch_quality_pass,
        require_hybrid_quality_pass=args.require_hybrid_quality_pass,
    )
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_hybrid_retrieval_v2_quality.json")
        write_json(out, q)
    s = q["summary"]
    print("TRACE-Net Hybrid Retrieval v2 quality")
    print(f" Status: {q['status']}")
    print(f" hybrid_v2_query_count: {s.get('hybrid_v2_query_count')}")
    print(f" queries_with_results_count: {s.get('queries_with_results_count')}")
    print(f" hybrid_v2_group_count: {s.get('hybrid_v2_group_count')}")
    print(f" exact_hit_group_count: {s.get('exact_hit_group_count')}")
    print(f" semantic_group_count: {s.get('semantic_group_count')}")
    print(f" unsafe_group_count: {s.get('unsafe_group_count')}")
    print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    return 0 if q["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
