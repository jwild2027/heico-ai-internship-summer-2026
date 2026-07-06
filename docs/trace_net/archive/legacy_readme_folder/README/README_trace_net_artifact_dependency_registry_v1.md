# TRACE-Net Artifact Dependency Registry v1

This module builds a dry-run dependency registry for TRACE-Net artifacts.

It scans `local_data/organization/trace_net`, identifies primary TRACE-Net report JSON files, hashes each artifact, reads quality/status/schema metadata, and attaches a curated dependency map between pipeline stages.

It is read-only. It does not write Postgres, Qdrant, OpenSearch, graph truth, source files, or answer records.

## Build

```bash
python scripts/build_trace_net_artifact_dependency_registry_v1.py \
  --trace-net-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/artifact_dependency_registry \
  --min-artifacts 25 \
  --min-dependency-edges 10 \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_artifact_dependency_registry_v1_quality.py \
  --report-path local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.json \
  --min-artifacts 25 \
  --min-dependency-edges 10 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/artifact_dependency_registry/
  trace_net_artifact_dependency_registry_v1.json
  trace_net_artifact_dependency_registry_v1_records.jsonl
  trace_net_artifact_dependency_registry_v1_edges.jsonl
  trace_net_artifact_dependency_registry_v1_summary.json
  trace_net_artifact_dependency_registry_v1_quality.json
  trace_net_artifact_dependency_registry_v1_manifest.json
  trace_net_artifact_dependency_registry_v1.md
  trace_net_artifact_dependency_registry_v1.html
```

## Purpose

This registry is the foundation for dynamic/incremental TRACE-Net processing. It records:

- artifact IDs
- stage IDs
- file hashes
- schema versions
- quality/status values
- record/page counts
- upstream dependencies
- downstream dependencies
- cache keys
- dirty/review state

The next layer can use this registry to build an artifact dirty planner and decide which downstream artifacts need rebuild when one file, model, config, or stage changes.

## Safety contract

```text
read_only_registry = true
source_truth_mutation_allowed_count = 0
postgres_write_attempt_count = 0
qdrant_write_attempt_count = 0
opensearch_write_attempt_count = 0
direct_answer_allowed_count = 0
claim_proof_allowed_count = 0
```

The registry can organize dependency state. It cannot answer, prove claims, or mutate source truth.
