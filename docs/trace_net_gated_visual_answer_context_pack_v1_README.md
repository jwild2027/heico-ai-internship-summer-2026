# TRACE-Net Gated Visual Answer Context Pack v1

This patch bridges gated visual retrieval documents into answer/retrieval context
construction.

## Input

```text
local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/
  trace_net_gated_visual_retrieval_documents_v1_1.jsonl
```

Optional review-only input:

```text
local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/
  trace_net_gated_visual_candidate_review_documents_v1_1.jsonl
```

## Output

```text
trace_net_gated_visual_answer_context_pack_v1.jsonl
trace_net_gated_visual_answer_context_pack_v1_report.txt
summary.json
```

## Contract

Only `search_ready=true` and `review_only=false` documents are used as automatic
visual context. Review-only visual candidates are counted but not used.

The output remains a context pack, not a final answer:

```text
final_answer_allowed=false
answer_permission=false
can_answer_directly=false
can_prove_claims=false
visual_context_is_retrieval_guidance_only=true
```

## Safety

- no Ollama calls
- no LLM calls
- no OCR execution
- no database/vector/search writes
- no source-truth mutation
- no answer permission
