#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_api_wrapper_smoke_v1 import add_common_args, build_and_write, thresholds_from_args


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E API Wrapper Smoke v1")
    parser.add_argument("--e2e-rag-demo-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k-citations", type=int, default=3)
    parser.add_argument("--quality", action="store_true")
    add_common_args(parser)
    args = parser.parse_args()

    report = build_and_write(
        e2e_rag_demo_report_path=Path(args.e2e_rag_demo_report),
        output_dir=Path(args.output_dir),
        top_k_citations=args.top_k_citations,
        thresholds=thresholds_from_args(args),
        write_quality=True,
    )

    s = report["summary"]
    print("TRACE-Net E2E API Wrapper Smoke v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" e2e_api_wrapper_smoke_status: {report['e2e_api_wrapper_smoke_status']}")
    for key in [
        "source_e2e_demo_record_count",
        "source_complete_demo_flow_count",
        "api_wrapper_request_count",
        "api_wrapper_response_count",
        "citation_backed_api_response_count",
        "audit_only_api_response_count",
        "total_api_citation_count",
        "page_with_api_citation_count",
        "field_count",
        "unsafe_api_wrapper_record_count",
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
    print(f" report_path: {report['report_path']}")
    print(f" requests_jsonl_path: {report['requests_jsonl_path']}")
    print(f" responses_jsonl_path: {report['responses_jsonl_path']}")
    print(f" inspect_md_path: {report['inspect_md_path']}")
    return 0 if report["quality_status"] == "PASS" or not args.quality else 1


if __name__ == "__main__":
    raise SystemExit(main())
