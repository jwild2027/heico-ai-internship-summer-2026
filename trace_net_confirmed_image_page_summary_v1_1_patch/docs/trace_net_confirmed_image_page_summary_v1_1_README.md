# TRACE-Net Confirmed Image Page Summary v1.1

v1.1 fixes the first adapter pass where:

```text
pages_with_clean_figure_refs=0
```

The v1 builder only looked at one top-level `figure_refs` field. The gated
visual artifacts can store figure signals in nested fields, identifiers,
retrieval payloads, summaries, or search text.

## Fix

v1.1 recursively harvests:

- `figure_refs`
- `figure_references`
- `figures`
- `search_text`
- `summary`
- `description`
- `title`
- `caption`
- `nomenclature`
- nested visual payload text

It then normalizes figure refs with regex such as:

```text
figure 26 sheet 1
figure 609
fig. 3
```

It also keeps dict-like visual metadata out of clean `figure_refs` and moves it
into structured visual metadata / uncertainty.

## Safety

Still adapter-only by default:

- no OCR rerun
- no LLaVA call
- no Gemma call
- no DB writes
- no source-truth mutation
- no answer permission
