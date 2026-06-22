# TRACE-Net E2E Reasoned Response Draft v12

This module turns v11 LLM prompt contracts into deterministic, citation-grounded reasoned response drafts.

It does not call an LLM yet. It is intentionally deterministic so the next final-answer gate can test claim/citation behavior before live generation is introduced.

## Inputs

- `e2e_llm_prompt_contract/trace_net_e2e_llm_prompt_contract_v11.json`

## Outputs

- `trace_net_e2e_reasoned_response_draft_v12.json`
- `trace_net_e2e_reasoned_response_draft_v12_records_v12.jsonl`
- `trace_net_e2e_reasoned_response_draft_v12_citations_v12.jsonl`
- `trace_net_e2e_reasoned_response_draft_v12.md`

## Contract

- Uses source-truth evidence only for factual claims.
- Treats graph, summaries, vector/page profiles, route metadata, and table-route summaries as guidance only.
- Does not call an LLM.
- Does not rerun retrieval, OCR, embeddings, graph, summaries, table extraction, or source ingest.
- Does not mutate source truth or write to services.
- Keeps `answer_permission=false`, `can_answer_directly=false`, and `can_prove_claims=false` until the final answer gate.

## Example command

```bash
python scripts/build_trace_net_e2e_reasoned_response_draft_v12.py \
  --llm-prompt-contract local_data/organization/trace_net/e2e_llm_prompt_contract/trace_net_e2e_llm_prompt_contract_v11.json \
  --output-dir local_data/organization/trace_net/e2e_reasoned_response_draft \
  --min-prompt-contracts 5 \
  --min-reasoned-drafts 5 \
  --min-ready-reasoned-drafts 5 \
  --min-total-citations 15 \
  --min-drafts-with-limitations 5 \
  --min-drafts-ready-for-final-gate 5 \
  --max-graph-summary-proof-violations 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-no-answer-permission \
  --quality
```


## Hotfix v12.1

The table-text draft now pairs every mentioned page id with its matching citation marker so the final answer gate does not flag uncited page mentions.
