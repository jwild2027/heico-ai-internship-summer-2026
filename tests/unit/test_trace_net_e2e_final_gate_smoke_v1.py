from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_final_gate_smoke_v1 import build_final_gate_smoke, evaluate_quality


def _source(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "evidence_sufficiency_contract": {"ready_for_final_gate_smoke": True},
        "summary": {"ready_for_final_gate_smoke": True},
        "gate_records": [
            {
                "query_id": "q1",
                "query_intent": "covered_part_number",
                "user_query": "Find part number 120-36833-001",
                "evidence_sufficiency_status": "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW",
                "context_item_count": 3,
                "page_ids": ["t_p_120_1176_p000003"],
                "evidence_items": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-001",
                        "citation_ready": True,
                        "source_trace_ready": True,
                        "retrieval_score": 988.2,
                        "routing_boost": 1.35,
                    },
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-003",
                        "citation_ready": True,
                        "source_trace_ready": True,
                    },
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-005",
                        "citation_ready": True,
                        "source_trace_ready": True,
                    },
                ],
                "audit_reasons": [],
            },
            {
                "query_id": "q2",
                "query_intent": "manual_page_reference",
                "user_query": "Where is manual reference 25-21-00 used?",
                "evidence_sufficiency_status": "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW",
                "page_ids": ["t_p_120_1176_p000005"],
                "top_evidence_items": [
                    {
                        "page_id": "t_p_120_1176_p000005",
                        "field_name": "manual_page_reference",
                        "normalized_value": "25-21-00",
                        "citation_ready": True,
                        "source_trace_ready": True,
                    }
                ],
                "audit_reasons": [],
            },
        ],
    }
    p = tmp_path / "gate.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_build_final_gate_smoke_pass(tmp_path: Path) -> None:
    report = build_final_gate_smoke(
        evidence_sufficiency_gate_path=_source(tmp_path),
        output_dir=tmp_path / "out",
        top_k=3,
        min_source_gate_records=2,
        min_final_gate_records=2,
        min_safe_response_drafts=2,
        min_citation_backed_response_drafts=2,
        min_audit_or_safe_responses=2,
        min_total_citations=2,
        min_pages_cited=1,
        min_field_count=2,
        require_source_sufficiency_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["final_gate_record_count"] == 2
    assert report["summary"]["safe_response_draft_count"] == 2
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["can_answer_directly_count"] == 0
    assert report["summary"]["can_prove_claims_count"] == 0
    assert (tmp_path / "out" / "trace_net_e2e_final_gate_smoke_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_e2e_final_gate_smoke_v1_inspect.md").exists()


def test_audit_only_when_insufficient(tmp_path: Path) -> None:
    src = {
        "quality_status": "PASS",
        "evidence_sufficiency_contract": {"ready_for_final_gate_smoke": True},
        "gate_records": [
            {
                "query_id": "q1",
                "query_intent": "unknown",
                "user_query": "bad query",
                "evidence_sufficiency_status": "AUDIT_ONLY_INSUFFICIENT_EVIDENCE",
                "page_ids": [],
                "audit_reasons": ["not_enough_evidence"],
            }
        ],
    }
    p = tmp_path / "gate.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    report = build_final_gate_smoke(
        evidence_sufficiency_gate_path=p,
        output_dir=tmp_path / "out",
        min_safe_response_drafts=0,
        min_citation_backed_response_drafts=0,
        min_total_citations=0,
        min_pages_cited=0,
        min_field_count=0,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["audit_only_response_count"] == 1
    assert report["final_gate_records"][0]["final_gate_decision"] == "FINAL_GATE_AUDIT_ONLY_RESPONSE"


def test_quality_fails_on_answer_permission() -> None:
    checks = evaluate_quality(
        {
            "source_gate_record_count": 1,
            "final_gate_record_count": 1,
            "safe_response_draft_count": 1,
            "citation_backed_response_draft_count": 1,
            "audit_or_safe_response_count": 1,
            "total_citation_count": 1,
            "page_with_citation_count": 1,
            "field_count": 1,
            "schema_missing_required_key_record_count": 0,
            "unsafe_final_gate_smoke_record_count": 0,
            "answer_permission_count": 1,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "all_final_gate_smoke_records_no_answer_authority": False,
        },
        require_no_answer_permission=True,
    )
    assert any(not c["passed"] for c in checks if c["name"] in {"answer_permission_count", "all_final_gate_smoke_records_no_answer_authority"})


def test_fallback_page_citation(tmp_path: Path) -> None:
    src = {
        "quality_status": "PASS",
        "evidence_sufficiency_contract": {"ready_for_final_gate_smoke": True},
        "gate_records": [
            {
                "query_id": "q1",
                "query_intent": "covered_part_number",
                "user_query": "Find part",
                "evidence_sufficiency_status": "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW",
                "page_ids": ["p1"],
            }
        ],
    }
    p = tmp_path / "gate.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    report = build_final_gate_smoke(evidence_sufficiency_gate_path=p, output_dir=tmp_path / "out")
    assert report["summary"]["safe_response_draft_count"] == 1
    assert report["final_gate_records"][0]["citations"][0]["page_id"] == "p1"
