#!/usr/bin/env python3
"""Build TRACE-Net Page Context Pack v3."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import json
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a TRACE-Net page context pack v3 JSON artifact.")
    parser.add_argument("--question", default="", help="User question used to select pages/entities.")
    parser.add_argument("--pages", nargs="*", default=[], help="Explicit page numbers or page IDs to include.")
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--route-manifest", default=None)
    parser.add_argument("--graph-export", default=None)
    parser.add_argument("--ocr-records", default=None)
    parser.add_argument("--table-evidence", default=None)
    parser.add_argument("--exact-part-records", default=None)
    parser.add_argument("--visual-summaries", default=None)
    parser.add_argument("--vector-hits", default=None)
    parser.add_argument(
        "--output",
        default="local_data/organization/trace_net/page_context_pack_v3/trace_net_page_context_pack_v3.json",
    )
    return parser.parse_args()


def _warn_missing_optional_path(label: str, value: str | None) -> None:
    if value and not Path(value).exists():
        print(f"WARNING: {label} path not found: {value}", file=sys.stderr)


def _resolve_sidecar_path(base_path: str | None, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    candidates = [p]
    if base_path:
        base = Path(base_path)
        candidates.append(base.parent / value)
    candidates.append(REPO_ROOT / value)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except UnicodeDecodeError:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def load_artifact_with_sidecars(path: str | None) -> Any:
    """Load a JSON artifact and hydrate common linked JSONL sidecars.

    Some visual/OpenWebUI route artifacts are manifests whose real page cards
    live in a `records_jsonl_path` or similar sidecar.  v3.2 follows those
    read-only sidecars so page 202-style image routes can attach visual
    guidance instead of only a manifest summary.
    """
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return payload
    merged = dict(payload)
    linked_keys = (
        "records_jsonl_path",
        "records_path",
        "sample_records_jsonl_path",
        "visual_records_jsonl_path",
        "llava_records_jsonl_path",
    )
    sidecar_records: list[dict[str, Any]] = []
    for key in linked_keys:
        sidecar = _resolve_sidecar_path(path, str(merged.get(key) or ""))
        if sidecar and sidecar.suffix.lower() == ".jsonl":
            sidecar_records.extend(_read_jsonl(sidecar))
        elif sidecar and sidecar.suffix.lower() == ".json":
            side_payload = load_json(sidecar, {})
            if isinstance(side_payload, list):
                sidecar_records.extend([x for x in side_payload if isinstance(x, dict)])
            elif isinstance(side_payload, dict) and isinstance(side_payload.get("records"), list):
                sidecar_records.extend([x for x in side_payload["records"] if isinstance(x, dict)])
    if sidecar_records:
        existing = merged.get("records") if isinstance(merged.get("records"), list) else []
        merged["records"] = list(existing) + sidecar_records
        merged["linked_sidecar_record_count"] = len(sidecar_records)
    return merged


def main() -> int:
    args = parse_args()
    for label, value in (
        ("route_manifest", args.route_manifest),
        ("graph_export", args.graph_export),
        ("ocr_records", args.ocr_records),
        ("table_evidence", args.table_evidence),
        ("exact_part_records", args.exact_part_records),
        ("visual_summaries", args.visual_summaries),
        ("vector_hits", args.vector_hits),
    ):
        _warn_missing_optional_path(label, value)

    pack = build_page_context_pack_v3(
        question=args.question,
        requested_pages=args.pages,
        max_pages=args.max_pages,
        route_manifest=load_artifact_with_sidecars(args.route_manifest),
        graph_export=load_artifact_with_sidecars(args.graph_export),
        ocr_records=load_artifact_with_sidecars(args.ocr_records),
        table_evidence=load_artifact_with_sidecars(args.table_evidence),
        exact_part_records=load_artifact_with_sidecars(args.exact_part_records),
        visual_summaries=load_artifact_with_sidecars(args.visual_summaries),
        vector_hits=load_artifact_with_sidecars(args.vector_hits),
    )
    write_json(args.output, pack)
    summary = pack.get("summary", {})
    print(f"Wrote: {args.output}")
    print(f"quality_status: {pack.get('quality_status')}")
    print(f"selected_page_count: {summary.get('selected_page_count')}")
    print(f"source_trace_ready_page_count: {summary.get('source_trace_ready_page_count')}")
    print(f"proof_record_count: {summary.get('proof_record_count')}")
    print(f"guidance_record_count: {summary.get('guidance_record_count')}")
    print(f"source_file_count: {summary.get('source_file_count')}")
    print(f"source_link_count: {summary.get('source_link_count')}")
    print(f"ocr_excerpt_count: {summary.get('ocr_excerpt_count')}")
    print(f"visual_guidance_count: {summary.get('visual_guidance_count')}")
    return 0 if pack.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
