# TRACE-Net Artifact Detector v1

`trace_net_artifact_detector_v1` is the first layer of the explicit routing stack. It inventories existing TRACE-Net JSON artifacts, extracts page/table evidence from their card arrays, and optionally parses a ResCarta/METS `metadata.zip` so source pages can be used as route examples.

It is read-only and advisory only:

- no answer permission
- no claim-proof authority
- no source-truth mutation
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes

## Inputs

- `--artifact-root`: root directory or JSON artifact file to scan. Defaults to `local_data/organization/trace_net`.
- `--metadata-zip`: optional ResCarta/METS metadata zip. The user-provided `metadata(2).zip` follows this shape: `metadata.xml` plus page TIFF files such as `00000001.tif`, `00000002.tif`, etc.

## Outputs

Default output directory:

```text
local_data/organization/trace_net/artifact_detector
```

Files:

```text
trace_net_artifact_detector_v1.json
trace_net_artifact_detector_v1_quality.json
trace_net_artifact_detector_v1_summary.json
trace_net_artifact_detector_v1_manifest.json
trace_net_artifact_detector_v1_artifact_cards.jsonl
trace_net_artifact_detector_v1_page_artifact_cards.jsonl
trace_net_artifact_detector_v1_source_page_cards.jsonl
```

## Build

```bash
python scripts/build_trace_net_artifact_detector_v1.py \
  --artifact-root local_data/organization/trace_net \
  --metadata-zip /path/to/metadata.zip \
  --output-dir local_data/organization/trace_net/artifact_detector \
  --max-json-files-scanned 25000 \
  --min-artifact-cards 1 \
  --min-page-artifact-cards 1 \
  --min-source-page-cards 1 \
  --max-unsafe-artifact-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-metadata-pages \
  --require-no-answer-permission \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_artifact_detector_v1_quality.py \
  --report-path local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json \
  --min-artifact-cards 1 \
  --min-page-artifact-cards 1 \
  --min-source-page-cards 1 \
  --max-unsafe-artifact-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-metadata-pages \
  --require-no-answer-permission \
  --write-json
```

## What it detects

Artifact cards include:

- artifact key
- path
- schema version
- quality status
- status
- known card-array counts
- page IDs sampled from cards
- table IDs sampled from cards
- evidence category such as `table`, `image_visual`, `ocr_text`, `human_review`
- routing safety flags

Page artifact cards join evidence by page ID and include counts like:

- table evidence artifact count
- image/visual evidence artifact count
- OCR/text evidence artifact count
- human-review evidence artifact count

Source page cards from metadata zip include:

- page number
- page aliases like `metadata_page_000013`, `p000013`, `00000013`, `00000013.tif`
- file ID
- image filename
- checksum/size where available

## Why this exists

Before this module, TRACE-Net routing was implicit: a page was considered table/image/text if downstream artifacts happened to include that page. This detector makes the evidence inventory explicit. The next layer should be `trace_net_page_route_manifest_v1`, which combines this artifact inventory with OCR/text and ink-detection signals into a route decision.
