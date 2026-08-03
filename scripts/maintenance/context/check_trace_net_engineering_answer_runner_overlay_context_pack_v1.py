from __future__ import annotations
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from tiff.trace_net_engineering_answer_runner_overlay_context_pack_v1 import check_main

if __name__ == "__main__":
    raise SystemExit(check_main())
