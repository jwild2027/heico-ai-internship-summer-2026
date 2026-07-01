# TRACE-Net Answer Context Anchor Injector v1

This module injects direct exact part-number retrieval hits into the answer context before semantic retrieval, graph/Leiden expansion, or Gemma drafting.

## Why it exists

The part-number exact retrieval probe proved that `120-29073-001` exists in trusted OCR/table artifacts. Earlier context stages were still giving Gemma weak nearby pages first. This injector makes exact-hit pages the first-class anchors for downstream graph/Leiden expansion and final answer drafting.

## Inputs

- `trace_net_part_number_exact_retrieval_probe_v1.json` from the exact retrieval probe.
- Optional graph/Leiden expander report for retained support context.
- Optional evidence enricher report for retained support context.

## Outputs

- `trace_net_answer_context_anchor_injector_v1.json`
- `trace_net_answer_context_anchor_injector_v1_prompt.txt`
- `trace_net_answer_context_anchor_injector_v1_records.jsonl`
- `trace_net_answer_context_anchor_injector_v1_records.csv`
- `trace_net_answer_context_anchor_injector_v1_citation_map.jsonl`
- `trace_net_answer_context_anchor_injector_v1_summary.json`
- `trace_net_answer_context_anchor_injector_v1_quality_check.json`

## Safety contract

- Dry-run only.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- Graph/Leiden remains ranking context only; exact source text proves part identity.

## Example

```bash
python scripts/build_trace_net_answer_context_anchor_injector_v1.py \
  --part-number-exact-retrieval-probe local_data/organization/trace_net/part_number_exact_retrieval_probe_gemma4_native_001/trace_net_part_number_exact_retrieval_probe_v1.json \
  --graph-leiden-expander local_data/organization/trace_net/answer_context_graph_leiden_expander_gemma4_native_001/trace_net_answer_context_graph_leiden_expander_v1.json \
  --evidence-enricher local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1.json \
  --output-dir local_data/organization/trace_net/answer_context_anchor_injector_gemma4_native_001 \
  --max-direct-anchors 12 \
  --max-reference-anchors 8 \
  --max-family-variants 12 \
  --require-source-quality-pass \
  --quality
```
