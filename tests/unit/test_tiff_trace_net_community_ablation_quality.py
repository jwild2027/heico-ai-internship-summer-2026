from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_community_ablation import (
    CommunityAblationPaths,
    build_community_ablation_quality,
    write_community_ablation_quality,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_community_ablation_quality_passes_for_valid_report(tmp_path: Path) -> None:
    paths = CommunityAblationPaths(communities_dir=tmp_path / "communities")
    _write_json(
        paths.eval_json_path,
        {
            "status": "OK",
            "summary": {
                "pages_loaded": 509,
                "projection_nodes": 100,
                "projection_edges": 200,
                "algorithm_count": 4,
                "available_algorithm_count": 4,
                "leiden_available": True,
                "best_repair_batching_algorithm": "leiden",
                "best_repair_batching_score": 0.82,
                "best_retrieval_expansion_algorithm": "route_grouping",
                "best_retrieval_expansion_score": 0.75,
            },
            "algorithms": [
                {"algorithm": "no_community"},
                {"algorithm": "route_grouping"},
                {"algorithm": "networkx_greedy_modularity"},
                {"algorithm": "leiden"},
            ],
        },
    )

    quality = build_community_ablation_quality(paths, min_pages=509, min_algorithms=3, require_leiden=True, min_repair_score=0.5)
    assert quality["status"] == "OK"
    out = write_community_ablation_quality(quality, paths)
    assert out.exists()


def test_community_ablation_quality_fails_when_leiden_required_but_missing(tmp_path: Path) -> None:
    paths = CommunityAblationPaths(communities_dir=tmp_path / "communities")
    _write_json(
        paths.eval_json_path,
        {
            "status": "OK",
            "summary": {
                "pages_loaded": 509,
                "projection_nodes": 100,
                "projection_edges": 200,
                "algorithm_count": 3,
                "available_algorithm_count": 3,
                "leiden_available": False,
                "best_repair_batching_algorithm": "route_grouping",
                "best_repair_batching_score": 0.7,
            },
            "algorithms": [
                {"algorithm": "no_community"},
                {"algorithm": "route_grouping"},
                {"algorithm": "networkx_greedy_modularity"},
            ],
        },
    )

    quality = build_community_ablation_quality(paths, min_pages=509, min_algorithms=2, require_leiden=True)
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "community_ablation_leiden_available" and not c["ok"] for c in quality["checks"])
