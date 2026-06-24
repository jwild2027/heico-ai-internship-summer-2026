from __future__ import annotations

import importlib


def test_script_imports():
    importlib.import_module("scripts.build_trace_net_e2e_cascade_route_feature_audit_v35_2")
    importlib.import_module("scripts.check_trace_net_e2e_cascade_route_feature_audit_v35_2_quality")
