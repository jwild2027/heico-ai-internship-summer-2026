from __future__ import annotations

import importlib


def test_script_imports():
    importlib.import_module("scripts.build_trace_net_e2e_corrected_visual_context_builder_v35_4")
    importlib.import_module("scripts.check_trace_net_e2e_corrected_visual_context_builder_v35_4_quality")
