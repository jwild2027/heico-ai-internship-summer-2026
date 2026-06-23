# TRACE-Net E2E Evidence Sufficiency Gate v1

This module reviews E2E context packs and decides whether each pack is ready for final-gate review or should remain audit-only because the evidence is insufficient.

It is intentionally conservative:

- sufficiency means **ready for final-gate review**, not answer permission;
- table/context evidence remains retrieval/ranking-only until the final gate;
- no source truth is mutated;
- no Postgres, Qdrant, OpenSearch, or upload writes occur.

Typical build:

```bash
python scripts/build_trace_net_e2e_evidence_sufficiency_gate_v1.py \
  --e2e-context-pack-builder local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json \
  --output-dir local_data/organization/trace_net/e2e_evidence_sufficiency_gate \
  --min-source-context-packs 5 \
  --min-context-packs-with-items 5 \
  --min-evidence-gate-records 5 \
  --min-sufficient-context-packs 4 \
  --min-final-gate-ready-packs 4 \
  --min-total-evidence-items 20 \
  --min-citation-ready-evidence-items 20 \
  --min-source-trace-ready-evidence-items 20 \
  --min-pages-with-evidence-items 2 \
  --min-field-count 3 \
  --max-unsafe-records 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-source-context-pack-quality-pass \
  --require-no-answer-permission \
  --quality
```

Outputs:

- `trace_net_e2e_evidence_sufficiency_gate_v1.json`
- `trace_net_e2e_evidence_sufficiency_gate_records_v1.jsonl`
- `trace_net_e2e_evidence_sufficiency_gate_v1_quality.json`
- `trace_net_e2e_evidence_sufficiency_gate_v1_inspect.md`
