from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_reasoned_response_draft_v12 import check_cli

if __name__ == "__main__":
    raise SystemExit(check_cli())
