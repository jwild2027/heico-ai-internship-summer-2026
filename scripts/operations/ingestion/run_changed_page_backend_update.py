#!/usr/bin/env python
"""Update backend search/catalog/RAG rows for changed TIFF pages only."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.local_config import load_local_config  # noqa: E402
from tiff.changed_page_backend import run_changed_page_backend_update, write_summary_json  # noqa: E402


def _cfg_value(cfg, *names: str, default=None):
    for name in names:
        if hasattr(cfg, name):
            value = getattr(cfg, name)
            if value not in (None, ""):
                return value
    if isinstance(cfg, dict):
        for name in names:
            value = cfg.get(name)
            if value not in (None, ""):
                return value
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply page-scoped backend updates for local_data/changed_tiffs.txt.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--rescarta-export-dir", default=None)
    parser.add_argument("--changed-list", default=None)
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--questions", default=None)
    parser.add_argument("--summary-json", default="local_data/pipeline_runs/latest_changed_page_backend_update.json")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--overlap-chars", type=int, default=180)
    args = parser.parse_args()

    cfg = load_local_config(args.config) if Path(args.config).exists() else {}
    db_path = args.db_path or _cfg_value(cfg, "db_path", "search_db", "search_db_path", default="local_data/db/tiff_search.db")
    export_root = args.rescarta_export_dir or _cfg_value(cfg, "rescarta_export_dir", "rescarta_exports", default="local_data/rescarta_exports")
    changed_list = args.changed_list or _cfg_value(cfg, "changed_tiffs", "changed_tiffs_path", "changed_list", default="local_data/changed_tiffs.txt")
    embed_model = args.embed_model or _cfg_value(cfg, "embed_model", "embedding_model", default="bge-m3:latest")
    questions = args.questions or _cfg_value(cfg, "eval_questions", "questions", default="local_data/evals/rag_eval_questions.json")

    summary = run_changed_page_backend_update(
        export_root=export_root,
        db_path=db_path,
        changed_list_path=changed_list,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )
    write_summary_json(summary, args.summary_json)

    print("Changed-page backend update complete")
    print(f"  Changed files: {summary.changed_files}")
    print(f"  Affected pages: {summary.affected_pages}")
    print(f"  Search pages updated: {summary.search_pages_updated}")
    print(f"  Part mentions updated: {summary.part_mentions_updated}")
    print(f"  Clean pages updated: {summary.clean_pages_updated}")
    print(f"  Part catalog rows updated: {summary.part_catalog_rows_updated}")
    print(f"  Canonical parts updated: {summary.canonical_parts_updated}")
    print(f"  RAG chunks updated: {summary.rag_chunks_updated}")
    print(f"  Stale embeddings deleted: {summary.stale_embeddings_deleted}")
    print(f"  Summary JSON: {args.summary_json}")
    if summary.unmatched_changed_files:
        print("  Unmatched changed TIFF files:")
        for item in summary.unmatched_changed_files[:20]:
            print(f"    - {item}")

    if summary.affected_pages == 0:
        print("No affected search pages were found; skipping embeddings/QA/eval.")
        return 0

    if not args.skip_embeddings:
        cmd = [sys.executable, "scripts/build/embeddings/build_rag_embeddings.py", "--db-path", str(db_path), "--model", str(embed_model)]
        print("\nRunning incremental embeddings:")
        print("  " + " ".join(cmd))
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            return proc.returncode

    if not args.skip_qa:
        cmd = [sys.executable, "scripts/maintenance/ingestion/report_part_catalog_qa.py", "--config", args.config]
        print("\nRunning QA report:")
        print("  " + " ".join(cmd))
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            return proc.returncode

    if not args.skip_eval:
        cmd = [sys.executable, "scripts/benchmark/evaluate_rag_questions.py", "--config", args.config, "--questions", str(questions)]
        print("\nRunning RAG eval:")
        print("  " + " ".join(cmd))
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            return proc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
