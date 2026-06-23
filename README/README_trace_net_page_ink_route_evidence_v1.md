# TRACE-Net Page Ink Route Evidence v1

`trace_net_page_ink_route_evidence_v1` adds direct page-pixel evidence for routing. It reads a Page Route Manifest and source page images, then writes one ink evidence card per page.

It computes lightweight deterministic visual features:

- ink density
- blank-space ratio
- horizontal line count
- vertical line count
- line-intersection count
- connected-component counts
- blank likelihood
- text likelihood
- table-grid likelihood
- diagram likelihood
- ink-primary route

The module is read-only. It cannot answer, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Build

```bash
PYTHONPATH=. python scripts/build_trace_net_page_ink_route_evidence_v1.py \
  --page-route-manifest local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1.json \
  --metadata-zip local_data/source/metadata/metadata.zip \
  --output-dir local_data/organization/trace_net/page_ink_route_evidence \
  --min-ink-evidence-cards 500 \
  --min-source-page-ink-evidence-cards 500 \
  --min-image-analyzed-cards 500 \
  --max-image-read-error-cards 0 \
  --max-unsafe-ink-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-page-route-manifest-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Quality

```bash
PYTHONPATH=. python scripts/check_trace_net_page_ink_route_evidence_v1_quality.py \
  --report-path local_data/organization/trace_net/page_ink_route_evidence/trace_net_page_ink_route_evidence_v1.json \
  --min-ink-evidence-cards 500 \
  --min-source-page-ink-evidence-cards 500 \
  --min-image-analyzed-cards 500 \
  --max-image-read-error-cards 0 \
  --max-unsafe-ink-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-page-route-manifest-quality-pass \
  --require-no-answer-permission \
  --write-json
```

## Purpose

This artifact feeds the next routing upgrade:

```text
OCR/text evidence
+ ink detection evidence
+ TRACE-Net artifact evidence
= page route decision
```
