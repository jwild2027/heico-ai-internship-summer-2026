from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_community_ablation import (
    CommunityAblationPaths,
    evaluate_trace_net_community_ablation,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _fixture_paths(tmp_path: Path) -> CommunityAblationPaths:
    return CommunityAblationPaths(
        communities_dir=tmp_path / "communities",
        trace_net_dir=tmp_path / "trace_net",
        table_scan_dir=tmp_path / "table_scan",
        export_dir=tmp_path / "export",
        entity_trait_dir=tmp_path / "entity_traits",
    )


def _make_fixture(paths: CommunityAblationPaths) -> None:
    pages = [f"t_p_120_1176_p00000{i}" for i in range(1, 7)]
    nodes = []
    for page in pages:
        nodes.append({"id": f"page:{page}", "type": "page", "page_id": page})
    nodes.extend(
        [
            {"id": "route:table_high", "type": "trait"},
            {"id": "route:human_review", "type": "trait"},
            {"id": "role:table", "type": "trait"},
            {"id": "role:figure", "type": "trait"},
            {"id": "part:P1", "type": "part"},
            {"id": "part:P2", "type": "part"},
        ]
    )
    edges = [
        {"source": "page:t_p_120_1176_p000001", "target": "route:table_high"},
        {"source": "page:t_p_120_1176_p000002", "target": "route:table_high"},
        {"source": "page:t_p_120_1176_p000003", "target": "route:table_high"},
        {"source": "page:t_p_120_1176_p000004", "target": "route:human_review"},
        {"source": "page:t_p_120_1176_p000005", "target": "route:human_review"},
        {"source": "page:t_p_120_1176_p000006", "target": "route:human_review"},
        {"source": "page:t_p_120_1176_p000001", "target": "role:table"},
        {"source": "page:t_p_120_1176_p000002", "target": "role:table"},
        {"source": "page:t_p_120_1176_p000003", "target": "role:table"},
        {"source": "page:t_p_120_1176_p000004", "target": "role:figure"},
        {"source": "page:t_p_120_1176_p000005", "target": "role:figure"},
        {"source": "page:t_p_120_1176_p000006", "target": "role:figure"},
        {"source": "page:t_p_120_1176_p000001", "target": "part:P1"},
        {"source": "page:t_p_120_1176_p000002", "target": "part:P1"},
        {"source": "page:t_p_120_1176_p000003", "target": "part:P1"},
        {"source": "page:t_p_120_1176_p000004", "target": "part:P2"},
        {"source": "page:t_p_120_1176_p000005", "target": "part:P2"},
        {"source": "page:t_p_120_1176_p000006", "target": "part:P2"},
    ]
    _write_json(paths.projection_nodes_path, nodes)
    _write_json(paths.projection_edges_path, edges)
    _write_json(paths.page_index_path, {p: {"page_id": p, "ata_code": "25-21-00"} for p in pages})
    _write_jsonl(
        paths.repair_plan_path,
        [
            {"page_id": pages[0], "repair_route": "table_crop_tile_repair_route_high", "trust_tier": "C", "review_traits": ["table_expected_but_not_extracted"]},
            {"page_id": pages[1], "repair_route": "table_crop_tile_repair_route_high", "trust_tier": "C", "review_traits": ["table_expected_but_not_extracted"]},
            {"page_id": pages[2], "repair_route": "table_crop_tile_repair_route_high", "trust_tier": "C", "review_traits": ["table_expected_but_not_extracted"]},
            {"page_id": pages[3], "repair_route": "human_review_route", "trust_tier": "C", "review_traits": ["needs_human_review"]},
            {"page_id": pages[4], "repair_route": "human_review_route", "trust_tier": "C", "review_traits": ["needs_human_review"]},
            {"page_id": pages[5], "repair_route": "human_review_route", "trust_tier": "C", "review_traits": ["needs_human_review"]},
        ],
    )
    _write_jsonl(
        paths.table_candidate_plan_path,
        [
            {"page_id": pages[0], "route": "table_crop_tile_repair_route_high", "candidate_level": "high"},
            {"page_id": pages[1], "route": "table_crop_tile_repair_route_high", "candidate_level": "high"},
            {"page_id": pages[2], "route": "table_crop_tile_repair_route_high", "candidate_level": "high"},
            {"page_id": pages[3], "route": "skip_non_table", "candidate_level": "none"},
            {"page_id": pages[4], "route": "skip_non_table", "candidate_level": "none"},
            {"page_id": pages[5], "route": "skip_non_table", "candidate_level": "none"},
        ],
    )


def test_community_ablation_evaluates_baselines_and_writes_outputs(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    _make_fixture(paths)

    report = evaluate_trace_net_community_ablation(paths, algorithms="no_community,route_grouping,greedy_modularity", write=True)

    assert report["status"] == "OK"
    summary = report["summary"]
    assert summary["pages_loaded"] == 6
    assert summary["projection_edges"] > 0
    assert summary["available_algorithm_count"] >= 2
    assert paths.eval_json_path.exists()
    assert paths.eval_md_path.exists()

    algs = {a["algorithm"]: a for a in report["algorithms"]}
    assert "no_community" in algs
    assert "route_grouping" in algs
    assert algs["route_grouping"]["community_count"] == 2
    assert algs["route_grouping"]["route_purity"] == 1.0


def test_community_ablation_handles_missing_leiden_as_unavailable(tmp_path: Path, monkeypatch) -> None:
    paths = _fixture_paths(tmp_path)
    _make_fixture(paths)

    # Force the Leiden partition function to fail without depending on the local env.
    import tiff.trace_net_community_ablation as mod

    def boom(*args, **kwargs):
        raise RuntimeError("leiden unavailable for test")

    monkeypatch.setattr(mod, "_partition_leiden", boom)
    report = evaluate_trace_net_community_ablation(paths, algorithms="leiden,no_community", write=False)
    algs = {a["algorithm"]: a for a in report["algorithms"]}
    assert algs["leiden"]["algorithm_available"] is False
    assert "leiden unavailable" in algs["leiden"]["algorithm_error"]
