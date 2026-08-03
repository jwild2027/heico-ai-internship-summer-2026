#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.incremental_pipeline import load_pipeline_config, run_incremental_pipeline
from tiff.incremental_state import IncrementalStateDB


def print_plan(result, cfg, dry_run: bool) -> None:
    s = result.summary
    print("Incremental TIFF pipeline")
    print(f"  TIFF root: {cfg.tiff_root}")
    print(f"  State DB: {cfg.state_db}")
    print(f"  Changed list: {cfg.changed_list}")
    print(f"  Hash mode: {cfg.hash_mode}")
    print()
    print("Changed detection summary")
    print(f"  Files seen: {s.files_seen}")
    print(f"  New files: {s.new_files}")
    print(f"  Changed files: {s.changed_files}")
    print(f"  Unchanged files: {s.unchanged_files}")
    print(f"  Missing files: {s.missing_files}")
    print(f"  Changed list count: {s.changed_list_count}")
    print()
    print("Planned commands")
    for idx, command in enumerate(result.commands, start=1):
        print(f"[{idx}/{len(result.commands)}] {command.name}")
        print(f"  {command.description}")
        if command.skip_reason:
            print(f"  SKIP: {command.skip_reason}")
        else:
            print("  " + " ".join(command.argv))
    print()
    if dry_run:
        print("Dry run only. Changed list was written, state DB was not updated, and commands were not executed.")
        return
    print("Incremental pipeline summary")
    for item in result.results:
        if item.status == "SKIPPED":
            print(f"  {item.name}: SKIPPED ({item.skip_reason})")
        elif item.status == "FAILED":
            print(f"  {item.name}: FAILED (exit {item.returncode})")
        else:
            print(f"  {item.name}: OK")
    print(f"  state_commit: {'OK' if result.state_committed else 'SKIPPED'} ({result.commit_message})")
    print()
    print("Incremental pipeline complete.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe incremental TIFF OCR/search/RAG backend pipeline.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--tiff-root")
    parser.add_argument("--state-db")
    parser.add_argument("--changed-list")
    parser.add_argument("--hash-mode", choices=["stat", "content"])
    parser.add_argument("--db-path")
    parser.add_argument("--rescarta-export-dir")
    parser.add_argument("--embed-model")
    parser.add_argument("--questions")
    parser.add_argument("--json-dir")
    parser.add_argument("--scan-db")
    parser.add_argument("--tesseract-cmd")
    parser.add_argument("--backend-mode", choices=["full", "changed-pages"], help="Use full backend rebuild or page-scoped changed-page backend update.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--skip-backend", action="store_true")
    parser.add_argument("--run-backend-when-unchanged", action="store_true")
    parser.add_argument("--reset-embeddings", action="store_true")
    parser.add_argument("--reset-state", action="store_true", help="Clear incremental state DB before scanning.")
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(
        args.config,
        tiff_root=args.tiff_root,
        state_db=args.state_db,
        changed_list=args.changed_list,
        hash_mode=args.hash_mode,
        db_path=args.db_path,
        rescarta_export_dir=args.rescarta_export_dir,
        embed_model=args.embed_model,
        questions=args.questions,
        json_dir=args.json_dir,
        scan_db=args.scan_db,
        tesseract_cmd=args.tesseract_cmd,
        backend_mode=args.backend_mode,
    )
    if args.reset_state:
        IncrementalStateDB(cfg.state_db).reset()
        print(f"Reset incremental state DB: {cfg.state_db}")
    result = run_incremental_pipeline(
        cfg,
        dry_run=args.dry_run,
        skip_ocr=args.skip_ocr,
        skip_backend=args.skip_backend,
        run_backend_when_unchanged=args.run_backend_when_unchanged,
        reset_embeddings=args.reset_embeddings,
    )
    print_plan(result, cfg, args.dry_run)
    failed = [r for r in result.results if r.status == "FAILED"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
