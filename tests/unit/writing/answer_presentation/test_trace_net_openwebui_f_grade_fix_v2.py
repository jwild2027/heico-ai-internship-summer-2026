from __future__ import annotations

from typing import Any, Dict, Mapping

from src.trace_net.writing.trace_net_h30_openwebui_f_grade_fix_v2 import (
    contains_internal_diagnostic,
    install_openwebui_f_grade_fix,
    is_capabilities_question,
    render_capabilities_answer,
    render_table_field_answer,
)


def test_capability_question_detection_positive_and_negative() -> None:
    assert is_capabilities_question(
        "What kinds of questions can you answer using the indexed aircraft manual?"
    )
    assert is_capabilities_question("What are your capabilities?")
    assert not is_capabilities_question(
        "What questions can you answer about part 120-20970-001?"
    )


def test_capability_answer_is_clean_and_useful() -> None:
    answer = render_capabilities_answer()
    assert "## Answer" in answer
    assert "## Evidence" in answer
    assert "## Limits" in answer
    assert "Exact part-number" in answer
    assert "Illustrated-parts-list" in answer
    assert "Helpful follow-up questions" not in answer
    assert "t_p_" not in answer
    assert not contains_internal_diagnostic(answer)


def test_table_exact_proof_fields_are_rendered() -> None:
    result = {
        "citation_registry": [
            {
                "citation_id": 3,
                "authority": "proof",
                "can_prove_claims": True,
                "page_id": "t_p_120_1176_p000084",
                "part_number": "120-41824-003",
                "item_number": "12",
                "nomenclature": "Single Passenger Seat Assembly",
                "quantity": "1",
            }
        ]
    }
    answer = render_table_field_answer(
        "Search the illustrated parts list for part 120-41824-003.",
        result,
    )
    assert "Item: `12` [3]" in answer
    assert "Nomenclature: Single Passenger Seat Assembly [3]" in answer
    assert "Quantity: `1` [3]" in answer
    assert "Page: `t_p_120_1176_p000084` [3]" in answer
    assert "not proven" not in answer.lower()


def test_table_missing_fields_are_explicitly_not_proven() -> None:
    result = {
        "content": "phase4_3_removed_3_direct_row(s)_without_exact_identifier_support",
        "citation_registry": [
            {
                "citation_id": 1,
                "authority": "guidance",
                "page_id": "t_p_120_1176_p000003",
                "part_number": "120-41824-003",
            }
        ],
    }
    answer = render_table_field_answer(
        "Search the illustrated parts list for part 120-41824-003.",
        result,
    )
    assert "No citation-ready IPL row was confirmed" in answer
    assert "Item: not proven" in answer
    assert "Nomenclature: not proven" in answer
    assert "Quantity: not proven" in answer
    assert "Candidate IPL page: `t_p_120_1176_p000003` [1]" in answer
    assert "phase4_3" not in answer
    assert not contains_internal_diagnostic(answer)


def test_table_drops_explicitly_different_identifier_proof() -> None:
    result = {
        "citation_registry": [
            {
                "citation_id": 7,
                "authority": "proof",
                "can_prove_claims": True,
                "page_id": "t_p_120_1176_p000094",
                "part_number": "120-41824-005",
                "item_number": "99",
                "quantity": "4",
            }
        ]
    }
    answer = render_table_field_answer(
        "Search the illustrated parts list for part 120-41824-003.",
        result,
    )
    assert "Item: `99`" not in answer
    assert "Quantity: `4`" not in answer
    assert "Item: not proven" in answer


def test_installer_short_circuits_capabilities_before_current_process() -> None:
    calls = {"process": 0}

    class Runtime:
        def process(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
            calls["process"] += 1
            raise AssertionError("current process must not run for capabilities")

        def health(self) -> Dict[str, Any]:
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": lambda content, query, result: {
            "accepted": True, "quality_status": "PASS", "failures": []
        },
        "extract_latest_user": lambda payload: payload["query"],
    }
    install_openwebui_f_grade_fix(module)
    result = Runtime().process({
        "query": "What kinds of questions can you answer using the indexed aircraft manual?"
    })
    assert calls["process"] == 0
    assert result["route"] == "safe_general_chat"
    assert result["post_answer_validation"]["accepted"] is True
    assert result["openwebui_f_grade_fix"]["gemma_call_avoided"] is True


def test_installer_replaces_broken_table_output() -> None:
    class Runtime:
        def process(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
            return {
                "route": "exact_table_ipl_lookup",
                "content": "phase4_3_removed_3_direct_row(s)_without_exact_identifier_support",
                "citation_registry": [
                    {
                        "citation_id": 1,
                        "authority": "guidance",
                        "page_id": "t_p_120_1176_p000003",
                        "part_number": "120-41824-003",
                    }
                ],
            }

        def health(self) -> Dict[str, Any]:
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": lambda content, query, result: {
            "accepted": True, "quality_status": "PASS", "failures": []
        },
        "extract_latest_user": lambda payload: payload["query"],
    }
    install_openwebui_f_grade_fix(module)
    result = Runtime().process({
        "query": "Search the illustrated parts list for part 120-41824-003."
    })
    assert "phase4_3" not in result["content"]
    assert "Item: not proven" in result["content"]
    assert result["post_answer_validation"]["accepted"] is True
    assert result["openwebui_f_grade_fix"]["applied"] is True
