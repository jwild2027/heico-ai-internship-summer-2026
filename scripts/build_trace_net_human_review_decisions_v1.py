from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_human_review_decision_recorder_v1 import build_main


if __name__ == "__main__":
    raise SystemExit(build_main())
