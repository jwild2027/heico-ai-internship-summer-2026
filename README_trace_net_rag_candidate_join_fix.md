# TRACE-Net RAG Candidate Index v1.1 - refined table tile join fix

This patch fixes the derived-context join between Stage 5b RAG eligibility
records and `table_tile_text_refined_records.jsonl`.

The previous v1 indexer was safe, but derived-context chunks could say:

```text
No refined table tile text record could be joined for this derived context candidate.
```

because Stage 5/Eligibility IDs may look like:

```text
table_tile_text_refined:t_p_120_1176_p000003:tile_t_p_120_1176_p000003_tile_001
```

while the refined tile text record stores:

```text
t_p_120_1176_p000003_tile_001
```

v1.1 normalizes those IDs and adds page/tile-index fallbacks.

## Files changed

```text
tiff/trace_net_rag_candidate_index.py
tiff/trace_net_rag_candidate_index_quality.py
tests/unit/test_tiff_trace_net_rag_candidate_index.py
README_trace_net_rag_candidate_join_fix.md
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_rag_candidate_index.py \
  tests/unit/test_tiff_trace_net_rag_candidate_index_quality.py \
  -q
```

Expected:

```text
..... [100%]
5 passed
```

## Rebuild the candidate index

```bash
python scripts/build_trace_net_rag_candidate_index.py --open
```

## Quality check

The old quality command still works:

```bash
python scripts/check_trace_net_rag_candidate_index_quality.py \
  --write-json \
  --min-records 931 \
  --min-pages 509 \
  --min-source-candidates 509 \
  --min-verified-part-candidates 360 \
  --min-derived-candidates 60 \
  --max-unsafe-candidate-records 0 \
  --max-empty-text-records 0 \
  --max-table-candidate-indexed-records 0 \
  --max-table-tiles-indexed-records 0
```

New optional stricter checks:

```bash
python scripts/check_trace_net_rag_candidate_index_quality.py \
  --write-json \
  --min-records 931 \
  --min-pages 509 \
  --min-source-candidates 509 \
  --min-verified-part-candidates 360 \
  --min-derived-candidates 60 \
  --min-derived-joined-records 60 \
  --max-derived-unjoined-records 0 \
  --max-unsafe-candidate-records 0 \
  --max-empty-text-records 0 \
  --max-table-candidate-indexed-records 0 \
  --max-table-tiles-indexed-records 0
```

## New summary fields

```text
derived_context_joined_records
derived_context_unjoined_records
derived_context_catalog_supported_records
```

After the fix, derived context chunks should include catalog-supported parts,
unsupported candidates, index labels, tile IDs, and extracted tile text instead
of the missing-join placeholder.
