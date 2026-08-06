from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_extraction import (
    ExtractionOptions,
    MockVisualTextClient,
    VisualTextPaths,
    build_visual_text_prompt,
    load_page_cards,
    normalize_visual_text_markdown,
    parse_visual_text_sections,
    run_visual_text_extraction,
    score_visual_text_markdown,
)
from tiff.visual_text_extraction_quality import (
    VisualTextQualityPaths,
    build_visual_text_extraction_quality,
)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_v2_fixture(tmp_path: Path) -> VisualTextPaths:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"mock image")
    ocr_path = tmp_path / "page.txt"
    ocr_path.write_text(
        "PASSENGER SEAT PARTS LIST ITEM PART NUMBER NOMENCLATURE QTY "
        "1 120-12345-001 BRACKET 2",
        encoding="utf-8",
    )
    cards_path = tmp_path / "page_character_cards.json"
    page_index_path = tmp_path / "page_index.json"
    output_dir = tmp_path / "visual_text"
    _write_json(
        cards_path,
        {
            "page_cards": [
                {
                    "page_id": "p001",
                    "parents": {"document_label": "T.P. 120/1176", "ata_code": "25-21-00"},
                    "context": {"page_role": "table", "summary": "Parts list table."},
                    "signals": {"image_classification": "likely_table_or_grid"},
                    "source": {"tiff_path": str(image_path), "ocr_path": str(ocr_path)},
                    "parts": [{"part_number": "120-12345-001", "nomenclature": "BRACKET"}],
                }
            ]
        },
    )
    _write_json(page_index_path, {"pages": []})
    return VisualTextPaths(page_cards_path=cards_path, page_index_path=page_index_path, output_dir=output_dir)


def test_v2_prompt_includes_ocr_assist_and_strict_rules(tmp_path: Path) -> None:
    paths = _make_v2_fixture(tmp_path)
    card = load_page_cards(paths.page_cards_path, paths.page_index_path)[0]
    prompt = build_visual_text_prompt(
        card,
        prompt_version="visual_text_v2",
        ocr_assist_text="OCR says ITEM PART NUMBER NOMENCLATURE QTY 120-12345-001 BRACKET",
    )

    lowered = prompt.lower()
    assert "strict visual text extraction" in lowered
    assert "transcribe first, summarize second" in lowered
    assert "unreadable" in lowered and "instead of guessing" in lowered
    assert "ocr assist start" in lowered
    assert "120-12345-001" in prompt
    assert "## Transcribed visible text" in prompt
    assert "## Model caution" in prompt


def test_v2_normalizer_and_scores_add_consistent_sections() -> None:
    partial = """# Page visual text
## Page type
parts_list

## Visual summary
A dense table appears to list part 120-12345-001.

## Tables
| item | part |
|---|---|
| 1 | 120-12345-001 |
"""
    normalized = normalize_visual_text_markdown(partial, prompt_version="visual_text_v2")
    sections = parse_visual_text_sections(normalized)
    scores = score_visual_text_markdown(normalized)

    assert set(sections) >= {"Page type", "Visible title/header", "Transcribed visible text", "Tables", "Model caution"}
    assert scores["required_sections_present"] is True
    assert scores["has_table_rows"] is True
    assert scores["has_part_numbers"] is True
    assert scores["visible_part_number_count"] >= 1


def test_v2_run_records_ocr_assist_scores_and_quality_requirement(tmp_path: Path) -> None:
    paths = _make_v2_fixture(tmp_path)
    result = run_visual_text_extraction(
        paths,
        ExtractionOptions(
            provider="mock",
            max_pages=1,
            overwrite=True,
            prompt_version="visual_text_v2",
            ocr_assist=True,
            ocr_max_chars=500,
        ),
        client=MockVisualTextClient(),
    )
    record = result.records[0]

    assert result.status == "OK"
    assert result.summary["prompt_version"] == "visual_text_v2"
    assert result.summary["ocr_assist_enabled"] is True
    assert result.summary["visual_text_v2_records"] == 1
    assert result.summary["visual_text_required_sections_records"] == 1
    assert record["prompt_version"] == "visual_text_v2"
    assert record["ocr_assist_used"] is True
    assert "PASSENGER SEAT PARTS LIST" in record["ocr_assist_preview"]
    assert record["visual_text_scores"]["required_sections_present"] is True

    quality = build_visual_text_extraction_quality(
        VisualTextQualityPaths(output_dir=paths.output_dir),
        allow_planned=False,
        require_v2=True,
        min_required_section_records=1,
        max_summary_heavy_records=0,
    )
    assert quality["status"] == "OK"
    assert quality["summary"]["visual_text_v2_records"] == 1
