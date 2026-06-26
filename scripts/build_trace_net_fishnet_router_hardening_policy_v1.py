from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_fishnet_router_hardening_policy_v1 import main_build

if __name__ == "__main__":
    raise SystemExit(main_build())
