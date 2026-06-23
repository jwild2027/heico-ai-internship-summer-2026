#!/usr/bin/env python3
"""Run TRACE-Net E2E codebase checklist v1."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_codebase_checklist_v1 import build_checklist, render_terminal_checklist, write_report_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net E2E codebase checklist v1.")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect.")
    parser.add_argument("--output-dir", default="", help="Optional output directory for JSON/Markdown reports.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of terminal checklist.")
    parser.add_argument("--fail-on-blocking", action="store_true", help="Exit nonzero when MISSING/FAIL items exist.")
    args = parser.parse_args(argv)

    report = build_checklist(Path(args.repo_root))
    if args.output_dir:
        paths = write_report_files(report, args.output_dir)
        report = {**report, "written_paths": paths}

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_terminal_checklist(report), end="")
        if args.output_dir:
            print("Reports written:")
            for k, v in report.get("written_paths", {}).items():
                print(f"- {k}: {v}")

    if args.fail_on_blocking and int(report.get("blocking_count", 0) or 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
