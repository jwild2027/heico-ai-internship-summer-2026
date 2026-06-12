from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_category_aware_graph_ui_overlay_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
