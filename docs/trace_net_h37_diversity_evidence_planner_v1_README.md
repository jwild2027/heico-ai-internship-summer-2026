# TRACE-Net H37 Diversity Evidence Planner v1

H37 is an artifact-first planner that prevents synthesis tasks from collapsing into one strong evidence cluster.

It selects source-trace candidate cards with diversity across:

- route
- page
- figure
- part number
- nomenclature

The planner emits:

- `trace_net_h37_diversity_evidence_planner_v1.json`
- `trace_net_h37_diversity_evidence_planner_v1_plan_records.jsonl`
- `trace_net_h37_diversity_overlay_map_v1.json`
- quality check JSON

Safety contract:

- no LLM calls
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission

Proof boundary:

The planner selects diverse evidence cards for downstream prompts, but the planner itself is not proof. Manual claims still require current `proof_context` citations.
