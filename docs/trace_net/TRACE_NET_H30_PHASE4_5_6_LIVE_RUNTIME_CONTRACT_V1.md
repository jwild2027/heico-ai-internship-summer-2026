# TRACE-Net H30 Phase 4.5.6 — Live Runtime Contract

## Problem

The Phase 4.5.5 unit and static gates passed, but the live two-question smoke
showed two installed-wrapper mismatches:

1. A mature planner-adopted part route used the Phase 4.3 bounded
   source-resolution tunnel while the returned executor plan omitted that tunnel.
2. The native Ollama timing/streaming overlay replaced the base writer
   `Runtime.process` method and therefore bypassed visible guided follow-up
   rendering.

## Fix

- The executor-owned mature tunnel registry now includes:
  - `phase4_3_exact_source_resolution`
  - `phase4_3_candidate_source_resolution`
- The native writer wrapper appends deterministic guided follow-ups after the
  engineer answer contract has formatted the answer.
- The wrapper reports how many follow-up questions are visible.
- Regression tests exercise the installed native wrapper rather than only the
  base writer implementation.

## Safety

The planner still cannot execute tools or select evidence. The executor remains
the owner of tunnel selection. Candidate evidence remains guidance only. No
answer permission or source-truth mutation is introduced.
