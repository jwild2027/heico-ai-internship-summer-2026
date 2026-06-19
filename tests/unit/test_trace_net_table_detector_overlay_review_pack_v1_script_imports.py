import importlib


def test_script_modules_import():
    importlib.import_module("scripts.build_trace_net_table_detector_overlay_review_pack_v1")
    importlib.import_module("scripts.check_trace_net_table_detector_overlay_review_pack_v1_quality")
