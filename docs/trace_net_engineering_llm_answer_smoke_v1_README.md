# TRACE-Net Engineering LLM Answer Smoke v1

H13 asks the 30 engineering smoke-test questions through a local LLM using TRACE-Net engineered context packs.

Pipeline:

1. Build the H5 engineering answer runner output for each question.
2. Load the H3 engineering answer context pack from the runner stage reports.
3. Build a strict LLM prompt containing proof context, guidance context, answer constraints, and forbidden-claim rules.
4. Ask a local Ollama model, or use `--llm-mode runner_answer` for offline harness testing.
5. Gate the LLM answer for citations, invalid citations, summary-as-proof, unsupported engineering claims, and safety counters.
6. Grade each answer as `GOOD`, `PARTIAL`, `BAD`, or `BLOCKED`.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes or uploads
- no source-truth mutation
- no answer permission
- v2 summaries are guidance only and are not proof
- LLaVA/visual text alone cannot prove part identity when source-trace proof is required

Default local LLM mode uses Ollama `/api/generate`.

Example real LLM run:

```bash
python -B scripts/build_trace_net_engineering_llm_answer_smoke_v1.py \
  --v2-summary-guidance-index local_data/organization/trace_net/v2_summary_guidance_index_v1/trace_net_v2_summary_guidance_index_v1.json \
  --image-visual-evidence-pack local_data/organization/trace_net/image_visual_evidence_nomenclature_merger_v1/trace_net_image_visual_evidence_pack_with_nomenclature_v1.json \
  --raw-ocr-nomenclature-extractor local_data/organization/trace_net/raw_ocr_nomenclature_window_extractor_v1/trace_net_raw_ocr_nomenclature_window_extractor_v1.json \
  --table-route-evidence-packager local_data/organization/trace_net/table_route_evidence_packager/trace_net_table_route_evidence_packager_v1.json \
  --table-exact-search-adapter local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json \
  --ollama-model "gemma4 26b" \
  --output-dir local_data/organization/trace_net/engineering_llm_answer_smoke_v1 \
  --max-questions 30 \
  --min-smoke-questions 30 \
  --min-llm-answered 30 \
  --min-good-or-partial-answers 20 \
  --max-bad-answers 0 \
  --max-unsupported-claims 0 \
  --max-summary-used-as-proof 0 \
  --require-quality-pass
```

Outputs:

- `trace_net_engineering_llm_answer_smoke_v1.json`
- `trace_net_engineering_llm_answer_smoke_v1_quality_check.json`
- `trace_net_engineering_llm_answer_smoke_v1_records.csv`
- `trace_net_engineering_llm_answer_smoke_v1_question_bank.jsonl`
- per-question prompt files
- per-question LLM answer files
