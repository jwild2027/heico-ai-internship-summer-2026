from __future__ import annotations

import json
from pathlib import Path

from tiff.pipeline_manifest import (
    refresh_manifest_incremental_summary,
    format_manifest_summary,
    summarize_incremental_smoke_json,
)
from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest


def _smoke_payload(ok: bool = True) -> dict:
    return {
        "ok": ok,
        "dry_run": False,
        "changed_list_count": 1,
        "new_files": 0,
        "changed_files": 1,
        "unchanged_files": 0,
        "state_committed": True,
        "backend_command_planned": True,
        "changed_page_command_used": True,
        "full_backend_command_used": False,
        "ocr_command_skipped": True,
        "failed_commands": [],
        "errors": [],
        "warnings": [],
        "work_dir": "local_data/incremental_smoke",
        "changed_list": "local_data/incremental_smoke/changed_tiffs.txt",
        "source_page": {
            "page_id": "p1",
            "manual_id": "m1",
            "ata_code": "25-21-00",
            "page_label": "1056",
        },
    }


def _base_manifest() -> dict:
    return {
        "run_id": "20260101T000000Z",
        "pipeline": "tiff_backend_pipeline",
        "status": "ok",
        "steps": [
            {"name": "source_link_audit", "returncode": 0},
            {"name": "ocr_coverage_audit", "returncode": 0},
            {"name": "rag_eval", "returncode": 0},
        ],
        "sqlite_counts": {
            "manuals": 1,
            "pages": 1,
            "part_mentions": 1,
            "part_catalog_clean": 1,
            "rag_chunks": 1,
            "rag_embeddings": 1,
            "source_links": 1,
        },
        "eval_summary": {"status_counts": {"pass": 21}, "questions": 21},
        "qa_summary": {"review_queue_rows": 149, "by_report": {"suspicious_part_ata": 5}},
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
        "artifacts": {},
    }


def test_summarize_incremental_smoke_json_keeps_command_line_facts() -> None:
    summary = summarize_incremental_smoke_json(_smoke_payload())

    assert summary["ok"] is True
    assert summary["changed_list_count"] == 1
    assert summary["changed_page_command_used"] is True
    assert summary["full_backend_command_used"] is False
    assert summary["source_page_id"] == "p1"


def test_refresh_manifest_incremental_summary_updates_latest_and_timestamped(tmp_path: Path) -> None:
    manifest = _base_manifest()
    manifest_dir = tmp_path / "pipeline_runs"
    latest = manifest_dir / "latest_backend_pipeline.json"
    timestamped = manifest_dir / "tiff_backend_pipeline_20260101T000000Z.json"
    latest.parent.mkdir(parents=True)
    latest.write_text(json.dumps(manifest), encoding="utf-8")
    timestamped.write_text(json.dumps(manifest), encoding="utf-8")
    smoke_json = tmp_path / "changed_page_smoke.json"
    smoke_json.write_text(json.dumps(_smoke_payload()), encoding="utf-8")

    written = refresh_manifest_incremental_summary(incremental_json=smoke_json, manifest_path=latest)

    assert latest in written
    assert timestamped in written
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["incremental_summary"]["ok"] is True
    assert payload["artifacts"]["incremental_smoke_json"] == str(smoke_json)
    assert "Incremental smoke summary" in format_manifest_summary(payload)


def test_quality_gate_accepts_passing_incremental_smoke_summary() -> None:
    manifest = _base_manifest()
    manifest["incremental_summary"] = summarize_incremental_smoke_json(_smoke_payload())

    result = check_pipeline_manifest(
        manifest,
        thresholds=QualityGateThresholds(require_incremental_smoke=True),
    )

    assert result.status == "ok"
    assert result.summary["incremental_smoke_present"] is True
    assert result.summary["incremental_changed_list_count"] == 1
    names = {check.name: check.status for check in result.checks}
    assert names["incremental_smoke_backend_path"] == "OK"


def test_quality_gate_fails_bad_incremental_smoke_summary() -> None:
    manifest = _base_manifest()
    bad = _smoke_payload(ok=False)
    bad["errors"] = ["backend path failed"]
    bad["full_backend_command_used"] = True
    manifest["incremental_summary"] = summarize_incremental_smoke_json(bad)

    result = check_pipeline_manifest(
        manifest,
        thresholds=QualityGateThresholds(require_incremental_smoke=True),
    )

    assert result.status == "fail"
    names = {check.name: check.status for check in result.checks}
    assert names["incremental_smoke_ok"] == "FAIL"
    assert names["incremental_smoke_backend_path"] == "FAIL"
    assert names["incremental_smoke_errors"] == "FAIL"


def test_quality_gate_can_require_incremental_smoke_summary() -> None:
    result = check_pipeline_manifest(
        _base_manifest(),
        thresholds=QualityGateThresholds(require_incremental_smoke=True),
    )

    assert result.status == "fail"
    names = {check.name: check.status for check in result.checks}
    assert names["incremental_smoke_summary"] == "FAIL"
