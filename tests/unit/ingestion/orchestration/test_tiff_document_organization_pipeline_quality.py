from __future__ import annotations

from tiff.pipeline_manifest import (
    format_manifest_summary,
    summarize_document_organization_audit_json,
    summarize_document_organization_export_json,
)
from tiff.pipeline_quality import check_pipeline_manifest
from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps


def _base_manifest() -> dict:
    return {
        "run_id": "test-run",
        "status": "ok",
        "steps": [
            {"name": "search_index", "returncode": 0},
            {"name": "part_catalog", "returncode": 0},
            {"name": "rag_chunks", "returncode": 0},
            {"name": "rag_embeddings", "returncode": 0},
            {"name": "part_catalog_qa", "returncode": 0},
            {"name": "part_catalog_qa_triage", "returncode": 0},
            {"name": "source_link_audit", "returncode": 0},
            {"name": "ocr_coverage_audit", "returncode": 0},
            {"name": "document_organization_audit", "returncode": 0},
            {"name": "document_organization_export", "returncode": 0},
            {"name": "rag_eval", "returncode": 0},
        ],
        "sqlite_counts": {
            "manuals": 1,
            "pages": 10,
            "part_mentions": 25,
            "part_catalog_clean": 12,
            "rag_chunks": 10,
            "rag_embeddings": 10,
            "source_links": 10,
        },
        "eval_summary": {"status_counts": {"pass": 20, "manual_review": 1}},
        "qa_summary": {"review_queue_rows": 10, "by_report": {"suspicious_part_ata": 0}},
        "source_link_summary": {
            "ready_for_local_source_review": True,
            "ready_for_real_rescarta_deeplinks": False,
            "pages_without_source_links": 0,
            "missing_tiff_path": 0,
            "missing_ocr_path": 0,
            "missing_source_url": 0,
            "missing_tiff_files": 0,
            "missing_ocr_files": 0,
            "sample_queries_without_results": 0,
            "local_or_placeholder_rescarta_urls": 10,
        },
        "ocr_coverage_summary": {
            "local_ocr_paths_ready": True,
            "missing_ocr_paths": 0,
            "missing_ocr_files": 0,
            "unreadable_ocr_files": 0,
            "empty_ocr_files": 1,
            "short_ocr_files": 0,
            "nonempty_ocr_files": 9,
        },
        "document_organization_summary": {
            "logical_tree_ready": True,
            "manuals_total": 1,
            "pages_total": 10,
            "ata_groups_total": 2,
            "pages_without_ata": 0,
            "distinct_parts_total": 7,
            "part_mentions_total": 25,
            "pages_with_parts": 9,
            "empty_ocr_pages": 1,
        },
        "document_organization_export_summary": {
            "ready": True,
            "manual_count": 1,
            "page_count": 10,
            "ata_group_count": 2,
            "part_count": 7,
            "part_mention_count": 25,
            "pages_with_parts": 9,
            "empty_ocr_page_count": 1,
            "files_written": 5,
        },
    }


def test_pipeline_includes_document_organization_audit_and_export_before_eval() -> None:
    steps = build_pipeline_steps(PipelineConfig())
    names = [step.name for step in steps]
    assert "document_organization_audit" in names
    assert "document_organization_export" in names
    assert names.index("document_organization_audit") < names.index("document_organization_export") < names.index("rag_eval")
    step = steps[names.index("document_organization_audit")]
    assert "scripts/maintenance/ingestion/audit_document_organization.py" in step.command
    assert "--no-refresh-manifest" in step.command
    export_step = steps[names.index("document_organization_export")]
    assert "scripts/build/ingestion/export_document_organization.py" in export_step.command
    assert "--strict" in export_step.command


def test_document_organization_summary_is_preserved_for_manifest_status() -> None:
    data = {
        "logical_tree_ready": True,
        "manuals_total": 1,
        "pages_total": 509,
        "ata_groups_total": 5,
        "pages_without_ata": 0,
        "distinct_parts_total": 636,
        "part_mentions_total": 1409,
        "pages_with_parts": 454,
        "empty_ocr_pages": 14,
        "top_ata_groups": [{"ata_code": "25-21-00"}],
        "top_parts": [{"part_number": "120-37313-001"}],
        "warnings": ["empty OCR pages"],
    }
    summary = summarize_document_organization_audit_json(data)
    assert summary["logical_tree_ready"] is True
    assert summary["part_mentions_total"] == 1409
    assert summary["top_parts"] == 1
    assert summary["warnings"] == 1

    manifest = _base_manifest()
    export_summary = summarize_document_organization_export_json({
        "ready": True,
        "page_count": 509,
        "part_count": 636,
        "part_mention_count": 1409,
        "files_written": ["a", "b", "c", "d", "e"],
        "warnings": ["empty OCR pages"],
    })
    assert export_summary["ready"] is True
    assert export_summary["files_written"] == 5

    text = format_manifest_summary(manifest)
    assert "Document organization summary" in text
    assert "Document organization export summary" in text
    assert "Part mentions: 25" in text


def test_quality_gate_checks_document_organization_summary() -> None:
    result = check_pipeline_manifest(_base_manifest())
    assert result.status == "ok"
    assert result.summary["document_organization_ready"] is True
    assert result.summary["document_organization_distinct_parts"] == 7
    assert result.summary["document_organization_export_ready"] is True
    assert result.summary["document_organization_export_files"] == 5
    check_names = {check.name for check in result.checks}
    assert "document_organization_audit_step" in check_names
    assert "document_organization_export_step" in check_names
    assert "document_organization_parts" in check_names
    assert "document_organization_export_ready" in check_names


def test_quality_gate_fails_when_document_organization_is_missing() -> None:
    manifest = _base_manifest()
    manifest["steps"] = [step for step in manifest["steps"] if step["name"] not in {"document_organization_audit", "document_organization_export"}]
    manifest.pop("document_organization_summary")
    manifest.pop("document_organization_export_summary")
    result = check_pipeline_manifest(manifest)
    assert result.status == "fail"
    failed = {check.name for check in result.checks if check.status == "FAIL"}
    assert "document_organization_audit_step" in failed
    assert "document_organization_export_step" in failed
    assert "document_organization_summary" in failed
    assert "document_organization_export_summary" in failed
