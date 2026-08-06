from __future__ import annotations

from src.trace_net.ocr.trace_net_coordinate_evidence_v1 import (
    SAFETY_CONTRACT,
    build_coordinate_lines,
    build_coordinate_words,
    build_page_coordinate_evidence,
    build_table_row_candidates,
    build_visual_callout_candidates,
    normalize_pixel_bbox,
    summarize_coordinate_evidence,
)

TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
)


def _tsv(rows):
    return TSV_HEADER + "\n".join(
        "\t".join(str(value) for value in row)
        for row in rows
    ) + "\n"


def test_normalize_pixel_bbox_rejects_out_of_bounds():
    assert normalize_pixel_bbox(
        {"x0": 10, "y0": 20, "x1": 30, "y1": 40},
        image_width=100,
        image_height=200,
    )["normalized"] == {
        "x0": 0.1,
        "y0": 0.1,
        "x1": 0.3,
        "y1": 0.2,
        "width": 0.2,
        "height": 0.1,
    }
    assert normalize_pixel_bbox(
        {"x0": -1, "y0": 0, "x1": 10, "y1": 10},
        image_width=100,
        image_height=100,
    ) is None


def test_tsv_words_and_lines_keep_coordinates_and_source_trace():
    tsv = _tsv([
        [5, 1, 1, 1, 1, 1, 10, 20, 30, 10, 96, "REMOVE"],
        [5, 1, 1, 1, 1, 2, 45, 20, 40, 10, 92, "PANEL"],
    ])
    words, meta = build_coordinate_words(
        tsv,
        image_width=100,
        image_height=200,
        page_id="p1",
        page_number=1,
        source_member="00000001.tif",
        source_image_sha256="abc",
        psm=3,
        raw_tsv_path="raw.tsv",
    )
    assert len(words) == 2
    assert meta["invalid_coordinate_word_count"] == 0
    assert all(word["within_page_bounds"] for word in words)
    assert all(word["source_image_sha256"] == "abc" for word in words)

    lines, line_meta = build_coordinate_lines(
        words,
        image_width=100,
        image_height=200,
        page_id="p1",
        page_number=1,
        source_member="00000001.tif",
        source_image_sha256="abc",
        psm=3,
    )
    assert line_meta["invalid_coordinate_line_count"] == 0
    assert len(lines) == 1
    assert lines[0]["text"] == "REMOVE PANEL"
    assert len(lines[0]["word_ids"]) == 2


def test_table_rows_are_coordinate_backed_but_not_claim_proof():
    tsv = _tsv([
        [5, 1, 1, 1, 1, 1, 10, 20, 60, 10, 95, "120-42660-001"],
        [5, 1, 1, 1, 1, 2, 180, 20, 60, 10, 94, "BRACKET"],
        [5, 1, 1, 1, 1, 3, 350, 20, 10, 10, 93, "2"],
    ])
    words, _ = build_coordinate_words(
        tsv,
        image_width=500,
        image_height=700,
        page_id="p82",
        page_number=82,
        source_member="00000082.tif",
        source_image_sha256="sha82",
        psm=6,
    )
    lines, _ = build_coordinate_lines(
        words,
        image_width=500,
        image_height=700,
        page_id="p82",
        page_number=82,
        source_member="00000082.tif",
        source_image_sha256="sha82",
        psm=6,
    )
    rows = build_table_row_candidates(
        lines,
        words,
        image_width=500,
        image_height=700,
        page_id="p82",
        page_number=82,
        source_member="00000082.tif",
        source_image_sha256="sha82",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["coordinates_present"] is True
    assert row["cell_count"] == 3
    assert row["row_relationship_usable"] is True
    assert row["proves_item_part_nomenclature_quantity"] is False
    assert row["confirmed"] is False
    assert row["source_truth"] is False


def test_visual_callouts_require_visual_route_bbox_and_psm11_uniqueness():
    primary = [
        {
            "coordinate_word_id": "p3-word",
            "text": "10",
            "bbox": {"x0": 1, "y0": 1, "x1": 5, "y1": 5},
            "normalized_bbox": {"x0": .01, "y0": .01, "x1": .05, "y1": .05},
        }
    ]
    sparse = [
        primary[0],
        {
            "coordinate_word_id": "p11-word-a",
            "text": "A",
            "bbox": {"x0": 20, "y0": 20, "x1": 30, "y1": 30},
            "normalized_bbox": {"x0": .2, "y0": .2, "x1": .3, "y1": .3},
        },
        {
            "coordinate_word_id": "p11-word-part",
            "text": "120-42660-001",
            "bbox": {"x0": 40, "y0": 40, "x1": 90, "y1": 50},
            "normalized_bbox": {"x0": .4, "y0": .4, "x1": .9, "y1": .5},
        },
    ]
    assert build_visual_callout_candidates(
        sparse,
        primary,
        route="normal_text",
        page_id="p",
        page_number=1,
        source_member="x.tif",
        source_image_sha256="sha",
    ) == []

    candidates = build_visual_callout_candidates(
        sparse,
        primary,
        route="image_visual",
        page_id="p",
        page_number=1,
        source_member="x.tif",
        source_image_sha256="sha",
    )
    assert {candidate["candidate_text"] for candidate in candidates} == {
        "A",
        "120-42660-001",
    }
    assert all(candidate["bbox"] for candidate in candidates)
    assert all(candidate["confirmed"] is False for candidate in candidates)
    assert all(candidate["source_truth"] is False for candidate in candidates)


def test_page_builder_preserves_route_and_safety_contract():
    tsv = _tsv([
        [5, 1, 1, 1, 1, 1, 10, 20, 40, 10, 95, "INTRODUCTION"],
    ])
    record = build_page_coordinate_evidence(
        page_id="p23",
        page_number=23,
        source_member="00000023.tif",
        source_image_sha256="sha23",
        image_width=100,
        image_height=200,
        source_manifest_route="normal_text",
        route_tsv_payloads={
            3: {
                "tsv_text": tsv,
                "raw_tsv_path": "page23.tsv",
                "raw_tsv_sha256": "hash",
                "tesseract_status": "ok",
                "tesseract_error": None,
            }
        },
    )
    assert record["source_manifest_route"] == "normal_text"
    assert record["coordinate_processing_route"] == "normal_text"
    assert record["route_preserved"] is True
    assert record["route_mutation_performed"] is False
    assert record["normal_text_block_count"] == 1
    for key, value in SAFETY_CONTRACT.items():
        assert record[key] == value


def test_summary_exposes_progress_and_safety_metrics():
    table_tsv = _tsv([
        [5, 1, 1, 1, 1, 1, 10, 20, 40, 10, 95, "ITEM"],
        [5, 1, 1, 1, 1, 2, 100, 20, 50, 10, 95, "PART"],
    ])
    table = build_page_coordinate_evidence(
        page_id="p24",
        page_number=24,
        source_member="24.tif",
        source_image_sha256="sha24",
        image_width=200,
        image_height=300,
        source_manifest_route="table",
        route_tsv_payloads={6: {"tsv_text": table_tsv}},
    )
    blank = build_page_coordinate_evidence(
        page_id="p2",
        page_number=2,
        source_member="2.tif",
        source_image_sha256="sha2",
        image_width=200,
        image_height=300,
        source_manifest_route="blank_candidate",
        route_tsv_payloads={3: {"tsv_text": TSV_HEADER}},
    )
    summary = summarize_coordinate_evidence([table, blank])
    assert summary["selected_page_count"] == 2
    assert summary["table_page_with_row_candidate_count"] == 1
    assert summary["blank_page_with_word_boxes_count"] == 0
    assert summary["route_mutation_count"] == 0
    assert summary["answer_permission_count"] == 0
