# TRACE-Net Evidence Snippet / Claim Materializer v1

Step 11.5 consumes the Step 10 answer context pack and the Step 11 citation/authority answer draft. It materializes citation-backed snippet claim records while keeping final answers disabled.

This stage upgrades safe Step 11 meta-claims such as:

```text
page 1 has citation-backed source-text evidence relevant to the query
```

into dry-run snippet claims that carry the actual source snippet used for review:

```text
page 1 has cited source-text evidence excerpt: "..."
```

## Safety contract

Only these buckets may become snippet claims:

```text
source_text_evidence
verified_part_evidence
```

These buckets remain retrieval-only and cannot prove snippet claims:

```text
page_retrieval_profile
context_retrieval_helper
source_evidence
derived_context
raw OCR / raw visual / raw table extraction
feedback / debug / prompt records
```

Every snippet claim must have:

```text
page_id
citation_id / citation_ids
authority
source_snippet
context-pack source record resolution
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
final_answer_allowed = false
llm_freeform_answer_allowed = false
```

## Outputs

The builder writes local artifacts under:

```text
local_data/organization/trace_net/evidence_snippet_claims/
```

Generated files:

```text
trace_net_evidence_snippet_claims_v1.json
trace_net_evidence_snippet_claims_v1_claims.jsonl
trace_net_evidence_snippet_claims_v1_blocked_records.jsonl
trace_net_evidence_snippet_claims_v1_summary.json
trace_net_evidence_snippet_claims_v1_manifest.json
trace_net_evidence_snippet_claims_v1_quality.json
trace_net_evidence_snippet_claims_v1.md
trace_net_evidence_snippet_claims_v1.html
```

Do not commit generated `local_data/...` outputs.

## Build

```bash
python scripts/build_trace_net_evidence_snippet_claims_v1.py \
  --citation-draft local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1.json \
  --context-pack local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json \
  --output-dir local_data/organization/trace_net/evidence_snippet_claims \
  --max-claims 12 \
  --max-snippet-chars 700 \
  --min-snippet-claims 1 \
  --require-draft-quality-pass \
  --require-context-pack-quality-pass \
  --require-draft-answer-status CITATION_DRAFT_ONLY \
  --require-context-pack-answer-status CONTEXT_PACK_ONLY \
  --require-embedding-dim 1024 \
  --quality
```

Expected shape:

```text
TRACE-Net evidence snippet / claim materializer v1
 Status: SNIPPET_CLAIMS_MATERIALIZED
 Quality status: PASS
 answer_status: SNIPPET_CLAIMS_ONLY
 snippet_claim_count: >=1
 cited_snippet_claim_count: snippet_claim_count
 missing_source_snippet_count: 0
 retrieval_only_snippet_claim_count: 0
 source_truth_mutation_allowed_count: 0
 final_answer_allowed_count: 0
```

## Quality check

```bash
python scripts/check_trace_net_evidence_snippet_claims_v1_quality.py \
  --report-path local_data/organization/trace_net/evidence_snippet_claims/trace_net_evidence_snippet_claims_v1.json \
  --min-snippet-claims 1 \
  --require-draft-quality-pass \
  --require-context-pack-quality-pass \
  --require-draft-answer-status CITATION_DRAFT_ONLY \
  --require-context-pack-answer-status CONTEXT_PACK_ONLY \
  --require-embedding-dim 1024 \
  --write-json
```

## Inspect snippets

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/evidence_snippet_claims/trace_net_evidence_snippet_claims_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("answer_status:", payload["answer_status"])
print("final_answer_allowed:", payload["final_answer_allowed"])
print("summary:", payload["summary"])

for claim in payload["snippet_claims"][:10]:
    print()
    print("rank:", claim["snippet_claim_rank"])
    print("text:", claim["materialized_claim_text"])
    print("page_id:", claim["page_id"])
    print("bucket:", claim["rag_bucket"])
    print("authority:", claim["authority"])
    print("citation_ids:", claim["citation_ids"])
    print("snippet:", claim["source_snippet"][:300])
    print("final_answer_allowed:", claim["final_answer_allowed"])
PY
```

## Tests

```bash
python -m pytest \
  tests/unit/test_trace_net_evidence_snippet_claims_v1.py \
  tests/unit/test_trace_net_evidence_snippet_claims_v1_quality.py \
  tests/unit/test_trace_net_evidence_snippet_claims_v1_script_imports.py \
  -q
```

## Role in TRACE-Net

```text
Step 10 context pack -> Step 11 citation draft -> Step 11.5 snippet claims -> Step 12 final answer gate
```

This stage still does not produce a final answer. It prepares snippet-backed, citation-bound claim material for the next final-answer gate.
