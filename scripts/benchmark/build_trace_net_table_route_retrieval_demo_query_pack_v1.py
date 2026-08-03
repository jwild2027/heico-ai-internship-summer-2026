from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_retrieval_demo_query_pack_v1 import (  # noqa: E402
    add_threshold_args,
    build_demo_query_pack,
    thresholds_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table route retrieval demo query pack v1.")
    parser.add_argument("--table-route-retrieval-readiness-report", required=True)
    parser.add_argument("--table-hybrid-retrieval-bridge", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--quality", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args()

    report = build_demo_query_pack(
        table_route_retrieval_readiness_report_path=args.table_route_retrieval_readiness_report,
        table_hybrid_retrieval_bridge_path=args.table_hybrid_retrieval_bridge,
        output_dir=args.output_dir,
        top_k=args.top_k,
        thresholds=thresholds_from_args(args),
    )
    summary = report["summary"]
    print("TRACE-Net Table Route Retrieval Demo Query Pack v1")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    for key in [
        "demo_readiness_status",
        "source_retrieval_readiness_status",
        "demo_query_count",
        "successful_demo_query_count",
        "total_demo_match_count",
        "page_with_demo_match_count",
        "field_count",
        "source_bridge_record_count",
        "source_ranking_available_bridge_record_count",
        "unsafe_demo_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(" report_path:", report.get("report_path"))
    print(" demo_queries_jsonl_path:", report.get("demo_queries_jsonl_path"))
    print(" inspect_md_path:", report.get("inspect_md_path"))
    return 0 if (not args.quality or report["quality_status"] == "PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
