# TRACE-Net Citation/Authority Answer Composer Dry Run v1

Step 11 consumes the Step 10 source-resolved answer context pack and produces a citation-backed dry-run draft.

This is **not** a final answer path. It is a guarded preview of what an answer composer could use later.

## Safety contract

- Only Step 10 `answer_support_records` can become draft claims.
- `page_retrieval_profile`, `context_retrieval_helper`, `source_evidence`, and `derived_context` records are excluded from proof and kept as retrieval-only notes.
- Every draft claim must have `page_id`, `citation_id`, authority, source-resolution requirement, citation requirement, and authority-gate requirement.
- `final_answer_allowed` remains `false`.
- `llm_freeform_answer_allowed` remains `false`.
- No source truth is mutated.

## Files

```text
tiff/trace_net_citation_answer_draft_v1.py
scripts/build_trace_net_citation_answer_draft_v1.py
scripts/check_trace_net_citation_answer_draft_v1_quality.py
tests/unit/test_trace_net_citation_answer_draft_v1.py
tests/unit/test_trace_net_citation_answer_draft_v1_quality.py
tests/unit/test_trace_net_citation_answer_draft_v1_script_imports.py
README_trace_net_citation_answer_draft_v1.md
```

## Output directory

```text
local_data/organization/trace_net/citation_answer_draft/
```

Generated files:

```text
trace_net_citation_answer_draft_v1.json
trace_net_citation_answer_draft_v1_claims.jsonl
trace_net_citation_answer_draft_v1_blocked_records.jsonl
trace_net_citation_answer_draft_v1_summary.json
trace_net_citation_answer_draft_v1_manifest.json
trace_net_citation_answer_draft_v1_quality.json
trace_net_citation_answer_draft_v1.md
trace_net_citation_answer_draft_v1.html
```

Retrieval-only notes are stored in the main JSON report under `retrieval_only_notes`.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_citation_answer_draft_v1.py \
  tests/unit/test_trace_net_citation_answer_draft_v1_quality.py \
  tests/unit/test_trace_net_citation_answer_draft_v1_script_imports.py \
  -q
```

## Build the dry-run draft

```bash
python scripts/build_trace_net_citation_answer_draft_v1.py \
  --context-pack local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json \
  --output-dir local_data/organization/trace_net/citation_answer_draft \
  --max-groups 8 \
  --max-claims 12 \
  --max-claims-per-page 3 \
  --min-claims 1 \
  --require-context-pack-quality-pass \
  --require-context-pack-answer-status CONTEXT_PACK_ONLY \
  --require-embedding-dim 1024 \
  --quality
```

Expected shape:

```text
TRACE-Net citation/authority answer draft v1
 Status: CITATION_DRAFT_BUILT
 Quality status: PASS
 answer_status: CITATION_DRAFT_ONLY
 claim_count: >=1
 cited_claim_count: claim_count
 uncited_claim_count: 0
 retrieval_only_claim_count: 0
 claim_without_authority_count: 0
 claim_without_citation_count: 0
 source_truth_mutation_allowed_count: 0
 final_answer_allowed_count: 0
```

## Run quality separately

```bash
python scripts/check_trace_net_citation_answer_draft_v1_quality.py \
  --report-path local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1.json \
  --min-claims 1 \
  --require-context-pack-quality-pass \
  --require-context-pack-answer-status CONTEXT_PACK_ONLY \
  --require-embedding-dim 1024 \
  --write-json
```

Expected:

```text
TRACE-Net citation/authority answer draft v1 quality
 Status: PASS
```

## Inspect output

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("answer_status:", payload["answer_status"])
print("summary:", payload["summary"])
print("\nDRAFT TEXT:\n", payload["draft_text"])

for claim in payload["claims"][:5]:
    print()
    print("claim_id:", claim["claim_id"])
    print("page_id:", claim["page_id"])
    print("rag_bucket:", claim["rag_bucket"])
    print("authority:", claim["authority"])
    print("claim_text:", claim["claim_text"])
    print("citation_ids:", claim["citation_ids"])
    print("final_answer_allowed:", claim["final_answer_allowed"])

print("retrieval_only_notes:", len(payload.get("retrieval_only_notes", [])))
PY
```

## Commit files only

Do not commit generated `local_data/...` artifacts.

```bash
git add \
  tiff/trace_net_citation_answer_draft_v1.py \
  scripts/build_trace_net_citation_answer_draft_v1.py \
  scripts/check_trace_net_citation_answer_draft_v1_quality.py \
  tests/unit/test_trace_net_citation_answer_draft_v1.py \
  tests/unit/test_trace_net_citation_answer_draft_v1_quality.py \
  tests/unit/test_trace_net_citation_answer_draft_v1_script_imports.py \
  README_trace_net_citation_answer_draft_v1.md

git commit -m "Add TRACE-Net citation answer draft dry run v1"
```

## Next step

After this passes, the next safe stage is a final-answer gate that verifies every draft claim against citation/source/trust policy before any user-visible answer composition is allowed.
