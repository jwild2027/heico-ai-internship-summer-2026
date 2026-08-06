# TRACE-Net Engram Overlay Steps 2-5 Patch v1

This ZIP is an applicator patch. Put it under your repo, then run `python patches/trace_net_engram_overlay_steps_2_5_v1/APPLY_ME.py` from the repo root.

It adds:
- `tiff/trace_net_engineering_answer_runner_overlay_context_pack_v1.py`
- `scripts/build_trace_net_engineering_answer_runner_overlay_context_pack_v1.py`
- `scripts/check_trace_net_engineering_answer_runner_overlay_context_pack_v1.py`
- `tiff/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_complete_v1.py`
- `scripts/check_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_complete_v1.py`
- unit tests for both pieces
- a conservative H25 retry prompt hardening if the current module has the old generic retry text

Safety contract:
- no live DB/vector writes
- answer_permission remains false
- source_truth_mutation_allowed remains false
- Engram overlay is guidance-only, never proof
- V2/V3 route hints are guidance-only, never proof
