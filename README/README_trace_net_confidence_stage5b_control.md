# TRACE-Net Layer Confidence Stage 5b policy control

Stage 5b extends Stage 5a by letting the layer-specific TRACE-LC confidence policy control one additional low-risk derived evidence layer:

```text
source_trace
part_catalog
table_tile_text_refined
```

Still rule-controlled:

```text
visual_text
table_candidate
table_tiles
```

The main Evidence Consensus records are **not** overwritten. Stage 5b writes a controlled decision view under:

```text
local_data/organization/trace_net/confidence/stage5_control/
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_confidence_stage5.py \
  tests/unit/test_tiff_trace_net_confidence_stage5_control.py \
  tests/unit/test_tiff_trace_net_confidence_stage5_quality.py \
  -q
```

Expected:

```text
....... [100%]
7 passed
```

## Build Stage 5b controlled view

```bash
python scripts/build_trace_net_confidence_stage5_control.py --open
```

Expected important values:

```text
controlled_layers: ['part_catalog', 'source_trace', 'table_tile_text_refined']
policy_controlled_records: 993
source_trace_policy_A_records: 509
part_catalog_policy_A_records: 362
table_tile_text_refined_controlled_records: 120
table_tile_text_refined_derived_context_records: >= 30
unsafe_stage5_rag_include_records: 0
table_candidate_direct_rag_records: 0
visual_text_controlled_records: 0
```

## Quality gate

```bash
python scripts/check_trace_net_confidence_stage5_quality.py \
  --write-json \
  --min-records 1813 \
  --min-pages 509 \
  --min-policy-controlled-records 993 \
  --min-source-trace-final-A-records 509 \
  --min-part-catalog-final-A-records 360 \
  --min-table-tile-text-refined-controlled-records 120 \
  --min-table-tile-text-refined-derived-context-records 30 \
  --max-table-tile-text-refined-direct-verified-records 0 \
  --max-unsafe-stage5-rag-include-records 0 \
  --max-table-candidate-direct-rag-records 0 \
  --max-visual-text-controlled-records 0
```

## Safety policy

`table_tile_text_refined` can be policy-controlled only as derived context. It must not become direct source or verified-part evidence in this stage. That is why the quality gate checks:

```text
--max-table-tile-text-refined-direct-verified-records 0
```

This keeps table-tile text useful for retrieval context while preserving source truth and verified part evidence boundaries.
