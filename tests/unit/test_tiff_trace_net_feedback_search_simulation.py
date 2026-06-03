from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_feedback_search_simulation import (
    FeedbackSearchSimulationOptions,
    FeedbackSearchSimulationPaths,
    simulate_feedback_aware_search,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_paths(tmp_path: Path) -> FeedbackSearchSimulationPaths:
    search_dir = tmp_path / "search"
    feedback_dir = tmp_path / "feedback"
    output_dir = tmp_path / "simulation"
    paths = FeedbackSearchSimulationPaths(search_dir=search_dir, feedback_dir=feedback_dir, output_dir=output_dir)
    _write_json(paths.search_summary, {"status": "OK", "part_number": "120-50645-009", "effective_query": "120-50645-009"})
    _write_json(paths.grouped_summary, {"status": "OK", "top_group_score": 65.0})
    _write_jsonl(
        paths.grouped_results,
        [
            {
                "rank": 1,
                "group_id": "search_group:p000003",
                "page_id": "t_p_120_1176_p000003",
                "group_score": 65.0,
                "best_score": 52.0,
                "rag_buckets": ["verified_part_evidence", "source_text_evidence"],
                "safe_group": True,
                "excluded_supporting_results": 0,
                "source_url": "http://localhost/p000003",
            },
            {
                "rank": 2,
                "group_id": "search_group:p000320",
                "page_id": "t_p_120_1176_p000320",
                "group_score": 61.0,
                "best_score": 52.0,
                "rag_buckets": ["verified_part_evidence"],
                "safe_group": True,
                "excluded_supporting_results": 0,
                "source_url": "http://localhost/p000320",
            },
            {
                "rank": 3,
                "group_id": "search_group:p000319",
                "page_id": "t_p_120_1176_p000319",
                "group_score": 50.0,
                "best_score": 46.0,
                "rag_buckets": ["source_text_evidence"],
                "safe_group": True,
                "excluded_supporting_results": 0,
                "source_url": "http://localhost/p000319",
            },
        ],
    )
    _write_jsonl(
        paths.feedback_signals,
        [
            {
                "signal_id": "feedback_signal:boost-p3",
                "query_fingerprint": "part_number:120-50645-009",
                "page_id": "t_p_120_1176_p000003",
                "signal": "boost_for_query",
                "strength": 0.5,
                "net_score": 0.5,
                "event_count": 1,
                "reason_counts": {"expected_page": 1},
                "requires_review": False,
                "advisory_only": True,
                "ranking_mutation": False,
            },
            {
                "signal_id": "feedback_signal:demote-p320",
                "query_fingerprint": "part_number:120-50645-009",
                "page_id": "t_p_120_1176_p000320",
                "signal": "demote_for_query",
                "strength": 1.0,
                "net_score": -1.0,
                "event_count": 1,
                "reason_counts": {"wrong_page": 1},
                "requires_review": True,
                "advisory_only": True,
                "ranking_mutation": False,
            },
            {
                "signal_id": "feedback_signal:old-context",
                "query_fingerprint": "query:seat_bottom_backrest",
                "page_id": "t_p_120_1176_p000003",
                "signal": "demote_for_query",
                "strength": 1.0,
                "advisory_only": True,
                "ranking_mutation": False,
            },
        ],
    )
    return paths


def test_feedback_search_simulation_demotes_page_without_mutating_truth(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    result = simulate_feedback_aware_search(paths, FeedbackSearchSimulationOptions())
    summary = result["summary"]
    assert summary["status"] == "OK"
    assert summary["matching_feedback_signal_records"] == 2
    assert summary["feedback_signals_used"] == 2
    assert summary["groups_with_feedback_adjustment"] == 2
    assert summary["source_truth_mutation_records"] == 0
    assert summary["unsafe_simulated_records"] == 0
    page_order = summary["simulated_page_order"]
    assert page_order[0] == "t_p_120_1176_p000003"
    assert page_order.index("t_p_120_1176_p000320") > page_order.index("t_p_120_1176_p000319")
    assert paths.summary.exists()
    assert paths.simulation_jsonl.exists()


def test_feedback_search_simulation_ignores_nonmatching_query_signals(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    result = simulate_feedback_aware_search(paths, FeedbackSearchSimulationOptions(query="seat bottom backrest"))
    assert result["summary"]["query_fingerprint"] == "query:seat_bottom_backrest"
    assert result["summary"]["matching_feedback_signal_records"] == 1
