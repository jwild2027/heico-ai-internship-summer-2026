"""Compatibility shim (repo reorg — reorg: s6_retrieval). Moved to ``src.trace_net.pipeline.s6_retrieval.context_build.trace_net_v2_summary_guidance_index_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s6_retrieval.context_build.trace_net_v2_summary_guidance_index_v1")
