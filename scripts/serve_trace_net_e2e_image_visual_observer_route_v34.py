from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_image_visual_observer_route_v34 import serve_endpoint


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve TRACE-Net E2E Image Visual Observer Route v34")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8029)
    ap.add_argument("--llm-mode", choices=["simulate", "ollama"], default="simulate")
    ap.add_argument("--llm-base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--llm-model", default="llava:13b")
    ap.add_argument("--llm-api-key", default="ollama")  # accepted for OpenAI-compatible CLI symmetry
    ap.add_argument("--request-timeout", type=int, default=180)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--llm-max-output-tokens", type=int, default=220)
    args = ap.parse_args()
    serve_endpoint(
        host=args.host,
        port=args.port,
        llm_mode=args.llm_mode,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        request_timeout=args.request_timeout,
        temperature=args.temperature,
        llm_max_output_tokens=args.llm_max_output_tokens,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
