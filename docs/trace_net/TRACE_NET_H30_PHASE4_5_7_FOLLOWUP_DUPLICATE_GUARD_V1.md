# TRACE-Net H30 Phase 4.5.7 — Follow-up Duplicate Guard

## Problem

The live Phase 4.5.6 two-question smoke correctly rendered five distinct guided
follow-up questions. The answer-quality guard still failed both records with
`duplicate_followup_topics:2`.

The previous duplicate heuristic counted shared words appearing multiple times
in the complete answer. Words such as `part`, `number`, `remember`, and
`component` legitimately occur in different clarification questions, so shared
vocabulary was incorrectly treated as duplicated questions.

## Fix

The guard now:

- normalizes each complete follow-up question;
- counts exact normalized question occurrences in the normalized answer;
- reports a duplicate only when the same full question appears more than once;
- ignores shared vocabulary across different questions;
- continues detecting actual repeated full questions.

No routing, retrieval, writer, evidence, planner, or safety behavior changes.
