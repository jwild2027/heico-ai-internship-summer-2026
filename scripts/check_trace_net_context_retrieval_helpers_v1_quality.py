from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_context_retrieval_helper_v1 import main_quality


if __name__ == "__main__":
    raise SystemExit(main_quality())
