# TRACE-Net Real Answer Smoke Engram Overlay Flag v1

This patch adds an explicit `--engram-answer-runner-overlay-map` flag to the normal
real answer-smoke CLI wrapper.

The flag keeps the existing real-answer smoke builder as the source of truth. When
an overlay map is supplied, the base smoke runs first. After it succeeds, the shim
builds a work-order context pack from:

- the produced `trace_net_engineering_real_answer_smoke_test_v1.json`
- the supplied Engram answer-runner overlay map

Safety contract:

- Engram overlay is behavior guidance only.
- Engram overlay is not source/manual proof.
- V2/V3 summaries and graph proximity remain route hints only.
- Manual/source claims still require current `proof_context` citations.
- No answer permission is granted by the overlay.
- No Postgres/Qdrant/OpenSearch writes are performed.

Typical usage adds the flag to the existing real smoke command:

```bash
python -B scripts/build_trace_net_engineering_real_answer_smoke_test_v1.py \
  ...existing real answer smoke args... \
  --output-dir local_data/organization/trace_net/engineering_real_answer_smoke_test_v1 \
  --engram-answer-runner-overlay-map local_data/organization/trace_net/.../trace_net_engineering_engram_answer_smoke_overlay_map_v1.json \
  --engram-overlay-min-records 1 \
  --engram-overlay-min-matched-overlays 1
```
