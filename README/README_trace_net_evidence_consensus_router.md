# TRACE-Net Evidence Consensus Router v1

This patch adds the missing TRACE-Net decision layer:

```text
Evidence Output
  -> Cleanup / Normalization
  -> Evidence Consensus Router
      -> OCR support?
      -> Graph support?
      -> Part catalog support?
      -> Source traceable?
      -> Hallucination risk?
  -> Trust tier
  -> RAG action
  -> Repair action
```

The router does not call Ollama, OCR, Leiden, PaddleOCR, or table models. It reads existing artifacts and creates page/layer-level consensus records.

## New files

```text
tiff/trace_net_evidence_consensus.py
tiff/trace_net_evidence_consensus_quality.py
scripts/build_trace_net_evidence_consensus.py
scripts/check_trace_net_evidence_consensus_quality.py
tests/unit/test_tiff_trace_net_evidence_consensus.py
tests/unit/test_tiff_trace_net_evidence_consensus_quality.py
README_trace_net_evidence_consensus_router.md
```

## Inputs

Defaults:

```text
local_data/organization/export/page_index.json
local_data/organization/export/part_tree.json
local_data/organization/visual_text/visual_text_extraction_clean.jsonl
local_data/organization/trust_traits/trust_trait_assertions.jsonl
local_data/organization/table_extraction/all_page_scan/table_candidate_plan.jsonl
local_data/organization/table_extraction/table_tile_plan.jsonl
local_data/organization/communities/community_algorithm_policy.json
```

## Outputs

```text
local_data/organization/trace_net/evidence_consensus/evidence_consensus_records.jsonl
local_data/organization/trace_net/evidence_consensus/evidence_consensus_summary.json
local_data/organization/trace_net/evidence_consensus/evidence_consensus_graph_nodes.json
local_data/organization/trace_net/evidence_consensus/evidence_consensus_graph_edges.json
local_data/organization/trace_net/evidence_consensus/evidence_consensus_review.md
local_data/organization/trace_net/evidence_consensus/evidence_consensus_review.html
local_data/organization/trace_net/evidence_consensus/evidence_consensus_quality.json
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_evidence_consensus.py \
  tests/unit/test_tiff_trace_net_evidence_consensus_quality.py \
  -q
```

## Build consensus records

```bash
python scripts/build_trace_net_evidence_consensus.py \
  --expect-pages 509 \
  --open
```

## Quality gate

```bash
python scripts/check_trace_net_evidence_consensus_quality.py \
  --write-json \
  --min-pages 509 \
  --require-source-trace
```

Optional stricter checks:

```bash
python scripts/check_trace_net_evidence_consensus_quality.py \
  --write-json \
  --min-pages 509 \
  --require-source-trace \
  --min-visual-text-records 25 \
  --min-table-tile-records 286
```

Use the `--min-table-tile-records` number from the latest `table_tile_summary.json` if it differs.

## Evidence layers emitted

```text
source_trace
part_catalog
visual_text
table_candidate
table_tiles
```

## Trust/RAG behavior

The router keeps the project safety rule:

```text
Source tracing and exact lookup use deterministic graph traversal.
Derived visual/table evidence must pass consensus before it can enter RAG.
D-tier or source-untraceable records cannot be RAG-included.
```

Example decisions:

```text
source_trace + source_verified -> trust A/B, include_as_source_evidence
visual_text + trust C -> exclude_from_rag, OCR/graph validation or human review
table_candidate -> exclude_until_table_tiles_exist, run table crop/tile
table_tiles -> exclude_until_table_text_exists, run table tile OCR
part_catalog + page mention/source -> trust A, include_as_verified_part_evidence
```

## Why this matters

Before this patch, evidence routing existed in multiple places:

```text
visual cleanup
trust traits
repair planner
table graph/layout gates
algorithm policy
```

This patch creates one explicit, inspectable consensus layer that future TRACE-Net code can read before allowing evidence into RAG.
