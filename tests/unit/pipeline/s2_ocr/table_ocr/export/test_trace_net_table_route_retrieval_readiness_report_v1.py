from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_table_route_retrieval_readiness_report_v1 import (
    ReadinessThresholds,
    build_readiness_report,
    check_report_quality,
)


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _fixture_paths(tmp_path: Path):
    adapter = tmp_path / "adapter.json"
    smoke = tmp_path / "smoke.json"
    bridge = tmp_path / "bridge.json"
    integration = tmp_path / "integration.json"
    _write(
        adapter,
        {
            "quality_status": "PASS",
            "summary": {
                "table_exact_search_document_count": 1497,
                "field_counts": {"covered_part_number": 150, "manual_page_reference": 39, "ipl_part_number": 197, "ipl_text": 188},
                "answer_permission_count": 0,
                "can_answer_directly_count": 0,
                "can_prove_claims_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
                "opensearch_upload_attempt_count": 0,
            },
        },
    )
    _write(
        smoke,
        {
            "quality_status": "PASS",
            "summary": {
                "successful_smoke_query_count": 6,
                "total_match_count": 42,
                "answer_permission_count": 0,
                "can_answer_directly_count": 0,
                "can_prove_claims_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
                "opensearch_upload_attempt_count": 0,
            },
        },
    )
    _write(
        bridge,
        {
            "quality_status": "PASS",
            "summary": {
                "table_hybrid_bridge_record_count": 1497,
                "query_bridge_group_count": 6,
                "successful_query_bridge_group_count": 6,
                "answer_permission_count": 0,
                "can_answer_directly_count": 0,
                "can_prove_claims_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
                "opensearch_upload_attempt_count": 0,
            },
        },
    )
    _write(
        integration,
        {
            "quality_status": "PASS",
            "summary": {
                "integration_audit_record_count": 1503,
                "ranking_available_bridge_record_count": 1497,
                "page_with_ranking_signal_count": 13,
                "field_count": 6,
                "schema_missing_required_key_record_count": 0,
                "field_counts": {
                    "covered_part_number": 150,
                    "manual_page_reference": 39,
                    "ipl_part_number": 197,
                    "ipl_figure_item_or_quantity": 843,
                    "ipl_text": 188,
                    "page_rev_or_sequence_value": 80,
                },
                "answer_permission_count": 0,
                "can_answer_directly_count": 0,
                "can_prove_claims_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
                "opensearch_upload_attempt_count": 0,
            },
        },
    )
    return adapter, smoke, bridge, integration


def test_build_readiness_report_passes(tmp_path: Path) -> None:
    adapter, smoke, bridge, integration = _fixture_paths(tmp_path)
    report = build_readiness_report(
        table_exact_search_adapter_path=adapter,
        table_exact_search_smoke_path=smoke,
        table_hybrid_retrieval_bridge_path=bridge,
        table_hybrid_retrieval_integration_audit_path=integration,
        output_dir=tmp_path / "out",
        thresholds=ReadinessThresholds(),
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["retrieval_readiness_status"] == "READY_FOR_RETRIEVAL_RANKING_ONLY"
    assert summary["exact_search_document_count"] == 1497
    assert summary["ranking_available_bridge_record_count"] == 1497
    assert summary["answer_permission_count"] == 0
    assert summary["can_answer_directly_count"] == 0
    assert summary["opensearch_upload_attempt_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["inspect_md_path"]).exists()


def test_quality_check_passes(tmp_path: Path) -> None:
    adapter, smoke, bridge, integration = _fixture_paths(tmp_path)
    report = build_readiness_report(
        table_exact_search_adapter_path=adapter,
        table_exact_search_smoke_path=smoke,
        table_hybrid_retrieval_bridge_path=bridge,
        table_hybrid_retrieval_integration_audit_path=integration,
        output_dir=tmp_path / "out",
    )
    result = check_report_quality(report["report_path"], ReadinessThresholds(), write_json=True)
    assert result["quality_status"] == "PASS"
    assert (Path(report["report_path"]).with_name("trace_net_table_route_retrieval_readiness_report_v1_quality.json")).exists()


def test_quality_fails_if_answer_authority_leaks(tmp_path: Path) -> None:
    adapter, smoke, bridge, integration = _fixture_paths(tmp_path)
    data = json.loads(adapter.read_text(encoding="utf-8"))
    data["summary"]["answer_permission_count"] = 1
    _write(adapter, data)
    report = build_readiness_report(
        table_exact_search_adapter_path=adapter,
        table_exact_search_smoke_path=smoke,
        table_hybrid_retrieval_bridge_path=bridge,
        table_hybrid_retrieval_integration_audit_path=integration,
        output_dir=tmp_path / "out",
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["answer_permission_count"] == 1


def test_quality_fails_if_schema_missing(tmp_path: Path) -> None:
    adapter, smoke, bridge, integration = _fixture_paths(tmp_path)
    data = json.loads(integration.read_text(encoding="utf-8"))
    data["summary"]["schema_missing_required_key_record_count"] = 1
    _write(integration, data)
    report = build_readiness_report(
        table_exact_search_adapter_path=adapter,
        table_exact_search_smoke_path=smoke,
        table_hybrid_retrieval_bridge_path=bridge,
        table_hybrid_retrieval_integration_audit_path=integration,
        output_dir=tmp_path / "out",
    )
    assert report["quality_status"] == "FAIL"


def test_markdown_mentions_ranking_only(tmp_path: Path) -> None:
    adapter, smoke, bridge, integration = _fixture_paths(tmp_path)
    report = build_readiness_report(
        table_exact_search_adapter_path=adapter,
        table_exact_search_smoke_path=smoke,
        table_hybrid_retrieval_bridge_path=bridge,
        table_hybrid_retrieval_integration_audit_path=integration,
        output_dir=tmp_path / "out",
    )
    text = Path(report["inspect_md_path"]).read_text(encoding="utf-8")
    assert "ranking_only" in text
    assert "answer_authority: blocked" in text
