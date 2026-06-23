#!/usr/bin/env python
"""Build TRACE-Net table-route evidence package from audited table values."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_evidence_packager_v1 import (  # noqa: E402
    DEFAULT_AUDIT_REPORT_PATH,
    DEFAULT_OUTPUT_DIR,
    EvidencePackagerThresholds,
    write_packager_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table-route-value-audit",
        type=Path,
        default=DEFAULT_AUDIT_REPORT_PATH,
        help="Path to trace_net_table_route_value_audit_v1.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for evidence package artifacts.",
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
    parser.add_argument("--quality", action="store_true", help="Return nonzero if quality fails.")
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
    report = write_packager_outputs(
        audit_report_path=args.table_route_value_audit,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
    )
    summary = report["summary"]
    print("TRACE-Net Table Route Evidence Packager v1")
    print(" Status: TABLE_ROUTE_EVIDENCE_PACKAGE_BUILT")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "source_audit_record_count",
        "source_search_ready_evidence_record_count",
        "table_route_evidence_document_count",
        "page_with_evidence_count",
        "table_with_evidence_count",
        "field_count",
        "unsafe_evidence_document_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_route_evidence_packager_v1.json'}")
    print(f" evidence_jsonl_path: {args.output_dir / 'trace_net_table_route_evidence_documents_v1.jsonl'}")
    print(f" inspect_md_path: {args.output_dir / 'trace_net_table_route_evidence_packager_v1_inspect.md'}")
    if args.quality and report["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
