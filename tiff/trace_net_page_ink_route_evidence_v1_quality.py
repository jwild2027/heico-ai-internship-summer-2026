"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.ingestion.quality.trace_net_page_ink_route_evidence_v1_quality``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.ingestion.quality.trace_net_page_ink_route_evidence_v1_quality")
