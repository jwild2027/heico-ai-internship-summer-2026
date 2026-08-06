# TRACE-Net TIFF Content Gemma Evidence-Pack Router v2

Runs fixed TIFF-content questions with local artifact evidence packs and Gemma, without using the old demo ask endpoint.

## What v2 fixes

- Adds question-type routing before retrieval.
- Blocks blank Gemma answers with a safe fallback.
- Routes ATA questions to ATA-like patterns such as `25-21-00`, not revision dates or unrelated part records.
- Routes document title/revision questions to title/revision evidence only.
- Treats warning/caution/note questions as visible manual/OCR page-text questions, not internal pipeline warning fields.
- Keeps exact phrase/nomenclature searches strict, so unrelated seat evidence does not answer paper-towel-dispenser questions.
- Writes `evidence_debug.jsonl` showing `route_used`, evidence count, top sources, pages, parts, and ATA hits per question.

## Safety contract

Read-only. No writes to Postgres, Qdrant, OpenSearch, or source-truth artifacts. No answer permission is granted by this runner. Source-trace claims still require selected evidence snippets.
