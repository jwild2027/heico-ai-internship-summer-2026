# TRACE-Net N19 — Upstream Latency + Preservation Writer

N19 keeps the unified public `8131` architecture from N18 and improves the
remaining upstream cognitive path without changing evidence authority.

## Runtime changes

1. `trace_net_h30_phase19_route_completion_fastpath_v1.py`
   - Applies only to `exact_identifier_lookup`, `exact_table_ipl_lookup`, and
     `ata_system_discovery`.
   - Stops launching additional retrieval tunnels after a requested part/ATA and
     canonical source page are already present.
   - Allows up to two calls when the first call does not resolve a matching page.
   - Does not fabricate evidence, modify ranking, or bypass Self-RAG/CRAG.

2. `trace_net_h30_phase19_preservation_writer_v1.py`
   - Keeps the existing one-call constrained Gemma writer.
   - Gives Gemma a compact exact-copy JSON task for the already validated Phase 3
     Answer lines.
   - Evidence and Limits remain deterministic.
   - Existing post-model validation and Phase 3 fallback remain intact.

## Live N19 gate

The 12-question unified gate requires:

- 6/6 NHA Gemma answers.
- 5/5 upstream constrained Gemma outputs accepted.
- 0 upstream safe fallbacks.
- N19 fastpath and preservation telemetry present for all five upstream cases.
- Upstream average latency <= 80 seconds and maximum <= 100 seconds by default.
- 1 synthetic request blocked before any model call.
- No graph writes, source mutation, or synthetic artifact access.

Thresholds are configurable with:

- `TRACE_NET_NHA_PHASE19_UPSTREAM_AVERAGE_MAX_SECONDS`
- `TRACE_NET_NHA_PHASE19_UPSTREAM_MAXIMUM_MAX_SECONDS`
- `TRACE_NET_NHA_PHASE19_NHA_MAXIMUM_MAX_SECONDS`

## Promotion and rollback

Promotion restarts 8118/8128 with N19 enabled, then promotes the unified NHA
bridge onto 8131. A failed server gate automatically restarts the old cognitive
stack with both N19 overlays disabled.

Manual rollback disables both N19 overlays, restarts 8118/8128, and then
re-promotes the proven N18 unified NHA endpoint on 8131:

```bash
bash scripts/launch_trace_net_nha_phase19_stack_v1.sh rollback
```

## Installer v2 correction
This package supersedes the v1 installer. The N19 feature code is unchanged.
Installer edit 10 now matches the launcher's source-level double backslash used
inside the heredoc that generates the 8128 start script. The v1 preflight made
no repository changes when it reported a conflict.
