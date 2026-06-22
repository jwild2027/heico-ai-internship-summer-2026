#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_local_endpoint_v1 import build_endpoint_manifest


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build TRACE-Net E2E local endpoint manifest v1")
    p.add_argument("--e2e-api-wrapper-smoke", default="local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json")
    p.add_argument("--output-dir", default="local_data/organization/trace_net/e2e_local_endpoint")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8014)
    p.add_argument("--min-api-responses", type=int, default=5)
    p.add_argument("--min-citation-backed-responses", type=int, default=4)
    p.add_argument("--min-total-citations", type=int, default=10)
    p.add_argument("--require-source-api-wrapper-quality-pass", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    report = build_endpoint_manifest(
        e2e_api_wrapper_smoke_path=args.e2e_api_wrapper_smoke,
        output_dir=args.output_dir,
        host=args.host,
        port=args.port,
        min_api_responses=args.min_api_responses,
        min_citation_backed_responses=args.min_citation_backed_responses,
        min_total_citations=args.min_total_citations,
        require_source_quality_pass=args.require_source_api_wrapper_quality_pass,
    )
    s = report["summary"]
    print("TRACE-Net E2E Local Endpoint v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" e2e_local_endpoint_status: {report['e2e_local_endpoint_status']}")
    for key in (
        "api_response_count",
        "citation_backed_response_count",
        "total_citation_count",
        "page_with_citation_count",
        "field_count",
        "endpoint_route_count",
        "ready_for_open_webui_smoke",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ):
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report['paths']['report_path']}")
    print(f" responses_jsonl_path: {report['paths']['responses_jsonl_path']}")
    print(f" inspect_md_path: {report['paths']['inspect_md_path']}")
    return 0 if report["quality_status"] == "PASS" or not args.quality else 1


if __name__ == "__main__":
    raise SystemExit(main())
