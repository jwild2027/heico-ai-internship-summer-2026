import json
from pathlib import Path

from tiff.trace_net_table_detector_overlay_audit_v1 import build_report


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_overlay_audit_json_only(tmp_path):
    parity = {
        "quality_status": "PASS",
        "parity_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "table_type": "parts_list_table",
                "selected_morphology_scope": "page",
                "bbox_source": "explicit_table_bbox",
                "detector_disagreement": True,
                "estimator_exceeds_production": True,
                "production_best_candidate": {
                    "production_vertical_line_count": 0,
                    "production_intersection_count": 0,
                    "production_signal": "WEAK_LINE_SIGNAL",
                    "expanded_bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                },
                "estimator_best_candidate": {
                    "estimator_vertical_line_count": 5,
                    "estimator_intersection_count": 12,
                    "estimator_signal": "GRID",
                    "expanded_bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                },
                "best_vertical_delta_estimator_minus_production": 5,
                "best_intersection_delta_estimator_minus_production": 12,
                "best_signal_rank_delta_estimator_minus_production": 2,
            }
        ],
    }
    bbox = {
        "quality_status": "PASS",
        "table_bbox_cards": [{"page_id": "p1", "table_id": "t1", "resolved_image_path": "missing.tif"}],
    }
    parity_path = tmp_path / "parity.json"
    bbox_path = tmp_path / "bbox.json"
    write_json(parity_path, parity)
    write_json(bbox_path, bbox)

    report = build_report(
        margin_detector_parity_path=parity_path,
        table_bbox_resolver_path=bbox_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        make_overlays=False,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["audit_card_count"] == 1
    assert report["summary"]["detector_disagreement_card_count"] == 1
    assert report["audit_cards"][0]["answer_permission"] is False
    assert (tmp_path / "out" / "trace_net_table_detector_overlay_audit_v1.json").exists()


def test_overlay_audit_safety_contract(tmp_path):
    parity_path = tmp_path / "parity.json"
    bbox_path = tmp_path / "bbox.json"
    write_json(parity_path, {"quality_status": "PASS", "parity_cards": []})
    write_json(bbox_path, {"quality_status": "PASS", "table_bbox_cards": []})
    report = build_report(
        margin_detector_parity_path=parity_path,
        table_bbox_resolver_path=bbox_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        make_overlays=False,
    )
    assert report["safety_contract"]["no_postgres_writes"] is True
    assert report["safety_contract"]["no_answer_permission"] is True
