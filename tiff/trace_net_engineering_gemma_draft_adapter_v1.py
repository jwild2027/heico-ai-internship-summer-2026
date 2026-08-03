"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.writing.trace_net_engineering_gemma_draft_adapter_v1``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.writing.trace_net_engineering_gemma_draft_adapter_v1")
