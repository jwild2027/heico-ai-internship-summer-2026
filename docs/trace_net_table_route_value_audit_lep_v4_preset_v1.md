# TRACE-Net Table Route Value Audit LEP v4 Preset v1

This patch operationalizes the immediate next step from the table-route handoff:
rerun `trace_net_table_route_value_audit_v1` after the LEP v4 normalizer with
thresholds adjusted for intentional context suppression.

The important threshold change is:

```text
--min-source-normalized-records 1800
```

The old 3000 threshold is no longer appropriate because LEP v4 suppresses noisy
LEP context values and currently reports 2108 normalized table values.

The preset writes:

- `trace_net_table_route_value_audit_lep_v4_preset_v1_manifest.json`
- `trace_net_table_route_value_audit_lep_v4_preset_v1_quality.json`
- `trace_net_table_route_value_audit_lep_v4_preset_v1_inspect.json`
- `trace_net_table_route_value_audit_lep_v4_preset_v1_inspect.md`

The inspect outputs focus on:

- `high_context_ratio_table_count`
- `review_required_table_count`
- `search_ready_evidence_record_count`
- promoted field counts
- first compact search-ready values

Safety remains read-only. This patch grants no answer permission and performs no
Postgres, Qdrant, or OpenSearch writes.
