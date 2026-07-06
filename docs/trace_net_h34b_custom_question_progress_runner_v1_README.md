# TRACE-Net H34B Custom Question Progress Runner v1

Runs five custom user-facing questions directly against evidence cards extracted from TRACE-Net artifacts instead of reusing old answer-smoke question templates.

Why this exists: changing only the question text in an old answer-smoke question bank can leave the old proof-context/fallback behavior intact, causing different custom questions to receive the same canned fallback answer. H34B builds a fresh evidence-card prompt per custom question.

Safety contract: evidence cards are proof_context; Engram/vector/feedback guidance is behavior-only and not proof. No DB/vector/search writes, no source-truth mutation, no answer permission.
