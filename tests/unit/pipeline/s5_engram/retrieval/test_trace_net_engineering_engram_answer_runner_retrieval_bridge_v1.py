import json
from pathlib import Path

from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import (
    build_answer_runner_retrieval_bridge_manifest,
    build_bridge_records,
    check_answer_runner_retrieval_bridge_manifest,
)


def _prompt_injector(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "summary": {
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_read_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": 0,
            "unsafe_finding_count": 0,
        },
        "prompt_bundles": [
            {"query_id": "h19_q_interchangeability_boundary", "task_type": "interchangeability_boundary", "selected_atom_count": 4, "selected_layers": ["procedural_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context require explicit authority"},
            {"query_id": "h19_q_visual_ocr_route_behavior", "task_type": "route_explanation", "selected_atom_count": 4, "selected_layers": ["semantic_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context visual OCR nomenclature"},
            {"query_id": "h19_q_unknown_part_not_source_trace_ready", "task_type": "unknown_part", "selected_atom_count": 4, "selected_layers": ["working_memory"], "selected_proof_roles": ["current_proof_context_only", "guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context no proof_context not source-trace-ready"},
            {"query_id": "h19_q_safe_but_too_generic_repair", "task_type": "critic_repair", "selected_atom_count": 4, "selected_layers": ["critic_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context safe but too generic repair"},
            {"query_id": "h19_q_summary_only_limit", "task_type": "summary_limit", "selected_atom_count": 4, "selected_layers": ["working_memory"], "selected_proof_roles": ["current_proof_context_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context summaries not proof"},
            {"query_id": "h19_q_installation_fit_effectivity_limit", "task_type": "approval_boundary", "selected_atom_count": 4, "selected_layers": ["procedural_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context figure identification not approval"},
        ],
    }
    p = tmp_path / "prompt_injector.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _h22_smoke(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "summary": {
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_read_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": 0,
            "unsafe_finding_count": 0,
        },
        "smoke_records": [
            {"query_id": "h19_q_interchangeability_boundary", "grade": "GOOD", "unsupported_claim_count": 0},
            {"query_id": "h19_q_visual_ocr_route_behavior", "grade": "GOOD", "unsupported_claim_count": 0},
            {"query_id": "h19_q_unknown_part_not_source_trace_ready", "grade": "GOOD", "unsupported_claim_count": 0},
            {"query_id": "h19_q_safe_but_too_generic_repair", "grade": "GOOD", "unsupported_claim_count": 0},
            {"query_id": "h19_q_summary_only_limit", "grade": "GOOD", "unsupported_claim_count": 0},
            {"query_id": "h19_q_installation_fit_effectivity_limit", "grade": "GOOD", "unsupported_claim_count": 0},
        ],
    }
    p = tmp_path / "h22.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_bridge_records_map_to_answer_runner_questions(tmp_path):
    prompt_path = _prompt_injector(tmp_path)
    data = json.loads(prompt_path.read_text())
    records = build_bridge_records(data)
    assert len(records) == 6
    rec = next(r for r in records if r["task_type"] == "interchangeability_boundary")
    assert "q12" in rec["target_answer_runner_question_ids"]
    assert rec["answer_permission"] is False
    assert rec["engram_is_proof"] is False
    assert not rec["unsafe"]


def test_build_bridge_passes_with_h22(tmp_path):
    result = build_answer_runner_retrieval_bridge_manifest(
        prompt_injector=_prompt_injector(tmp_path),
        h22_llm_smoke=_h22_smoke(tmp_path),
        output_dir=tmp_path / "out",
        min_bridge_records=6,
        min_task_types=6,
        require_h20_quality_pass=True,
        require_h22_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["target_answer_runner_question_count"] >= 6
    assert Path(result["guidance_map_path"]).exists()


def test_check_bridge_artifact(tmp_path):
    result = build_answer_runner_retrieval_bridge_manifest(
        prompt_injector=_prompt_injector(tmp_path),
        h22_llm_smoke=_h22_smoke(tmp_path),
        output_dir=tmp_path / "out",
        require_h20_quality_pass=True,
        require_h22_quality_pass=True,
    )
    check = check_answer_runner_retrieval_bridge_manifest(
        bridge=result["output_path"],
        min_bridge_records=6,
        min_task_types=5,
        require_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert check["quality_status"] == "PASS"


def test_h20_prompt_wording_is_safe_boundary():
    data = {
        "quality_status": "PASS",
        "summary": {
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_read_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": 0,
            "unsafe_finding_count": 0,
        },
        "prompt_bundles": [
            {
                "query_id": "h19_q_visual_ocr_route_behavior",
                "task_type": "route_explanation",
                "selected_atom_count": 4,
                "selected_layers": ["semantic_memory"],
                "selected_proof_roles": ["guidance_only"],
                "prompt_guidance_text": "TRACE-NET ENGRAM RETRIEVAL GUIDANCE — BEHAVIOR ONLY, NOT PROOF\nUse these retrieved Engram atoms to shape answer behavior only. Do not use Engram memory as manual evidence. Manual/source claims still require current proof_context citations from TRACE-Net.",
            }
        ],
    }
    records = build_bridge_records(data)
    assert records[0]["unsafe"] is False
    assert records[0]["unsafe_findings"] == []


def test_missing_boundary_is_unsafe(tmp_path):
    data = json.loads(_prompt_injector(tmp_path).read_text())
    data["prompt_bundles"][0]["prompt_guidance_text"] = "missing the required boundary"
    records = build_bridge_records(data)
    assert records[0]["unsafe"] is True
    assert records[0]["unsafe_findings"]
