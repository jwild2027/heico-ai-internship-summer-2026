#!/usr/bin/env python
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.incremental_state import IncrementalStateDB, write_changed_list
from tiff.incremental_pipeline import load_pipeline_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test incremental change detection in an isolated copy folder.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--work-dir", default="local_data/incremental_smoke")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--hash-mode", choices=["stat", "content"], default="stat")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.config)
    src_root = Path(cfg.tiff_root)
    tiffs = sorted(p for p in src_root.rglob("*") if p.is_file() and p.suffix.lower() in {".tif", ".tiff"})
    if not tiffs:
        print(f"No TIFF files found under {src_root}")
        return 1

    work = Path(args.work_dir)
    if work.exists() and not args.keep:
        shutil.rmtree(work)
    smoke_root = work / "source"
    smoke_root.mkdir(parents=True, exist_ok=True)
    for idx, path in enumerate(tiffs[: args.limit], start=1):
        shutil.copy2(path, smoke_root / f"sample_{idx:03d}{path.suffix.lower()}")

    state_db = work / "state.db"
    changed_list = work / "changed_tiffs.txt"
    state = IncrementalStateDB(state_db)

    first = state.detect_changes(smoke_root, hash_mode=args.hash_mode)
    write_changed_list(first.changed_paths, changed_list)
    state.commit_summary(first, status="smoke_baseline")

    second = state.detect_changes(smoke_root, hash_mode=args.hash_mode)

    added = smoke_root / f"sample_added{tiffs[0].suffix.lower()}"
    shutil.copy2(tiffs[0], added)
    third = state.detect_changes(smoke_root, hash_mode=args.hash_mode)
    write_changed_list(third.changed_paths, changed_list)

    print("Incremental smoke test")
    print(f"  Work dir: {work}")
    print(f"  Hash mode: {args.hash_mode}")
    print(f"  Baseline new files: {first.new_files}")
    print(f"  Second-run changed list count: {second.changed_list_count}")
    print(f"  After adding one TIFF changed list count: {third.changed_list_count}")
    print(f"  Changed list: {changed_list}")
    if first.new_files != min(args.limit, len(tiffs)) or second.changed_list_count != 0 or third.changed_list_count != 1:
        print("Smoke test FAILED")
        return 1
    print("Smoke test PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
