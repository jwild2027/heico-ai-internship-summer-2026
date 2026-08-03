# TRACE-Net Confirmed Image Gemma Structured Visual Cards v1.1

v1.1 tightens the v1 Gemma structured visual card output.

The v1 5-page sample worked mechanically, but inspection showed proof-like
wording and loose fields:

- `visual confirmation`
- non-figure text in `figure_refs`
- generic callouts like `part numbers`, `measurements`, `arrows`

v1.1 adds deterministic validation:

- figure refs normalize to `figure N` / `figure N sheet M`
- generic callouts are removed
- invented part numbers are rejected
- proof words are rewritten or quality-gated
- `evidence_use` is forced to retrieval-only / not-final-proof wording
