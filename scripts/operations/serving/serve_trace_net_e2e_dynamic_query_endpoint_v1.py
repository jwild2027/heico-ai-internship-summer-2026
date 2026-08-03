#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import DEFAULT_MODEL_ID, build_endpoint_state, serve_dynamic_endpoint


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve TRACE-Net E2E dynamic query endpoint v1")
    ap.add_argument("--table-exact-search-adapter", type=Path, required=True)
    ap.add_argument("--table-hybrid-retrieval-bridge", type=Path, required=True)
    ap.add_argument("--dynamic-query-tunnels", type=Path, default=None, help="Optional v3 tunnel report JSON to expose in response debug metadata")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8016)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--top-k-citations", type=int, default=3)
    ap.add_argument("--model", default=DEFAULT_MODEL_ID)
    args = ap.parse_args()
    state = build_endpoint_state(
        args.table_exact_search_adapter,
        args.table_hybrid_retrieval_bridge,
        top_k=args.top_k,
        top_k_citations=args.top_k_citations,
        model_id=args.model,
        dynamic_query_tunnels=args.dynamic_query_tunnels,
    )
    serve_dynamic_endpoint(state, args.host, args.port)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
