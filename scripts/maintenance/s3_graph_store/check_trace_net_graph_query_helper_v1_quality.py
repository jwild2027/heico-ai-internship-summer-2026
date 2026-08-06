#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_graph_query_helper_v1 import (
    QualityThresholds,
    check_graph_query_helper_quality,
    print_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Graph Query Helper v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-page-results", type=int, default=1)
    parser.add_argument("--min-source-resolved-results", type=int, default=1)
    parser.add_argument("--min-part-query-results", type=int, default=0)
    parser.add_argument("--min-page-query-results", type=int, default=0)
    parser.add_argument("--min-ata-query-results", type=int, default=0)
    parser.add_argument("--require-graph-nodes", action="store_true")
    parser.add_argument("--require-graph-edges", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    thresholds = QualityThresholds(
        min_query_records=args.min_query_records,
        min_page_results=args.min_page_results,
        min_source_resolved_results=args.min_source_resolved_results,
        min_part_query_results=args.min_part_query_results,
        min_page_query_results=args.min_page_query_results,
        min_ata_query_results=args.min_ata_query_results,
        require_graph_nodes=args.require_graph_nodes,
        require_graph_edges=args.require_graph_edges,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = check_graph_query_helper_quality(
        report_path=args.report_path,
        thresholds=thresholds,
        write_json_report=args.write_json,
    )
    print_summary(report, quality_only=True)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
