#!/usr/bin/env python3
"""Run a controlled changed-page incremental smoke test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.incremental_changed_page_smoke import (  # noqa: E402
    DEFAULT_WORK_DIR,
    format_changed_page_smoke_report,
    run_changed_page_smoke_test,
    write_changed_page_smoke_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--sample-part", default="120-37313-001")
    parser.add_argument("--dry-run", action="store_true", help="Plan the smoke test but do not execute changed-page backend commands.")
    parser.add_argument("--keep-work-dir", action="store_true", help="Do not remove the smoke work directory before preparing the test.")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/incremental_smoke/changed_page_smoke.json")
    args = parser.parse_args(argv)

    report = run_changed_page_smoke_test(
        config_path=args.config,
        work_dir=args.work_dir,
        sample_part=args.sample_part or None,
        dry_run=args.dry_run,
        reset_work_dir=not args.keep_work_dir,
    )
    print(format_changed_page_smoke_report(report))

    if args.write_json:
        path = write_changed_page_smoke_json(report, args.json_output)
        print()
        print(f"JSON: {path}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
