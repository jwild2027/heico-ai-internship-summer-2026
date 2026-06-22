#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_query_input_v1 import (  # noqa: E402
    QUALITY_PASS,
    QueryBuildConfig,
    STANDARD_DEMO_QUERIES,
    build_report,
    read_queries_from_file,
    write_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E query input v1 artifact.")
    parser.add_argument("--query", action="append", default=[], help="User query. Can be repeated.")
    parser.add_argument("--query-file", type=Path, help="Optional JSON/JSONL/text file containing queries.")
    parser.add_argument("--include-standard-demo-queries", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-routeable-queries", type=int, default=1)
    parser.add_argument("--min-unique-intents", type=int, default=1)
    parser.add_argument("--min-planned-retrieval-queries", type=int, default=1)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queries = list(args.query or [])
    if args.query_file:
        queries.extend(read_queries_from_file(args.query_file))
    if args.include_standard_demo_queries:
        queries.extend(STANDARD_DEMO_QUERIES)
    if not queries:
        raise SystemExit("No queries provided. Use --query, --query-file, or --include-standard-demo-queries.")

    config = QueryBuildConfig(
        min_query_records=args.min_query_records,
        min_routeable_queries=args.min_routeable_queries,
        min_unique_intents=args.min_unique_intents,
        min_planned_retrieval_queries=args.min_planned_retrieval_queries,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_report(queries, config)
    paths = write_outputs(report, args.output_dir)
    summary = report["summary"]

    print("TRACE-Net E2E Query Input v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" e2e_query_input_status: {report['e2e_query_input_status']}")
    for key in [
        "e2e_query_input_record_count",
        "routeable_query_count",
        "planned_retrieval_query_count",
        "unique_intent_count",
        "unsafe_query_input_record_count",
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
    for key, value in paths.items():
        print(f" {key}: {value}")

    if args.quality and report["quality_status"] != QUALITY_PASS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
