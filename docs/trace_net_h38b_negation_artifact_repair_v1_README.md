# H38B Negation + Artifact Contract Repair

H38B repairs H38's validator/artifact-mode mismatch.

Fixes:
- word-boundary matching for forbidden terms, so `installation safe` does not falsely match `installation safety`
- stronger negation detection for `cannot prove` / `does not prove` / `not ...`
- artifact quiz boundary answer now uses `cannot prove` wording

Safety contract:
- no live IO changes
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
