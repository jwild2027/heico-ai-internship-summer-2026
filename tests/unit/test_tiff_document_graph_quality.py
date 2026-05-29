from __future__ import annotations

import json
from pathlib import Path

from tiff.document_graph_quality import build_graph_quality_result


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_graph_quality_happy_path(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    context_file = tmp_path / "contexts.json"
    user_results = tmp_path / "user_query.json"

    nodes = [
        {"id": "document:doc", "type": "document", "label": "Doc"},
        {"id": "ata_section:doc_25_21_00", "type": "ata_section", "label": "ATA 25-21-00"},
        {"id": "page:t_p_120_1176_p000083", "type": "page", "label": "Page 1056", "properties": {"page_id": "t_p_120_1176_p000083"}},
        {"id": "page:t_p_120_1176_p000495", "type": "page", "label": "Page 621", "properties": {"page_id": "t_p_120_1176_p000495"}},
        {"id": "source_link:t_p_120_1176_p000083", "type": "source_link", "label": "source 83"},
        {"id": "source_link:t_p_120_1176_p000495", "type": "source_link", "label": "source 495"},
        {"id": "part:120_37313_001", "type": "part", "label": "120-37313-001", "properties": {"part_number": "120-37313-001"}},
        {"id": "nomenclature:holder_magazine", "type": "nomenclature", "label": "HOLDER, MAGAZINE"},
        {"id": "page_context:t_p_120_1176_p000083", "type": "page_context", "label": "context 83", "properties": {"score": 0.9}},
        {"id": "page_context:t_p_120_1176_p000495", "type": "page_context", "label": "context 495", "properties": {"score": 0.9}},
    ]
    edges = [
        {"source": "document:doc", "target": "page:t_p_120_1176_p000083", "type": "HAS_PAGE"},
        {"source": "document:doc", "target": "page:t_p_120_1176_p000495", "type": "HAS_PAGE"},
        {"source": "page:t_p_120_1176_p000083", "target": "document:doc", "type": "BELONGS_TO_DOCUMENT"},
        {"source": "page:t_p_120_1176_p000495", "target": "document:doc", "type": "BELONGS_TO_DOCUMENT"},
        {"source": "page:t_p_120_1176_p000083", "target": "ata_section:doc_25_21_00", "type": "BELONGS_TO_ATA"},
        {"source": "page:t_p_120_1176_p000495", "target": "ata_section:doc_25_21_00", "type": "BELONGS_TO_ATA"},
        {"source": "page:t_p_120_1176_p000083", "target": "source_link:t_p_120_1176_p000083", "type": "HAS_SOURCE_LINK"},
        {"source": "page:t_p_120_1176_p000495", "target": "source_link:t_p_120_1176_p000495", "type": "HAS_SOURCE_LINK"},
        {"source": "part:120_37313_001", "target": "page:t_p_120_1176_p000083", "type": "APPEARS_ON"},
        {"source": "part:120_37313_001", "target": "nomenclature:holder_magazine", "type": "HAS_NOMENCLATURE"},
        {"source": "page:t_p_120_1176_p000083", "target": "part:120_37313_001", "type": "MENTIONS_PART"},
        {"source": "page:t_p_120_1176_p000083", "target": "page_context:t_p_120_1176_p000083", "type": "HAS_CONTEXT"},
        {"source": "page:t_p_120_1176_p000495", "target": "page_context:t_p_120_1176_p000495", "type": "HAS_CONTEXT"},
    ]
    write_json(graph_dir / "graph_nodes.json", nodes)
    write_json(graph_dir / "graph_edges.json", edges)
    write_json(context_file, {"contexts": [
        {"page_id": "t_p_120_1176_p000083", "role": "parts_list", "confidence": "high"},
        {"page_id": "t_p_120_1176_p000495", "role": "procedure", "confidence": "high"},
    ]})
    write_json(user_results, {"results": [{"status": "pass"}, {"status": "pass"}]})

    result = build_graph_quality_result(
        graph_dir=graph_dir,
        context_file=context_file,
        user_query_results=user_results,
    )
    assert result.status == "ok"
    assert result.summary["page_nodes"] == 2
    assert result.summary["page_context_nodes"] == 2
    assert result.summary["part_traceability_sample_ok"] is True
    assert result.summary["vector_payload_traceability_sample_ok"] is True


def test_graph_quality_detects_missing_context(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    context_file = tmp_path / "contexts.json"
    write_json(graph_dir / "graph_nodes.json", [
        {"id": "page:one", "type": "page"},
        {"id": "source_link:one", "type": "source_link"},
        {"id": "part:abc", "type": "part", "label": "ABC"},
    ])
    write_json(graph_dir / "graph_edges.json", [
        {"source": "page:one", "target": "source_link:one", "type": "HAS_SOURCE_LINK"},
    ])
    write_json(context_file, {"contexts": []})
    result = build_graph_quality_result(graph_dir=graph_dir, context_file=context_file)
    assert result.status == "fail"
    failing = {check.name for check in result.checks if check.status == "FAIL"}
    assert "graph_context_coverage" in failing
