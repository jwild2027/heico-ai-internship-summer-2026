"""Compatibility shim (repo reorg — reorg: s6_retrieval). Moved to ``src.trace_net.pipeline.s6_retrieval.search.trace_net_e2e_optional_tunnel_activator_v5``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s6_retrieval.search.trace_net_e2e_optional_tunnel_activator_v5")
