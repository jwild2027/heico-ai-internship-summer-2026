# TRACE-Net Page Query Response Source Cross-Reference v1

Read-only cross-reference artifact for the Page Query Response Dataset.

It verifies that each page-level question/response record points to the expected
TIFF entry in the metadata ZIP and METS `metadata.xml` file. It computes ZIP
entry SHA-1 checksums and compares them with METS checksums, checks sizes, and
confirms that the response text includes the page and source-entry anchors.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

Example:

```bash
python scripts/build_trace_net_page_query_response_source_cross_reference_v1.py \
  --page-query-response-dataset local_data/organization/trace_net/page_query_response_dataset/trace_net_page_query_response_dataset_v1.json \
  --metadata-zip "$METADATA_ZIP" \
  --output-dir local_data/organization/trace_net/page_query_response_source_cross_reference \
  --first-pages 200 \
  --min-records 200 \
  --min-responses 200 \
  --min-zip-entry-resolved 200 \
  --min-mets-file-entry-resolved 200 \
  --min-checksum-verified 200 \
  --min-size-matches 200 \
  --min-response-page-anchors 200 \
  --min-response-source-entry-anchors 200 \
  --min-blank-answer-cross-references 1 \
  --max-missing-zip-entries 0 \
  --max-missing-mets-entries 0 \
  --max-checksum-mismatches 0 \
  --max-size-mismatches 0 \
  --max-wrong-source-entries 0 \
  --max-unsafe-responses 0 \
  --max-answer-capable-responses 0 \
  --max-claim-proof-responses 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-dataset-quality-pass \
  --require-metadata-xml \
  --require-no-answer-permission \
  --quality
```
