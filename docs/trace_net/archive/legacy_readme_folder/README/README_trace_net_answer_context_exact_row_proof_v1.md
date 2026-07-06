# TRACE-Net Answer Context Exact Row Proof v1

Adds an exact-row proof layer after the graph/Leiden context expander.

This module only upgrades `direct_exact_match_candidate` to `direct_exact_match_proven`
when the queried part number is found in source-traceable OCR/table/exact-search text
for the cited page. Graph and Leiden community context remain context/ranking signals
only; they do not prove exact part identity or interchangeability.

Safety contract: dry-run only; no Postgres/Qdrant/OpenSearch writes; no answer
permission; no source-truth mutation.

## Strict-source proof fix

This version only upgrades evidence to `direct_exact_match_proven` when the queried part number appears in trusted joined source artifacts: OCR route scan pack, table exact search adapter, table evidence package, or normalized table values. Graph/Leiden/enriched context records can carry useful excerpts and ranking metadata, but they also contain query metadata and role labels; therefore they cannot prove exact part identity by themselves.

Diagnostic fields include `untrusted_context_part_match_ignored_count`, `untrusted_context_part_match_ignored`, `trusted_exact_proof_sources`, and `exact_row_proof_warnings`.
