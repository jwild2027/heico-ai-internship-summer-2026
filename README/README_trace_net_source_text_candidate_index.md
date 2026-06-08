# TRACE-Net source text candidate index v1

Adds `source_text_evidence` candidate chunks to the TRACE-Net RAG candidate index.

This extends the safe candidate pool beyond source metadata, verified part evidence, and refined table context. It reads source-trace eligible pages and joins local OCR/page-context text so natural-language search can match source-backed text.

## What changes

New/updated artifacts written by `build_trace_net_rag_candidate_index.py`:

```text
local_data/organization/trace_net/rag_candidates/rag_candidate_source_text_chunks.jsonl
local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl
local_data/organization/trace_net/rag_candidates/rag_candidate_summary.json
local_data/organization/trace_net/rag_candidates/rag_candidate_review.html
```

The new bucket is:

```text
source_text_evidence
```

It is safe for local search because it is created only from source-trace eligible pages and source-backed OCR/page-context text. It does not index raw excluded visual text, table candidate routing records, or preprocessing-only table tiles.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_rag_candidate_index.py \
  tests/unit/test_tiff_trace_net_rag_candidate_index_quality.py \
  tests/unit/test_tiff_trace_net_rag_search.py \
  tests/unit/test_tiff_trace_net_rag_search_quality.py \
  -q
```

## Rebuild candidates

```bash
python scripts/build_trace_net_rag_candidate_index.py --open
```

Then run quality. Adjust the minimum source-text count to the number printed in the summary. For the current 509-page corpus, it should normally be around the number of non-empty OCR pages.

```bash
python scripts/check_trace_net_rag_candidate_index_quality.py \
  --write-json \
  --min-records 931 \
  --min-pages 509 \
  --min-source-candidates 509 \
  --min-source-text-candidates 1 \
  --min-verified-part-candidates 360 \
  --min-derived-candidates 60 \
  --min-derived-joined-records 60 \
  --max-derived-unjoined-records 0 \
  --max-unsafe-candidate-records 0 \
  --max-empty-text-records 0 \
  --max-table-candidate-indexed-records 0 \
  --max-table-tiles-indexed-records 0
```

## Search examples

Natural-language search should now hit `source_text_evidence` records:

```bash
python scripts/search_trace_net_rag_candidates.py \
  --query "seat bottom backrest" \
  --bucket source_text_evidence,derived_context,verified_part_evidence \
  --top-k 10 \
  --open
```

Quality can require source-text results when testing natural-language queries:

```bash
python scripts/check_trace_net_rag_search_quality.py \
  --write-json \
  --min-results 1 \
  --min-source-text-results 1 \
  --max-unsafe-results 0 \
  --max-excluded-results 0
```

## Disable source-text candidates

```bash
python scripts/build_trace_net_rag_candidate_index.py --no-source-text
```
