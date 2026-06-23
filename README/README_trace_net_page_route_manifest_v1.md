# TRACE-Net Page Route Manifest v1

Builds a page-level routing manifest from TRACE-Net artifact evidence, metadata/source pages, and optional page ink route evidence.

The manifest is advisory and read-only. It does not answer user questions, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Inputs

Required:

- `trace_net_artifact_detector_v1.json`

Optional:

- `trace_net_page_ink_route_evidence_v1.json`

## Output

`local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1.json`

Each route card includes:

- `page_id`
- `source_page_id`
- `page_number`
- `primary_route`
- `secondary_routes`
- `blank_score`
- `text_score`
- `table_score`
- `image_visual_score`
- `review_score`
- `route_confidence`
- `routing_reasons`
- `evidence_summary`
- `ink_route_integration` when ink evidence is provided

Supported primary routes:

- `table`
- `image_visual`
- `normal_text`
- `blank_candidate`
- `review`

## Ink integration behavior

Ink evidence can boost an existing route and create review/disagreement signals.
It should not blindly override artifact routing.

Examples:

- artifact table + ink table = stronger table route
- artifact blank + strong ink table = review signal
- artifact image + strong ink table = conflict/review signal
- no artifacts + ink blank = stronger blank candidate

## Build

```bash
PYTHONPATH=. python scripts/build_trace_net_page_route_manifest_v1.py \
  --artifact-detector local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json \
  --page-ink-route-evidence local_data/organization/trace_net/page_ink_route_evidence/trace_net_page_ink_route_evidence_v1.json \
  --output-dir local_data/organization/trace_net/page_route_manifest \
  --min-page-route-cards 500 \
  --min-source-page-route-cards 500 \
  --min-table-route-cards 1 \
  --min-page-ink-route-evidence-cards 500 \
  --max-unsafe-route-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-artifact-detector-quality-pass \
  --require-page-ink-route-evidence-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Quality check

```bash
PYTHONPATH=. python scripts/check_trace_net_page_route_manifest_v1_quality.py \
  --report-path local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1.json \
  --min-page-route-cards 500 \
  --min-source-page-route-cards 500 \
  --min-table-route-cards 1 \
  --min-page-ink-route-evidence-cards 500 \
  --max-unsafe-route-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-artifact-detector-quality-pass \
  --require-page-ink-route-evidence-quality-pass \
  --require-no-answer-permission \
  --write-json
```
