# TRACE-Net Cleanup Repair Executor

This patch adds the first executable TRACE-Net repair action:

```text
prompt_cleanup_repair_route -> rerun_cleanup_salvage
```

It does not call Ollama, OCR, or a table model. It reads the current clean visual-text records and TRACE-Net repair plan, then deterministically repairs prompt-template leakage and section bleed.

## Inputs

```text
local_data/organization/visual_text/visual_text_extraction_clean.jsonl
local_data/organization/trace_net/trace_net_repair_plan.jsonl
```

## Outputs

```text
local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repaired_records.jsonl
local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_summary.json
local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_review.md
local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_review.html
local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_quality.json
```

With `--apply`, it also updates:

```text
local_data/organization/visual_text/visual_text_extraction_clean.jsonl
local_data/organization/visual_text/visual_text_clean_summary.json
local_data/organization/visual_text/visual_text_clean_corpus.md
local_data/organization/visual_text/visual_text_clean_review.md
local_data/organization/visual_text/visual_text_clean_review.html
```

Backups are created by default when `--apply` is used.

## Run

```bash
python scripts/run_trace_net_cleanup_repairs.py --apply --open
```

Then quality check:

```bash
python scripts/check_trace_net_cleanup_repair_quality.py \
  --write-json \
  --min-input-records 25 \
  --min-repaired-records 1 \
  --max-remaining-prompt-template-leakage-records 0 \
  --require-applied
```

Then rebuild trust traits and repair plan:

```bash
python scripts/export_trust_trait_overlay.py --expect-records 25
python scripts/plan_trace_net_repairs.py --expect-pages 25 --samples 25
```

The expected improvement is fewer D-tier visual-text records, fewer prompt-template leakage traits, and possibly some B/C records becoming eligible for later RAG inclusion.
