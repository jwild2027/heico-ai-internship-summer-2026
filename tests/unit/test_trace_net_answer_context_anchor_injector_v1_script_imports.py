import importlib


def test_build_script_imports():
    assert importlib.import_module("scripts.build_trace_net_answer_context_anchor_injector_v1")


def test_check_script_imports():
    assert importlib.import_module("scripts.check_trace_net_answer_context_anchor_injector_v1_quality")
