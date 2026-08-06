import json
from pathlib import Path

from tiff.trace_net_incremental_orchestrator_v1 import build_incremental_orchestrator_plan, quality_report


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def manifest_payload(*, dirty: bool = True) -> dict:
    dirty_stages = [
        "ocr",
        "page_element_registry",
        "table_understanding",
        "table_cell_normalizer",
        "figure_chart_understanding",
        "visual_ink_layout_calibrator",
        "fishnet_retry",
        "evidence_consensus",
        "trust_authority",
        "safe_candidates",
        "embeddings",
        "qdrant_upsert",
        "opensearch_upsert",
        "graph_attachment",
        "graph_writeback",
        "leiden_communities",
        "retrieval_regression_smoke",
    ] if dirty else []
    return {
        "schema_version": "trace_net_incremental_corpus_manifest_v1",
        "quality_status": "PASS",
        "source_file_records": [
            {
                "file_id": "src_1",
                "page_ids": ["t_p_120_1176_p000001"],
                "change_state": "changed" if dirty else "unchanged",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            }
        ],
        "missing_source_file_records": [],
        "page_manifest_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "source_file_ids": ["src_1"],
                "dirty_stages": dirty_stages,
                "dirty_stage_count": len(dirty_stages),
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "source_file_ids": ["src_2"],
                "dirty_stages": [],
                "dirty_stage_count": 0,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            },
        ],
    }


def test_builds_jobs_only_for_dirty_pages(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest_payload(dirty=True))

    plan = build_incremental_orchestrator_plan(
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        write_quality=True,
    )

    assert plan["quality_status"] == "PASS"
    assert plan["summary"]["dirty_page_count"] == 1
    assert plan["summary"]["planned_job_count"] >= 10
    assert plan["summary"]["affected_page_count"] == 1
    assert plan["summary"]["unchanged_page_reprocess_count"] == 0
    assert plan["summary"]["full_rescan_required"] is False
    assert all(job["affected_page_ids"] == ["t_p_120_1176_p000001"] for job in plan["planned_jobs"])
    assert any(job["job_type"] == "qdrant_upsert_changed_points" for job in plan["planned_jobs"])
    assert any(job["job_type"] == "opensearch_upsert_changed_docs" for job in plan["planned_jobs"])
    assert any(job["job_type"] == "graph_writeback_changed_nodes" for job in plan["planned_jobs"])


def test_clean_manifest_creates_no_jobs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest_payload(dirty=False))

    plan = build_incremental_orchestrator_plan(
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        write_quality=True,
    )

    assert plan["quality_status"] == "PASS"
    assert plan["summary"]["dirty_page_count"] == 0
    assert plan["summary"]["planned_job_count"] == 0
    assert plan["no_op_job"] is not None
    assert plan["summary"]["no_op_planned"] is True
    assert plan["summary"]["state_commit_after_success_only"] is True


def test_removed_sources_create_tombstone_jobs(tmp_path: Path) -> None:
    payload = manifest_payload(dirty=False)
    payload["missing_source_file_records"] = [
        {
            "file_id": "src_removed",
            "page_ids": ["t_p_120_1176_p000002"],
            "change_state": "missing",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
        }
    ]
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, payload)

    plan = build_incremental_orchestrator_plan(
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        write_quality=True,
    )

    assert plan["quality_status"] == "PASS"
    assert any(job["job_type"] == "qdrant_delete_removed_points" for job in plan["planned_jobs"])
    assert any(job["job_type"] == "opensearch_delete_removed_docs" for job in plan["planned_jobs"])
    assert any(job["job_type"] == "graph_tombstone_removed_source_nodes" for job in plan["planned_jobs"])
    assert plan["summary"]["unsafe_job_count"] == 0


def test_quality_report_enforces_no_full_rescan(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest_payload(dirty=True))
    plan = build_incremental_orchestrator_plan(
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        full_rescan_threshold=0.01,
    )
    report = quality_report(
        plan,
        require_page_count=2,
        max_unchanged_page_reprocess=0,
        require_no_full_rescan=True,
    )
    assert report["status"] == "FAIL"
    assert report["full_rescan_required"] is True
