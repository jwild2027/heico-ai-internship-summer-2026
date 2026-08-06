from __future__ import annotations

from typing import Any, Dict

from src.trace_net.writing.trace_net_h30_openwebui_f_grade_fix_v2 import (
    _merge_validation,
    install_openwebui_f_grade_fix,
    render_table_field_answer,
)

IPL_QUERY = (
    "Search the illustrated parts list for part 120-41824-003. "
    "Report only source-backed item, nomenclature, quantity, and page fields. "
    "Clearly mark any field that is not proven."
)


def _proof_result() -> Dict[str, Any]:
    return {
        "route": "exact_table_ipl_lookup",
        "content": "legacy malformed answer",
        "citation_registry": [
            {
                "citation_id": 1,
                "authority": "proof",
                "claim_support_allowed": True,
                "page_id": "t_p_120_1176_p000085",
                "part_number": "120-41824-003",
            }
        ],
    }


def _rejecting_validator(content: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "accepted": False,
        "quality_status": "FAIL",
        "failures": ["requested_ipl_fields_not_all_present"],
    }


def test_truthful_partial_ipl_answer_is_accepted_deterministically() -> None:
    class Runtime:
        def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            return _proof_result()

        def health(self) -> Dict[str, Any]:
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": _rejecting_validator,
        "extract_latest_user": lambda payload: payload["query"],
    }
    install_openwebui_f_grade_fix(module)

    result = Runtime().process({"query": IPL_QUERY})
    validation = result["post_answer_validation"]

    assert result["route"] == "exact_table_ipl_lookup"
    assert validation["accepted"] is True
    assert validation["quality_status"] == "PASS"
    assert validation["failures"] == []
    assert validation["acceptance_basis"] == "deterministic_exact_ipl_field_status"
    assert validation["deterministic_exact_ipl_match"] is True

    assert validation["technical_validator_result"]["accepted"] is False
    assert validation["technical_validator_result"]["failures"] == [
        "requested_ipl_fields_not_all_present"
    ]

    content = result["content"]
    assert "Page: `t_p_120_1176_p000085` [1]." in content
    assert "Item: not proven" in content
    assert "Nomenclature: not proven" in content
    assert "Quantity: not proven" in content


def test_tampered_ipl_answer_cannot_use_deterministic_acceptance() -> None:
    result = _proof_result()
    expected = render_table_field_answer(IPL_QUERY, result)
    tampered = expected.replace(
        "t_p_120_1176_p000085",
        "t_p_120_1176_p999999",
    )

    validation = _merge_validation(
        content=tampered,
        query=IPL_QUERY,
        result=result,
        route="exact_table_ipl_lookup",
        validate_answer=_rejecting_validator,
        safe_exact_ipl=True,
    )

    assert validation["accepted"] is False
    assert validation["deterministic_exact_ipl_match"] is False
    assert "deterministic_exact_ipl_field_status_mismatch" in validation["failures"]


def test_missing_public_section_cannot_use_deterministic_acceptance() -> None:
    result = _proof_result()
    expected = render_table_field_answer(IPL_QUERY, result)
    malformed = expected.replace("## Limits", "Limits")

    validation = _merge_validation(
        content=malformed,
        query=IPL_QUERY,
        result=result,
        route="exact_table_ipl_lookup",
        validate_answer=_rejecting_validator,
        safe_exact_ipl=True,
    )

    assert validation["accepted"] is False
    assert validation["deterministic_exact_ipl_match"] is False
    assert (
        "deterministic_exact_ipl_field_status_mismatch"
        in validation["failures"]
    )


def test_health_reports_v22_validation_policy() -> None:
    class Runtime:
        def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            return _proof_result()

        def health(self) -> Dict[str, Any]:
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": _rejecting_validator,
        "extract_latest_user": lambda payload: payload.get("query", ""),
    }
    install_openwebui_f_grade_fix(module)
    health = Runtime().health()

    assert health["exact_ipl_deterministic_validation_acceptance_enabled"] is True
    assert health["exact_ipl_legacy_validator_preserved_for_audit"] is True
    assert health["exact_ipl_validator_can_promote_guidance_to_proof"] is False
