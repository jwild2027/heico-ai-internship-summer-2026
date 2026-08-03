"""Compatibility shim (tiff reorganization). Moved to ``src.trace_net.visual.trace_net_image_diagram_fast_answer_composer_v1_check``.

Old ``tiff`` imports keep working: this re-exports the relocated module in full.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.visual.trace_net_image_diagram_fast_answer_composer_v1_check")
