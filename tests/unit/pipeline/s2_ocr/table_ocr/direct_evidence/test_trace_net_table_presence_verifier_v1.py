import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_presence_verifier_v1 import (
    build_report,
    compute_ink_metrics,
    make_presence_record,
    normalize_bbox,
    signal_score,
)


def structure_record(**overrides):
    rec = {
        "table_structure_bbox_localizer_id": "struct1",
        "page_id": "t_p_120_1176_p000003",
        "table_id": "table1",
        "structure_selected_table_bbox": {"x0": 100, "y0": 100, "x1": 2100, "y1": 3100, "width": 2000, "height": 3000, "coordinate_system": "pixels"},
        "structure_selected_bbox_source": "conservative_input_bbox_fallback",
        "structure_selected_bbox_ready": True,
        "horizontal_line_run_count": 18,
        "vertical_line_run_count": 15,
        "row_band_run_count": 42,
        "column_band_run_count": 24,
        "review_flags": [],
    }
    rec.update(overrides)
    return rec


def scoped_record(**overrides):
    rec = {
        "scoped_table_record_id": "scope1",
        "page_id": "t_p_120_1176_p000003",
        "table_id": "table1",
        "scoped_row_count": 70,
        "scoped_cell_count": 250,
        "scoped_value_record_count": 250,
        "value_records": [
            {"normalized_text": "PART NUMBER"},
            {"normalized_text": "120-46137-001"},
            {"normalized_text": "NOMENCLATURE"},
        ],
        "bbox_scoped_extraction_ready": True,
    }
    rec.update(overrides)
    return rec


def ocr_record(**overrides):
    rec = {
        "table_ocr_bbox_enrichment_id": "ocr1",
        "page_id": "t_p_120_1176_p000003",
        "table_id": "table1",
        "part_number_ocr_match_count": 2,
        "matched_ocr_bbox_count": 22,
        "text": "part number nomenclature units per assy 120-46137-001",
    }
    rec.update(overrides)
    return rec


def test_presence_confirms_route_table_with_structure_signals():
    record = make_presence_record(
        structure_record(),
        visual=None,
        scoped=scoped_record(),
        ocr=ocr_record(),
        route={"primary_route": "table"},
    )
    assert record["table_presence_label"] == "confirmed_table"
    assert record["table_localization_allowed"] is True
    assert "route_primary_table" in record["positive_table_signals"]
    assert record["answer_permission"] is False


def test_presence_suppresses_non_table_route_even_with_candidate_box():
    record = make_presence_record(
        structure_record(horizontal_line_run_count=0, vertical_line_run_count=0, row_band_run_count=1, column_band_run_count=1, review_flags=["weak_horizontal_table_signal", "weak_vertical_table_signal"]),
        visual=None,
        scoped=scoped_record(scoped_row_count=1, scoped_cell_count=3, scoped_value_record_count=3, value_records=[{"normalized_text": "Chapter 2 Aircraft description"}]),
        ocr=ocr_record(part_number_ocr_match_count=0, matched_ocr_bbox_count=0, text="Chapter 2 Aircraft description figure illustration"),
        route={"primary_route": "image_visual"},
    )
    assert record["table_presence_label"] == "not_table"
    assert record["table_localization_allowed"] is False
    assert record["recommended_route"] == "image_visual"
    assert record["false_positive_table_candidate"] is True


def test_compute_ink_metrics_detects_grid_like_table(tmp_path: Path):
    image_path = tmp_path / "p000003.png"
    img = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(img)
    for x in range(40, 361, 80):
        draw.line((x, 40, x, 360), fill="black", width=2)
    for y in range(40, 361, 40):
        draw.line((40, y, 360, y), fill="black", width=2)
    img.save(image_path)
    metrics = compute_ink_metrics(image_path, {"x0": 30, "y0": 30, "x1": 370, "y1": 370})
    assert metrics["image_available"] is True
    assert metrics["ink_metrics_available"] is True
    assert metrics["ink_horizontal_rule_run_count"] >= 5
    assert metrics["ink_vertical_rule_run_count"] >= 4


def test_signal_score_adds_anti_table_route_negative_signal():
    pos, neg, pos_names, neg_names, rec = signal_score(
        structure_record(horizontal_line_run_count=0, vertical_line_run_count=0, row_band_run_count=0, column_band_run_count=0),
        None,
        scoped_record(scoped_row_count=0, scoped_cell_count=0, scoped_value_record_count=0, value_records=[]),
        ocr_record(part_number_ocr_match_count=0, matched_ocr_bbox_count=0, text="chapter figure aircraft"),
        {"primary_route": "normal_text"},
        {"ink_metrics_available": False},
        "chapter figure aircraft",
    )
    assert neg > pos
    assert "route_primary_normal_text" in neg_names
    assert rec == "normal_text"


def test_build_report_writes_allowed_and_suppressed_outputs(tmp_path: Path):
    structure_payload = {
        "quality_status": "PASS",
        "table_structure_bbox_localizer_records": [
            structure_record(),
            structure_record(page_id="t_p_120_1176_p000004", table_id="table2", horizontal_line_run_count=0, vertical_line_run_count=0, row_band_run_count=1, column_band_run_count=1),
        ],
    }
    scoped_payload = {
        "quality_status": "PASS",
        "scoped_table_records": [
            scoped_record(),
            scoped_record(page_id="t_p_120_1176_p000004", table_id="table2", scoped_row_count=1, scoped_cell_count=3, scoped_value_record_count=3, value_records=[{"normalized_text": "chapter photo"}]),
        ],
    }
    ocr_payload = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            ocr_record(),
            ocr_record(page_id="t_p_120_1176_p000004", table_id="table2", part_number_ocr_match_count=0, matched_ocr_bbox_count=0, text="chapter photo aircraft"),
        ],
    }
    route_payload = {
        "quality_status": "PASS",
        "page_route_records": [
            {"page_id": "t_p_120_1176_p000003", "primary_route": "table"},
            {"page_id": "t_p_120_1176_p000004", "primary_route": "image_visual"},
        ],
    }
    paths = {}
    for name, payload in [("structure", structure_payload), ("scoped", scoped_payload), ("ocr", ocr_payload), ("route", route_payload)]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    report = build_report(
        table_structure_bbox_localizer_path=paths["structure"],
        table_bbox_scoped_cell_extraction_path=paths["scoped"],
        table_ocr_bbox_enrichment_path=paths["ocr"],
        page_route_manifest_path=paths["route"],
        output_dir=tmp_path / "out",
        thresholds={
            "min_source_structure_records": 2,
            "min_presence_records": 2,
            "min_presence_decisions": 2,
            "min_localization_allowed_records": 1,
            "min_suppressed_candidates": 1,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_structure_bbox_localizer_quality_pass": True,
            "require_table_bbox_scoped_cell_extraction_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_all_records_have_presence_decision": True,
        },
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["confirmed_table_record_count"] == 1
    assert report["summary"]["not_table_record_count"] == 1
    assert report["summary"]["table_localization_suppressed_record_count"] == 1
    assert (tmp_path / "out" / "trace_net_table_presence_verifier_v1_allowed_table_records.jsonl").exists()
    assert (tmp_path / "out" / "trace_net_table_presence_verifier_v1_suppressed_candidates.jsonl").exists()


def test_build_report_parses_current_page_route_manifest_cards(tmp_path: Path):
    structure_payload = {
        "quality_status": "PASS",
        "table_structure_bbox_localizer_records": [
            structure_record(page_id="t_p_120_1176_p000003", table_id="table1"),
            structure_record(page_id="t_p_120_1176_p000004", table_id="table2", horizontal_line_run_count=0, vertical_line_run_count=0, row_band_run_count=1, column_band_run_count=1),
        ],
    }
    scoped_payload = {
        "quality_status": "PASS",
        "scoped_table_records": [
            scoped_record(page_id="t_p_120_1176_p000003", table_id="table1"),
            scoped_record(page_id="t_p_120_1176_p000004", table_id="table2", scoped_row_count=1, scoped_cell_count=3, scoped_value_record_count=3, value_records=[{"normalized_text": "chapter photo"}]),
        ],
    }
    ocr_payload = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            ocr_record(page_id="t_p_120_1176_p000003", table_id="table1"),
            ocr_record(page_id="t_p_120_1176_p000004", table_id="table2", part_number_ocr_match_count=0, matched_ocr_bbox_count=0, text="chapter photo aircraft"),
        ],
    }
    # This mirrors the current TRACE-Net manifest shape from local artifacts:
    # top-level page_route_cards, not page_route_records.
    route_payload = {
        "quality_status": "PASS",
        "page_route_cards": [
            {"page_id": "t_p_120_1176_p000003", "primary_route": "table"},
            {"page_id": "t_p_120_1176_p000004", "primary_route": "image_visual"},
        ],
    }
    paths = {}
    for name, payload in [("structure", structure_payload), ("scoped", scoped_payload), ("ocr", ocr_payload), ("route", route_payload)]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    report = build_report(
        table_structure_bbox_localizer_path=paths["structure"],
        table_bbox_scoped_cell_extraction_path=paths["scoped"],
        table_ocr_bbox_enrichment_path=paths["ocr"],
        page_route_manifest_path=paths["route"],
        output_dir=tmp_path / "out_current_route_shape",
        thresholds={
            "min_source_structure_records": 2,
            "min_presence_records": 2,
            "min_presence_decisions": 2,
            "min_localization_allowed_records": 1,
            "min_suppressed_candidates": 1,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_structure_bbox_localizer_quality_pass": True,
            "require_table_bbox_scoped_cell_extraction_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_all_records_have_presence_decision": True,
        },
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["route_manifest_page_count"] == 2
    assert report["summary"]["confirmed_table_record_count"] == 1
    assert report["summary"]["not_table_record_count"] == 1
    assert report["summary"]["non_table_route_suppressed_count"] == 1


def test_route_table_with_incomplete_visual_candidate_demotes_to_weak_table():
    record = make_presence_record(
        structure_record(
            structure_selected_bbox_source="conservative_input_bbox_fallback",
            structure_visual_candidate_rejected=True,
            visual_to_input_width_ratio=0.34,
            visual_to_input_height_ratio=0.99,
            visual_to_input_area_ratio=0.34,
            review_flags=[
                "visual_candidate_cuts_table_columns",
                "visual_candidate_low_input_x_overlap",
                "input_bbox_broad_page_coverage",
            ],
        ),
        visual=None,
        scoped=scoped_record(scoped_row_count=75, scoped_cell_count=250, scoped_value_record_count=250),
        ocr=ocr_record(matched_ocr_bbox_count=25),
        route={"primary_route": "table"},
    )
    assert record["route_primary"] == "table"
    assert record["table_route_challenged"] is True
    assert record["table_presence_label"] == "weak_table"
    assert record["table_localization_allowed"] is True
    assert record["full_table_enclosure_recommended"] is True
    assert record["recommended_downstream_action"] == "allow_table_workflow_but_reconstruct_full_table_enclosure"
    assert "route_primary_table_challenged_by_structure_qa" in record["review_flags"]
    assert record["answer_permission"] is False
