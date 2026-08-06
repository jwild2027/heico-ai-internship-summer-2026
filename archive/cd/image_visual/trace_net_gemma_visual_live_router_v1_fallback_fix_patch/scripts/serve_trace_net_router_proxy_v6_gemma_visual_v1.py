#!/usr/bin/env python3
"""TRACE-Net router proxy v6 + Gemma visual route v1.

This is the live router integration for the clean Gemma visual route.

Routes:
- visual/diagram/figure/callout questions -> gemma_confirmed_image_visual
- partial/uncertain part lookups -> existing guided discovery router
- normal exact/OCR/table questions -> existing normal route

The Gemma visual route is retrieval guidance only and never grants final answer
permission.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


MODULE_NAME = "trace_net_router_proxy_v6_gemma_visual_v1"
STATUS_READY = "TRACE_NET_ROUTER_PROXY_V6_GEMMA_VISUAL_V1_READY"
STATUS_DONE = "TRACE_NET_ROUTER_PROXY_V6_GEMMA_VISUAL_V1_DONE"
DEFAULT_MODEL = "trace-net-router-proxy-v6-gemma-visual-v1"
DEFAULT_NORMAL_BASE_URL = "http://127.0.0.1:8014"
DEFAULT_GUIDED_BASE_URL = "http://127.0.0.1:8016"


def _load_sibling_module(module_name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


base_router = _load_sibling_module("trace_net_guided_discovery_router_proxy_v6_module", "serve_trace_net_guided_discovery_router_proxy_v6.py")
visual_live = _load_sibling_module("trace_net_gemma_visual_live_endpoint_v1_module", "serve_trace_net_gemma_visual_live_endpoint_v1.py")


@dataclass
class CompositeConfig:
    host: str
    port: int
    normal_base_url: str
    guided_base_url: str
    model: str
    timeout_seconds: float
    default_top_k: int
    default_loose_top_k: int
    visual_top_k: int
    visual_min_score: float
    visual_route_first: bool
    base_config: Any
    visual_endpoint: Any


def compact(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())[:limit]
    try:
        return " ".join(json.dumps(value, ensure_ascii=False, sort_keys=True).split())[:limit]
    except Exception:
        return str(value)[:limit]


def extract_question(payload: Dict[str, Any]) -> str:
    if base_router is not None and hasattr(base_router, "extract_question"):
        return base_router.extract_question(payload)
    for key in ("query", "question", "input", "prompt"):
        if payload.get(key):
            return compact(payload[key], 2000)
    messages = payload.get("messages")
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                return compact(msg.get("content"), 2000)
    return ""


PARTIAL_PART_MARKERS = (
    "only know", "only remember", "do not know", "don't know", "partial",
    "starts with", "starts", "begins with", "begins", "contains", "looks like",
    "looked like", "might be", "i think", "first few", "part starts", "part begins",
)
PART_WORDS = ("part", "parts", "p/n", "pn", "part number", "item number", "nomenclature")


def looks_like_partial_part_lookup(question: str) -> bool:
    q = question.lower()
    has_marker = any(marker in q for marker in PARTIAL_PART_MARKERS)
    has_part_word = any(word in q for word in PART_WORDS)
    has_prefix_number = bool(re.search(r"\b(starts|begins|contains)\s+(with\s+)?[a-z0-9-]{1,8}\b", q))
    return bool(has_part_word and (has_marker or has_prefix_number))


def visual_mode_forced(payload: Dict[str, Any]) -> bool:
    mode = str(payload.get("mode") or "").strip().lower()
    route = str(payload.get("route") or "").strip().lower()
    return mode in {"visual", "image_visual", "gemma_visual", "gemma_confirmed_image_visual", "visual_context"} or route in {
        "visual", "image_visual", "gemma_visual", "gemma_confirmed_image_visual", "visual_context",
    }


def base_mode_forced(payload: Dict[str, Any]) -> bool:
    mode = str(payload.get("mode") or "").strip().lower()
    route = str(payload.get("route") or "").strip().lower()
    forced = {"guided", "guided_discovery", "candidate_discovery", "normal", "ask", "qa", "chat"}
    return mode in forced or route in forced


def fallback_base_route(payload: Dict[str, Any], config: CompositeConfig) -> Dict[str, Any]:
    # In production build_config creates a real base_config, so we can delegate
    # to the existing v6 router. In unit tests/sample configs base_config may be
    # None; then use the local safe stub instead of calling the base router with
    # None and crashing on config.normal_base_url/guided_base_url.
    if base_router is not None and hasattr(base_router, "route_payload") and config.base_config is not None:
        return base_router.route_payload(payload, config.base_config)

    question = extract_question(payload)
    route = "guided_discovery" if looks_like_partial_part_lookup(question) else "normal_ask"
    return {
        "status": "TRACE_NET_BASE_ROUTER_STUB_DONE",
        "quality_status": "WARN",
        "router": "base_router_stub",
        "route": route,
        "question": question,
        "downstream_response": {"content": "Base router module not available in this environment."},
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def visual_payload_to_router_response(question: str, visual_payload: Dict[str, Any], start_time: float) -> Dict[str, Any]:
    return {
        "status": STATUS_DONE,
        "quality_status": "PASS",
        "router": MODULE_NAME,
        "route": "gemma_confirmed_image_visual",
        "route_reason": "visual diagram/figure/callout query matched clean Gemma visual route",
        "route_confidence": "high",
        "question": question,
        "visual_route_checked": True,
        "visual_route_used": True,
        "gemma_visual_context": visual_payload,
        "citation_count": int(visual_payload.get("citation_count", 0)),
        "citations": visual_payload.get("citations", []),
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "runtime_seconds": round(time.time() - start_time, 4),
    }


def route_payload(payload: Dict[str, Any], config: CompositeConfig) -> Dict[str, Any]:
    start = time.time()
    question = extract_question(payload)
    forced_visual = visual_mode_forced(payload)
    partial_part = looks_like_partial_part_lookup(question)

    if partial_part and not forced_visual:
        base_response = fallback_base_route(payload, config)
        if isinstance(base_response, dict):
            base_response.update({
                "router": MODULE_NAME,
                "partial_part_lookup": True,
                "partial_part_visual_bypass": True,
                "visual_route_checked": False,
                "visual_route_used": False,
                "answer_permission": False,
                "final_answer_allowed": False,
                "source_truth_mutation_allowed": False,
            })
        return base_response

    if config.visual_route_first and not base_mode_forced(payload):
        visual_payload = config.visual_endpoint.context_for_query(
            question,
            top_k=config.visual_top_k,
            min_score=config.visual_min_score,
        )
        if forced_visual or (visual_payload.get("route_triggered") and int(visual_payload.get("citation_count", 0)) > 0):
            return visual_payload_to_router_response(question, visual_payload, start)

    base_response = fallback_base_route(payload, config)
    if isinstance(base_response, dict):
        base_response.update({
            "router": MODULE_NAME,
            "visual_route_checked": True,
            "visual_route_used": False,
            "gemma_visual_route_available": True,
            "partial_part_lookup": partial_part,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        })
    return base_response


def openai_response(config: CompositeConfig, routed: Dict[str, Any]) -> Dict[str, Any]:
    content = json.dumps(routed, ensure_ascii=False, indent=2)
    return {
        "id": "trace-net-router-proxy-v6-gemma-visual-v1",
        "object": "chat.completion",
        "model": config.model,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def make_handler(config: CompositeConfig):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetRouterGemmaVisual/1.0"

        def _json(self, status: int, obj: Dict[str, Any]) -> None:
            body = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _payload(self) -> Dict[str, Any]:
            size = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(size) if size > 0 else b"{}"
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {
                    "status": "ok",
                    "module": MODULE_NAME,
                    "route": "gemma_confirmed_image_visual",
                    "model": config.model,
                    "clean_visual_docs": len(config.visual_endpoint.docs),
                    "answer_permission": False,
                    "final_answer_allowed": False,
                })
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            payload = self._payload()
            routed = route_payload(payload, config)
            if self.path in {"/api/trace-net/ask", "/api/trace-net/router", "/api/chat"}:
                self._json(200, routed)
            elif self.path == "/v1/chat/completions":
                self._json(200, openai_response(config, routed))
            else:
                self._json(404, {"error": "not_found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def make_base_config(args: argparse.Namespace) -> Any:
    if base_router is not None and hasattr(base_router, "ServerConfig"):
        return base_router.ServerConfig(
            host=args.host,
            port=args.port,
            normal_base_url=args.normal_base_url,
            guided_base_url=args.guided_base_url,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
            default_top_k=args.default_top_k,
            default_loose_top_k=args.default_loose_top_k,
        )
    return None


def build_config(args: argparse.Namespace) -> CompositeConfig:
    if visual_live is None or not hasattr(visual_live, "GemmaVisualEndpoint"):
        raise RuntimeError("serve_trace_net_gemma_visual_live_endpoint_v1.py is required next to this script")
    docs = list(visual_live.read_jsonl(Path(args.gemma_visual_retrieval_documents_jsonl)) or [])
    visual_endpoint = visual_live.GemmaVisualEndpoint(docs, top_k=args.visual_top_k, min_score=args.visual_min_score)
    return CompositeConfig(
        host=args.host,
        port=args.port,
        normal_base_url=args.normal_base_url,
        guided_base_url=args.guided_base_url,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        default_top_k=args.default_top_k,
        default_loose_top_k=args.default_loose_top_k,
        visual_top_k=args.visual_top_k,
        visual_min_score=args.visual_min_score,
        visual_route_first=not args.disable_visual_route_first,
        base_config=make_base_config(args),
        visual_endpoint=visual_endpoint,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8017)
    p.add_argument("--normal-base-url", default=DEFAULT_NORMAL_BASE_URL)
    p.add_argument("--guided-base-url", default=DEFAULT_GUIDED_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--timeout-seconds", type=float, default=180.0)
    p.add_argument("--default-top-k", type=int, default=8)
    p.add_argument("--default-loose-top-k", type=int, default=8)
    p.add_argument("--visual-top-k", type=int, default=8)
    p.add_argument("--visual-min-score", type=float, default=0.001)
    p.add_argument("--disable-visual-route-first", action="store_true")
    p.add_argument("--gemma-visual-retrieval-documents-jsonl", required=True)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = build_config(args)
    server = ThreadingHTTPServer((config.host, config.port), make_handler(config))
    print(f"status={STATUS_READY}")
    print(f"host={config.host}")
    print(f"port={config.port}")
    print(f"model={config.model}")
    print(f"route=gemma_confirmed_image_visual")
    print(f"clean_visual_document_count={len(config.visual_endpoint.docs)}")
    print(f"rejected_visual_document_count={len(config.visual_endpoint.rejected_docs)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
