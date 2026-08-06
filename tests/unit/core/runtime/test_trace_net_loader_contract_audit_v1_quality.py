import json
from pathlib import Path

from tiff.trace_net_loader_contract_audit_v1 import build_loader_contract_audit, check_loader_contract_audit_quality


def test_quality_check_enforces_lineage_and_contract_counts(tmp_path):
    planner = tmp_path / "planner.json"
    ocr = tmp_path / "ocr.json"
    planner.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [{
            "page_id": "p1",
            "page_number": 1,
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
        }]
    }), encoding="utf-8")
    ocr.write_text(json.dumps({"records": [{"page_id": "p1", "canonical_page_number": 1, "source_member": "p1.tif", "raw_image_sha256": "abc"}]}), encoding="utf-8")
    build_loader_contract_audit(dry_run_loader_planner=planner, ocr_route_scan_pack=ocr, output_dir=tmp_path / "out")
    result = check_loader_contract_audit_quality(
        report_path=tmp_path / "out" / "trace_net_loader_contract_audit_v1.json",
        min_records=1,
        min_lineage_ready=1,
        max_missing_lineage=0,
        min_postgres_contract_ready=1,
        min_qdrant_contract_ready=1,
        min_opensearch_contract_ready=1,
        require_source_quality_pass=True,
        require_dry_run_only=True,
        require_no_human_review_required=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_unsafe=0,
        write_json=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "out" / "trace_net_loader_contract_audit_v1_quality_check.json").exists()


def test_quality_check_fails_when_missing_lineage_exceeds_limit(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "loader_contract_audit_record_count": 1,
            "lineage_ready_count": 0,
            "missing_lineage_count": 1,
            "postgres_contract_ready_count": 0,
            "qdrant_contract_ready_count": 0,
            "opensearch_contract_ready_count": 0,
            "source_dry_run_loader_planner_quality_status": "PASS",
            "dry_run_only": True,
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }), encoding="utf-8")
    result = check_loader_contract_audit_quality(report_path=report, max_missing_lineage=0)
    assert result["quality_status"] == "FAIL"
    assert result["failures"]
