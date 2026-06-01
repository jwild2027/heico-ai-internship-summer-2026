#!/usr/bin/env python3
"""Write the real-server access checklist and runbook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.server_access_runbook import (  # noqa: E402
    DEFAULT_JSON_OUTPUT,
    DEFAULT_MARKDOWN_OUTPUT,
    build_server_access_runbook,
    write_runbook_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a read-only real-server access checklist/runbook.")
    parser.add_argument("--server-root", default="<SERVER_ROOT>", help="Placeholder or known server root path.")
    parser.add_argument("--target-total-tb", type=float, default=5.0, help="Target archive size assumption in TiB.")
    parser.add_argument("--max-files", type=int, default=100000, help="Recommended max files for first inventory sample.")
    parser.add_argument("--pilot-pages", type=int, default=500, help="Recommended pilot OCR page count.")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--write", action="store_true", help="Write JSON and Markdown outputs.")
    args = parser.parse_args()

    report = build_server_access_runbook(
        server_root=args.server_root,
        target_total_tb=args.target_total_tb,
        max_files=args.max_files,
        pilot_pages=args.pilot_pages,
    )

    if args.write:
        write_runbook_files(report, json_output=args.json_output, markdown_output=args.markdown_output)

    print("Server access checklist/runbook")
    print(f"  Status: {report['status']}")
    print(f"  Server root: {report['server_root']}")
    print(f"  Target total TiB: {report['target_total_tb']}")
    print(f"  Max inventory files: {report['max_inventory_files']}")
    print(f"  Pilot pages: {report['pilot_pages']}")
    print(f"  Checklist items: {len(report['checklist'])}")
    print(f"  Required before processing: {report['required_open_questions']}")
    print(f"  Runbook steps: {len(report['runbook_steps'])}")
    print("\nFirst run commands:")
    for step in report["runbook_steps"][:4]:
        print(f"  {step['number']}. {step['name']}")
        print(f"     {step['command']}")
    if args.write:
        print("\nFiles written:")
        print(f"  JSON: {args.json_output}")
        print(f"  Markdown: {args.markdown_output}")
    else:
        print("\nUse --write to save JSON and Markdown outputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
