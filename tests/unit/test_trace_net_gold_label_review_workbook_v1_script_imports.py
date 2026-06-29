import importlib


def test_script_modules_import():
    assert importlib.import_module("scripts.build_trace_net_gold_label_review_workbook_v1")
    assert importlib.import_module("scripts.check_trace_net_gold_label_review_workbook_v1_quality")
