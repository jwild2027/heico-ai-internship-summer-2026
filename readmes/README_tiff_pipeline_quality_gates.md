# TIFF Pipeline Quality Gates

This patch adds a manifest checker for the backend pipeline.

The backend pipeline already writes:

```text
local_data/pipeline_runs/latest_backend_pipeline.json
```

This add-on reads that manifest and verifies the run is acceptable:

- pipeline status is `ok`
- all steps returned `0`
- key SQLite tables are populated
- RAG eval failures are below threshold
- manual-review eval rows are below threshold
- QA review rows are below threshold
- suspicious part/ATA rows are below threshold

## Run

```bash
python scripts/check_pipeline_quality.py
```

Outputs:

```text
local_data/pipeline_runs/latest_quality_gate.json
local_data/pipeline_runs/latest_quality_gate.html
```

## Current pilot-friendly defaults

The current pilot typically has:

```text
manual_review: 1
qa review rows: about 205
suspicious_part_ata: about 5
```

So the defaults are set to pass that current known-good state:

```text
--max-manual-review 1
--max-qa-review 250
--max-suspicious-part-ata 10
```

For stricter CI-style behavior, use:

```bash
python scripts/check_pipeline_quality.py --strict --max-manual-review 0 --max-qa-review 0
```

## Why this matters

The manifest tells you what happened. The quality gate tells you whether the run
is good enough to trust or needs review before moving forward.
