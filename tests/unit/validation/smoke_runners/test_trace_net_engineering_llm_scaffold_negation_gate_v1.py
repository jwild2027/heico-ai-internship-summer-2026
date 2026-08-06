from tiff.trace_net_engineering_llm_answer_smoke_v1 import (
    build_llm_prompt,
    count_unsupported_claims,
    _build_trace_net_scaffold_answer,
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
                        "line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY .......... VS4956 A REF",
                        "source_trace_ready": True,
                    },
                ],
                "guidance_context": [],
                "answer_constraints": {"summary_guidance_policy": "summaries are guidance only"},
            }
        ]
    }


def test_negated_replacement_approval_is_not_unsupported():
    answer = (
        "Not proven. There is no information in the provided documentation to confirm "
        "that 120-50645-005 is an approved replacement for 120-50645-011. "
        "The context does not provide evidence regarding replacement approval."
    )
    assert count_unsupported_claims(answer) == 0


def test_positive_replacement_approval_is_unsupported():
    answer = "120-50645-005 is an approved replacement for 120-50645-011."
    assert count_unsupported_claims(answer) >= 1


def test_positive_interchangeability_is_unsupported_but_not_proven_is_safe():
    assert count_unsupported_claims("120-50645-005 is interchangeable with 120-50645-011.") >= 1
    assert count_unsupported_claims("Not proven. The evidence does not prove the parts are interchangeable.") == 0


def test_scaffold_for_troubleshooting_mentions_visual_and_ocr_roles():
    scaffold = _build_trace_net_scaffold_answer(
        question="Why was nomenclature missing from the visual route evidence?",
        category="troubleshooting",
        runner_manifest={"answer_text": "runner answer"},
        context_pack=_context_pack(),
    )
    assert "visual route" in scaffold.lower()
    assert "OCR" in scaffold or "ocr" in scaffold
    assert "[V6]" in scaffold
    assert "[O1]" in scaffold


def test_prompt_includes_category_rules_and_scaffold():
    prompt = build_llm_prompt(
        question="What changed after the raw OCR nomenclature extractor was added?",
        category="pipeline_recovery",
        runner_manifest={"summary": {"task_type": "troubleshooting_question"}},
        context_pack=_context_pack(),
        scaffold_answer="Answer scaffold: OCR-backed nomenclature became available [O1].",
    )
    assert "QUESTION_CATEGORY: pipeline_recovery" in prompt
    assert "INTENT_RULE:" in prompt
    assert "STRUCTURED_TRACE_NET_SCAFFOLD" in prompt
    assert "Never return an empty answer" in prompt
