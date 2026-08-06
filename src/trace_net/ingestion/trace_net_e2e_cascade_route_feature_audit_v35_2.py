"""Compatibility shim (repo reorg — reorg: ingestion). Moved to ``src.trace_net.ingestion.page_routing.trace_net_e2e_cascade_route_feature_audit_v35_2``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.ingestion.page_routing.trace_net_e2e_cascade_route_feature_audit_v35_2")
