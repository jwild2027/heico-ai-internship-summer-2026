"""Compatibility shim (repo reorg — reorg: s3_graph_store). Moved to ``src.trace_net.pipeline.s3_graph_store.nha.trace_net_nha_phase5_synthetic_benchmark_v1``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s3_graph_store.nha.trace_net_nha_phase5_synthetic_benchmark_v1")
