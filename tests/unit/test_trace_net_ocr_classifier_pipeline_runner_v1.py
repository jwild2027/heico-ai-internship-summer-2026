from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tiff import trace_net_ocr_classifier_pipeline_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_stage_payload(stage: str) -> dict:
    base = {
        "quality_status": "PASS",
        "summary": {
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_record_count": 0,
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "write_attempt_count": 0,
        },
        "records": [],
    }
    summary = base["summary"]
    if stage == "ocr":
        summary.update({"source_page_count": 509, "scan_record_count": 509})
    if stage == "storage":
        summary.update({
            "final_validated_route_counts": {"blank": 14, "plain_text": 163, "table": 320, "image": 12},
            "storage_gate_record_count": 509,
            "postgres_graph_record_count": 509,
            "qdrant_embedding_allowed_count": 450,
            "opensearch_index_allowed_count": 282,
            "final_do_not_embed_count": 59,
        })
    if stage == "loader":
        summary.update({
            "loader_plan_record_count": 509,
            "postgres_dry_run_plan_count": 509,
            "qdrant_dry_run_plan_count": 450,
            "opensearch_dry_run_plan_count": 282,
            "blocked_loader_record_count": 59,
        })
    if stage == "contract":
        summary.update({
            "loader_contract_audit_record_count": 509,
            "postgres_contract_ready_count": 509,
            "qdrant_contract_ready_count": 450,
            "opensearch_contract_ready_count": 282,
            "contract_blocked_record_count": 0,
            "lineage_ready_count": 509,
            "missing_lineage_count": 0,
        })
    if stage == "retrieval_payload_audit":
        summary.update({
            "retrieval_payload_audit_record_count": 509,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "violation_record_count": 0,
            "route_payload_mismatch_count": 0,
            "blank_payload_violation_count": 0,
            "blocked_payload_violation_count": 0,
            "missing_lineage_payload_count": 0,
        })
    return base


def test_pipeline_runner_builds_all_stage_commands_and_summary(tmp_path):
    output_dir = tmp_path / "pipeline"
    paths = runner.PipelinePaths.from_output_dir(output_dir)
    commands_seen: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands_seen.append(command)
        script = command[1]
        stage = None
        for name, report_path in paths.report_paths.items():
            if name in script or (
                name == "four_route" and "four_route_operational" in script
            ) or (
                name == "payload_audit" and "retrieval_payload_audit" in script
            ):
                stage = name
        # More explicit because several names differ from file stems.
        if "ocr_route_scan_pack" in script:
            stage = "ocr"
        elif "route_confidence_resolver" in script:
            stage = "resolver"
        elif "four_route_operational_resolver" in script:
            stage = "four_route"
        elif "route_validator_runner" in script:
            stage = "validator"
        elif "route_unresolved_retry_probe" in script:
            stage = "retry"
        elif "four_route_storage_gate" in script:
            stage = "storage"
        elif "dry_run_loader_planner" in script:
            stage = "loader"
        elif "loader_contract_audit" in script:
            stage = "contract"
        elif "retrieval_payload_audit" in script:
            stage = "retrieval_payload_audit"
        if "build_" in script and stage:
            _write_json(paths.report_paths[stage], _build_stage_payload(stage))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    payload = runner.build_pipeline_runner(
        source_package=tmp_path / "metadata.zip",
        output_dir=output_dir,
        tesseract_cmd=tmp_path / "tesseract.exe",
        route_label_taxonomy=tmp_path / "taxonomy.json",
        command_runner=fake_runner,
        python_executable="python",
    )

    assert payload["quality_status"] == "PASS"
    assert len(commands_seen) == 18
    summary = payload["summary"]
    assert summary["stage_report_count"] == 9
    assert summary["all_stage_quality_pass"] is True
    assert summary["postgres_contract_ready_count"] == 509
    assert summary["qdrant_contract_ready_count"] == 450
    assert summary["opensearch_contract_ready_count"] == 282
    assert summary["qdrant_payload_count"] == 450
    assert summary["opensearch_payload_count"] == 282
    assert summary["write_attempt_count"] == 0
    assert (output_dir / "trace_net_ocr_classifier_pipeline_runner_v1.json").exists()


def test_pipeline_runner_raises_on_command_failure(tmp_path):
    def failing_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="bad", stderr="failed")

    try:
        runner.build_pipeline_runner(
            source_package=tmp_path / "metadata.zip",
            output_dir=tmp_path / "pipeline",
            tesseract_cmd=tmp_path / "tesseract.exe",
            command_runner=failing_runner,
            python_executable="python",
        )
    except RuntimeError as exc:
        assert "Pipeline command failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_check_quality_passes_for_good_report(tmp_path):
    report = tmp_path / "report.json"
    _write_json(
        report,
        {
            "quality_status": "PASS",
            "summary": {
                "stage_report_count": 9,
                "all_stage_quality_pass": True,
                "postgres_contract_ready_count": 509,
                "qdrant_contract_ready_count": 450,
                "opensearch_contract_ready_count": 282,
                "qdrant_payload_count": 450,
                "opensearch_payload_count": 282,
                "violation_record_count": 0,
                "dry_run_only": True,
                "human_review_required_count": 0,
                "unsafe_record_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "write_attempt_count": 0,
            },
        },
    )
    result = runner.check_quality(
        report_path=report,
        require_all_stage_quality_pass=True,
        require_dry_run_only=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_check_quality_fails_when_payload_violations_exist(tmp_path):
    report = tmp_path / "report.json"
    _write_json(
        report,
        {
            "quality_status": "PASS",
            "summary": {
                "stage_report_count": 9,
                "postgres_contract_ready_count": 509,
                "qdrant_contract_ready_count": 450,
                "opensearch_contract_ready_count": 282,
                "qdrant_payload_count": 450,
                "opensearch_payload_count": 282,
                "violation_record_count": 1,
            },
        },
    )
    result = runner.check_quality(report_path=report, max_violation_records=0)
    assert result["quality_status"] == "FAIL"
    assert any("violation" in failure for failure in result["failures"])
