from pathlib import Path

from scripts.migration.ingestion.apply_trace_net_h16d_conservative_retry_repair_v1 import (
    OPTION_MARKER,
    _patch_ollama_options,
    _remove_h16c_incomplete_calls,
    _remove_h16c_import_block,
)


def test_remove_h16c_incomplete_if_block():
    src = '''def f():\n    answer = "x"\n    if _h16c_looks_incomplete_llm_answer(answer):\n        raise RuntimeError("Ollama response looked incomplete or truncated")  # marker\n    return answer\n'''
    out, count = _remove_h16c_incomplete_calls(src)
    assert count == 1
    assert "_h16c_looks_incomplete_llm_answer" not in out
    assert "return answer" in out


def test_remove_h16c_import_block_simple():
    src = 'from tiff.trace_net_h16c_llm_answer_reliability_v1 import looks_incomplete_llm_answer as _h16c_looks_incomplete_llm_answer\n\ndef f():\n    return 1\n'
    out, count = _remove_h16c_import_block(src)
    assert count >= 1
    assert "trace_net_h16c" not in out


def test_patch_ollama_options_multiline_payload():
    src = '''def call():\n    payload = {\n        "model": model,\n        "prompt": prompt,\n        "stream": False,\n    }\n    return payload\n'''
    out, count, note = _patch_ollama_options(src)
    assert count == 1
    assert OPTION_MARKER in out
    assert '"num_predict": 900' in out
    assert '"temperature": 0.1' in out


def test_patch_ollama_options_removes_h16c_merge_call():
    src = '''def call():\n    payload = {\n        "model": model,\n        "prompt": prompt,\n        "stream": False,\n    }\n    payload = _h16c_merge_ollama_options(payload)\n    return payload\n'''
    out, count, note = _patch_ollama_options(src)
    assert count == 1
    assert "_h16c_merge_ollama_options" not in out
    assert OPTION_MARKER in out
