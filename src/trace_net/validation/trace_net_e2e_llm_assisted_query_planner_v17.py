"""Compatibility shim (repo reorg — reorg: validation). Moved to ``src.trace_net.validation.query_context.trace_net_e2e_llm_assisted_query_planner_v17``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.validation.query_context.trace_net_e2e_llm_assisted_query_planner_v17")
