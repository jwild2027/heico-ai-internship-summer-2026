from scripts.operations.serving.start_trace_net_openwebui_e2e_v1 import (
    endpoint_ask_url,
    endpoint_chat_url,
    endpoint_health_url,
    openai_base_url_for_openwebui,
    openai_base_url_for_windows,
    openwebui_url,
    summarize_chat_response,
)


def test_urls():
    assert endpoint_health_url("127.0.0.1", 8014) == "http://127.0.0.1:8014/health"
    assert endpoint_chat_url("127.0.0.1", 8014) == "http://127.0.0.1:8014/v1/chat/completions"
    assert endpoint_ask_url("127.0.0.1", 8014) == "http://127.0.0.1:8014/api/trace-net/ask"
    assert openwebui_url(3000) == "http://localhost:3000"


def test_openwebui_connection_urls():
    assert openai_base_url_for_openwebui(8014) == "http://host.docker.internal:8014/v1"
    assert openai_base_url_for_windows(8014) == "http://127.0.0.1:8014/v1"


def test_summarize_chat_response():
    data = {"choices": [{"message": {"content": "hello world"}}]}
    assert summarize_chat_response(data) == "hello world"
