# TRACE-Net OpenSearch Adapter v1

This patch builds a safe local OpenSearch document set from TRACE-Net artifacts.
It does not require a running OpenSearch server and does not write to OpenSearch.
The generated JSONL/bulk NDJSON output can be reviewed first, then used by a
future incremental OpenSearch uploader.

## Safety contract

The adapter indexes only safe/searchable TRACE-Net records:

- `source_text_evidence`
- `verified_part_evidence`
- `source_evidence` as retrieval/source locator records
- `derived_context` and `context_retrieval_helper` as search helpers
- page retrieval profiles as route-only records
- normalized table rows/cells as retrieval-only structured records
- clean evidence snippets when available
- Leiden community summaries as navigation helpers
- PartCandidate lineage records as navigation helpers

It blocks or excludes raw/unsafe families:

- raw OCR before filtering
- raw visual/model output
- raw table extraction before normalization
- raw feedback comments
- prompt/debug/internal text
- unsafe/untraceable records

The adapter sets every document to non-mutating and non-answering:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
```

Answer support still requires citation, source resolution, authority, and the
final answer gate.

## Files

```text
tiff/trace_net_opensearch_adapter_v1.py
scripts/build_trace_net_opensearch_adapter_v1.py
scripts/check_trace_net_opensearch_adapter_v1_quality.py
tests/unit/test_trace_net_opensearch_adapter_v1.py
tests/unit/test_trace_net_opensearch_adapter_v1_quality.py
tests/unit/test_trace_net_opensearch_adapter_v1_script_imports.py
README_trace_net_opensearch_adapter_v1.md
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_opensearch_adapter_v1.py \
  tests/unit/test_trace_net_opensearch_adapter_v1_quality.py \
  tests/unit/test_trace_net_opensearch_adapter_v1_script_imports.py \
  -q
```

## Build local OpenSearch documents

```bash
python scripts/build_trace_net_opensearch_adapter_v1.py \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --page-profiles local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --evidence-snippet-cleaner local_data/organization/trace_net/evidence_snippet_cleaner/trace_net_evidence_snippet_cleaner_v1.json \
  --context-helpers local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --graph-overlay-part-normalizer local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json \
  --output-dir local_data/organization/trace_net/opensearch_adapter \
  --index-name trace_net_safe_search_v1 \
  --min-documents 100 \
  --min-page-scoped-documents 100 \
  --require-mapping \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_opensearch_adapter_v1_quality.py \
  --report-path local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --min-documents 100 \
  --min-page-scoped-documents 100 \
  --require-mapping \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_documents_v1.jsonl
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_bulk_v1.ndjson
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_mapping_v1.json
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1_summary.json
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1_quality.json
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1_manifest.json
local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.md
```

## Next step

After this local adapter passes, the next module should be an incremental
OpenSearch uploader that reads the Step 25 orchestrator plan and upserts only
changed safe documents.
