# TRACE-Net router proxy v6.1 q044 safety assert hotfix

This test-only hotfix updates the q044 regression test to read safety counts from either the top-level response shape or the nested `safety_contract` used by the internal fast-clarification payload. It does not modify router behavior.

Safety contract remains: read-only, no final answer permission, no source-truth mutation, and no Postgres/Qdrant/OpenSearch writes.
