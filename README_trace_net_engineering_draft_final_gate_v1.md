# TRACE-Net Engineering Draft Final Gate v1.1

Evaluates Gemma draft-runner outputs before any response is allowed out.

v1.1 adds negation-aware risky phrase scanning:
- blocks asserted risky claims like "this is an approved replacement"
- allows boundary language like "this does not claim approved replacement"
- records raw, blocked, and negated risky phrase hits separately

This fixes false positives where the Do-not-claim section used risky phrases while explicitly denying them.

Safety:
- no LLM calls
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
- no direct answer permission
