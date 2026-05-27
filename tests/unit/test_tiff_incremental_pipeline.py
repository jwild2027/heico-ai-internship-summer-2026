from __future__ import annotations

from pathlib import Path

from tiff.incremental_pipeline import (
    IncrementalPipelineConfig,
    build_incremental_commands,
    config_from_file,
    format_command,
    merge_config,
)


def test_build_incremental_commands_skips_when_no_changes():
    config = IncrementalPipelineConfig(run_backend_when_unchanged=False)
    commands = build_incremental_commands(config, changed_count=0)

    assert [item.name for item in commands] == ["ocr_changed_tiffs", "backend_pipeline"]
    assert commands[0].skip_reason == "No changed TIFF files."
    assert "No changed TIFF files" in str(commands[1].skip_reason)


def test_build_incremental_commands_runs_backend_when_requested():
    config = IncrementalPipelineConfig(run_backend_when_unchanged=True, run_ocr=False)
    commands = build_incremental_commands(config, changed_count=0)

    assert len(commands) == 1
    assert commands[0].name == "backend_pipeline"
    assert commands[0].skip_reason is None
    assert "scripts/run_tiff_backend_pipeline.py" in commands[0].command


def test_build_incremental_commands_includes_ocr_for_changed_files():
    config = IncrementalPipelineConfig(tesseract_cmd="C:/Tesseract/tesseract.exe")
    commands = build_incremental_commands(config, changed_count=3)
    ocr = commands[0]

    assert ocr.name == "ocr_changed_tiffs"
    assert "--input-list" in ocr.command
    assert "--tesseract-cmd" in ocr.command


def test_config_from_file_reads_incremental_values(tmp_path: Path):
    config_path = tmp_path / "local_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "tiff_root: local_data/real_tiffs",
                "incremental_state_db: local_data/db/state.db",
                "changed_tiffs_path: local_data/changed.txt",
                "scan_db_path: local_data/db/scans.db",
                "json_scan_dir: local_data/json_scans",
                "db_path: local_data/db/search.db",
                "embed_model: bge-test:latest",
                "tesseract_cmd: C:/Tesseract/tesseract.exe",
                "incremental_hash_mode: sha256",
            ]
        ),
        encoding="utf-8",
    )

    config = config_from_file(config_path)

    assert config.root == "local_data/real_tiffs"
    assert config.state_db_path == "local_data/db/state.db"
    assert config.changed_list_path == "local_data/changed.txt"
    assert config.scan_db_path == "local_data/db/scans.db"
    assert config.json_dir == "local_data/json_scans"
    assert config.search_db_path == "local_data/db/search.db"
    assert config.embed_model == "bge-test:latest"
    assert config.tesseract_cmd == "C:/Tesseract/tesseract.exe"
    assert config.hash_mode == "sha256"


def test_merge_config_keeps_none_values_from_overriding():
    base = IncrementalPipelineConfig(root="original", run_ocr=True)
    merged = merge_config(base, root=None, run_ocr=False)

    assert merged.root == "original"
    assert merged.run_ocr is False


def test_format_command_quotes_spaces():
    assert format_command(("python", "script.py", "two words")) == 'python script.py "two words"'


def test_run_changed_detection_preview_does_not_commit_state(tmp_path: Path):
    from tiff.incremental_pipeline import run_changed_detection
    from tiff.incremental_state import read_changed_list

    root = tmp_path / "tiffs"
    root.mkdir()
    file_path = root / "a.tif"
    file_path.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed_list = tmp_path / "changed.txt"
    config = IncrementalPipelineConfig(root=str(root), state_db_path=str(state_db), changed_list_path=str(changed_list))

    preview = run_changed_detection(config, commit_state=False)
    actual = run_changed_detection(config, commit_state=True)

    assert preview.summary.new_files == 1
    assert read_changed_list(changed_list) == (str(file_path),)
    assert actual.summary.new_files == 1
