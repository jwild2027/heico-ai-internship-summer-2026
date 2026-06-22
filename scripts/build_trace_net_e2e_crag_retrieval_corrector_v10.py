#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import (  # noqa: E402
    QUALITY_PASS,
    add_quality_args,
    build_crag_corrector_report,
    evaluate_quality,
    print_quality_result,
    read_json,
    write_report_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E CRAG retrieval corrector v10 artifact.")
    parser.add_argument("--self-rag-context-critic", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args()

    source = read_json(args.self_rag_context_critic)
    report = build_crag_corrector_report(source, source_path=args.self_rag_context_critic)
    quality_status, checks = evaluate_quality(report, args)
    report["quality_status"] = quality_status
    report["summary"]["quality_status"] = quality_status
    report["quality_checks"] = checks
    paths = write_report_files(report, args.output_dir)

    print("TRACE-Net E2E CRAG Retrieval Corrector v10")
    print(f" Status: {report.get('e2e_crag_retrieval_corrector_status')}")
    print(f" Quality status: {quality_status}")
    summary = report["summary"]
    for key in [
        "context_critique_count",
        "crag_plan_count",
        "ready_crag_plan_count",
        "no_retry_needed_count",
        "retry_required_plan_count",
        "human_review_plan_count",
        "unresolved_plan_count",
        "corrective_action_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    for key, value in paths.items():
        print(f" {key}: {value}")

    if args.quality and quality_status != QUALITY_PASS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
