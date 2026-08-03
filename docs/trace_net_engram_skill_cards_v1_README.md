# TRACE-Net Engram Skill Cards v1 — Phase 1

Phase 1 adds a source-controlled, validated skill-card library for the
middle-ground Engram + mature LLM architecture.

## Important boundary

This phase does **not** inject skills into the live cognitive runtime.

It adds:

- a strict skill-card schema;
- five initial reasoning skills;
- deterministic, inspectable query-to-skill selection;
- safety validation;
- unit tests and command-line inspection tools.

Engram skill cards are behavior guidance only. They cannot prove manual facts,
grant answer permission, execute retrieval, mutate source truth, or write to
Postgres, Qdrant, or OpenSearch.

## Initial skills

1. `partial_identifier_discovery`
2. `exact_identifier_lookup`
3. `nomenclature_function_discovery`
4. `ata_plus_description_discovery`
5. `manufacturer_plus_description_discovery`

Each skill contains at least:

- five positive examples;
- three negative examples;
- three known failure lessons;
- retrieval-order guidance;
- ranking policy;
- evidence-sufficiency rules;
- answer-mode rules;
- follow-up policy;
- an explicit safety contract.

## Check

```bash
python -B scripts/check_trace_net_engram_skill_cards_v1.py \
  --skills local_data/organization/trace_net/engram_skill_cards_v1/trace_net_engram_skill_cards_v1.json \
  --min-cards 5 \
  --max-cards 40 \
  --require-quality-pass \
  --require-no-answer-permission \
  --max-write-attempts 0
```

Expected:

```text
quality_status=PASS
checker_quality_status=PASS
skill_card_count=5
error_count=0
answer_permission=False
source_truth_mutation_allowed=False
can_be_used_as_proof=False
write_attempt_count=0
```

## Inspect Q001 selection

```bash
python -B scripts/select_trace_net_engram_skills_v1.py \
  --query "I only know the part starts with 123" \
  --route guided_part_discovery
```

Expected first skill:

```text
partial_identifier_discovery
```

## Phase 2 handoff

Phase 2 will convert the old successful play-by-play behaviors into runtime
Engram prompt bundles and connect reviewed skill selection to the planner and
writer in shadow mode before live enforcement.
