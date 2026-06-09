# TRACE-Net Community Ablation Evaluation

Status: **OK**

## Summary

- `pages_loaded`: 509
- `projection_nodes`: 1856
- `projection_edges`: 12363
- `algorithm_count`: 4
- `available_algorithm_count`: 4
- `leiden_available`: True
- `best_repair_batching_algorithm`: route_grouping
- `best_repair_batching_score`: 0.959966
- `best_retrieval_expansion_algorithm`: leiden
- `best_retrieval_expansion_score`: 0.899821
- `leiden_vs_route_repair_delta`: -0.114817
- `leiden_vs_route_retrieval_delta`: 0.014623
- `leiden_vs_no_community_repair_delta`: 0.143336
- `leiden_vs_no_community_retrieval_delta`: 0.249821

## Algorithm Comparison

| Algorithm | Available | Communities | Largest pages | Largest ratio | Route purity | Table purity | Repair score | Retrieval score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_community | True | 509 | 1 | 0.001965 | 1.0 | 1.0 | 0.701813 | 0.65 |
| route_grouping | True | 4 | 314 | 0.616896 | 1.0 | 1.0 | 0.959966 | 0.885198 |
| networkx_greedy_modularity | True | 17 | 277 | 0.544204 | 1.0 | 0.917485 | 0.896215 | 0.846756 |
| leiden | True | 18 | 194 | 0.381139 | 1.0 | 0.852652 | 0.845149 | 0.899821 |

## Interpretation

Use Leiden only if it improves a downstream task. If route grouping beats Leiden for repair batching, use route grouping for that job and keep Leiden for exploration/community summaries.

Core source tracing should never depend on communities; it should continue to use deterministic graph traversal.
