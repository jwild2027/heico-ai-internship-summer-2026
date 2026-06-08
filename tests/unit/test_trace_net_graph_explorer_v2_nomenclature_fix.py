from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "build_trace_net_graph_explorer_v2_nomenclature_fix.py"

spec = importlib.util.spec_from_file_location("graph_v2_nom_fix", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_parse_page_range_accepts_reversed_ranges() -> None:
    assert mod._parse_page_range("1-50") == (1, 50)
    assert mod._parse_page_range("50-1") == (1, 50)
    assert mod._parse_page_range("") is None
    with pytest.raises(ValueError):
        mod._parse_page_range("first-50")


def test_enrich_with_context_v2_adds_node_edge_and_page_payload() -> None:
    graph = {
        "nodes": [
            {
                "id": "page:t_p_120_1176_p000001",
                "type": "page",
                "label": "Page 000001",
                "size": 24,
                "weight": 3.0,
                "payload": {"page_id": "t_p_120_1176_p000001"},
            }
        ],
        "edges": [],
        "summary": {},
    }
    rows = [
        {
            "page_id": "t_p_120_1176_p000001",
            "summary": "This page helps route queries about the title page and manual identity.",
            "retrieval_cues": ["title page", "manual identity"],
            "payload": {"model": "gemma-4-26b"},
        }
    ]

    added = mod.enrich_with_context_v2(graph, rows, fallback_doc="t_p_120_1176")

    assert added["page_context_v2_nodes_added"] == 1
    assert added["has_context_v2_edges_added"] == 1
    assert any(node["type"] == "page_context_v2" for node in graph["nodes"])
    assert any(edge["type"] == "HAS_CONTEXT_V2" for edge in graph["edges"])
    page = next(node for node in graph["nodes"] if node["type"] == "page")
    assert page["payload"]["context_v2_present"] is True
    assert page["payload"]["context_v2_authority"] == "retrieval_helper_only"
    assert "manual identity" in page["payload"]["context_v2_summary"]


def test_missing_context_v2_pages_reports_required_page_gaps() -> None:
    graph = {
        "nodes": [],
        "edges": [
            {
                "id": "HAS_CONTEXT_V2:page:t_p_120_1176_p000001->page_context_v2:one",
                "source": "page:t_p_120_1176_p000001",
                "target": "page_context_v2:one",
                "type": "HAS_CONTEXT_V2",
            }
        ],
    }

    assert mod._missing_context_v2_pages(graph, "1-3", fallback_doc="t_p_120_1176") == [
        "t_p_120_1176_p000002",
        "t_p_120_1176_p000003",
    ]


def test_enrich_with_nomenclature_promotes_part_name_edges() -> None:
    graph = {"nodes": [], "edges": [], "summary": {}}
    rows = {
        "graph_nodes": [
            {
                "node_id": "part:120-37313-001",
                "node_type": "part",
                "label": "120-37313-001",
                "payload": {"part_number": "120-37313-001"},
            },
            {
                "node_id": "nom:120-37313-001",
                "node_type": "nomenclature",
                "label": "Bracket Assembly",
                "payload": {"nomenclature": "Bracket Assembly"},
            },
        ],
        "graph_edges": [
            {
                "edge_id": "edge-1",
                "source_id": "part:120-37313-001",
                "target_id": "nom:120-37313-001",
                "edge_type": "HAS_NOMENCLATURE",
                "payload": {},
            }
        ],
    }

    added = mod.enrich_with_nomenclature(graph, rows, fallback_doc="t_p_120_1176")

    assert added["nomenclature_nodes_added"] == 1
    assert added["has_nomenclature_edges_added"] == 1
    assert any(node["type"] == "part" and node["label"] == "120-37313-001" for node in graph["nodes"])
    assert any(node["type"] == "nomenclature" and node["label"] == "Bracket Assembly" for node in graph["nodes"])
    assert any(edge["type"] == "HAS_NOMENCLATURE" for edge in graph["edges"])


def test_recompute_summary_counts_new_overlay_types() -> None:
    graph = {
        "nodes": [
            {"id": "page:t_p_120_1176_p000001", "type": "page", "payload": {}},
            {"id": "part:120-37313-001", "type": "part", "payload": {}},
            {"id": "nomenclature:nom1", "type": "nomenclature", "payload": {}},
            {"id": "page_context_v2:ctx1", "type": "page_context_v2", "payload": {}},
        ],
        "edges": [
            {
                "id": "HAS_NOMENCLATURE:part:120-37313-001->nomenclature:nom1",
                "source": "part:120-37313-001",
                "target": "nomenclature:nom1",
                "type": "HAS_NOMENCLATURE",
            },
            {
                "id": "HAS_CONTEXT_V2:page:t_p_120_1176_p000001->page_context_v2:ctx1",
                "source": "page:t_p_120_1176_p000001",
                "target": "page_context_v2:ctx1",
                "type": "HAS_CONTEXT_V2",
            },
        ],
        "summary": {},
    }

    summary = mod._recompute_summary(graph, {"extra_check": "ok"})

    assert summary["nomenclature_nodes"] == 1
    assert summary["page_context_v2_nodes"] == 1
    assert summary["has_nomenclature_edges"] == 1
    assert summary["has_context_v2_edges"] == 1
    assert summary["extra_check"] == "ok"
