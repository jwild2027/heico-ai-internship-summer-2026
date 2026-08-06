from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_rag_demo_report_v1 import build_e2e_rag_demo_report


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    planning = {
        "quality_status": "PASS",
        "summary": {"query_route_plan_count": 5, "total_query_tunnel_count": 20, "unique_tunnel_type_count": 4, "answer_permission_count": 0},
        "query_route_plans": [
            {"query_id": f"q{i}", "query_intent": "covered_part_number", "user_query": f"Find {i}", "tunnel_types": ["graph_source_trace_tunnel", "table_route_summary_tunnel"], "planned_retrieval_order": [{"step": 1}, {"step": 2}]}
            for i in range(5)
        ],
    }
    runtime = {
        "quality_status": "PASS",
        "summary": {"retrieval_group_count": 5, "successful_retrieval_query_count": 5, "total_retrieval_hit_count": 50, "answer_permission_count": 0},
        "retrieval_groups": [
            {"query_id": f"q{i}", "retrieval_status": "RETRIEVAL_MATCHED", "hit_count": 5, "page_ids": [f"p{i}"], "hits": []}
            for i in range(5)
        ],
    }
    context = {
        "quality_status": "PASS",
        "summary": {"context_pack_count": 5, "total_context_item_count": 25, "citation_ready_context_item_count": 25, "source_trace_ready_context_item_count": 25},
        "context_packs": [
            {"query_id": f"q{i}", "context_pack_status": "CONTEXT_PACK_READY", "context_item_count": 5, "top_context_items": [{"page_id": f"p{i}", "field_name": "covered_part_number", "normalized_value": f"v{i}", "citation_ready": True, "source_trace_ready": True}]}
            for i in range(5)
        ],
    }
    sufficiency = {
        "quality_status": "PASS",
        "summary": {"final_gate_review_ready_pack_count": 5, "sufficient_context_pack_count": 5},
        "gate_records": [
            {"query_id": f"q{i}", "evidence_sufficiency_status": "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW", "page_ids": [f"p{i}"]}
            for i in range(5)
        ],
    }
    final_gate = {
        "quality_status": "PASS",
        "summary": {"final_gate_record_count": 5, "safe_response_draft_count": 5, "citation_backed_response_draft_count": 5, "total_citation_count": 15, "page_with_citation_count": 5, "field_count": 3},
        "final_gate_records": [
            {"query_id": f"q{i}", "final_gate_decision": "SAFE_RESPONSE_DRAFT", "response_draft": f"Draft {i}", "citation_count": 3, "page_ids": [f"p{i}"], "citations": [{"citation_id": f"c{i}", "page_id": f"p{i}", "field_name": "covered_part_number", "normalized_value": f"v{i}"}]}
            for i in range(5)
        ],
    }
    paths = {}
    for name, data in [("planning", planning), ("runtime", runtime), ("context", context), ("sufficiency", sufficiency), ("final", final_gate)]:
        path = tmp_path / f"{name}.json"
        _write(path, data)
        paths[name] = path
    return paths


def test_build_report_passes(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report = build_e2e_rag_demo_report(
        query_planning_routing_path=paths["planning"],
        e2e_hybrid_retrieval_runtime_path=paths["runtime"],
        e2e_context_pack_builder_path=paths["context"],
        e2e_evidence_sufficiency_gate_path=paths["sufficiency"],
        e2e_final_gate_smoke_path=paths["final"],
        output_dir=tmp_path / "out",
        thresholds={
            "min_stage_passes": 5,
            "min_demo_records": 5,
            "min_complete_demo_flows": 5,
            "min_route_plans": 5,
            "min_total_tunnels": 10,
            "min_retrieval_groups": 5,
            "min_successful_retrieval_queries": 5,
            "min_context_packs": 5,
            "min_final_gate_ready_packs": 5,
            "min_final_gate_records": 5,
            "min_safe_response_drafts": 5,
            "min_citation_backed_response_drafts": 5,
            "min_total_citations": 10,
            "min_pages_cited": 2,
            "min_field_count": 1,
        },
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["complete_demo_flow_count"] == 5
    assert report["summary"]["answer_permission_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["records_jsonl_path"]).exists()
    assert Path(report["inspect_md_path"]).exists()


def test_report_blocks_answer_authority(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report = build_e2e_rag_demo_report(
        query_planning_routing_path=paths["planning"],
        e2e_hybrid_retrieval_runtime_path=paths["runtime"],
        e2e_context_pack_builder_path=paths["context"],
        e2e_evidence_sufficiency_gate_path=paths["sufficiency"],
        e2e_final_gate_smoke_path=paths["final"],
        output_dir=tmp_path / "out2",
        thresholds={"min_stage_passes": 5, "min_demo_records": 5, "min_complete_demo_flows": 5},
    )
    assert report["demo_contract"]["answer_authority"] == "blocked_in_artifact_smoke"
    assert all(not r["can_answer_directly"] for r in report["demo_records"])
    assert all(not r["can_prove_claims"] for r in report["demo_records"])


def test_incomplete_flow_fails_quality(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    final = json.loads(paths["final"].read_text(encoding="utf-8"))
    final["final_gate_records"] = final["final_gate_records"][:4]
    paths["final"].write_text(json.dumps(final), encoding="utf-8")
    report = build_e2e_rag_demo_report(
        query_planning_routing_path=paths["planning"],
        e2e_hybrid_retrieval_runtime_path=paths["runtime"],
        e2e_context_pack_builder_path=paths["context"],
        e2e_evidence_sufficiency_gate_path=paths["sufficiency"],
        e2e_final_gate_smoke_path=paths["final"],
        output_dir=tmp_path / "out3",
        thresholds={"min_stage_passes": 5, "min_demo_records": 5, "min_complete_demo_flows": 5},
    )
    assert report["summary"]["complete_demo_flow_count"] == 4
    assert report["quality_status"] == "FAIL"


def test_quality_checks_are_serializable(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report = build_e2e_rag_demo_report(
        query_planning_routing_path=paths["planning"],
        e2e_hybrid_retrieval_runtime_path=paths["runtime"],
        e2e_context_pack_builder_path=paths["context"],
        e2e_evidence_sufficiency_gate_path=paths["sufficiency"],
        e2e_final_gate_smoke_path=paths["final"],
        output_dir=tmp_path / "out4",
        thresholds={},
    )
    json.dumps(report["quality_checks"])
    assert report["quality_checks"]
