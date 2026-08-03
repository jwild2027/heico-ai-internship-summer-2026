import importlib


def test_script_imports():
    assert importlib.import_module("scripts.benchmark.validation.build_trace_net_fast_chat_multi_route_quality_gate_v1")
    assert importlib.import_module("scripts.benchmark.check_trace_net_fast_chat_multi_route_quality_gate_v1_quality")
