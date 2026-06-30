from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tiff.trace_net_image_route_openwebui_endpoint_v1 import check_main

if __name__ == "__main__":
    raise SystemExit(check_main())
