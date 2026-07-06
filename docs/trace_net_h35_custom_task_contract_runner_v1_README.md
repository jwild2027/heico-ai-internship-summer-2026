# TRACE-Net H35 Custom Task Contract Runner v1

H35 adds a contract-first custom task runner for complex TRACE-Net questions such as quiz generation, multi-page summaries, comparisons, nomenclature lookup, and representative page explanations.

The module is artifact-first and safe by default:

- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission

The key improvement over H34B is that each custom task has a measurable contract: minimum evidence labels, minimum routes, required output pieces, forbidden claims, answer budget, and fallback limits.

Fallback can be forbidden with `--max-fallback-used 0`.

Engram/task contracts are behavior guidance only; factual claims still require current evidence-card citations.
