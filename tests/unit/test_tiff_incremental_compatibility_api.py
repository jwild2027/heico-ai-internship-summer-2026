from __future__ import annotations

from pathlib import Path

from tiff.incremental_state import build_changed_tiff_list, read_changed_list
from tiff.incremental_pipeline import IncrementalPipelineConfig, build_incremental_commands, format_command


def test_legacy_build_changed_tiff_list_api_still_commits_by_default(tmp_path: Path):
    root = tmp_path / "tiffs"
    root.mkdir()
    target = root / "a.tif"
    target.write_bytes(b"one")
    state_db = tmp_path / "state.db"
    changed = tmp_path / "changed.txt"

    first = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed)
    second = build_changed_tiff_list(root=root, state_db_path=state_db, changed_list_path=changed)

    assert first.summary.new_files == 1
    assert second.summary.unchanged_files == 1
    assert read_changed_list(changed) == []


def test_legacy_incremental_command_api_still_exists():
    cfg = IncrementalPipelineConfig(run_backend_when_unchanged=True, run_ocr=False)
    commands = build_incremental_commands(cfg, changed_count=0)
    assert [c.name for c in commands] == ["backend_pipeline"]
    assert "scripts/run_tiff_backend_pipeline.py" in commands[0].command
    assert format_command(("python", "script.py", "two words")) == 'python script.py "two words"'
