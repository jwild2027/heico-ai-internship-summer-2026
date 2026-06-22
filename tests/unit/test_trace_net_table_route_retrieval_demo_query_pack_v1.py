from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_route_retrieval_demo_query_pack_v1 import (
    DemoPackThresholds,
    build_demo_query_pack,
    evaluate_quality,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _readiness_payload() -> dict:
    return {
        "quality_status": "PASS",
        "summary": {
            "retrieval_readiness_status": "READY_FOR_RETRIEVAL_RANKING_ONLY",
            "exact_search_document_count": 1497,
            "successful_smoke_query_count": 6,
            "total_smoke_match_count": 42,
            "bridge_record_count": 1497,
            "ranking_available_bridge_record_count": 1497,
            "ready_for_hybrid_retrieval_ranking": True,
            "ready_for_live_opensearch_upload": False,
            "field_counts": {
                "covered_part_number": 150,
                "manual_page_reference": 39,
                "ipl_part_number": 197,
                "ipl_text": 188,
            },
        },
    }


def _bridge_payload() -> dict:
    groups = []
    for idx, (query, field, value, page, boost) in enumerate(
        [
            ("120-36833-001", "covered_part_number", "120-36833-001", "t_p_120_1176_p000003", 1.35),
            ("25-21-00", "manual_page_reference", "25-21-00", "t_p_120_1176_p000005", 1.25),
            ("ABC-999", "ipl_part_number", "ABC-999", "t_p_120_1176_p000027", 1.30),
        ],
        start=1,
    ):
        groups.append(
            {
                "query": query,
                "match_count": 1,
                "page_ids": [page],
                "hits": [
                    {
                        "page_id": page,
                        "table_id": f"table_{idx}",
                        "field_name": field,
                        "normalized_value": value,
                        "routing_boost": boost,
                    }
                ],
            }
        )
    return {
        "quality_status": "PASS",
        "summary": {
            "table_hybrid_bridge_record_count": 1497,
            "field_counts": {"covered_part_number": 1, "manual_page_reference": 1, "ipl_part_number": 1},
        },
        "query_bridge_groups": groups,
    }


def test_build_demo_query_pack_passes(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    bridge_path = tmp_path / "bridge.json"
    out_dir = tmp_path / "out"
    _write_json(readiness_path, _readiness_payload())
    _write_json(bridge_path, _bridge_payload())

    report = build_demo_query_pack(
        table_route_retrieval_readiness_report_path=readiness_path,
        table_hybrid_retrieval_bridge_path=bridge_path,
        output_dir=out_dir,
        top_k=3,
        thresholds=DemoPackThresholds(
            min_demo_queries=3,
            min_successful_demo_queries=3,
            min_total_demo_matches=3,
            min_pages_with_demo_matches=1,
            min_field_count=3,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["demo_query_count"] == 3
    assert report["summary"]["successful_demo_query_count"] == 3
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["can_answer_directly_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
    assert report["demo_queries"][0]["retrieval_permission"] == "ranking_only"
    assert report["demo_queries"][0]["answer_authority"] == "blocked"
    assert (out_dir / "trace_net_table_route_retrieval_demo_query_pack_v1.json").exists()
    assert (out_dir / "trace_net_table_route_retrieval_demo_queries_v1.jsonl").exists()
    assert (out_dir / "trace_net_table_route_retrieval_demo_query_pack_v1_inspect.md").exists()


def test_quality_fails_when_no_demo_queries() -> None:
    summary = {
        "source_readiness_quality_pass": True,
        "source_bridge_quality_pass": True,
        "source_retrieval_readiness_status": "READY_FOR_RETRIEVAL_RANKING_ONLY",
        "demo_query_count": 0,
        "successful_demo_query_count": 0,
        "total_demo_match_count": 0,
        "page_with_demo_match_count": 0,
        "field_count": 0,
        "unsafe_demo_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }
    checks = evaluate_quality(summary, DemoPackThresholds())
    assert not all(check["passed"] for check in checks)
    assert any(check["name"] == "demo_query_count" and not check["passed"] for check in checks)


def test_demo_queries_include_plain_english_explanation(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    bridge_path = tmp_path / "bridge.json"
    out_dir = tmp_path / "out"
    _write_json(readiness_path, _readiness_payload())
    _write_json(bridge_path, _bridge_payload())

    report = build_demo_query_pack(
        table_route_retrieval_readiness_report_path=readiness_path,
        table_hybrid_retrieval_bridge_path=bridge_path,
        output_dir=out_dir,
        thresholds=DemoPackThresholds(min_field_count=3),
    )
    first = report["demo_queries"][0]
    assert "SKU" in first["analogy"]
    assert "table" in first["simple_explanation"].lower() or "part" in first["simple_explanation"].lower()
    assert first["final_gate_required"] is True


def test_top_k_limits_hits(tmp_path: Path) -> None:
    bridge = _bridge_payload()
    bridge["query_bridge_groups"][0]["hits"] = bridge["query_bridge_groups"][0]["hits"] * 10
    readiness_path = tmp_path / "readiness.json"
    bridge_path = tmp_path / "bridge.json"
    _write_json(readiness_path, _readiness_payload())
    _write_json(bridge_path, bridge)

    report = build_demo_query_pack(
        table_route_retrieval_readiness_report_path=readiness_path,
        table_hybrid_retrieval_bridge_path=bridge_path,
        output_dir=tmp_path / "out",
        top_k=2,
        thresholds=DemoPackThresholds(min_field_count=3),
    )
    assert len(report["demo_queries"][0]["hits"]) == 2


def test_requires_ready_status_when_requested(tmp_path: Path) -> None:
    readiness = _readiness_payload()
    readiness["summary"]["retrieval_readiness_status"] = "NOT_READY"
    readiness_path = tmp_path / "readiness.json"
    bridge_path = tmp_path / "bridge.json"
    _write_json(readiness_path, readiness)
    _write_json(bridge_path, _bridge_payload())

    report = build_demo_query_pack(
        table_route_retrieval_readiness_report_path=readiness_path,
        table_hybrid_retrieval_bridge_path=bridge_path,
        output_dir=tmp_path / "out",
        thresholds=DemoPackThresholds(require_readiness_status=True, min_field_count=3),
    )
    assert report["quality_status"] == "FAIL"
