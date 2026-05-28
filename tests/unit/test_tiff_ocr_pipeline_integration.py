from __future__ import annotations

from pathlib import Path

from tiff.pipeline_manifest import summarize_ocr_coverage_audit_json, format_manifest_summary
from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest
from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps


def _healthy_manifest() -> dict:
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
            {"name": "rag_eval", "returncode": 0},
        ],
        "sqlite_counts": {
            "manuals": 1,
            "pages": 509,
            "part_mentions": 1409,
            "part_catalog_clean": 504,
            "rag_chunks": 538,
            "rag_embeddings": 538,
            "source_links": 509,
        },
        "eval_summary": {
            "questions": 21,
            "status_counts": {"pass": 20, "manual_review": 1},
            "llm_used": 1,
            "embeddings_used": 5,
        },
        "qa_summary": {
            "rows": 305,
            "review_queue_rows": 149,
            "by_report": {"suspicious_part_ata": 5},
            "by_severity": {"ok": 43, "info": 113, "review": 149},
        },
        "source_link_summary": {
            "total_links": 509,
            "pages_total": 509,
            "pages_without_source_links": 0,
            "missing_tiff_path": 0,
            "missing_ocr_path": 0,
            "missing_source_url": 0,
            "missing_tiff_files": 0,
            "missing_ocr_files": 0,
            "sample_queries_without_results": 0,
            "ready_for_local_source_review": True,
            "ready_for_real_rescarta_deeplinks": False,
            "local_or_placeholder_rescarta_urls": 509,
        },
        "ocr_coverage_summary": {
            "total_source_links": 509,
            "pages_total": 509,
            "readable_ocr_files": 509,
            "nonempty_ocr_files": 495,
            "empty_ocr_files": 14,
            "short_ocr_files": 0,
            "missing_ocr_paths": 0,
            "missing_ocr_files": 0,
            "unreadable_ocr_files": 0,
            "local_ocr_paths_ready": True,
            "has_empty_or_short_ocr": True,
        },
    }


def test_pipeline_steps_include_ocr_coverage_after_source_audit() -> None:
    steps = build_pipeline_steps(PipelineConfig())
    names = [step.name for step in steps]

    assert "source_link_audit" in names
    assert "ocr_coverage_audit" in names
    assert "rag_eval" in names
    assert names.index("source_link_audit") < names.index("ocr_coverage_audit") < names.index("rag_eval")


def test_pipeline_steps_can_skip_ocr_coverage_audit() -> None:
    steps = build_pipeline_steps(PipelineConfig(skip_ocr_coverage_audit=True))
    assert "ocr_coverage_audit" not in [step.name for step in steps]


def test_manifest_summarizes_and_formats_ocr_coverage() -> None:
    summary = summarize_ocr_coverage_audit_json(
        {
            "total_source_links": 3,
            "readable_ocr_files": 3,
            "nonempty_ocr_files": 2,
            "empty_ocr_files": 1,
            "short_ocr_files": 0,
            "missing_ocr_paths": 0,
            "missing_ocr_files": 0,
            "unreadable_ocr_files": 0,
            "local_ocr_paths_ready": True,
            "has_empty_or_short_ocr": True,
            "sample_rows": [{"page_id": "p1"}],
            "warnings": ["empty OCR"],
        }
    )
    manifest = _healthy_manifest()
    manifest["ocr_coverage_summary"] = summary
    text = format_manifest_summary(manifest)

    assert summary["sample_rows"] == 1
    assert summary["warnings"] == 1
    assert "OCR coverage summary:" in text
    assert "Empty OCR files: 1" in text


def test_quality_gate_allows_empty_ocr_by_default() -> None:
    result = check_pipeline_manifest(_healthy_manifest())

    assert result.status == "ok"
    assert any(check.name == "ocr_empty_or_short_review" and check.status == "OK" for check in result.checks)
    assert result.summary["ocr_empty_files"] == 14


def test_quality_gate_can_require_complete_ocr_text() -> None:
    result = check_pipeline_manifest(
        _healthy_manifest(),
        thresholds=QualityGateThresholds(require_complete_ocr_text=True),
    )

    assert result.status == "fail"
    assert any(check.name == "ocr_empty_files" and check.status == "FAIL" for check in result.checks)


def test_quality_gate_fails_missing_ocr_summary() -> None:
    manifest = _healthy_manifest()
    manifest.pop("ocr_coverage_summary")
    result = check_pipeline_manifest(manifest)

    assert result.status == "fail"
    assert any(check.name == "ocr_coverage_summary" and check.status == "FAIL" for check in result.checks)
