from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_page_query_response_tiff_content_audit_v1 import main_build

if __name__ == "__main__":
    raise SystemExit(main_build())
