# TRACE-Net E2E Final Answer Gate v13

`trace_net_e2e_final_answer_gate_v13` validates v12 reasoned response drafts before they are wired into a WebUI-facing final answer endpoint.

## Purpose

This stage checks that answer-like drafts are still grounded in source-truth evidence and safe to expose as final-gated drafts. It does not make new factual claims, call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph artifacts, rerun table extraction, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Inputs

- `local_data/organization/trace_net/e2e_reasoned_response_draft/trace_net_e2e_reasoned_response_draft_v12.json`

## Outputs

- `trace_net_e2e_final_answer_gate_v13.json`
- `trace_net_e2e_final_answer_gate_records_v13.jsonl`
- `trace_net_e2e_final_answer_gate_citations_v13.jsonl`
- `trace_net_e2e_final_answer_gate_v13.md`

## Checks

The final gate validates:

- every draft is ready for final gate;
- every citation is citation-ready;
- every citation is source-trace-ready;
- citations use source-truth evidence authority;
- answer text contains citation markers;
- answer text does not mention evidence values/pages without citation markers;
- graph, summary, vector, route, and table-route guidance are not used as proof;
- unsupported physical part descriptions are blocked;
- limitations are present when evidence is incomplete;
- answer permission, direct answer authority, claim-proof authority, and source-truth mutation remain blocked.

## Contract

The output is ready for WebUI endpoint integration, but still keeps:

- `answer_permission=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`

The later endpoint may display these as final-gated draft answers, but it must not claim proof beyond the cited source-truth evidence.
