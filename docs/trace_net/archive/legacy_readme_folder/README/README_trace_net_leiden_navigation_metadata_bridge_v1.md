# TRACE-Net Leiden Navigation Metadata Bridge v1

Read-only bridge from tightened Leiden representative profiles to retrieval/UI navigation metadata.

The bridge does not make communities proof. It writes routing-only community navigation records, retrieval navigation hints, page navigation hints, and review records. Every output has `can_answer_directly: false`, `can_prove_claims: false`, and no source-truth mutation.

## Inputs

- `local_data/organization/trace_net/leiden_representative_label_tightening/trace_net_leiden_representative_label_tightening_v1.json`

## Outputs

- `trace_net_leiden_navigation_metadata_bridge_v1.json`
- `trace_net_leiden_navigation_metadata_bridge_v1_quality.json`
- `trace_net_leiden_navigation_metadata_bridge_v1_records.jsonl`
- `trace_net_leiden_navigation_metadata_bridge_v1_page_hints.jsonl`
- `trace_net_leiden_navigation_metadata_bridge_v1.md`

## Safety

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority

## Example

```bash
python scripts/build_trace_net_leiden_navigation_metadata_bridge_v1.py \
  --leiden-representative-label-tightening local_data/organization/trace_net/leiden_representative_label_tightening/trace_net_leiden_representative_label_tightening_v1.json \
  --output-dir local_data/organization/trace_net/leiden_navigation_metadata_bridge \
  --min-community-records 229 \
  --min-retrieval-hints 200 \
  --min-page-navigation-hints 223 \
  --max-review-only-communities 6 \
  --max-low-confidence-communities 2 \
  --max-missing-page-membership 6 \
  --require-label-tightening-quality-pass \
  --require-no-answer-permission \
  --quality
```
