# TRACE-Net Evidence Consensus Router v1.1: refined table tile text

This patch wires the refined table-tile text layer into Evidence Consensus.

New consensus layer:

```text
table_tile_text_refined
```

It reads:

```text
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_records.jsonl
```

and produces one consensus record per refined tile-text record. B-tier refined records with catalog-supported part evidence can now be included as derived context, while C-tier records remain excluded from RAG.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_evidence_consensus.py \
  tests/unit/test_tiff_trace_net_evidence_consensus_quality.py \
  -q
```

Expected:

```text
...... [100%]
6 passed
```

## Rebuild Evidence Consensus

```bash
python scripts/build_trace_net_evidence_consensus.py \
  --expect-pages 509 \
  --samples 25 \
  --open
```

## Quality gate with refined table-text requirement

For your current 120 refined tile records:

```bash
python scripts/check_trace_net_evidence_consensus_quality.py \
  --write-json \
  --min-pages 509 \
  --require-source-trace \
  --require-rag-safety \
  --min-table-tile-text-refined-records 120
```

Expected new summary fields:

```text
table_tile_text_refined_records: 120
layer_counts.table_tile_text_refined: 120
rag_action_counts.include_as_derived_context: increases by B-tier refined records
```

This does not mark C-tier refined table text as RAG-safe. It only lets refined B-tier tile text become derived context.
