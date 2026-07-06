# H37C Diversity Planner Cleanup

H37C replaces the failed H37B patcher with a top-level function-boundary scanner instead of a fragile regex.

Fixes applied to H37:
- reject placeholder figure values such as `anchor`
- reject metadata-like nomenclature values such as `source_evidence_document_count`
- prevent duplicate selected evidence labels such as repeated `V6`
- avoid manifest-only records becoming diversity evidence

Safety contract:
- no LLM calls
- no database writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
