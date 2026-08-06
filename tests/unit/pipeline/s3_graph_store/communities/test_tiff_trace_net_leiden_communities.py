import json
from pathlib import Path

from tiff.trace_net_leiden_communities import LeidenPaths, CommunityOptions, build_leiden_community_overlay


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_build_projection_and_fallback_communities(tmp_path: Path):
    export = tmp_path / "export"
    traits = tmp_path / "traits"
    trust = tmp_path / "trust"
    table = tmp_path / "table"
    trace = tmp_path / "trace"
    out = tmp_path / "communities"

    _write(export / "page_index.json", {"pages": [
        {"page_id": "p1", "ata_code": "25-21-00", "document_id": "doc1"},
        {"page_id": "p2", "ata_code": "25-21-00", "document_id": "doc1"},
        {"page_id": "p3", "ata_code": "25-21-00", "document_id": "doc1"},
    ]})
    _write(traits / "page_character_cards.json", [
        {"page_id": "p1", "page_role": "table", "image_class": "likely_table_or_grid", "parts": ["120-1"]},
        {"page_id": "p2", "page_role": "table", "image_class": "likely_table_or_grid", "parts": ["120-2"]},
        {"page_id": "p3", "page_role": "figure", "image_class": "likely_figure_or_diagram", "parts": ["120-3"]},
    ])
    _write_jsonl(table / "all_page_scan" / "table_candidate_plan.jsonl", [
        {"page_id": "p1", "route": "table_crop_tile_repair_route_high"},
        {"page_id": "p2", "route": "table_crop_tile_repair_route_high"},
    ])
    _write_jsonl(trust / "trust_trait_assertions.jsonl", [
        {"entity_id": "page:p1", "trait_id": "trust:visual_text:C"},
        {"entity_id": "page:p2", "trait_id": "trust:visual_text:C"},
        {"entity_id": "page:p3", "trait_id": "review:visual_text:hallucination_risk"},
    ])

    paths = LeidenPaths(export, traits, trust, table, trace, out)
    result = build_leiden_community_overlay(paths, CommunityOptions(algorithm="components"))

    assert result["status"] == "OK"
    assert result["summary"]["pages_loaded"] == 3
    assert result["summary"]["projection_edges"] > 0
    assert result["summary"]["community_count"] >= 1
    assert paths.summary_path.exists()
    assert paths.communities_jsonl_path.exists()


def test_greedy_fallback_runs_without_leiden_dependency(tmp_path: Path):
    export = tmp_path / "export"
    traits = tmp_path / "traits"
    trust = tmp_path / "trust"
    table = tmp_path / "table"
    trace = tmp_path / "trace"
    out = tmp_path / "communities"
    _write(export / "page_index.json", {"pages": [
        {"page_id": "p1", "ata_code": "A"}, {"page_id": "p2", "ata_code": "A"}, {"page_id": "p3", "ata_code": "B"}
    ]})
    _write(traits / "page_character_cards.json", [
        {"page_id": "p1", "page_role": "parts_list", "image_class": "likely_table_or_grid"},
        {"page_id": "p2", "page_role": "parts_list", "image_class": "likely_table_or_grid"},
        {"page_id": "p3", "page_role": "figure", "image_class": "likely_figure_or_diagram"},
    ])
    paths = LeidenPaths(export, traits, trust, table, trace, out)
    result = build_leiden_community_overlay(paths, CommunityOptions(algorithm="greedy"))
    assert result["status"] == "OK"
    assert result["summary"]["community_count"] >= 1
