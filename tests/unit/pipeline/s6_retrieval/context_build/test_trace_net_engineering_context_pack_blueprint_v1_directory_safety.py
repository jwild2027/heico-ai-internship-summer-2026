import json
from pathlib import Path

from tiff.trace_net_engineering_context_pack_blueprint_v1 import (
    build_engineering_context_pack_blueprint,
    _write_json,
    _write_jsonl,
    _write_markdown,
)


def _planner_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "question_id": "engineering_q0001",
                "user_question": "Find part number 120-29073-001 and nearby similar parts.",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "seed_entities": ["120-29073-001"],
                "requested_change": None,
                "forbidden_answer_claims": ["approved replacement", "guaranteed fit"],
                "evidence_policy": {"candidate_language_required": False},
                "dynamic_context_pack_blueprint": {
                    "route_context_needed": ["graph", "normal_text", "route_dispatch", "table"],
                    "context_budget": {"table_records": 12},
                    "compression_policy": {"prefer_source_truth_over_summary": True},
                    "sections_in_order": [
                        "system_engineering_role",
                        "selected_engineering_playbook",
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


def test_writer_helpers_create_parent_directories(tmp_path):
    _write_json(tmp_path / "a" / "b" / "payload.json", {"ok": True})
    _write_jsonl(tmp_path / "c" / "d" / "records.jsonl", [{"x": 1}])
    _write_markdown(
        tmp_path / "e" / "f" / "report.md",
        {"quality_status": "PASS", "summary": {"context_pack_blueprint_count": 0}, "records": []},
    )

    assert (tmp_path / "a" / "b" / "payload.json").exists()
    assert (tmp_path / "c" / "d" / "records.jsonl").exists()
    assert (tmp_path / "e" / "f" / "report.md").exists()


def test_blueprint_build_creates_clean_nested_stage_directory(tmp_path):
    planner = tmp_path / "stage_reports" / "query_planner" / "trace_net_engineering_query_planner_v1.json"
    planner.parent.mkdir(parents=True)
    planner.write_text(json.dumps(_planner_payload()), encoding="utf-8")

    output_dir = tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint"
    payload = build_engineering_context_pack_blueprint(query_planner_path=planner, output_dir=output_dir)

    assert payload["quality_status"] == "PASS"
    assert (output_dir / "trace_net_engineering_context_pack_blueprint_v1.json").exists()
    assert (output_dir / "trace_net_engineering_context_pack_blueprint_v1_records.jsonl").exists()
    assert (output_dir / "trace_net_engineering_context_pack_blueprint_v1.md").exists()
