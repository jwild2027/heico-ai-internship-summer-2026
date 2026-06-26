# TRACE-Net Engineering Gemma Draft Adapter v1.1

Quality status: **PASS**

## Adapter config

- Provider: `ollama`
- Base URL: `http://127.0.0.1:11434`
- Model ID: `gemma4:26b`
- Ollama think: `False`
- Temperature: `0.0`
- Max output tokens: `700`

## Summary

- Adapter records: 1
- Request payloads written: 1
- Request payloads sent: 0
- Ready for final answer: 0
- Requires final gate after draft: 1
- Ollama think counts: `{'False': 1}`
- Source-truth evidence total: 14
- Candidate evidence total: 16

## Records

### engineering_gemma_draft_adapter_0001

- Question: `Find part number 120-29073-001 and nearby similar parts.`
- Provider: `ollama`
- Endpoint: `http://127.0.0.1:11434/api/chat`
- Model: `gemma4:26b`
- Ollama think: `False`
- Request payload: `local_data\organization\trace_net\engineering_gemma_draft_adapter\request_payloads\engineering_draft_packet_0001_ollama_request.json`
- Request sent: `False`
- Ready for final answer: `False`
