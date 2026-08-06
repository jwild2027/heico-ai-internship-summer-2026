from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_confidence_stage2_quality import ConfidenceStage2QualityPaths, build_confidence_stage2_quality


def test_stage2_quality_ok(tmp_path: Path) -> None:
    report = {
        "status": "OK",
        "records": 10,
        "scored_records": 10,
        "missing_confidence_records": 0,
        "disagreement_records": 3,
        "per_layer": {"source_trace": {"records": 5}, "part_catalog": {"records": 5}},
    }
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(report), encoding="utf-8")
    paths = ConfidenceStage2QualityPaths(eval_json=eval_path, quality_json=tmp_path / "quality.json")

    quality = build_confidence_stage2_quality(paths, min_records=10, min_layers=2)

    assert quality["status"] == "OK"
    assert quality["summary"]["trace_lc_stage2_records"] == 10


def test_stage2_quality_fails_missing_confidence(tmp_path: Path) -> None:
    report = {
        "status": "OK",
        "records": 10,
        "scored_records": 8,
        "missing_confidence_records": 2,
        "disagreement_records": 1,
        "per_layer": {"source_trace": {"records": 10}},
    }
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(report), encoding="utf-8")
    paths = ConfidenceStage2QualityPaths(eval_json=eval_path, quality_json=tmp_path / "quality.json")

    quality = build_confidence_stage2_quality(paths, min_records=10, max_missing_confidence_records=0)

    assert quality["status"] == "FAIL"
    failed = [c for c in quality["checks"] if not c["ok"]]
    assert any(c["name"] == "all_records_scored" for c in failed)
