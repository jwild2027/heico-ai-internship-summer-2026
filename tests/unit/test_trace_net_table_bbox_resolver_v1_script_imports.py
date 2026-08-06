import importlib


def test_scripts_import():
    importlib.import_module("scripts.build.tables.build_trace_net_table_bbox_resolver_v1")
    importlib.import_module("scripts.maintenance.s2_ocr.check_trace_net_table_bbox_resolver_v1_quality")


def test_modules_import():
    importlib.import_module("tiff.trace_net_table_bbox_resolver_v1")
    importlib.import_module("tiff.trace_net_table_bbox_resolver_v1_quality")
