from __future__ import annotations

import importlib


def test_module_and_scripts_import() -> None:
    assert importlib.import_module("tiff.trace_net_image_visual_summary_v1")
    assert importlib.import_module("scripts.build.visual.build_trace_net_image_visual_summary_v1")
    assert importlib.import_module("scripts.maintenance.visual.check_trace_net_image_visual_summary_v1_quality")
