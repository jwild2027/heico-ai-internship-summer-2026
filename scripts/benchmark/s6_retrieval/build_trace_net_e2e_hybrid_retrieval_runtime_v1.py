#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_hybrid_retrieval_runtime_v1 import QualityThresholds, build_from_paths


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build TRACE-Net E2E hybrid retrieval runtime v1 artifact.")
    p.add_argument("--e2e-query-input", required=True)
    p.add_argument("--table-hybrid-retrieval-bridge", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--min-source-query-records", type=int, default=1)
    p.add_argument("--min-source-bridge-records", type=int, default=1)
    p.add_argument("--min-retrieval-queries", type=int, default=1)
    p.add_argument("--min-successful-retrieval-queries", type=int, default=1)
    p.add_argument("--min-retrieval-groups", type=int, default=1)
    p.add_argument("--min-total-retrieval-hits", type=int, default=1)
    p.add_argument("--min-pages-with-retrieval-hits", type=int, default=1)
    p.add_argument("--min-field-count", type=int, default=1)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-source-query-input-quality-pass", action="store_true")
    p.add_argument("--require-source-bridge-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = QualityThresholds(
        min_source_query_records=args.min_source_query_records,
        min_source_bridge_records=args.min_source_bridge_records,
        min_retrieval_queries=args.min_retrieval_queries,
        min_successful_retrieval_queries=args.min_successful_retrieval_queries,
        min_retrieval_groups=args.min_retrieval_groups,
        min_total_retrieval_hits=args.min_total_retrieval_hits,
        min_pages_with_retrieval_hits=args.min_pages_with_retrieval_hits,
        min_field_count=args.min_field_count,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_query_input_quality_pass=args.require_source_query_input_quality_pass,
        require_source_bridge_quality_pass=args.require_source_bridge_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_from_paths(
        e2e_query_input_path=args.e2e_query_input,
        table_hybrid_retrieval_bridge_path=args.table_hybrid_retrieval_bridge,
        output_dir=args.output_dir,
        top_k=args.top_k,
        thresholds=thresholds,
        write_quality_json=True,
    )
    s = report["summary"]
    print("TRACE-Net E2E Hybrid Retrieval Runtime v1")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    for key in [
        "e2e_hybrid_retrieval_runtime_status",
        "source_query_input_record_count",
        "source_bridge_record_count",
        "hybrid_retrieval_query_count",
        "successful_retrieval_query_count",
        "retrieval_group_count",
        "total_retrieval_hit_count",
        "page_with_retrieval_hit_count",
        "field_count",
        "unsafe_runtime_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(" report_path:", report.get("report_path"))
    print(" retrieval_groups_jsonl_path:", report.get("retrieval_groups_jsonl_path"))
    print(" inspect_md_path:", report.get("inspect_md_path"))
    if args.quality and report["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
