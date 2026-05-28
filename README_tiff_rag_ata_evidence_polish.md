# TIFF RAG ATA evidence polish

This patch improves the deterministic ATA answer used by:

```bash
python scripts/ask_tiff_rag.py --config local_config.yaml "Find evidence for ATA 25-21-00."
```

The earlier fix correctly found the ATA section, but the first sample pages could
be front-matter or empty-OCR pages. This patch keeps the answer deterministic and
source-backed while prioritizing useful sample pages:

```text
1. non-empty OCR pages first
2. pages with extracted logical parts before pages with no parts
3. original page order after that
```

The answer also prints a small `parts=N` indicator for each sample page.
