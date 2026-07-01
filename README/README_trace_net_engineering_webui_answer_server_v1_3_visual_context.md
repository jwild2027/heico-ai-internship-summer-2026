# TRACE-Net Engineering WebUI Answer Server v1.3 Visual Context Integration

This patch wires the safe WebUI visual context bridge into the active v1.3 WebUI answer server wrapper.

The server now accepts `--webui-visual-context-bridge` and passes it into the Self-RAG/CRAG bridge preflight before Gemma drafting. The response trace exposes:

- `webui_visual_context_bridge_used`
- `visual_image_route_used`
- `webui_visual_context_bridge_quality_status`
- `visual_context_card_count`
- `review_only_visual_context_excluded_count`
- `visual_context_included_pages`
- `webui_visual_context_cards`

The visual cards are still retrieval guidance only. They do not grant answer permission and cannot mutate source truth.

Expected current artifact behavior from the 12-page LLaVA run:

- 2 safe visual context cards included
- 10 review-only visual observations excluded
- 0 answer permission
- 0 source-truth mutation
- 0 Postgres/Qdrant/OpenSearch write attempts
