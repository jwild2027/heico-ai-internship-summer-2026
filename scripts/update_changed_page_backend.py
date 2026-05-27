#!/usr/bin/env python3
"""Update search/catalog/RAG rows for changed TIFF pages only.

This is the page-scoped backend path used by the safe incremental pipeline.
It intentionally fails on unmatched changed TIFF paths unless --allow-unmatched
is set, because otherwise the incremental state DB could mark a file processed
even though the backend never found the affected source page.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.changed_page_update import run_changed_page_backend_update  # noqa: E402
from tiff.local_config import load_local_config  # noqa: E402


def _run_step(argv: Sequence[str], *, label: str) -> int:
    print(f"\nRunning {label}...")
    print("  " + " ".join(str(part) for part in argv))
    proc = subprocess.run(list(argv), check=False)
    if proc.returncode != 0:
        print(f"{label} failed with exit code {proc.returncode}.")
    return int(proc.returncode)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument(
        "--skip-triage",
        action="store_true",
        help="Do not run command-line QA severity triage after raw QA. Normally leave this off.",
    )
    parser.add_argument(
        "--skip-source-audit",
        action="store_true",
        help="Do not run source-link audit after the changed-page update.",
    )
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument(
        "--allow-unmatched",
        action="store_true",
        help="Return success even if changed paths do not match indexed pages. Use only for diagnostics.",
    )
    parser.add_argument("--source-audit-json", default="local_data/source_links/source_link_audit.json")
    parser.add_argument("--triage-limit", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
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
    if getattr(summary, "warnings", None):
        print("  Warnings:")
        for warning in summary.warnings:
            print(f"    - {warning}")

    if summary.changed_paths and summary.unmatched_paths and not args.allow_unmatched:
        print()
        print("Changed-page update did not match every changed TIFF to an indexed source page.")
        print("State should not be committed. Re-run in full backend mode or inspect the changed list.")
        return 3

    if summary.changed_paths and summary.matched_pages == 0 and not args.allow_unmatched:
        print()
        print("Changed-page update matched zero pages for a non-empty changed list.")
        print("State should not be committed. Re-run in full backend mode or inspect the changed list.")
        return 3

    if summary.matched_pages == 0:
        print()
        print("No matched pages to update. Post-update QA/eval/source-audit skipped.")
        return 0

    if not args.skip_embeddings:
        code = _run_step(
            [sys.executable, "scripts/build_rag_embeddings.py", "--db-path", str(db_path), "--model", str(embed_model)],
            label="embedding refresh",
        )
        if code != 0:
            return code

    if not args.skip_qa:
        code = _run_step([sys.executable, "scripts/report_part_catalog_qa.py", "--config", args.config], label="part catalog QA")
        if code != 0:
            return code
        if not args.skip_triage:
            code = _run_step(
                [
                    sys.executable,
                    "scripts/triage_part_catalog_qa.py",
                    "--replace-all-report",
                    "--limit",
                    str(max(0, args.triage_limit)),
                ],
                label="part catalog QA triage",
            )
            if code != 0:
                return code

    if not args.skip_source_audit:
        code = _run_step(
            [
                sys.executable,
                "scripts/audit_source_links.py",
                "--strict",
                "--write-json",
                "--json-output",
                args.source_audit_json,
                "--print-limit",
                "5",
                "--config",
                args.config,
            ],
            label="source-link audit",
        )
        if code != 0:
            return code

    if not args.skip_eval:
        code = _run_step(
            [sys.executable, "scripts/evaluate_rag_questions.py", "--config", args.config, "--questions", args.questions],
            label="RAG eval",
        )
        if code != 0:
            return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
