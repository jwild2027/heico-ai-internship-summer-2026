import json
from pathlib import Path

from tiff.trace_net_incremental_orchestrator_v1 import build_incremental_orchestrator_plan, quality_report


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def base_manifest() -> dict:
    return {
        "schema_version": "trace_net_incremental_corpus_manifest_v1",
        "quality_status": "PASS",
        "source_file_records": [],
        "missing_source_file_records": [],
        "page_manifest_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "dirty_stages": [],
                "dirty_stage_count": 0,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            }
        ],
    }


def test_quality_report_passes_clean_plan(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_json(path, base_manifest())
    plan = build_incremental_orchestrator_plan(
        manifest_path=path,
        output_dir=tmp_path / "out",
        require_page_count=1,
    )
    report = quality_report(
        plan,
        require_page_count=1,
        max_unchanged_page_reprocess=0,
        require_no_full_rescan=True,
    )
    assert report["status"] == "PASS"
    assert report["planned_job_count"] == 0
    assert report["state_commit_after_success_only"] is True


def test_quality_report_fails_wrong_page_count(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_json(path, base_manifest())
    plan = build_incremental_orchestrator_plan(manifest_path=path, output_dir=tmp_path / "out")
    report = quality_report(plan, require_page_count=2)
    assert report["status"] == "FAIL"


def test_quality_report_writes_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_json(path, base_manifest())
    plan = build_incremental_orchestrator_plan(
        manifest_path=path,
        output_dir=tmp_path / "out",
        require_page_count=1,
        write_quality=True,
    )
    report_path = Path(plan["report_path"])
    report = quality_report(report_path, require_page_count=1, write_json_report=True)
    assert report["status"] == "PASS"
    assert (report_path.with_name("trace_net_incremental_orchestrator_v1_quality.json")).exists()
