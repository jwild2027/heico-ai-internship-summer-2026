# TRACE-Net H22 Prompt Boundary Phrase Fix v1

Small repair for H22 prompt retrieval LLM smoke.

The original H22 v1b fixed `_compact_text(max_chars=...)`, but one unit test still expected the exact boundary sentence:

`Manual/source claims still require current proof_context citations.`

This patch inserts or normalizes that sentence in the H22 prompt module. It does not change runtime permissions or IO behavior.

Safety contract:

- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
- Engram guidance remains behavior-only, not proof
