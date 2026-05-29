from __future__ import annotations

import json
from pathlib import Path

from tiff.page_context import generate_page_contexts
from tiff.page_context_inspector import inspect_page_contexts


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_export(tmp_path: Path) -> Path:
    export = tmp_path / "export"
    ocr = tmp_path / "page.txt"
    ocr.write_text("120-37313-001 HOLDER, MAGAZINE parts list.", encoding="utf-8")
    write_json(export / "page_index.json", {"pages": [{"page_id": "p1", "manual": "Manual", "ata_code": "25-21-00", "ocr_path": str(ocr), "parts": ["120-37313-001"]}]})
    return export


def test_generate_page_contexts_progress_callback_reports_context(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    seen = []

    def callback(index, total, context, action):
        seen.append((index, total, context.page_id, action, context.approx_prompt_tokens, context.approx_response_tokens, context.quality_score))

    result, contexts = generate_page_contexts(export_dir=export, output_dir=tmp_path / "context", dry_run=True, force=True, progress_callback=callback)

    assert result.status == "OK"
    assert contexts[0].elapsed_seconds >= 0
    assert contexts[0].approx_prompt_tokens >= 0
    assert contexts[0].approx_response_tokens > 0
    assert contexts[0].quality_score > 0
    assert seen and seen[0][0] == 1 and seen[0][1] == 1 and seen[0][2] == "p1" and seen[0][3] == "done"


def test_inspector_reads_new_graph_summary_nested_counts(tmp_path: Path) -> None:
    context_file = tmp_path / "page_contexts.json"
    graph_file = tmp_path / "graph_summary.json"
    write_json(context_file, {"contexts": [{"page_id": "p1", "short_summary": "ok", "page_role": "parts_list", "confidence": "high"}]})
    write_json(graph_file, {"graph_counts": {"node_types": {"page_context": 1}, "edge_types": {"HAS_CONTEXT": 1, "TAGGED_AS": 2, "HIGHLIGHTS_PART": 3}}})

    result = inspect_page_contexts(context_file=context_file, graph_summary_file=graph_file, strict=True)

    assert result.status == "OK"
    assert result.graph_page_context_nodes == 1
    assert result.graph_has_context_edges == 1
    assert result.graph_tagged_as_edges == 2
    assert result.graph_highlights_part_edges == 3


def test_limited_batch_preserves_existing_contexts_outside_selection(tmp_path: Path) -> None:
    export = tmp_path / "export"
    for idx in range(3):
        ocr = tmp_path / f"page{idx}.txt"
        ocr.write_text(f"120-37313-00{idx} HOLDER, MAGAZINE parts list.", encoding="utf-8")
    pages = [
        {"page_id": f"p{idx}", "manual": "Manual", "ata_code": "25-21-00", "ocr_path": str(tmp_path / f"page{idx}.txt"), "parts": [f"120-37313-00{idx}"]}
        for idx in range(3)
    ]
    write_json(export / "page_index.json", {"pages": pages})
    out_dir = tmp_path / "context"

    result1, _ = generate_page_contexts(export_dir=export, output_dir=out_dir, dry_run=True, force=True, limit=3)
    assert result1.contexts_written == 3

    result2, _ = generate_page_contexts(export_dir=export, output_dir=out_dir, dry_run=True, force=True, limit=1)
    assert result2.contexts_written == 3
    data = json.loads((out_dir / "page_contexts.json").read_text(encoding="utf-8"))
    assert {ctx["page_id"] for ctx in data["contexts"]} == {"p0", "p1", "p2"}


def test_missing_only_selects_next_unprocessed_pages(tmp_path: Path) -> None:
    export = tmp_path / "export"
    pages = []
    for idx in range(4):
        ocr = tmp_path / f"page{idx}.txt"
        ocr.write_text(f"120-37313-00{idx} HOLDER, MAGAZINE parts list.", encoding="utf-8")
        pages.append({"page_id": f"p{idx}", "manual": "Manual", "ata_code": "25-21-00", "ocr_path": str(ocr), "parts": [f"120-37313-00{idx}"]})
    write_json(export / "page_index.json", {"pages": pages})
    out_dir = tmp_path / "context"

    generate_page_contexts(export_dir=export, output_dir=out_dir, dry_run=True, force=True, page_ids=["p0", "p1"])
    result, contexts = generate_page_contexts(export_dir=export, output_dir=out_dir, dry_run=True, missing_only=True, limit=2)

    assert result.page_count_seen == 2
    assert [ctx.page_id for ctx in contexts] == ["p2", "p3"]
    data = json.loads((out_dir / "page_contexts.json").read_text(encoding="utf-8"))
    assert {ctx["page_id"] for ctx in data["contexts"]} == {"p0", "p1", "p2", "p3"}


def test_cached_contexts_get_repaired_quality_score(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    out_dir = tmp_path / "context"
    write_json(
        out_dir / "page_contexts.json",
        {"contexts": [{"page_id": "p1", "short_summary": "cached", "page_role": "parts_list", "confidence": "high", "quality_score": 0.0}]},
    )

    result, contexts = generate_page_contexts(export_dir=export, output_dir=out_dir, dry_run=True, force=False)

    assert result.skipped_existing == 1
    assert contexts[0].quality_score == 0.9
