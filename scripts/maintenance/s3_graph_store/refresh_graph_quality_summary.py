#!/usr/bin/env python
"""Refresh graph-quality summary into the latest pipeline manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.document_graph_quality import (  # noqa: E402
    DEFAULT_CONTEXT_FILE,
    DEFAULT_GRAPH_DIR,
    DEFAULT_GRAPH_QUALITY_JSON,
    DEFAULT_REALISTIC_QUERY_TRACE_RESULTS,
    DEFAULT_USER_QUERY_RESULTS,
    build_graph_quality_result,
    write_graph_quality_json,
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="local_data/pipeline_runs/latest_backend_pipeline.json")
    parser.add_argument("--graph-dir", default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--context-file", default=DEFAULT_CONTEXT_FILE)
    parser.add_argument("--user-query-results", default=DEFAULT_USER_QUERY_RESULTS)
    parser.add_argument("--realistic-query-results", default=DEFAULT_REALISTIC_QUERY_TRACE_RESULTS)
    parser.add_argument("--graph-quality-json", default=DEFAULT_GRAPH_QUALITY_JSON)
    args = parser.parse_args()

    result = build_graph_quality_result(
        graph_dir=args.graph_dir,
        context_file=args.context_file,
        user_query_results=args.user_query_results,
        realistic_query_results=args.realistic_query_results,
    )
    write_graph_quality_json(result, args.graph_quality_json)
    manifest_path = Path(args.manifest)
    manifest = _load_json(manifest_path)
    if not manifest:
        print(f"No manifest updated: {manifest_path}")
        return 1
    manifest["graph_quality_summary"] = result.summary
    _write_json(manifest_path, manifest)

    # Also update the run-specific manifest if it sits next to latest and matches the run id.
    run_id = str(manifest.get("run_id") or "")
    pipeline_name = str(manifest.get("pipeline") or "tiff_backend_pipeline")
    run_manifest = manifest_path.parent / f"{pipeline_name}_{run_id}.json" if run_id else None
    if run_manifest and run_manifest.exists():
        run_payload = _load_json(run_manifest)
        if run_payload:
            run_payload["graph_quality_summary"] = result.summary
            _write_json(run_manifest, run_payload)

    print("Refreshed graph quality summary:")
    print(f"  Manifest: {manifest_path}")
    if run_manifest and run_manifest.exists():
        print(f"  Run manifest: {run_manifest}")
    print(f"  Graph quality JSON: {args.graph_quality_json}")
    print(f"  Status: {result.status}")
    print(f"  Page contexts: {result.summary.get('page_context_nodes')}/{result.summary.get('page_nodes')}")
    print(f"  Pages without context: {result.summary.get('pages_without_context')}")
    print(f"  Pages without source links: {result.summary.get('pages_without_source_links')}")
    print(f"  Realistic query trace: {result.summary.get('realistic_query_pass')}/{result.summary.get('realistic_query_total')} cases; failures={result.summary.get('realistic_query_fail')}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
