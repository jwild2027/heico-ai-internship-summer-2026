# TRACE-Net Repair Planner

This patch adds a standalone TRACE-Net repair-planning layer.

TRACE-Net means:

```text
Traceable Routed Adaptive Context Extraction Network
```

The repair planner does not call Ollama, OCR, or a table model. It reads the existing cleaned visual-text records and trust-tier outputs, then decides the next action for each page.

## Inputs

```text
local_data/organization/visual_text/visual_text_extraction_clean.jsonl
local_data/organization/trust_traits/trust_trait_assertions.jsonl
local_data/organization/trust_traits/trust_trait_summary.json
```

The clean records are the primary input. The trust-trait overlay is treated as the graph-traceable state that explains why each page is or is not RAG-safe.

## Outputs

```text
local_data/organization/trace_net/repair/trace_net_repair_plan.json
local_data/organization/trace_net/repair/trace_net_repair_plan.jsonl
local_data/organization/trace_net/repair/trace_net_repair_plan_summary.json
local_data/organization/trace_net/repair/trace_net_repair_graph_nodes.json
local_data/organization/trace_net/repair/trace_net_repair_graph_edges.json
local_data/organization/trace_net/repair/trace_net_repair_plan_review.md
local_data/organization/trace_net/repair/trace_net_repair_quality.json
```

## Route logic

The planner turns trust/review traits into next actions:

```text
trust D + prompt_template_leakage
  -> clean_postprocess_route
  -> rerun_visual_prompt_route
  -> reject_visual_text_from_rag_route

trust C/D + table_expected_but_not_extracted
  -> grit_table_crop_tile_route

hallucination_risk / suspicious_phrase / unsupported part numbers
  -> ocr_graph_validation_route

trust C/D
  -> human_review_route

trust A/B
  -> rag_include_route
```

The current `grit_table_crop_tile_route` and `ocr_graph_validation_route` are planner routes, not implemented executors yet. They are placeholders for the next TRACE-Net stages.

## Run

```bash
python scripts/plan_trace_net_repairs.py --samples 25
```

Quality gate:

```bash
python scripts/check_trace_net_repair_quality.py \
  --write-json \
  --min-records 25 \
  --expect-pages 25 \
  --min-repair-needed-records 1
```

For the current 25-page visual-text pilot, a healthy planner output is expected to show many repair/review records because the current visual-text trust tiers are mostly C/D.

## Why this matters

Before this layer, the graph could say:

```text
Visual text trust tier D
Visual text needs human review
Visual text excluded from RAG
```

Now TRACE-Net can decide the next action:

```text
send to table route
rerun with safer prompt
run OCR/graph validation
queue human review
include/exclude from RAG
```

So trust traits become operational routing decisions.
