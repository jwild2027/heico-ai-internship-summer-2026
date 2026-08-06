
import json
from pathlib import Path

from tiff.trace_net_engineering_context_pack_builder_v1 import (
    build_engineering_context_pack_builder,
    check_engineering_context_pack_builder_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _blueprint_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "blueprint_id": "context_pack_blueprint_0001",
                "question_id": "engineering_q0001",
                "user_question": "Find part number 120-29073-001 and nearby similar parts.",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "seed_entities": ["120-29073-001"],
                "requested_change": None,
                "route_evidence_slots": [
                    {"route": "table", "max_records": 4},
                    {"route": "image_visual", "max_records": 4},
                ],
                "section_contracts": [
                    {"section_id": "source_truth_evidence", "required": True, "source_truth_required": True},
                    {"section_id": "candidate_evidence", "required": True},
                    {"section_id": "missing_evidence", "required": True},
                ],
                "answer_format_contract": {"answer_mode": "exact_evidence_first_then_related_context"},
                "self_rag_crag_contract": {"self_rag_checks": ["check claims"], "crag_retry_triggers": ["retry"]},
                "forbidden_answer_claims": ["unverified alternate part"],
            }
        ],
    }


def test_build_context_pack_with_missing_optional_image_artifact(tmp_path):
    blueprint = tmp_path / "blueprint.json"
    table = tmp_path / "table.json"
    missing_image = tmp_path / "missing_image.json"
    _write(blueprint, _blueprint_payload())
    _write(table, {"quality_status": "PASS", "payload": {"exact_search_documents": [{"page_id": "p1", "fields": {"part_number": "120-29073-001"}}]}})

    payload = build_engineering_context_pack_builder(
        blueprint_path=blueprint,
        output_dir=tmp_path / "out",
        table_exact_search_adapter=table,
        image_visual_observer=missing_image,
        max_records_per_slot=4,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["artifact_missing_input_count"] == 1
    assert payload["summary"]["artifact_missing_inputs"][0]["artifact_name"] == "image_visual_observer"
    assert payload["summary"]["total_high_signal_evidence_capsule_count"] >= 1
    assert payload["records"][0]["answer_permission"] is False


def test_quality_checker_allows_missing_optional_by_default(tmp_path):
    blueprint = tmp_path / "blueprint.json"
    table = tmp_path / "table.json"
    _write(blueprint, _blueprint_payload())
    _write(table, {"records": [{"page_id": "p1", "part_number": "120-29073-001"}]})
    build_engineering_context_pack_builder(
        blueprint_path=blueprint,
        output_dir=tmp_path / "out",
        table_exact_search_adapter=table,
        image_visual_observer=tmp_path / "missing.json",
    )
    report = tmp_path / "out" / "trace_net_engineering_context_pack_builder_v1.json"
    result = check_engineering_context_pack_builder_quality(
        report_path=report,
        require_source_blueprint_quality_pass=True,
        min_context_packs=1,
        min_artifact_corpus_records=1,
        min_evidence_capsules=1,
        min_high_signal_evidence_capsules=1,
        min_packs_ready_for_gemma_context=1,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_checker_can_fail_too_many_missing_optional(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_blueprint_quality_status": "PASS",
            "context_pack_count": 1,
            "artifact_corpus_record_count": 1,
            "total_evidence_capsule_count": 1,
            "total_high_signal_evidence_capsule_count": 1,
            "packs_ready_for_gemma_context_count": 1,
            "artifact_missing_input_count": 1,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_context_pack_builder_quality(
        report_path=path,
        max_missing_optional_artifact_inputs=0,
    )
    assert result["quality_status"] == "FAIL"
