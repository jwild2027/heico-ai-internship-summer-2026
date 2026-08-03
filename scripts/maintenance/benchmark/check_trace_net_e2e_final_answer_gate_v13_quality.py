#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_final_answer_gate_v13 import quality_check, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E final answer gate v13 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-reasoned-drafts", type=int, default=0)
    parser.add_argument("--min-final-gates", type=int, default=0)
    parser.add_argument("--min-passed-final-gates", type=int, default=0)
    parser.add_argument("--min-citation-supported-answers", type=int, default=0)
    parser.add_argument("--min-total-citations", type=int, default=0)
    parser.add_argument("--min-final-answers-ready-for-webui", type=int, default=0)
    parser.add_argument("--min-answers-with-limitations", type=int, default=0)
    parser.add_argument("--max-unsupported-claim-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.report_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    quality_status, checks = quality_check(
        report,
        min_reasoned_drafts=args.min_reasoned_drafts,
        min_final_gates=args.min_final_gates,
        min_passed_final_gates=args.min_passed_final_gates,
        min_citation_supported_answers=args.min_citation_supported_answers,
        min_total_citations=args.min_total_citations,
        min_final_answers_ready_for_webui=args.min_final_answers_ready_for_webui,
        min_answers_with_limitations=args.min_answers_with_limitations,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_graph_summary_proof_violations=args.max_graph_summary_proof_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report["quality_status"] = quality_status
    report.setdefault("summary", {})["quality_status"] = quality_status
    report["quality_checks"] = checks
    if args.write_json:
        write_json(path, report)
    print("TRACE-Net E2E Final Answer Gate v13 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        label = "PASS" if check["passed"] else "FAIL"
        print(f" {label} {check['name']}: observed={check['observed']} expected={check['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
