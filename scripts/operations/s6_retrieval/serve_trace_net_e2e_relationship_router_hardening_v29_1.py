from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import (
    MODEL_ID,
    SAFETY_CONTRACT,
    RuntimeState,
    _extract_user_text,
    make_chat_completion_response,
)


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(state: RuntimeState, model_id: str):
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # noqa: N802
            _send_json(self, 200, {"ok": True})

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                _send_json(
                    self,
                    200,
                    {
                        "status": "ok",
                        "module": state.report.get("module"),
                        "quality_status": state.report.get("quality_status"),
                        "model_id": model_id,
                        "exact_search_document_count": state.report.get("exact_search_document_count"),
                        "page_context_v2_page_count": state.report.get("page_context_v2_page_count"),
                        "graph_has_v2_page_count": state.report.get("graph_has_v2_page_count"),
                        "graph_has_nomenclature_page_count": state.report.get("graph_has_nomenclature_page_count"),
                        "relationship_mode": state.report.get("relationship_mode"),
                        "safety": dict(SAFETY_CONTRACT, llm_called=False, response_is_final_gated=True),
                    },
                )
                return
            if self.path == "/v1/models":
                _send_json(
                    self,
                    200,
                    {"object": "list", "data": [{"id": model_id, "object": "model", "created": 1782236000, "owned_by": "trace-net-local"}]},
                )
                return
            _send_json(self, 404, {"error": f"Unknown route: {self.path}"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/chat/completions":
                _send_json(self, 404, {"error": f"Unknown route: {self.path}"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                _send_json(self, 400, {"error": f"Invalid JSON: {exc}"})
                return
            query = _extract_user_text(payload.get("messages", []))
            if not query:
                _send_json(self, 400, {"error": "No user message found"})
                return
            result = state.answer(query)
            _send_json(self, 200, make_chat_completion_response(payload.get("model") or model_id, query, result))

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net relationship router hardening v29.1 endpoint.")
    parser.add_argument("--relationship-router-hardening", required=True, type=Path)
    parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
    parser.add_argument("--page-context-v2", required=False, type=Path)
    parser.add_argument("--leiden-communities", required=False, type=Path)
    parser.add_argument("--graph-signal-artifact", action="append", type=Path, default=[])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8025)
    parser.add_argument("--model-id", default=MODEL_ID)
    # Accepted for compatibility with earlier endpoints; v29.1 deterministic hardening does not call the LLM.
    parser.add_argument("--llm-mode", default="ollama")
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--llm-api-key", default="ollama")
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--relationship-mode", default="guarded")
    args = parser.parse_args()

    state = RuntimeState(
        report_path=args.relationship_router_hardening,
        table_exact_search_adapter=args.table_exact_search_adapter,
        page_context_v2=args.page_context_v2,
        leiden_communities=args.leiden_communities,
        graph_signal_paths=args.graph_signal_artifact or None,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state, args.model_id))
    print(f"Serving TRACE-Net relationship router hardening v29.1 on http://{args.host}:{args.port}/v1")
    print(f"Model: {args.model_id}")
    server.serve_forever()


if __name__ == "__main__":
    main()
