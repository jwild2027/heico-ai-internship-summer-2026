"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.graph.trace_net_graph_overlay_part_property_normalizer_v1``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.graph.trace_net_graph_overlay_part_property_normalizer_v1")
