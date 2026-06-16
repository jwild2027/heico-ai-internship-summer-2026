# TRACE-Net Fishnet Retry Refinement v1

Step 17.1 refines the raw universal fishnet retry plan into a cleaner priority/disposition layer.

The raw Step 17 plan is intentionally broad. It catches every page in the fishnet and records baseline validation, OCR availability, table validation, visual validation, graph comparison, citation checks, trust gates, and human-review routes. That is safe, but it is noisy: every page can look like it needs every retry.

This refinement layer separates those actions into:

- `baseline_validation`
- `actual_retry`
- `review_required`
- `optional_enrichment`
- `block_or_downgrade`
- `blank_handling`

## Safety contract

Fishnet refinement can route, retry, review, downgrade, or block.

It cannot:

- answer directly
- prove claims
- mutate source truth
- allow final answers
- promote retrieval-only records into evidence

## Main command

```bash
python scripts/build_trace_net_fishnet_retry_refinement_v1.py \
  --fishnet-report local_data/organization/trace_net/fishnet_retry_engine/trace_net_fishnet_retry_engine_v1.json \
  --output-dir local_data/organization/trace_net/fishnet_retry_refined \
  --require-page-count 509 \
  --min-refined-records 509 \
  --min-baseline-validation-pages 509 \
  --require-actual-retry-less-than-page-count \
  --quality
```

## Quality command

```bash
python scripts/check_trace_net_fishnet_retry_refinement_v1_quality.py \
  --report-path local_data/organization/trace_net/fishnet_retry_refined/trace_net_fishnet_retry_refinement_v1.json \
  --require-page-count 509 \
  --min-refined-records 509 \
  --min-baseline-validation-pages 509 \
  --require-actual-retry-less-than-page-count \
  --write-json
```

## Expected improvement

The raw Step 17 plan may say every page has retry actions. Step 17.1 should show fewer actual retry pages because it demotes normal validation and optional checks:

- text-heavy pages should not get actual vision retries
- confirmed blank pages should not get actual visual retries
- unknown-table pages should not get actual table-answer retries
- graph/citation/trust checks remain baseline validation

## Outputs

Generated under:

```text
local_data/organization/trace_net/fishnet_retry_refined/
```

Expected files:

```text
trace_net_fishnet_retry_refinement_v1.json
trace_net_fishnet_retry_refinement_v1_records.jsonl
trace_net_fishnet_retry_refinement_v1_actions.jsonl
trace_net_fishnet_retry_refinement_v1_routes.jsonl
trace_net_fishnet_retry_refinement_v1_summary.json
trace_net_fishnet_retry_refinement_v1_manifest.json
trace_net_fishnet_retry_refinement_v1_quality.json
trace_net_fishnet_retry_refinement_v1.md
trace_net_fishnet_retry_refinement_v1.html
```

## Next step

After this passes, use the refined fishnet plan for:

```text
Step 18: Element-to-Graph Attachment Plan v1
```
