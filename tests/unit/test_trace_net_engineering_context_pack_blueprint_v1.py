
import json
from pathlib import Path

from tiff.trace_net_engineering_context_pack_blueprint_v1 import (
    build_engineering_context_pack_blueprint,
    check_engineering_context_pack_blueprint_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _planner_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "question_id": "engineering_q0001",
                "user_question": "This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?",
                "intent_family": "engineering_change_candidate",
                "selected_playbook_id": "dimensional_change_candidate_search",
                "seed_entities": ["123-45"],
                "requested_change": {"property": "length", "direction": "decrease", "delta_value": 4.0, "delta_unit": "inches"},
                "forbidden_answer_claims": ["will fit", "approved modification"],
                "evidence_policy": {"candidate_language_required": True},
                "dynamic_context_pack_blueprint": {
                    "route_context_needed": ["graph", "normal_text", "table"],
                    "context_budget": {"table_records": 12},
                    "compression_policy": {"prefer_source_truth_over_summary": True},
                    "sections_in_order": [
                        "system_engineering_role",
                        "selected_engineering_playbook",
                        "few_shot_engineering_examples",
                        "structured_user_intent",
                        "route_handoff_availability",
                        "source_truth_evidence",
                        "candidate_evidence",
                        "missing_evidence",
                        "trust_tier_policy",
                        "forbidden_claims",
                        "answer_format_contract",
                    ],
                },
            }
        ],
    }


def test_build_context_pack_blueprint(tmp_path):
    planner = tmp_path / "planner.json"
    _write(planner, _planner_payload())

    payload = build_engineering_context_pack_blueprint(
        query_planner_path=planner,
        output_dir=tmp_path / "out",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["context_pack_blueprint_count"] == 1
    record = payload["records"][0]
    assert record["candidate_language_required"] is True
    assert record["answer_format_contract"]["answer_mode"] == "candidate_for_engineering_review"
    assert "table" in [slot["route"] for slot in record["route_evidence_slots"]]
    assert record["llm_call_allowed"] is False
    assert record["retrieval_execution_allowed"] is False


def test_quality_checker_passes(tmp_path):
    planner = tmp_path / "planner.json"
    _write(planner, _planner_payload())
    build_engineering_context_pack_blueprint(query_planner_path=planner, output_dir=tmp_path / "out")
    report = tmp_path / "out" / "trace_net_engineering_context_pack_blueprint_v1.json"

    result = check_engineering_context_pack_blueprint_quality(
        report_path=report,
        require_source_query_planner_quality_pass=True,
        min_blueprints=1,
        min_total_route_slots=3,
        min_source_truth_required_blueprints=1,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
