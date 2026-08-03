from __future__ import annotations

import importlib


def test_script_modules_import() -> None:
    assert importlib.import_module("scripts.build.visual.build_trace_net_table_visual_bbox_overlay_export_v1")
    assert importlib.import_module("scripts.maintenance.benchmark.check_trace_net_table_visual_bbox_overlay_export_v1_quality")


def test_core_modules_import() -> None:
    assert importlib.import_module("tiff.trace_net_table_visual_bbox_overlay_export_v1")
    assert importlib.import_module("tiff.trace_net_table_visual_bbox_overlay_export_v1_quality")
