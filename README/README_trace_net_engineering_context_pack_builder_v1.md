# TRACE-Net Engineering Context Pack Builder v1.2

Fills engineering context-pack blueprints with available TRACE-Net artifact evidence capsules.

v1.2:
- optional missing artifact paths do not crash the build
- missing optional inputs are recorded in summary.artifact_missing_inputs
- recursive nested artifact parsing remains from v1.1
- high-signal and fallback evidence remain separated

No LLM calls, no live retrieval execution, no DB writes, no source-truth mutation, no answer permission.
