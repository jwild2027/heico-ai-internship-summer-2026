import importlib


def test_script_modules_import():
    assert importlib.import_module("scripts.build.ingestion.build_trace_net_gold_label_review_workbook_v1")
    assert importlib.import_module("scripts.maintenance.benchmark.check_trace_net_gold_label_review_workbook_v1_quality")
