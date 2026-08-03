# TRACE-Net guided discovery router proxy v5

Adds fast clarification handling for ambiguous clue-only part queries.

Router v4 correctly routed more weak queries into guided discovery, but the 50-question smoke showed that some contains/suffix/page/nomenclature clues can run into long candidate-search timeouts. v5 keeps strict prefix candidate discovery available, while returning immediate unanswered follow-up questions for ambiguous clue-only or safety-sensitive queries before running expensive search.

Safety contract: read-only, no source-truth mutation, no Postgres/Qdrant/OpenSearch writes, no answer permission.
