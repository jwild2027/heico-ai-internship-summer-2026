from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.page_image_recognition import (  # noqa: E402
    DEFAULT_CONTEXT_FILE,
    DEFAULT_EXPORT_DIR,
    DEFAULT_OUTPUT,
    print_report,
    run_page_image_recognition_audit,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TIFF pages with lightweight local image-recognition features.")
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--context-file", type=Path, default=DEFAULT_CONTEXT_FILE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-graph-overlay", action="store_true", help="Write graph-ready image analysis overlay nodes/edges.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary, records = run_page_image_recognition_audit(
        export_dir=args.export_dir,
        context_file=args.context_file,
        limit=args.limit,
        sample_limit=args.sample_limit,
        write_graph_overlay=args.write_graph_overlay,
        output_path=args.json_output,
    )
    print_report(summary)
    if args.write_json:
        write_report(args.json_output, summary, records)
        print(f"\nJSON: {args.json_output}")
    if args.strict and summary.status != "OK":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
