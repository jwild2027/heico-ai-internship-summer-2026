"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.visual.trace_net_e2e_corrected_visual_context_builder_v35_4``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.visual.trace_net_e2e_corrected_visual_context_builder_v35_4")
