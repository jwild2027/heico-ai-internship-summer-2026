# TRACE-Net H39A Llama Chat Adapter v1

This adapter keeps H39A as-is but calls Ollama vision through `/api/chat`
instead of `/api/generate`.

Why:
- User wants Llama-only vision, no Qwen/Qwen-VL.
- H39A already correctly converts TIFF pages to JPEG.
- Llama 3.2 Vision/mllama image messages are safer through `messages[].images`.

Safety contract:
- same as H39A
- no source-truth mutation
- no answer permission
- no DB/vector/search writes
