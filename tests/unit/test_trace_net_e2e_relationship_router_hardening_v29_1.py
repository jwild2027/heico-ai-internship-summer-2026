from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import (
    answer_query,
    build_leiden_index,
    build_page_summary_index,
    build_report,
    load_graph_signal_pages,
    load_source_truth_records,
)


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    table = _write(
        tmp_path / "table.json",
        {
            "records": [
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-503"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-001"},
                {"page_id": "t_p_120_1176_p000005", "field": "manual_page_reference", "value": "25-21-00"},
                {"page_id": "t_p_120_1176_p000027", "field": "ipl_text", "value": "ILLUSTRATED PARTS LIST"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-002"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-003"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-004"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-005"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-006"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-007"},
            ]
        },
    )
    page_context = _write(
        tmp_path / "page_context.json",
        {
            "page_contexts": [
                {"page_id": "t_p_120_1176_p000001", "summary": "summary 1"},
                {"page_id": "t_p_120_1176_p000002", "summary": "summary 2"},
            ]
        },
    )
    leiden = _write(
        tmp_path / "leiden.json",
        {
            "communities": [
                {"leiden_community_id": "tracenet_community_00115", "page_ids": ["t_p_120_1176_p000003", "t_p_120_1176_p000319"]}
            ]
        },
    )
    graph = _write(
        tmp_path / "graph.json",
        {
            "edges": [
                # Deliberately partial Has_v2: page_context_v2 should win for the count.
                {"edge_type": "Has_v2", "source": "t_p_120_1176_p000001", "target": "v2_summary_1"},
                # HAS_CONTEXT/SUMMARIZES diagnostic path.
                {"edge_type": "HAS_CONTEXT", "source": "t_p_120_1176_p000002", "target": "page_context_2"},
                {"edge_type": "SUMMARIZES", "source": "page_context_2", "target": "t_p_120_1176_p000002"},
                # Nomenclature is not on the page edge. It must be joined through part->appears_on.
                {"edge_type": "HAS_NOMENCLATURE", "source": "part_120-36833-503", "target": "nomenclature_widget"},
                {"edge_type": "APPEARS_ON", "source": "part_120-36833-503", "target": "t_p_120_1176_p000003"},
            ]
        },
    )
    return table, page_context, leiden, graph


def test_v2_summary_count_prefers_page_context_over_partial_graph_signal(tmp_path: Path):
    table, page_context, leiden, graph = _fixtures(tmp_path)
    result = answer_query(
        "how many pages have a v2 summary",
        load_source_truth_records(table),
        build_page_summary_index(page_context),
        build_leiden_index(leiden),
        load_graph_signal_pages([graph]),
    )
    assert result["response_mode"] == "artifact_metadata_count"
    assert result["metadata_count_router_used"] is True
    assert result["metadata_count_source"] == "page_context_v2_summary_records"
    assert result["v2_summary_page_count"] == 2
    assert result["graph_has_v2_page_count"] == 1
    assert result["graph_has_context_page_count"] == 1
    assert "covered_part_number" not in result["answer"]


def test_nomenclature_count_joins_part_has_nomenclature_to_appears_on_page(tmp_path: Path):
    table, page_context, leiden, graph = _fixtures(tmp_path)
    result = answer_query(
        "how many pages mention a nomenclature",
        load_source_truth_records(table),
        build_page_summary_index(page_context),
        build_leiden_index(leiden),
        load_graph_signal_pages([graph]),
    )
    assert result["metadata_count_router_used"] is True
    assert result["metadata_count_source"] == "graph_has_nomenclature_signal"
    assert result["nomenclature_page_count"] == 1
    assert result["nomenclature_part_count"] == 1
    assert result["bad_broad_fallback_blocked"] is True
    assert "120-36833" not in result["answer"]


def test_missing_exact_part_is_audit_only(tmp_path: Path):
    table, page_context, leiden, graph = _fixtures(tmp_path)
    result = answer_query(
        "Find part number DOES-NOT-EXIST-999",
        load_source_truth_records(table),
        build_page_summary_index(page_context),
        build_leiden_index(leiden),
        load_graph_signal_pages([graph]),
    )
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
    assert result["total_match_count"] == 0
    assert "120-36833" not in result["answer"]


def test_exact_part_still_works(tmp_path: Path):
    table, page_context, leiden, graph = _fixtures(tmp_path)
    result = answer_query(
        "find part number 120-36833-503",
        load_source_truth_records(table),
        build_page_summary_index(page_context),
        build_leiden_index(leiden),
        load_graph_signal_pages([graph]),
    )
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"
    assert "120-36833-503" in result["answer"]


def test_relationship_navigation_uses_guidance_only(tmp_path: Path):
    table, page_context, leiden, graph = _fixtures(tmp_path)
    result = answer_query(
        "What pages are related to part number 120-36833-503?",
        load_source_truth_records(table),
        build_page_summary_index(page_context),
        build_leiden_index(leiden),
        load_graph_signal_pages([graph]),
    )
    assert result["relationship_query"] is True
    assert result["relationship_guidance_only"] is True
    assert result["relationship_proof_violation"] is False
    assert "guidance only" in result["answer"]


def test_build_report_quality_passes(tmp_path: Path):
    table, page_context, leiden, graph = _fixtures(tmp_path)
    report = build_report(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        output_dir=tmp_path / "out",
        host="127.0.0.1",
        port=8025,
        llm_mode="simulate",
        llm_model="gemma4:26b",
        relationship_mode="guarded",
        graph_signal_paths=[graph],
        include_standard_demo_queries=True,
        min_sample_queries=8,
        min_sample_successes=8,
        min_metadata_count_samples=2,
        max_bad_broad_fallback_count=0,
        require_no_answer_permission=True,
        quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["metadata_count_sample_count"] >= 2
    assert report["bad_broad_fallback_count"] == 0
    assert report["graph_has_context_page_count"] >= 1
    assert report["graph_has_nomenclature_part_count"] >= 1
