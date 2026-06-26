# TRACE-Net Engineering Gemma Draft Adapter v1 curl examples
# These commands are NOT run by the adapter.
# Running them manually will call the configured local model endpoint.

# engineering_gemma_draft_adapter_0001 / engineering_draft_packet_0001
curl -s http://127.0.0.1:11434/api/chat -H 'Content-Type: application/json' -d '@local_data\organization\trace_net\engineering_gemma_draft_adapter\request_payloads\engineering_draft_packet_0001_ollama_request.json' | python -m json.tool
