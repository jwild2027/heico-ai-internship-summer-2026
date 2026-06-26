# TRACE-Net Engineering WebUI Answer Server v1.3

v1.3 is a quality layer over v1.2.

It fixes the remaining weak spot from the v1.2 rerun:
- if Gemma4 returns empty on search-style questions, fallback is now a clean deterministic mini-answer
- fallback no longer exposes raw `router_classifier_input_only` / fishnet scaffolding
- repair/material/diagram results are summarized as source leads
- source notes remain visible in user-facing answers

Run this server instead of v1 while testing weak spots.
