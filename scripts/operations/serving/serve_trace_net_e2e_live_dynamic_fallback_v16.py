from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_live_dynamic_fallback_v16 import read_json, serve_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net E2E live dynamic fallback v16")
    parser.add_argument("--live-dynamic-fallback", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8019)
    args = parser.parse_args()
    state = read_json(args.live_dynamic_fallback)
    serve_state(state, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
