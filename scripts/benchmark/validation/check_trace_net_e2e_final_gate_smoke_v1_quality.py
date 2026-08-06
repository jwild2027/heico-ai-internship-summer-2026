#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_final_gate_smoke_v1 import QUALITY_FILENAME, evaluate_quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E final gate smoke v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-source-gate-records", type=int, default=1)
    parser.add_argument("--min-final-gate-records", type=int, default=1)
    parser.add_argument("--min-safe-response-drafts", type=int, default=1)
    parser.add_argument("--min-citation-backed-response-drafts", type=int, default=1)
    parser.add_argument("--min-audit-or-safe-responses", type=int, default=1)
    parser.add_argument("--min-total-citations", type=int, default=1)
    parser.add_argument("--min-pages-cited", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=1)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-sufficiency-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    checks = evaluate_quality(
        summary,
        min_source_gate_records=args.min_source_gate_records,
        min_final_gate_records=args.min_final_gate_records,
        min_safe_response_drafts=args.min_safe_response_drafts,
        min_citation_backed_response_drafts=args.min_citation_backed_response_drafts,
        min_audit_or_safe_responses=args.min_audit_or_safe_responses,
        min_total_citations=args.min_total_citations,
        min_pages_cited=args.min_pages_cited,
        min_field_count=args.min_field_count,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_sufficiency_quality_pass=args.require_source_sufficiency_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    print("TRACE-Net E2E Final Gate Smoke v1 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['expected']}")
    if args.write_json:
        out = report_path.parent / QUALITY_FILENAME
        out.write_text(json.dumps({"quality_status": quality_status, "quality_checks": checks, "summary": summary}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
