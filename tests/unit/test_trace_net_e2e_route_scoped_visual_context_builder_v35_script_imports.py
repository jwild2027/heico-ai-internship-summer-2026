from __future__ import annotations

import importlib


def test_script_imports() -> None:
    importlib.import_module("scripts.build.visual.build_trace_net_e2e_route_scoped_visual_context_builder_v35")
    importlib.import_module("scripts.maintenance.visual.check_trace_net_e2e_route_scoped_visual_context_builder_v35_quality")
    importlib.import_module("tiff.trace_net_e2e_route_scoped_visual_context_builder_v35")
