from __future__ import annotations

from pathlib import Path

from tiff.pipeline_manifest import (
    build_pipeline_manifest,
    format_manifest_summary,
    summarize_source_link_audit_json,
    summarize_ocr_coverage_audit_json,
)
from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest, format_quality_gate_result
from tiff.pipeline_runner import PipelineConfig, PipelineRunResult, PipelineStep, build_pipeline_steps


def _good_manifest() -> dict:
    return {
        "run_id": "TEST",
        "status": "ok",
        "steps": [
            {"name": "search_index", "returncode": 0},
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
            "status_counts": {"pass": 20, "manual_review": 1},
            "questions": 21,
            "llm_used": 1,
            "embeddings_used": 5,
        },
        "qa_summary": {
            "review_queue_rows": 149,
            "by_report": {"suspicious_part_ata": 5},
            "by_severity": {"info": 113, "ok": 43, "review": 149},
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
            "source_links_table_exists": True,
            "total_source_links": 509,
            "pages_total": 509,
            "missing_ocr_paths": 0,
            "missing_ocr_files": 0,
            "unreadable_ocr_files": 0,
            "nonempty_ocr_files": 495,
            "empty_ocr_files": 14,
            "short_ocr_files": 0,
            "local_ocr_paths_ready": True,
            "has_empty_or_short_ocr": True,
        },
    }


def test_pipeline_adds_source_link_audit_before_rag_eval(tmp_path: Path) -> None:
    questions = tmp_path / "questions.json"
    questions.write_text("[]", encoding="utf-8")
    config_file = tmp_path / "missing-local-config.yaml"
    config = PipelineConfig(
        python_executable="python",
        config_path=str(config_file),
        questions_path=str(questions),
    )

    steps = build_pipeline_steps(config)
    names = [step.name for step in steps]

    assert "source_link_audit" in names
    assert names.index("source_link_audit") < names.index("rag_eval")
    audit = steps[names.index("source_link_audit")]
    assert audit.command[:2] == ("python", "scripts/maintenance/ingestion/audit_source_links.py")
    assert "--strict" in audit.command
    assert "--write-json" in audit.command
    assert "local_data/source_links/source_link_audit.json" in audit.command


def test_pipeline_adds_ocr_coverage_audit_before_rag_eval(tmp_path: Path) -> None:
    questions = tmp_path / "questions.json"
    questions.write_text("[]", encoding="utf-8")
    config_file = tmp_path / "missing-local-config.yaml"
    config = PipelineConfig(
        python_executable="python",
        config_path=str(config_file),
        questions_path=str(questions),
    )

    steps = build_pipeline_steps(config)
    names = [step.name for step in steps]

    assert "ocr_coverage_audit" in names
    assert names.index("source_link_audit") < names.index("ocr_coverage_audit") < names.index("rag_eval")
    audit = steps[names.index("ocr_coverage_audit")]
    assert audit.command[:2] == ("python", "scripts/maintenance/ocr/audit_ocr_coverage.py")
    assert "--strict" in audit.command
    assert "--write-json" in audit.command
    assert "--fail-on-empty-ocr" not in audit.command
    assert "local_data/ocr/ocr_coverage_audit.json" in audit.command


def test_pipeline_can_skip_source_link_audit() -> None:
    config = PipelineConfig(
        python_executable="python",
        skip_search_index=True,
        skip_source_audit=True,
        skip_ocr_coverage_audit=True,
        skip_part_catalog=True,
        skip_rag_chunks=True,
        skip_embeddings=True,
        skip_qa=True,
        skip_eval=True,
    )

    assert build_pipeline_steps(config) == []


def test_summarize_source_link_audit_json_keeps_readiness_fields() -> None:
    summary = summarize_source_link_audit_json(
        {
            "total_links": 509,
            "pages_total": 509,
            "pages_without_source_links": 0,
            "missing_tiff_files": 0,
            "missing_ocr_files": 0,
            "ready_for_local_source_review": True,
            "ready_for_real_rescarta_deeplinks": False,
            "local_or_placeholder_rescarta_urls": 509,
            "warnings": ["placeholder urls"],
            "sample_rows": [{"query": "120-37313-001"}],
        }
    )

    assert summary["total_links"] == 509
    assert summary["pages_without_source_links"] == 0
    assert summary["ready_for_local_source_review"] is True
    assert summary["ready_for_real_rescarta_deeplinks"] is False
    assert summary["local_or_placeholder_rescarta_urls"] == 509
    assert summary["warnings"] == 1
    assert "sample_rows" not in summary


def test_summarize_ocr_coverage_audit_json_keeps_warning_fields() -> None:
    summary = summarize_ocr_coverage_audit_json(
        {
            "total_source_links": 509,
            "pages_total": 509,
            "missing_ocr_paths": 0,
            "missing_ocr_files": 0,
            "unreadable_ocr_files": 0,
            "nonempty_ocr_files": 495,
            "empty_ocr_files": 14,
            "short_ocr_files": 0,
            "local_ocr_paths_ready": True,
            "has_empty_or_short_ocr": True,
            "warnings": ["empty OCR"],
            "sample_rows": [{"page_id": "p1"}],
        }
    )

    assert summary["total_source_links"] == 509
    assert summary["local_ocr_paths_ready"] is True
    assert summary["empty_ocr_files"] == 14
    assert summary["warnings"] == 1
    assert summary["sample_rows"] == 1


def test_manifest_summary_prints_source_link_summary() -> None:
    text = format_manifest_summary(_good_manifest())

    assert "Source-link summary:" in text
    assert "Total links: 509" in text
    assert "Local source review ready: True" in text
    assert "Real ResCarta deep-link ready: False" in text
    assert "OCR coverage summary:" in text
    assert "Empty OCR files: 14" in text


def test_quality_gate_passes_local_source_ready_with_placeholder_rescarta() -> None:
    result = check_pipeline_manifest(_good_manifest(), manifest_path="local_data/pipeline_runs/latest_backend_pipeline.json")
    text = format_quality_gate_result(result)

    assert result.status == "ok"
    assert "source_local_review_ready" in text
    assert "source_real_rescarta_ready" in text
    assert "Status: OK" in text


def test_quality_gate_allows_empty_ocr_by_default_but_can_require_complete_text() -> None:
    result = check_pipeline_manifest(_good_manifest())
    assert result.status == "ok"

    strict = check_pipeline_manifest(_good_manifest(), thresholds=QualityGateThresholds(require_complete_ocr_text=True))
    assert strict.status == "fail"
    failed = {check.name for check in strict.checks if check.status == "FAIL"}
    assert "ocr_empty_files" in failed


def test_quality_gate_fails_when_source_links_are_missing() -> None:
    manifest = _good_manifest()
    manifest["source_link_summary"] = {
        **manifest["source_link_summary"],
        "pages_without_source_links": 2,
        "ready_for_local_source_review": False,
    }

    result = check_pipeline_manifest(manifest, thresholds=QualityGateThresholds(max_source_pages_without_links=0))

    assert result.status == "fail"
    failed = {check.name for check in result.checks if check.status == "FAIL"}
    assert "source_local_review_ready" in failed
    assert "source_pages_without_links" in failed


def test_quality_gate_can_require_real_rescarta_later() -> None:
    result = check_pipeline_manifest(_good_manifest(), thresholds=QualityGateThresholds(require_real_rescarta=True))

    assert result.status == "fail"
    failed = {check.name for check in result.checks if check.status == "FAIL"}
    assert "source_real_rescarta_ready" in failed


def test_manifest_artifacts_include_source_link_audit_json() -> None:
    config = PipelineConfig(
        db_path="missing.db",
        skip_search_index=True,
        skip_source_audit=True,
        skip_ocr_coverage_audit=True,
        skip_part_catalog=True,
        skip_rag_chunks=True,
        skip_embeddings=True,
        skip_qa=True,
        skip_eval=True,
    )
    manifest = build_pipeline_manifest(
        config=config,
        results=[
            PipelineRunResult(
                step=PipelineStep(name="source_link_audit", command=("python", "scripts/maintenance/ingestion/audit_source_links.py")),
                returncode=0,
            )
        ],
        status="ok",
    )

    assert manifest["artifacts"]["source_link_audit_json"] == "local_data/source_links/source_link_audit.json"
    assert manifest["artifacts"]["ocr_coverage_json"] == "local_data/ocr/ocr_coverage_audit.json"
    assert "source_link_summary" in manifest
    assert "ocr_coverage_summary" in manifest
