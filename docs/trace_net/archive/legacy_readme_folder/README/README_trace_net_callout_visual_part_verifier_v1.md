# TRACE-Net Callout Cleaner / Visual Part Verifier v1

This patch adds a read-only visual verification layer for technical drawings,
illustrated parts pages, callouts, and visual part candidates.

It consumes:

- `figure_chart_understanding/trace_net_figure_chart_understanding_v1.json`
- `table_cell_normalizer/trace_net_table_cell_normalizer_v1.json`
- `graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json`
- optionally `embedding_candidates/trace_net_embedding_candidates_v1.json`

It produces:

- cleaned callout candidates
- suppressed random-number candidates
- callout-to-table-row candidate links
- visual-part-to-catalog comparison records
- review flags for unverified diagrams
- graph attachment plans

The module is conservative.  Clean callouts and visual part links are retrieval
and review helpers only.  They cannot answer directly, prove claims, mutate
source truth, or bypass citation/trust/final-answer gates.

## Build

```bash
python scripts/build_trace_net_callout_visual_part_verifier_v1.py \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --graph-overlay-part-normalizer local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/callout_visual_part_verifier \
  --min-verifier-records 1 \
  --min-clean-callouts 1 \
  --min-random-numbers-suppressed 1 \
  --min-callout-to-table-row-links 1 \
  --min-catalog-verified-visual-parts 1 \
  --quality
```

If the current corpus does not produce table-linked callouts, lower the link
thresholds to zero for the first audit run.  Do not lower the safety checks.

## Quality

```bash
python scripts/check_trace_net_callout_visual_part_verifier_v1_quality.py \
  --report-path local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json \
  --min-verifier-records 1 \
  --min-clean-callouts 1 \
  --min-random-numbers-suppressed 1 \
  --min-callout-to-table-row-links 1 \
  --min-catalog-verified-visual-parts 1 \
  --write-json
```

## Safety contract

- `can_answer_directly = false`
- `can_prove_claims = false`
- `can_mutate_source_truth = false`
- `final_answer_allowed = false`
- visual output remains retrieval/review-only until OCR/catalog/graph/source,
  citation, trust authority, and final answer gates approve it.

## Outputs

```text
local_data/organization/trace_net/callout_visual_part_verifier/
  trace_net_callout_visual_part_verifier_v1.json
  trace_net_callout_visual_part_verifier_v1_records.jsonl
  trace_net_callout_visual_part_verifier_v1_callouts.jsonl
  trace_net_callout_visual_part_verifier_v1_links.jsonl
  trace_net_callout_visual_part_verifier_v1_summary.json
  trace_net_callout_visual_part_verifier_v1_manifest.json
  trace_net_callout_visual_part_verifier_v1_quality.json
  trace_net_callout_visual_part_verifier_v1.md
  trace_net_callout_visual_part_verifier_v1.html
```
