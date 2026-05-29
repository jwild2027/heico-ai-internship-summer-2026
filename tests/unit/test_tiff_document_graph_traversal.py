from pathlib import Path
import json

from tiff.document_graph_traversal import build_traversal_report, context_score, render_report


def write_graph(tmp_path: Path) -> Path:
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    nodes = [
        {"id": "document:doc1", "type": "document", "label": "Manual A"},
        {"id": "page:p1", "type": "page", "label": "Page 1", "page_label": "1"},
        {"id": "part:120_37313_001", "type": "part", "label": "120-37313-001", "part_number": "120-37313-001"},
        {"id": "nomenclature:holder_magazine", "type": "nomenclature", "label": "HOLDER, MAGAZINE"},
        {"id": "source_link:p1", "type": "source_link", "label": "Source p1"},
        {"id": "page_context:p1", "type": "page_context", "label": "Context p1", "summary": "Parts list for holder magazine.", "confidence": "high"},
    ]
    edges = [
        {"source": "document:doc1", "target": "page:p1", "type": "HAS_PAGE"},
        {"source": "page:p1", "target": "part:120_37313_001", "type": "MENTIONS_PART"},
        {"source": "part:120_37313_001", "target": "page:p1", "type": "APPEARS_ON"},
        {"source": "part:120_37313_001", "target": "nomenclature:holder_magazine", "type": "HAS_NOMENCLATURE"},
        {"source": "page:p1", "target": "source_link:p1", "type": "HAS_SOURCE_LINK"},
        {"source": "page:p1", "target": "page_context:p1", "type": "HAS_CONTEXT"},
        {"source": "page_context:p1", "target": "page:p1", "type": "SUMMARIZES"},
    ]
    (graph_dir / "graph_nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    (graph_dir / "graph_edges.json").write_text(json.dumps(edges), encoding="utf-8")
    return graph_dir


def test_document_page_part_name_context_traversal(tmp_path):
    graph_dir = write_graph(tmp_path)
    report = build_traversal_report(graph_dir=graph_dir, part="120-37313-001", strict=True)
    assert report.status == "OK"
    assert report.document and report.document.label == "Manual A"
    assert report.page and report.page.id == "page:p1"
    assert report.part and report.part.id == "part:120_37313_001"
    assert report.nomenclature and report.nomenclature.label == "HOLDER, MAGAZINE"
    assert report.context and report.context.id == "page_context:p1"
    assert report.part_to_context_pages[0]["has_source_link"] is True
    assert context_score(report.context) == 0.90


def test_render_report_mentions_ai_context(tmp_path):
    graph_dir = write_graph(tmp_path)
    report = build_traversal_report(graph_dir=graph_dir, part="120-37313-001")
    text = render_report(report)
    assert "Back to AI context" in text
    assert "Parts list for holder magazine" in text
