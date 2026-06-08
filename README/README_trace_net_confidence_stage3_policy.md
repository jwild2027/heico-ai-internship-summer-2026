# TRACE-Net Layer Confidence Stage 3 Policy

This patch materializes the Stage 3 layer-specific confidence policy.

Stage 1 wrote advisory confidence scores to Evidence Consensus. Stage 2 compared those score-derived tiers against rule-based trust tiers. Stage 3 stores a measured, layer-specific policy so future code can interpret confidence differently for different evidence layers.

It writes:

```text
local_data/organization/trace_net/confidence/trace_lc_confidence_policy.json
local_data/organization/trace_net/confidence/trace_lc_confidence_policy_report.md
local_data/organization/trace_net/confidence/trace_lc_confidence_policy_report.html
local_data/organization/trace_net/confidence/trace_lc_confidence_policy_quality.json
```

Run:

```bash
python scripts/build_trace_net_confidence_policy.py --require-stage2 --open
python scripts/check_trace_net_confidence_policy_quality.py --write-json
```

The policy keeps routing safe:

```text
source_trace: source truth; A allowed when source artifacts exist
part_catalog: verified part evidence; A allowed with source/catalog support
table_tile_text_refined: derived table context; B allowed with catalog-supported parts
visual_text: conservative model-derived context; max auto tier B
table_candidate: routing signal only; no direct RAG include
table_tiles: preprocessing artifact only; no direct RAG include
```

This does not yet override Evidence Consensus routing. It is the config/report layer needed before layer-specific confidence can be tested as a routing input.
