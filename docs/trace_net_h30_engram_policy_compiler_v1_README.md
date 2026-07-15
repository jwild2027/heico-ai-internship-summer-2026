# TRACE-Net H30 Engram Policy Compiler v1

This phase makes the live Engram influence retrieval and presentation without
turning memory into a database or evidence source.

## What changes

- Engram memory is selected before retrieval.
- Overlapping memories are deduplicated by `canonical_rule_id`.
- Selected memory compiles into an allowlisted policy.
- Request-local working memory is created fresh for every question.
- Retrieval completion reads policy for specialized search activation,
  direct-source attempts, evidence ranking, grouping, result limits, and
  internal-ID hiding.

## What remains deterministic

- permitted routes and adapters;
- database and service access;
- exact source-truth promotion;
- citation readiness;
- authority requirements;
- bounded repair limits;
- no-write safety controls.

The compiler cannot execute SQL, graph queries, arbitrary searches, or writes.
It produces validated preferences only.
