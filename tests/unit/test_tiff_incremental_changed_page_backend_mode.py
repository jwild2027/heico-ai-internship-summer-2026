from __future__ import annotations

from tiff.incremental_pipeline import IncrementalPipelineConfig, build_commands
from tiff.incremental_state import ChangeDetectionSummary


def test_changed_page_backend_mode_uses_update_script_for_changed_files():
    cfg = IncrementalPipelineConfig(backend_mode="changed-pages", changed_list="local_data/changed_tiffs.txt")
    summary = ChangeDetectionSummary(files_seen=1, new_files=1, changed_paths=["a.tif"])

    commands = build_commands(cfg, summary)
    backend = [cmd for cmd in commands if cmd.name == "backend_pipeline"][0]

    assert backend.skip_reason is None
    assert "scripts/update_changed_page_backend.py" in backend.argv
    assert "--changed-list" in backend.argv


def test_full_backend_mode_still_uses_full_backend_pipeline():
    cfg = IncrementalPipelineConfig(backend_mode="full")
    summary = ChangeDetectionSummary(files_seen=1, new_files=1, changed_paths=["a.tif"])

    commands = build_commands(cfg, summary)
    backend = [cmd for cmd in commands if cmd.name == "backend_pipeline"][0]

    assert "scripts/run_tiff_backend_pipeline.py" in backend.argv
    assert "scripts/update_changed_page_backend.py" not in backend.argv
