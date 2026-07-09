# TRACE-Net real answer overlay question-id aligner v1

This module builds a real-answer-smoke-compatible Engram overlay map whose records are keyed to the exact `question_id` values emitted by the real answer smoke manifest.

Purpose:

- Real answer smoke emits question IDs such as `q01`.
- Earlier Engram overlay smokes emitted standalone query IDs.
- The answer-runner overlay context pack matches overlays by question ID.
- This adapter creates a safe, question-ID-aligned overlay map so the normal real-answer CLI can prove the overlay channel attaches to the same real-smoke question.

Safety contract:

- Engram overlay text is behavior guidance only.
- It is not proof.
- It grants no answer permission.
- It does not mutate source truth.
- It performs no Postgres, Qdrant, OpenSearch, or upload writes.

The adapter can copy a source overlay when question ID or question text matches. When there is no matching source overlay, it creates a safe fallback guidance overlay for that real-answer question ID, explicitly labeled as guidance only.
