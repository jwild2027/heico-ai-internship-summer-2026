# TRACE-Net Page Element Registry v1

This patch adds Step 14: a read-only page element registry for TRACE-Net.

The registry creates one per-page intake/control record that summarizes:

- page traits
- detected page elements
- recommended extraction routes
- fishnet retry plan
- OCR/catalog/graph/source/citation comparison targets
- trust assignment policy
- graph attachment plan

It does not mutate Postgres, Qdrant, source TIFFs, OCR, trust, citations, or source truth.

## Files

```text
tiff/trace_net_page_element_registry_v1.py
scripts/build_trace_net_page_element_registry_v1.py
scripts/check_trace_net_page_element_registry_v1_quality.py
tests/unit/test_trace_net_page_element_registry_v1.py
tests/unit/test_trace_net_page_element_registry_v1_quality.py
tests/unit/test_trace_net_page_element_registry_v1_script_imports.py
README_trace_net_page_element_registry_v1.md
```

## Build

```bash
python scripts/build_trace_net_page_element_registry_v1.py \
  --page-profiles local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --context-helpers local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json \
  --baseline-checkpoint local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --evidence-consensus-summary local_data/organization/trace_net/evidence_consensus/evidence_consensus_summary.json \
  --image-recognition-quality local_data/organization/image_recognition/page_image_recognition_quality.json \
  --output-dir local_data/organization/trace_net/page_element_registry \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-pages-with-detected-elements 509 \
  --min-pages-with-recommended-routes 509 \
  --min-pages-with-fishnet 509 \
  --min-pages-with-comparison-targets 509 \
  --min-pages-with-graph-attachment-plan 509 \
  --min-pages-with-trust-policy 509 \
  --min-pages-with-source-trace 509 \
  --min-pages-with-ocr 495 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_page_element_registry_v1_quality.py \
  --report-path local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-pages-with-detected-elements 509 \
  --min-pages-with-recommended-routes 509 \
  --min-pages-with-fishnet 509 \
  --min-pages-with-comparison-targets 509 \
  --min-pages-with-graph-attachment-plan 509 \
  --min-pages-with-trust-policy 509 \
  --min-pages-with-source-trace 509 \
  --min-pages-with-ocr 495 \
  --write-json
```

## Output directory

```text
local_data/organization/trace_net/page_element_registry/
```

Expected generated files:

```text
trace_net_page_element_registry_v1.json
trace_net_page_element_registry_v1_records.jsonl
trace_net_page_element_registry_v1_routes.jsonl
trace_net_page_element_registry_v1_graph_attachment_plan.jsonl
trace_net_core_algorithm_matrix_v1.json
trace_net_core_algorithm_matrix_v1.md
trace_net_page_element_registry_v1_summary.json
trace_net_page_element_registry_v1_manifest.json
trace_net_page_element_registry_v1_quality.json
trace_net_page_element_registry_v1.md
trace_net_page_element_registry_v1.html
```

## Safety contract

The registry can classify and route.

The registry cannot:

- answer directly
- prove claims
- mutate source truth
- override trust authority
- bypass citation requirements

It is a front-start TRACE-Net control layer that prepares future table, chart, figure, and universal fishnet work.
