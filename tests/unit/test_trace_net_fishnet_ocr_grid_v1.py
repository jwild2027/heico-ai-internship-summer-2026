from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_fishnet_ocr_grid_v1 import (
    DEFAULT_REPORT_NAME,
    build_fishnet_ocr_grid,
    discover_source_pages,
)


def _make_source_zip(tmp_path: Path, page_count: int = 2) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for idx in range(1, page_count + 1):
        image = Image.new("RGB", (240, 320), "white")
        draw = ImageDraw.Draw(image)
        if idx == 1:
            draw.rectangle([20, 40, 220, 260], outline="black", width=3)
            for y in range(80, 260, 40):
                draw.line([20, y, 220, y], fill="black", width=2)
            for x in range(70, 220, 50):
                draw.line([x, 40, x, 260], fill="black", width=2)
            draw.text((30, 55), "120-36833-001", fill="black")
        else:
            draw.text((30, 50), "Plain text manual page", fill="black")
            draw.text((30, 75), "This page has words only.", fill="black")
        image.save(source_dir / f"t_p_120_1176_p{idx:06d}.tif")
    (source_dir / "metadata.xml").write_text("<mets></mets>", encoding="utf-8")
    zip_path = tmp_path / "metadata.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(source_dir / "metadata.xml", "metadata.xml")
        for path in sorted(source_dir.glob("*.tif")):
            zf.write(path, path.name)
    return zip_path


def test_discover_source_pages_from_zip(tmp_path: Path) -> None:
    zip_path = _make_source_zip(tmp_path, page_count=2)
    pages = discover_source_pages(zip_path)
    assert len(pages) == 2
    assert pages[0].page_id == "t_p_120_1176_p000001"
    assert pages[1].page_number == 2
    assert pages[0].package_kind == "zip"


def test_build_fishnet_ocr_grid_writes_safe_artifacts(tmp_path: Path) -> None:
    zip_path = _make_source_zip(tmp_path, page_count=2)
    output_dir = tmp_path / "fishnet_ocr_grid"
    payload = build_fishnet_ocr_grid(
        source_package=zip_path,
        output_dir=output_dir,
        rows=2,
        cols=3,
        ocr_mode="disabled",
        ocr_scope="none",
        write_overlays=True,
        max_overlay_pages=2,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["source_page_count"] == 2
    assert payload["summary"]["page_record_count"] == 2
    assert payload["summary"]["total_cell_count"] == 12
    assert payload["summary"]["unsafe_record_count"] == 0
    assert payload["summary"]["source_truth_mutation_allowed_count"] == 0
    assert payload["records"][0]["cell_count"] == 6
    assert payload["records"][0]["can_answer_directly"] is False
    assert payload["records"][0]["source_truth_mutation_allowed"] is False
    assert (output_dir / DEFAULT_REPORT_NAME).exists()
    assert (output_dir / "trace_net_fishnet_ocr_grid_v1_cards.jsonl").exists()
    assert (output_dir / "trace_net_fishnet_ocr_grid_contact_sheet_v1.png").exists()

    persisted = json.loads((output_dir / DEFAULT_REPORT_NAME).read_text(encoding="utf-8"))
    assert persisted["records"][0]["grid_shape"] == {"rows": 2, "cols": 3}
    assert persisted["records"][0]["safety_contract"]["guidance_only"] is True


def test_build_marks_ocr_failures_as_review_required(tmp_path: Path, monkeypatch) -> None:
    import sys
    import types

    fake = types.SimpleNamespace()

    def _raise_ocr(*args, **kwargs):
        raise RuntimeError("fake missing tesseract binary")

    fake.image_to_string = _raise_ocr
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd="")
    monkeypatch.setitem(sys.modules, "pytesseract", fake)

    zip_path = _make_source_zip(tmp_path, page_count=1)
    output_dir = tmp_path / "fishnet_ocr_grid"
    payload = build_fishnet_ocr_grid(
        source_package=zip_path,
        output_dir=output_dir,
        rows=2,
        cols=2,
        ocr_mode="available",
        ocr_scope="page",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["ocr_failed_page_count"] == 1
    assert payload["summary"]["review_required_count"] == 1
    assert payload["records"][0]["recommended_route_candidate"] == "review_required"
    assert payload["records"][0]["route_confidence"] == 0.0
    assert payload["records"][0]["page_ocr_error"]


def test_build_marks_empty_ocr_as_review_required(tmp_path: Path, monkeypatch) -> None:
    import sys
    import types

    fake = types.SimpleNamespace()

    def _empty_ocr(*args, **kwargs):
        return "   "

    fake.image_to_string = _empty_ocr
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd="")
    monkeypatch.setitem(sys.modules, "pytesseract", fake)

    zip_path = _make_source_zip(tmp_path, page_count=1)
    output_dir = tmp_path / "fishnet_ocr_grid"
    payload = build_fishnet_ocr_grid(
        source_package=zip_path,
        output_dir=output_dir,
        rows=2,
        cols=2,
        ocr_mode="available",
        ocr_scope="page",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["ocr_empty_page_count"] == 1
    assert payload["summary"]["ocr_ok_page_count"] == 0
    assert payload["summary"]["review_required_count"] == 1
    assert payload["records"][0]["ocr_engine_status"] == "empty"
    assert payload["records"][0]["recommended_route_candidate"] == "review_required"
    assert payload["records"][0]["route_confidence"] == 0.0


def test_page_scope_ocr_text_is_not_overrouted_to_image_visual() -> None:
    from tiff.trace_net_fishnet_ocr_grid_v1 import _score_route

    page_features = {
        "grid_rows": 8,
        "grid_cols": 6,
        "ink_ratio": 0.08,
        "ocr_char_count": 1800,
        "ocr_word_count": 260,
        "ocr_line_count": 35,
        "numeric_token_count": 8,
        "part_number_token_count": 0,
        "callout_hint_count": 0,
        "table_keyword_count": 2,
        "visual_keyword_count": 0,
    }
    cells = [
        {"row_index": row, "col_index": col, "ink_ratio": 0.08, "ocr_word_count": 0, "ocr_char_count": 0, "numeric_token_count": 0, "part_number_token_count": 0}
        for row in range(8)
        for col in range(6)
    ]

    route = _score_route(page_features, cells)

    assert route["recommended_route_candidate"] == "normal_text"
    assert route["route_scores"]["normal_text"] > route["route_scores"]["image_visual"]
    assert route["reason_counts"]["page_level_ocr_only"] == 1


def test_page_scope_ocr_part_list_without_word_boxes_is_not_overtrusted() -> None:
    from tiff.trace_net_fishnet_ocr_grid_v1 import _score_route

    page_features = {
        "grid_rows": 8,
        "grid_cols": 6,
        "ink_ratio": 0.07,
        "ocr_char_count": 2300,
        "ocr_word_count": 280,
        "ocr_line_count": 48,
        "numeric_token_count": 58,
        "part_number_token_count": 12,
        "callout_hint_count": 1,
        "table_keyword_count": 14,
        "visual_keyword_count": 0,
    }
    cells = [
        {"row_index": row, "col_index": col, "ink_ratio": 0.06, "ocr_word_count": 0, "ocr_char_count": 0, "numeric_token_count": 0, "part_number_token_count": 0}
        for row in range(8)
        for col in range(6)
    ]

    route = _score_route(page_features, cells)

    assert route["recommended_route_candidate"] in {"normal_text", "review_required"}
    assert route["reason_counts"]["page_level_ocr_only"] == 1
    assert route["reason_counts"]["structural_table_cues"] == 0


def test_spatial_ocr_part_list_can_be_table_candidate() -> None:
    from tiff.trace_net_fishnet_ocr_grid_v1 import _score_route

    page_features = {
        "grid_rows": 8,
        "grid_cols": 6,
        "ink_ratio": 0.07,
        "ocr_char_count": 2300,
        "ocr_word_count": 280,
        "ocr_line_count": 48,
        "numeric_token_count": 120,
        "part_number_token_count": 24,
        "callout_hint_count": 1,
        "table_keyword_count": 20,
        "visual_keyword_count": 0,
        "ocr_word_box_count": 300,
    }
    cells = []
    for row in range(8):
        for col in range(6):
            if 1 <= row <= 6 and col in {1, 2, 3, 4}:
                cells.append({
                    "row_index": row,
                    "col_index": col,
                    "ink_ratio": 0.06,
                    "ocr_word_count": 10,
                    "ocr_char_count": 50,
                    "numeric_token_count": 6,
                    "part_number_token_count": 2,
                    "table_keyword_count": 2,
                })
            else:
                cells.append({
                    "row_index": row,
                    "col_index": col,
                    "ink_ratio": 0.01,
                    "ocr_word_count": 1,
                    "ocr_char_count": 5,
                    "numeric_token_count": 0,
                    "part_number_token_count": 0,
                    "table_keyword_count": 0,
                })

    route = _score_route(page_features, cells)

    assert route["recommended_route_candidate"] == "table"
    assert route["route_scores"]["table"] > route["route_scores"]["image_visual"]
    assert route["reason_counts"]["structural_table_cues"] == 1


def test_page_scope_tsv_word_boxes_populate_cells(tmp_path: Path, monkeypatch) -> None:
    import sys
    import types

    fake = types.SimpleNamespace()

    def _ocr_text(*args, **kwargs):
        return "LEFT WORD RIGHT 120-36833-001"

    def _ocr_data(*args, **kwargs):
        return {
            "text": ["LEFT", "WORD", "RIGHT", "120-36833-001"],
            "left": [10, 40, 150, 160],
            "top": [20, 20, 20, 60],
            "width": [20, 40, 30, 55],
            "height": [10, 10, 10, 10],
            "conf": [90, 88, 91, 85],
        }

    fake.image_to_string = _ocr_text
    fake.image_to_data = _ocr_data
    fake.Output = types.SimpleNamespace(DICT="dict")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd="")
    monkeypatch.setitem(sys.modules, "pytesseract", fake)

    zip_path = _make_source_zip(tmp_path, page_count=1)
    output_dir = tmp_path / "fishnet_ocr_grid"
    payload = build_fishnet_ocr_grid(
        source_package=zip_path,
        output_dir=output_dir,
        rows=2,
        cols=2,
        ocr_mode="available",
        ocr_scope="page",
    )

    record = payload["records"][0]
    assert payload["summary"]["total_ocr_word_box_count"] == 4
    assert payload["summary"]["pages_with_ocr_word_boxes_count"] == 1
    assert record["page_ocr_features"]["ocr_word_box_count"] == 4
    assert record["page_ocr_word_box_status"] == "ok"
    assert any(cell["ocr_word_box_count"] > 0 and cell["ocr_char_count"] > 0 for cell in record["cell_records"])
    assert record["reason_counts"]["page_level_ocr_only"] == 0
