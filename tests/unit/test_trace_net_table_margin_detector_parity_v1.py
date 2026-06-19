from pathlib import Path

from PIL import Image, ImageDraw

from tiff import trace_net_table_margin_detector_parity_v1 as mod


def make_grid_image(path: Path) -> None:
    img = Image.new("L", (120, 120), 255)
    draw = ImageDraw.Draw(img)
    for y in (20, 50, 80):
        draw.line((10, y, 110, y), fill=0, width=2)
    for x in (20, 60, 100):
        draw.line((x, 10, x, 110), fill=0, width=2)
    img.save(path)


def test_estimator_detects_grid(tmp_path: Path):
    image_path = tmp_path / "grid.png"
    make_grid_image(image_path)
    result = mod.estimator_morphology_from_crop(image_path, {"x0": 0, "y0": 0, "x1": 120, "y1": 120})
    assert result["status"] == "IMAGE_ANALYSIS_OK"
    assert result["vertical_line_count"] >= 2
    assert result["intersection_count"] >= 4
    assert result["morphology_signal_strength"] == "GRID"


def test_build_report_flags_detector_disagreement(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "grid.png"
    make_grid_image(image_path)
    line_payload = {
        "quality_status": "PASS",
        "table_geometry_cards": [{
            "page_id": "p1",
            "table_id": "t1",
            "table_type": "parts_list_table",
            "resolved_image_path": str(image_path),
            "selected_morphology_scope": "page",
            "table_region_bbox": {"x0": 0, "y0": 0, "x1": 120, "y1": 120},
        }],
    }
    bbox_payload = {
        "quality_status": "PASS",
        "table_bbox_cards": [{
            "page_id": "p1",
            "table_id": "t1",
            "bbox_source": "explicit_table_bbox",
            "table_region_bbox": {"x0": 0, "y0": 0, "x1": 120, "y1": 120},
        }],
    }
    line_path = tmp_path / "line.json"
    bbox_path = tmp_path / "bbox.json"
    mod.write_json(line_path, line_payload)
    mod.write_json(bbox_path, bbox_payload)

    def fake_production(_image_path, _bbox):
        return {
            "status": "IMAGE_ANALYSIS_OK",
            "horizontal_line_count": 1,
            "vertical_line_count": 0,
            "intersection_count": 0,
            "morphology_signal_strength": "WEAK_LINE_SIGNAL",
            "morphology_quality_score": 1.0,
        }

    monkeypatch.setattr(mod, "production_morphology_from_crop", fake_production)
    report = mod.build_report(
        table_line_geometry_path=line_path,
        table_bbox_resolver_path=bbox_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        margin_pixels=[0],
        thresholds=mod.Thresholds(
            min_parity_cards=1,
            min_margin_candidate_evaluations=1,
            min_successful_image_cards=1,
            min_detector_disagreement_cards=1,
            require_table_line_geometry_quality_pass=True,
            require_table_bbox_resolver_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["parity_card_count"] == 1
    assert summary["detector_disagreement_card_count"] == 1
    assert summary["estimator_exceeds_production_card_count"] == 1
    card = report["parity_cards"][0]
    assert "production_and_experiment_detectors_disagree" in card["detector_parity_findings"]
