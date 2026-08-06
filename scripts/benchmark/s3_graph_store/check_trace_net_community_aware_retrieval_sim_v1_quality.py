from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_community_aware_retrieval_sim_v1 import quality_main

if __name__ == "__main__":
    raise SystemExit(quality_main())
