#!/usr/bin/env python3
"""Batch-scan a folder of TIFF files into JSON reports and optional SQLite rows.

This is the folder-level companion to scripts/scan_tiff_to_json.py.
It stays local-only: TIFF bytes, OCR text, JSON, and SQLite data remain on the
machine where the script runs.

Examples:
    python scripts/batch_scan_tiffs_to_json.py \
        --input-dir local_data/sample_tiffs \
        --output-dir local_data/json_scans \
        --db-path local_data/db/tiff_scans.db \
        --ocr \
        --tesseract-cmd "C:\\Users\\juswil\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe"

    python scripts/batch_scan_tiffs_to_json.py \
        --input-dir local_data/sample_tiffs \
        --output-dir local_data/json_scans \
        --db-path local_data/db/tiff_scans.db \
        --no-hash \
        --limit 25
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Allow running from the repo root without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.json_report import scan_tiff_to_dict, write_scan_json
from tiff.sqlite_store import connect, upsert_scan_report

TIFF_EXTENSIONS = {".tif", ".tiff"}


@dataclass
class BatchScanResult:
    input_dir: str
    output_dir: str
    db_path: str | None
    total_discovered: int = 0
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


def iter_tiff_files(input_dir: str | Path, *, recursive: bool = True) -> Iterable[Path]:
    """Yield TIFF files under input_dir in stable sorted order."""

    root = Path(input_dir)
    pattern = "**/*" if recursive else "*"
    candidates = (p for p in root.glob(pattern) if p.is_file())
    yield from sorted(p for p in candidates if p.suffix.lower() in TIFF_EXTENSIONS)


def report_output_path(tiff_path: Path, *, input_dir: Path, output_dir: Path) -> Path:
    """Return the JSON output path for one TIFF, preserving subfolders."""

    try:
        relative = tiff_path.relative_to(input_dir)
    except ValueError:
        relative = Path(tiff_path.name)
    return output_dir / relative.with_suffix(relative.suffix + ".scan.json")


def _write_failure_report(
    *,
    tiff_path: Path,
    output_path: Path,
    error: Exception,
    source_root: Path,
) -> dict[str, Any]:
    try:
        relative_path = str(tiff_path.relative_to(source_root))
    except ValueError:
        relative_path = tiff_path.name

    report = {
        "schema_version": "tiff_scan_failure.v1",
        "scan_status": "failed",
        "source": {
            "type": "batch_tiff_file",
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


def scan_folder_to_json(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    db_path: str | Path | None = None,
    hash_file: bool = True,
    parse_filename: bool = True,
    run_ocr: bool = False,
    ocr_page_index: int = 0,
    ocr_lang: str = "eng",
    tesseract_cmd: str | None = None,
    recursive: bool = True,
    limit: int | None = None,
    overwrite: bool = True,
    continue_on_error: bool = True,
    write_failure_json: bool = True,
    summary_output: str | Path | None = None,
) -> BatchScanResult:
    """Batch-scan TIFF files to JSON and optional SQLite.

    Args mirror the single-file scanner. The function returns a summary object
    that can be printed, tested, or written to JSON.
    """

    input_root = Path(input_dir)
    output_root = Path(output_dir)
    if not input_root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_root}")
    if not input_root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_root}")

    files = list(iter_tiff_files(input_root, recursive=recursive))
    if limit is not None:
        files = files[: max(limit, 0)]

    result = BatchScanResult(
        input_dir=str(input_root),
        output_dir=str(output_root),
        db_path=str(db_path) if db_path is not None else None,
        total_discovered=len(files),
    )

    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db_conn = connect(db_path) if db_path else None
    try:
        for index, tiff_path in enumerate(files, start=1):
            out_path = report_output_path(tiff_path, input_dir=input_root, output_dir=output_root)
            if out_path.exists() and not overwrite:
                result.total_skipped += 1
                print(f"[{index}/{len(files)}] skip existing: {out_path}")
                continue

            result.total_attempted += 1
            print(f"[{index}/{len(files)}] scanning: {tiff_path}")
            try:
                report = scan_tiff_to_dict(
                    tiff_path,
                    source_root=input_root,
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
            except Exception as exc:  # noqa: BLE001 - CLI should report and continue when requested.
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
                    _write_failure_report(
                        tiff_path=tiff_path,
                        output_path=out_path,
                        error=exc,
                        source_root=input_root,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-scan TIFF files into JSON reports and optional SQLite rows.")
    parser.add_argument(
        "--input-dir",
        default="local_data/sample_tiffs",
        help="Folder containing raw .tif/.tiff files. Default: local_data/sample_tiffs",
    )
    parser.add_argument(
        "--output-dir",
        default="local_data/json_scans",
        help="Folder where .scan.json files are written. Default: local_data/json_scans",
    )
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_scans.db",
        help="SQLite database path. Use --no-db to disable. Default: local_data/db/tiff_scans.db",
    )
    parser.add_argument("--no-db", action="store_true", help="Do not save scan reports to SQLite")
    parser.add_argument("--no-hash", action="store_true", help="Skip SHA-256 hashing for faster scans")
    parser.add_argument("--no-filename-parse", action="store_true", help="Disable filename-based metadata parsing")
    parser.add_argument("--ocr", action="store_true", help="Run local Tesseract OCR on likely title/header regions")
    parser.add_argument("--ocr-page-index", type=int, default=0, help="Zero-based TIFF page index to OCR. Default: 0")
    parser.add_argument("--ocr-lang", default="eng", help="Tesseract language code. Default: eng")
    parser.add_argument("--tesseract-cmd", default=None, help="Optional explicit path to tesseract.exe")
    parser.add_argument("--non-recursive", action="store_true", help="Only scan TIFF files directly inside input-dir")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of TIFFs to scan")
    parser.add_argument("--no-overwrite", action="store_true", help="Skip JSON files that already exist")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop at the first failed file")
    parser.add_argument(
        "--summary-output",
        default="local_data/json_scans/batch_summary.json",
        help="Write batch summary JSON here. Default: local_data/json_scans/batch_summary.json",
    )
    parser.add_argument("--print-summary", action="store_true", help="Print full summary JSON to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = None if args.no_db else args.db_path
    result = scan_folder_to_json(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        db_path=db_path,
        hash_file=not args.no_hash,
        parse_filename=not args.no_filename_parse,
        run_ocr=args.ocr,
        ocr_page_index=args.ocr_page_index,
        ocr_lang=args.ocr_lang,
        tesseract_cmd=args.tesseract_cmd,
        recursive=not args.non_recursive,
        limit=args.limit,
        overwrite=not args.no_overwrite,
        continue_on_error=not args.stop_on_error,
        summary_output=args.summary_output,
    )

    summary = result.to_dict()
    if args.print_summary:
        print(json.dumps(summary, indent=2))
    else:
        print(
            "Batch complete: "
            f"discovered={result.total_discovered} "
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
