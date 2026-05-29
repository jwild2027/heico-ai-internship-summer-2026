# TIFF Page Context Diagnostics Patch

This patch keeps the page-context graph behavior the same, but improves the CLI output from
`scripts/generate_page_contexts.py` so warnings and fallback reasons are visible.

Use:

```bash
python scripts/generate_page_contexts.py --model gemma3:12B --limit 25 --force --write-json --show-error-details
```

The command now prints warning/error categories such as:

- `empty_ocr`
- `model_json_parse_fallback`
- `ollama_failed`
- `ollama_timeout`
- `model_fallback`

This helps determine whether page contexts came from the model or from deterministic fallback summaries.
