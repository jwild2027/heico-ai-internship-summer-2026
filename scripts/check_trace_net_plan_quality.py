from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net import TraceNetPaths, build_trace_net_quality, print_trace_net_quality, write_trace_net_quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route plan quality.")
    parser.add_argument("--export-dir", default="local_data/organization/export")
    parser.add_argument("--trait-dir", default="local_data/organization/entity_traits")
    parser.add_argument("--visual-text-dir", default="local_data/organization/visual_text")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    paths = TraceNetPaths(
        export_dir=Path(args.export_dir),
        trait_dir=Path(args.trait_dir),
        visual_text_dir=Path(args.visual_text_dir),
        output_dir=Path(args.output_dir),
    )
    quality = build_trace_net_quality(paths, min_records=args.min_records, expected_pages=args.expect_pages)
    print_trace_net_quality(quality)
    if args.write_json:
        out = write_trace_net_quality(quality, paths)
        print(f"\nJSON: {out}")
    return 0 if quality.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
