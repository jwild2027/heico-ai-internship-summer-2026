from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_incremental_processing_runner_v1 import (
    build_execution_step,
    build_incremental_processing_runner,
    normalize_job,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def clean_orchestrator() -> dict:
    return {
        "schema_version": "trace_net_incremental_orchestrator_v1",
        "status": "INCREMENTAL_ORCHESTRATOR_PLAN_BUILT",
        "quality_status": "PASS",
        "summary": {
            "status": "PASS",
            "page_count": 509,
            "source_record_count": 1018,
            "dirty_page_count": 0,
            "affected_page_count": 0,
            "full_rescan_required": False,
            "unchanged_page_reprocess_count": 0,
        },
        "planned_jobs": [],
    }


def dirty_orchestrator() -> dict:
    return {
        "schema_version": "trace_net_incremental_orchestrator_v1",
        "status": "INCREMENTAL_ORCHESTRATOR_PLAN_BUILT",
        "quality_status": "PASS",
        "summary": {
            "status": "PASS",
            "page_count": 509,
            "source_record_count": 1018,
            "dirty_page_count": 2,
            "affected_page_count": 2,
            "changed_source_count": 1,
            "full_rescan_required": False,
            "unchanged_page_reprocess_count": 0,
        },
        "planned_jobs": [
            {
                "job_id": "job_ocr_1",
                "job_type": "ocr_changed_pages",
                "job_family": "ocr",
                "priority": "medium",
                "affected_page_count": 2,
                "affected_page_ids": ["p1", "p2"],
            },
            {
                "job_id": "job_qdrant_1",
                "job_type": "qdrant_upsert_changed_points",
                "job_family": "qdrant",
                "priority": "high",
                "affected_page_count": 2,
                "affected_page_ids": ["p1", "p2"],
            },
        ],
    }


def test_clean_orchestrator_produces_no_op_plan(tmp_path: Path) -> None:
    path = tmp_path / "orch.json"
    write_json(path, clean_orchestrator())
    report = build_incremental_processing_runner(
        path,
        tmp_path / "out",
        require_page_count=509,
        require_no_full_rescan=True,
        max_unchanged_page_reprocess=0,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["planned_job_count"] == 0
    assert report["summary"]["no_op_processed"] is True
    assert report["summary"]["external_command_execution_count"] == 0
    assert report["processing_steps"] == []


def test_dirty_orchestrator_creates_dry_run_steps_and_batches(tmp_path: Path) -> None:
    path = tmp_path / "orch.json"
    write_json(path, dirty_orchestrator())
    report = build_incremental_processing_runner(
        path,
        tmp_path / "out",
        batch_size=1,
        require_page_count=509,
        min_processing_steps=2,
        require_no_full_rescan=True,
        max_unchanged_page_reprocess=0,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["planned_job_count"] == 2
    assert report["summary"]["processing_step_count"] == 2
    assert report["summary"]["processing_batch_count"] == 4
    assert report["summary"]["qdrant_write_attempt_count"] == 0
    assert {s["job_type"] for s in report["processing_steps"]} == {
        "ocr_changed_pages",
        "qdrant_upsert_changed_points",
    }
    assert all(s["execution_status"] == "planned_only" for s in report["processing_steps"])


def test_normalize_job_infers_defaults() -> None:
    job = normalize_job({"job_type": "opensearch_upsert_changed_docs", "affected_page_ids": ["p1"]}, 1)
    assert job["job_family"] == "opensearch"
    assert job["affected_page_count"] == 1
    assert job["priority"] == "high"
    assert "OpenSearch" in job["runner_hint"]


def test_build_execution_step_marks_write_family_as_dry_run_required() -> None:
    job = normalize_job({"job_type": "graph_writeback_changed_nodes", "affected_page_ids": ["p1"]}, 1)
    step = build_execution_step(job, execution_mode="dry-run", batch_size=100, order=1)
    assert step["requires_dry_run_before_write"] is True
    assert step["postgres_write_attempted"] is False
    assert step["can_mutate_source_truth"] is False
