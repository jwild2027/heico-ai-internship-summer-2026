# TRACE-Net Engineering Gemma Draft Runner v1

Controlled local runner for Gemma/Ollama draft payloads.

Default mode is dry-run validation:
- reads adapter request payloads
- writes empty draft response artifacts
- sends no network/model requests

Execution mode:
- use `--execute` to POST the prepared payload to the configured local model endpoint
- saves the raw model response and extracted draft text
- still does not grant final answer permission

Safety:
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
- no direct answer permission
- final gate is required after any draft response
