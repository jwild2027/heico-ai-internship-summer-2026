# Incremental Pipeline Compatibility Fix

This patch restores backward-compatible public APIs after the safe-commit patch:

- `tiff.incremental_state.build_changed_tiff_list`
- `tiff.incremental_state.read_changed_list`
- `tiff.incremental_pipeline.build_incremental_commands`
- `tiff.incremental_pipeline.config_from_file`
- `tiff.incremental_pipeline.merge_config`
- `tiff.incremental_pipeline.format_command`
- `tiff.incremental_pipeline.run_changed_detection`

The safe-commit behavior remains in place: the new incremental pipeline still commits file state only after downstream OCR/backend work succeeds.

## Recommended test command

```bash
python -m pytest tests/unit/test_tiff_incremental_safe_commit.py tests/unit/test_tiff_incremental_pipeline_safe_commit.py tests/unit/test_tiff_incremental_state.py tests/unit/test_tiff_incremental_pipeline.py tests/unit/test_tiff_incremental_compatibility_api.py -q
```
