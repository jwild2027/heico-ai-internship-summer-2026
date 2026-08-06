"""Compatibility shim (repo reorg — reorg: visual). Moved to ``src.trace_net.visual.answer_composer.trace_net_image_diagram_fast_answer_composer_v1_check``.

Importing from this old path keeps working: it re-exports the relocated module in full.
Update imports to the new path when convenient.
"""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("src.trace_net.visual.answer_composer.trace_net_image_diagram_fast_answer_composer_v1_check")
