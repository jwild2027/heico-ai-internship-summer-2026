"""Compatibility shim (repo reorg — reorg: serving). Moved to ``src.trace_net.serving.api.trace_net_ask_api_hybrid_v3_routing_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.serving.api.trace_net_ask_api_hybrid_v3_routing_v1")
