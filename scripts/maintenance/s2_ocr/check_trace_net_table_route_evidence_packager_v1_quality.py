#!/usr/bin/env python
"""Check TRACE-Net table-route evidence packager quality."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_evidence_packager_v1 import (  # noqa: E402
    DEFAULT_PACKAGE_REPORT_PATH,
    EvidencePackagerThresholds,
    build_quality_checks,
    load_json,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_PACKAGE_REPORT_PATH,
        help="Path to trace_net_table_route_evidence_packager_v1.json.",
    )
    parser.add_argument("--min-source-audit-records", type=int, default=20)
    parser.add_argument("--min-source-search-ready-records", type=int, default=1000)
    parser.add_argument("--min-evidence-documents", type=int, default=1000)
    parser.add_argument("--min-pages-with-evidence", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=4)
    parser.add_argument("--min-covered-part-number-documents", type=int, default=100)
    parser.add_argument("--min-manual-page-reference-documents", type=int, default=39)
    parser.add_argument("--min-ipl-part-number-documents", type=int, default=100)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args()


def thresholds_from_args(args: argparse.Namespace) -> EvidencePackagerThresholds:
    return EvidencePackagerThresholds(
        min_source_audit_records=args.min_source_audit_records,
        min_source_search_ready_records=args.min_source_search_ready_records,
        min_evidence_documents=args.min_evidence_documents,
        min_pages_with_evidence=args.min_pages_with_evidence,
        min_field_count=args.min_field_count,
        min_covered_part_number_documents=args.min_covered_part_number_documents,
        min_manual_page_reference_documents=args.min_manual_page_reference_documents,
        min_ipl_part_number_documents=args.min_ipl_part_number_documents,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_audit_quality_pass=args.require_source_audit_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def main() -> int:
    args = parse_args()
    report = load_json(args.report_path)
    summary = report.get("summary", {})
    checks = build_quality_checks(summary, thresholds_from_args(args))
    quality_status = "PASS" if all(check.passed for check in checks) else "FAIL"
    output = {
        "schema_version": "trace_net_table_route_evidence_packager_quality_check_v1",
        "quality_status": quality_status,
        "summary": summary,
        "checks": [check.to_dict() for check in checks],
        "report_path": str(args.report_path),
    }
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_route_evidence_packager_v1_quality.json"), output)
    print("TRACE-Net Table Route Evidence Packager v1 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f" {marker} {check.name}: observed={check.observed} expected={check.expected}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
