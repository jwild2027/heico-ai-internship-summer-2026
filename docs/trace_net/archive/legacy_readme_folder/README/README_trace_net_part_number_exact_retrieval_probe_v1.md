# TRACE-Net Part Number Exact Retrieval Probe v1

Dry-run context-engineering module for exact part-number questions.

## Purpose

The probe searches trusted local artifacts directly for a queried part number before semantic retrieval, graph expansion, or LLM answer drafting. This prevents exact part-number questions from being answered from weak similar pages when exact OCR/table evidence exists elsewhere.

## Trusted inputs

- OCR route scan pack
- Table exact search adapter
- Table route evidence package
- Page context v2
- Normalized table values, when available

## Outputs

- `trace_net_part_number_exact_retrieval_probe_v1.json`
- exact-hit JSONL
- family-variant JSONL
- context seed prompt
- CSV summary records
- quality check JSON

## Safety

This module is dry-run only. It does not write to Postgres, Qdrant, or OpenSearch. It grants no answer permission and does not mutate source truth.

## Key rule

Exact OCR/table/source text can become direct evidence. Query text, prompt text, citation labels, and metadata do not prove part identity.
