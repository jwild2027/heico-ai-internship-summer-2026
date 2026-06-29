from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_dry_run_loader_planner_v1 import build_dry_run_loader_planner, check_dry_run_loader_planner_quality


def _source(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "records": [
                    {
                        "page_id": "p1",
                        "page_number": 1,
                        "final_validated_operational_route": "table",
                        "postgres_graph_record": True,
                        "qdrant_embedding_allowed": True,
                        "opensearch_index_allowed": True,
                        "final_do_not_embed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_quality_check_passes_with_required_flags(tmp_path: Path) -> None:
    source = _source(tmp_path / "storage.json")
    out = tmp_path / "out"
    build_dry_run_loader_planner(four_route_storage_gate=source, output_dir=out)
    result = check_dry_run_loader_planner_quality(
        report_path=out / "trace_net_dry_run_loader_planner_v1.json",
        min_records=1,
        min_postgres_plans=1,
        min_qdrant_plans=1,
        min_opensearch_plans=1,
        require_source_quality_pass=True,
        require_decision_files=True,
        require_dry_run_only=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        write_json=True,
    )
    assert result["quality_status"] == "PASS"
    assert (out / "trace_net_dry_run_loader_planner_v1_quality_check.json").exists()


def test_quality_check_fails_minimums(tmp_path: Path) -> None:
    source = _source(tmp_path / "storage.json")
    out = tmp_path / "out"
    build_dry_run_loader_planner(four_route_storage_gate=source, output_dir=out)
    result = check_dry_run_loader_planner_quality(
        report_path=out / "trace_net_dry_run_loader_planner_v1.json",
        min_records=2,
    )
    assert result["quality_status"] == "FAIL"
    assert result["failures"]
