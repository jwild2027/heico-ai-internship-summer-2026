"""Refresh visual-text extraction summary artifacts without calling a vision model.

This is useful when a long visual-text run checkpointed records/corpus/graph artifacts
but crashed before writing the final summary JSON. The script rebuilds the summary from
``visual_text_extraction.jsonl`` and rewrites the corpus/graph overlay from the same
records so counts are consistent.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

# Allow direct script execution from the repo root on Windows/Git Bash:
#   python scripts/refresh_visual_text_extraction_summary.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.visual_text_extraction import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_OCR_MAX_CHARS,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_PROMPT_VERSION,
    ExtractionOptions,
    VisualTextPaths,
    _build_graph_overlay,
    _existing_records,
    _write_json,
    _write_visual_text_artifacts,
    build_visual_text_summary,
    load_page_cards,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _first_nonempty(records: Sequence[Mapping[str, Any]], key: str, default: Any = None) -> Any:
    for record in records:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _infer_options(
    records: Sequence[Mapping[str, Any]],
    old_summary: Mapping[str, Any],
    *,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    ocr_assist: bool | None = None,
    ocr_max_chars: int | None = None,
    write_graph_overlay: bool = True,
) -> ExtractionOptions:
    inferred_provider = provider or str(old_summary.get("provider") or _first_nonempty(records, "provider", "ollama"))
    inferred_model = model or str(old_summary.get("model") or _first_nonempty(records, "model", DEFAULT_MODEL))
    inferred_prompt = prompt_version or str(
        old_summary.get("prompt_version") or _first_nonempty(records, "prompt_version", DEFAULT_PROMPT_VERSION)
    )

    if ocr_assist is None:
        old_value = old_summary.get("ocr_assist_enabled")
        if old_value is None:
            old_value = _first_nonempty(records, "ocr_assist_used", True)
        inferred_ocr_assist = bool(old_value)
    else:
        inferred_ocr_assist = bool(ocr_assist)

    if ocr_max_chars is None:
        try:
            inferred_ocr_max_chars = int(old_summary.get("ocr_max_chars") or DEFAULT_OCR_MAX_CHARS)
        except (TypeError, ValueError):
            inferred_ocr_max_chars = DEFAULT_OCR_MAX_CHARS
    else:
        inferred_ocr_max_chars = int(ocr_max_chars)

    return ExtractionOptions(
        provider=inferred_provider,
        model=inferred_model,
        ollama_base_url=DEFAULT_OLLAMA_BASE_URL,
        max_pages=None,
        overwrite=False,
        timeout_seconds=0,
        max_image_edge=0,
        temperature=0.0,
        prompt_version=inferred_prompt,
        ocr_assist=inferred_ocr_assist,
        ocr_max_chars=inferred_ocr_max_chars,
        write_graph_overlay=write_graph_overlay,
        progress=False,
        checkpoint_every=0,
        retry_error_pages_only=False,
    )


def refresh_visual_text_extraction_summary(
    paths: VisualTextPaths,
    *,
    selected_count: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    ocr_assist: bool | None = None,
    ocr_max_chars: int | None = None,
    write_graph_overlay: bool = True,
) -> dict[str, Any]:
    existing = _existing_records(paths.records_path)
    records = sorted(existing.values(), key=lambda record: str(record.get("page_id") or ""))
    if not records:
        raise RuntimeError(f"No visual-text records found at {paths.records_path}")

    old_summary = _load_json(paths.summary_path)
    options = _infer_options(
        records,
        old_summary,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        ocr_assist=ocr_assist,
        ocr_max_chars=ocr_max_chars,
        write_graph_overlay=write_graph_overlay,
    )

    try:
        total_cards = len(load_page_cards(paths.page_cards_path, paths.page_index_path))
    except Exception:
        total_cards = int(old_summary.get("total_page_cards") or 0)

    graph_nodes, graph_edges = _build_graph_overlay(records) if write_graph_overlay else ([], [])
    effective_selected_count = int(selected_count) if selected_count is not None else len(records)
    summary = build_visual_text_summary(
        records,
        selected_count=effective_selected_count,
        total_cards=total_cards,
        options=options,
        warnings=[],
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        provider_name=options.provider,
        model_name=options.model if options.provider != "planned" else "none",
    )
    summary["refreshed_from_records"] = True
    summary["previous_summary_selected_pages"] = old_summary.get("selected_pages")
    summary["previous_summary_records"] = old_summary.get("records")

    _write_visual_text_artifacts(paths, records, graph_nodes, graph_edges, write_graph_overlay)
    _write_json(paths.summary_path, summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh visual-text summary/corpus/graph artifacts from visual_text_extraction.jsonl without model calls."
    )
    parser.add_argument("--page-cards", type=Path, default=VisualTextPaths().page_cards_path)
    parser.add_argument("--page-index", type=Path, default=VisualTextPaths().page_index_path)
    parser.add_argument("--output-dir", type=Path, default=VisualTextPaths().output_dir)
    parser.add_argument("--selected-count", type=int, default=None, help="Override selected_pages; defaults to record count.")
    parser.add_argument("--provider", default=None, help="Override provider in refreshed summary.")
    parser.add_argument("--model", default=None, help="Override model in refreshed summary.")
    parser.add_argument("--prompt-version", default=None, help="Override prompt version in refreshed summary.")
    parser.add_argument("--ocr-max-chars", type=int, default=None)
    parser.add_argument("--no-ocr-assist", action="store_true")
    parser.add_argument("--no-graph-overlay", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = VisualTextPaths(
        page_cards_path=args.page_cards,
        page_index_path=args.page_index,
        output_dir=args.output_dir,
    )
    summary = refresh_visual_text_extraction_summary(
        paths,
        selected_count=args.selected_count,
        provider=args.provider,
        model=args.model,
        prompt_version=args.prompt_version,
        ocr_assist=False if args.no_ocr_assist else None,
        ocr_max_chars=args.ocr_max_chars,
        write_graph_overlay=not args.no_graph_overlay,
    )

    print("Refreshed visual text extraction summary")
    print(f"  Status: {summary.get('status')}")
    print(f"  Records: {summary.get('records')}")
    print(f"  OK records: {summary.get('ok_records')}")
    print(f"  Error records: {summary.get('error_records')}")
    print(f"  Selected pages: {summary.get('selected_pages')}")
    print(f"  Prompt version: {summary.get('prompt_version')}")
    print(f"  V2.2 records: {summary.get('visual_text_v2_2_records')}")
    print(f"  Required-section records: {summary.get('visual_text_required_sections_records')}")
    print(f"  Metadata-leakage records: {summary.get('visual_text_metadata_leakage_records')}")
    print(f"  Refusal-like records: {summary.get('visual_text_refusal_like_records')}")
    print(f"  Graph nodes: {summary.get('graph_overlay_nodes')}")
    print(f"  Graph edges: {summary.get('graph_overlay_edges')}")
    print("Files refreshed:")
    print(f"  records: {paths.records_path}")
    print(f"  summary: {paths.summary_path}")
    print(f"  corpus_md: {paths.corpus_md_path}")
    print(f"  graph_nodes: {paths.graph_nodes_path}")
    print(f"  graph_edges: {paths.graph_edges_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
