#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_opensearch_loader_smoke_v1 import (
    LoaderSmokeThresholds,
    check_loader_smoke_quality,
    print_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net OpenSearch Loader Smoke v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-documents", type=int, default=100)
    parser.add_argument("--min-page-scoped-documents", type=int, default=100)
    parser.add_argument("--expected-document-count", type=int, default=None)
    parser.add_argument("--min-query-plans", type=int, default=3)
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--require-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-bulk-preview", action="store_true")
    parser.add_argument("--require-live-read-check", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    thresholds = LoaderSmokeThresholds(
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        expected_document_count=args.expected_document_count,
        min_query_plans=args.min_query_plans,
        require_mapping=args.require_mapping,
        require_adapter_quality_pass=args.require_adapter_quality_pass,
        require_bulk_preview=args.require_bulk_preview,
        require_live_read_check=args.require_live_read_check,
    )
    report = check_loader_smoke_quality(
        report_path=args.report_path,
        thresholds=thresholds,
        write_json_report=args.write_json,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
