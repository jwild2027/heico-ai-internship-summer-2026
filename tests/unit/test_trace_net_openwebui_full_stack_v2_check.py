from __future__ import annotations
import importlib.util, sys
from pathlib import Path

SCRIPT = Path("scripts/maintenance/serving/check_trace_net_openwebui_full_stack_v2.py")

def load():
    spec = importlib.util.spec_from_file_location("checker_v2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["checker_v2"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

def test_trace_from_openai():
    mod = load()
    assert mod.trace_from_openai({"trace_net":{"route":"normal_ask"}})["route"] == "normal_ask"
    assert mod.trace_from_openai({}) == {}
