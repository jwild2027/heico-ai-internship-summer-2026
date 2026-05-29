# TIFF realistic query trace quality gate

This patch folds realistic user-prompt trace tests into the document graph quality gate and the main pipeline quality gate.

It protects the chain:

```text
realistic user prompt
  -> deterministic lookup or RAG retrieval
  -> page/chunk payload
  -> document graph
  -> document / ATA / source link / AI context
```

## Added quality fields

The graph quality summary now includes:

```text
realistic_query_results_present
realistic_query_total
realistic_query_pass
realistic_query_fail
realistic_query_check_total
realistic_query_check_pass
realistic_query_check_fail
realistic_query_slow_cases
```

## Recommended commands

Run the realistic trace suite first:

```bash
python scripts/run_realistic_query_trace_tests.py --config local_config.yaml --include-slow --write-json
```

Refresh graph quality:

```bash
python scripts/check_document_graph_quality.py --require-realistic-query-trace --require-slow-realistic-query-trace --write-json
python scripts/refresh_graph_quality_summary.py
```

Run the full quality gate:

```bash
python scripts/check_pipeline_quality.py --require-incremental-smoke --require-user-query-tests --require-realistic-query-trace --require-slow-realistic-query-trace
```

## Notes

- The realistic query trace result file is expected at `local_data/evals/realistic_query_trace/realistic_query_trace_results.json`.
- The slow realistic case is optional unless `--require-slow-realistic-query-trace` is passed.
- If realistic traces fail, the quality gate points you back to `scripts/run_realistic_query_trace_tests.py`.
