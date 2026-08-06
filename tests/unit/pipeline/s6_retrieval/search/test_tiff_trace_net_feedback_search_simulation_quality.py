from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_feedback_search_simulation import FeedbackSearchSimulationOptions, FeedbackSearchSimulationPaths, simulate_feedback_aware_search
from tiff.trace_net_feedback_search_simulation_quality import (
    FeedbackSearchSimulationQualityOptions,
    FeedbackSearchSimulationQualityPaths,
    check_feedback_search_simulation_quality,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_paths(tmp_path: Path) -> FeedbackSearchSimulationPaths:
    paths = FeedbackSearchSimulationPaths(search_dir=tmp_path / "search", feedback_dir=tmp_path / "feedback", output_dir=tmp_path / "sim")
    _write_json(paths.search_summary, {"part_number": "120-50645-009", "effective_query": "120-50645-009"})
    _write_json(paths.grouped_summary, {"status": "OK"})
    _write_jsonl(
        paths.grouped_results,
        [
            {"rank": 1, "group_id": "g1", "page_id": "p1", "group_score": 10, "rag_buckets": ["verified_part_evidence"], "safe_group": True, "excluded_supporting_results": 0},
            {"rank": 2, "group_id": "g2", "page_id": "p2", "group_score": 9, "rag_buckets": ["source_text_evidence"], "safe_group": True, "excluded_supporting_results": 0},
        ],
    )
    _write_jsonl(
        paths.feedback_signals,
        [
            {"signal_id": "s1", "query_fingerprint": "part_number:120-50645-009", "page_id": "p2", "signal": "boost_for_query", "strength": 1.0, "advisory_only": True, "ranking_mutation": False}
        ],
    )
    return paths


def test_quality_passes_for_safe_feedback_search_simulation(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    simulate_feedback_aware_search(paths, FeedbackSearchSimulationOptions())
    qpaths = FeedbackSearchSimulationQualityPaths(output_dir=paths.output_dir)
    result = check_feedback_search_simulation_quality(
        qpaths,
        FeedbackSearchSimulationQualityOptions(
            min_groups=1,
            min_matching_feedback_signals=1,
            min_feedback_signals_used=1,
            min_groups_adjusted=1,
            max_unsafe_results=0,
            max_excluded_results=0,
            write_json=True,
        ),
    )
    assert result["status"] == "OK"
    assert qpaths.quality.exists()


def test_quality_fails_when_no_signal_used_required(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    # Override with nonmatching signal.
    _write_jsonl(paths.feedback_signals, [{"signal_id": "s2", "query_fingerprint": "query:no_match", "page_id": "p2", "signal": "boost_for_query", "strength": 1.0, "advisory_only": True, "ranking_mutation": False}])
    simulate_feedback_aware_search(paths, FeedbackSearchSimulationOptions())
    result = check_feedback_search_simulation_quality(
        FeedbackSearchSimulationQualityPaths(output_dir=paths.output_dir),
        FeedbackSearchSimulationQualityOptions(min_feedback_signals_used=1),
    )
    assert result["status"] == "FAIL"
