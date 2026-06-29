# TRACE-Net Four Route Storage Gate v1

Builds a conservative final storage policy from the four-route retry/probe output.

## Purpose

This module turns validated four-route decisions into storage candidate manifests:

- Postgres graph/source-map policy for every page.
- Qdrant candidate records only for validated non-blank semantic evidence.
- OpenSearch candidate records only for validated table/exact-evidence pages.
- Blocked records for unresolved, blank, unsafe, or do-not-embed pages.

## Safety contract

This builder writes local JSON/JSONL/CSV/Markdown files only. It does not write to
Postgres, Qdrant, or OpenSearch. It grants no answer permission and does not mutate
source truth.
