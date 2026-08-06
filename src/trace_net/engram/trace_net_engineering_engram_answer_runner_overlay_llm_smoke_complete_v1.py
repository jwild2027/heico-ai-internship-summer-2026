"""Compatibility shim (repo reorg — reorg: s5_engram). Moved to ``src.trace_net.pipeline.s5_engram.smoke.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_complete_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s5_engram.smoke.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_complete_v1")
