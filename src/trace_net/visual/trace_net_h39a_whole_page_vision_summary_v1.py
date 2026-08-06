"""Compatibility shim (repo reorg — reorg: visual). Moved to ``src.trace_net.visual.observers.trace_net_h39a_whole_page_vision_summary_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.visual.observers.trace_net_h39a_whole_page_vision_summary_v1")
