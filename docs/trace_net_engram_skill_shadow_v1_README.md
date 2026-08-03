# TRACE-Net H30 Phase 2 — Engram Skill Shadow v1

Phase 2 turns the validated Phase 1 skill cards into compact guidance bundles
and comparison diagnostics.

## Shadow-only contract

The skill bundle is attached after the current runtime finishes its work.

It does not change:

- query atoms;
- route selection;
- route plan;
- retrieval tunnels;
- evidence envelope;
- citations;
- current deterministic or Gemma answer;
- follow-up questions;
- safety gates.

The trace contains fingerprints proving that current behavior fields were
unchanged.

## Runtime stages

The bundle is attached at two points:

1. `cognitive_pre_writer` after retrieval and deterministic rendering;
2. `final_answer_writer` after the final deterministic/Gemma writing stage.

The public OpenWebUI trace therefore contains the final-answer comparison.

## Offline report

Existing Phase 0 `records.jsonl` files can be analyzed without rerunning any
questions:

```bash
python -B scripts/build_trace_net_engram_skill_shadow_report_v1.py \
  /data/trace_net_runs/cognitive_openwebui_h30_phase4_5_8_mature_v1/full_180/records.jsonl \
  --question-id q001 \
  --question-id q002 \
  --output-dir \
  /data/trace_net_runs/cognitive_openwebui_h30_phase4_5_8_mature_v1/full_180/engram_skill_shadow_q001_q002
```

For the first rollout gate, analyze Q001–Q020:

```bash
python -B scripts/build_trace_net_engram_skill_shadow_report_v1.py \
  /data/trace_net_runs/cognitive_openwebui_h30_phase4_5_8_mature_v1/full_180/records.jsonl \
  --limit 20
```

## Q001 expected diagnosis

- selected skill: `partial_identifier_discovery`;
- expected answer mode: `candidate_discovery`;
- generic candidate boilerplate detected;
- all five standard follow-up questions detected;
- shadow recommends exact partial-identifier retrieval first, candidate
  deduplication, match-reason explanations, and discriminating follow-ups.

## Phase 3 handoff

After the Q001–Q020 shadow report is reviewed, Phase 3 may allow the selected
skill to influence the validated planner. Answer writing remains shadow-only
until planner behavior passes its own targeted gate.
