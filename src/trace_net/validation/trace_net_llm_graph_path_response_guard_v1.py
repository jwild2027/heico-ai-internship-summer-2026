"""Compatibility shim (repo reorg — reorg: validation). Moved to ``src.trace_net.validation.graph_path_guards.trace_net_llm_graph_path_response_guard_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.validation.graph_path_guards.trace_net_llm_graph_path_response_guard_v1")
