from __future__ import annotations

from tiff.incremental_pipeline import ChangeDetectionSummary, IncrementalPipelineConfig, build_commands


def test_changed_page_backend_command_is_selected_when_requested():
    cfg = IncrementalPipelineConfig(
        config_path="local_config.yaml",
        tiff_root="local_data/sample_tiffs",
        changed_list="local_data/changed_tiffs.txt",
        db_path="local_data/db/tiff_search.db",
        embed_model="bge-m3:latest",
    )
    summary = ChangeDetectionSummary(files_seen=1, changed_paths=["local_data/sample_tiffs/00000001.tif"])
    commands = build_commands(cfg, summary, changed_page_backend=True)
    backend = [c for c in commands if c.name == "backend_pipeline"][0]
    assert backend.will_run
    assert "scripts/operations/ingestion/run_changed_page_backend_update.py" in backend.argv
    assert "--changed-list" in backend.argv
    assert "local_data/changed_tiffs.txt" in backend.argv


def test_changed_page_backend_is_not_default():
    cfg = IncrementalPipelineConfig(config_path="local_config.yaml")
    summary = ChangeDetectionSummary(files_seen=1, changed_paths=["changed.tif"])
    commands = build_commands(cfg, summary)
    backend = [c for c in commands if c.name == "backend_pipeline"][0]
    assert "scripts/operations/ingestion/run_tiff_backend_pipeline.py" in backend.argv
