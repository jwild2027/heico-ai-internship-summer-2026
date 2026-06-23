# TRACE-Net Table Margin Morphology Parity v1

Read-only diagnostic module that compares Table Line Geometry margin-aware crop selection against the standalone Table Crop Margin Expansion Experiment.

It explains cases where the experiment found a margin-expanded crop with stronger grid evidence but production Table Line Geometry still kept page morphology.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- cannot prove claims

Outputs are advisory diagnostics under `local_data/organization/trace_net/table_margin_morphology_parity`.
