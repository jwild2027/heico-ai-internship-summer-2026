from __future__ import annotations

import json
from pathlib import Path

from tiff.api_backend import ApiPaths, api_status, page_lookup, part_lookup, submit_feedback, summarize_feedback


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_graph(tmp_path: Path) -> ApiPaths:
    graph_dir = tmp_path / "graph"
    export_dir = tmp_path / "export"
    quality = tmp_path / "latest_quality_gate.json"
    graph_quality = graph_dir / "graph_quality.json"
    feedback_jsonl = tmp_path / "feedback" / "feedback.jsonl"
    feedback_summary = tmp_path / "feedback" / "summary.json"

    nodes = [
        {"id": "document:manual_a", "type": "document", "label": "Manual A"},
        {"id": "ata:25_21_00", "type": "ata_section", "label": "ATA 25-21-00", "ata_code": "25-21-00"},
        {"id": "page:p1", "type": "page", "label": "Manual A page 1", "page_id": "p1", "page_label": "1"},
        {"id": "part:120_37313_001", "type": "part", "label": "120-37313-001", "part_number": "120-37313-001"},
        {"id": "nomenclature:holder_magazine", "type": "nomenclature", "label": "HOLDER, MAGAZINE"},
        {"id": "source_link:p1", "type": "source_link", "label": "source for p1", "source_url": "http://source/p1"},
        {"id": "page_context:p1", "type": "page_context", "label": "AI context", "summary": "This page lists a holder magazine part.", "confidence": "high"},
    ]
    edges = [
        {"source": "document:manual_a", "target": "page:p1", "type": "HAS_PAGE"},
        {"source": "page:p1", "target": "document:manual_a", "type": "BELONGS_TO_DOCUMENT"},
        {"source": "ata:25_21_00", "target": "page:p1", "type": "CONTAINS_PAGE"},
        {"source": "page:p1", "target": "ata:25_21_00", "type": "BELONGS_TO_ATA"},
        {"source": "page:p1", "target": "part:120_37313_001", "type": "MENTIONS_PART"},
        {"source": "part:120_37313_001", "target": "page:p1", "type": "APPEARS_ON"},
        {"source": "part:120_37313_001", "target": "nomenclature:holder_magazine", "type": "HAS_NOMENCLATURE"},
        {"source": "page:p1", "target": "source_link:p1", "type": "HAS_SOURCE_LINK"},
        {"source": "page:p1", "target": "page_context:p1", "type": "HAS_CONTEXT"},
    ]
    write_json(graph_dir / "graph_nodes.json", nodes)
    write_json(graph_dir / "graph_edges.json", edges)
    write_json(quality, {"status": "OK", "summary": {"pipeline_status": "ok"}})
    write_json(graph_quality, {"status": "OK", "summary": {"graph_present": True, "nodes_total": 7, "edges_total": 9, "page_nodes": 1, "page_context_nodes": 1, "source_link_nodes": 1, "pages_without_context": 0, "pages_without_source_links": 0}})
    return ApiPaths(
        graph_dir=graph_dir,
        export_dir=export_dir,
        feedback_jsonl=feedback_jsonl,
        feedback_summary=feedback_summary,
        quality_json=quality,
        graph_quality_json=graph_quality,
    )


def test_api_status_reads_quality_and_graph_summary(tmp_path: Path):
    paths = make_graph(tmp_path)
    status = api_status(paths)
    assert status["status"] == "OK"
    assert status["graph"]["page_context_nodes"] == 1
    assert status["graph"]["source_link_nodes"] == 1


def test_part_lookup_traverses_to_page_source_context_and_name(tmp_path: Path):
    paths = make_graph(tmp_path)
    result = part_lookup("120-37313-001", paths=paths)
    assert result["status"] == "ok"
    assert result["nomenclature"] == "HOLDER, MAGAZINE"
    assert result["pages_total"] == 1
    assert result["pages"][0]["source_link_present"] is True
    assert result["pages"][0]["context_present"] is True
    assert result["pages"][0]["context_score"] == 0.9


def test_page_lookup_returns_document_ata_part_and_context(tmp_path: Path):
    paths = make_graph(tmp_path)
    result = page_lookup("p1", paths=paths)
    assert result["status"] == "ok"
    assert result["page"]["document"] == "Manual A"
    assert result["page"]["ata"] == "ATA 25-21-00"
    assert result["parts"][0]["nomenclature"] == "HOLDER, MAGAZINE"


def test_feedback_persists_jsonl_and_summary(tmp_path: Path):
    paths = make_graph(tmp_path)
    saved = submit_feedback(
        question="What is part 120-37313-001?",
        rating="up",
        category="useful",
        reason="Correct and sourced.",
        paths=paths,
    )
    assert saved["status"] == "ok"
    assert paths.feedback_jsonl.exists()
    summary = summarize_feedback(paths)
    assert summary["total_feedback"] == 1
    assert summary["rating_counts"]["up"] == 1
    assert summary["category_counts"]["useful"] == 1
