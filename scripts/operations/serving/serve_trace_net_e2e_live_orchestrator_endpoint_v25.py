import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_orchestrator_endpoint_v25 import load_state_for_serving, serve


def parse_args():
    p = argparse.ArgumentParser(description="Serve TRACE-Net E2E Live Orchestrator Endpoint v25.")
    p.add_argument("--live-orchestrator-endpoint", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8021)
    p.add_argument("--llm-mode", choices=["simulate", "ollama"], default=None)
    p.add_argument("--llm-base-url", default=None)
    p.add_argument("--llm-model", default=None)
    p.add_argument("--llm-api-key", default=None)
    p.add_argument("--request-timeout", type=int, default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state_for_serving(Path(args.live_orchestrator_endpoint))
    state["host"] = args.host
    state["port"] = args.port
    if args.llm_mode is not None:
        state["llm_mode"] = args.llm_mode
    if args.llm_base_url is not None:
        state["llm_base_url"] = args.llm_base_url
    if args.llm_model is not None:
        state["llm_model"] = args.llm_model
    if args.llm_api_key is not None:
        state["llm_api_key"] = args.llm_api_key
    if args.request_timeout is not None:
        state["request_timeout"] = args.request_timeout
    serve(state, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
