from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_algorithm_policy_quality import build_algorithm_policy_quality


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _policy():
    return {
        "status": "OK",
        "policy_version": "trace_net_algorithm_policy_v1",
        "summary": {
            "leiden_available": True,
            "best_repair_batching_score": 0.959966,
            "best_retrieval_expansion_score": 0.899821,
        },
        "jobs": {
            "source_trace": {"selected_algorithm": "deterministic_graph_traversal", "uses_communities": False},
            "exact_part_lookup": {"selected_algorithm": "deterministic_graph_traversal", "uses_communities": False},
            "exact_page_lookup": {"selected_algorithm": "deterministic_graph_traversal", "uses_communities": False},
            "trace_net_repair_batching": {"selected_algorithm": "route_grouping", "uses_communities": False},
            "table_extraction_batching": {"selected_algorithm": "route_grouping", "uses_communities": False},
            "broad_retrieval_expansion": {"selected_algorithm": "leiden", "uses_communities": True},
            "community_summaries": {"selected_algorithm": "leiden", "uses_communities": True},
        },
    }


def test_algorithm_policy_quality_passes(tmp_path: Path) -> None:
    policy_path = tmp_path / "community_algorithm_policy.json"
    _write_json(policy_path, _policy())

    report = build_algorithm_policy_quality(policy_path)

    assert report["status"] == "OK"


def test_algorithm_policy_quality_fails_if_repair_not_route_when_required(tmp_path: Path) -> None:
    policy = _policy()
    policy["jobs"]["trace_net_repair_batching"]["selected_algorithm"] = "leiden"
    policy_path = tmp_path / "community_algorithm_policy.json"
    _write_json(policy_path, policy)

    report = build_algorithm_policy_quality(policy_path, require_route_for_repair=True)

    assert report["status"] == "FAIL"
    failed = {c["name"] for c in report["checks"] if c["status"] == "FAIL"}
    assert "algorithm_policy_route_repair" in failed


def test_algorithm_policy_quality_fails_if_source_trace_uses_community(tmp_path: Path) -> None:
    policy = _policy()
    policy["jobs"]["source_trace"]["selected_algorithm"] = "leiden"
    policy["jobs"]["source_trace"]["uses_communities"] = True
    policy_path = tmp_path / "community_algorithm_policy.json"
    _write_json(policy_path, policy)

    report = build_algorithm_policy_quality(policy_path)

    assert report["status"] == "FAIL"
    failed = {c["name"] for c in report["checks"] if c["status"] == "FAIL"}
    assert "algorithm_policy_deterministic_source_trace" in failed
    assert "algorithm_policy_no_communities_for_truth" in failed
