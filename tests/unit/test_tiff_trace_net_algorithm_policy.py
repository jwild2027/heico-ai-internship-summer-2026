from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_algorithm_policy import AlgorithmPolicyPaths, build_algorithm_policy, build_and_write_algorithm_policy


def _ablation_report():
    return {
        "status": "OK",
        "summary": {
            "pages_loaded": 509,
            "projection_nodes": 1856,
            "projection_edges": 12363,
            "leiden_available": True,
            "best_repair_batching_algorithm": "route_grouping",
            "best_repair_batching_score": 0.959966,
            "best_retrieval_expansion_algorithm": "leiden",
            "best_retrieval_expansion_score": 0.899821,
            "leiden_vs_route_repair_delta": -0.114817,
            "leiden_vs_route_retrieval_delta": 0.014623,
        },
        "algorithms": [
            {"algorithm": "no_community", "algorithm_available": True, "repair_batching_score": 0.701813, "retrieval_expansion_score": 0.65},
            {"algorithm": "route_grouping", "algorithm_available": True, "repair_batching_score": 0.959966, "retrieval_expansion_score": 0.885198},
            {"algorithm": "networkx_greedy_modularity", "algorithm_available": True, "repair_batching_score": 0.896215, "retrieval_expansion_score": 0.846756},
            {"algorithm": "leiden", "algorithm_available": True, "repair_batching_score": 0.845149, "retrieval_expansion_score": 0.899821},
        ],
    }


def test_algorithm_policy_selects_route_for_repair_and_leiden_for_retrieval() -> None:
    policy = build_algorithm_policy(_ablation_report())
    jobs = policy["jobs"]

    assert jobs["source_trace"]["selected_algorithm"] == "deterministic_graph_traversal"
    assert jobs["exact_part_lookup"]["selected_algorithm"] == "deterministic_graph_traversal"
    assert jobs["trace_net_repair_batching"]["selected_algorithm"] == "route_grouping"
    assert jobs["table_extraction_batching"]["selected_algorithm"] == "route_grouping"
    assert jobs["broad_retrieval_expansion"]["selected_algorithm"] == "leiden"
    assert jobs["community_summaries"]["selected_algorithm"] == "leiden"
    assert jobs["source_trace"]["uses_communities"] is False
    assert jobs["broad_retrieval_expansion"]["uses_communities"] is True


def test_algorithm_policy_writes_artifacts(tmp_path: Path) -> None:
    community_dir = tmp_path / "communities"
    community_dir.mkdir(parents=True)
    (community_dir / "community_ablation_eval.json").write_text(json.dumps(_ablation_report()), encoding="utf-8")

    paths = AlgorithmPolicyPaths(community_dir=community_dir)
    policy = build_and_write_algorithm_policy(paths)

    assert policy["status"] == "OK"
    assert paths.policy_path.exists()
    assert paths.policy_report_path.exists()
    saved = json.loads(paths.policy_path.read_text(encoding="utf-8"))
    assert saved["jobs"]["trace_net_repair_batching"]["selected_algorithm"] == "route_grouping"
