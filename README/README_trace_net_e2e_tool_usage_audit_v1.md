# TRACE-Net E2E Tool Usage Audit v1

Runs one TRACE-Net WebUI/OpenAI-compatible question and writes a tool-usage checklist for the returned answer.

This module distinguishes two different ideas:

- **used**: the answer/trace/citations exposed a visible signal that the tool contributed to this response.
- **available, not used**: a known local artifact exists, but this specific response did not expose a usage signal.

The goal is to prove what the current E2E/WebUI answer layer actually used before adding more features.

## Checked tools

- WebUI endpoint
- Gemma LLM
- OCR/Fishnet
- Page Context v2
- Route Dispatch
- Table Route
- Embedding/Vector
- Graph/Leiden
- Visual/Image Route
- Self-RAG
- CRAG Retry
- Final Gate

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission

## Typical run

```bash
python scripts/build_trace_net_e2e_tool_usage_audit_v1.py \
  --question "Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evidence route that is available and show source boundaries." \
  --endpoint-url http://127.0.0.1:8044/v1/chat/completions \
  --model trace-net-engineering-webui-v1 \
  --output-dir local_data/organization/trace_net/e2e_tool_usage_audit \
  --quality
```

The report is written to:

```text
local_data/organization/trace_net/e2e_tool_usage_audit/trace_net_e2e_tool_usage_audit_v1.json
```

A short checklist is also written to:

```text
local_data/organization/trace_net/e2e_tool_usage_audit/trace_net_e2e_tool_usage_audit_v1_checklist.txt
```

## Quality check

```bash
python scripts/check_trace_net_e2e_tool_usage_audit_v1_quality.py \
  --report-path local_data/organization/trace_net/e2e_tool_usage_audit/trace_net_e2e_tool_usage_audit_v1.json \
  --write-json \
  --min-checklist-count 10 \
  --min-used-tool-count 2 \
  --require-trace-net \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```

Use `--require-tool-status graph_leiden=used` or `--require-tool-status embedding_vector=used` when you want the audit to fail unless that tool was actually visible in the answer.
