#!/usr/bin/env python
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.changed_page_update import run_changed_page_backend_update
from tiff.local_config import load_local_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update search/catalog/RAG rows for changed TIFF pages only.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--db-path")
    parser.add_argument("--rescarta-export-dir")
    parser.add_argument("--changed-list", default="local_data/changed_tiffs.txt")
    parser.add_argument("--embed-model")
    parser.add_argument("--questions", default="local_data/evals/rag_eval_questions.json")
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--overlap-chars", type=int, default=180)
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_local_config(args.config)
    db_path = Path(args.db_path or cfg.get("db_path", "local_data/db/tiff_search.db"))
    export_root = Path(args.rescarta_export_dir or cfg.get("rescarta_export_dir", "local_data/rescarta_exports"))
    embed_model = args.embed_model or cfg.get("embed_model", "bge-m3:latest")

    summary = run_changed_page_backend_update(
        db_path=db_path,
        export_root=export_root,
        changed_list_path=args.changed_list,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )

    print("Changed-page backend update complete")
    print(f"  DB: {summary.db_path}")
    print(f"  Export root: {summary.export_root}")
    print(f"  Changed paths: {summary.changed_paths}")
    print(f"  Matched pages: {summary.matched_pages}")
    print(f"  Unmatched paths: {summary.unmatched_paths}")
    print(f"  Pages updated: {summary.pages_updated}")
    print(f"  Part mentions updated: {summary.part_mentions_updated}")
    print(f"  Clean pages updated: {summary.clean_pages_updated}")
    print(f"  Catalog rows updated: {summary.catalog_rows_updated}")
    print(f"  Canonical parts updated: {summary.canonical_parts_updated}")
    print(f"  RAG chunks updated: {summary.rag_chunks_updated}")
    print(f"  Stale embeddings deleted: {summary.stale_embeddings_deleted}")
    if summary.warnings:
        print("  Warnings:")
        for warning in summary.warnings:
            print(f"    - {warning}")

    if summary.matched_pages == 0:
        return 0

    if not args.skip_embeddings:
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/build_rag_embeddings.py",
                "--db-path",
                str(db_path),
                "--model",
                embed_model,
            ],
            check=False,
        )
        if proc.returncode != 0:
            return proc.returncode

    if not args.skip_qa:
        proc = subprocess.run(
            [sys.executable, "scripts/report_part_catalog_qa.py", "--config", args.config],
            check=False,
        )
        if proc.returncode != 0:
            return proc.returncode

    if not args.skip_eval:
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/evaluate_rag_questions.py",
                "--config",
                args.config,
                "--questions",
                args.questions,
            ],
            check=False,
        )
        if proc.returncode != 0:
            return proc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
