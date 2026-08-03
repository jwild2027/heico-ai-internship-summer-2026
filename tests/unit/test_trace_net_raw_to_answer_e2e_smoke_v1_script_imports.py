import importlib


def test_scripts_import():
    assert importlib.import_module("scripts.benchmark.run_trace_net_raw_to_answer_e2e_smoke_v1")
    assert importlib.import_module("scripts.benchmark.check_trace_net_raw_to_answer_e2e_smoke_v1_quality")
