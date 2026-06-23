#!/usr/bin/env python
"""Check/inspect a post-LEP-v4 table-route value audit report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_value_audit_lep_v4_preset_v1 import (
    DEFAULT_AUDIT_OUTPUT_DIR,
    DEFAULT_AUDIT_REPORT_PATH,
    DEFAULT_NORMALIZER_PATH,
    LepV4AuditPreset,
    write_inspection_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_AUDIT_REPORT_PATH,
        help="Path to trace_net_table_route_value_audit_v1.json.",
    )
    parser.add_argument(
        "--table-route-value-normalizer",
        type=Path,
        default=DEFAULT_NORMALIZER_PATH,
        help="Optional source normalizer report for checking source quality PASS.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_AUDIT_OUTPUT_DIR,
        help="Directory for preset quality/inspect outputs.",
    )
    parser.add_argument("--min-source-normalizer-records", type=int, default=20)
    parser.add_argument("--min-source-normalized-records", type=int, default=1800)
    parser.add_argument("--min-audit-records", type=int, default=20)
    parser.add_argument("--min-audited-tables", type=int, default=19)
    parser.add_argument("--min-promoted-evidence-records", type=int, default=1000)
    parser.add_argument("--min-search-ready-evidence-records", type=int, default=1000)
    parser.add_argument("--min-covered-part-number-promoted", type=int, default=100)
    parser.add_argument("--min-manual-page-reference-promoted", type=int, default=39)
    parser.add_argument("--min-ipl-part-number-promoted", type=int, default=100)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-route-value-normalizer-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--inspect-limit", type=int, default=50)
    parser.add_argument(
        "--write-json",
        action="store_true",
        help="Accepted for compatibility; this checker always writes JSON/Markdown inspect files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preset = LepV4AuditPreset(
        min_source_normalizer_records=args.min_source_normalizer_records,
        min_source_normalized_records=args.min_source_normalized_records,
        min_audit_records=args.min_audit_records,
        min_audited_tables=args.min_audited_tables,
        min_promoted_evidence_records=args.min_promoted_evidence_records,
        min_search_ready_evidence_records=args.min_search_ready_evidence_records,
        min_covered_part_number_promoted=args.min_covered_part_number_promoted,
        min_manual_page_reference_promoted=args.min_manual_page_reference_promoted,
        min_ipl_part_number_promoted=args.min_ipl_part_number_promoted,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_route_value_normalizer_quality_pass=args.require_table_route_value_normalizer_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        inspect_limit=args.inspect_limit,
    )
    inspection = write_inspection_outputs(
        audit_report_path=args.report_path,
        output_dir=args.output_dir,
        preset=preset,
        normalizer_path=args.table_route_value_normalizer,
    )
    print(f"quality_status: {inspection['quality_status']}")
    for key, value in inspection["watch_counters"].items():
        print(f"{key}: {value}")
    return 0 if inspection["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
