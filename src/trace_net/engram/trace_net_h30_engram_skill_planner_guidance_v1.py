"""Compatibility shim (repo reorg — reorg: s5_engram). Moved to ``src.trace_net.pipeline.s5_engram.skills.trace_net_h30_engram_skill_planner_guidance_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s5_engram.skills.trace_net_h30_engram_skill_planner_guidance_v1")
