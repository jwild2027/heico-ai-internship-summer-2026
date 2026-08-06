import json
from pathlib import Path

from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import (
    build_answer_runner_prompt_overlay_smoke_manifest,
    build_overlay_records,
    build_overlay_text,
    check_answer_runner_prompt_overlay_smoke_manifest,
)


def _bridge(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "summary": {
            "unsafe_finding_count": 0,
            "answer_permission_count": 0,
            "write_attempt_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_read_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
        },
        "bridge_records": [
            {
                "query_id": "h19_q_interchangeability_boundary",
                "task_type": "interchangeability_boundary",
                "target_answer_runner_question_ids": ["q12", "q21"],
                "selected_layers": ["procedural_memory", "critic_memory"],
                "selected_proof_roles": ["guidance_only"],
                "guidance_overlay_text": "Use these atoms to shape answer behavior only. Do not use Engram memory as manual evidence. Manual/source claims still require current proof_context citations.",
                "answer_permission": False,
                "write_attempt": False,
            },
            {
                "query_id": "h19_q_summary_only_limit",
                "task_type": "summary_limit",
                "target_answer_runner_question_ids": ["q29"],
                "selected_layers": ["working_memory"],
                "selected_proof_roles": ["current_proof_context_only"],
                "guidance_overlay_text": "TRACE-NET guidance is behavior only, not proof. Manual/source claims still require current proof_context citations.",
                "answer_permission": False,
                "write_attempt": False,
            },
        ],
    }
    p = tmp_path / "bridge.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _smoke(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "records": [
            {"question_id": "q12", "question": "Is A interchangeable with B?", "grade": "GOOD", "proof_context_count": 8},
            {"question_id": "q29", "question": "Can summaries prove it?", "grade": "GOOD", "proof_context_count": 3},
        ],
    }
    p = tmp_path / "smoke.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_overlay_text_contains_boundaries():
    overlay = build_overlay_text("q12", [{"query_id": "q", "task_type": "t", "guidance_overlay_text": "shape answer behavior only; not proof; proof_context"}])
    assert "behavior guidance only" in overlay
    assert "Manual/source claims still require current proof_context citations" in overlay
    assert "not proof" in overlay.lower()


def test_build_overlay_records_maps_question():
    bridge = json.loads(_bridge(Path.cwd()).read_text(encoding="utf-8"))
    records = build_overlay_records(bridge, question_ids="q12,q29")
    assert len(records) == 2
    q12 = [r for r in records if r["question_id"] == "q12"][0]
    assert q12["matched_bridge_record_count"] == 1
    assert q12["unsafe"] is False


def test_build_manifest_passes(tmp_path):
    result = build_answer_runner_prompt_overlay_smoke_manifest(
        bridge=_bridge(tmp_path),
        source_answer_smoke=_smoke(tmp_path),
        output_dir=tmp_path / "out",
        question_ids="q12,q29",
        min_overlay_records=2,
        min_matched_bridge_records=2,
        require_h23_quality_pass=True,
        require_source_answer_smoke_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["overlay_record_count"] == 2
    assert result["summary"]["matched_bridge_record_count"] == 2


def test_check_manifest(tmp_path):
    result = build_answer_runner_prompt_overlay_smoke_manifest(
        bridge=_bridge(tmp_path),
        output_dir=tmp_path / "out",
        question_ids="q12,q29",
        min_overlay_records=2,
        min_matched_bridge_records=2,
    )
    checked = check_answer_runner_prompt_overlay_smoke_manifest(
        overlay_smoke=Path(result["output_path"]),
        min_overlay_records=2,
        min_matched_bridge_records=2,
        require_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert checked["quality_status"] == "PASS"


def test_missing_bridge_record_is_unsafe(tmp_path):
    bridge = json.loads(_bridge(tmp_path).read_text(encoding="utf-8"))
    records = build_overlay_records(bridge, question_ids="q99")
    assert records[0]["unsafe"] is True
    assert "no_bridge_guidance_for_question" in records[0]["unsafe_findings"]
