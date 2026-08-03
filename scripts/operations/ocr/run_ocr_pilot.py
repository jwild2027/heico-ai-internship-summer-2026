#!/usr/bin/env python3
"""Run a safe OCR pilot on a TIFF sample with streaming progress."""
from __future__ import annotations

from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ocr_pilot_progress import run_ocr_pilot_with_progress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an isolated OCR pilot on TIFF pages.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--zip", dest="zip_path", help="Source ZIP containing TIFF pages")
    src.add_argument("--root", help="Source root directory containing TIFF pages")
    src.add_argument("--export-dir", help="Organization export directory with page_index.json")
    parser.add_argument("--output-dir", default="local_data/ocr/pilot", help="Pilot output directory")
    parser.add_argument("--limit", type=int, default=25, help="Number of pages to select")
    parser.add_argument("--offset", type=int, default=0, help="Start offset in sorted page list")
    parser.add_argument("--engine", choices=["auto", "tesseract", "existing", "none"], default="auto")
    parser.add_argument("--tesseract-cmd", default="tesseract")
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--psm", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--force", action="store_true", help="Regenerate OCR outputs even if pilot OCR exists")
    parser.add_argument("--write-json", action="store_true", help="Accepted for consistency; pilot always writes JSON report files")
    parser.add_argument("--no-progress", action="store_true", help="Disable per-page progress output")
    parser.add_argument("--progress-every", type=int, default=1, help="Print progress every N pages; default is every page")
    return parser


def _print_summary(summary) -> None:
    print("OCR pilot")
    print(f"  Status: {summary.status}")
    print(f"  Source: {summary.source}")
    print(f"  Output dir: {summary.output_dir}")
    print(f"  Engine requested: {summary.engine_requested}")
    print(f"  Engine used: {summary.engine_used}")
    print(f"  Tesseract available: {summary.tesseract_available}")
    print("")
    print("Counts:")
    print(f"  Pages selected: {summary.pages_selected}")
    print(f"  OCR attempted: {summary.ocr_attempted}")
    print(f"  OCR succeeded: {summary.ocr_succeeded}")
    print(f"  OCR failed: {summary.ocr_failed}")
    print(f"  Existing OCR copied: {summary.copied_existing}")
    print(f"  Cached outputs reused: {summary.cached_existing}")
    print(f"  Missing OCR engine/existing OCR: {summary.missing_ocr_engine}")
    print(f"  Skipped no input: {summary.skipped_no_input}")
    print(f"  Elapsed: {summary.elapsed_seconds:.2f}s")
    print("")
    print("By status:")
    for key, value in sorted(summary.by_status.items()):
        print(f"  {key}: {value}")
    print("")
    print("By OCR-depth classification:")
    if summary.by_classification:
        for key, value in sorted(summary.by_classification.items()):
            print(f"  {key}: {value}")
    else:
        print("  none")
    if summary.sample_records:
        print("")
        print("Sample records:")
        for idx, row in enumerate(summary.sample_records, start=1):
            status = row.get("status")
            classification = row.get("classification") or "-"
            chars = row.get("visible_chars", 0)
            print(f"  {idx}. {row.get('page_id')} | status={status} | class={classification} | chars={chars}")
            if row.get("error"):
                print(f"     error: {row.get('error')}")
            if row.get("ocr_path"):
                print(f"     OCR: {row.get('ocr_path')}")
            if row.get("tiff_path"):
                print(f"     TIFF: {row.get('tiff_path')}")
    if summary.warnings:
        print("")
        print("Warnings:")
        for warning in summary.warnings:
            print(f"  - {warning}")
    print("")
    print("Files written:")
    for label, path in summary.files_written.items():
        print(f"  {label}: {path}")
    print("")
    print("Next useful audit:")
    print(f"  python scripts/maintenance/ocr/audit_ocr_depth.py --export-dir {summary.output_dir} --write-json --json-output local_data/ocr/ocr_pilot_depth_audit.json")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_ocr_pilot_with_progress(
            zip_path=args.zip_path,
            root=args.root,
            export_dir=args.export_dir,
            output_dir=args.output_dir,
            limit=args.limit,
            offset=args.offset,
            engine=args.engine,
            tesseract_cmd=args.tesseract_cmd,
            lang=args.lang,
            psm=args.psm,
            timeout_seconds=args.timeout_seconds,
            force=args.force,
            repo_root=REPO_ROOT,
            progress=not args.no_progress,
            progress_every=args.progress_every,
        )
    except Exception as exc:
        print(f"OCR pilot failed: {exc}", file=sys.stderr)
        return 2

    print("")
    _print_summary(summary)
    return 0 if summary.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
