import importlib


def test_script_modules_import():
    importlib.import_module("scripts.build_trace_net_table_ocr_bbox_enrichment_v1")
    importlib.import_module("scripts.check_trace_net_table_ocr_bbox_enrichment_v1_quality")
    importlib.import_module("tiff.trace_net_table_ocr_bbox_enrichment_v1")
    importlib.import_module("tiff.trace_net_table_ocr_bbox_enrichment_v1_quality")
