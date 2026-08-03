from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_ask_api_final_return_policy_hybrid_v3_v22 import main

if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if "--serve" not in argv and "--build-only" not in argv:
        argv.append("--serve")
    raise SystemExit(main(argv))
