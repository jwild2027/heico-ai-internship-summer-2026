# TRACE-Net Visual Question Context Adapter v1.1

Route-seeded, artifact-specific correction to v1.

## Safety and non-redundancy
- Does not call LLaVA, Gemma, OCR, or any model.
- Does not reroute pages or redetect regions.
- Reads only approved image-route artifact families.
- Requires canonical TRACE-Net page IDs.
- Requires the page to be in the authoritative `image_visual` route allowlist.
- Produces read-only, no-answer-permission artifacts.

## Recommended laptop smoke
Use the authoritative page-route cards JSONL explicitly and start with lenient thresholds:

```bash
python -B scripts/build_trace_net_visual_question_context_adapter_v1_1.py \
  --artifact-root local_data/organization/trace_net \
  --route-manifest local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1_cards.jsonl \
  --output-dir local_data/organization/trace_net/visual_question_context_adapter_v1_1_smoke \
  --max-pages 10 \
  --min-context-count 1
```

After inspecting the first records, tighten `--min-pages-with-visual-ids` and
`--min-pages-with-page-context-v2`.
