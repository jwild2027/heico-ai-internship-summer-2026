# TRACE-Net H38 Diversity Task Runner v1

H38 consumes the cleaned H37C diversity planner output and runs the five custom complex tasks using the selected diverse cards.

It is designed to test whether q03/q05 improve after diversity planning.

Features:

- uses H37 selected evidence cards as proof_context candidates
- direct Ollama or artifact mode
- progress line after every question
- retry on empty Ollama response
- validates fallback, citations, quiz structure, metadata quiz items, answer length, and unsafe boundary claims

Safety contract:

- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
