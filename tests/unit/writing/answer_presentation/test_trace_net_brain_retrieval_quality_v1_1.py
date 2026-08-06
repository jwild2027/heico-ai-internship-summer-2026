from __future__ import annotations

from scripts.benchmark.run_trace_net_brain_retrieval_quality_canary_v1 import (
    ata_description_outcome,
)
from src.trace_net.writing.trace_net_h30_brain_retrieval_quality_v1 import (
    render_ata_description_answer,
    render_nomenclature_answer,
    render_visual_answer,
)


def test_grouped_split_locking_ring_nomenclature_is_reconstructed() -> None:
    query = (
        "Find a locking ring used near the passenger seat and show "
        "source-backed candidates."
    )
    result = {
        "query_atoms": {"nomenclature_terms": ["locking ring", "ring", "seat"]},
        "citation_registry": [
            {
                "citation_id": 1,
                "part_number": "120-48024-001",
                "page_id": "t_p_120_1176_p000055",
                "field_name": "RING",
                "authority": "proof",
                "claim_support_allowed": True,
            },
            {
                "citation_id": 1,
                "part_number": "120-48024-001",
                "page_id": "t_p_120_1176_p000055",
                "field_value": "LOCKING",
                "authority": "proof",
                "claim_support_allowed": True,
            },
            {
                "citation_id": 2,
                "part_number": "120-36833-001",
                "page_id": "t_p_120_1176_p000145",
                "nomenclature": "Single Passenger Seat Assembly",
            },
        ],
    }
    answer = render_nomenclature_answer(result, query)
    assert "120-48024-001" in answer
    assert "Ring Locking" in answer
    assert "120-36833-001" not in answer


def test_grouped_split_structure_armrest_is_reconstructed() -> None:
    query = (
        "In ATA 25, find armrest-related parts and cite the strongest "
        "indexed source pages."
    )
    result = {
        "query_atoms": {
            "ata_prefix": "25",
            "nomenclature_terms": ["armrest"],
        },
        "citation_registry": [
            {
                "citation_id": 1,
                "part_number": "120-20970-001",
                "page_id": "t_p_120_1176_p000343",
                "field_name": "STRUCTURE",
                "authority": "proof",
                "claim_support_allowed": True,
            },
            {
                "citation_id": 1,
                "part_number": "120-20970-001",
                "page_id": "t_p_120_1176_p000343",
                "field_value": "ARMREST",
                "authority": "proof",
                "claim_support_allowed": True,
            },
        ],
    }
    answer = render_ata_description_answer(result, query)
    assert "120-20970-001" in answer
    assert "Structure Armrest" in answer


def test_split_figure_number_and_sheet_are_reconstructed() -> None:
    query = (
        "Show the diagram or figure for part 120-41824-003 and cite "
        "the strongest visual source page."
    )
    result = {
        "query_atoms": {"exact_part_numbers": ["120-41824-003"]},
        "citation_registry": [
            {
                "citation_id": 4,
                "part_number": "120-41824-003",
                "page_id": "t_p_120_1176_p000084",
                "figure_number": "2",
                "sheet_number": "1",
                "class": "visual_guidance",
            },
        ],
    }
    answer = render_visual_answer(result, query)
    assert "Figure 2 Sheet 1" in answer
    assert "t_p_120_1176_p000084" in answer


def test_ata_canary_accepts_truthful_safe_limited_answer() -> None:
    answer = """## Answer

The ATA search returned source-location leads, but none had a citation-ready nomenclature matching armrest.

## Evidence

- Source-location lead: `120-20970-001` — page `t_p_120_1176_p000343` [1]

## Limits

- ATA and source-location agreement does not by itself prove a technical relationship.
"""
    assert ata_description_outcome(answer) == "safe_limited"


def test_ata_canary_still_rejects_unexplained_generic_result() -> None:
    answer = """## Answer

The ATA search returned some pages.

## Evidence

- Page `t_p_120_1176_p000343` [1]
"""
    assert ata_description_outcome(answer) == "missing"
