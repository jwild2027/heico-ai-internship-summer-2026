from __future__ import annotations

import json
from pathlib import Path

from scripts.maintenance.visual.refresh_visual_text_extraction_summary import refresh_visual_text_extraction_summary
from tiff.visual_text_extraction import VisualTextPaths


def _record(page_id: str) -> dict[str, object]:
    return {
        "page_id": page_id,
        "status": "ok",
        "provider": "ollama",
        "model": "llava:13b",
        "prompt_version": "visual_text_v2_2",
        "ocr_assist_used": True,
        "page_role": "parts_list",
        "image_classification": "likely_table_or_grid",
        "char_count": 1000,
        "visual_text_plain": "# Page visual text\n\n## Page type\nparts_list\n",
        "visual_text_scores": {
            "prompt_version": "visual_text_v2_2",
            "required_sections_present": True,
            "has_ocr_context_notes": True,
            "metadata_leakage_risk": False,
            "refusal_like": False,
            "too_summary_heavy": False,
        },
    }


def test_refresh_visual_text_summary_uses_jsonl_record_count(tmp_path: Path) -> None:
    out = tmp_path / "visual_text"
    out.mkdir()
    records_path = out / "visual_text_extraction.jsonl"
    records = [_record(f"page_{i:03d}") for i in range(25)]
    records_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    (out / "visual_text_extraction_summary.json").write_text(
        json.dumps({"status": "OK", "records": 10, "selected_pages": 1, "total_page_cards": 509}),
        encoding="utf-8",
    )

    paths = VisualTextPaths(
        page_cards_path=tmp_path / "missing_page_cards.json",
        page_index_path=tmp_path / "missing_page_index.json",
        output_dir=out,
    )
    summary = refresh_visual_text_extraction_summary(paths)

    assert summary["status"] == "OK"
    assert summary["records"] == 25
    assert summary["selected_pages"] == 25
    assert summary["ok_records"] == 25
    assert summary["visual_text_v2_2_records"] == 25
    assert summary["visual_text_required_sections_records"] == 25
    assert summary["visual_text_metadata_leakage_records"] == 0
    assert summary["visual_text_refusal_like_records"] == 0
    assert summary["graph_overlay_nodes"] == 26
    assert summary["graph_overlay_edges"] == 75

    refreshed = json.loads((out / "visual_text_extraction_summary.json").read_text(encoding="utf-8"))
    assert refreshed["records"] == 25
    assert refreshed["refreshed_from_records"] is True
