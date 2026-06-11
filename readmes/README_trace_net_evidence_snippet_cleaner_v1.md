# TRACE-Net Evidence Snippet Cleaner / Source Text Extractor v1

Step 11.6 consumes Step 11.5 evidence snippet claims and produces cleaner, source-facing snippet records. It is still **not** a final answer gate.

This stage exists because Step 11.5 correctly proved citation/source safety, but the raw snippet text can still include TRACE-Net wrapper metadata such as:

```text
Source text evidence for page ...
This chunk is source-backed OCR/page-context text...
Source URL: ...
TIFF path: local_data\...
OCR path: local_data\...
OCR text: [b...
```

Step 11.6 removes those wrappers, optionally reads the traceable local OCR file for `source_text_evidence`, and writes cleaned snippet claims that can later be evaluated by a final answer gate.

## Safety contract

Allowed clean snippet buckets:

```text
source_text_evidence
verified_part_evidence, only when meaningful part/nomenclature content exists
```

Blocked from clean snippet proof:

```text
page_retrieval_profile
context_retrieval_helper
source_evidence
derived_context
raw OCR / raw visual / raw table extraction
feedback / debug / prompt records
```

Every clean snippet claim keeps:

```text
answer_status = CLEAN_SNIPPETS_ONLY
final_answer_allowed = false
llm_freeform_answer_allowed = false
requires_final_answer_gate = true
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
```

The cleaner blocks or fails quality if clean snippets leak:

```text
local_data\
rescarta_exports
TIFF path:
OCR path:
Source URL:
Source text evidence for page
This chunk is source-backed
OCR text: [b
Python bytes wrappers like b'...'
```

## Outputs

The builder writes local artifacts under:

```text
local_data/organization/trace_net/evidence_snippet_cleaner/
```

Generated files:

```text
trace_net_evidence_snippet_cleaner_v1.json
trace_net_evidence_snippet_cleaner_v1_claims.jsonl
trace_net_evidence_snippet_cleaner_v1_blocked_records.jsonl
trace_net_evidence_snippet_cleaner_v1_summary.json
trace_net_evidence_snippet_cleaner_v1_manifest.json
trace_net_evidence_snippet_cleaner_v1_quality.json
trace_net_evidence_snippet_cleaner_v1.md
trace_net_evidence_snippet_cleaner_v1.html
```

Do not commit generated `local_data/...` outputs.

## Build

```bash
python scripts/build_trace_net_evidence_snippet_cleaner_v1.py \
  --snippet-claims local_data/organization/trace_net/evidence_snippet_claims/trace_net_evidence_snippet_claims_v1.json \
  --context-pack local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/evidence_snippet_cleaner \
  --max-claims 12 \
  --max-clean-snippet-chars 700 \
  --min-clean-snippet-chars 20 \
  --min-clean-snippets 1 \
  --require-snippet-claims-quality-pass \
  --require-context-pack-quality-pass \
  --require-snippet-claims-answer-status SNIPPET_CLAIMS_ONLY \
  --require-context-pack-answer-status CONTEXT_PACK_ONLY \
  --require-embedding-dim 1024 \
  --quality
```

By default, source-text claims may read their traceable local `ocr_path` to recover actual manual/OCR text when the Step 11.5 snippet only contains metadata wrapper text. Disable that behavior with:

```bash
--no-local-ocr-read
```

## Quality check

```bash
python scripts/check_trace_net_evidence_snippet_cleaner_v1_quality.py \
  --report-path local_data/organization/trace_net/evidence_snippet_cleaner/trace_net_evidence_snippet_cleaner_v1.json \
  --min-clean-snippets 1 \
  --require-snippet-claims-quality-pass \
  --require-context-pack-quality-pass \
  --require-snippet-claims-answer-status SNIPPET_CLAIMS_ONLY \
  --require-context-pack-answer-status CONTEXT_PACK_ONLY \
  --require-embedding-dim 1024 \
  --write-json
```

Expected pass shape:

```text
Quality status: PASS
clean_snippet_claim_count >= 1
missing_clean_snippet_count: 0
boilerplate_snippet_count: 0
local_path_leak_count: 0
raw_bytes_repr_count: 0
forbidden_marker_count: 0
retrieval_only_clean_claim_count: 0
final_answer_allowed_count: 0
llm_freeform_answer_allowed_count: 0
```

## Inspect

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/evidence_snippet_cleaner/trace_net_evidence_snippet_cleaner_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("answer_status:", payload["answer_status"])
print("summary:", payload["summary"])

for claim in payload["clean_snippet_claims"][:8]:
    print()
    print("rank:", claim["clean_snippet_rank"])
    print("claim:", claim["clean_materialized_claim_text"])
    print("page_id:", claim["page_id"])
    print("bucket:", claim["rag_bucket"])
    print("authority:", claim["authority"])
    print("citation_ids:", claim["citation_ids"])
    print("clean_source_snippet:", claim["clean_source_snippet"][:500])
    print("raw_source_path_read:", claim["raw_source_path_read"])
    print("final_answer_allowed:", claim["final_answer_allowed"])
PY
```

## Commit source files only

```bash
git add \
  tiff/trace_net_evidence_snippet_cleaner_v1.py \
  scripts/build_trace_net_evidence_snippet_cleaner_v1.py \
  scripts/check_trace_net_evidence_snippet_cleaner_v1_quality.py \
  tests/unit/test_trace_net_evidence_snippet_cleaner_v1.py \
  tests/unit/test_trace_net_evidence_snippet_cleaner_v1_quality.py \
  tests/unit/test_trace_net_evidence_snippet_cleaner_v1_script_imports.py \
  README_trace_net_evidence_snippet_cleaner_v1.md

git commit -m "Add TRACE-Net evidence snippet cleaner v1"
```
