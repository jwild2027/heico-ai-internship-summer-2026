# TRACE-Net Artifact Dirty Planner v1

Read-only planner for deciding which downstream TRACE-Net artifacts should be rebuilt when an artifact or input path changes.

## Purpose

TRACE-Net now has many generated artifacts under `local_data/organization/trace_net/`. This module reads the Artifact Dependency Registry and a set of changed artifact IDs or paths, then emits a rebuild plan ordered by downstream dependency depth.

The planner is advisory. It does not rebuild anything by itself.

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority

## Example

```bash
python scripts/build_trace_net_artifact_dirty_planner_v1.py \
  --artifact-registry local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.json \
  --changed-artifact opensearch_adapter \
  --changed-artifact opensearch_loader_smoke \
  --output-dir local_data/organization/trace_net/artifact_dirty_planner \
  --min-planner-records 1 \
  --min-dirty-artifacts 1 \
  --max-dependency-cycles 0 \
  --require-registry-quality-pass \
  --quality
```

Check:

```bash
python scripts/check_trace_net_artifact_dirty_planner_v1_quality.py \
  --report-path local_data/organization/trace_net/artifact_dirty_planner/trace_net_artifact_dirty_planner_v1.json \
  --min-planner-records 1 \
  --min-dirty-artifacts 1 \
  --max-dependency-cycles 0 \
  --require-registry-quality-pass \
  --write-json
```

## Outputs

- `trace_net_artifact_dirty_planner_v1.json`
- `trace_net_artifact_dirty_planner_v1_quality.json`
- `trace_net_artifact_dirty_planner_v1.md`

## Interpretation

`planner_records` is the main rebuild list. Each record includes:

- `artifact_id`
- `rebuild_order`
- `dependency_depth`
- `seed_artifacts`
- `direct_dirty_upstreams`
- `recommended_action`

Communities, categories, feedback, and retrieval-only artifacts remain advisory. This planner does not grant answer authority.
