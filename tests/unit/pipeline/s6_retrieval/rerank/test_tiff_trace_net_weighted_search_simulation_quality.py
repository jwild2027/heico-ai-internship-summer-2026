from __future__ import annotations

from pathlib import Path
import json

from tiff.trace_net_weighted_search_simulation import WeightedSearchSimulationOptions, simulate_weighted_search
from tiff.trace_net_weighted_search_simulation_quality import (
    WeightedSearchQualityOptions,
    WeightedSearchQualityPaths,
    evaluate_weighted_search_quality,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_paths(tmp_path: Path):
    from tiff.trace_net_weighted_search_simulation import WeightedSearchSimulationPaths
    search_dir = tmp_path / "search"
    weights_dir = tmp_path / "weights"
    feedback_dir = tmp_path / "feedback"
    output_dir = tmp_path / "weighted"
    paths = WeightedSearchSimulationPaths(search_dir=search_dir, weights_dir=weights_dir, feedback_dir=feedback_dir, output_dir=output_dir)
    _write_json(paths.search_summary, {"status": "OK", "part_number": "120-50645-009", "effective_query": "120-50645-009"})
    _write_json(paths.grouped_summary, {"status": "OK", "grouped_page_records": 3})
    _write_json(paths.weights_policy, {
        "status": "OK", "version": "trace_net_weights_policy_v1",
        "retrieval_ranking": {
            "exact_match_bonuses": {"exact_part_number_match": 20.0, "exact_page_id_match": 25.0, "exact_phrase_match": 8.0, "all_query_terms_matched": 10.0, "per_matched_term": 2.0},
            "bucket_bonuses": {"verified_part_evidence": 8.0, "source_text_evidence": 5.0, "derived_context": 3.0, "source_evidence": 2.0},
            "evidence_diversity": {"per_bucket_bonus": 4.0, "max_bucket_bonus": 12.0},
            "confidence_bonus": {"multiplier": 3.0},
        },
        "feedback_ranking": {"reason_weights": {"answer_correct": 6.0, "wrong_page": -8.0, "citation_not_supporting_answer": -7.0, "expected_page_boost": 8.0}, "cap_min": -15.0, "cap_max": 15.0},
    })
    _write_jsonl(paths.grouped_results, [
        {"rank": 1, "group_id": "search_group:p3", "page_id": "t_p_120_1176_p000003", "group_score": 65.0, "best_score": 52.0, "rag_buckets": ["verified_part_evidence", "source_text_evidence", "derived_context"], "evidence_layers": ["part_catalog", "source_text", "table_tile_text_refined"], "matched_part_numbers": ["120-50645-009"], "max_usable_confidence": 0.88, "safe_group": True, "excluded_supporting_results": 0, "unsafe_supporting_results": 0, "source_url": "http://localhost/p3"},
        {"rank": 2, "group_id": "search_group:p320", "page_id": "t_p_120_1176_p000320", "group_score": 40.0, "best_score": 36.0, "rag_buckets": ["verified_part_evidence", "source_text_evidence"], "evidence_layers": ["part_catalog", "source_text"], "matched_part_numbers": ["120-50645-009"], "max_usable_confidence": 0.86, "safe_group": True, "excluded_supporting_results": 0, "unsafe_supporting_results": 0, "source_url": "http://localhost/p320"},
        {"rank": 3, "group_id": "search_group:p319", "page_id": "t_p_120_1176_p000319", "group_score": 50.0, "best_score": 46.0, "rag_buckets": ["source_text_evidence"], "evidence_layers": ["source_text"], "matched_part_numbers": ["120-50645-009"], "max_usable_confidence": 0.76, "safe_group": True, "excluded_supporting_results": 0, "unsafe_supporting_results": 0, "source_url": "http://localhost/p319"},
    ])
    _write_jsonl(paths.feedback_signals, [
        {"query_fingerprint": "part_number:120-50645-009", "target_id": "t_p_120_1176_p000320", "recommendation": "demote_for_query", "reason_counts": {"wrong_page": 1, "citation_not_supporting_answer": 1}, "ranking_eligible": True, "context_validated_count": 1, "context_warning_count": 0, "advisory_only": True, "mutates_source_truth": False},
        {"query_fingerprint": "part_number:120-50645-009", "target_id": "t_p_120_1176_p000003", "recommendation": "promote_expected_page_for_query", "reason_counts": {"wrong_page": 1}, "ranking_eligible": True, "context_validated_count": 1, "context_warning_count": 0, "advisory_only": True, "mutates_source_truth": False},
    ])
    return paths


def test_weighted_search_quality_passes(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    simulate_weighted_search(paths, WeightedSearchSimulationOptions())
    qpaths = WeightedSearchQualityPaths(output_dir=paths.output_dir)
    result = evaluate_weighted_search_quality(
        qpaths,
        WeightedSearchQualityOptions(
            min_groups=1,
            min_pages=1,
            min_rank_comparison_records=1,
            min_feedback_signals_used=1,
            min_groups_adjusted=1,
            min_rank_changed_records=1,
            max_unsafe_results=0,
            max_excluded_results=0,
            max_source_truth_mutations=0,
            max_context_warning_signals_used=0,
            write_json=True,
        ),
    )
    assert result["status"] == "OK"
    assert qpaths.quality.exists()


def test_weighted_search_quality_fails_on_missing_feedback_requirement(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    simulate_weighted_search(paths, WeightedSearchSimulationOptions(use_feedback=False))
    result = evaluate_weighted_search_quality(
        WeightedSearchQualityPaths(output_dir=paths.output_dir),
        WeightedSearchQualityOptions(min_feedback_signals_used=1),
    )
    assert result["status"] == "FAIL"
