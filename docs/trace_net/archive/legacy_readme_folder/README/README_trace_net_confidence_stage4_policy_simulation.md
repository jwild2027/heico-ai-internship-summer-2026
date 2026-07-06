# TRACE-Net Layer Confidence Stage 4 Policy Simulation

Stage 4 safely simulates the Stage 3 layer-specific confidence policy against the current Evidence Consensus records.

It answers:

```text
If this policy controlled trust/RAG/repair recommendations, what would change?
Would any unsafe record enter RAG?
Would source_trace remain A?
Would table_candidate stay excluded from direct RAG?
Would visual_text remain capped at B?
```

It does not modify Evidence Consensus, trust traits, RAG artifacts, or graph artifacts.

## Run

```bash
python scripts/simulate_trace_net_confidence_policy.py --open
```

Then quality:

```bash
python scripts/check_trace_net_confidence_stage4_quality.py \
  --write-json \
  --min-records 1813 \
  --min-pages 509 \
  --min-source-trace-policy-A-records 509 \
  --max-unsafe-policy-rag-include-records 0 \
  --max-table-candidate-direct-rag-records 0 \
  --max-visual-text-above-B-records 0
```

## Outputs

```text
local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation.json
local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation.md
local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation.html
local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation_quality.json
```

## Interpretation

This is still simulation-only. Stage 5 can use the simulation to decide which low-risk layers can start using the policy for routing.
