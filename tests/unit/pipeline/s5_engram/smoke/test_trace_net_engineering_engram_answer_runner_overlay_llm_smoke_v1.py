import json
from pathlib import Path

from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import (
    build_answer_runner_overlay_llm_smoke,
    build_overlay_llm_prompt,
    check_answer_runner_overlay_llm_smoke,
    grade_h25_answer,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    p12 = prompt_dir / "q12_prompt.txt"
    p12.write_text("Question q12 proof_context [E1] [O1].", encoding="utf-8")
    p25 = prompt_dir / "q25_prompt.txt"
    p25.write_text("Question q25 no proof_context.", encoding="utf-8")

    source = _write_json(tmp_path / "source.json", {
        "quality_status": "PASS",
        "records": [
            {
                "question_id": "q12",
                "question": "Is A interchangeable with B?",
                "grade": "GOOD",
                "runner_passed": True,
                "runner_quality_status": "PASS",
                "prompt_path": str(p12),
                "answer_text": "Not proven. [E1] shows A, but no explicit authority proves interchangeability.",
            },
            {
                "question_id": "q25",
                "question": "Find part 999.",
                "grade": "PARTIAL",
                "runner_passed": False,
                "runner_quality_status": "FAIL",
                "prompt_path": str(p25),
                "answer_text": "Not found / not source-trace-ready. No proof_context was available.",
            },
        ],
    })
    overlay = _write_json(tmp_path / "overlay.json", {
        "quality_status": "PASS",
        "overlay_records": [
            {
                "question_id": "q12",
                "source_question": "Is A interchangeable with B?",
                "matched_bridge_query_ids": ["h19_q_interchangeability_boundary"],
                "matched_bridge_task_types": ["interchangeability_boundary"],
                "selected_layers": ["procedural_memory"],
                "selected_proof_roles": ["guidance_only"],
                "overlay_text": "Use this overlay as behavior guidance only. It is not proof. Manual/source claims still require current proof_context citations.",
            },
            {
                "question_id": "q25",
                "source_question": "Find part 999.",
                "matched_bridge_query_ids": ["h19_q_unknown_part_not_source_trace_ready"],
                "matched_bridge_task_types": ["unknown_part"],
                "selected_layers": ["working_memory"],
                "selected_proof_roles": ["current_proof_context_only"],
                "overlay_text": "If no proof_context exists, say not found / not source-trace-ready. Engram is not proof.",
            },
        ],
    })
    return overlay, source


def test_build_prompt_contains_overlay_boundary(tmp_path):
    overlay, source = _fixtures(tmp_path)
    o = json.loads(overlay.read_text())["overlay_records"][0]
    s = json.loads(source.read_text())["records"][0]
    prompt = build_overlay_llm_prompt(
        question_id="q12",
        source_record=s,
        overlay_record=o,
        source_prompt_text="source prompt proof_context",
    )
    assert "Retrieved Engram overlay shapes behavior only" in prompt
    assert "Manual/source claims still require current proof_context" in prompt
    assert "SOURCE ANSWER-RUNNER PROMPT" in prompt


def test_grade_catches_unsupported_claim():
    grade, unsupported, reasons = grade_h25_answer("q12", "Answer: A is interchangeable with B.")
    assert grade == "BAD"
    assert unsupported == 1


def test_artifact_build_passes(tmp_path):
    overlay, source = _fixtures(tmp_path)
    result = build_answer_runner_overlay_llm_smoke(
        overlay_smoke=overlay,
        source_answer_smoke=source,
        output_dir=tmp_path / "out",
        question_ids="q12,q25",
        llm_mode="artifact",
        min_queries=2,
        min_llm_answered=2,
        min_good_answers=2,
        min_good_or_partial_answers=2,
        max_bad_answers=0,
        max_unsupported_claims=0,
        require_h24_quality_pass=True,
        require_source_answer_smoke_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["good_answer_count"] == 2
    assert result["summary"]["write_attempt_count"] == 0


def test_check_artifact(tmp_path):
    overlay, source = _fixtures(tmp_path)
    result = build_answer_runner_overlay_llm_smoke(
        overlay_smoke=overlay,
        source_answer_smoke=source,
        output_dir=tmp_path / "out",
        question_ids="q12,q25",
        llm_mode="artifact",
        min_queries=2,
        min_llm_answered=2,
        min_good_answers=2,
        min_good_or_partial_answers=2,
    )
    main = tmp_path / "out" / "trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.json"
    checked = check_answer_runner_overlay_llm_smoke(
        llm_smoke=main,
        min_queries=2,
        min_llm_answered=2,
        min_good_answers=2,
        min_good_or_partial_answers=2,
        require_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert checked["quality_status"] == "PASS"


def test_missing_overlay_fails(tmp_path):
    overlay, source = _fixtures(tmp_path)
    result = build_answer_runner_overlay_llm_smoke(
        overlay_smoke=overlay,
        source_answer_smoke=source,
        output_dir=tmp_path / "out2",
        question_ids="q12,q99",
        llm_mode="artifact",
        min_queries=2,
    )
    assert result["quality_status"] == "FAIL"
    assert any("missing_source_answer_record:q99" in x for x in result["summary"]["unsafe_findings"])
