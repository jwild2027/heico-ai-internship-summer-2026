# TRACE-Net table route retrieval demo query pack v1

This module creates a local-only demo report from the table route retrieval readiness and hybrid retrieval bridge artifacts.

It is meant for human review and project explanation. It shows example user queries, matched table values, source pages, routing boosts, and the safety contract that keeps table-route values retrieval-only.

Safety contract:

- `retrieval_permission = ranking_only`
- `answer_authority = blocked`
- `can_answer_directly = false`
- `can_prove_claims = false`
- `source_truth_mutation_allowed = false`
- no Postgres, Qdrant, OpenSearch, or upload writes
