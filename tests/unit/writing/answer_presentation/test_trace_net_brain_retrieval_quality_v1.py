from __future__ import annotations

from typing import Any, Dict

from src.trace_net.writing.trace_net_h30_brain_retrieval_quality_v1 import (
    contains_internal_diagnostic,
    install_brain_retrieval_quality,
    render_ata_description_answer,
    render_guided_part_answer,
    render_nomenclature_answer,
    render_visual_answer,
    sanitize_public_answer,
)

PARTIAL_QUERY = (
    "I only remember that the part number contains 41824. "
    "Show the matching candidates and the source page for each candidate."
)
VISUAL_QUERY = (
    "Show the diagram or figure for part 120-41824-003 "
    "and cite the strongest visual source page."
)


def _entry(
    citation: int,
    *,
    part: str = "",
    page: str = "",
    name: str = "",
    figure: str = "",
    authority: str = "guidance",
    class_name: str = "",
) -> Dict[str, Any]:
    return {
        "citation_id": citation,
        "part_number": part,
        "page_id": page,
        "nomenclature": name,
        "figure": figure,
        "authority": authority,
        "class": class_name,
        "claim_support_allowed": authority == "proof",
    }


def test_partial_renderer_groups_full_format_before_irregular() -> None:
    result = {
        "query_atoms": {
            "identifier_mode": "contains",
            "part_contains": "41824",
        },
        "citation_registry": [
            _entry(1, part="120-41824", page="t_p_120_1176_p000094"),
            _entry(
                2,
                part="120-41824-003",
                page="t_p_120_1176_p000084",
                name="Single Passenger Seat Assembly",
            ),
            _entry(
                3,
                part="120-41824-21",
                page="t_p_120_1176_p000117",
                name="120Cmm251008",
            ),
        ],
    }
    answer = render_guided_part_answer(result, PARTIAL_QUERY)
    assert answer.index("120-41824-003") < answer.index("120-41824-21")
    assert "Strong full-format candidate" in answer
    assert "Irregular or OCR-uncertain match" in answer


def test_nomenclature_renderer_ranks_locking_ring_and_removes_seat_only_noise() -> None:
    query = "Find a locking ring used near the passenger seat and show source-backed candidates."
    result = {
        "query_atoms": {
            "nomenclature_terms": ["locking ring", "ring", "seat"],
        },
        "citation_registry": [
            _entry(
                1,
                part="120-48024-001",
                page="t_p_120_1176_p000055",
                name="Ring Locking",
                authority="proof",
            ),
            _entry(
                2,
                part="120-36833-001",
                page="t_p_120_1176_p000145",
                name="Single Passenger Seat Assembly",
            ),
            _entry(
                3,
                part="120-36058-001",
                page="t_p_120_1176_p000412",
                name="W Seat Oot",
            ),
        ],
    }
    answer = render_nomenclature_answer(result, query)
    assert "120-48024-001" in answer
    assert "120-36833-001" not in answer
    assert "120-36058-001" not in answer
    assert "Ring Locking" in answer


def test_ata_renderer_explains_armrest_match() -> None:
    query = "In ATA 25, find armrest-related parts and cite the strongest indexed source pages."
    result = {
        "query_atoms": {
            "ata_prefix": "25",
            "nomenclature_terms": ["armrest"],
        },
        "citation_registry": [
            _entry(
                1,
                part="120-20970-001",
                page="t_p_120_1176_p000343",
                name="Structure Armrest",
                authority="proof",
            ),
            _entry(
                2,
                part="120-36833-001",
                page="t_p_120_1176_p000145",
                name="Single Passenger Seat Assembly",
            ),
        ],
    }
    answer = render_ata_description_answer(result, query)
    assert "120-20970-001" in answer
    assert "Structure Armrest" in answer
    assert "120-36833-001" not in answer


def test_visual_renderer_is_substantive_and_guidance_limited() -> None:
    result = {
        "query_atoms": {"exact_part_numbers": ["120-41824-003"]},
        "citation_registry": [
            _entry(
                1,
                part="120-41824-003",
                page="t_p_120_1176_p000084",
                name="Single Passenger Seat Assembly",
                authority="proof",
            ),
            _entry(
                5,
                part="120-41824-003",
                page="t_p_120_1176_p000084",
                figure="Figure 2 Sheet 1",
                class_name="visual_guidance",
            ),
        ],
    }
    answer = render_visual_answer(result, VISUAL_QUERY)
    assert "strongest visual lead" in answer.lower()
    assert "Figure 2 Sheet 1" in answer
    assert "t_p_120_1176_p000084" in answer
    assert "visual guidance" in answer
    assert "Directly Supported:" not in answer
    assert not contains_internal_diagnostic(answer)


def test_global_sanitizer_removes_internal_diagnostic() -> None:
    original = (
        "## Answer\n\nDirectly Supported:\n\n"
        "## Evidence\n\n- A candidate figure exists [1].\n\n"
        "## Limits\n\n"
        "- phase4_3_removed_3_direct_row(s)_without_exact_identifier_support"
    )
    cleaned = sanitize_public_answer(original)
    assert "No public technical conclusion was produced." in cleaned
    assert "phase4_3" not in cleaned
    assert not contains_internal_diagnostic(cleaned)


def test_runtime_defensively_overrides_stale_visual_route() -> None:
    class Runtime:
        def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "route": "multi_question_research",
                "content": (
                    "## Answer\n\nDirectly Supported:\n\n"
                    "## Evidence\n\n- candidate\n\n"
                    "## Limits\n\n- phase4_3_removed_3_direct_row"
                ),
                "query_atoms": {"exact_part_numbers": ["120-41824-003"]},
                "citation_registry": [
                    _entry(
                        5,
                        part="120-41824-003",
                        page="t_p_120_1176_p000084",
                        figure="Figure 2 Sheet 1",
                        class_name="visual_guidance",
                    ),
                ],
                "post_answer_validation": {
                    "accepted": True,
                    "quality_status": "PASS",
                    "failures": [],
                },
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
    install_brain_retrieval_quality(module)
    result = Runtime().process({"query": VISUAL_QUERY})
    assert result["route"] == "visual_figure_callout_lookup"
    assert result["post_answer_validation"]["accepted"] is True
    assert result["brain_retrieval_quality"]["route_changed"] is True
    assert "Figure 2 Sheet 1" in result["content"]
    assert "phase4_3" not in result["content"]
