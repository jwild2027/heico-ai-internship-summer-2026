# TRACE-Net H38C Diversity Task Repair Runner v1

H38C consumes the H37C diversity planner, runs the custom tasks, and retries once with a task-specific repair prompt when a contract fails.

Repairs issues observed in H38:
- q02 safe boundary language with "nor can it confirm" was falsely flagged
- q04 could return no citations / cut off
- q05 quiz could be inline-numbered and still not counted
- q05 could ask internal LLaVA/visual-authority questions

Safety contract:
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
