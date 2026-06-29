# TRACE-Net Answer Context Engineering Pack v1

Builds a route-aware, source-traceable answer context pack from a raw-to-answer E2E smoke report.

## Purpose

This module turns retrieved evidence into a clean LLM prompt/context pack with:

- question intent and query part-number extraction
- direct evidence candidates
- nearby/similar evidence candidates
- route-aware evidence roles
- citation map back to TIFF page lineage
- strict final-answer constraints
- dry-run-only safety metadata

## Inputs

- `trace_net_raw_to_answer_e2e_smoke_native_v1.json` or compatible raw-to-answer smoke report
- sibling retrieval evidence JSONL if evidence records are not embedded in the report

## Outputs

- `trace_net_answer_context_engineering_pack_v1.json`
- `trace_net_answer_context_engineering_pack_v1_summary.json`
- `trace_net_answer_context_engineering_pack_v1_records.jsonl`
- `trace_net_answer_context_engineering_pack_v1_records.csv`
- `trace_net_answer_context_engineering_pack_v1_citation_map.jsonl`
- `trace_net_answer_context_engineering_pack_v1_violations.csv`
- `trace_net_answer_context_engineering_pack_v1_prompt.txt`
- `trace_net_answer_context_engineering_pack_v1.md`

## Safety contract

This module is read-only and dry-run-only. It does not write to Postgres, Qdrant, or OpenSearch. It does not mutate source truth. It does not grant answer permission.
