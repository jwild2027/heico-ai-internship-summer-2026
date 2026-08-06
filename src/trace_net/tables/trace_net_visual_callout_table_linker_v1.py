"""Compatibility shim (repo reorg — reorg: visual). Moved to ``src.trace_net.visual.callout_linker.trace_net_visual_callout_table_linker_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.visual.callout_linker.trace_net_visual_callout_table_linker_v1")
