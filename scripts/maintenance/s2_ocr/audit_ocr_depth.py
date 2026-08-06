from __future__ import annotations

from pathlib import Path
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ocr_depth_audit import OcrDepthThresholds, run_ocr_depth_audit, write_summary_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit whether OCR is missing, header-only, or likely full-page body text.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--export-dir", default=None)
    parser.add_argument("--page-index", default=None)
    parser.add_argument("--zip", dest="zip_path", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--sample-limit", type=int, default=12)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/ocr/ocr_depth_audit.json")
    parser.add_argument("--full-page-min-chars", type=int, default=300)
    parser.add_argument("--full-page-min-lines", type=int, default=6)
    parser.add_argument("--full-page-min-words", type=int, default=30)
    return parser


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = OcrDepthThresholds(
        full_page_min_chars=args.full_page_min_chars,
        full_page_min_lines=args.full_page_min_lines,
        full_page_min_words=args.full_page_min_words,
    )
    summary = run_ocr_depth_audit(
        export_dir=args.export_dir,
        page_index_path=args.page_index,
        zip_path=args.zip_path,
        root=args.root,
        db_path=args.db_path,
        config_path=args.config,
        sample_limit=args.sample_limit,
        max_files=args.max_files,
        repo_root=REPO_ROOT,
        thresholds=thresholds,
    )

    print("OCR depth audit")
    print(f"  Status: {summary.status}")
    print(f"  Source: {summary.source}")
    print(f"  Pages checked: {summary.pages_checked}")
    print()
    print("Classification counts:")
    print(f"  Missing OCR paths: {summary.missing_ocr_paths}")
    print(f"  Missing OCR files: {summary.missing_ocr_files}")
    print(f"  Unreadable OCR files: {summary.unreadable_ocr_files}")
    print(f"  Empty OCR files: {summary.empty_ocr_files}")
    print(f"  Short OCR files: {summary.short_ocr_files}")
    print(f"  Likely header-only OCR: {summary.likely_header_only_ocr}")
    print(f"  Likely full-page OCR: {summary.likely_full_page_ocr}")
    print(f"  Noisy/unknown OCR: {summary.noisy_or_unknown_ocr}")
    print()
    print("Text volume:")
    print(f"  Readable OCR files: {summary.readable_ocr_files}")
    print(f"  Total visible chars: {summary.total_visible_chars}")
    print(f"  Median visible chars: {summary.median_visible_chars:g}")
    print()
    print("Readiness:")
    print(f"  Local OCR paths ready: {yes_no(summary.local_ocr_paths_ready)}")
    print(f"  Full-page OCR likely ready: {yes_no(summary.full_page_ocr_likely_ready)}")
    print(f"  Header/body OCR review needed: {yes_no(summary.header_body_review_needed)}")

    if summary.sample_records:
        print()
        print("Sample OCR-depth rows:")
        for i, row in enumerate(summary.sample_records, start=1):
            print(
                f"  {i}. {row['classification']} | page={row['page_id']} "
                f"label={row.get('page_label') or '-'} ata={row.get('ata_code') or '-'}"
            )
            print(
                f"     chars={row['visible_chars']} lines={row['line_count']} "
                f"words={row['word_count']} parts={row['part_count']} reason={row['reason']}"
            )
            if row.get("ocr_path"):
                print(f"     OCR: {row['ocr_path']}")
            if row.get("sample_text"):
                print(f"     sample: {row['sample_text']}")

    if summary.warnings:
        print()
        print("Warnings:")
        for warning in summary.warnings:
            print(f"  - {warning}")

    if args.write_json:
        write_summary_json(summary, args.json_output)
        print()
        print(f"JSON: {args.json_output}")

    return 0 if summary.status == "OK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
