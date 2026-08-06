from __future__ import annotations

from typing import Any, Dict

from scripts.operations.s6_retrieval.serve_trace_net_cognitive_router_v1 import (
    extract_query_atoms,
    plan_route,
)
from src.trace_net.writing.trace_net_h30_openwebui_f_grade_fix_v2 import (
    contains_internal_diagnostic,
    install_openwebui_f_grade_fix,
    is_exact_ipl_field_question,
)

IPL_QUERY = (
    "Search the illustrated parts list for part 120-41824-003. "
    "Report only source-backed item, nomenclature, quantity, and page fields. "
    "Clearly mark any field that is not proven."
)


def test_exact_identifier_plus_ipl_fields_is_one_table_intent() -> None:
    atoms = extract_query_atoms(IPL_QUERY)
    assert atoms.table_requested is True
    assert atoms.exact_part_numbers == ["120-41824-003"]
    assert plan_route(atoms).primary_route == "exact_table_ipl_lookup"


def test_authority_plus_exact_identifier_stays_multi_question() -> None:
    query = "Find part 120-41824-003 and determine whether it is approved"
    assert plan_route(extract_query_atoms(query)).primary_route == "multi_question_research"


def test_ipl_query_detector_rejects_conflicting_task() -> None:
    assert is_exact_ipl_field_question(IPL_QUERY) is True
    assert is_exact_ipl_field_question(
        IPL_QUERY + " Also determine whether it is an approved replacement."
    ) is False


def test_writer_defensively_repairs_stale_multi_question_route() -> None:
    class Runtime:
        def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "route": "multi_question_research",
                "content": (
                    "## Answer\n\n| Requested claim | Status | Best current result | [1].\n\n"
                    "## Evidence\n\n- Evidence status:** Citation-ready source evidence is listed above.\n\n"
                    "## Limits\n\n- phase4_3_removed_3_direct_row(s)_without_exact_identifier_support"
                ),
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
            "accepted": True,
            "quality_status": "PASS",
            "failures": [],
        },
        "extract_latest_user": lambda payload: payload["query"],
    }
    install_openwebui_f_grade_fix(module)
    result = Runtime().process({"query": IPL_QUERY})

    assert result["route"] == "exact_table_ipl_lookup"
    assert result["route_before_openwebui_f_grade_fix"] == "multi_question_research"
    assert result["post_answer_validation"]["accepted"] is True
    assert result["openwebui_f_grade_fix"]["route_changed"] is True
    assert result["openwebui_f_grade_fix"]["dominant_exact_ipl_intent"] is True
    assert "No citation-ready IPL row was confirmed" in result["content"]
    for label in ("Item", "Nomenclature", "Quantity", "Page"):
        assert label in result["content"]
    assert "| Requested claim |" not in result["content"]
    assert "Evidence status:**" not in result["content"]
    assert not contains_internal_diagnostic(result["content"])


def test_health_reports_v21_guards() -> None:
    class Runtime:
        def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"route": "safe_general_chat", "content": ""}

        def health(self) -> Dict[str, Any]:
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": lambda content, query, result: {
            "accepted": True, "quality_status": "PASS", "failures": []
        },
        "extract_latest_user": lambda payload: payload.get("query", ""),
    }
    install_openwebui_f_grade_fix(module)
    health = Runtime().health()
    assert health["exact_ipl_dominant_intent_enabled"] is True
    assert health["exact_ipl_defensive_route_override_enabled"] is True
