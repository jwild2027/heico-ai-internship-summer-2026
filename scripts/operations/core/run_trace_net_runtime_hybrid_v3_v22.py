from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_runtime_hybrid_v3_v22 import run_main

if __name__ == "__main__":
    raise SystemExit(run_main())
