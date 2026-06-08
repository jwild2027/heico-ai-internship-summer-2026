# TRACE-Net Algorithm Policy

This patch turns the community ablation metrics into a reusable policy/config artifact.

It records the current decision:

```text
source tracing / exact lookup: deterministic graph traversal
TRACE-Net repair batching: route_grouping
Table extraction batching: route_grouping
Broad retrieval expansion: Leiden
Community summaries: Leiden
```

The policy is intentionally conservative: Leiden can expand candidates or create semantic neighborhoods, but it never proves source truth.

## Files added

```text
tiff/trace_net_algorithm_policy.py
tiff/trace_net_algorithm_policy_quality.py
scripts/build_trace_net_algorithm_policy.py
scripts/check_trace_net_algorithm_policy_quality.py
tests/unit/test_tiff_trace_net_algorithm_policy.py
tests/unit/test_tiff_trace_net_algorithm_policy_quality.py
README_trace_net_algorithm_policy.md
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_algorithm_policy.py \
  tests/unit/test_tiff_trace_net_algorithm_policy_quality.py \
  -q
```

## Build the policy from the current ablation report

Make sure this exists first:

```text
local_data/organization/communities/community_ablation_eval.json
```

Then run:

```bash
python scripts/build_trace_net_algorithm_policy.py
```

Outputs:

```text
local_data/organization/communities/community_algorithm_policy.json
local_data/organization/communities/community_algorithm_policy_report.md
```

## Quality gate

```bash
python scripts/check_trace_net_algorithm_policy_quality.py --write-json
```

Output:

```text
local_data/organization/communities/community_algorithm_policy_quality.json
```

## Policy use

Future code should read `community_algorithm_policy.json` and choose algorithms by job:

```text
exact_part_lookup -> deterministic_graph_traversal
source_trace -> deterministic_graph_traversal
trace_net_repair_batching -> route_grouping
table_extraction_batching -> route_grouping
broad_retrieval_expansion -> leiden
community_summaries -> leiden
```
