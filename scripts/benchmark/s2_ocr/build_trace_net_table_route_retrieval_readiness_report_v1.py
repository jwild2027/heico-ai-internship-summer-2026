from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_retrieval_readiness_report_v1 import (  # noqa: E402
    add_threshold_args,
    build_readiness_report,
    thresholds_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table route retrieval readiness report v1.")
    parser.add_argument("--table-exact-search-adapter", required=True)
    parser.add_argument("--table-exact-search-smoke", required=True)
    parser.add_argument("--table-hybrid-retrieval-bridge", required=True)
    parser.add_argument("--table-hybrid-retrieval-integration-audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args()

    report = build_readiness_report(
        table_exact_search_adapter_path=args.table_exact_search_adapter,
        table_exact_search_smoke_path=args.table_exact_search_smoke,
        table_hybrid_retrieval_bridge_path=args.table_hybrid_retrieval_bridge,
        table_hybrid_retrieval_integration_audit_path=args.table_hybrid_retrieval_integration_audit,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
    )
    summary = report["summary"]
    print("TRACE-Net Table Route Retrieval Readiness Report v1")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    for key in [
        "retrieval_readiness_status",
        "exact_search_document_count",
        "successful_smoke_query_count",
        "total_smoke_match_count",
        "bridge_record_count",
        "ranking_available_bridge_record_count",
        "page_with_ranking_signal_count",
        "field_count",
        "schema_missing_required_key_record_count",
        "unsafe_total_count",
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
    print(" inspect_md_path:", report.get("inspect_md_path"))
    return 0 if (not args.quality or report["quality_status"] == "PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
