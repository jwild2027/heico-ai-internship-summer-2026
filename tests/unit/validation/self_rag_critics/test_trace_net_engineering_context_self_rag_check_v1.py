
import json
from pathlib import Path

from tiff.trace_net_engineering_context_self_rag_check_v1 import (
    build_engineering_context_self_rag_check,
    check_engineering_context_self_rag_check_quality,
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
                "required_route_slot_count": 2,
                "filled_route_slot_count": 2,
                "high_signal_filled_route_slot_count": 2,
                "missing_evidence": [],
                "forbidden_answer_claims": ["unverified alternate part"],
                "route_evidence_capsules": {
                    "table": [
                        {
                            "trust_tier": "exact_source_evidence_candidate",
                            "fallback_available_context": False,
                            "source_trace_ready": True,
                            "route": "table",
                        }
                    ],
                    "normal_text": [
                        {
                            "trust_tier": "source_context_guidance",
                            "fallback_available_context": False,
                            "source_trace_ready": True,
                            "route": "normal_text",
                        }
                    ],
                },
                "answer_permission": False,
                "llm_call_allowed": False,
                "retrieval_execution_allowed": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "context_pack_id": "engineering_context_pack_0002",
                "question_id": "q2",
                "user_question": "This model needs to be shorter.",
                "intent_family": "engineering_change_candidate",
                "selected_playbook_id": "dimensional_change_candidate_search",
                "required_route_slot_count": 2,
                "filled_route_slot_count": 2,
                "high_signal_filled_route_slot_count": 2,
                "missing_evidence": [
                    {
                        "missing_type": "source_dimension_not_confirmed",
                        "route": "table",
                        "crag_retry_recommended": True,
                    }
                ],
                "forbidden_answer_claims": ["will fit"],
                "route_evidence_capsules": {
                    "table": [
                        {
                            "trust_tier": "structured_table_candidate",
                            "fallback_available_context": False,
                            "source_trace_ready": True,
                            "route": "table",
                        }
                    ],
                    "graph": [
                        {
                            "trust_tier": "relationship_candidate",
                            "fallback_available_context": False,
                            "source_trace_ready": True,
                            "route": "graph",
                        }
                    ],
                },
                "answer_permission": False,
                "llm_call_allowed": False,
                "retrieval_execution_allowed": False,
                "source_truth_mutation_allowed": False,
            },
        ],
    }


def test_self_rag_marks_ready_and_crag_retry(tmp_path):
    context_pack = tmp_path / "context_pack.json"
    _write(context_pack, _context_pack_payload())

    payload = build_engineering_context_self_rag_check(
        context_pack_path=context_pack,
        output_dir=tmp_path / "out",
        min_high_signal_capsules=1,
        min_evidence_strength_score=35,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["self_rag_record_count"] == 2
    assert payload["summary"]["ready_for_gemma_draft_count"] == 1
    assert payload["summary"]["crag_retry_required_count"] == 1
    first, second = payload["records"]
    assert first["ready_for_gemma_draft"] is True
    assert first["answer_permission"] is False
    assert second["crag_retry_required"] is True
    assert "critical_missing:source_dimension_not_confirmed" in second["crag_retry_reasons"]


def test_quality_checker_passes(tmp_path):
    context_pack = tmp_path / "context_pack.json"
    _write(context_pack, _context_pack_payload())
    build_engineering_context_self_rag_check(context_pack_path=context_pack, output_dir=tmp_path / "out")
    report = tmp_path / "out" / "trace_net_engineering_context_self_rag_check_v1.json"

    result = check_engineering_context_self_rag_check_quality(
        report_path=report,
        require_source_context_pack_quality_pass=True,
        min_self_rag_records=2,
        min_ready_for_gemma_draft=1,
        min_crag_retry_required=1,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
