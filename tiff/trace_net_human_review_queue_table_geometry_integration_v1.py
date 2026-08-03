"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.tables.trace_net_human_review_queue_table_geometry_integration_v1``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.tables.trace_net_human_review_queue_table_geometry_integration_v1")
