import json
from pathlib import Path

from tiff.trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1 import (
    build_llm_prompt,
    build_prompt_retrieval_llm_smoke,
    check_prompt_retrieval_llm_smoke,
    detect_unsupported_claims,
)


def _prompt_smoke(tmp_path: Path) -> Path:
    p = tmp_path / "prompt_smoke.json"
    records = [
        {
            "query_id": "q_interchange",
            "task_type": "interchangeability_boundary",
            "query_text": "Is A interchangeable with B?",
            "selected_atom_count": 4,
            "selected_layers": ["procedural_memory", "critic_memory"],
            "selected_proof_roles": ["guidance_only"],
            "integration_prompt_text": "TRACE-NET guidance: require explicit authority. Engram is not proof.",
        },
        {
            "query_id": "q_unknown",
            "task_type": "unknown_part",
            "query_text": "Find part 999.",
            "selected_atom_count": 4,
            "selected_layers": ["working_memory"],
            "selected_proof_roles": ["current_proof_context_only"],
            "integration_prompt_text": "If proof_context missing, say not source-trace-ready.",
        },
    ]
    p.write_text(json.dumps({
        "quality_status": "PASS",
        "prompt_integration_records": records,
        "summary": {"query_count": 2},
    }), encoding="utf-8")
    return p


def test_detect_unsupported_claims_respects_negation():
    assert detect_unsupported_claims("This is interchangeable with that.")
    assert not detect_unsupported_claims("This is not proven; it is not interchangeable with that.")


def test_build_prompt_contains_boundary():
    prompt = build_llm_prompt({
        "query_id": "q",
        "task_type": "summary_limit",
        "query_text": "Can summaries prove it?",
        "integration_prompt_text": "guidance only",
    })
    assert "behavior guidance only" in prompt
    assert "CURRENT PROOF_CONTEXT" in prompt
    assert "Manual/source claims still require current proof_context" in prompt


def test_build_artifact_mode_passes(tmp_path):
    source = _prompt_smoke(tmp_path)
    result = build_prompt_retrieval_llm_smoke(
        prompt_smoke=source,
        output_dir=tmp_path / "out",
        llm_mode="artifact",
        max_queries=2,
        min_queries=2,
        min_llm_answered=2,
        min_good_answers=2,
        max_bad_answers=0,
        max_unsupported_claims=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["good_answer_count"] == 2
    assert result["summary"]["write_attempt_count"] == 0
    assert Path(result["output_path"]).exists()


def test_check_artifact(tmp_path):
    source = _prompt_smoke(tmp_path)
    result = build_prompt_retrieval_llm_smoke(
        prompt_smoke=source,
        output_dir=tmp_path / "out",
        llm_mode="artifact",
        max_queries=2,
        min_queries=2,
        min_llm_answered=2,
        min_good_answers=2,
    )
    checked = check_prompt_retrieval_llm_smoke(
        llm_smoke=result["output_path"],
        min_queries=2,
        min_llm_answered=2,
        min_good_answers=2,
        require_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert checked["quality_status"] == "PASS"
