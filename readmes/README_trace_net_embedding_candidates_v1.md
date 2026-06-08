# TRACE-Net Embedding Candidates v1

Step 4 builds the safe embedding-candidate layer for TRACE-Net.

This patch does **not** compute vectors and does **not** load Qdrant. It only writes local JSON/JSONL artifacts that step 5 can embed/load.

## Files in this patch

```text
tiff/trace_net_embedding_candidates_v1.py
scripts/build_trace_net_embedding_candidates_v1.py
scripts/check_trace_net_embedding_candidates_v1_quality.py
tests/unit/test_trace_net_embedding_candidates_v1.py
tests/unit/test_trace_net_embedding_candidates_v1_quality.py
README_trace_net_embedding_candidates_v1.md
```

## Inputs

- Postgres `rag_candidate_chunks`
- Postgres `source_citations`
- Postgres `trust_authority_records`
- Step 3 helper artifact:
  - `local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json`
- Step 2 graph baseline checkpoint:
  - `local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json`

## Outputs

Under:

```text
local_data/organization/trace_net/embedding_candidates/
```

Generated files:

```text
trace_net_embedding_candidates_v1.json
trace_net_embedding_candidates_v1.jsonl
trace_net_embedding_candidates_v1_rejected.jsonl
trace_net_embedding_candidates_v1_summary.json
trace_net_embedding_candidates_v1_manifest.json
trace_net_embedding_candidates_v1_quality.json
```

## Allowed embedding buckets

```text
source_text_evidence
verified_part_evidence
derived_context
context_retrieval_helper
```

`source_evidence` is safe source-trace data, but this step rejects it from embedding because it is usually a source/page locator rather than useful semantic answer text.

## Safety boundary

Every safe embedding candidate must keep these rules:

```text
can_embed = true
can_retrieve = true
can_answer_directly = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
canonical_source_truth = false
can_mutate_source_truth = false
```

Retrieval-only buckets remain retrieval-only:

```text
derived_context
context_retrieval_helper
```

They may route search and rank candidates, but they cannot prove claims.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_embedding_candidates_v1.py \
  tests/unit/test_trace_net_embedding_candidates_v1_quality.py \
  -q
```

## Build embedding candidates

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/build_trace_net_embedding_candidates_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --baseline-checkpoint local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --context-helpers local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json \
  --output-dir local_data/organization/trace_net/embedding_candidates \
  --require-first-pages 1-50 \
  --min-safe-candidates 967 \
  --min-rag-candidates 917 \
  --min-context-helper-candidates 50 \
  --min-pages-with-candidates 50 \
  --require-baseline-quality-pass \
  --require-context-helper-quality-pass \
  --quality
```

Expected baseline shape:

```text
safe_embedding_candidate_count: 967
rag_candidate_embedding_count: 917
context_helper_embedding_count: 50
rejected_embedding_candidate_count: 509
unsafe_embedding_candidate_count: 0
Quality status: PASS
```

The 509 rejected records should mostly be `source_evidence` locator records that remain safe in Postgres but are not embedded in this step.

## Run quality separately

```bash
python scripts/check_trace_net_embedding_candidates_v1_quality.py \
  --candidates-path local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --rejected-path local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1_rejected.jsonl \
  --baseline-checkpoint local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --context-helpers local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json \
  --require-first-pages 1-50 \
  --min-safe-candidates 967 \
  --min-rag-candidates 917 \
  --min-context-helper-candidates 50 \
  --min-pages-with-candidates 50 \
  --require-baseline-quality-pass \
  --require-context-helper-quality-pass \
  --write-json
```

## Quick inspect

```bash
python - <<'PY'
import json
from pathlib import Path
path = Path("local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))
print("record_count:", payload["record_count"])
print("rejected_record_count:", payload["rejected_record_count"])
print("bucket_counts:", payload["summary"]["bucket_counts"])
record = payload["records"][0]
for key in [
    "embedding_candidate_id",
    "source_candidate_id",
    "page_id",
    "rag_bucket",
    "authority",
    "can_answer_directly",
    "requires_source_resolution",
    "requires_citation",
]:
    print(key + ":", record.get(key))
PY
```

## Commit source files only

Do not commit generated `local_data/...` artifacts.

```bash
git add \
  tiff/trace_net_embedding_candidates_v1.py \
  scripts/build_trace_net_embedding_candidates_v1.py \
  scripts/check_trace_net_embedding_candidates_v1_quality.py \
  tests/unit/test_trace_net_embedding_candidates_v1.py \
  tests/unit/test_trace_net_embedding_candidates_v1_quality.py \
  README_trace_net_embedding_candidates_v1.md

git commit -m "Build TRACE-Net embedding candidates v1"
```

## Next step

Step 5 should embed `trace_net_embedding_candidates_v1.jsonl` and load those points into Qdrant. Qdrant remains an index; Postgres/source/citation/trust remain the authority layer.
