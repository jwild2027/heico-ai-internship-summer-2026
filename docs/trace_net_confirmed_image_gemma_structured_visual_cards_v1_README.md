# TRACE-Net Confirmed Image Gemma Structured Visual Cards v1

This module turns confirmed image cards with cleaned LLaVA observations into
structured retrieval-ready visual cards.

## Input

Use the v1.2 clean merge output:

```text
local_data/organization/trace_net/confirmed_image_page_summary_v1_2_with_llava/trace_net_confirmed_image_page_summary_v1_2.jsonl
```

## Model roles

- LLaVA = visual observer / eyes.
- Gemma4 = organizer / schema cleaner.
- OCR/table/source fields remain authority for exact text and part-number facts.

## Outputs

- `trace_net_confirmed_image_gemma_structured_visual_cards_v1.jsonl`
- `trace_net_confirmed_image_gemma_structured_visual_retrieval_documents_v1.jsonl`
- `summary.json`

## Safety

The script does not write to Postgres, Qdrant, or OpenSearch. It does not grant
answer permission. The cards are retrieval guidance only.
