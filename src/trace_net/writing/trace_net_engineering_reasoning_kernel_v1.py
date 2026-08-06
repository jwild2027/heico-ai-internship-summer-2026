"""Compatibility shim (repo reorg — reorg: writing). Moved to ``src.trace_net.writing.orchestration.trace_net_engineering_reasoning_kernel_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.writing.orchestration.trace_net_engineering_reasoning_kernel_v1")
