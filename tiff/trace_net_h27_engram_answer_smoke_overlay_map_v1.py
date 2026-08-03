"""Compatibility shim (tiff reorganization). Moved to ``scripts/benchmark/trace_net_h27_engram_answer_smoke_overlay_map_v1.py``.

Loads the relocated module by file path so old ``tiff`` imports keep working
even though the destination is outside an import package.
"""
import importlib.util as _u
import sys as _s
from pathlib import Path as _P

_target = _P(__file__).resolve().parent.parent / "scripts/benchmark/trace_net_h27_engram_answer_smoke_overlay_map_v1.py"
_spec = _u.spec_from_file_location(__name__, str(_target))
_mod = _u.module_from_spec(_spec)
_s.modules[__name__] = _mod
_spec.loader.exec_module(_mod)
