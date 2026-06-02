from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_table_tiles import (
    DEFAULT_OUTPUT_DIR,
    TraceNetTableTilePaths,
    build_table_tile_quality,
    print_table_tile_quality,
    write_table_tile_quality,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table crop/tile artifacts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--min-ok-records", type=int, default=1)
    parser.add_argument("--min-tile-images", type=int, default=1)
    parser.add_argument("--max-missing-image-records", type=int, default=0)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    paths = TraceNetTableTilePaths(output_dir=Path(args.output_dir))
    quality = build_table_tile_quality(
        paths,
        min_records=args.min_records,
        expect_pages=args.expect_pages,
        min_ok_records=args.min_ok_records,
        min_tile_images=args.min_tile_images,
        max_missing_image_records=args.max_missing_image_records,
        require_status_ok=not args.allow_partial,
    )
    if args.write_json:
        write_table_tile_quality(quality, paths)
    print_table_tile_quality(quality)
    if args.write_json:
        print(f"\nJSON: {paths.quality}")
    return 0 if quality.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
