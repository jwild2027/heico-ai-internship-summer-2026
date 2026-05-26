#!/usr/bin/env python3
"""Scan only TIFF files listed by the Stage 0 inventory bridge.

This script is the Stage 0 -> Stage 1 bridge:

    inventory crawler
      -> list_changed_tiffs_for_scan.py
      -> changed_tiffs.txt
      -> scan_changed_tiffs.py
      -> JSON reports + TIFF scan SQLite DB

It intentionally scans only paths in the input list. If the list is empty, it
exits successfully without doing OCR or writing scan rows.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.json_report import scan_tiff_to_dict, write_scan_json
from tiff.sqlite_store import connect, upsert_scan_report

TIFF_EXTENSIONS = {".tif", ".tiff"}


@dataclass
class ChangedScanResult:
    file_list: str
    output_dir: str
    db_path: str | None
    source_root: str | None = None
    total_listed: int = 0
    total_attempted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    started_at_unix: float = field(default_factory=time.time)
    finished_at_unix: float | None = None
    reports: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at_unix if self.finished_at_unix is not None else time.time()
        return round(end - self.started_at_unix, 3)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["elapsed_seconds"] = self.elapsed_seconds
        return data


def read_path_list(file_list: str | Path) -> list[str]:
    """Read one path per line, ignoring blanks and # comments."""

    path = Path(file_list)
    if not path.exists():
        raise FileNotFoundError(f"file list not found: {path}")

    values: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values.append(line)
    return values


def resolve_listed_path(raw_path: str, *, source_root: str | Path | None = None) -> Path:
    """Resolve a path from changed_tiffs.txt.

    list_changed_tiffs_for_scan.py can output absolute paths or relative paths.
    If source_root is supplied and the path is relative, resolve against it.
    """

    path = Path(raw_path)
    if path.is_absolute():
        return path
    if source_root is not None:
        return Path(source_root) / path
    return path


def _safe_output_name(tiff_path: Path, *, source_root: Path | None, output_dir: Path) -> Path:
    """Return report path, preserving relative subfolders when possible."""

    if source_root is not None:
        try:
            relative = tiff_path.resolve().relative_to(source_root.resolve())
        except Exception:  # noqa: BLE001 - fallback to simple filename for mixed roots.
            relative = Path(tiff_path.name)
    else:
        relative = Path(tiff_path.name)
    return output_dir / relative.with_suffix(relative.suffix + ".scan.json")


def _failure_report(
    *,
    tiff_path: Path,
    output_path: Path,
    error: Exception,
    source_root: Path | None,
) -> dict[str, Any]:
    if source_root is not None:
        try:
            relative_path = str(tiff_path.resolve().relative_to(source_root.resolve()))
        except Exception:  # noqa: BLE001
            relative_path = tiff_path.name
    else:
        relative_path = tiff_path.name

    report = {
        "schema_version": "tiff_changed_scan_failure.v1",
        "scan_status": "failed",
        "source": {
            "type": "changed_tiff_file",
            "path": str(tiff_path),
            "relative_path": relative_path,
        },
        "file": {
            "file_name": tiff_path.name,
            "extension": tiff_path.suffix.lower(),
        },
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def scan_changed_tiffs(
    *,
    file_list: str | Path,
    output_dir: str | Path,
    db_path: str | Path | None = None,
    source_root: str | Path | None = None,
    hash_file: bool = True,
    parse_filename: bool = True,
    run_ocr: bool = False,
    ocr_page_index: int = 0,
    ocr_lang: str = "eng",
    tesseract_cmd: str | None = None,
    overwrite: bool = True,
    continue_on_error: bool = True,
    write_failure_json: bool = True,
    summary_output: str | Path | None = None,
) -> ChangedScanResult:
    """Scan only TIFF paths listed in file_list."""

    source_root_path = Path(source_root) if source_root is not None else None
    output_root = Path(output_dir)
    raw_paths = read_path_list(file_list)
    paths = [resolve_listed_path(p, source_root=source_root_path) for p in raw_paths]

    result = ChangedScanResult(
        file_list=str(file_list),
        output_dir=str(output_root),
        db_path=str(db_path) if db_path is not None else None,
        source_root=str(source_root_path) if source_root_path is not None else None,
        total_listed=len(paths),
    )

    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db_conn = connect(db_path) if db_path else None

    try:
        for index, tiff_path in enumerate(paths, start=1):
            out_path = _safe_output_name(tiff_path, source_root=source_root_path, output_dir=output_root)
            if out_path.exists() and not overwrite:
                result.total_skipped += 1
                print(f"[{index}/{len(paths)}] skip existing: {out_path}")
                continue

            result.total_attempted += 1
            print(f"[{index}/{len(paths)}] scanning changed/new TIFF: {tiff_path}")
            try:
                if tiff_path.suffix.lower() not in TIFF_EXTENSIONS:
                    raise ValueError(f"not a TIFF file: {tiff_path}")
                if not tiff_path.exists():
                    raise FileNotFoundError(f"TIFF file not found: {tiff_path}")

                report = scan_tiff_to_dict(
                    tiff_path,
                    source_root=source_root_path if source_root_path is not None else tiff_path.parent,
                    hash_file=hash_file,
                    parse_filename=parse_filename,
                    run_ocr=run_ocr,
                    ocr_page_index=ocr_page_index,
                    ocr_lang=ocr_lang,
                    tesseract_cmd=tesseract_cmd,
                )
                json_path = write_scan_json(report, out_path)
                file_id = None
                if db_conn is not None:
                    file_id = upsert_scan_report(db_conn, report)

                result.total_succeeded += 1
                result.reports.append(
                    {
                        "source_path": str(tiff_path),
                        "json_path": str(json_path),
                        "file_id": file_id,
                        "scan_status": report.get("scan_status"),
                        "detected_type": (report.get("document_classification") or {}).get("detected_type"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                result.total_failed += 1
                failure = {
                    "source_path": str(tiff_path),
                    "json_path": str(out_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                result.failures.append(failure)
                print(f"  failed: {type(exc).__name__}: {exc}")
                if write_failure_json:
                    _failure_report(
                        tiff_path=tiff_path,
                        output_path=out_path,
                        error=exc,
                        source_root=source_root_path,
                    )
                if not continue_on_error:
                    raise
    finally:
        if db_conn is not None:
            db_conn.close()

    result.finished_at_unix = time.time()

    if summary_output is not None:
        summary_path = Path(summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan TIFF files listed in changed_tiffs.txt into JSON/SQLite.")
    parser.add_argument("--file-list", required=True, help="Text file with one TIFF path per line")
    parser.add_argument(
        "--output-dir",
        default="local_data/json_scans_changed",
        help="Folder where .scan.json files are written",
    )
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_scans_incremental.db",
        help="SQLite scan DB path. Use --no-db to disable.",
    )
    parser.add_argument("--no-db", action="store_true", help="Do not save scan reports to SQLite")
    parser.add_argument("--source-root", default=None, help="Optional root for relative paths and relative JSON output")
    parser.add_argument("--no-hash", action="store_true", help="Skip SHA-256 hashing for faster scans")
    parser.add_argument("--no-filename-parse", action="store_true", help="Disable filename-based parsing")
    parser.add_argument("--ocr", action="store_true", help="Run local Tesseract OCR on likely title/header regions")
    parser.add_argument("--ocr-page-index", type=int, default=0, help="Zero-based TIFF page index to OCR")
    parser.add_argument("--ocr-lang", default="eng", help="Tesseract language code")
    parser.add_argument("--tesseract-cmd", default=None, help="Optional explicit path to tesseract.exe")
    parser.add_argument("--no-overwrite", action="store_true", help="Skip JSON files that already exist")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop at the first failed file")
    parser.add_argument(
        "--summary-output",
        default="local_data/json_scans_changed/changed_batch_summary.json",
        help="Write summary JSON here",
    )
    parser.add_argument("--print-summary", action="store_true", help="Print full summary JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    db_path = None if args.no_db else args.db_path
    result = scan_changed_tiffs(
        file_list=args.file_list,
        output_dir=args.output_dir,
        db_path=db_path,
        source_root=args.source_root,
        hash_file=not args.no_hash,
        parse_filename=not args.no_filename_parse,
        run_ocr=args.ocr,
        ocr_page_index=args.ocr_page_index,
        ocr_lang=args.ocr_lang,
        tesseract_cmd=args.tesseract_cmd,
        overwrite=not args.no_overwrite,
        continue_on_error=not args.stop_on_error,
        summary_output=args.summary_output,
    )

    if args.print_summary:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            "Changed scan complete: "
            f"listed={result.total_listed} "
            f"attempted={result.total_attempted} "
            f"succeeded={result.total_succeeded} "
            f"failed={result.total_failed} "
            f"skipped={result.total_skipped} "
            f"elapsed={result.elapsed_seconds}s"
        )
        if args.summary_output:
            print(f"Summary JSON: {args.summary_output}")
        if db_path:
            print(f"SQLite DB: {db_path}")

    return 1 if result.total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
