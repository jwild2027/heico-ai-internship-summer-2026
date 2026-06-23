#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import read_json, serve_state  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net E2E WebUI final answer endpoint v14.")
    parser.add_argument("--webui-final-answer-endpoint", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8017)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    state = read_json(args.webui_final_answer_endpoint)
    serve_state(state, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
