"""Compatibility shim (created by the src reorganization).

This module was moved to ``src.trace_net.validation.citation_checker``. Importing from this old path continues to
work: the shim re-exports the relocated module in full. Update imports to the
new path when convenient.
"""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("src.trace_net.validation.citation_checker")
