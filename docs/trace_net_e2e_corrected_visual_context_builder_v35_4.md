# TRACE-Net Corrected Visual Context Builder v35.4

This module consumes the calibrated cascade route brain v35.3 decisions and builds stored visual context only for pages marked `visual_context_eligible`.

It intentionally does not process fishnet-only visual review candidates as full visual-context pages. Those pages remain in the review/retry queue. This prevents broad dual-route visual candidates from inflating the image route.

Safety contract:

- no source-truth mutation
- no answer permission
- no database writes
- no LLaVA/Gemma calls
- visual context is guidance only

Primary outputs:

- `trace_net_corrected_visual_context_builder_v35_4.json`
- `trace_net_corrected_visual_context_cards_v35_4.jsonl`
- `trace_net_corrected_visual_prompt_context_v35_4.jsonl`
- `trace_net_fishnet_visual_review_candidates_skipped_v35_4.jsonl`
