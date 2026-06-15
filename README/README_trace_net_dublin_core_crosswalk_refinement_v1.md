# TRACE-Net Dublin Core Crosswalk Refinement v1

This module refines the `TRACE-Net Dublin Core Crosswalk v1` output into a cleaner UI/export profile.

It separates:

- physical/document elements: OCR/source text, tables, rows, cells, visual regions, callouts, part candidates, citations
- operational TRACE-Net elements: fishnet actions, route plans, review tasks, communities, search helper records, trust/operational metadata

It also creates a stricter `dc:type` list and moves weaker signals into `trace_net:secondary_type_signals`.

## Safety

This module is read-only metadata refinement only.

It does not write Postgres, Qdrant, OpenSearch, source files, graph truth, trust records, citations, or answer records.

All refined records keep:

```text
can_answer_directly = false
can_prove_claims = false
source_truth_mutation_allowed = false
```

## Build

```bash
python scripts/build_trace_net_dublin_core_crosswalk_refinement_v1.py \
  --crosswalk local_data/organization/trace_net/dublin_core_crosswalk/trace_net_dublin_core_crosswalk_v1.json \
  --output-dir local_data/organization/trace_net/dublin_core_crosswalk_refined \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-records-with-physical-counts 509 \
  --min-records-with-operational-counts 509 \
  --min-records-with-review-summary 509 \
  --min-blank-pages-with-low-physical 14 \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_dublin_core_crosswalk_refinement_v1_quality.py \
  --report-path local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_crosswalk_refinement_v1.json \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-records-with-physical-counts 509 \
  --min-records-with-operational-counts 509 \
  --min-records-with-review-summary 509 \
  --min-blank-pages-with-low-physical 14 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/dublin_core_crosswalk_refined/
  trace_net_dublin_core_crosswalk_refinement_v1.json
  trace_net_dublin_core_refined_pages_v1.jsonl
  trace_net_dublin_core_refined_documents_v1.jsonl
  trace_net_dublin_core_crosswalk_refinement_v1_summary.json
  trace_net_dublin_core_crosswalk_refinement_v1_quality.json
  trace_net_dublin_core_crosswalk_refinement_v1_manifest.json
  trace_net_dublin_core_crosswalk_refinement_v1.md
  trace_net_dublin_core_crosswalk_refinement_v1.html
```
