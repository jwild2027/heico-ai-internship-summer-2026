#!/usr/bin/env python
"""Run the local TIFF backend rebuild/evaluation pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.pipeline_manifest import (  # noqa: E402
    DEFAULT_MANIFEST_DIR,
    build_pipeline_manifest,
    write_pipeline_manifest,
)
from tiff.pipeline_runner import (  # noqa: E402
    build_pipeline_steps,
    config_from_file,
    format_command,
    merge_config,
    run_pipeline,
    successful,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local TIFF search/RAG backend pipeline.")
    parser.add_argument("--config", default="local_config.yaml", help="Path to local_config.yaml.")
    parser.add_argument("--db-path", default=None, help="Override search/RAG SQLite DB path.")
    parser.add_argument("--rescarta-export-dir", default=None, help="Override ResCarta staging export root.")
    parser.add_argument("--embed-model", default=None, help="Override Ollama embedding model.")
    parser.add_argument("--questions", default=None, help="Override RAG evaluation question JSON path.")
    parser.add_argument("--reset-embeddings", action="store_true", help="Rebuild all embeddings with --reset.")
    parser.add_argument("--skip-search-index", action="store_true", help="Skip rebuilding the search index.")
    parser.add_argument("--skip-part-catalog", action="store_true", help="Skip OCR cleanup and part catalog rebuild.")
    parser.add_argument("--skip-rag-chunks", action="store_true", help="Skip RAG chunk rebuild.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip embedding rebuild.")
    parser.add_argument("--skip-qa", action="store_true", help="Skip part catalog QA report and QA triage.")
    parser.add_argument("--skip-qa-triage", action="store_true", help="Run raw QA but skip the QA severity triage step.")
    parser.add_argument("--skip-eval", action="store_true", help="Skip RAG evaluation report.")
    parser.add_argument("--skip-source-audit", action="store_true", help="Skip source-link audit checks.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue running later steps after a failed step.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument("--manifest-dir", default=DEFAULT_MANIFEST_DIR, help="Directory for pipeline run manifests.")
    parser.add_argument("--skip-manifest", action="store_true", help="Do not write a JSON run manifest.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = config_from_file(args.config)
    config = merge_config(
        config,
        db_path=args.db_path,
        rescarta_export_dir=args.rescarta_export_dir,
        embed_model=args.embed_model,
        questions_path=args.questions,
        reset_embeddings=True if args.reset_embeddings else None,
        skip_search_index=True if args.skip_search_index else None,
        skip_part_catalog=True if args.skip_part_catalog else None,
        skip_rag_chunks=True if args.skip_rag_chunks else None,
        skip_embeddings=True if args.skip_embeddings else None,
        skip_qa=True if args.skip_qa else None,
        skip_qa_triage=True if args.skip_qa_triage else None,
        skip_eval=True if args.skip_eval else None,
        skip_source_audit=True if args.skip_source_audit else None,
    )
    steps = build_pipeline_steps(config)

    print("TIFF backend pipeline")
    print(f"  DB: {config.db_path}")
    print(f"  ResCarta export dir: {config.rescarta_export_dir}")
    print(f"  Embed model: {config.embed_model}")
    print(f"  Config: {config.config_path}")
    print(f"  Eval questions: {config.questions_path}")
    print(f"  Steps: {len(steps)}")
    print("")
    for index, step in enumerate(steps, start=1):
        print(f"[{index}/{len(steps)}] {step.name}")
        if step.description:
            print(f"  {step.description}")
        print(f"  {format_command(step.command)}")

    started_at = _utc_iso()
    if args.dry_run:
        print("\nDry run only. No commands executed.")
        if not args.skip_manifest:
            manifest = build_pipeline_manifest(
                config=config,
                results=run_pipeline(config, dry_run=True, cwd=REPO_ROOT),
                started_at=started_at,
                ended_at=_utc_iso(),
                dry_run=True,
                status="dry_run",
            )
            timestamped, latest = write_pipeline_manifest(manifest, args.manifest_dir)
            print(f"Manifest: {timestamped}")
            print(f"Latest manifest: {latest}")
        return 0

    print("\nRunning pipeline...\n")
    results = run_pipeline(config, continue_on_error=args.continue_on_error, cwd=REPO_ROOT)
    ended_at = _utc_iso()

    print("\nPipeline summary")
    for result in results:
        status = "OK" if result.returncode == 0 else f"FAILED ({result.returncode})"
        elapsed = getattr(result, "elapsed_seconds", 0.0)
        print(f"  {result.step.name}: {status} ({elapsed:.2f}s)")

    ok = successful(results)
    if not args.skip_manifest:
        manifest = build_pipeline_manifest(
            config=config,
            results=results,
            started_at=started_at,
            ended_at=ended_at,
            dry_run=False,
            status="ok" if ok else "failed",
        )
        timestamped, latest = write_pipeline_manifest(manifest, args.manifest_dir)
        print(f"\nManifest: {timestamped}")
        print(f"Latest manifest: {latest}")

    if ok:
        print("\nPipeline complete.")
        return 0
    print("\nPipeline stopped with errors.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
