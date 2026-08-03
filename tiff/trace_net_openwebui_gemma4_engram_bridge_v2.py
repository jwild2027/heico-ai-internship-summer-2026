"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.serving.trace_net_openwebui_gemma4_engram_bridge_v2``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.serving.trace_net_openwebui_gemma4_engram_bridge_v2")
