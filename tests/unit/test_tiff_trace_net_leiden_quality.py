from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_leiden_quality import LeidenQualityPaths, build_leiden_quality


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_good_overlay(out: Path, *, algorithm_used: str = "greedy", leiden_available: bool = False) -> None:
    _write(
        out / "leiden_community_summary.json",
        {
            "status": "OK",
            "requested_algorithm": "auto",
            "algorithm_used": algorithm_used,
            "leiden_available": leiden_available,
            "pages_loaded": 4,
            "projection_nodes": 12,
            "projection_edges": 18,
            "community_count": 2,
            "communities_with_pages": 2,
            "largest_community_pages": 3,
            "overlay_nodes": 14,
            "overlay_edges": 16,
        },
    )
    _write_jsonl(out / "leiden_communities.jsonl", [{"community_id": 0}, {"community_id": 1}])
    _write(out / "semantic_projection_nodes.json", [{"id": f"n{i}"} for i in range(12)])
    _write(out / "semantic_projection_edges.json", [{"source": "n0", "target": "n1"}])
    _write(out / "leiden_graph_nodes.json", [{"id": f"g{i}"} for i in range(14)])
    _write(out / "leiden_graph_edges.json", [{"source": "g0", "target": "g1"} for _ in range(16)])


def test_leiden_quality_passes_for_valid_overlay(tmp_path: Path) -> None:
    out = tmp_path / "communities"
    _write_good_overlay(out)
    report = build_leiden_quality(
        LeidenQualityPaths(out),
        min_pages=4,
        min_communities=1,
        min_projection_edges=1,
    )
    assert report["status"] == "OK"
    assert report["summary"]["leiden_pages_loaded"] == 4
    assert report["summary"]["leiden_community_count"] == 2


def test_leiden_quality_can_require_real_leiden(tmp_path: Path) -> None:
    out = tmp_path / "communities"
    _write_good_overlay(out, algorithm_used="greedy", leiden_available=False)
    report = build_leiden_quality(LeidenQualityPaths(out), require_leiden=True)
    assert report["status"] == "FAIL"
    assert any(c["name"] == "leiden_algorithm_available" and not c["ok"] for c in report["checks"])
