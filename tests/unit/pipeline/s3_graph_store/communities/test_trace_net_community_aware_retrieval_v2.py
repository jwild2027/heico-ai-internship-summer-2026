from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_community_aware_retrieval_v2 import build_community_aware_retrieval_v2


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_hybrid() -> dict:
    return {
        "quality_status": "PASS",
        "status": "HYBRID_RETRIEVAL_V2_BUILT",
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    {"hybrid_v2_rank": 1, "hybrid_v2_score": 0.5, "page_id": "p1", "part_numbers": ["120-46137-001"]},
                    {"hybrid_v2_rank": 2, "hybrid_v2_score": 0.49, "page_id": "p2"},
                ],
            }
        ],
    }


def sample_bridge() -> dict:
    return {
        "quality_status": "PASS",
        "status": "LEIDEN_NAVIGATION_METADATA_BRIDGE_BUILT",
        "summary": {
            "community_navigation_record_count": 3,
            "retrieval_navigation_hint_count": 2,
            "page_navigation_hint_count": 2,
            "review_only_community_count": 1,
            "low_navigation_confidence_count": 0,
        },
        "community_navigation_records": [
            {"community_id": "c1", "navigation_confidence": "HIGH_NAVIGATION_CONFIDENCE"},
            {"community_id": "c2", "navigation_confidence": "MODERATE_NAVIGATION_CONFIDENCE"},
            {"community_id": "c3", "navigation_confidence": "REVIEW_ONLY", "review_only": True},
        ],
        "retrieval_navigation_hints": [
            {
                "community_id": "c1",
                "refined_label": "Part family community 120-46137",
                "navigation_intent": "part_family_navigation",
                "navigation_confidence": "HIGH_NAVIGATION_CONFIDENCE",
                "representative_page_ids": ["p1"],
                "representative_part_family": "120-46137",
                "representative_part_numbers": ["120-46137-001"],
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "community_id": "c2",
                "refined_label": "Table community",
                "navigation_intent": "table_evidence_navigation",
                "navigation_confidence": "MODERATE_NAVIGATION_CONFIDENCE",
                "representative_page_ids": ["p3"],
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
        ],
        "page_navigation_hints": [
            {"page_id": "p1", "community_id": "c1", "navigation_confidence": "HIGH_NAVIGATION_CONFIDENCE"},
            {"page_id": "p2", "community_id": "c3", "navigation_confidence": "REVIEW_ONLY"},
        ],
    }


def test_build_creates_retrieval_only_navigation_records(tmp_path: Path) -> None:
    hybrid = tmp_path / "hybrid.json"
    bridge = tmp_path / "bridge.json"
    out = tmp_path / "out"
    write_json(hybrid, sample_hybrid())
    write_json(bridge, sample_bridge())

    report = build_community_aware_retrieval_v2(
        leiden_navigation_metadata_bridge_path=bridge,
        hybrid_v2_report_path=hybrid,
        output_dir=out,
        thresholds={
            "min_queries": 1,
            "min_queries_with_navigation_hints": 1,
            "min_navigation_results": 1,
            "min_page_navigation_boosts": 1,
            "require_navigation_bridge_quality_pass": True,
            "require_hybrid_v2_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["query_count"] == 1
    assert summary["queries_with_navigation_hints_count"] == 1
    assert summary["navigation_result_count"] >= 1
    assert summary["page_navigation_boost_count"] >= 1
    assert summary["review_only_hints_used_count"] == 0
    assert summary["can_answer_directly_count"] == 0
    assert summary["can_prove_claims_count"] == 0
    assert (out / "trace_net_community_aware_retrieval_v2.json").exists()


def test_review_only_hint_is_excluded(tmp_path: Path) -> None:
    hybrid = tmp_path / "hybrid.json"
    bridge = tmp_path / "bridge.json"
    out = tmp_path / "out"
    write_json(hybrid, sample_hybrid())
    write_json(bridge, sample_bridge())

    report = build_community_aware_retrieval_v2(
        leiden_navigation_metadata_bridge_path=bridge,
        hybrid_v2_report_path=hybrid,
        output_dir=out,
    )

    record = report["query_navigation_records"][0]
    excluded = record.get("excluded_hint_records") or []
    assert any(x.get("community_id") == "c3" for x in excluded)
    assert all(r.get("navigation_confidence") != "REVIEW_ONLY" for r in record.get("navigation_results") or [])


def test_quality_fails_when_required_navigation_missing(tmp_path: Path) -> None:
    hybrid = tmp_path / "hybrid.json"
    bridge = tmp_path / "bridge.json"
    out = tmp_path / "out"
    data = sample_bridge()
    data["page_navigation_hints"] = []
    data["retrieval_navigation_hints"] = []
    write_json(hybrid, sample_hybrid())
    write_json(bridge, data)

    report = build_community_aware_retrieval_v2(
        leiden_navigation_metadata_bridge_path=bridge,
        hybrid_v2_report_path=hybrid,
        output_dir=out,
        thresholds={"min_queries_with_navigation_hints": 1, "min_navigation_results": 1},
    )

    assert report["quality_status"] == "FAIL"
    assert report["quality_failures"]
