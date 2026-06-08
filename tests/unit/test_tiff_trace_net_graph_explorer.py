from decimal import Decimal

from tiff.trace_net_graph_explorer import build_explorer_graph, canonical_page_id, extract_part_numbers, render_html, write_json


def test_canonical_page_id_maps_zip_to_trace_net():
    assert canonical_page_id("zip_page_000003") == "t_p_120_1176_p000003"
    assert canonical_page_id("t_p_120_1176_p000010") == "t_p_120_1176_p000010"


def test_extract_part_numbers_filters_basic_parts():
    text = "120-50645-009 120-50645-017 25-21 120-50645-009"
    parts = extract_part_numbers(text)
    assert "120-50645-009" in parts
    assert "120-50645-017" in parts
    assert "25-21" not in parts
    assert parts.count("120-50645-009") == 1


def test_build_graph_has_part_to_page_crosslinks():
    rows = {
        "pages": [
            {"page_id": "zip_page_000003", "document_id": "doc", "page_number": 3, "source_url": "http://x/3", "tiff_path": "p3.tif", "ocr_path": "p3.txt"},
            {"page_id": "zip_page_000004", "document_id": "doc", "page_number": 4, "source_url": "http://x/4", "tiff_path": "p4.tif", "ocr_path": "p4.txt"},
        ],
        "ocr_records": [{"page_id": "zip_page_000003", "classification": "likely_full_page", "chars": 100, "text": "hello"}],
        "rag_candidate_chunks": [
            {"candidate_id": "c1", "page_id": "t_p_120_1176_p000003", "rag_bucket": "verified_part_evidence", "evidence_layer": "part_catalog", "trust_tier": "A", "usable_confidence": 0.9, "text": "Part 120-50645-009 appears here", "source_url": "http://x/3"},
            {"candidate_id": "c2", "page_id": "t_p_120_1176_p000004", "rag_bucket": "source_text_evidence", "evidence_layer": "source_text", "trust_tier": "A", "usable_confidence": 0.8, "text": "Another 120-50645-009 reference", "source_url": "http://x/4"},
        ],
        "source_citations": [{"citation_id": "cit1", "candidate_id": "c1", "page_id": "t_p_120_1176_p000003", "source_url": "http://x/3"}],
        "page_trust_traits": [{"page_id": "t_p_120_1176_p000003", "evidence_layer": "source_trace", "trust_tier": "A"}],
        "page_context_records": [
            {"context_id": "page_context:t_p_120_1176_p000003", "page_id": "t_p_120_1176_p000003", "page_id_resolved": "zip_page_000003", "role": "parts_list", "summary": "Applicability page listing passenger seat parts", "topics": ["parts list", "passenger seat"], "highlighted_parts": ["120-50645-009"], "confidence": "high", "can_answer_directly": False, "can_support_answer": True, "canonical_source_truth": False}
        ],
        "page_context_topics": [{"context_id": "page_context:t_p_120_1176_p000003", "page_id": "t_p_120_1176_p000003", "topic": "passenger seat"}],
        "page_context_highlighted_parts": [{"context_id": "page_context:t_p_120_1176_p000003", "page_id": "t_p_120_1176_p000003", "part_number": "120-50645-009"}],
    }
    graph = build_explorer_graph(rows)
    summary = graph["summary"]
    assert summary["page_nodes"] == 2
    assert summary["part_nodes"] >= 1
    assert summary["candidate_nodes"] == 2
    assert summary["page_context_nodes"] == 1
    edge_types = summary["edge_type_counts"]
    assert edge_types["PART_ON_PAGE"] >= 2
    assert edge_types["HAS_CANDIDATE"] == 2
    assert edge_types["HAS_CONTEXT"] == 1
    assert edge_types["TAGGED_AS"] >= 1
    assert edge_types["HIGHLIGHTS_PART"] >= 1


def test_render_html_embeds_expected_app_text():
    graph = {"nodes": [], "edges": [], "summary": {"nodes": 0, "edges": 0, "node_type_counts": {}}}
    html = render_html(graph)
    assert "TRACE-Net Graph Explorer" in html
    assert "Click any node" in html


def test_write_json_serializes_decimal_payload(tmp_path):
    out = tmp_path / "graph.json"
    write_json(out, {"nodes": [{"payload": {"usable_confidence": Decimal("0.81225")}}]})
    text = out.read_text(encoding="utf-8")
    assert "0.81225" in text

def test_render_html_serializes_decimal_payload():
    graph = {"nodes": [{"id": "x", "type": "candidate", "label": "x", "payload": {"usable_confidence": Decimal("0.5")}}], "edges": [], "summary": {"nodes": 1, "edges": 0, "node_type_counts": {}}}
    html = render_html(graph)
    assert "0.5" in html
