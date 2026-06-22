"""Quality checker for TRACE-Net Table Full-Enclosure BBox Overlay Export v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from tiff.trace_net_table_full_enclosure_bbox_overlay_export_v1 import evaluate_quality, write_json


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table full-enclosure bbox overlay export quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-source-records", type=int, default=0)
    parser.add_argument("--min-overlay-records", type=int, default=0)
    parser.add_argument("--min-image-available-records", type=int, default=0)
    parser.add_argument("--min-overlay-pngs", type=int, default=0)
    parser.add_argument("--min-contact-sheets", type=int, default=0)
    parser.add_argument("--min-final-bbox-ready-overlays", type=int, default=0)
    parser.add_argument("--min-full-enclosure-reconstructed-overlays", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-full-enclosure-bbox-reconstructor-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = json.loads(args.report_path.read_text(encoding="utf-8"))
    quality = evaluate_quality(payload, args=args)
    if args.write_json:
        quality_path = args.report_path.with_name(args.report_path.stem + "_quality.json")
        write_json(quality_path, quality)
    print("TRACE-Net Table Full-Enclosure BBox Overlay Export v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key, value in quality.items():
        if key.endswith("_count") or key in {"contact_sheet_path", "source_table_full_enclosure_bbox_reconstructor_quality_status"}:
            print(f" {key}: {value}")
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
