from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_candidate_scan import (
    TableCandidateScanPaths,
    build_table_candidate_quality,
    write_jsonl,
    _write_json,
)


def test_table_candidate_quality_passes(tmp_path: Path) -> None:
    paths = TableCandidateScanPaths(output_dir=tmp_path)
    _write_json(
        paths.summary,
        {
            "status": "OK",
            "records": 2,
            "candidate_records": 1,
            "high_candidate_records": 1,
            "medium_candidate_records": 0,
            "review_candidate_records": 0,
            "skip_records": 1,
            "missing_image_records": 0,
            "route_counts": {"table_crop_tile_repair_route_high": 1, "skip_non_table": 1},
        },
    )
    write_jsonl(paths.candidate_plan_jsonl, [{"page_id": "p1"}, {"page_id": "p2"}])
    report = build_table_candidate_quality(paths, min_records=2, expect_pages=2, min_candidates=1)
    assert report["status"] == "OK"
    assert all(check["ok"] for check in report["checks"])


def test_table_candidate_quality_fails_missing_candidates(tmp_path: Path) -> None:
    paths = TableCandidateScanPaths(output_dir=tmp_path)
    _write_json(paths.summary, {"status": "OK", "records": 2, "candidate_records": 0, "missing_image_records": 0})
    write_jsonl(paths.candidate_plan_jsonl, [{"page_id": "p1"}, {"page_id": "p2"}])
    report = build_table_candidate_quality(paths, min_records=2, expect_pages=2, min_candidates=1)
    assert report["status"] == "FAIL"
    assert any(not check["ok"] and check["name"] == "table_candidate_candidates" for check in report["checks"])
