# TRACE-Net Evidence Consensus Router v1

This patch adds the missing center of TRACE-Net: a rule-based evidence consensus router.

It reads existing local artifacts and produces one consensus layer that answers, per page/evidence layer:

- OCR support?
- Graph support?
- Part catalog support?
- Source traceable?
- Hallucination / leakage risk?
- Trust tier?
- RAG action?
- Repair action?

The router does not call Ollama, OCR engines, Leiden, PaddleOCR, or any external service.

## Files added

```text
tiff/trace_net_evidence_consensus.py
tiff/trace_net_evidence_consensus_quality.py
scripts/build_trace_net_evidence_consensus.py
scripts/check_trace_net_evidence_consensus_quality.py
tests/unit/test_tiff_trace_net_evidence_consensus.py
tests/unit/test_tiff_trace_net_evidence_consensus_quality.py
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_evidence_consensus.py \
  tests/unit/test_tiff_trace_net_evidence_consensus_quality.py \
  -q
```

## Build consensus

```bash
python scripts/build_trace_net_evidence_consensus.py \
  --expect-pages 509 \
  --samples 25 \
  --open
```

## Quality gate

```bash
python scripts/check_trace_net_evidence_consensus_quality.py \
  --write-json \
  --min-pages 509 \
  --require-source-trace \
  --require-rag-safety \
  --require-visual-consensus \
  --require-table-tile-consensus
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

## Trust and routing policy

The router treats source traceability as mandatory for RAG inclusion.

```text
A = source-backed / RAG-safe evidence
B = usable derived context
C = review needed
D = reject from RAG
```

For v1, the router is page/layer level:

```text
page + source_trace
page + visual_text
page + table_candidate
page + table_tiles
```

Later v2 can add claim-level consensus:

```text
part-number claims
table-row claims
figure-label claims
warning/note claims
nomenclature claims
```
