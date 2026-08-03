# TRACE-Net H30 Phase 2.1

This corrective patch completes the Phase 2 gate.

## Repairs

1. Empty dataclass fields such as `manufacturer=None` no longer become positive
   skill-selection atoms.
2. The skill-shadow wrapper is installed in the cognitive router and final
   Gemma writer.
3. The launcher passes shadow settings to both services.
4. Regression tests verify Q001 selects only
   `partial_identifier_discovery`.

## Expected corrected Q001–Q020 count

```text
partial_identifier_discovery=20
manufacturer_plus_description_discovery=0
```

This remains shadow-only and does not alter answers, routes, retrieval,
evidence, citations, or safety gates.
