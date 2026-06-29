from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib


def test_module_imports():
    assert importlib.import_module("tiff.trace_net_answer_context_evidence_enricher_v1")
