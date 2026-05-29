# Realistic prompt-to-graph trace tests

This patch adds a higher-level regression suite for realistic user prompts and
retrieval-to-graph traceability.

It validates paths such as:

```text
user prompt
  -> deterministic lookup or RAG retrieval
  -> page/chunk id
  -> graph trace
  -> document / ATA / source link / AI page context / part / nomenclature
```

The local MVP does not run a production Qdrant service yet, so vector retrieval
is simulated with the same payload shape Qdrant should return later:

```json
{
  "chunk_id": "chunk_t_p_120_1176_p000495_001",
  "page_id": "t_p_120_1176_p000495",
  "score": 0.635
}
```

The backend then resolves `page_id` through the graph.

## Run fast realistic trace tests

```bash
python -m pytest tests/unit/test_tiff_realistic_query_trace_tests.py -q
python scripts/run_realistic_query_trace_tests.py --config local_config.yaml --write-json
```

## Run slow LLM/RAG trace test too

```bash
python scripts/run_realistic_query_trace_tests.py --config local_config.yaml --include-slow --write-json
```

## List cases

```bash
python scripts/run_realistic_query_trace_tests.py --list
```

## Run one case

```bash
python scripts/run_realistic_query_trace_tests.py --case vector_payload_page_000495_to_graph_context --write-json
```

## Output

```text
local_data/evals/realistic_query_trace/realistic_query_trace_results.json
```
