#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import (  # noqa: E402
    build_endpoint_manifest,
    read_json,
    write_report_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E WebUI final answer endpoint v14 manifest.")
    parser.add_argument("--final-answer-gate", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8017)
    parser.add_argument("--model", default="trace-net-e2e-webui-final-answer-endpoint-v14")
    parser.add_argument("--min-final-answers", type=int, default=5)
    parser.add_argument("--min-ready-final-answers", type=int, default=5)
    parser.add_argument("--min-total-citations", type=int, default=15)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--max-unsupported-claim-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    final_gate = read_json(args.final_answer_gate)
    report = build_endpoint_manifest(
        final_gate,
        host=args.host,
        port=args.port,
        model=args.model,
        min_final_answers=args.min_final_answers,
        min_ready_final_answers=args.min_ready_final_answers,
        min_total_citations=args.min_total_citations,
        min_endpoint_routes=args.min_endpoint_routes,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_graph_summary_proof_violations=args.max_graph_summary_proof_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    paths = write_report_files(report, args.output_dir)
    summary = report.get("summary", {})
    print("TRACE-Net E2E WebUI Final Answer Endpoint v14")
    print(f" Status: {report.get('e2e_webui_final_answer_endpoint_status')}")
    print(f" Quality status: {report.get('quality_status')}")
    print(f" final_answer_count: {summary.get('final_answer_count')}")
    print(f" ready_final_answer_count: {summary.get('ready_final_answer_count')}")
    print(f" total_citation_count: {summary.get('total_citation_count')}")
    print(f" endpoint_route_count: {report.get('endpoint_route_count')}")
    print(f" unsupported_claim_count: {summary.get('unsupported_claim_count')}")
    print(f" graph_summary_proof_violation_count: {summary.get('graph_summary_proof_violation_count')}")
    print(f" answer_permission_count: {summary.get('answer_permission_count')}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}")
    print(f" base_url_windows: {report.get('base_url_windows')}")
    print(f" base_url_open_webui_docker: {report.get('base_url_open_webui_docker')}")
    print(f" report_path: {paths['report_path']}")
    print(f" responses_jsonl_path: {paths['responses_jsonl_path']}")
    print(f" inspect_md_path: {paths['inspect_md_path']}")
    if args.quality and report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
