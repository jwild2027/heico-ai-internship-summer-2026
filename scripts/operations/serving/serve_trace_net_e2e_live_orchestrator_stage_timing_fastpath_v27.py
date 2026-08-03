import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 import load_state_for_serving, serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net v27 stage timing + fast path endpoint")
    parser.add_argument("--live-orchestrator-stage-timing-fastpath", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8022)
    parser.add_argument("--llm-mode", default=None, choices=["simulate", "ollama"])
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--request-timeout", type=int, default=None)
    parser.add_argument("--fast-path-mode", default=None, choices=["exact", "all_direct", "off"])
    args = parser.parse_args()

    state = load_state_for_serving(Path(args.live_orchestrator_stage_timing_fastpath))
    for attr in ("llm_mode", "llm_base_url", "llm_model", "llm_api_key", "request_timeout", "fast_path_mode"):
        value = getattr(args, attr)
        if value is not None:
            state[attr] = value
    state["host"] = args.host
    state["port"] = args.port
    serve(state, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
