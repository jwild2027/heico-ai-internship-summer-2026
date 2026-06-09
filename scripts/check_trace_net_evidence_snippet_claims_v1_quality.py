from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_evidence_snippet_claims_v1 import quality_main


if __name__ == "__main__":
    raise SystemExit(quality_main())
