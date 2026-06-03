# TRACE-Net Trust Semantics / Trust Authority v1

This patch adds a Postgres-backed trust semantics overlay. Trust tiers already say
how trusted an evidence record is. This module says what that trust is allowed to
mean.

It creates:

- `trust_authority_records` in PostgreSQL
- `local_data/organization/trace_net/trust_authority/trace_net_trust_authority_summary.json`
- `trace_net_trust_authority_records.jsonl`
- `trace_net_trust_authority_report.html`
- graph node/edge overlay artifacts

It does not mutate source truth, RAG eligibility, feedback, or production ranking.

## Build

```bash
python scripts/build_trace_net_trust_authority.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --open
```

## Quality

```bash
python scripts/check_trace_net_trust_authority_quality.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --write-json \
  --min-authority-records 1426 \
  --max-missing-authority-records 0 \
  --max-missing-candidate-trust-tier 0 \
  --min-source-evidence-authority-records 509 \
  --min-source-text-authority-records 495 \
  --min-verified-part-authority-records 360 \
  --min-derived-context-authority-records 60 \
  --max-source-evidence-direct-answer-records 0 \
  --max-derived-context-direct-answer-records 0 \
  --max-derived-context-canonical-source-truth-records 0 \
  --max-unsafe-authority-records 0 \
  --max-missing-source-url-authority-records 0 \
  --max-source-truth-mutations 0
```

## Semantics

- `source_evidence` proves the page/source exists; it supports answers but is not a direct answer record.
- `source_text_evidence` is source-backed OCR text; it can support direct text claims with citation.
- `verified_part_evidence` supports part/page relationship claims.
- `derived_context` is supporting context only; it is not canonical source truth and cannot answer directly.
