from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_opensearch_missing_lineage_inspector_v1 import (
    add_common_quality_args,
    check_existing_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net OpenSearch missing-lineage inspection quality.")
    parser.add_argument(
        "--report-path",
        required=True,
        help="Path to trace_net_opensearch_missing_lineage_inspector_v1.json",
    )
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args(argv)

    report = check_existing_report(
        report_path=args.report_path,
        min_documents=args.min_documents,
        max_missing_lineage_docs=args.max_missing_lineage_docs,
        require_adapter_quality_pass=args.require_adapter_quality_pass,
        write_json_flag=args.write_json,
    )
    summary = report.get("summary") or {}
    print("TRACE-Net OpenSearch Missing Lineage Inspector v1 quality")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "opensearch_document_count",
        "page_scoped_document_count",
        "missing_lineage_doc_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
