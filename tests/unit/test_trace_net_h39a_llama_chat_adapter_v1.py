from scripts.build.visual.build_trace_net_h39a_whole_page_vision_summary_llama_chat_v1 import _chat_url


def test_chat_url_rewrites_generate_endpoint():
    assert _chat_url("http://127.0.0.1:11434/api/generate") == "http://127.0.0.1:11434/api/chat"


def test_chat_url_keeps_chat_endpoint():
    assert _chat_url("http://127.0.0.1:11434/api/chat") == "http://127.0.0.1:11434/api/chat"


def test_chat_url_appends_chat_endpoint():
    assert _chat_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434/api/chat"
