from __future__ import annotations

import json
from pathlib import Path

from tiff.pipeline_quality import (
    QualityGateThresholds,
    check_pipeline_manifest,
    check_pipeline_manifest_file,
    write_quality_gate_html,
    write_quality_gate_json,
)


def _manifest(**overrides):
    base = {
        "run_id": "test-run",
        "status": "ok",
        "steps": [
            {"name": "search_index", "returncode": 0},
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
            "questions": 4,
            "status_counts": {"pass": 3, "manual_review": 1},
            "llm_used": 1,
            "embeddings_used": 2,
        },
        "qa_summary": {
            "rows": 305,
            "by_report": {"suspicious_part_ata": 5},
            "by_severity": {"info": 57, "ok": 43, "review": 205},
        },
    }
    base.update(overrides)
    return base


def test_quality_gate_accepts_current_pilot_thresholds():
    result = check_pipeline_manifest(_manifest())
    assert result.status == "ok"
    assert result.summary["eval_failures"] == 0
    assert result.summary["qa_review_rows"] == 205


def test_quality_gate_fails_pipeline_failure():
    result = check_pipeline_manifest(_manifest(status="failed"))
    assert result.status == "fail"


def test_quality_gate_fails_eval_failures():
    manifest = _manifest(eval_summary={"questions": 1, "status_counts": {"fail": 1}})
    result = check_pipeline_manifest(manifest)
    assert result.status == "fail"


def test_quality_gate_reviews_too_many_qa_rows():
    manifest = _manifest(qa_summary={"rows": 999, "by_report": {"suspicious_part_ata": 5}, "by_severity": {"review": 300}})
    result = check_pipeline_manifest(manifest, thresholds=QualityGateThresholds(max_qa_review=250))
    assert result.status == "review"


def test_quality_gate_fails_missing_required_counts():
    manifest = _manifest(sqlite_counts={"manuals": 1, "pages": 509, "part_mentions": 0, "part_catalog_clean": 504, "rag_chunks": 538, "rag_embeddings": 538, "source_links": 509})
    result = check_pipeline_manifest(manifest)
    assert result.status == "fail"


def test_quality_gate_file_and_writers(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    result = check_pipeline_manifest_file(manifest_path)
    json_path = write_quality_gate_json(result, tmp_path / "quality.json")
    html_path = write_quality_gate_html(result, tmp_path / "quality.html")
    assert json_path.exists()
    assert html_path.exists()
    assert "TIFF Pipeline Quality Gate" in html_path.read_text(encoding="utf-8")
