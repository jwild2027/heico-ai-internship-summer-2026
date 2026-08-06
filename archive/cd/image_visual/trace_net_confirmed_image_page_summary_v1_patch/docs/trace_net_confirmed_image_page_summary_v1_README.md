# TRACE-Net Confirmed Image Page Summary v1

Front-half visual summary layer.

This module builds one clean summary card for every confirmed image/diagram page.

```text
confirmed image pages
→ clean visual page summary cards
→ visual retrieval-ready summary docs
```

## Why this exists

Earlier visual work made the route safe:

```text
185 raw visual candidates
→ 104 confirmed image pages
→ 81 review-only visual candidates
```

This module improves the front-half image memory, similar to how V2/V3 summaries
support text pages and table evidence packs support table pages.

## Default mode

Default mode is adapter-only:

- no OCR rerun
- no LLaVA call
- no Gemma call
- no database writes
- no source-truth mutation

It cleans the existing gated visual docs into a stable schema.

## Optional model mode

Explicit flags enable model calls:

```text
--call-ollama-llava
--call-ollama-gemma
```

Contract:

```text
OCR    = source text authority
LLaVA  = visual-layout observation only
Gemma  = schema normalization only
```

LLaVA does not replace OCR. Gemma does not create source truth.

## Main output

```text
trace_net_confirmed_image_page_summary_v1.jsonl
trace_net_confirmed_image_page_summary_v1_retrieval_documents.jsonl
summary.json
trace_net_confirmed_image_page_summary_v1_report.txt
```
