from __future__ import annotations

import py_compile


def test_scripts_compile() -> None:
    py_compile.compile("scripts/build/router/build_trace_net_e2e_query_planning_routing_v1.py", doraise=True)
    py_compile.compile("scripts/maintenance/benchmark/check_trace_net_e2e_query_planning_routing_v1_quality.py", doraise=True)


def test_module_imports() -> None:
    import tiff.trace_net_e2e_query_planning_routing_v1 as mod

    assert mod.STATUS_BUILT == "E2E_QUERY_PLANNING_ROUTING_BUILT"
    assert callable(mod.build_query_planning_routing)
