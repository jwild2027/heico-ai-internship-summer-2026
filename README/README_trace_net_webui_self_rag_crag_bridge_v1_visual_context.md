# TRACE-Net WebUI Self-RAG / CRAG Bridge visual context integration

This patch wires the safe WebUI visual context bridge into the existing WebUI Self-RAG / CRAG bridge.

The bridge can now accept:

```text
--webui-visual-context-bridge local_data/organization/trace_net/webui_visual_context_bridge/trace_net_webui_visual_context_bridge_v1.json
```

When the supplied visual context bridge has `quality_status: PASS` and one or more safe visual context cards, the Self-RAG/CRAG bridge checklist records:

- `visual_image_route: used`
- `webui_visual_context_bridge: used`

The main bridge report also includes:

- `visual_context_card_count`
- `review_only_visual_context_excluded_count`
- `visual_context_included_pages`
- `visual_context_included_canonical_page_numbers`
- `webui_visual_context_cards`

The visual cards remain retrieval guidance only. They do not grant answer permission and do not mutate source truth.

## Safety

This patch is artifact-only and pre-answer:

- no Gemma call
- no final answer draft
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
