# TRACE-Net Fast Chat Runner Image Route Integration v1 — Anchor Fix

Focused fix for the Patch E integrator. Some local versions of `trace_net_fast_chat_runner_v1.py` keep the check function and CLI validation in a compact one-line style, so the first integrator could find every runtime anchor but fail on `check function image query validation`.

This fix makes the check-function and check-CLI edits whitespace/format tolerant. It does not rerun LLaVA and does not change source-truth artifacts. Safety remains no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
