# TRACE-Net Page Query Response Dataset v1

This module builds a read-only JSON viewing dataset with one source-bound
question/response record per page from `trace_net_page_retrieval_large_eval_v2`.

The responses are deterministic and graph/source anchored. They are intended for
reviewing retrieval coverage and page summaries, not for returning final answers.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority

Typical use for first 200 pages:

```bash
python scripts/build_trace_net_page_query_response_dataset_v1.py \
  --page-retrieval-large-eval-v2 local_data/organization/trace_net/page_retrieval_large_eval_v2/trace_net_page_retrieval_large_eval_v2.json \
  --profiles-path local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/page_query_response_dataset \
  --first-pages 200 \
  --min-records 200 \
  --min-responses 200 \
  --min-blank-responses 1 \
  --min-graph-path-resolved 200 \
  --min-source-identity-resolved 200 \
  --min-qdrant-evaluated 200 \
  --max-unsafe-responses 0 \
  --max-answer-capable-responses 0 \
  --max-claim-proof-responses 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-eval-quality-pass \
  --require-no-answer-permission \
  --quality
```
