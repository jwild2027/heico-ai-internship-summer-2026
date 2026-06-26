from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tiff.trace_net_fishnet_route_manifest_overlay_v1 import main_build

if __name__ == "__main__":
    raise SystemExit(main_build())
