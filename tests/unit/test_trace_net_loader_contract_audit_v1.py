import json
from pathlib import Path

from tiff.trace_net_loader_contract_audit_v1 import build_loader_contract_audit


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_loader_contract_audit_repairs_lineage_and_keeps_dry_run(tmp_path):
    planner = tmp_path / "planner.json"
    ocr = tmp_path / "ocr.json"
    _write(planner, {
        "quality_status": "PASS",
        "summary": {"loader_plan_record_count": 2},
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "route": "plain_text",
                "storage_decision": "validated_graph_and_semantic_index",
                "loader_targets": ["postgres_graph", "qdrant"],
                "evidence_policy": "graph_source_map_plus_validated_evidence_links",
                "embedding_scope": "validated_page_or_evidence_summary",
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
                "evidence_policy": "graph_source_map_plus_validated_evidence_links",
                "embedding_scope": "validated_page_or_evidence_summary",
                "exact_index_scope": "validated_table_or_exact_evidence",
                "dry_run_only": True,
                "live_write_enabled": False,
                "write_attempted": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
        ]
    })
    _write(ocr, {
        "quality_status": "PASS",
        "records": [
            {"page_id": "p1", "canonical_page_number": 1, "source_member": "a/p1.tif", "raw_image_sha256": "aaa"},
            {"page_id": "p2", "canonical_page_number": 2, "source_member": "a/p2.tif", "raw_image_sha256": "bbb"},
        ]
    })
    payload = build_loader_contract_audit(
        dry_run_loader_planner=planner,
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["lineage_ready_count"] == 2
    assert summary["missing_lineage_count"] == 0
    assert summary["postgres_contract_ready_count"] == 2
    assert summary["qdrant_contract_ready_count"] == 2
    assert summary["opensearch_contract_ready_count"] == 1
    assert summary["write_attempt_count"] == 0
    first = payload["records"][0]
    assert first["source_member"] == "a/p1.tif"
    assert first["raw_tiff_reference"] == "a/p1.tif"
    assert first["source_image_sha256"] == "aaa"
    assert first["live_write_allowed"] is False


def test_loader_contract_audit_blocks_missing_lineage(tmp_path):
    planner = tmp_path / "planner.json"
    _write(planner, {
        "quality_status": "PASS",
        "summary": {"loader_plan_record_count": 1},
        "records": [{
            "page_id": "p1",
            "page_number": 1,
            "route": "plain_text",
            "storage_decision": "validated_graph_and_semantic_index",
            "loader_targets": ["postgres_graph", "qdrant"],
            "evidence_policy": "graph_source_map_plus_validated_evidence_links",
            "embedding_scope": "validated_page_or_evidence_summary",
            "dry_run_only": True,
            "live_write_enabled": False,
            "write_attempted": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }]
    })
    payload = build_loader_contract_audit(
        dry_run_loader_planner=planner,
        output_dir=tmp_path / "out",
        quality=False,
    )
    record = payload["records"][0]
    assert payload["quality_status"] == "PASS"
    assert record["lineage_ready"] is False
    assert "missing_lineage" in record["loader_contract_blockers"]
    assert payload["summary"]["contract_blocked_record_count"] == 1
