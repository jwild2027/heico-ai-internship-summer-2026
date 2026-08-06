from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_v2_summary_smoke_tester_v1 import (
    build_v2_summary_smoke_test,
    check_v2_summary_smoke_report,
    validate_v2_card,
    validate_v2_prompt,
)


def test_validate_v2_card_blocks_answer_permission() -> None:
    card = {
        "page_id": "t_p_120_1176_p000048",
        "role": "table",
        "subrole": "parts_list",
        "confidence": "medium",
        "short_summary": "A page with table-like retrieval guidance.",
        "retrieval_summary": "Use as retrieval guidance only.",
        "answerable_questions": ["What page is relevant?"],
        "retrieval_cues": ["parts list"],
        "important_entities": [],
        "component_families": [],
        "source_grounding": {
            "has_ocr": True,
            "source_url_present": True,
            "supporting_ocr_phrases": ["PARTS LIST"],
        },
        "not_good_for": ["proving source truth without checking the source page"],
        "authority": {
            "trust_scope": "page_context_summary",
            "can_answer_directly": True,
            "canonical_source_truth": False,
            "requires_source_check": True,
        },
        "prompt_version": "page_context_v2_query_guidance_card",
    }

    validation = validate_v2_card(card)

    assert validation["quality_status"] == "FAIL"
    assert "v2_summary_grants_answer_permission" in validation["failure_reasons"]


def test_validate_prompt_requires_existing_schema_terms() -> None:
    prompt = """
    Return JSON with short_summary, retrieval_summary, answerable_questions,
    retrieval_cues, important_entities, source_grounding, not_good_for,
    authority, and OCR grounding.
    """
    result = validate_v2_prompt(prompt)

    assert result["quality_status"] == "PASS"
    assert result["prompt_contains_json_schema"] is False


def test_build_smoke_from_context_file_uses_existing_v2_guide(tmp_path: Path) -> None:
    context_file = tmp_path / "page_contexts.json"
    context_file.write_text(
        json.dumps(
            {
                "t_p_120_1176_p000048": {
                    "page_id": "t_p_120_1176_p000048",
                    "role": "table",
                    "summary": "Illustrated parts list page for passenger seat components.",
                    "text": "FIGURE 1 PASSENGER SEAT PARTS LIST ARMREST BACKREST 120-36833-001",
                    "source_url": "file:///sample/00000048.tif",
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_v2_summary_smoke_test(
        context_file=context_file,
        output_dir=tmp_path / "out",
        max_pages=1,
        min_prompt_smoke_cards=1,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["prompt_smoke_card_count"] == 1
    assert Path(report["output_paths"]["json"]).exists()
    assert Path(report["output_paths"]["markdown"]).exists()


def test_check_quality_passes_report(tmp_path: Path) -> None:
    context_file = tmp_path / "page_contexts.json"
    context_file.write_text(
        json.dumps(
            [
                {
                    "page_id": "t_p_120_1176_p000202",
                    "role": "figure",
                    "summary": "Figure page for passenger seat backrest area.",
                    "ocr_text": "FIGURE 2 BACKREST CALLOUT ITEM 10",
                    "source_url": "file:///sample/00000202.tif",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = build_v2_summary_smoke_test(
        context_file=context_file,
        output_dir=tmp_path / "out",
        max_pages=1,
        min_prompt_smoke_cards=1,
    )
    quality = check_v2_summary_smoke_report(
        report=report["output_paths"]["json"],
        output=tmp_path / "quality.json",
        require_quality_pass=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        min_prompt_smoke_cards=1,
    )

    assert quality["quality_status"] == "PASS"
    assert Path(tmp_path / "quality.json").exists()
