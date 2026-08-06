import json
from pathlib import Path

from tiff.trace_net_weighted_search_calibration import (
    WeightedSearchCalibrationOptions,
    WeightedSearchCalibrationPaths,
    build_weighted_search_calibration,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_calibration_explains_feedback_margin(tmp_path: Path):
    out = tmp_path / "out"
    weighted = tmp_path / "weighted"
    weights = tmp_path / "weights"
    _write_json(weighted / "trace_net_weighted_search_simulation_summary.json", {
        "status": "OK",
        "query_fingerprint": "part_number:120-50645-009",
        "weights_policy_version": "trace_net_weights_policy_v1",
        "feedback_enabled": True,
        "matching_feedback_signal_records": 2,
        "feedback_signals_used": 2,
        "groups_with_feedback_adjustment": 2,
        "rank_changed_records": 0,
        "unsafe_weighted_records": 0,
        "excluded_weighted_records": 0,
        "source_truth_mutation_records": 0,
        "context_warning_signals_used": 0,
        "top_page_before": "p1",
        "top_page_after": "p1",
    })
    _write_json(weights / "trace_net_weights_policy.json", {
        "version": "trace_net_weights_policy_v1",
        "feedback_ranking": {"cap_min": -15.0, "cap_max": 15.0},
    })
    rows = [
        {
            "page_id": "p1",
            "original_rank": 1,
            "weighted_rank": 1,
            "rank_changed": False,
            "weighted_score": 100.0,
            "group_score": 60.0,
            "best_score": 60.0,
            "rag_buckets": ["verified_part_evidence", "source_text_evidence", "derived_context"],
            "evidence_layers": ["part_catalog", "source_text", "table_tile_text_refined"],
            "supporting_results": [{"x": 1}],
            "weighted_score_components": {
                "base_score": 60.0,
                "bucket_bonus": 16.0,
                "evidence_diversity_bonus": 8.0,
                "exact_match_bonus": 20.0,
                "confidence_bonus": 2.0,
                "feedback_adjustment": 6.0,
                "feedback_signals_used": [{"signal_id": "s1"}],
                "context_warning_signals_used": 0,
            },
        },
        {
            "page_id": "p2",
            "original_rank": 2,
            "weighted_rank": 2,
            "rank_changed": False,
            "weighted_score": 79.0,
            "group_score": 58.0,
            "best_score": 58.0,
            "rag_buckets": ["verified_part_evidence", "source_text_evidence"],
            "evidence_layers": ["part_catalog", "source_text"],
            "supporting_results": [{"x": 1}],
            "weighted_score_components": {
                "base_score": 58.0,
                "bucket_bonus": 13.0,
                "evidence_diversity_bonus": 4.0,
                "exact_match_bonus": 20.0,
                "confidence_bonus": 2.0,
                "feedback_adjustment": -15.0,
                "feedback_signals_used": [{"signal_id": "s2"}],
                "context_warning_signals_used": 0,
            },
        },
        {
            "page_id": "p3",
            "original_rank": 3,
            "weighted_rank": 3,
            "rank_changed": False,
            "weighted_score": 75.5,
            "group_score": 50.0,
            "best_score": 50.0,
            "rag_buckets": ["source_text_evidence"],
            "evidence_layers": ["source_text"],
            "supporting_results": [{"x": 1}],
            "weighted_score_components": {
                "base_score": 50.0,
                "bucket_bonus": 5.0,
                "evidence_diversity_bonus": 0.0,
                "exact_match_bonus": 20.0,
                "confidence_bonus": 0.5,
                "feedback_adjustment": 0.0,
                "feedback_signals_used": [],
                "context_warning_signals_used": 0,
            },
        },
    ]
    _write_jsonl(weighted / "trace_net_weighted_search_simulation_results.jsonl", rows)
    paths = WeightedSearchCalibrationPaths(weighted_search_dir=weighted, weights_dir=weights, output_dir=out)
    result = build_weighted_search_calibration(paths, WeightedSearchCalibrationOptions())
    assert result["status"] == "OK"
    summary = result["summary"]
    assert summary["feedback_cap_hit_records"] == 1
    assert summary["demotion_shortfall_records"] == 1
    assert summary["evidence_diversity_overrode_feedback_records"] == 1
    p2 = [r for r in result["records"] if r["page_id"] == "p2"][0]
    assert p2["additional_demotion_to_fall_below_next"] > 3.49
    assert p2["feedback_cap_hit"] is True
    assert paths.report_html.exists()
    assert paths.graph_nodes.exists()


def test_calibration_fails_if_unsafe_present(tmp_path: Path):
    out = tmp_path / "out"
    weighted = tmp_path / "weighted"
    weights = tmp_path / "weights"
    _write_json(weighted / "trace_net_weighted_search_simulation_summary.json", {
        "status": "OK",
        "query_fingerprint": "query:test",
        "weights_policy_version": "trace_net_weights_policy_v1",
        "unsafe_weighted_records": 1,
    })
    _write_json(weights / "trace_net_weights_policy.json", {"version": "trace_net_weights_policy_v1"})
    _write_jsonl(weighted / "trace_net_weighted_search_simulation_results.jsonl", [{
        "page_id": "p1",
        "original_rank": 1,
        "weighted_rank": 1,
        "weighted_score": 1.0,
        "weighted_score_components": {
            "base_score": 1.0,
            "bucket_bonus": 0,
            "evidence_diversity_bonus": 0,
            "exact_match_bonus": 0,
            "confidence_bonus": 0,
            "feedback_adjustment": 0,
        },
    }])
    result = build_weighted_search_calibration(WeightedSearchCalibrationPaths(weighted_search_dir=weighted, weights_dir=weights, output_dir=out))
    assert result["status"] == "FAIL"
