import importlib


def test_scripts_import():
    assert importlib.import_module("scripts.build.ocr.build_trace_net_fishnet_route_manifest_overlay_v1")
    assert importlib.import_module("scripts.maintenance.benchmark.check_trace_net_fishnet_route_manifest_overlay_v1_quality")


def test_module_import():
    mod = importlib.import_module("tiff.trace_net_fishnet_route_manifest_overlay_v1")
    assert mod.MODULE_NAME == "trace_net_fishnet_route_manifest_overlay_v1"
