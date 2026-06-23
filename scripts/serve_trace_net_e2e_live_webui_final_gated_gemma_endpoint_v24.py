import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import read_json, serve


def parse_args():
    p = argparse.ArgumentParser(description="Serve TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24.")
    p.add_argument("--live-webui-final-gated-gemma-endpoint", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8020)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    state = read_json(Path(args.live_webui_final_gated_gemma_endpoint))
    state["host"] = args.host
    state["port"] = args.port
    state["base_url_windows"] = f"http://{args.host}:{args.port}/v1"
    state["base_url_open_webui_docker"] = f"http://host.docker.internal:{args.port}/v1"
    serve(state, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
