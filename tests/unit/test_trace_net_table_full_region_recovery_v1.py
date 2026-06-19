import json
from pathlib import Path

from tiff.trace_net_table_full_region_recovery_v1 import build_report, parse_bbox, BBox


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_bbox_width_height():
    bbox = parse_bbox({"x0": 1, "y0": 2, "width": 10, "height": 20}, "unit")
    assert bbox is not None
    assert bbox.x1 == 11
    assert bbox.y1 == 22


def test_build_report_recovers_full_region(tmp_path):
    bbox = {
        "quality_status": "PASS",
        "table_bbox_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "table_type": "parts_list_table",
                "table_region_bbox": {"x0": 100, "y0": 100, "x1": 400, "y1": 400, "page_width": 1000, "page_height": 1000},
            }
        ],
    }
    ocr = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "content_band_bbox": {"x0": 80, "y0": 80, "x1": 500, "y1": 600},
                "matched_ocr_bbox_count": 12,
                "part_number_ocr_match_count": 3,
            }
        ],
    }
    overlay = {
        "quality_status": "PASS",
        "audit_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "detector_disagreement": True,
                "estimator_best_candidate": {"expanded_bbox": {"x0": 90, "y0": 70, "x1": 520, "y1": 650}},
            }
        ],
    }
    bpath = tmp_path / "bbox.json"
    opath = tmp_path / "ocr.json"
    apath = tmp_path / "audit.json"
    write_json(bpath, bbox)
    write_json(opath, ocr)
    write_json(apath, overlay)
    report = build_report(
        table_bbox_resolver_path=bpath,
        table_ocr_bbox_enrichment_path=opath,
        table_detector_overlay_audit_path=apath,
        output_dir=tmp_path / "out",
        thresholds={
            "min_recovery_cards": 1,
            "min_expanded_full_table_bbox_cards": 1,
            "min_ocr_content_bbox_cards": 1,
            "max_unsafe_recovery_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_bbox_resolver_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    card = report["recovery_cards"][0]
    assert card["expanded_full_table_bbox"]
    assert card["ocr_content_bbox"]
    assert card["part_number_coverage_ok"] is True
    assert card["answer_permission"] is False
    assert card["source_truth_mutation_allowed"] is False


def test_build_report_fails_threshold_when_no_ocr(tmp_path):
    bbox = {"quality_status": "PASS", "table_bbox_cards": [{"page_id": "p1", "table_id": "t1", "table_region_bbox": {"x0": 1, "y0": 1, "x1": 20, "y1": 20}}]}
    ocr = {"quality_status": "PASS", "table_ocr_bbox_enrichment_cards": []}
    bpath = tmp_path / "bbox.json"
    opath = tmp_path / "ocr.json"
    write_json(bpath, bbox)
    write_json(opath, ocr)
    report = build_report(
        table_bbox_resolver_path=bpath,
        table_ocr_bbox_enrichment_path=opath,
        output_dir=tmp_path / "out",
        thresholds={"min_recovery_cards": 1, "min_ocr_content_bbox_cards": 1},
    )
    assert report["quality_status"] == "FAIL"
