# TRACE-Net Artifact Dependency Registry v1 Cycle Fix

This patch fixes an artificial dependency cycle in the registry dependency map.

## What changed

`page_retrieval_profiles` is an upstream route/search artifact used by the Page Element Registry. The previous dependency map made it depend on `page_element_registry`, while `page_element_registry` also depends on `page_retrieval_profiles`, creating an artificial cycle.

The corrected dependency is:

```text
page_retrieval_profiles -> context_retrieval_helpers
page_element_registry -> page_retrieval_profiles, embedding_candidates, evidence_consensus
```

This preserves the actual pipeline direction and removes the cycle.

The patch also excludes generated OpenSearch mapping files like:

```text
trace_net_opensearch_mapping_v1.json
```

from being treated as primary build artifacts.

## Safety

The registry remains read-only:

```text
no Postgres writes
no Qdrant writes
no OpenSearch writes
no source truth mutation
no direct answer permission
no claim proof permission
```
