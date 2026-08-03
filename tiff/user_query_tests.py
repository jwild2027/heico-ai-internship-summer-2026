"""Compatibility shim (tiff reorganization). Moved to ``tests/integration/user_query_tests.py``.

Loads the relocated module by file path so old ``tiff`` imports keep working
even though the destination is outside an import package.
"""
import importlib.util as _u
import sys as _s
from pathlib import Path as _P

_target = _P(__file__).resolve().parent.parent / "tests/integration/user_query_tests.py"
_spec = _u.spec_from_file_location(__name__, str(_target))
_mod = _u.module_from_spec(_spec)
_s.modules[__name__] = _mod
_spec.loader.exec_module(_mod)
