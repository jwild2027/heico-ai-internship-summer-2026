from __future__ import annotations

import json
from pathlib import Path

from tiff.document_graph_quality import GraphQualityThresholds, build_graph_quality_result


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_minimal_graph(graph_dir: Path) -> None:
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


def test_graph_quality_requires_realistic_query_trace_results(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    context_file = tmp_path / "contexts.json"
    user_results = tmp_path / "user_query.json"
    realistic_results = tmp_path / "realistic.json"
    write_minimal_graph(graph_dir)
    write_json(context_file, {"contexts": [
        {"page_id": "t_p_120_1176_p000083", "role": "parts_list", "confidence": "high"},
        {"page_id": "t_p_120_1176_p000495", "role": "procedure", "confidence": "high"},
    ]})
    write_json(user_results, {"results": [{"status": "pass"}]})
    write_json(realistic_results, {"summary": {"total": 2, "pass": 2, "fail": 0, "check_total": 4, "check_pass": 4, "check_fail": 0}})

    result = build_graph_quality_result(
        graph_dir=graph_dir,
        context_file=context_file,
        user_query_results=user_results,
        realistic_query_trace_results=realistic_results,
        thresholds=GraphQualityThresholds(require_realistic_query_trace_tests=True),
    )
    assert result.status == "ok"
    assert result.summary["realistic_query_trace_results_present"] is True
    assert result.summary["realistic_query_trace_total"] == 2
    assert result.summary["realistic_query_trace_check_fail"] == 0


def test_graph_quality_fails_when_required_realistic_trace_results_missing(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    context_file = tmp_path / "contexts.json"
    user_results = tmp_path / "user_query.json"
    write_minimal_graph(graph_dir)
    write_json(context_file, {"contexts": [
        {"page_id": "t_p_120_1176_p000083", "role": "parts_list", "confidence": "high"},
        {"page_id": "t_p_120_1176_p000495", "role": "procedure", "confidence": "high"},
    ]})
    write_json(user_results, {"results": [{"status": "pass"}]})

    result = build_graph_quality_result(
        graph_dir=graph_dir,
        context_file=context_file,
        user_query_results=user_results,
        realistic_query_trace_results=tmp_path / "missing.json",
        thresholds=GraphQualityThresholds(require_realistic_query_trace_tests=True),
    )
    assert result.status == "fail"
    failing = {check.name for check in result.checks if check.status == "FAIL"}
    assert "realistic_query_trace_results" in failing
