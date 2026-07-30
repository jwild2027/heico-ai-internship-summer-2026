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
