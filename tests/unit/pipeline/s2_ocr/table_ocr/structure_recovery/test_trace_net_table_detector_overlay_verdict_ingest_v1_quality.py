import json
from pathlib import Path

from tiff.trace_net_table_detector_overlay_verdict_ingest_v1 import build_verdict_ingest_report
from tiff.trace_net_table_detector_overlay_verdict_ingest_v1_quality import build_quality_report


def make_pack(path: Path):
    path.write_text(json.dumps({
        "quality_status": "PASS",
        "review_cards": [{
            "page_id": "p1", "table_id": "t1", "overlay_ready": True,
            "detector_disagreement": True, "production_counts": {}, "estimator_counts": {}
        }]
    }), encoding="utf-8")


def test_quality_pass(tmp_path):
    pack = tmp_path / "pack.json"
    make_pack(pack)
    out = tmp_path / "out"
    report = build_verdict_ingest_report(pack, out, thresholds={"min_review_cards": 1})
    q = build_quality_report(Path(report["paths"]["report_path"]), {"min_review_cards": 1, "min_overlay_ready_cards": 1}, True, True)
    assert q["status"] == "PASS"
    assert q["checks"]["schema_version_ok"] is True


def test_quality_fails_minimum(tmp_path):
    pack = tmp_path / "pack.json"
    make_pack(pack)
    out = tmp_path / "out"
    report = build_verdict_ingest_report(pack, out)
    q = build_quality_report(Path(report["paths"]["report_path"]), {"min_review_cards": 2}, True, True)
    assert q["status"] == "FAIL"
    assert "min_review_cards_met" in q["quality_fail_reasons"]
