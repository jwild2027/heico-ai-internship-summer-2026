from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_category_aware_leiden_overlay_v1 import (
    build_category_aware_leiden_overlay,
    build_overlay,
    label_for_community,
    page_category_node_id,
    quality_report,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_leiden() -> dict:
    return {
        "schema_version": "trace_net_leiden_graph_communities_v1",
        "quality_status": "PASS",
        "summary": {"community_count": 2, "page_count": 4},
        "communities": [
            {
                "community_id": "tracenet_community_00001",
                "label": "Source text community",
                "page_ids": ["p1", "p4"],
                "node_count": 10,
            },
            {
                "community_id": "tracenet_community_00002",
                "label": "Part family community 120-1",
                "page_ids": ["p2", "p3"],
                "node_count": 30,
            },
        ],
        "node_membership": [
            {"node_id": "page::p1", "node_type": "Page", "page_id": "p1", "community_id": "tracenet_community_00001"},
            {"node_id": "page::p2", "node_type": "Page", "page_id": "p2", "community_id": "tracenet_community_00002"},
        ],
    }


def sample_taxonomy() -> dict:
    def profile(page_id: str, label: str, dc_type: list[str], families: dict[str, int], hints: list[str], suppressed: list[str] | None = None, review: bool = False) -> dict:
        return {
            "page_id": page_id,
            "page_category_label": label,
            "dc_type": dc_type,
            "element_family_counts": families,
            "element_category_counts": {f"{k}_cat": v for k, v in families.items()},
            "leiden_hint_element_families": hints,
            "suppressed_leiden_hint_families": suppressed or [],
            "review_required": review,
            "part_numbers": ["120-TEST-001"] if "part" in families else [],
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }
    return {
        "schema_version": "trace_net_element_category_taxonomy_v1",
        "quality_status": "PASS",
        "summary": {"page_count": 4, "page_category_profile_count": 4},
        "page_category_profiles": [
            profile("p1", "text_source_page", ["technical_manual_page", "text_page"], {"source": 2, "text": 2, "citation": 1, "table": 9}, ["source", "text", "citation"], ["table"]),
            profile("p2", "blank_source_trace_page", ["technical_manual_page", "blank_page"], {"blank": 1, "source": 1, "review": 1}, ["blank", "source", "review"], ["visual"], True),
            profile("p3", "table_parts_diagram_page_review", ["technical_manual_page", "table_page", "visual_page", "parts_page"], {"table": 100, "part": 20, "visual": 5, "diagram": 10, "citation": 5, "review": 4}, ["source", "table", "part", "visual", "diagram", "citation", "review"], [], True),
            profile("p4", "text_source_page", ["technical_manual_page", "text_page"], {"source": 3, "text": 2, "context": 1}, ["source", "text", "context"], ["visual"]),
        ],
    }


def test_build_overlay_creates_category_profiles_and_no_global_hubs() -> None:
    report = build_overlay(leiden=sample_leiden(), taxonomy=sample_taxonomy())
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["page_count"] == 4
    assert summary["community_count"] == 2
    assert summary["communities_with_category_summary_count"] == 2
    assert summary["giant_global_category_hub_count"] == 0
    assert summary["category_as_proof_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert report["category_overlay_nodes"]
    assert report["category_overlay_edges"]


def test_text_page_keeps_tightened_leiden_hints() -> None:
    report = build_overlay(leiden=sample_leiden(), taxonomy=sample_taxonomy())
    membership = [m for m in report["page_category_membership"] if m["page_id"] == "p1"][0]
    assert "table" not in membership["leiden_hint_element_families"]
    assert "table" in membership["suppressed_leiden_hint_families"]
    hint_nodes = [n for n in report["category_overlay_nodes"] if n.get("page_id") == "p1" and n["node_type"] == "PageLocalCategoryHint"]
    families = {n["properties"]["element_family"] for n in hint_nodes}
    assert families == {"source", "text", "citation"}


def test_complex_table_diagram_community_gets_readable_label() -> None:
    report = build_overlay(leiden=sample_leiden(), taxonomy=sample_taxonomy())
    profiles = {c["community_id"]: c for c in report["community_category_profiles"]}
    label = profiles["tracenet_community_00002"]["category_aware_label"].lower()
    assert "table" in label or "visual" in label or "part" in label
    assert profiles["tracenet_community_00002"]["review_required"] is True


def test_quality_report_fails_for_global_hub() -> None:
    report = build_overlay(leiden=sample_leiden(), taxonomy=sample_taxonomy())
    report["summary"]["giant_global_category_hub_count"] = 1
    quality = quality_report(report)
    assert quality["status"] == "FAIL"
    assert any("giant_global_category_hub_count" in issue for issue in quality["issues"])


def test_build_category_aware_leiden_overlay_writes_outputs(tmp_path: Path) -> None:
    leiden_path = tmp_path / "leiden.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    output_dir = tmp_path / "out"
    write_json(leiden_path, sample_leiden())
    write_json(taxonomy_path, sample_taxonomy())

    report = build_category_aware_leiden_overlay(
        leiden_communities_path=leiden_path,
        element_category_taxonomy_path=taxonomy_path,
        output_dir=output_dir,
        require_page_count=4,
        min_communities=2,
        min_page_category_profiles=4,
        min_communities_with_category_summary=2,
        min_category_overlay_edges=1,
        require_source_leiden_quality_pass=True,
        require_source_taxonomy_quality_pass=True,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert (output_dir / "trace_net_category_aware_leiden_overlay_v1.json").exists()
    assert (output_dir / "trace_net_category_aware_leiden_overlay_v1_communities.jsonl").exists()
    assert (output_dir / "trace_net_category_aware_leiden_overlay_v1_nodes.jsonl").exists()


def test_page_category_node_id_is_page_local() -> None:
    assert page_category_node_id("p1", "table") == "page_category::p1::table"
