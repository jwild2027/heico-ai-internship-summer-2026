from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_repair import (
    TraceNetRepairPaths,
    build_trace_net_repair_quality,
    print_trace_net_repair_quality,
    write_trace_net_repair_quality,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net repair plan quality.")
    parser.add_argument("--visual-text-dir", default="local_data/organization/visual_text")
    parser.add_argument("--trust-trait-dir", default="local_data/organization/trust_traits")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--min-auto-repair-candidates", type=int, default=0)
    parser.add_argument("--max-unplanned-problem-records", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    paths = TraceNetRepairPaths(
        visual_text_dir=Path(args.visual_text_dir),
        trust_trait_dir=Path(args.trust_trait_dir),
        output_dir=Path(args.output_dir),
    )
    quality = build_trace_net_repair_quality(
        paths,
        min_records=args.min_records,
        expected_pages=args.expect_pages,
        min_auto_repair_candidates=args.min_auto_repair_candidates,
        max_unplanned_problem_records=args.max_unplanned_problem_records,
    )
    print_trace_net_repair_quality(quality)
    if args.write_json:
        out = write_trace_net_repair_quality(quality, paths)
        print(f"\nJSON: {out}")
    return 0 if quality.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
