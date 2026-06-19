import importlib


def test_script_imports():
    assert importlib.import_module("scripts.build_trace_net_table_detector_overlay_verdict_ingest_v1")
    assert importlib.import_module("scripts.check_trace_net_table_detector_overlay_verdict_ingest_v1_quality")
    assert importlib.import_module("tiff.trace_net_table_detector_overlay_verdict_ingest_v1")
    assert importlib.import_module("tiff.trace_net_table_detector_overlay_verdict_ingest_v1_quality")
