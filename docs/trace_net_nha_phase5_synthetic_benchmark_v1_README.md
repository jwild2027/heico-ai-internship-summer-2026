# TRACE-Net NHA Phase N5 Synthetic Benchmark V1

Phase N5 generates a deterministic, benchmark-only overlay for project-, configuration-, revision-, hierarchy-, conflict-, and negative NHA cases.

## Isolation contract

- Does not modify TIFF pages or OCR.
- Does not mutate N0-N4 artifacts.
- Does not write Postgres, Qdrant, OpenSearch, or the production graph.
- Uses reserved synthetic part numbers under `990-xxxxx-xxx`.
- Uses only `BENCHMARK_*` graph edges.
- Synthetic traits are assigned to real page identifiers only as retrieval-test anchors; the physical pages are not claimed to contain those traits.
- The overlay is disabled by default.

## Canonical benchmark

- Fixed seed: `TRACE_NET_NHA_SYNTHETIC_SEED_V1_20260729`
- 30 scenarios
- 66 synthetic relationships
- 68 unique synthetic page assignments
- 60 questions and 60 machine-readable answer-key cases

Case types: simple direct NHA, three-hop chain, direct children, mixed direct/descendant trees, project-scoped parents, revision changes, attaching parts, contradictions, and no-NHA controls.
