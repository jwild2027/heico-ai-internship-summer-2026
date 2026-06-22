import json
from pathlib import Path

from tiff.trace_net_table_full_enclosure_bbox_reconstructor_v1 import (
    build_report,
    normalize_bbox,
    reconstruct_record,
    union_bboxes,
)


def test_union_bboxes_adds_padding_and_encloses_inputs():
    a = {"x0": 10, "y0": 20, "x1": 110, "y1": 220, "coordinate_system": "pixels"}
    b = {"x0": 40, "y0": 50, "x1": 140, "y1": 260, "coordinate_system": "pixels"}
    out = union_bboxes([a, b], padding_ratio=0.01)
    assert out is not None
    assert out["x0"] <= 10
    assert out["y0"] <= 20
    assert out["x1"] >= 140
    assert out["y1"] >= 260
    assert out["width"] > 130
    assert out["height"] > 240


def test_reconstruct_record_uses_full_enclosure_when_recommended():
    structure = {
        "page_id": "p1",
        "table_id": "t1",
        "input_bbox": {"x0": 100, "y0": 100, "x1": 500, "y1": 800, "coordinate_system": "pixels"},
        "visual_candidate_bbox": {"x0": 200, "y0": 200, "x1": 300, "y1": 400, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 100, "y0": 100, "x1": 500, "y1": 800, "coordinate_system": "pixels"},
        "review_flags": ["visual_candidate_cuts_table_columns"],
    }
    presence = {
        "table_presence_verifier_id": "pv1",
        "page_id": "p1",
        "table_id": "t1",
        "table_presence_label": "weak_table",
        "table_localization_allowed": True,
        "full_table_enclosure_recommended": True,
        "table_route_challenged": True,
        "review_flags": ["full_table_enclosure_reconstruction_recommended"],
    }
    rec = reconstruct_record(structure, presence, "table_id", padding_ratio=0.01)
    assert rec["final_table_bbox_source"] in {"full_table_enclosure_reconstructed", "full_table_boundary_reconstructed"}
    assert rec["boundary_expanded_x"] is True
    assert rec["row_cell_extraction_scope"] == "full_table_enclosure_bbox_crop"
    assert rec["full_table_enclosure_bbox_ready"] is True
    assert rec["full_table_enclosure_bbox"]["x0"] <= 100
    assert rec["full_table_enclosure_bbox"]["x1"] >= 500
    assert "full_table_enclosure_reconstructed" in rec["review_flags"]
    assert rec["answer_permission"] is False
    assert rec["source_truth_mutation_allowed"] is False


def test_split_column_boundary_expands_toward_full_table_enclosure():
    structure = {
        "page_id": "p_split",
        "table_id": "t_split",
        "input_bbox": {"x0": 200, "y0": 100, "x1": 1200, "y1": 1800, "coordinate_system": "pixels"},
        "visual_candidate_bbox": {"x0": 220, "y0": 180, "x1": 650, "y1": 900, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 200, "y0": 100, "x1": 1200, "y1": 1800, "coordinate_system": "pixels"},
        "multi_column_vertical_merge_applied": True,
        "review_flags": ["split_column_table_geometry_merged", "visual_candidate_cuts_table_columns", "visual_candidate_cuts_table_rows"],
    }
    presence = {
        "page_id": "p_split",
        "table_id": "t_split",
        "table_presence_label": "weak_table",
        "table_localization_allowed": True,
        "full_table_enclosure_recommended": True,
        "table_route_challenged": True,
        "table_route_challenge_issues": ["visual_candidate_width_under_table_extent", "visual_candidate_height_under_table_extent"],
    }
    rec = reconstruct_record(structure, presence, "table_id", padding_ratio=0.01)
    assert rec["final_table_bbox_source"] == "full_table_boundary_reconstructed"
    assert rec["split_column_boundary_reconstructed"] is True
    assert rec["boundary_expanded_x"] is True
    assert rec["boundary_expanded_y"] is True
    assert rec["final_table_bbox"]["x1"] > 1200
    assert rec["final_table_bbox"]["y1"] > 1800
    assert "split_column_full_table_boundary_reconstructed" in rec["review_flags"]


def test_image_visual_presence_marks_bbox_review_only_not_ready():
    structure = {
        "page_id": "p_img",
        "table_id": "t_img",
        "input_bbox": {"x0": 0, "y0": 0, "x1": 1000, "y1": 1000, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 0, "y0": 0, "x1": 1000, "y1": 1000, "coordinate_system": "pixels"},
    }
    presence = {
        "page_id": "p_img",
        "table_id": "t_img",
        "table_presence_label": "not_table",
        "table_localization_allowed": True,
        "recommended_route": "image_visual",
        "recommended_downstream_action": "review_or_route_to_image_visual",
        "full_table_enclosure_recommended": True,
        "review_flags": ["diagram_like_image_region"],
    }
    rec = reconstruct_record(structure, presence, "table_id", padding_ratio=0.01)
    assert rec["table_bbox_review_only"] is True
    assert rec["full_table_enclosure_bbox_ready"] is False
    assert rec["recommended_downstream_action"] == "review_or_route_to_image_visual_before_table_extraction"
    assert "table_bbox_review_only_image_or_non_table" in rec["review_flags"]


def test_build_report_writes_outputs_and_quality_pass(tmp_path: Path):
    structure_payload = {
        "quality_status": "PASS",
        "table_structure_bbox_localizer_records": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "input_bbox": {"x0": 0, "y0": 0, "x1": 1000, "y1": 1000, "coordinate_system": "pixels"},
                "structure_selected_table_bbox": {"x0": 0, "y0": 0, "x1": 1000, "y1": 1000, "coordinate_system": "pixels"},
                "visual_candidate_bbox": {"x0": 200, "y0": 200, "x1": 500, "y1": 500, "coordinate_system": "pixels"},
                "review_flags": ["visual_candidate_cuts_table_columns"],
            },
            {
                "page_id": "p2",
                "table_id": "t2",
                "input_bbox": {"x0": 10, "y0": 10, "x1": 600, "y1": 700, "coordinate_system": "pixels"},
                "structure_selected_table_bbox": {"x0": 20, "y0": 20, "x1": 590, "y1": 690, "coordinate_system": "pixels"},
                "visual_candidate_bbox": {"x0": 20, "y0": 20, "x1": 590, "y1": 690, "coordinate_system": "pixels"},
                "review_flags": [],
            },
        ],
    }
    presence_payload = {
        "quality_status": "PASS",
        "table_presence_verifier_records": [
            {"page_id": "p1", "table_id": "t1", "table_presence_label": "weak_table", "table_localization_allowed": True, "full_table_enclosure_recommended": True, "table_route_challenged": True},
            {"page_id": "p2", "table_id": "t2", "table_presence_label": "confirmed_table", "table_localization_allowed": True, "full_table_enclosure_recommended": False, "table_route_challenged": False},
        ],
    }
    sp = tmp_path / "structure.json"
    pp = tmp_path / "presence.json"
    sp.write_text(json.dumps(structure_payload), encoding="utf-8")
    pp.write_text(json.dumps(presence_payload), encoding="utf-8")

    report = build_report(
        table_structure_bbox_localizer_path=sp,
        table_presence_verifier_path=pp,
        output_dir=tmp_path / "out",
        thresholds={
            "min_source_structure_records": 2,
            "min_source_presence_records": 2,
            "min_reconstructor_records": 2,
            "min_final_bbox_ready_records": 2,
            "min_full_enclosure_reconstructed_records": 1,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_structure_bbox_localizer_quality_pass": True,
            "require_table_presence_verifier_quality_pass": True,
            "require_all_final_bboxes_ready": True,
            "require_all_recommended_reconstructed": True,
        },
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["full_enclosure_reconstructor_record_count"] == 2
    assert summary["full_table_enclosure_reconstructed_record_count"] == 1
    assert summary["structure_selected_passthrough_record_count"] == 1
    assert (tmp_path / "out" / "trace_net_table_full_enclosure_bbox_reconstructor_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_table_full_enclosure_bbox_reconstructor_v1_reconstructed_records.jsonl").exists()


def test_bounded_full_enclosure_caps_over_expansion_to_content_band():
    structure = {
        "page_id": "p_bound",
        "table_id": "t_bound",
        "input_bbox": {"x0": 100, "y0": 100, "x1": 1100, "y1": 2100, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 100, "y0": 100, "x1": 1100, "y1": 2100, "coordinate_system": "pixels"},
        "visual_candidate_bbox": {"x0": 350, "y0": 350, "x1": 600, "y1": 700, "coordinate_system": "pixels"},
        "review_flags": [
            "visual_candidate_cuts_table_columns",
            "visual_candidate_cuts_table_rows",
            "visual_candidate_over_tightened_area",
        ],
    }
    presence = {
        "page_id": "p_bound",
        "table_id": "t_bound",
        "table_presence_label": "weak_table",
        "table_localization_allowed": True,
        "full_table_enclosure_recommended": True,
        "table_route_challenged": True,
        "table_route_challenge_issues": ["visual_candidate_area_under_table_extent"],
    }
    rec = reconstruct_record(structure, presence, "table_id", padding_ratio=0.012)
    assert rec["final_table_bbox_source"] == "full_table_boundary_reconstructed"
    assert rec["bounded_table_content_band_applied"] is True
    assert rec["selected_to_input_width_ratio"] <= 1.13
    assert rec["selected_to_input_height_ratio"] <= 1.11
    assert rec["full_table_enclosure_bbox"]["x0"] <= 100
    assert rec["full_table_enclosure_bbox"]["x1"] >= 1100


def test_weak_unrefined_diagram_like_record_is_review_only():
    structure = {
        "page_id": "p_diagram_like",
        "table_id": "t_diagram_like",
        "input_bbox": {"x0": 100, "y0": 100, "x1": 2100, "y1": 2600, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 100, "y0": 100, "x1": 2100, "y1": 2600, "coordinate_system": "pixels"},
        "review_flags": [
            "visual_candidate_not_refined",
            "visual_candidate_quality_not_pass",
            "visual_refinement_not_applied",
            "visual_candidate_weak_row_structure",
            "visual_candidate_weak_column_structure",
            "localized_bbox_still_broad",
        ],
    }
    presence = {
        "page_id": "p_diagram_like",
        "table_id": "t_diagram_like",
        "table_presence_label": "weak_table",
        "table_localization_allowed": True,
        "full_table_enclosure_recommended": True,
        "review_flags": ["weak_row_structure_flag", "weak_column_structure_flag", "weak_horizontal_table_signal", "weak_vertical_table_signal"],
    }
    rec = reconstruct_record(structure, presence, "table_id", padding_ratio=0.012)
    assert rec["table_bbox_review_only"] is True
    assert rec["full_table_enclosure_bbox_ready"] is False
    assert rec["recommended_downstream_action"] == "review_or_route_to_image_visual_before_table_extraction"


def test_force_full_page_bbox_uses_record_dimensions_for_ready_table():
    structure = {
        "page_id": "p_full",
        "table_id": "t_full",
        "image_width": 3300,
        "image_height": 4400,
        "input_bbox": {"x0": 100, "y0": 200, "x1": 1000, "y1": 2000, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 100, "y0": 200, "x1": 1000, "y1": 2000, "coordinate_system": "pixels"},
    }
    presence = {
        "page_id": "p_full",
        "table_id": "t_full",
        "table_presence_label": "weak_table",
        "table_localization_allowed": True,
        "full_table_enclosure_recommended": True,
    }
    rec = reconstruct_record(
        structure,
        presence,
        "table_id",
        padding_ratio=0.012,
        force_final_bbox_full_page=True,
    )
    assert rec["final_table_bbox_source"] == "full_page_table_bbox"
    assert rec["full_page_bbox_applied"] is True
    assert rec["full_table_enclosure_bbox_ready"] is True
    assert rec["final_table_bbox"] == {
        "x0": 0.0,
        "y0": 0.0,
        "x1": 3300.0,
        "y1": 4400.0,
        "width": 3300.0,
        "height": 4400.0,
        "coordinate_system": "pixels",
    }
    assert rec["row_cell_extraction_scope"] == "full_table_enclosure_bbox_crop"
    assert "full_page_bbox_for_step0_table_extraction" in rec["review_flags"]


def test_force_full_page_bbox_does_not_make_review_only_record_ready():
    structure = {
        "page_id": "p_img_full",
        "table_id": "t_img_full",
        "image_width": 3300,
        "image_height": 4400,
        "input_bbox": {"x0": 100, "y0": 200, "x1": 1000, "y1": 2000, "coordinate_system": "pixels"},
        "structure_selected_table_bbox": {"x0": 100, "y0": 200, "x1": 1000, "y1": 2000, "coordinate_system": "pixels"},
    }
    presence = {
        "page_id": "p_img_full",
        "table_id": "t_img_full",
        "table_presence_label": "not_table",
        "table_localization_allowed": True,
        "recommended_route": "image_visual",
        "full_table_enclosure_recommended": True,
        "review_flags": ["diagram_like_image_region"],
    }
    rec = reconstruct_record(
        structure,
        presence,
        "table_id",
        padding_ratio=0.012,
        force_final_bbox_full_page=True,
    )
    assert rec["full_page_bbox_applied"] is False
    assert rec["final_table_bbox_source"] == "review_only_image_or_non_table_bbox_preserved"
    assert rec["table_bbox_review_only"] is True
    assert rec["full_table_enclosure_bbox_ready"] is False
