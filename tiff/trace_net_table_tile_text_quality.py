"""Quality checks for TRACE-Net table tile text extraction v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_table_tile_text import DEFAULT_OUTPUT_DIR, QUALITY_FILE, RECORDS_FILE, SUMMARY_FILE, read_jsonl, _read_json, _write_json


@dataclass(frozen=True)
class TableTileTextQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    summary_path: Path | None = None
    records_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def records(self) -> Path:
        return self.records_path or (self.output_dir / RECORDS_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "status": "OK" if ok else "FAIL", "ok": bool(ok), "message": message}


def build_table_tile_text_quality(
    paths: TableTileTextQualityPaths,
    *,
    min_records: int = 1,
    min_ok_records: int = 0,
    max_error_records: int = 0,
    min_text_chars: int = 0,
    min_part_number_records: int = 0,
    require_status_ok: bool = True,
) -> dict[str, Any]:
    summary = _read_json(paths.summary, {}) if paths.summary.exists() else {}
    records = read_jsonl(paths.records)
    present = paths.summary.exists() and paths.records.exists()
    status = str(summary.get("status", "")).upper()
    error_records = int(summary.get("error_records", 0) or 0)
    ok_records = int(summary.get("ok_records", 0) or 0)
    text_chars = int(summary.get("tile_text_char_total", 0) or 0)
    part_number_records = int(summary.get("part_number_records", 0) or 0)
    checks = [
        _check("table_tile_text_artifacts_present", present, f"summary={paths.summary.exists()}; records={paths.records.exists()}."),
        _check("table_tile_text_status", (status == "OK") if require_status_ok else status in {"OK", "PARTIAL"}, f"status={summary.get('status')} require_status_ok={require_status_ok}."),
        _check("table_tile_text_records", len(records) >= min_records, f"records jsonl={len(records)}; minimum={min_records}."),
        _check("table_tile_text_record_count_match", int(summary.get("records", 0) or 0) == len(records), f"records summary={summary.get('records')}; jsonl={len(records)}."),
        _check("table_tile_text_ok_records", ok_records >= min_ok_records, f"ok_records={ok_records}; minimum={min_ok_records}."),
        _check("table_tile_text_error_records", error_records <= max_error_records, f"error_records={error_records}; max={max_error_records}."),
        _check("table_tile_text_chars", text_chars >= min_text_chars, f"tile_text_char_total={text_chars}; minimum={min_text_chars}."),
        _check("table_tile_text_part_numbers", part_number_records >= min_part_number_records, f"part_number_records={part_number_records}; minimum={min_part_number_records}."),
    ]
    output_summary = {
        "table_tile_text_summary_present": paths.summary.exists(),
        "table_tile_text_records_present": paths.records.exists(),
        "table_tile_text_status": summary.get("status"),
        "table_tile_text_provider": summary.get("provider"),
        "table_tile_text_model": summary.get("model"),
        "table_tile_text_records": summary.get("records", len(records)),
        "table_tile_text_jsonl_records": len(records),
        "table_tile_text_pages": summary.get("pages", 0),
        "table_tile_text_ok_records": ok_records,
        "table_tile_text_planned_records": summary.get("planned_records", 0),
        "table_tile_text_empty_records": summary.get("empty_records", 0),
        "table_tile_text_error_records": error_records,
        "table_tile_text_chars": text_chars,
        "table_tile_text_part_number_records": part_number_records,
        "table_tile_text_catalog_supported_records": summary.get("catalog_supported_part_number_records", 0),
        "table_tile_text_graph_nodes": summary.get("graph_nodes", 0),
        "table_tile_text_graph_edges": summary.get("graph_edges", 0),
        "table_tile_text_summary_path": paths.summary.as_posix(),
        "table_tile_text_records_path": paths.records.as_posix(),
    }
    status_out = "OK" if all(c["ok"] for c in checks) else "FAIL"
    return {"status": status_out, "summary": output_summary, "checks": checks}


def _print_quality(report: Mapping[str, Any], paths: TableTileTextQualityPaths) -> None:
    print("TRACE-Net table tile text quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in report.get("summary", {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.get("checks", []):
        print(f"    {check.get('status')} {check.get('name')}: {check.get('message')}")
    print(f"\nJSON: {paths.quality}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table tile text extraction quality.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-ok-records", type=int, default=0)
    parser.add_argument("--max-error-records", type=int, default=0)
    parser.add_argument("--min-text-chars", type=int, default=0)
    parser.add_argument("--min-part-number-records", type=int, default=0)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = TableTileTextQualityPaths(output_dir=args.output_dir)
    report = build_table_tile_text_quality(
        paths,
        min_records=args.min_records,
        min_ok_records=args.min_ok_records,
        max_error_records=args.max_error_records,
        min_text_chars=args.min_text_chars,
        min_part_number_records=args.min_part_number_records,
        require_status_ok=not args.allow_partial,
    )
    if args.write_json:
        _write_json(paths.quality, report)
    _print_quality(report, paths)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
