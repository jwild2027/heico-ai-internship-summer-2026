from __future__ import annotations

import json
from pathlib import Path

from tiff.document_graph_traceability import build_traceability_report, trace_part_to_sources, trace_page_context, trace_vector_candidate_to_graph, trace_ata_to_sources
from tiff.document_graph_traversal import GraphStore


def write_graph(tmp_path: Path) -> Path:
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    nodes = [
        {"id": "document:manual_a", "type": "document", "label": "Manual A", "properties": {"document_id": "manual_a"}},
        {"id": "ata_section:manual_a_25_21_00", "type": "ata_section", "label": "ATA 25-21-00", "properties": {"ata_code": "25-21-00"}},
        {"id": "page:manual_a_p000001", "type": "page", "label": "Manual A page 1", "properties": {"page_id": "manual_a_p000001", "page_label": "1", "sequence_number": 1}},
        {"id": "part:120_37313_001", "type": "part", "label": "120-37313-001", "properties": {"part_number": "120-37313-001"}},
        {"id": "nomenclature:holder_magazine", "type": "nomenclature", "label": "HOLDER, MAGAZINE", "properties": {"text": "HOLDER, MAGAZINE"}},
        {"id": "page_context:manual_a_p000001", "type": "page_context", "label": "This page lists magazine holder parts.", "properties": {"score": 0.9, "short_summary": "This page lists magazine holder parts."}},
        {"id": "source_link:manual_a_p000001", "type": "source_link", "label": "Source link", "properties": {"source_url": "http://example/source/1"}},
    ]
    edges = [
        {"type": "HAS_PAGE", "from": "document:manual_a", "to": "page:manual_a_p000001"},
        {"type": "BELONGS_TO_DOCUMENT", "from": "page:manual_a_p000001", "to": "document:manual_a"},
        {"type": "HAS_ATA_SECTION", "from": "document:manual_a", "to": "ata_section:manual_a_25_21_00"},
        {"type": "CONTAINS_PAGE", "from": "ata_section:manual_a_25_21_00", "to": "page:manual_a_p000001"},
        {"type": "BELONGS_TO_ATA", "from": "page:manual_a_p000001", "to": "ata_section:manual_a_25_21_00"},
        {"type": "MENTIONS_PART", "from": "page:manual_a_p000001", "to": "part:120_37313_001"},
        {"type": "APPEARS_ON", "from": "part:120_37313_001", "to": "page:manual_a_p000001"},
        {"type": "HAS_NOMENCLATURE", "from": "part:120_37313_001", "to": "nomenclature:holder_magazine"},
        {"type": "HAS_CONTEXT", "from": "page:manual_a_p000001", "to": "page_context:manual_a_p000001"},
        {"type": "SUMMARIZES", "from": "page_context:manual_a_p000001", "to": "page:manual_a_p000001"},
        {"type": "HAS_SOURCE_LINK", "from": "page:manual_a_p000001", "to": "source_link:manual_a_p000001"},
        {"type": "OPENS", "from": "source_link:manual_a_p000001", "to": "page:manual_a_p000001"},
    ]
    (graph_dir / "graph_nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    (graph_dir / "graph_edges.json").write_text(json.dumps(edges), encoding="utf-8")
    return graph_dir


def test_trace_part_to_sources_resolves_page_context_and_source(tmp_path: Path) -> None:
    graph_dir = write_graph(tmp_path)
    graph = GraphStore.load(graph_dir)
    trace = trace_part_to_sources(graph, "120-37313-001", strict=True)
    assert trace.status == "OK"
    assert trace.summary["total_pages_found"] == 1
    assert trace.summary["sample_pages_with_source_links"] == 1
    assert trace.summary["sample_pages_with_context"] == 1
    assert any(step.edge_type == "HAS_CONTEXT" for step in trace.steps)
    assert any(step.edge_type == "HAS_SOURCE_LINK" for step in trace.steps)


def test_trace_page_resolves_parts_and_nomenclature(tmp_path: Path) -> None:
    graph_dir = write_graph(tmp_path)
    graph = GraphStore.load(graph_dir)
    trace = trace_page_context(graph, "manual_a_p000001", strict=True)
    assert trace.status == "OK"
    assert any(step.node_label == "120-37313-001" for step in trace.steps)
    assert any(step.node_label == "HOLDER, MAGAZINE" for step in trace.steps)


def test_ata_trace_resolves_pages_sources_context_and_parts(tmp_path: Path) -> None:
    graph_dir = write_graph(tmp_path)
    graph = GraphStore.load(graph_dir)
    trace = trace_ata_to_sources(graph, "25-21-00", strict=True)
    assert trace.status == "OK"
    assert trace.id == "ata_to_sources"
    assert trace.summary["total_pages_found"] == 1
    assert trace.summary["sample_pages_with_source_links"] == 1
    assert trace.summary["sample_pages_with_context"] == 1
    assert trace.summary["distinct_parts_in_ata"] == 1
    assert any(step.edge_type == "CONTAINS_PAGE" for step in trace.steps)


def test_vector_candidate_trace_resolves_qdrant_payload_to_graph(tmp_path: Path) -> None:
    graph_dir = write_graph(tmp_path)
    graph = GraphStore.load(graph_dir)
    trace = trace_vector_candidate_to_graph(graph, "manual_a_p000001", chunk_id="chunk_manual_a_p000001_001", score=0.635, strict=True)
    assert trace.status == "OK"
    assert trace.id == "vector_candidate_to_graph"
    assert trace.steps[0].node_type == "vector_payload"
    assert trace.summary["vector_payload_chunk_id"] == "chunk_manual_a_p000001_001"
    assert trace.summary["vector_payload_score"] == 0.635
    assert trace.summary["source_link_present"] is True
    assert trace.summary["context_present"] is True


def test_build_traceability_report_writes_combined_summary(tmp_path: Path) -> None:
    graph_dir = write_graph(tmp_path)
    report = build_traceability_report(graph_dir=graph_dir, part="120-37313-001", page="manual_a_p000001", ata="25-21-00", vector_page="manual_a_p000001", vector_chunk="chunk_manual_a_p000001_001", vector_score=0.635, strict=True)
    assert report.status == "OK"
    assert len(report.traces) == 4
    data = report.to_jsonable()
    assert data["node_type_counts"]["page"] == 1
