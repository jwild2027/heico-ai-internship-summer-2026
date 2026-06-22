#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_local_endpoint_v1 import DEFAULT_MODEL_ID, serve_endpoint


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Serve TRACE-Net E2E local endpoint v1")
    p.add_argument("--e2e-api-wrapper-smoke", default="local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8014)
    return p.parse_args()



def _trace_net_final_output_scrub(value):
    """Last-mile WebUI/OpenAI response cleanup."""
    if isinstance(value, str):
        return (
            value
            .replace("ont_p_", "on t_p_")
            .replace(" on  t_p_", " on t_p_")
        )
    if isinstance(value, list):
        return [_trace_net_final_output_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _trace_net_final_output_scrub(v) for k, v in value.items()}
    return value

def main() -> int:
    args = parse_args()
    server = serve_endpoint(e2e_api_wrapper_smoke_path=args.e2e_api_wrapper_smoke, host=args.host, port=args.port)
    print("TRACE-Net E2E local endpoint v1")
    print(f" Serving: http://{args.host}:{args.port}")
    print(f" Health:  http://{args.host}:{args.port}/health")
    print(f" Ask:     http://{args.host}:{args.port}/api/trace-net/ask")
    print(f" Chat:    http://{args.host}:{args.port}/v1/chat/completions")
    print(f" Model:   {DEFAULT_MODEL_ID}")
    print(" Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net E2E local endpoint v1")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
