from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tiff.trace_net_openwebui_page_context_bridge_v1 import main

if __name__ == "__main__":
    raise SystemExit(main(["serve", *sys.argv[1:]]))
