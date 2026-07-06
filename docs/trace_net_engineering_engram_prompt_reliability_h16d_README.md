# TRACE-Net H16D Conservative Engram Smoke Reliability Repair

H16C fixed q18 in isolation but made the full 30-question smoke less stable by treating too many normal answers as incomplete and forcing retry/fallback.

H16D restores the pre-H16C smoke runner from the automatic H16C backup when available, removes aggressive `_h16c_looks_incomplete_llm_answer(...)` call sites, and applies only conservative Ollama generation options:

- `num_predict=900`
- `temperature=0.1`

The question-bank filter tool is retained for targeted reruns.

Safety contract: no DB writes, no vector/search writes, no source-truth mutation, no answer permission. Engram memory remains guidance only; proof still comes from `proof_context` citations.
