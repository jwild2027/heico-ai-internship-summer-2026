from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_cleanup import (
    VisualTextCleanupPaths,
    build_visual_text_clean_quality,
    run_visual_text_cleanup,
)


def _write_record(path: Path, markdown: str) -> None:
    record = {
        "page_id": "t_p_120_1176_p000001",
        "status": "ok",
        "provider": "ollama",
        "model": "llava:13b",
        "page_role": "figure",
        "image_classification": "likely_figure_or_diagram",
        "prompt_version": "visual_text_v2_2",
        "visual_text_markdown": markdown,
        "visual_text_scores": {},
        "char_count": len(markdown),
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _good_markdown() -> str:
    return """
# Page visual text

## Page type
figure

## Visible title/header
Passenger Seat

## Transcribed visible text
SEAT BOTTOM; SEAT BACKRESTS

## Visual summary
A technical figure shows a passenger seat with labeled seat bottom and backrests.

## OCR/context assist notes
No OCR/context-only notes reported.

## Tables
No readable table detected.

## Figures/diagrams
A passenger seat diagram is visible with labels for seat bottom and backrests.

## Charts/graphs
No readable chart or graph detected.

## Labels/callouts/part numbers
- SEAT BOTTOM
- SEAT BACKRESTS

## Warnings/notes
No visible warnings, cautions, notes, revision notes, or procedural notes detected.

## Uncertain/unreadable
No uncertain or unreadable visual regions reported.

## Model caution
Use this visual extraction as derived context. Verify critical facts against source TIFF/OCR evidence.
"""


def test_clean_quality_passes_for_good_record(tmp_path: Path) -> None:
    output_dir = tmp_path / "visual_text"
    output_dir.mkdir()
    _write_record(output_dir / "visual_text_extraction.jsonl", _good_markdown())
    paths = VisualTextCleanupPaths(output_dir=output_dir)
    run_visual_text_cleanup(paths)

    report = build_visual_text_clean_quality(
        paths,
        min_records=1,
        min_usable_for_rag_records=1,
        max_prompt_template_leakage_records=0,
        max_section_bleed_records=0,
        max_metadata_leakage_records=0,
        max_refusal_like_records=0,
        max_trust_d_records=0,
    )

    assert report["status"] == "OK"


def test_clean_quality_passes_after_repairing_prompt_template_leakage(tmp_path: Path) -> None:
    output_dir = tmp_path / "visual_text"
    output_dir.mkdir()
    bad = _good_markdown().replace(
        "- SEAT BOTTOM\n- SEAT BACKRESTS",
        "bullet list of exact visible labels, callouts, item numbers, part numbers, quantities, references. If none visible, say so.",
    )
    _write_record(output_dir / "visual_text_extraction.jsonl", bad)
    paths = VisualTextCleanupPaths(output_dir=output_dir)
    run_visual_text_cleanup(paths)

    report = build_visual_text_clean_quality(paths, max_prompt_template_leakage_records=0, max_trust_d_records=0)

    assert report["status"] == "OK"
    assert report["summary"]["prompt_template_leakage_records"] == 0
    assert report["summary"]["prompt_template_repaired_records"] == 1
