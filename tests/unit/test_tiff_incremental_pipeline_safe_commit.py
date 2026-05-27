from __future__ import annotations

from pathlib import Path

from tiff.incremental_pipeline import (
    IncrementalPipelineConfig,
    PipelineCommand,
    PipelineCommandResult,
    build_commands,
    load_pipeline_config,
    should_commit_state,
)
from tiff.incremental_state import ChangeDetectionSummary


def test_no_commit_when_changed_but_all_processing_skipped():
    summary = ChangeDetectionSummary(new_files=1, files_seen=1, changed_paths=["a.tif"])
    commands = [
        PipelineCommand("ocr", "ocr", ["python"], skip_reason="skip"),
        PipelineCommand("backend", "backend", ["python"], skip_reason="skip"),
    ]
    results = [PipelineCommandResult("ocr", "SKIPPED"), PipelineCommandResult("backend", "SKIPPED")]
    commit, message = should_commit_state(summary, commands, results)
    assert commit is False
    assert "no processing commands" in message.lower()


def test_no_commit_when_processing_fails():
    summary = ChangeDetectionSummary(new_files=1, files_seen=1, changed_paths=["a.tif"])
    commands = [PipelineCommand("ocr", "ocr", ["python"])]
    results = [PipelineCommandResult("ocr", "FAILED", returncode=1)]
    commit, message = should_commit_state(summary, commands, results)
    assert commit is False
    assert "failed" in message.lower()


def test_commit_when_changed_and_processing_succeeds():
    summary = ChangeDetectionSummary(new_files=1, files_seen=1, changed_paths=["a.tif"])
    commands = [PipelineCommand("ocr", "ocr", ["python"])]
    results = [PipelineCommandResult("ocr", "OK", returncode=0)]
    commit, message = should_commit_state(summary, commands, results)
    assert commit is True
    assert "success" in message.lower()


def test_build_commands_skips_when_unchanged():
    cfg = IncrementalPipelineConfig(config_path="local_config.yaml")
    summary = ChangeDetectionSummary(files_seen=3, unchanged_files=3)
    commands = build_commands(cfg, summary)
    assert commands[0].skip_reason == "No changed TIFF files."
    assert "No changed TIFF files" in commands[1].skip_reason


def test_load_pipeline_config_reads_simple_yaml(tmp_path: Path):
    cfg_path = tmp_path / "local_config.yaml"
    cfg_path.write_text(
        "db_path: custom/search.db\nembed_model: gemma-embed\ntiff_root: data/tiffs\n",
        encoding="utf-8",
    )
    cfg = load_pipeline_config(str(cfg_path))
    assert cfg.db_path == "custom/search.db"
    assert cfg.embed_model == "gemma-embed"
    assert cfg.tiff_root == "data/tiffs"
