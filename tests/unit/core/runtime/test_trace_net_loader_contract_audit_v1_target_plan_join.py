import json
from pathlib import Path

from tiff.trace_net_loader_contract_audit_v1 import build_loader_contract_audit


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_loader_contract_audit_joins_target_specific_plan_fields(tmp_path):
    planner = tmp_path / "planner.json"
    ocr = tmp_path / "ocr.json"
    _write(
        planner,
        {
            "quality_status": "PASS",
            "summary": {"loader_plan_record_count": 2},
            "records": [
                {
                    "page_id": "p1",
                    "page_number": 1,
                    "route": "plain_text",
                    "storage_decision": "validated_graph_and_semantic_index",
                    "loader_targets": ["postgres_graph", "qdrant"],
                    "dry_run_only": True,
                    "live_write_enabled": False,
                    "write_attempted": False,
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                },
                {
                    "page_id": "p2",
                    "page_number": 2,
                    "route": "table",
                    "storage_decision": "validated_graph_semantic_and_exact_index",
                    "loader_targets": ["postgres_graph", "qdrant", "opensearch"],
                    "dry_run_only": True,
                    "live_write_enabled": False,
                    "write_attempted": False,
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                },
            ],
            "postgres_dry_run_plan_records": [
                {"page_id": "p1", "page_number": 1, "evidence_policy": "graph_source_map_plus_validated_evidence_links", "dry_run_only": True, "live_write_enabled": False, "write_attempted": False, "answer_permission": False, "source_truth_mutation_allowed": False},
                {"page_id": "p2", "page_number": 2, "evidence_policy": "graph_source_map_plus_validated_evidence_links", "dry_run_only": True, "live_write_enabled": False, "write_attempted": False, "answer_permission": False, "source_truth_mutation_allowed": False},
            ],
            "qdrant_dry_run_plan_records": [
                {"page_id": "p1", "page_number": 1, "embedding_scope": "validated_page_or_evidence_summary", "dry_run_only": True, "live_write_enabled": False, "write_attempted": False, "answer_permission": False, "source_truth_mutation_allowed": False},
                {"page_id": "p2", "page_number": 2, "embedding_scope": "validated_page_or_evidence_summary", "dry_run_only": True, "live_write_enabled": False, "write_attempted": False, "answer_permission": False, "source_truth_mutation_allowed": False},
            ],
            "opensearch_dry_run_plan_records": [
                {"page_id": "p2", "page_number": 2, "exact_index_scope": "validated_table_or_exact_evidence", "dry_run_only": True, "live_write_enabled": False, "write_attempted": False, "answer_permission": False, "source_truth_mutation_allowed": False}
            ],
        },
    )
    _write(
        ocr,
        {
            "quality_status": "PASS",
            "records": [
                {"page_id": "p1", "canonical_page_number": 1, "source_member": "0001.tif", "raw_image_sha256": "aaa"},
                {"page_id": "p2", "canonical_page_number": 2, "source_member": "0002.tif", "raw_image_sha256": "bbb"},
            ],
        },
    )
    payload = build_loader_contract_audit(
        dry_run_loader_planner=planner,
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
    )
    summary = payload["summary"]
    assert summary["postgres_contract_ready_count"] == 2
    assert summary["qdrant_contract_ready_count"] == 2
    assert summary["opensearch_contract_ready_count"] == 1
    assert summary["contract_blocked_record_count"] == 0
    first = payload["records"][0]
    assert first["evidence_policy"] == "graph_source_map_plus_validated_evidence_links"
    assert first["embedding_scope"] == "validated_page_or_evidence_summary"
    assert first["target_plan_join_status"] == "joined_target_specific_dry_run_plans"
