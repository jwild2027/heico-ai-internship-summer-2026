import importlib


def test_script_modules_import():
    importlib.import_module("scripts.build.tables.build_trace_net_table_detector_overlay_review_pack_v1")
    importlib.import_module("scripts.maintenance.s2_ocr.check_trace_net_table_detector_overlay_review_pack_v1_quality")
