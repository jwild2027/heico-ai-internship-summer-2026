import json
from pathlib import Path

from tiff.trace_net_table_detector_overlay_review_pack_v1 import build_review_pack_report, Thresholds


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_review_pack_without_contact_sheets(tmp_path: Path):
    overlay_dir = tmp_path / "overlays"
    overlay_dir.mkdir()
    overlay = overlay_dir / "card.png"
    overlay.write_bytes(b"not-a-real-png-but-exists")
    audit = {
        "schema_version": "trace_net_table_detector_overlay_audit_v1",
        "quality_status": "PASS",
        "audit_cards": [
            {
                "page_id": "page1",
                "table_id": "table1",
                "table_type": "parts_list_table",
                "overlay_ready": True,
                "overlay_path": str(overlay),
                "detector_disagreement": True,
                "estimator_exceeds_production": True,
                "production_exceeds_estimator": False,
                "production_best_candidate": {
                    "production_horizontal_line_count": 4,
                    "production_vertical_line_count": 0,
                    "production_intersection_count": 0,
                    "production_signal": "WEAK_LINE_SIGNAL",
                    "production_score": 4.0,
                },
                "estimator_best_candidate": {
                    "estimator_horizontal_line_count": 8,
                    "estimator_vertical_line_count": 47,
                    "estimator_intersection_count": 258,
                    "estimator_signal": "GRID",
                    "estimator_score": 2692.0,
                },
            }
        ],
    }
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, audit)

    report = build_review_pack_report(
        overlay_audit_path=audit_path,
        output_dir=tmp_path / "out",
        repo_root=tmp_path,
        write_contact_sheets=False,
        thresholds=Thresholds(min_review_cards=1, min_overlay_ready_cards=1, require_overlay_audit_quality_pass=True, require_no_answer_permission=True),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["review_card_count"] == 1
    assert report["summary"]["overlay_ready_card_count"] == 1
    card = report["review_cards"][0]
    assert card["human_review_verdict"] == "UNREVIEWED"
    assert card["can_answer_directly"] is False
    assert "verify_estimator_lines_are_table_rules_not_text_strokes" in card["recommended_actions"]


def test_missing_overlay_is_review_flagged(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, {
        "quality_status": "PASS",
        "audit_cards": [{"page_id": "p", "table_id": "t", "overlay_ready": True, "overlay_path": "missing.png"}],
    })
    report = build_review_pack_report(
        overlay_audit_path=audit_path,
        output_dir=tmp_path / "out",
        repo_root=tmp_path,
        write_contact_sheets=False,
        thresholds=Thresholds(min_review_cards=1, min_overlay_ready_cards=0),
    )
    card = report["review_cards"][0]
    assert card["overlay_ready"] is False
    assert "overlay_missing_or_unreadable" in card["review_flags"]
