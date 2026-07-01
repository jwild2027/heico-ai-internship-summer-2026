# TRACE-Net Engineering Runner Expanded Eval Set v1

H8 wraps the existing H6 engineering runner evaluation set with a broader default
question set. It is an evaluation layer only: it does not change retrieval,
proof selection, answer composition, endpoints, LLaVA, or safety policy.

The default question set expands beyond the first six questions into exact part
lookups, evidence questions, unsupported interchangeability/safety questions, and
troubleshooting prompts. The goal is to measure engineering-brain coverage and
surface the next weak task types.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes or uploads
- no source-truth mutation
- no answer permission

The full question text is stored inside JSON records. H6C short run-directory
names remain the path-safety mechanism for Windows.
