from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/trace_net_h30_cold_start_streaming_v1.py")
LAUNCHER_PATH = Path("scripts/launch_trace_net_cognitive_openwebui_v1.sh")
WRITER_PATH = Path("scripts/serve_trace_net_full_gemma_cognitive_v1.py")
BRIDGE_PATH = Path("scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("trace_net_h30_cold_start_streaming_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_native_ollama_base_removes_only_v1_suffix():
    mod = load_module()
    assert mod.native_ollama_base("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert mod.native_ollama_base("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_native_payload_has_keep_alive_and_streaming_metrics_path():
    mod = load_module()
    payload = mod.native_chat_payload(
        model="gemma4:26b",
        messages=[{"role": "user", "content": "test"}],
        keep_alive="1h",
    )
    assert payload["keep_alive"] == "1h"
    assert payload["stream"] is True
    assert payload["options"]["temperature"] == 0


def test_ndjson_buffer_collects_answer_and_final_metrics():
    mod = load_module()
    ticks = iter([10.25])
    answer, final, first_ms = mod.consume_ollama_ndjson(
        [
            json.dumps({"message": {"content": "Hello "}, "done": False}),
            json.dumps({"message": {"content": "world"}, "done": False}),
            json.dumps({
                "message": {"content": ""},
                "done": True,
                "load_duration": 2_000_000_000,
                "prompt_eval_duration": 500_000_000,
                "eval_duration": 1_000_000_000,
                "total_duration": 3_500_000_000,
                "prompt_eval_count": 100,
                "eval_count": 20,
            }),
        ],
        started_at=10.0,
        clock=lambda: next(ticks),
    )
    assert answer == "Hello world"
    assert final["done"] is True
    assert first_ms == 250.0
    timing = mod.ollama_timing(final, first_token_ms=first_ms, transport_ms=3600.0)
    assert timing["ollama_load_ms"] == 2000.0
    assert timing["ollama_prompt_eval_ms"] == 500.0
    assert timing["ollama_generation_ms"] == 1000.0
    assert timing["ollama_generation_tokens_per_second"] == 20.0


def test_sse_chunks_are_openai_compatible_and_include_timing():
    mod = load_module()
    role = mod.sse_role_chunk("model", "id", 1).decode()
    content = mod.sse_content_chunk("model", "id", 1, "hello").decode()
    finish = mod.sse_finish_chunk("model", "id", 1, {"router_retrieval_ms": 12.3}).decode()
    assert "chat.completion.chunk" in role
    assert '"role": "assistant"' in role
    assert '"content": "hello"' in content
    assert "trace_net_timing" in finish
    assert "upstream_sse_with_validated_answer_release" in finish


def test_launcher_preloads_model_and_exports_one_hour_keep_alive():
    text = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert 'TRACE_NET_GEMMA_KEEP_ALIVE:-1h' in text
    assert '/api/generate' in text
    assert '"prompt": ""' in text
    assert 'gemma_preload_status=PASS' in text
    assert 'TRACE_NET_GEMMA_KEEP_ALIVE="$GEMMA_KEEP_ALIVE"' in text


def test_writer_installs_native_latency_support_before_main():
    text = WRITER_PATH.read_text(encoding="utf-8")
    assert "install_gemma_latency_support" in text
    assert text.index("install_gemma_latency_support(globals())") < text.index('if __name__ == "__main__"')


def test_bridge_installs_upstream_sse_passthrough_before_main():
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    assert "install_bridge_streaming_support" in text
    assert text.index("install_bridge_streaming_support(globals())") < text.index('if __name__ == "__main__"')


def test_patch_does_not_change_answer_permission_contract():
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert '"answer_permission": False' in text
    assert '"final_answer_allowed": False' in text
    assert '"source_truth_mutation_allowed": False' in text
    assert '"raw_unvalidated_tokens_exposed": False' in text


def test_bridge_proxy_is_line_streamed_and_connection_closes_cleanly():
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "for line in response:" in text
    assert "response.read(4096)" not in text
    assert 'self.send_header("Connection", "close")' in text
    assert "X-Trace-Net-Bridge-Time-To-First-Byte-Ms" in text
