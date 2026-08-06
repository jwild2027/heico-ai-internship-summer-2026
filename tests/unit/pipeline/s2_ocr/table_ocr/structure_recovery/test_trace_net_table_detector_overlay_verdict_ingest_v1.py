import csv
import json
from pathlib import Path

import pytest

from tiff.trace_net_table_detector_overlay_verdict_ingest_v1 import (
    build_verdict_ingest_report,
    normalize_verdict,
)


def make_pack(path: Path):
    payload = {
        "schema_version": "trace_net_table_detector_overlay_review_pack_v1",
        "quality_status": "PASS",
        "review_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "table_type": "parts_list_table",
                "overlay_ready": True,
                "overlay_path": "overlays/one.png",
                "detector_disagreement": True,
                "estimator_exceeds_production": True,
                "production_counts": {"vertical_line_count": 0, "intersection_count": 0},
                "estimator_counts": {"vertical_line_count": 10, "intersection_count": 50},
                "review_flags": ["detector_outputs_disagree_on_same_crop"],
                "recommended_actions": ["open_overlay_png"],
            },
            {
                "page_id": "p2",
                "table_id": "t2",
                "table_type": "index_table",
                "overlay_ready": True,
                "overlay_path": "overlays/two.png",
                "detector_disagreement": True,
                "estimator_exceeds_production": False,
                "production_counts": {"vertical_line_count": 5, "intersection_count": 20},
                "estimator_counts": {"vertical_line_count": 4, "intersection_count": 18},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_default_unreviewed(tmp_path):
    pack = tmp_path / "pack.json"
    make_pack(pack)
    out = tmp_path / "out"
    report = build_verdict_ingest_report(
        pack,
        out,
        thresholds={"min_review_cards": 2, "min_overlay_ready_cards": 2},
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["unreviewed_card_count"] == 2
    assert report["summary"]["crop_selection_blocked_by_verdict_card_count"] == 2
    assert (out / "trace_net_table_detector_overlay_verdict_template_v1.csv").exists()


def test_build_with_csv_verdicts(tmp_path):
    pack = tmp_path / "pack.json"
    make_pack(pack)
    verdicts = tmp_path / "verdicts.csv"
    with verdicts.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["page_id", "table_id", "human_review_verdict", "review_notes"])
        writer.writeheader()
        writer.writerow({"page_id": "p1", "table_id": "t1", "human_review_verdict": "REAL", "review_notes": "looks like real rules"})
        writer.writerow({"page_id": "p2", "table_id": "t2", "human_review_verdict": "NOISE", "review_notes": "text strokes"})
    report = build_verdict_ingest_report(pack, tmp_path / "out", verdicts_path=verdicts)
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["provided_verdict_card_count"] == 2
    assert summary["real_table_rules_verdict_card_count"] == 1
    assert summary["text_or_noise_verdict_card_count"] == 1
    assert summary["crop_selection_allowed_by_verdict_card_count"] == 1
    first = report["review_cards"][0]
    assert first["human_review_verdict"] == "ESTIMATOR_LINES_REAL_TABLE_RULES"
    assert first["safe_for_crop_selection"] is True


def test_invalid_verdict_fails(tmp_path):
    pack = tmp_path / "pack.json"
    make_pack(pack)
    verdicts = tmp_path / "verdicts.jsonl"
    verdicts.write_text('{"page_id":"p1","table_id":"t1","human_review_verdict":"BAD"}\n', encoding="utf-8")
    report = build_verdict_ingest_report(pack, tmp_path / "out", verdicts_path=verdicts)
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["invalid_verdict_row_count"] == 1


def test_normalize_aliases():
    assert normalize_verdict("real") == "ESTIMATOR_LINES_REAL_TABLE_RULES"
    assert normalize_verdict("noise") == "ESTIMATOR_LINES_TEXT_OR_NOISE"
    assert normalize_verdict("mixed") == "MIXED_OR_UNCLEAR"
    with pytest.raises(ValueError):
        normalize_verdict("not-valid")
