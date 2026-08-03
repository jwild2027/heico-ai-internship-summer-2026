# TRACE-Net Gemma Residency Launcher v2.1

## Purpose

This revision fixes the v2 launcher's hanging shutdown path while preserving the
validated Gemma-residency and safe progress-streaming work.

## Changes

- Removes every use of `fuser -k`.
- Stops only exact known 8128 and 8131 Python service command lines.
- Bounds tmux, TERM, and KILL waits.
- Refuses to kill an unknown process merely because it owns a port.
- Stops public proxy 8131 before writer 8128; starts writer first and verifies it
  before starting the proxy.
- Uses simple runtime start scripts instead of `tee` service pipelines.
- Restores and verifies Engram shadow, evidence-aware modes, final Engram
  rollout, evidence synthesis, constrained writing, and deterministic fallback.
- Converts the old v2 filename into a safe compatibility shim to v2.1.
- Leaves 8118, PostgreSQL, Qdrant, OpenSearch, and source artifacts untouched.

## Commands

Use the new launcher:

```bash
bash scripts/launch_trace_net_gemma_resident_openwebui_v2_1.sh
```

The old command is also safe after this patch:

```bash
bash scripts/launch_trace_net_gemma_resident_openwebui_v2.sh
```

For an idempotency gate, run v2.1 once and then run the compatibility command.
Both runs must end with:

```text
FULL_HEALTH_GATE=PASS
SAFE_PROGRESS_STREAM_GATE=PASS
TRACE_NET_GEMMA_RESIDENCY_LAUNCHER_V2_1=PASS
```

The second run proves that already-running services can be stopped and restarted
without hanging or losing the full writer configuration.
