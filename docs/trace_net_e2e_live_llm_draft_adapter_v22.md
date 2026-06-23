# TRACE-Net E2E Live LLM Draft Adapter v22

This module connects the cleaned v21 prompt contracts to an LLM draft adapter.

The adapter supports two modes:

- `simulate`: deterministic local draft generation for tests and offline contract validation.
- `ollama`: real OpenAI-compatible Ollama call, intended for `gemma4:26b`.

The output is **not** a final answer. It is a draft that must be checked by the next final-gate stage before WebUI final-answer use.

## Authority contract

- Source-truth evidence is the only proof authority.
- Graph / Leiden guidance remains navigation-only.
- v2 summaries remain meaning/compression guidance-only.
- Aggregation and cap metadata must be disclosed when results are capped.
- LLM reasoning fields are metadata only; they are not passed as answer text.
- Query-time draft generation does not scan the raw 5TB corpus, rebuild graph, rerun OCR, mutate source truth, or write to services.

## Example live command

```bash
python scripts/build_trace_net_e2e_live_llm_draft_adapter_v22.py \
  --live-llm-prompt-contract local_data/organization/trace_net/e2e_live_llm_prompt_contract/trace_net_e2e_live_llm_prompt_contract_v21.json \
  --output-dir local_data/organization/trace_net/e2e_live_llm_draft_adapter \
  --llm-mode ollama \
  --llm-base-url http://127.0.0.1:11434/v1 \
  --llm-model gemma4:26b \
  --llm-api-key ollama \
  --temperature 0 \
  --request-timeout 180 \
  --min-prompt-contracts 5 \
  --min-llm-drafts 5 \
  --min-drafts-ready-for-final-gate 5 \
  --min-drafts-with-nonempty-content 5 \
  --min-source-truth-supported-prompts 5 \
  --min-successful-llm-calls 5 \
  --min-live-llm-calls 5 \
  --max-llm-call-errors 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-no-answer-permission \
  --quality
```
