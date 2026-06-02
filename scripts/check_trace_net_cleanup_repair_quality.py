from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_cleanup_repair import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TRACE_NET_DIR,
    DEFAULT_VISUAL_TEXT_DIR,
    TraceNetCleanupRepairPaths,
    build_trace_net_cleanup_repair_quality,
    print_cleanup_repair_quality,
    write_trace_net_cleanup_repair_quality,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net cleanup repair quality.")
    parser.add_argument("--visual-text-dir", default=str(DEFAULT_VISUAL_TEXT_DIR))
    parser.add_argument("--trace-net-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-input-records", type=int, default=1)
    parser.add_argument("--min-repaired-records", type=int, default=1)
    parser.add_argument("--max-remaining-prompt-template-leakage-records", type=int, default=None)
    parser.add_argument("--max-remaining-section-bleed-records", type=int, default=None)
    parser.add_argument("--min-improved-trust-tier-records", type=int, default=None)
    parser.add_argument("--require-applied", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    paths = TraceNetCleanupRepairPaths(
        visual_text_dir=Path(args.visual_text_dir),
        trace_net_dir=Path(args.trace_net_dir),
        output_dir=Path(args.output_dir),
    )
    report = build_trace_net_cleanup_repair_quality(
        paths,
        min_input_records=args.min_input_records,
        min_repaired_records=args.min_repaired_records,
        max_remaining_prompt_template_leakage_records=args.max_remaining_prompt_template_leakage_records,
        max_remaining_section_bleed_records=args.max_remaining_section_bleed_records,
        min_improved_trust_tier_records=args.min_improved_trust_tier_records,
        require_applied=args.require_applied,
    )
    print_cleanup_repair_quality(report)
    if args.write_json:
        out = write_trace_net_cleanup_repair_quality(report, paths)
        print(f"\nJSON: {out}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
