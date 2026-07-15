# TRACE-Net H30 Cognitive Precision + Dynamic Engram v1

This focused patch repairs issues observed in the first live Open WebUI route run.

## Changes

- matches route/nomenclature terms at word boundaries (`recover` no longer activates `cover`)
- rejects prose such as `THE` from partial part-number extraction
- gives explicit topical/page-discovery intent priority over incidental component nouns
- removes evidence rows that explicitly name only different part numbers
- decomposes multi-question research into claim-specific bounded subqueries
- loads and selects up to six relevant Engram atoms per request
- exposes selected Engram atoms to the Gemma writer as uncitable behavior guidance
- adds regression tests for the exact Open WebUI failures

## Safety contract

- no Postgres, Qdrant, OpenSearch, or source-truth writes
- Engram memory is guidance only and grants no answer permission
- exact authority is still required for approval, effectivity, applicability, fit, and interchangeability
- candidate, semantic, visual, graph, summary, and unresolved OCR evidence remain non-proof guidance
