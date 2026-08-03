import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_deterministic_answer_planner_v28 import load_state_for_serving, serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net live deterministic answer planner + drilldown v28")
    parser.add_argument("--live-deterministic-answer-planner", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8023)
    parser.add_argument("--llm-mode", default="ollama", choices=["simulate", "ollama"])
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--llm-api-key", default="ollama")
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--deterministic-mode", default="expanded", choices=["expanded", "exact", "off"])
    args = parser.parse_args()

    state = load_state_for_serving(Path(args.live_deterministic_answer_planner))
    state["host"] = args.host
    state["port"] = args.port
    state["llm_mode"] = args.llm_mode
    state["llm_base_url"] = args.llm_base_url
    state["llm_model"] = args.llm_model
    state["llm_api_key"] = args.llm_api_key
    state["request_timeout"] = args.request_timeout
    state["deterministic_mode"] = args.deterministic_mode
    serve(state, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
