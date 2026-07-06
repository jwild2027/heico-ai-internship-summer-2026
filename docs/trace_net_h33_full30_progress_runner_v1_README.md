# TRACE-Net H33 Full-30 Progress Runner v1

Runs the real engineering LLM answer smoke through a wrapper that:

1. Builds a per-question H33 answer-budget overlay map.
2. Passes the map through `--engram-answer-runner-overlay-map`.
3. Prints a progress line after each answer file is written.

Safety contract: artifact/local wrapper only. It does not create proof, grant answer permission, mutate source truth, or perform live Postgres/Qdrant/OpenSearch/graph IO.

The overlay is behavior guidance only. Factual claims still require current `proof_context` citations.
