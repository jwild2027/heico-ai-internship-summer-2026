from pathlib import Path

from tiff.trace_net_engineering_llm_answer_smoke_v1 import (
    _build_reasoning_trace,
    _short_run_dir,
    evaluate_llm_answer,
)


def test_h13_nested_run_dirs_are_short_and_hash_only(tmp_path):
    run_dir = _short_run_dir(
        tmp_path,
        1,
        "interchangeability",
        "Is 120-50645-005 interchangeable with 120-50645-011?",
    )
    assert run_dir.name.startswith("q01_")
    assert "interchange" not in run_dir.name
    assert len(run_dir.name) <= 11


def test_safe_reasoning_trace_is_not_hidden_chain_of_thought(tmp_path):
    context_pack = {
        "records": [
            {
                "proof_context": [
                    {
                        "citation_label": "V6",
                        "context_type": "visual_figure_link",
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "source_trace_ready": True,
                    }
                ],
                "guidance_context": [],
                "answer_constraints": {"summary_guidance_policy": "guidance only"},
            }
        ]
    }
    eval_result = evaluate_llm_answer(
        answer_text="Figure 69 is linked to 120-50645-005 [V6].",
        proof_context=context_pack["records"][0]["proof_context"],
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
    )
    trace = _build_reasoning_trace(
        question_id="q01",
        category="figure_lookup",
        question="What does figure 69 show?",
        runner_manifest={"quality_status": "PASS", "summary": {"task_type": "visual_part_identification"}},
        context_pack=context_pack,
        prompt_path=tmp_path / "p.txt",
        answer_path=tmp_path / "a.txt",
        prompt="INTENT_RULE: answer with citations\nSTRUCTURED_TRACE_NET_SCAFFOLD",
        answer_text="Figure 69 is linked to 120-50645-005 [V6].",
        eval_result=eval_result,
        llm_error="",
    )
    assert trace["trace_type"] == "safe_reasoning_trace_not_hidden_chain_of_thought"
    assert "not raw model hidden reasoning" in trace["trace_note"]
    assert trace["available_citation_labels"] == ["V6"]
    assert trace["gate_result"]["grade"] == "GOOD"
    assert trace["scaffold_present"] is True


def test_negated_approval_answer_remains_safe():
    answer = "Not proven. The evidence does not prove this is an approved replacement [V6]."
    proof_context = [{"citation_label": "V6", "source_trace_ready": True}]
    result = evaluate_llm_answer(
        answer_text=answer,
        proof_context=proof_context,
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
    )
    assert result["unsupported_claim_count"] == 0
    assert result["grade"] == "GOOD"


def test_blocked_trace_records_error_without_answer(tmp_path):
    trace = _build_reasoning_trace(
        question_id="np05",
        category="troubleshooting",
        question="Why was nomenclature missing from the visual route evidence?",
        runner_manifest={},
        context_pack={},
        prompt_path=tmp_path / "p.txt",
        answer_path=tmp_path / "a.txt",
        prompt="",
        answer_text="",
        eval_result={"grade": "BLOCKED", "llm_answered": False, "unsupported_claim_count": 0},
        llm_error="runner error: sample",
    )
    assert trace["llm_error"] == "runner error: sample"
    assert trace["gate_result"]["grade"] == "BLOCKED"
    assert trace["proof_context_count"] == 0


def test_shortened_full_nested_quality_check_path_stays_under_windows_limit():
    base = Path("C:/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026/local_data/organization/trace_net/engineering_llm_answer_smoke_h14b_not_proven_rerun_v1")
    run_dir = _short_run_dir(base / "r", 13, "limitations", "Give the engineering limitations for Figure 91.")
    nested = run_dir / "r" / "context_pack" / "trace_net_engineering_answer_context_pack_v1_quality_check.json"
    assert len(str(nested)) < 260
