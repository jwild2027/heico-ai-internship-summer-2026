#!/usr/bin/env python3
"""Build TRACE-Net NHA phases N0-N3 artifacts from a TIFF directory or ZIP."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Direct execution (``python scripts/build_...py``) places only ``scripts/`` on
# sys.path. Add the repository root so the established ``scripts.*`` imports
# work without requiring callers to set PYTHONPATH first.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase0_3_v1 import build_phase0_3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Directory or ZIP containing metadata.xml and TIFF pages")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--metadata-member", default="metadata.xml")
    parser.add_argument("--page-id-prefix", default="t_p_120_1176_p")
    parser.add_argument("--document-id", default="120-1176")
    parser.add_argument("--pilot-pages", default="342-344,348-349,351,354,363,368")
    parser.add_argument("--ocr-records", default="")
    parser.add_argument("--tesseract-cmd", default="")
    parser.add_argument("--tesseract-psm", type=int, default=6)
    parser.add_argument("--expected-page-count", type=int, default=509)
    parser.add_argument("--min-source-supported", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_phase0_3(
        input_path=args.input,
        output_dir=args.output_dir,
        metadata_member=args.metadata_member,
        page_id_prefix=args.page_id_prefix,
        document_id=args.document_id,
        pilot_pages=args.pilot_pages,
        ocr_records=args.ocr_records or None,
        tesseract_cmd=args.tesseract_cmd,
        tesseract_psm=args.tesseract_psm,
        expected_page_count=args.expected_page_count,
        min_source_supported=args.min_source_supported,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    print(f"summary={Path(args.output_dir).resolve() / 'trace_net_nha_phase0_3_summary_v1.json'}")
    if args.strict and summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE0_3=FAIL")
    print("TRACE_NET_NHA_PHASE0_3=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE0_3=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
