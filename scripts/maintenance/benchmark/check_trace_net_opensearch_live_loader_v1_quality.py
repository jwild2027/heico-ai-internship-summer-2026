from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_opensearch_live_loader_v1 import (
    LiveLoaderThresholds,
    check_live_loader_quality,
    print_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net OpenSearch Live Loader v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-documents", type=int, default=100)
    parser.add_argument("--min-page-scoped-documents", type=int, default=100)
    parser.add_argument("--min-loaded-documents", type=int, default=100)
    parser.add_argument("--min-smoke-queries", type=int, default=3)
    parser.add_argument("--require-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-loader-smoke-quality-pass", action="store_true")
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--require-live-read-check", action="store_true")
    parser.add_argument("--require-bulk-load", action="store_true")
    parser.add_argument("--allow-opensearch-writes", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    report = check_live_loader_quality(
        report_path=args.report_path,
        thresholds=LiveLoaderThresholds(
            min_documents=args.min_documents,
            min_page_scoped_documents=args.min_page_scoped_documents,
            min_loaded_documents=args.min_loaded_documents,
            min_smoke_queries=args.min_smoke_queries,
            require_adapter_quality_pass=args.require_adapter_quality_pass,
            require_loader_smoke_quality_pass=args.require_loader_smoke_quality_pass,
            require_mapping=args.require_mapping,
            require_live_read_check=args.require_live_read_check,
            require_bulk_load=args.require_bulk_load,
            allow_opensearch_writes=args.allow_opensearch_writes,
        ),
        write_json_report=args.write_json,
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
