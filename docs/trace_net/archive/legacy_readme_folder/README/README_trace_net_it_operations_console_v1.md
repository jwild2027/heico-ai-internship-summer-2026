# TRACE-Net IT Operations Console v1

This module builds a backend/IT-facing health console for TRACE-Net. It scans local TRACE-Net artifacts, summarizes quality statuses, flags safety blockers, groups review backlogs, and writes JSON/JSONL/Markdown/HTML reports.

It is read-only. It does not mutate Postgres, Qdrant, OpenSearch, source files, graph truth, or answer artifacts.

## Purpose

The Human Review Queue catches evidence-level issues. The IT Operations Console catches project/system-level issues:

- Which stages are missing?
- Which quality files are failing?
- Are unsafe counts non-zero?
- Are source-truth mutation counts non-zero?
- Is raw feedback being passed to the LLM?
- Are retrieval-only records being allowed as answer evidence?
- Which stages have review backlogs?

## Build

```bash
python scripts/build_trace_net_it_operations_console_v1.py \
  --trace-net-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/it_operations_console \
  --max-critical-issues 0 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_it_operations_console_v1_quality.py \
  --report-path local_data/organization/trace_net/it_operations_console/trace_net_it_operations_console_v1.json \
  --max-critical-issues 0 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/it_operations_console/
  trace_net_it_operations_console_v1.json
  trace_net_it_operations_console_v1_stages.jsonl
  trace_net_it_operations_console_v1_issues.jsonl
  trace_net_it_operations_console_v1_summary.json
  trace_net_it_operations_console_v1_manifest.json
  trace_net_it_operations_console_v1_quality.json
  trace_net_it_operations_console_v1.md
  trace_net_it_operations_console_v1.html
```

## Safety rules

The console treats these as hard blockers when non-zero:

- unsafe records/results
- source-truth mutation allowance
- direct answer permission leakage
- retrieval-only records allowed as answer proof
- uncited claims
- raw feedback passed directly to an LLM
- local path leaks, raw bytes leaks, boilerplate leaks
- orphan graph edges

Review backlogs like human review or prompt-injection-flagged feedback are surfaced as review issues, not source truth.

## Corporate 5 TB fit

For a 5 TB deployment, this becomes the IT/admin backend panel that says what is healthy, what is failing, what needs review, and what should not be published.
