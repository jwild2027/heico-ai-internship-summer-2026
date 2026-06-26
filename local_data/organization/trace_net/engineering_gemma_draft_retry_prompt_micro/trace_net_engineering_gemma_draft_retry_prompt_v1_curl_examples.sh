# TRACE-Net Engineering Gemma Draft Retry Prompt v1.1 curl examples
# These commands are NOT run by the retry prompt builder.

# engineering_gemma_draft_retry_prompt_0001 / engineering_draft_packet_0001
curl -s http://127.0.0.1:11434/api/chat -H 'Content-Type: application/json' -d '@local_data\organization\trace_net\engineering_gemma_draft_retry_prompt_micro\request_payloads\engineering_gemma_draft_retry_0001_ollama_request.json' | python -m json.tool
