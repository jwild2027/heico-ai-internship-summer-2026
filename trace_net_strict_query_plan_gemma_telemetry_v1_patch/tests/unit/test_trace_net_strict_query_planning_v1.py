import json
from pathlib import Path

from tiff.trace_net_e2e_live_orchestrator_endpoint_v25 import (
    build_orchestrator_state,
    detect_query_plan,
    run_live_query,
)


def adapter(path: Path) -> Path:
    rows = [
        {
            "document_id": "manual-real",
            "page_id": "t_p_120_1176_p000003",
            "field_name": "manual_page_reference",
            "normalized_value": "25-21-00",
            "search_text": "ATA 25-21-00",
        },
        {
            "document_id": "ring-real",
            "page_id": "t_p_120_1176_p000055",
            "field_name": "table_text",
            "normalized_value": "RING, LOCKING",
            "search_text": "IPL row RING, LOCKING",
        },
        {
            "document_id": "random",
            "page_id": "t_p_120_1176_p000001",
            "field_name": "table_text",
            "normalized_value": "EDGES, PRESERVED",
            "search_text": "unrelated source evidence",
        },
    ]
    path.write_text(
        json.dumps({"quality_status": "PASS", "exact_search_documents": rows}),
        encoding="utf-8",
    )
    return path


def test_ata_query_is_always_strict_manual_reference():
    plan = detect_query_plan("Search ATA 98-98-98")
    assert plan["query_intent"] == "manual_page_reference"
    assert plan["target_value"] == "98-98-98"
    assert plan["required_source_truth_fields"] == ["manual_page_reference"]
    assert plan["strict_target_match_required"] is True


def test_missing_ata_fails_closed_instead_of_broad_match(tmp_path):
    state = build_orchestrator_state(adapter(tmp_path / "adapter.json"), include_standard_demo_queries=False)
    result = run_live_query("Search ATA 98-98-98", state)
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
    assert result["retrieval"]["direct_evidence"] == []
    assert result["retrieval"]["total_match_count"] == 0


def test_natural_ipl_queries_extract_strict_targets():
    cases = {
        "Search the IPL table for RING, LOCKING": "RING, LOCKING",
        "Find locking ring in the illustrated parts list": "locking ring",
        "Find the IPL row for NONEXISTENT COMPONENT": "NONEXISTENT COMPONENT",
        "Find a table cell containing buckle": "buckle",
        "Find the nomenclature row for latch": "latch",
    }
    for query, target in cases.items():
        plan = detect_query_plan(query)
        assert plan["query_intent"] == "table_text", query
        assert plan["target_value"].lower() == target.lower(), query
        assert plan["strict_target_match_required"] is True


def test_missing_natural_ipl_target_is_audit_only(tmp_path):
    state = build_orchestrator_state(adapter(tmp_path / "adapter.json"), include_standard_demo_queries=False)
    result = run_live_query("Find the IPL row for NONEXISTENT COMPONENT", state)
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
    assert result["retrieval"]["direct_evidence"] == []
    assert result["retrieval"]["total_match_count"] == 0


def test_positive_natural_ipl_query_matches_order_insensitive(tmp_path):
    state = build_orchestrator_state(adapter(tmp_path / "adapter.json"), include_standard_demo_queries=False)
    result = run_live_query("Search the IPL table for LOCKING RING", state)
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"
    assert len(result["retrieval"]["direct_evidence"]) == 1
    assert result["retrieval"]["direct_evidence"][0]["normalized_value"] == "RING, LOCKING"


def test_unknown_dynamic_query_cannot_promote_all_fields(tmp_path):
    plan = detect_query_plan("Tell me something interesting")
    assert plan["query_intent"] == "unknown_dynamic_query"
    assert plan["required_source_truth_fields"] == []
    state = build_orchestrator_state(adapter(tmp_path / "adapter.json"), include_standard_demo_queries=False)
    result = run_live_query("Tell me something interesting", state)
    assert result["retrieval"]["direct_evidence"] == []
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
