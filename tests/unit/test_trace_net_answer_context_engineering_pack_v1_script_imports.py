import importlib


def test_script_modules_import():
    importlib.import_module("scripts.build_trace_net_answer_context_engineering_pack_v1")
    importlib.import_module("scripts.check_trace_net_answer_context_engineering_pack_v1_quality")
