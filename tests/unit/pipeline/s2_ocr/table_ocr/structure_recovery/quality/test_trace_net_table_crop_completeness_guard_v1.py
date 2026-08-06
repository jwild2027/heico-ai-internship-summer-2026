import json
from pathlib import Path

from tiff.trace_net_table_crop_completeness_guard_v1 import build_report


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_completeness_guard_blocks_unreviewed_detector_disagreement(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "table_type": "parts_list_table",
                "selected_morphology_scope": "page",
                "table_region_crop_available": True,
                "table_region_crop_applied": True,
                "horizontal_line_count": 2,
                "vertical_line_count": 0,
                "intersection_count": 0,
                "morphology_signal_strength": "WEAK_LINE_SIGNAL",
                "row_record_count": 10,
                "cell_record_count": 50,
            }
        ],
    }
    bbox = {
        "quality_status": "PASS",
        "table_bbox_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "table_type": "parts_list_table",
                "bbox_source": "explicit_table_bbox",
                "bbox_coverage_ratio": 0.5,
                "table_region_bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100, "width": 200, "height": 200},
            }
        ],
    }
    review = {
        "quality_status": "PASS",
        "review_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "human_review_verdict": "UNREVIEWED",
                "detector_disagreement": True,
                "estimator_exceeds_production": True,
                "overlay_path": "overlay.png",
            }
        ],
    }
    tlg_path = tmp_path / "tlg.json"
    bbox_path = tmp_path / "bbox.json"
    review_path = tmp_path / "review.json"
    write_json(tlg_path, tlg)
    write_json(bbox_path, bbox)
    write_json(review_path, review)

    report = build_report(
        table_line_geometry_path=tlg_path,
        table_bbox_resolver_path=bbox_path,
        overlay_review_pack_path=review_path,
        output_dir=tmp_path / "out",
        thresholds={
            "min_completeness_cards": 1,
            "max_unsafe_completeness_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_overlay_review_pack_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )

    assert report["quality_status"] == "PASS"
    card = report["crop_completeness_cards"][0]
    assert card["crop_selection_allowed"] is False
    assert "detector_disagreement_without_human_verdict" in card["review_flags"]
    assert card["answer_permission"] is False
    assert (tmp_path / "out" / "trace_net_table_crop_completeness_guard_v1.json").exists()


def test_safe_review_verdict_can_pass_when_grid_present(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {
                "page_id": "p2",
                "table_id": "t2",
                "table_type": "index_table",
                "selected_morphology_scope": "page",
                "table_region_crop_available": True,
                "table_region_crop_applied": True,
                "horizontal_line_count": 8,
                "vertical_line_count": 6,
                "intersection_count": 20,
                "morphology_signal_strength": "GRID",
            }
        ],
    }
    bbox = {
        "quality_status": "PASS",
        "table_bbox_cards": [
            {
                "page_id": "p2",
                "table_id": "t2",
                "bbox_source": "explicit_table_bbox",
                "bbox_coverage_ratio": 0.7,
                "table_region_bbox": {"x0": 10, "y0": 10, "x1": 190, "y1": 190, "width": 200, "height": 200},
            }
        ],
    }
    review = {
        "quality_status": "PASS",
        "review_cards": [
            {
                "page_id": "p2",
                "table_id": "t2",
                "human_review_verdict": "ESTIMATOR_LINES_REAL_TABLE_RULES",
                "detector_disagreement": True,
                "estimator_exceeds_production": True,
            }
        ],
    }
    paths = []
    for name, payload in [("tlg", tlg), ("bbox", bbox), ("review", review)]:
        path = tmp_path / f"{name}.json"
        write_json(path, payload)
        paths.append(path)
    report = build_report(
        table_line_geometry_path=paths[0],
        table_bbox_resolver_path=paths[1],
        overlay_review_pack_path=paths[2],
        output_dir=tmp_path / "out",
        thresholds={"min_completeness_cards": 1},
    )
    assert report["summary"]["crop_completeness_pass_card_count"] == 1
    assert report["crop_completeness_cards"][0]["crop_selection_allowed"] is True


def test_full_region_recovery_ready_can_unblock_grid_candidate_when_enabled(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {
                "page_id": "p3",
                "table_id": "t3",
                "table_type": "index_table",
                "selected_morphology_scope": "page",
                "table_region_crop_available": True,
                "table_region_crop_applied": True,
                "table_full_region_recovery_used_for_crop": True,
                "horizontal_line_count": 30,
                "vertical_line_count": 10,
                "intersection_count": 180,
                "morphology_signal_strength": "GRID",
                "table_region_crop_comparison": {
                    "crop_vertical_line_gain": 0,
                    "crop_intersection_gain": 45,
                },
            }
        ],
    }
    bbox = {
        "quality_status": "PASS",
        "table_bbox_cards": [
            {
                "page_id": "p3",
                "table_id": "t3",
                "bbox_source": "table_full_region_recovery",
                "bbox_coverage_ratio": 0.7,
                "table_region_bbox": {"x0": 10, "y0": 10, "x1": 180, "y1": 180, "width": 200, "height": 200},
            }
        ],
    }
    review = {
        "quality_status": "PASS",
        "review_cards": [
            {
                "page_id": "p3",
                "table_id": "t3",
                "human_review_verdict": "UNREVIEWED",
                "detector_disagreement": True,
                "estimator_exceeds_production": True,
            }
        ],
    }
    full_region = {
        "quality_status": "PASS",
        "recovery_cards": [
            {
                "page_id": "p3",
                "table_id": "t3",
                "table_type": "index_table",
                "crop_recovery_status": "FULL_TABLE_REGION_RECOVERY_READY",
                "crop_recovery_ready": True,
                "full_table_coverage_ratio": 0.91,
                "expanded_full_table_bbox": {"x0": 10, "y0": 10, "x1": 180, "y1": 180},
            }
        ],
    }
    paths = []
    for name, payload in [("tlg", tlg), ("bbox", bbox), ("review", review), ("full_region", full_region)]:
        path = tmp_path / f"{name}.json"
        write_json(path, payload)
        paths.append(path)

    report = build_report(
        table_line_geometry_path=paths[0],
        table_bbox_resolver_path=paths[1],
        overlay_review_pack_path=paths[2],
        table_full_region_recovery_path=paths[3],
        output_dir=tmp_path / "out",
        thresholds={
            "min_completeness_cards": 1,
            "allow_full_region_recovery_ready_selection": True,
            "max_full_region_coverage_ratio": 0.95,
            "require_table_full_region_recovery_quality_pass": True,
        },
    )

    assert report["quality_status"] == "PASS"
    card = report["crop_completeness_cards"][0]
    assert card["crop_selection_allowed"] is True
    assert card["crop_completeness_status"] == "PASS_FULL_REGION_RECOVERY_READY"
    assert card["full_region_recovery_gate_allowed"] is True
    assert report["summary"]["full_region_recovery_gate_allowed_card_count"] == 1


def test_full_region_recovery_too_page_like_remains_blocked(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {
                "page_id": "p4",
                "table_id": "t4",
                "table_type": "parts_list_table",
                "selected_morphology_scope": "page",
                "table_region_crop_available": True,
                "table_region_crop_applied": True,
                "table_full_region_recovery_used_for_crop": True,
                "horizontal_line_count": 30,
                "vertical_line_count": 10,
                "intersection_count": 180,
                "morphology_signal_strength": "GRID",
                "table_region_crop_comparison": {"crop_intersection_gain": 45},
            }
        ],
    }
    bbox = {
        "quality_status": "PASS",
        "table_bbox_cards": [{"page_id": "p4", "table_id": "t4", "table_region_bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100, "width": 100, "height": 100}}],
    }
    review = {"quality_status": "PASS", "review_cards": [{"page_id": "p4", "table_id": "t4", "human_review_verdict": "UNREVIEWED", "detector_disagreement": True}]}
    full_region = {"quality_status": "PASS", "recovery_cards": [{"page_id": "p4", "table_id": "t4", "crop_recovery_ready": True, "full_table_coverage_ratio": 0.97}]}
    paths = []
    for name, payload in [("tlg", tlg), ("bbox", bbox), ("review", review), ("full_region", full_region)]:
        path = tmp_path / f"{name}.json"
        write_json(path, payload)
        paths.append(path)

    report = build_report(
        table_line_geometry_path=paths[0],
        table_bbox_resolver_path=paths[1],
        overlay_review_pack_path=paths[2],
        table_full_region_recovery_path=paths[3],
        output_dir=tmp_path / "out",
        thresholds={"allow_full_region_recovery_ready_selection": True, "max_full_region_coverage_ratio": 0.95},
    )
    card = report["crop_completeness_cards"][0]
    assert card["crop_selection_allowed"] is False
    assert "full_region_recovery_too_page_like" in card["full_region_recovery_gate_reasons"]
