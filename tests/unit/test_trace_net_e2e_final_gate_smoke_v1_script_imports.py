from __future__ import annotations

import py_compile
from pathlib import Path


def test_scripts_compile() -> None:
    py_compile.compile("scripts/build_trace_net_e2e_final_gate_smoke_v1.py", doraise=True)
    py_compile.compile("scripts/check_trace_net_e2e_final_gate_smoke_v1_quality.py", doraise=True)


def test_module_imports() -> None:
    import tiff.trace_net_e2e_final_gate_smoke_v1 as mod

    assert mod.STATUS_BUILT == "E2E_FINAL_GATE_SMOKE_BUILT"
    assert callable(mod.build_final_gate_smoke)
