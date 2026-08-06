import json
from pathlib import Path

from tiff.trace_net_engineering_llm_answer_smoke_v1 import (
    _short_run_dir,
    build_llm_prompt,
    check_engineering_llm_answer_smoke,
    count_summary_used_as_proof,
    count_unsupported_claims,
    evaluate_llm_answer,
)


def _context_pack():
    return {
        "records": [
            {
                "proof_context": [
                    {
                        "context_type": "visual_figure_link",
                        "citation_label": "V6",
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "page_number": 315,
                        "source_trace_ready": True,
                        "proof_eligible": True,
                    },
                    {
                        "context_type": "ocr_nomenclature",
                        "citation_label": "O1",
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY",
                        "source_trace_ready": True,
                        "proof_eligible": True,
                    },
                ],
                "guidance_context": [
                    {"page_number": 17, "summary_text": "This is guidance only."}
                ],
                "answer_constraints": {
                    "may_not_claim": ["interchangeability", "installation safety"],
                    "summary_guidance_policy": "v2 summaries are not proof",
                },
            }
        ]
    }


def test_prompt_includes_proof_and_forbids_summary_proof():
    prompt = build_llm_prompt(
        question="What does figure 69 show?",
        runner_manifest={"summary": {"task_type": "visual_part_identification"}},
        context_pack=_context_pack(),
    )
    assert "using ONLY the supplied proof_context" in prompt
    assert "guidance_context and v2 summaries" in prompt
    assert "[V6]" in prompt
    assert "DOUBLE PASSENGER SEAT ASSY" in prompt


def test_evaluate_good_answer_with_valid_citations():
    proof = _context_pack()["records"][0]["proof_context"]
    result = evaluate_llm_answer(
        answer_text='Figure 69 identifies part 120-50645-005 as "DOUBLE PASSENGER SEAT ASSY" [V6] [O1].',
        proof_context=proof,
        min_answer_citations=2,
        min_source_trace_ready_citations=2,
    )
    assert result["grade"] == "GOOD"
    assert result["invalid_answer_citation_count"] == 0
    assert result["unsupported_claim_count"] == 0


def test_evaluate_bad_answer_for_invalid_citation_and_unsupported_claim():
    proof = _context_pack()["records"][0]["proof_context"]
    result = evaluate_llm_answer(
        answer_text="The parts are interchangeable and approved [ZZ9].",
        proof_context=proof,
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
    )
    assert result["grade"] == "BAD"
    assert result["invalid_answer_citation_count"] == 1
    assert result["unsupported_claim_count"] >= 1


def test_summary_proof_detection_respects_negation():
    assert count_summary_used_as_proof("V2 summaries prove Figure 69 part identity.") == 1
    assert count_summary_used_as_proof("V2 summaries do not prove Figure 69 part identity.") == 0
    assert count_unsupported_claims("Figure 69 proves installation safety.") == 1
    assert count_unsupported_claims("Figure 69 does not prove installation safety.") == 0


def test_short_run_dir_avoids_long_question_paths(tmp_path):
    q = "Find part number 120-50645-005 and cite the source with a very long sentence that should not become a folder name."
    p = _short_run_dir(tmp_path / "runs", 4, "exact_part_lookup", q)
    assert p.name.startswith("q04_")
    assert len(p.name) < 32
    assert "very_long_sentence" not in p.name


def test_check_engineering_llm_answer_smoke_thresholds(tmp_path):
    manifest = {
        "summary": {
            "smoke_question_count": 2,
            "llm_answered_count": 2,
            "good_answer_count": 1,
            "good_or_partial_answer_count": 2,
            "bad_answer_count": 0,
            "unsupported_claim_count": 0,
            "summary_used_as_proof_count": 0,
            "invalid_answer_citation_count": 0,
            "llava_only_part_identity_claim_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        }
    }
    source = tmp_path / "smoke.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "check.json"
    result = check_engineering_llm_answer_smoke(
        smoke_test=source,
        output=out,
        min_smoke_questions=2,
        min_llm_answered=2,
        min_good_answers=1,
        min_good_or_partial_answers=2,
        max_bad_answers=0,
    )
    assert result["quality_status"] == "PASS"
    assert out.exists()
