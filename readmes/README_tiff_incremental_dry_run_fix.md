# Incremental TIFF Pipeline Dry-Run Fix

This patch fixes the incremental pipeline dry-run behavior.

## Problem fixed

Before this patch, running:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --dry-run
```

could update the incremental state database. That meant a preview run could accidentally mark new TIFF files as already seen, causing the next real run to report `Changed list count: 0`.

## New behavior

Default dry-run behavior now:

```text
changed_tiffs.txt is written for inspection
state DB is not updated
commands are not executed
```

So this sequence is safe:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --dry-run
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml
```

The second command will still process the same new/changed TIFFs seen in the dry run.

## Advanced option

To intentionally let a dry run update state, use:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --dry-run --commit-state-on-dry-run
```

Most normal users should not use that option.

## Files patched

```text
tiff/incremental_state.py
tiff/incremental_pipeline.py
scripts/run_incremental_tiff_pipeline.py
tests/unit/test_tiff_incremental_state.py
tests/unit/test_tiff_incremental_pipeline.py
```

## Recommended test

```bash
python -m pytest tests/unit/test_tiff_incremental_state.py tests/unit/test_tiff_incremental_pipeline.py -q
```

Expected:

```text
14 passed
```
