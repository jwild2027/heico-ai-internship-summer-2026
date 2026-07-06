# TRACE-Net Open WebUI Gemma4 Engram Bridge v2

V2 fixes the issue where asking "how many pages can you look at" was routed as a normal evidence query and returned unrelated cards like `can_answer_directly_count`.

Changes:
- adds corpus_stats query routing
- answers page-count questions deterministically from TRACE-Net artifact page IDs
- filters metric/quality fields out of evidence retrieval
- advertises new Open WebUI model id: trace-net-gemma4-engram-e2e-v2
- keeps Gemma4 + Engram path for normal/complex questions
- supports llm-policy auto|always|never and fast-task-types

Safety:
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
- answer permission remains false
