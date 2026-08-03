from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_table_candidate_scan import (
    DEFAULT_OUTPUT_DIR,
    TableCandidateScanPaths,
    build_table_candidate_quality,
    print_table_candidate_quality,
    write_table_candidate_quality,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net all-page table candidate scan quality.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--min-candidates", type=int, default=1)
    parser.add_argument("--max-missing-images", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    paths = TableCandidateScanPaths(output_dir=Path(args.output_dir))
    report = build_table_candidate_quality(
        paths,
        min_records=args.min_records,
        expect_pages=args.expect_pages,
        min_candidates=args.min_candidates,
        max_missing_images=args.max_missing_images,
    )
    print_table_candidate_quality(report)
    if args.write_json:
        path = write_table_candidate_quality(report, paths)
        print(f"\nJSON: {path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
