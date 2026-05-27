#!/usr/bin/env python
"""Smoke-test changed-page backend mode against the real local sample folder.

This script safely touches one TIFF file in the configured source TIFF root so
stat-based incremental detection sees exactly one changed file. It then runs the
incremental pipeline in changed-page backend mode and verifies that a follow-up
preview sees no remaining changes.

It changes only file timestamps, not TIFF file contents.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.incremental_pipeline import load_pipeline_config


def find_first_tiff(root: Path) -> Path:
    for pattern in ("*.tif", "*.tiff", "*.TIF", "*.TIFF"):
        matches = sorted(p for p in root.rglob(pattern) if p.is_file())
        if matches:
            return matches[0]
    raise FileNotFoundError(f"No TIFF files found under {root}")


def touch_file(path: Path) -> float:
    stat = path.stat()
    # Add enough time to avoid coarse timestamp-resolution issues.
    new_mtime = max(time.time(), stat.st_mtime + 5.0)
    os.utime(path, (new_mtime, new_mtime))
    return new_mtime


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    print("\n$ " + " ".join(argv))
    proc = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout)
    return proc


def extract_changed_list_count(output: str) -> int | None:
    match = re.search(r"Changed list count:\s*(\d+)", output)
    if not match:
        return None
    return int(match.group(1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Touch one TIFF and verify changed-page backend mode.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--target-tiff", help="Specific TIFF to touch; defaults to first TIFF under configured root.")
    parser.add_argument("--skip-followup-check", action="store_true")
    parser.add_argument("--no-run", action="store_true", help="Only print what would be touched/run.")
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.config)
    root = Path(cfg.tiff_root)
    target = Path(args.target_tiff) if args.target_tiff else find_first_tiff(root)
    if not target.exists():
        print(f"ERROR: target TIFF does not exist: {target}")
        return 2

    print("Changed-page backend smoke test")
    print(f"  Config: {args.config}")
    print(f"  TIFF root: {root}")
    print(f"  Target TIFF: {target}")
    print(f"  Backend mode: changed-pages")
    print("  Note: this changes only the file timestamp, not file contents.")

    run_argv = [
        sys.executable,
        "scripts/run_incremental_tiff_pipeline.py",
        "--config",
        args.config,
        "--backend-mode",
        "changed-pages",
    ]
    followup_argv = [
        sys.executable,
        "scripts/run_incremental_tiff_pipeline.py",
        "--config",
        args.config,
        "--backend-mode",
        "changed-pages",
        "--dry-run",
    ]

    if args.no_run:
        print("\nWould touch:")
        print(f"  {target}")
        print("\nWould run:")
        print("  " + " ".join(run_argv))
        if not args.skip_followup_check:
            print("  " + " ".join(followup_argv))
        return 0

    new_mtime = touch_file(target)
    print(f"\nTouched target TIFF. New mtime: {new_mtime:.3f}")

    proc = run_command(run_argv)
    if proc.returncode != 0:
        print("ERROR: changed-page incremental pipeline failed.")
        return proc.returncode

    count = extract_changed_list_count(proc.stdout)
    if count is None:
        print("WARNING: could not find 'Changed list count' in pipeline output.")
    elif count != 1:
        print(f"ERROR: expected Changed list count: 1, got {count}.")
        print("This usually means the state DB was not at a clean baseline before the smoke test.")
        return 3

    required_markers = [
        "ocr_changed_tiffs: OK",
        "backend_pipeline: OK",
        "state_commit: OK",
    ]
    missing = [marker for marker in required_markers if marker not in proc.stdout]
    if missing:
        print("ERROR: changed-page run did not show expected success markers:")
        for marker in missing:
            print(f"  - {marker}")
        return 4

    if not args.skip_followup_check:
        followup = run_command(followup_argv)
        if followup.returncode != 0:
            print("ERROR: follow-up dry run failed.")
            return followup.returncode
        followup_count = extract_changed_list_count(followup.stdout)
        if followup_count != 0:
            print(f"ERROR: expected follow-up Changed list count: 0, got {followup_count}.")
            return 5

    print("\nChanged-page backend smoke test PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
