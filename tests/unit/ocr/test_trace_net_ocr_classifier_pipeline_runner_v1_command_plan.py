from __future__ import annotations

from pathlib import Path

from tiff.trace_net_ocr_classifier_pipeline_runner_v1 import PipelinePaths, _build_command_plan


def test_command_plan_contains_build_and_check_for_each_stage(tmp_path):
    paths = PipelinePaths.from_output_dir(tmp_path / "out")
    commands = _build_command_plan(
        paths=paths,
        source_package=tmp_path / "metadata.zip",
        tesseract_cmd=tmp_path / "tesseract.exe",
        route_label_taxonomy=tmp_path / "taxonomy.json",
        psm_modes="3,6,11",
        request_timeout=180,
        python_executable="python",
    )
    assert len(commands) == 18
    assert sum(1 for command in commands if command.kind == "build") == 9
    assert sum(1 for command in commands if command.kind == "check") == 9
    assert commands[0].stage == "ocr"
    assert commands[-1].stage == "retrieval_payload_audit"
    assert any(any("build_trace_net_loader_contract_audit_v1.py" in part for part in command.command) for command in commands)
    assert any(any("check_trace_net_retrieval_payload_audit_v1_quality.py" in part for part in command.command) for command in commands)
