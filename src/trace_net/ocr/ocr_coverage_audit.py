"""Compatibility shim (repo reorg — reorg: s2_ocr). Moved to ``src.trace_net.pipeline.s2_ocr.quality.ocr_coverage_audit``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s2_ocr.quality.ocr_coverage_audit")
