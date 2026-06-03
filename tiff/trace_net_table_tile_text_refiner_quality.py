"""Quality gate for TRACE-Net table tile text classifier/refiner v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_table_tile_text_refiner import (
    DEFAULT_OUTPUT_DIR,
    QUALITY_FILE,
    REFINED_RECORDS_FILE,
    SUMMARY_FILE,
    read_jsonl,
    _read_json,
    _write_json,
)


@dataclass(frozen=True)
class TableTileTextRefinerQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    summary_path: Path | None = None
    records_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def records(self) -> Path:
        return self.records_path or (self.output_dir / REFINED_RECORDS_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass
class TableTileTextRefinerQualityOptions:
    min_records: int = 1
    min_catalog_supported_records: int = 0
    min_canonical_part_records: int = 0
    max_error_records: int = 0
    max_index_labels_in_canonical_parts: int = 0
    require_status_ok: bool = True


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _status(ok: bool, name: str, message: str) -> dict[str, Any]:
    return {"status": "OK" if ok else "FAIL", "name": name, "message": message}


def _has_index_in_canonical(records: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for row in records:
        canonical = {str(x).upper() for x in row.get("canonical_part_numbers", []) if x}
        labels = {str(x).upper() for x in row.get("index_labels", []) if x}
        total += len(canonical & labels)
    return total


def build_table_tile_text_refiner_quality(
    paths: TableTileTextRefinerQualityPaths,
    options: TableTileTextRefinerQualityOptions,
) -> dict[str, Any]:
    summary = _as_dict(_read_json(paths.summary, {}))
    records = read_jsonl(paths.records)
    jsonl_records = len(records)
    index_in_canonical = _has_index_in_canonical(records)
    error_records = _int(summary.get("error_records"))
    catalog_records = _int(summary.get("records_with_catalog_supported_parts"))
    canonical_records = _int(summary.get("records_with_canonical_parts"))
    status_text = str(summary.get("status", "")).upper()
    report_summary = {
        "table_tile_text_refined_summary_present": paths.summary.exists(),
        "table_tile_text_refined_records_present": paths.records.exists(),
        "table_tile_text_refined_status": status_text,
        "table_tile_text_refined_records": _int(summary.get("records")),
        "table_tile_text_refined_jsonl_records": jsonl_records,
        "table_tile_text_refined_pages": _int(summary.get("pages")),
        "table_tile_text_refined_ok_records": _int(summary.get("ok_records")),
        "table_tile_text_refined_error_records": error_records,
        "table_tile_text_refined_canonical_part_records": canonical_records,
        "table_tile_text_refined_catalog_supported_records": catalog_records,
        "table_tile_text_refined_probable_part_records": _int(summary.get("records_with_probable_parts")),
        "table_tile_text_refined_index_label_records": _int(summary.get("records_with_index_labels")),
        "table_tile_text_refined_ata_code_records": _int(summary.get("records_with_ata_codes")),
        "table_tile_text_refined_filtered_non_part_records": _int(summary.get("records_with_filtered_non_part_tokens")),
        "table_tile_text_refined_index_labels_in_canonical_parts": index_in_canonical,
        "table_tile_text_refined_trust_tier_counts": summary.get("trust_tier_counts", {}),
        "table_tile_text_refined_rag_action_counts": summary.get("rag_action_counts", {}),
        "table_tile_text_refined_graph_nodes": _int(summary.get("graph_nodes")),
        "table_tile_text_refined_graph_edges": _int(summary.get("graph_edges")),
        "table_tile_text_refined_summary_path": paths.summary.as_posix(),
        "table_tile_text_refined_records_path": paths.records.as_posix(),
    }
    checks = []
    checks.append(_status(paths.summary.exists() and paths.records.exists(), "artifacts_present", f"summary={paths.summary.exists()}; records={paths.records.exists()}"))
    checks.append(_status((not options.require_status_ok) or status_text == "OK", "status_ok", f"status={status_text}; require_status_ok={options.require_status_ok}"))
    checks.append(_status(jsonl_records >= options.min_records, "records", f"records jsonl={jsonl_records}; minimum={options.min_records}"))
    checks.append(_status(_int(summary.get("records")) == jsonl_records, "record_count_match", f"records summary={summary.get('records')}; jsonl={jsonl_records}"))
    checks.append(_status(error_records <= options.max_error_records, "error_records", f"error_records={error_records}; max={options.max_error_records}"))
    checks.append(_status(canonical_records >= options.min_canonical_part_records, "canonical_part_records", f"canonical part records={canonical_records}; minimum={options.min_canonical_part_records}"))
    checks.append(_status(catalog_records >= options.min_catalog_supported_records, "catalog_supported_records", f"catalog supported records={catalog_records}; minimum={options.min_catalog_supported_records}"))
    checks.append(_status(index_in_canonical <= options.max_index_labels_in_canonical_parts, "index_labels_filtered", f"index labels in canonical parts={index_in_canonical}; max={options.max_index_labels_in_canonical_parts}"))
    checks.append(_status(_int(summary.get("graph_nodes")) >= 1, "graph_nodes", f"graph_nodes={summary.get('graph_nodes')}"))
    checks.append(_status(_int(summary.get("graph_edges")) >= 1, "graph_edges", f"graph_edges={summary.get('graph_edges')}"))
    status = "OK" if all(c["status"] == "OK" for c in checks) else "FAIL"
    report = {"status": status, "summary": report_summary, "checks": checks}
    return report


def print_quality(report: Mapping[str, Any], paths: TableTileTextRefinerQualityPaths) -> None:
    print("TRACE-Net table tile text refined quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in dict(report.get("summary") or {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.get("checks", []):
        print(f"    {check.get('status')} {check.get('name')}: {check.get('message')}")
    print(f"\nJSON: {paths.quality}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table tile text refined quality.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--records", type=Path, default=None)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-catalog-supported-records", type=int, default=0)
    parser.add_argument("--min-canonical-part-records", type=int, default=0)
    parser.add_argument("--max-error-records", type=int, default=0)
    parser.add_argument("--max-index-labels-in-canonical-parts", type=int, default=0)
    parser.add_argument("--allow-partial-status", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = TableTileTextRefinerQualityPaths(output_dir=args.output_dir, summary_path=args.summary, records_path=args.records)
    options = TableTileTextRefinerQualityOptions(
        min_records=args.min_records,
        min_catalog_supported_records=args.min_catalog_supported_records,
        min_canonical_part_records=args.min_canonical_part_records,
        max_error_records=args.max_error_records,
        max_index_labels_in_canonical_parts=args.max_index_labels_in_canonical_parts,
        require_status_ok=not args.allow_partial_status,
    )
    report = build_table_tile_text_refiner_quality(paths, options)
    if args.write_json:
        _write_json(paths.quality, report)
    print_quality(report, paths)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
