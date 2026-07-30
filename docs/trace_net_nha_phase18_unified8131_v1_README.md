# TRACE-Net N18 Unified 8131 Promotion

This milestone promotes the proven NHA Engram/evidence/Gemma route onto the existing public port 8131 without changing the public model ID. Non-NHA requests continue to the full cognitive writer on port 8128. The old 8131 bridge can be restored with one command, and port 8132 is not modified.

The mixed live gate requires:

- 6 NHA requests with one accepted constrained NHA Gemma call each.
- 5 existing cognitive requests with one accepted constrained upstream Gemma call each.
- 1 synthetic benchmark request blocked with zero model and source access.
- 6 streaming and 6 non-streaming requests.
- No production graph writes or source mutation.

Promotion:

```bash
bash scripts/run_trace_net_nha_phase18_unified8131_server_gate_v1.sh
```

Rollback:

```bash
bash scripts/launch_trace_net_cognitive_openwebui_nha_unified_v1.sh rollback
```

## N18.1 mixed-gate policy correction

The public promotion gate distinguishes three upstream outcomes:

- `accepted`: Gemma returned a validated constrained rewrite.
- `safe_fallback`: Gemma returned an answer, the safety validator rejected the rewrite, and TRACE-Net released the already-validated deterministic Phase 3 answer.
- `invalid`: the model was skipped, timed out, failed, or produced an unknown runtime state.

Both `accepted` and `safe_fallback` prove a completed real Gemma call while preserving fail-closed behavior. The gate still rejects skipped calls, timeouts, HTTP/model failures, missing public evidence, or invalid final formatting. IPL/table questions follow their existing public contract and require `## Answer` plus `## Evidence`; they do not invent a `## Limits` requirement when the golden contract marks limits as optional.

