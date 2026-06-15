# TRACE-Net Context Retrieval Helper v1

This patch implements step 3 in the TRACE-Net sequence: turn `PageContextV2` records into safe retrieval-helper records.

The helper records are not source truth and cannot answer directly. They are query tunnels that help future keyword/vector/hybrid retrieval find likely pages and evidence faster. Any final answer still has to resolve through Postgres graph/source data, trust authority, and citations.

## Files in this patch

```text
tiff/trace_net_context_retrieval_helper_v1.py
scripts/build_trace_net_context_retrieval_helpers_v1.py
scripts/check_trace_net_context_retrieval_helpers_v1_quality.py
tests/unit/test_trace_net_context_retrieval_helper_v1.py
tests/unit/test_trace_net_context_retrieval_helper_v1_quality.py
README_trace_net_context_retrieval_helper_v1.md
```

## Output location

The builder writes local generated artifacts under:

```text
local_data/organization/trace_net/context_retrieval_helpers/
```

Generated files:

```text
trace_net_context_retrieval_helpers_v1.json
trace_net_context_retrieval_helpers_v1.jsonl
trace_net_context_retrieval_helpers_v1_summary.json
trace_net_context_retrieval_helpers_v1_manifest.json
trace_net_context_retrieval_helpers_v1_quality.json  # when --quality or --write-json is used
```

Do not commit these generated `local_data/...` artifacts unless you intentionally want local checkpoint output in Git.

## Safety contract

Every helper record is forced into this policy shape:

```text
record_type = context_retrieval_helper
safety_bucket = context_retrieval_helper
authority = retrieval_helper_only
can_answer_directly = false
can_prove_claims = false
canonical_source_truth = false
can_mutate_source_truth = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
embedding_answer_authority_allowed = false
```

Allowed use:

```text
retrieve
route
rank_boost
query_expansion
candidate_discovery
```

Forbidden use:

```text
direct_answer
claim_proof
canonical_source_truth
source_truth_mutation
citation_replacement
trust_tier_override
```

## Install from patch zip

From Git Bash at repo root:

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o /c/Users/juswil/Downloads/tracenet_context_retrieval_helper_v1_patch.zip -d .
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_context_retrieval_helper_v1.py \
  tests/unit/test_trace_net_context_retrieval_helper_v1_quality.py \
  -q
```

## Build helper records

Make sure Postgres is running:

```bash
docker start trace-net-postgres
docker exec trace-net-postgres pg_isready -U tracenet -d tracenet_dev
```

Set the active local TRACE-Net database URL:

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"
```

Build the helper records and run quality gates:

```bash
python scripts/build_trace_net_context_retrieval_helpers_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --baseline-checkpoint local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --require-baseline-quality-pass \
  --output-dir local_data/organization/trace_net/context_retrieval_helpers \
  --require-first-pages 1-50 \
  --min-helper-records 50 \
  --min-pages-with-helpers 50 \
  --min-records-with-summary 40 \
  --min-records-with-retrieval-cues 40 \
  --min-records-with-query-tunnel-terms 40 \
  --quality
```

Expected result:

```text
TRACE-Net context retrieval helper v1
 Status: BUILT
 helper_count: 50
 page_count: 50
 required_page_missing_count: 0
 unsafe_helper_count: 0
 Quality status: PASS
```

## Run quality separately

```bash
python scripts/check_trace_net_context_retrieval_helpers_v1_quality.py \
  --helpers-path local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json \
  --baseline-checkpoint local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --require-baseline-quality-pass \
  --require-first-pages 1-50 \
  --min-helper-records 50 \
  --min-pages-with-helpers 50 \
  --min-records-with-summary 40 \
  --min-records-with-retrieval-cues 40 \
  --min-records-with-query-tunnel-terms 40 \
  --write-json
```

Expected result:

```text
TRACE-Net context retrieval helper v1 quality
 Status: PASS
 helper_count: 50
 page_count: 50
 required_page_missing_count: 0
 unsafe_helper_count: 0
 baseline_quality_status: PASS
```

## Inspect generated records

```bash
python - <<'PY'
import json
from pathlib import Path
path = Path('local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json')
payload = json.loads(path.read_text(encoding='utf-8'))
print(payload['record_count'])
record = payload['records'][0]
for key in ['helper_id', 'page_id', 'authority', 'can_answer_directly', 'requires_source_resolution', 'requires_citation']:
    print(key, record.get(key))
print(record.get('query_tunnel_terms', [])[:10])
PY
```

## Commit patch files only

```bash
git add \
  tiff/trace_net_context_retrieval_helper_v1.py \
  scripts/build_trace_net_context_retrieval_helpers_v1.py \
  scripts/check_trace_net_context_retrieval_helpers_v1_quality.py \
  tests/unit/test_trace_net_context_retrieval_helper_v1.py \
  tests/unit/test_trace_net_context_retrieval_helper_v1_quality.py \
  README_trace_net_context_retrieval_helper_v1.md

git commit -m "Build TRACE-Net context retrieval helper records v1"
```

## Next step

After this passes, step 4 can build embedding candidates from safe buckets only, including these `context_retrieval_helper` records as retrieval-only candidates.
