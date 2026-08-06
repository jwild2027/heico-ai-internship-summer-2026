import json
from pathlib import Path

from tiff.trace_net_weighted_search_calibration_quality import (
    WeightedSearchCalibrationQualityOptions,
    WeightedSearchCalibrationQualityPaths,
    evaluate_weighted_search_calibration_quality,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_quality_ok_with_component_breakdowns(tmp_path: Path):
    out = tmp_path / "out"
    _write_json(out / "trace_net_weighted_search_calibration_summary.json", {
        "status": "OK",
        "version": "trace_net_weighted_search_calibration_v1",
        "query_fingerprint": "part_number:X",
        "weights_policy_version": "trace_net_weights_policy_v1",
        "records": 2,
        "pages": 2,
        "groups_with_feedback_adjustment": 1,
        "feedback_cap_hit_records": 1,
        "demotion_shortfall_records": 1,
        "unsafe_records": 0,
        "excluded_records": 0,
        "source_truth_mutation_records": 0,
        "context_warning_signals_used": 0,
    })
    rows = [
        {"page_id": "p1", "original_rank": 1, "weighted_rank": 1, "components": {"base_score": 1, "bucket_bonus": 1, "evidence_diversity_bonus": 1, "exact_match_bonus": 1, "confidence_bonus": 1, "feedback_adjustment": 1}},
        {"page_id": "p2", "original_rank": 2, "weighted_rank": 2, "feedback_direction": "demote", "feedback_cap_hit": True, "additional_demotion_to_fall_below_next": 1, "components": {"base_score": 1, "bucket_bonus": 1, "evidence_diversity_bonus": 1, "exact_match_bonus": 1, "confidence_bonus": 1, "feedback_adjustment": -15}},
    ]
    _write_jsonl(out / "trace_net_weighted_search_calibration_records.jsonl", rows)
    result = evaluate_weighted_search_calibration_quality(WeightedSearchCalibrationQualityPaths(output_dir=out), WeightedSearchCalibrationQualityOptions(min_records=2, min_pages=2, min_feedback_adjusted_records=1, min_feedback_cap_hit_records=1, min_demotion_shortfall_records=1, write_json=True))
    assert result["status"] == "OK"
    assert (out / "trace_net_weighted_search_calibration_quality.json").exists()


def test_quality_fails_missing_components(tmp_path: Path):
    out = tmp_path / "out"
    _write_json(out / "trace_net_weighted_search_calibration_summary.json", {
        "status": "OK",
        "version": "trace_net_weighted_search_calibration_v1",
        "weights_policy_version": "trace_net_weights_policy_v1",
        "records": 1,
        "pages": 1,
        "unsafe_records": 0,
        "excluded_records": 0,
        "source_truth_mutation_records": 0,
        "context_warning_signals_used": 0,
    })
    _write_jsonl(out / "trace_net_weighted_search_calibration_records.jsonl", [{"page_id": "p1", "original_rank": 1, "weighted_rank": 1, "components": {"base_score": 1}}])
    result = evaluate_weighted_search_calibration_quality(WeightedSearchCalibrationQualityPaths(output_dir=out), WeightedSearchCalibrationQualityOptions(max_missing_components=0))
    assert result["status"] == "FAIL"
    failed = [c for c in result["checks"] if not c["ok"]]
    assert any(c["name"] == "missing_components" for c in failed)
