
import json
from pathlib import Path

from tiff.trace_net_engineering_context_draft_packet_v1 import (
    build_engineering_context_draft_packet,
    check_engineering_context_draft_packet_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _context_pack_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "context_pack_id": "engineering_context_pack_0001",
                "question_id": "q1",
                "user_question": "Find part number 120-29073-001 and nearby similar parts.",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "seed_entities": ["120-29073-001"],
                "route_evidence_capsules": {
                    "table": [
                        {
                            "route": "table",
                            "trust_tier": "exact_source_evidence_candidate",
                            "source_text_excerpt": "120-29073-001 LATERAL STRUCTURE",
                            "page_id": "p1",
                            "source_trace_ready": True,
                            "match_score": 101,
                            "fallback_available_context": False,
                        }
                    ],
                    "graph": [
                        {
                            "route": "graph",
                            "trust_tier": "relationship_candidate",
                            "source_text_excerpt": "same assembly neighbor",
                            "page_id": "p2",
                            "source_trace_ready": True,
                            "match_score": 7,
                            "fallback_available_context": False,
                        }
                    ],
                },
                "sections": [
                    {
                        "section_id": "structured_user_intent",
                        "content": {"seed_entities": ["120-29073-001"], "requested_change": None},
                    }
                ],
                "missing_evidence": [],
                "forbidden_answer_claims": ["unverified alternate part"],
                "answer_format_contract": {"answer_mode": "exact_evidence_first_then_related_context"},
            },
            {
                "context_pack_id": "engineering_context_pack_0002",
                "question_id": "q2",
                "user_question": "This part needs to be shorter.",
                "intent_family": "engineering_change_candidate",
                "selected_playbook_id": "dimensional_change_candidate_search",
                "route_evidence_capsules": {},
                "missing_evidence": [{"missing_type": "source_dimension_not_confirmed"}],
                "forbidden_answer_claims": ["will fit"],
            },
        ],
    }


def _self_rag_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "self_rag_record_id": "self_1",
                "context_pack_id": "engineering_context_pack_0001",
                "ready_for_gemma_draft": True,
                "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY",
                "evidence_strength_score": 90,
                "source_truth_evidence_strength": "strong_exact_source_truth",
                "route_coverage": {"route_coverage_status": "complete_high_signal_route_coverage"},
                "capsule_counts": {"exact_source_capsule_count": 1},
                "crag_retry_required": False,
            },
            {
                "self_rag_record_id": "self_2",
                "context_pack_id": "engineering_context_pack_0002",
                "ready_for_gemma_draft": False,
                "self_rag_status": "CRAG_RETRY_REQUIRED",
                "evidence_strength_score": 40,
                "source_truth_evidence_strength": "partial_source_truth_context",
                "crag_retry_required": True,
            },
        ],
    }


def test_build_draft_packet_filters_only_self_rag_ready(tmp_path):
    context_pack = tmp_path / "context_pack.json"
    self_rag = tmp_path / "self_rag.json"
    _write(context_pack, _context_pack_payload())
    _write(self_rag, _self_rag_payload())

    payload = build_engineering_context_draft_packet(
        context_pack_path=context_pack,
        self_rag_report_path=self_rag,
        output_dir=tmp_path / "out",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["draft_packet_count"] == 1
    assert payload["summary"]["skipped_context_pack_count"] == 1
    record = payload["records"][0]
    assert record["ready_for_gemma_draft"] is True
    assert record["ready_for_final_answer"] is False
    assert record["answer_permission"] is False
    assert record["llm_call_allowed"] is False
    assert record["prompt_contract"]["source_truth_evidence"]
    assert record["prompt_contract"]["candidate_evidence"]


def test_quality_checker_passes(tmp_path):
    context_pack = tmp_path / "context_pack.json"
    self_rag = tmp_path / "self_rag.json"
    _write(context_pack, _context_pack_payload())
    _write(self_rag, _self_rag_payload())
    build_engineering_context_draft_packet(
        context_pack_path=context_pack,
        self_rag_report_path=self_rag,
        output_dir=tmp_path / "out",
    )
    report = tmp_path / "out" / "trace_net_engineering_context_draft_packet_v1.json"

    result = check_engineering_context_draft_packet_quality(
        report_path=report,
        require_source_context_pack_quality_pass=True,
        require_source_self_rag_quality_pass=True,
        min_draft_packets=1,
        min_ready_for_gemma_draft=1,
        max_ready_for_final_answer=0,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
