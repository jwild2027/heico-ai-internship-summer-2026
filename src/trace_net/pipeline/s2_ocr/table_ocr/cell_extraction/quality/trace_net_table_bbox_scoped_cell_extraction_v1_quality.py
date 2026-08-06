"""Quality checker for TRACE-Net Table BBox Scoped Cell Extraction v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tiff.trace_net_table_bbox_scoped_cell_extraction_v1 import QUALITY_SCHEMA_VERSION, quality_checks, write_json


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net table bbox scoped cell extraction v1 quality.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-source-table-records", type=int, default=1)
    p.add_argument("--min-scoped-table-records", type=int, default=1)
    p.add_argument("--min-bbox-consumed-records", type=int, default=1)
    p.add_argument("--min-scoped-cells", type=int, default=1)
    p.add_argument("--min-scoped-value-records", type=int, default=1)
    p.add_argument("--max-unsafe-scoped-table-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-understanding-quality-pass", action="store_true")
    p.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    p.add_argument("--require-all-records-bbox-scoped", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = read_json(args.report_path)
    summary = payload.get("summary", {}) if isinstance(payload, Mapping) else {}
    status, checks = quality_checks(summary, args)
    print("TRACE-Net Table BBox Scoped Cell Extraction v1 quality")
    print(f" Status: {status}")
    for key in (
        "source_table_record_count",
        "source_page_count",
        "bbox_scope_target_record_count",
        "legacy_unscoped_table_record_count",
        "scoped_table_record_count",
        "page_count",
        "scoped_row_count",
        "scoped_cell_count",
        "scoped_value_record_count",
        "table_extraction_bbox_consumed_record_count",
        "table_extraction_bbox_missing_or_invalid_record_count",
        "bbox_scoped_extraction_ready_record_count",
        "unsafe_scoped_table_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_table_bbox_scoped_cell_extraction_v1_quality.json")
        write_json(out, {"schema_version": QUALITY_SCHEMA_VERSION, "status": status, "summary": summary, "checks": checks})
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
