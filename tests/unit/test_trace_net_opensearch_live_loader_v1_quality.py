from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_opensearch_live_loader_v1 import LiveLoaderThresholds, check_live_loader_quality


def test_quality_check_fails_on_unallowed_opensearch_write(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    payload = {
        "schema_version": "trace_net_opensearch_live_loader_v1",
        "quality_status": "PASS",
        "summary": {
            "opensearch_document_count": 100,
            "page_scoped_document_count": 100,
            "loaded_document_count": 100,
            "smoke_query_count": 3,
            "smoke_query_success_count": 3,
            "mapping_present": True,
            "adapter_quality_status": "PASS",
            "loader_smoke_quality_status": "PASS",
            "bulk_load_performed": True,
            "live_read_check_ok": True,
            "opensearch_write_attempt_count": 2,
            "missing_page_id_count": 0,
            "missing_source_trace_count": 0,
            "unsafe_index_document_count": 0,
            "raw_feedback_indexed_count": 0,
            "raw_visual_output_indexed_count": 0,
            "raw_ocr_unfiltered_indexed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = check_live_loader_quality(
        report_path=path,
        thresholds=LiveLoaderThresholds(
            min_documents=100,
            min_page_scoped_documents=100,
            min_loaded_documents=100,
            min_smoke_queries=3,
            require_adapter_quality_pass=True,
            require_loader_smoke_quality_pass=True,
            require_mapping=True,
            require_bulk_load=True,
            require_live_read_check=True,
            allow_opensearch_writes=False,
        ),
    )
    assert report["quality_status"] == "FAIL"
    assert any("allow-opensearch-writes" in err for err in report["quality_errors"])


def test_quality_check_allows_explicit_opensearch_write(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    payload = {
        "schema_version": "trace_net_opensearch_live_loader_v1",
        "quality_status": "PASS",
        "summary": {
            "opensearch_document_count": 100,
            "page_scoped_document_count": 100,
            "loaded_document_count": 100,
            "smoke_query_count": 3,
            "smoke_query_success_count": 3,
            "mapping_present": True,
            "adapter_quality_status": "PASS",
            "loader_smoke_quality_status": "PASS",
            "bulk_load_performed": True,
            "live_read_check_ok": True,
            "opensearch_write_attempt_count": 2,
            "missing_page_id_count": 0,
            "missing_source_trace_count": 0,
            "unsafe_index_document_count": 0,
            "raw_feedback_indexed_count": 0,
            "raw_visual_output_indexed_count": 0,
            "raw_ocr_unfiltered_indexed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = check_live_loader_quality(
        report_path=path,
        thresholds=LiveLoaderThresholds(
            min_documents=100,
            min_page_scoped_documents=100,
            min_loaded_documents=100,
            min_smoke_queries=3,
            require_adapter_quality_pass=True,
            require_loader_smoke_quality_pass=True,
            require_mapping=True,
            require_bulk_load=True,
            require_live_read_check=True,
            allow_opensearch_writes=True,
        ),
    )
    assert report["quality_status"] == "PASS"
