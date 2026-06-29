import inspect
import json
from pathlib import Path

from tiff import trace_net_engineering_context_pack_blueprint_v1 as mod


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


def test_writer_helpers_directly_create_parent_dirs(tmp_path: Path) -> None:
    mod._write_json(tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint" / "trace_net_engineering_context_pack_blueprint_v1.json", {"ok": True})
    mod._write_jsonl(tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint" / "trace_net_engineering_context_pack_blueprint_v1_records.jsonl", [{"x": 1}])
    mod._write_markdown(
        tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint" / "trace_net_engineering_context_pack_blueprint_v1.md",
        {"quality_status": "PASS", "summary": {"context_pack_blueprint_count": 0}, "records": []},
    )

    assert (tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint" / "trace_net_engineering_context_pack_blueprint_v1.json").exists()
    assert (tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint" / "trace_net_engineering_context_pack_blueprint_v1_records.jsonl").exists()
    assert (tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint" / "trace_net_engineering_context_pack_blueprint_v1.md").exists()


def test_runtime_write_json_contains_parent_mkdir_guard() -> None:
    source = inspect.getsource(mod._write_json)
    assert "path.parent.mkdir" in source
    assert "parents=True" in source


def test_real_blueprint_build_writes_into_clean_webui_sample_path(tmp_path: Path) -> None:
    planner = tmp_path / "sample_bridge_preflight" / "stage_reports" / "query_planner" / "trace_net_engineering_query_planner_v1.json"
    planner.parent.mkdir(parents=True, exist_ok=True)
    planner.write_text(json.dumps(_planner_payload()), encoding="utf-8")

    output_dir = tmp_path / "sample_bridge_preflight" / "stage_reports" / "context_pack_blueprint"
    payload = mod.build_engineering_context_pack_blueprint(query_planner_path=planner, output_dir=output_dir)

    assert payload["quality_status"] == "PASS"
    assert (output_dir / "trace_net_engineering_context_pack_blueprint_v1.json").exists()
    assert (output_dir / "trace_net_engineering_context_pack_blueprint_v1_records.jsonl").exists()
    assert (output_dir / "trace_net_engineering_context_pack_blueprint_v1.md").exists()
