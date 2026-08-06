"""Compatibility shim (repo reorg — reorg: s2_ocr). Moved to ``src.trace_net.pipeline.s2_ocr.table_ocr.direct_evidence.quality.trace_net_table_presence_verifier_v1_quality``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.pipeline.s2_ocr.table_ocr.direct_evidence.quality.trace_net_table_presence_verifier_v1_quality")
