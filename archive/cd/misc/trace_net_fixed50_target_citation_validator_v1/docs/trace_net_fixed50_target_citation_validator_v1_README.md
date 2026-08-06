# TRACE-Net Fixed-50 Target Citation Validator v1

Adds a read-only validator for fixed-50 `answers.jsonl` outputs.

The validator catches cases where the runner reports a citation-backed answer, but the returned citations do not actually match the explicit target part number in the question. This is important for cases like `DF250040-501`, where the loaded corpus has no source-artifact hit, but the endpoint may still return nearby/off-target citations for another part number.

## Safety contract

- Reads `answers.jsonl` only.
- Writes a validation summary JSON and per-question validation JSONL.
- Does not call the TRACE-Net endpoint.
- Does not call Ollama/Gemma.
- Does not write to Postgres, Qdrant, OpenSearch, or source-truth artifacts.
- Engram, V2/V3, and graph proximity remain guidance only; proof requires target-matching citation/source-trace records.

## Example

```bash
python3 -B scripts/validate_trace_net_fixed50_target_citation_v1.py \
  --answers /data/trace_net_runs/fixed50_trace_server_gemma_multiquery_v1/answers.jsonl \
  --summary-output /data/trace_net_runs/fixed50_trace_server_gemma_multiquery_v1/target_citation_summary_v1.json \
  --records-output /data/trace_net_runs/fixed50_trace_server_gemma_multiquery_v1/target_citation_records_v1.jsonl \
  --corpus-missing-target DF250040-501
```

Expected current behavior for the best multi-query run:

- `quality_status=PASS` for safety if there are no unsupported source-ready claims.
- `target_quality_status=WARN` if off-target citations are returned.
- `adjusted_citation_backed_count` should be lower than `raw_citation_backed_count` when off-target citations are found.

## New metrics

- `raw_citation_backed_count`: old metric; any citation counts.
- `adjusted_citation_backed_count`: raw count minus answers with off-target citations for explicit target parts.
- `target_citation_backed_count`: exact part-target questions with at least one target-matching citation.
- `safe_no_proof_count`: model safely says not found / not source-trace-ready / cannot prove.
- `corpus_missing_answer_count`: answers whose explicit target is known missing from source artifacts.
- `off_target_citation_answer_count`: citations returned, but none match the target part.
- `unsupported_claim_count`: source-ready claim without target-matching citation.
