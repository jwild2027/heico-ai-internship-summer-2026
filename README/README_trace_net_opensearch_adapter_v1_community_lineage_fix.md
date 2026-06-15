# TRACE-Net OpenSearch Adapter v1 Community Lineage Fix

This patch fixes a safe-indexing issue where a small number of Leiden community summary documents could be created without a single `page_id` or `source_page_ids` lineage.

The adapter now:

- derives community `source_page_ids` from `node_membership` when the community summary does not carry `page_ids` directly;
- skips community summaries that still have no page lineage after derivation;
- keeps community documents retrieval-only and navigation-only;
- keeps OpenSearch as a search/index layer, not a source-truth layer.

Safety behavior remains unchanged:

- no Postgres writes;
- no Qdrant writes;
- no OpenSearch writes;
- no answer authority granted;
- no source-truth mutation allowed.

Run tests:

```bash
python -m pytest \
  tests/unit/test_trace_net_opensearch_adapter_v1.py \
  tests/unit/test_trace_net_opensearch_adapter_v1_quality.py \
  tests/unit/test_trace_net_opensearch_adapter_v1_script_imports.py \
  -q
```

Then rebuild the adapter with the same Step 26 command.
