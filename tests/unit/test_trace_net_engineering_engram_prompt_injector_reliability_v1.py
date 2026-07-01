from tiff.trace_net_engineering_llm_answer_smoke_v1 import (
    _fallback_answer_from_context,
    _minimal_retry_prompt,
    build_engram_prompt_block,
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
                        "source_trace_ready": True,
                    },
                    {
                        "context_type": "ocr_nomenclature",
                        "citation_label": "O1",
                        "figure": "69",
                        "part_number": "120-50645-005",
                        "nomenclature": "DOUBLE PASSENGER SEAT ASSY",
                        "line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY",
                        "source_trace_ready": True,
                    },
                    {
                        "context_type": "table_ocr_proof",
                        "citation_label": "T1",
                        "part_number": "120-50645-005",
                        "source_trace_ready": True,
                    },
                ],
                "guidance_context": [],
            }
        ]
    }


def test_engram_prompt_block_is_compact_behavior_memory_not_proof():
    block = build_engram_prompt_block([
        {
            "engram_id": "policy_demo",
            "memory_type": "policy_trait",
            "priority": "hard_boundary",
            "trait": "source_trace_caution",
            "rule": "x" * 500,
            "good_behavior": "y" * 500,
        }
    ])
    assert "behavior guidance only" in block
    assert "never cite them as evidence" in block
    assert len(block) < 700


def test_minimal_retry_prompt_excludes_engram_block_and_preserves_citations():
    prompt = _minimal_retry_prompt(
        question="What changed after the raw OCR nomenclature extractor was added?",
        category="pipeline_recovery",
        context_pack=_context_pack(),
        scaffold_answer="The OCR route provides name text.",
    )
    assert "TRACE_NET_ENGINEERING_ENGRAM_MEMORY" not in prompt
    assert "[V6]" in prompt and "[O1]" in prompt
    assert "Return a concise non-empty engineering answer" in prompt


def test_fallback_pipeline_answer_is_non_empty_and_citation_backed():
    answer = _fallback_answer_from_context(
        question="What changed after the raw OCR nomenclature extractor was added?",
        category="pipeline_recovery",
        runner_manifest={"quality_status": "PASS", "summary": {"task_type": "table_extraction_question"}},
        context_pack=_context_pack(),
        scaffold_answer="",
    )
    assert "visual route" in answer.lower()
    assert "ocr nomenclature" in answer.lower()
    result = evaluate_llm_answer(
        answer_text=answer,
        proof_context=_context_pack()["records"][0]["proof_context"],
        min_answer_citations=1,
        min_source_trace_ready_citations=1,
        llm_error="",
        runner_passed=True,
    )
    assert result["llm_answered"] is True
    assert result["grade"] == "GOOD"


def test_fallback_unknown_has_no_unrelated_citations():
    answer = _fallback_answer_from_context(
        question="What does figure 999 show?",
        category="unknown_figure",
        runner_manifest={"quality_status": "FAIL"},
        context_pack={"records": [{"proof_context": []}]},
        scaffold_answer="",
    )
    assert "not source-trace-ready" in answer.lower()
    assert "[V6]" not in answer
