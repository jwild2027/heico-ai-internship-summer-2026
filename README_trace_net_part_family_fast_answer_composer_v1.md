# TRACE-Net Part Family Fast Answer Composer v1

Builds a deterministic, cited fast answer for part-family questions from an already-built anchor-aware context pack.

The family lookup uses two layers:

1. **Part-number prefix / variant evidence** as the primary family signal, e.g. `120-29073-001`, `120-29073-005`, `120-29073-007`.
2. **Graph/Leiden community context** as a ranking/support signal for nearby family records. Leiden can group and prioritize related evidence, but it does not prove interchangeability or substitute status.

Safety contract: dry-run only, no answer permission, no source-truth mutation, no Postgres/Qdrant/OpenSearch writes.
