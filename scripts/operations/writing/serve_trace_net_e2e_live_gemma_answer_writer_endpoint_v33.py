from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v33 import (
    MODEL_ID,
    TraceNetGemmaAnswerWriterV33,
    _extract_messages_user_text,
)


def _send_json(handler: BaseHTTPRequestHandler, data: Dict[str, Any], status: int = 200) -> None:
    body = json.dumps(data, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table-exact-search-adapter", required=True)
    ap.add_argument("--page-context-v2", required=True)
    ap.add_argument("--leiden-communities", required=True)
    ap.add_argument("--relationship-router-hardening", default=None)
    ap.add_argument("--relationship-final-gate-hardener", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8027)
    ap.add_argument("--llm-mode", default="ollama")
    ap.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--llm-model", default="gemma4:26b")
    ap.add_argument("--llm-api-key", default="ollama")
    ap.add_argument("--request-timeout", type=int, default=240)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--llm-answer-mode", default="always")
    ap.add_argument("--llm-prompt-mode", default="compact", choices=["compact", "full"])
    ap.add_argument("--llm-max-output-tokens", type=int, default=180)
    ns = ap.parse_args(argv)

    writer = TraceNetGemmaAnswerWriterV33.from_paths(
        table_exact_search_adapter=ns.table_exact_search_adapter,
        page_context_v2=ns.page_context_v2,
        leiden_communities=ns.leiden_communities,
        relationship_router_hardening=ns.relationship_router_hardening,
        relationship_final_gate_hardener=ns.relationship_final_gate_hardener,
    )
    metadata = writer._page_metadata()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            _send_json(self, {"ok": True})

        def do_GET(self) -> None:
            if self.path == "/health":
                _send_json(
                    self,
                    {
                        "status": "ok",
                        "module": "trace_net_e2e_live_gemma_answer_writer_endpoint_v33",
                        "quality_status": "PASS",
                        "model_id": MODEL_ID,
                        "llm_answer_mode": "always",
                        "llm_mode": ns.llm_mode,
                        "llm_model": ns.llm_model,
                        "llm_prompt_mode": ns.llm_prompt_mode,
                        "llm_max_output_tokens": ns.llm_max_output_tokens,
                        "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
                        "nomenclature_page_count": metadata.get("nomenclature_page_count"),
                        "safety": {
                            "answer_permission": False,
                            "can_answer_directly": False,
                            "can_prove_claims": False,
                            "source_truth_mutation_allowed": False,
                            "raw_5tb_scan_at_query_time": False,
                            "graph_rebuild_at_query_time": False,
                            "llm_called": True,
                            "llm_answer_writer_required": True,
                            "compact_prompt_mode_supported": True,
                            "self_rag_package_quality_telemetry_enabled": True,
                            "crag_retry_telemetry_enabled": True,
                            "rich_page_profile_package_supported": True,
                            "timeout_fallback_supported": True,
                            "response_is_final_gated": True,
                        },
                    },
                )
                return
            if self.path.rstrip("/") == "/v1/models":
                _send_json(self, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "trace-net-local"}]})
                return
            _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404)

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8", errors="replace")
                payload = json.loads(raw) if raw else {}
                if self.path.rstrip("/") != "/v1/chat/completions":
                    _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404)
                    return
                query = _extract_messages_user_text(payload)
                if not query:
                    _send_json(self, {"error": "No user message found"}, status=400)
                    return
                resp = writer.answer_query(
                    query,
                    llm_mode=ns.llm_mode,
                    llm_base_url=ns.llm_base_url,
                    llm_model=ns.llm_model,
                    llm_api_key=ns.llm_api_key,
                    temperature=ns.temperature,
                    request_timeout=ns.request_timeout,
                    llm_prompt_mode=ns.llm_prompt_mode,
                    llm_max_output_tokens=ns.llm_max_output_tokens,
                )
                # Preserve requested model id for OpenWebUI compatibility.
                resp["model"] = MODEL_ID
                _send_json(self, resp)
            except Exception as exc:
                safe = {
                    "id": "chatcmpl-tracenet-v33-error",
                    "object": "chat.completion",
                    "created": 0,
                    "model": MODEL_ID,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "TRACE-Net encountered a live endpoint error while preparing the Gemma answer package. No source-truth claim is made.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "trace_net": {
                        "endpoint_version": "live_gemma_answer_writer_v33",
                        "llm_called": False,
                        "llm_status": "LIVE_ENDPOINT_ERROR_SAFE_FALLBACK",
                        "final_gate_applied": True,
                        "final_gate_status": "LIVE_GEMMA_ANSWER_WRITER_SAFE_ERROR_FALLBACK",
                        "post_gate_issue_count": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                }
                _send_json(self, safe, status=200)

    server = ThreadingHTTPServer((ns.host, ns.port), Handler)
    print(f"Serving TRACE-Net live Gemma answer writer endpoint v33 on http://{ns.host}:{ns.port}/v1")
    print(f"Model: {MODEL_ID}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
