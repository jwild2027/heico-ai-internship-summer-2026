from __future__ import annotations

import json
from pathlib import Path

from tiff.document_organization_graph import build_graph_from_export
from tiff.page_context import create_page_context, generate_page_contexts


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_export(tmp_path: Path) -> tuple[Path, Path]:
    export = tmp_path / "export"
    ocr = tmp_path / "000001.txt"
    ocr.write_text("120-37313-001 HOLDER, MAGAZINE parts list for magazine holder.", encoding="utf-8")
    page = {
        "page_id": "doc_p000001",
        "manual_id": "doc",
        "manual": "Test Manual",
        "ata_code": "25-21-00",
        "page_label": "1",
        "source_url": "http://example/source/1",
        "tiff_path": str(tmp_path / "000001.tif"),
        "ocr_path": str(ocr),
        "parts": ["120-37313-001"],
    }
    write_json(export / "page_index.json", {"pages": [page]})
    write_json(export / "part_tree.json", {"parts": [{"part_number": "120-37313-001", "nomenclature": "HOLDER, MAGAZINE", "pages": [{"page_id": "doc_p000001"}]}]})
    write_json(export / "ata_tree.json", {"ata_groups": [{"ata_code": "25-21-00", "manual_id": "doc", "manual": "Test Manual", "page_count": 1, "part_count": 1}]})
    write_json(export / "manual_ata_tree.json", {"manuals": [{"manual_id": "doc", "manual": "Test Manual"}]})
    write_json(export / "organization_summary.json", {"manuals": 1, "pages": 1, "parts": 1, "part_mentions": 1})
    return export, ocr


def test_create_page_context_dry_run(tmp_path: Path) -> None:
    export, _ = make_export(tmp_path)
    page = json.loads((export / "page_index.json").read_text(encoding="utf-8"))["pages"][0]
    context = create_page_context(page, dry_run=True, model="gemma3:12B")
    assert context.page_id == "doc_p000001"
    assert context.page_role == "parts_list"
    assert "120-37313-001" in context.important_parts
    assert context.context_id.startswith("page_context:")


def test_generate_page_contexts_writes_json(tmp_path: Path) -> None:
    export, _ = make_export(tmp_path)
    result, contexts = generate_page_contexts(export_dir=export, output_dir=tmp_path / "context", dry_run=True, force=True)
    assert result.status == "OK"
    assert result.contexts_written == 1
    assert contexts[0].page_id == "doc_p000001"
    out = tmp_path / "context" / "page_contexts.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["contexts"][0]["page_id"] == "doc_p000001"


def test_graph_includes_page_context_nodes_and_edges(tmp_path: Path) -> None:
    export, _ = make_export(tmp_path)
    result, contexts = generate_page_contexts(export_dir=export, output_dir=tmp_path / "context", dry_run=True, force=True)
    assert contexts
    graph = build_graph_from_export(export, strict=True, context_file=Path(result.output_path))
    node_types = graph.summary["graph_counts"]["node_types"]
    edge_types = graph.summary["graph_counts"]["edge_types"]
    assert node_types["page_context"] == 1
    assert edge_types["HAS_CONTEXT"] == 1
    assert edge_types["SUMMARIZES"] == 1
    assert edge_types["HIGHLIGHTS_PART"] == 1
    assert "topic" in node_types

from tiff.page_context import parse_context_response


def test_parse_context_response_accepts_literal_control_chars() -> None:
    payload = '{"short_summary":"Line one\nline two","page_role":"procedure","topics":["repair"],"important_parts":[],"confidence":"high"}'
    parsed = parse_context_response(payload)
    assert parsed["short_summary"] == "Line one\nline two"
    assert parsed["page_role"] == "procedure"


def test_parse_context_response_strips_markdown_fences() -> None:
    payload = '```json\n{"short_summary":"OK","page_role":"unknown","topics":[],"important_parts":[],"confidence":"medium"}\n```'
    parsed = parse_context_response(payload)
    assert parsed["short_summary"] == "OK"

from tiff.page_context import normalize_ollama_host


def test_normalize_ollama_host_adds_scheme_and_port() -> None:
    assert normalize_ollama_host("0.0.0.0") == "http://127.0.0.1:11434"
    assert normalize_ollama_host("0.0.0.0:11434") == "http://127.0.0.1:11434"
    assert normalize_ollama_host("localhost:11434") == "http://localhost:11434"


def test_normalize_ollama_host_preserves_valid_url() -> None:
    assert normalize_ollama_host("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert normalize_ollama_host("http://localhost:11434/") == "http://localhost:11434"


def test_page_context_reads_organization_export_ocr_text_path(tmp_path):
    from tiff.page_context import create_page_context

    ocr = tmp_path / "page.txt"
    ocr.write_text("120-37313-001 HOLDER, MAGAZINE", encoding="utf-8")
    page = {
        "page_id": "p1",
        "manual": "T.P. 120/1176",
        "ata": "25-21-00",
        "page_label": "1056",
        "ocr_text_path": str(ocr),
        "source_image_path": "page.tif",
        "parts": ["120-37313-001"],
    }

    ctx = create_page_context(page, dry_run=True, generated_at="2026-01-01T00:00:00Z")

    assert ctx.ocr_path == str(ocr)
    assert ctx.ocr_char_count > 0
    assert ctx.error == ""
    assert ctx.tiff_path == "page.tif"

from tiff.page_context import approx_token_count, context_quality_score


def test_page_context_progress_fields_and_callback(tmp_path: Path) -> None:
    export, _ = make_export(tmp_path)
    events = []

    def callback(idx, total, context, action):
        events.append((idx, total, context.page_id, action, context.quality_score, context.elapsed_seconds))

    result, contexts = generate_page_contexts(
        export_dir=export,
        output_dir=tmp_path / "context",
        dry_run=True,
        force=True,
        progress_callback=callback,
    )

    assert result.total_elapsed_seconds >= 0
    assert result.average_elapsed_seconds >= 0
    assert contexts[0].quality_score > 0
    assert contexts[0].elapsed_seconds >= 0
    assert events == [(1, 1, "doc_p000001", "done", contexts[0].quality_score, contexts[0].elapsed_seconds)]


def test_token_and_quality_helpers() -> None:
    assert approx_token_count("abcd") == 1
    assert approx_token_count("abcde") == 2
    assert context_quality_score("high", "") == 0.9
    assert context_quality_score("high", "empty OCR text") < 0.9
