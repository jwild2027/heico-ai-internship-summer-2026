from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_incremental_processing_runner_v1 import (
    build_incremental_processing_runner,
    quality_report,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def orchestrator(full_rescan: bool = False, unchanged_reprocess: int = 0) -> dict:
    return {
        "quality_status": "PASS",
        "summary": {
            "status": "PASS",
            "page_count": 509,
            "dirty_page_count": 0,
            "affected_page_count": 0,
            "full_rescan_required": full_rescan,
            "unchanged_page_reprocess_count": unchanged_reprocess,
        },
        "planned_jobs": [],
    }


def test_quality_report_passes_clean_report(tmp_path: Path) -> None:
    src = tmp_path / "orch.json"
    write_json(src, orchestrator())
    report = build_incremental_processing_runner(src, tmp_path / "out", require_page_count=509)
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_processing_runner_v1.json",
        require_page_count=509,
        require_no_full_rescan=True,
        max_unchanged_page_reprocess=0,
    )
    assert report["quality_status"] == "PASS"
    assert result["status"] == "PASS"


def test_quality_report_fails_when_full_rescan_required(tmp_path: Path) -> None:
    src = tmp_path / "orch.json"
    write_json(src, orchestrator(full_rescan=True))
    build_incremental_processing_runner(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_processing_runner_v1.json",
        require_no_full_rescan=True,
    )
    assert result["status"] == "FAIL"


def test_quality_report_fails_when_unchanged_pages_would_reprocess(tmp_path: Path) -> None:
    src = tmp_path / "orch.json"
    write_json(src, orchestrator(unchanged_reprocess=5))
    build_incremental_processing_runner(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_processing_runner_v1.json",
        max_unchanged_page_reprocess=0,
    )
    assert result["status"] == "FAIL"


def test_quality_json_written(tmp_path: Path) -> None:
    src = tmp_path / "orch.json"
    write_json(src, orchestrator())
    build_incremental_processing_runner(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_processing_runner_v1.json",
        write_json_report=True,
    )
    assert result["status"] == "PASS"
    assert (tmp_path / "out" / "trace_net_incremental_processing_runner_v1_quality.json").exists()
