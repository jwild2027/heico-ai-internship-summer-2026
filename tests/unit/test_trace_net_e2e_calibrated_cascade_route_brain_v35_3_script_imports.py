from __future__ import annotations

import importlib


def test_script_imports():
    importlib.import_module("scripts.build.engram.build_trace_net_e2e_calibrated_cascade_route_brain_v35_3")
    importlib.import_module("scripts.maintenance.s6_retrieval.check_trace_net_e2e_calibrated_cascade_route_brain_v35_3_quality")
