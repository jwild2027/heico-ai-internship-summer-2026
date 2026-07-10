#!/usr/bin/env python3
"""TRACE-Net router proxy v6 + gated visual route v1.1.

Composite OpenAI-compatible router for port 8017.

It reuses the existing guided/normal v6 router for:
- normal TRACE-Net ask/chat
- guided candidate discovery / fast clarification

And adds a gated visual route in front for:
- diagram / figure / callout / visual questions

The visual route consumes only:
- gated_visual_retrieval_adapter_v1_1 search-ready confirmed visual docs

It does not consume:
- raw 185-page visual context
- visual_candidate_review pages as automatic answer context

Safety contract:
- Read-only.
- Does not call OCR/LLM/Ollama for visual routing.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not mutate source-truth artifacts.
- Does not grant answer permission.
- Visual context remains retrieval guidance only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


MODULE_NAME = "trace_net_router_proxy_v6_gated_visual_v1_1"
STATUS_READY = "TRACE_NET_ROUTER_PROXY_V6_GATED_VISUAL_V1_1_READY"
STATUS_DONE = "TRACE_NET_ROUTER_PROXY_V6_GATED_VISUAL_V1_1_DONE"
QUALITY_PASS = "PASS"
QUALITY_WARN = "WARN"
QUALITY_FAIL = "FAIL"

DEFAULT_MODEL = "trace-net-router-proxy-v6-gated-visual-v1-1"
DEFAULT_NORMAL_BASE_URL = "http://127.0.0.1:8014"
DEFAULT_GUIDED_BASE_URL = "http://127.0.0.1:8016"


def _load_sibling_module(module_name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    if not path.exists():
        raise FileNotFoundError(f"Required module file not found: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to import {filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


base_router = _load_sibling_module(
    "trace_net_guided_discovery_router_proxy_v6_module",
    "serve_trace_net_guided_discovery_router_proxy_v6.py",
)
visual_live = _load_sibling_module(
    "trace_net_gated_visual_live_endpoint_v1_1_module",
    "serve_trace_net_gated_visual_live_endpoint_v1_1.py",
)


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
    return base_router.extract_question(payload)


PARTIAL_PART_MARKERS = (
    "only know",
    "only remember",
    "do not know",
    "don't know",
    "partial",
    "starts with",
    "starts",
    "begins with",
    "begins",
    "contains",
    "looks like",
    "looked like",
    "might be",
    "i think",
    "first few",
    "part starts",
    "part begins",
)

PART_WORDS = ("part", "parts", "p/n", "pn", "part number", "item number", "nomenclature")


def looks_like_partial_part_lookup(question: str) -> bool:
    q = question.lower()
    has_marker = any(marker in q for marker in PARTIAL_PART_MARKERS)
    has_part_word = any(word in q for word in PART_WORDS)
    # Also catch bare "starts with 24" style if part-like numeric prefix appears.
    has_prefix_number = bool(__import__("re").search(r"\b(starts|begins|contains)\s+(with\s+)?[a-z0-9-]{1,8}\b", q))
    return bool(has_part_word and (has_marker or has_prefix_number))


def visual_mode_forced(payload: Dict[str, Any]) -> bool:
    mode = str(payload.get("mode") or "").strip().lower()
    route = str(payload.get("route") or "").strip().lower()
    return mode in {"visual", "image_visual", "gated_image_visual", "visual_context"} or route in {
        "visual",
        "image_visual",
        "gated_image_visual",
        "visual_context",
    }


def base_mode_forced(payload: Dict[str, Any]) -> bool:
    mode = str(payload.get("mode") or "").strip().lower()
    route = str(payload.get("route") or "").strip().lower()
    forced = {
        "guided",
        "guided_discovery",
        "candidate_discovery",
        "guided_candidate_discovery",
        "normal",
        "ask",
        "qa",
        "chat",
    }
    return mode in forced or route in forced


def visual_payload_to_router_response(
    *,
    question: str,
    visual_payload: Dict[str, Any],
    start_time: float,
) -> Dict[str, Any]:
    return {
        "status": STATUS_DONE,
        "quality_status": QUALITY_PASS,
        "router": MODULE_NAME,
        "route": "gated_image_visual",
        "route_reason": "auto-detected visual/diagram/figure/callout question with gated visual context",
        "route_confidence": "high" if visual_payload.get("citation_count", 0) else "medium",
        "weak_query": False,
        "partial_part_lookup": False,
        "fast_clarification_only": False,
        "question": question,
        "downstream_status_code": 200,
        "downstream_endpoint": "internal://trace-net/router/gated-image-visual",
        "downstream_request": {
            "query": question,
            "top_k": visual_payload.get("top_k"),
            "route_name": "gated_image_visual",
        },
        "downstream_response": visual_payload,
        "gated_visual_context": visual_payload,
        "final_answer_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_trace_status": "visual-retrieval-guidance-only",
        "route_triggered": bool(visual_payload.get("route_triggered")),
        "citation_count": int(visual_payload.get("citation_count", 0) or 0),
        "page_count": int(visual_payload.get("page_count", 0) or 0),
        "review_only_docs_used_for_context_count": 0,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "ollama_call_attempt_count": 0,
            "llm_call_attempt_count": 0,
            "answer_permission_count": 0,
        },
        "elapsed_seconds": round(time.time() - start_time, 3),
    }


def route_payload(payload: Dict[str, Any], config: CompositeConfig) -> Dict[str, Any]:
    start = time.time()
    question = extract_question(payload)
    if not question:
        return {
            "status": STATUS_DONE,
            "quality_status": QUALITY_FAIL,
            "router": MODULE_NAME,
            "error": "missing_question",
            "message": "Provide a non-empty question, query, prompt, input, or chat messages payload.",
            "final_answer_allowed": False,
            "answer_permission": False,
            "elapsed_seconds": round(time.time() - start, 3),
        }

    force_visual = visual_mode_forced(payload)
    partial_part_lookup = looks_like_partial_part_lookup(question)

    # Partial part/nomenclature lookups belong to guided discovery, not visual
    # route, unless the caller explicitly forces visual mode.
    use_visual_first = (
        config.visual_route_first
        and not base_mode_forced(payload)
        and not partial_part_lookup
    )

    if use_visual_first or force_visual:
        visual_payload = config.visual_endpoint.build_payload(question)
        if force_visual or (
            visual_payload.get("route_triggered")
            and int(visual_payload.get("citation_count", 0) or 0) > 0
        ):
            return visual_payload_to_router_response(
                question=question,
                visual_payload=visual_payload,
                start_time=start,
            )

    routed = base_router.route_payload(payload, config.base_config)
    if isinstance(routed, dict):
        routed = dict(routed)
        routed["composite_router"] = MODULE_NAME
        routed["visual_route_checked"] = bool(use_visual_first or force_visual)
        routed["visual_route_used"] = False
        routed["partial_part_visual_bypass"] = bool(partial_part_lookup and not force_visual)
        routed.setdefault("answer_permission", False)
        routed.setdefault("final_answer_allowed", False)
        return routed

    return {
        "status": STATUS_DONE,
        "quality_status": QUALITY_FAIL,
        "router": MODULE_NAME,
        "error": "base_router_returned_non_dict",
        "final_answer_allowed": False,
        "answer_permission": False,
        "elapsed_seconds": round(time.time() - start, 3),
    }


def visual_chat_content(routed: Dict[str, Any]) -> str:
    visual_payload = routed.get("gated_visual_context")
    if isinstance(visual_payload, dict):
        return visual_live.safe_context_text(visual_payload)
    downstream = routed.get("downstream_response")
    if isinstance(downstream, dict):
        return visual_live.safe_context_text(downstream)
    return "TRACE-Net gated visual route produced no context. Final answer allowed: false."


def chat_content_for_routed(routed: Dict[str, Any]) -> str:
    if routed.get("route") == "gated_image_visual":
        return visual_chat_content(routed)
    downstream = routed.get("downstream_response") if isinstance(routed.get("downstream_response"), dict) else {}
    decision = base_router.RouteDecision(
        route=str(routed.get("route")),
        reason=str(routed.get("route_reason")),
        confidence=str(routed.get("route_confidence")),
        weak_query=bool(routed.get("weak_query")),
        partial_part_lookup=bool(routed.get("partial_part_lookup")),
    )
    if decision.route == "guided_discovery":
        return base_router.guided_payload_to_chat_content(downstream)
    return base_router.normal_payload_to_chat_content(downstream)


def openai_chat_response(model: str, content: str, routed_payload: Dict[str, Any]) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "id": f"{MODULE_NAME}-{now}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net_router": {
            "router": MODULE_NAME,
            "route": routed_payload.get("route"),
            "reason": routed_payload.get("route_reason"),
            "confidence": routed_payload.get("route_confidence"),
            "weak_query": bool(routed_payload.get("weak_query")),
            "partial_part_lookup": bool(routed_payload.get("partial_part_lookup")),
            "final_answer_allowed": bool(routed_payload.get("final_answer_allowed", False)),
            "answer_permission": bool(routed_payload.get("answer_permission", False)),
        },
        "trace_net_payload": routed_payload,
    }


class CompositeRouterHandler(BaseHTTPRequestHandler):
    server_version = "TraceNetRouterProxyV6GatedVisualV1_1/1.0"

    def _config(self) -> CompositeConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send_json(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        raw = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"_json_error": str(exc), "_raw": raw}
        return parsed if isinstance(parsed, dict) else {"input": parsed}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"status": "ok"})

    def do_GET(self) -> None:  # noqa: N802
        config = self._config()
        if self.path in {
            "/health",
            "/api/trace-net/router/health",
            "/api/trace-net/guided-router/health",
        }:
            visual_health = config.visual_endpoint.health()
            self._send_json(
                {
                    "status": STATUS_READY,
                    "quality_status": QUALITY_PASS,
                    "router": MODULE_NAME,
                    "model": config.model,
                    "normal_base_url": config.normal_base_url,
                    "guided_base_url": config.guided_base_url,
                    "visual_route_name": "gated_image_visual",
                    "visual_retrieval_document_count": visual_health.get("retrieval_document_count"),
                    "visual_review_only_document_count": visual_health.get("review_only_document_count"),
                    "routes": {
                        "router": "/api/trace-net/router",
                        "ask": "/api/trace-net/ask",
                        "chat": "/v1/chat/completions",
                    },
                    "safety_contract": {
                        "read_only": True,
                        "final_answer_allowed": False,
                        "answer_permission": False,
                        "source_truth_mutation_allowed_count": 0,
                        "postgres_write_attempt_count": 0,
                        "qdrant_write_attempt_count": 0,
                        "opensearch_write_attempt_count": 0,
                        "ollama_call_attempt_count_for_visual_route": 0,
                        "llm_call_attempt_count_for_visual_route": 0,
                    },
                }
            )
            return
        self._send_json({"error": "not_found", "path": self.path}, status_code=404)

    def do_POST(self) -> None:  # noqa: N802
        config = self._config()
        payload = self._read_json()
        if payload.get("_json_error"):
            self._send_json(
                {
                    "status": STATUS_DONE,
                    "quality_status": QUALITY_FAIL,
                    "error": "invalid_json",
                    "detail": payload.get("_json_error"),
                },
                status_code=400,
            )
            return

        if self.path in {
            "/api/trace-net/router",
            "/api/trace-net/guided-router",
            "/api/trace-net/ask",
        }:
            routed = route_payload(payload, config)
            code = 200 if routed.get("quality_status") != QUALITY_FAIL else 400
            self._send_json(routed, status_code=code)
            return

        if self.path == "/v1/chat/completions":
            routed = route_payload(payload, config)
            if routed.get("quality_status") == QUALITY_FAIL:
                self._send_json(routed, status_code=400)
                return
            content = chat_content_for_routed(routed)
            self._send_json(openai_chat_response(str(payload.get("model") or config.model), content, routed))
            return

        self._send_json({"error": "not_found", "path": self.path}, status_code=404)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Serve TRACE-Net router proxy v6 with gated visual route.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8017)
    p.add_argument("--normal-base-url", default=DEFAULT_NORMAL_BASE_URL)
    p.add_argument("--guided-base-url", default=DEFAULT_GUIDED_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--timeout-seconds", type=float, default=300.0)
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--loose-top-k", type=int, default=8)
    p.add_argument("--visual-top-k", type=int, default=8)
    p.add_argument("--visual-min-score", type=float, default=0.001)
    p.add_argument("--visual-route-first", action="store_true", default=True)
    p.add_argument("--no-visual-route-first", dest="visual_route_first", action="store_false")
    p.add_argument("--gated-visual-retrieval-documents-jsonl", required=True)
    p.add_argument("--review-only-documents-jsonl", default="")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> CompositeConfig:
    base_config = base_router.ServerConfig(
        host=args.host,
        port=args.port,
        normal_base_url=args.normal_base_url.rstrip("/"),
        guided_base_url=args.guided_base_url.rstrip("/"),
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        default_top_k=args.top_k,
        default_loose_top_k=args.loose_top_k,
    )
    docs = list(visual_live.read_jsonl(Path(args.gated_visual_retrieval_documents_jsonl)) or [])
    review_docs = (
        list(visual_live.read_jsonl(Path(args.review_only_documents_jsonl)) or [])
        if args.review_only_documents_jsonl
        else []
    )
    visual_endpoint = visual_live.VisualEndpoint(
        docs=docs,
        review_docs=review_docs,
        top_k=args.visual_top_k,
        min_score=args.visual_min_score,
    )
    return CompositeConfig(
        host=args.host,
        port=args.port,
        normal_base_url=args.normal_base_url.rstrip("/"),
        guided_base_url=args.guided_base_url.rstrip("/"),
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        default_top_k=args.top_k,
        default_loose_top_k=args.loose_top_k,
        visual_top_k=args.visual_top_k,
        visual_min_score=args.visual_min_score,
        visual_route_first=bool(args.visual_route_first),
        base_config=base_config,
        visual_endpoint=visual_endpoint,
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config = build_config(args)
    server = ThreadingHTTPServer((config.host, config.port), CompositeRouterHandler)
    server.config = config  # type: ignore[attr-defined]
    visual_health = config.visual_endpoint.health()
    print(f"status={STATUS_READY}")
    print(f"quality_status={QUALITY_PASS}")
    print(f"router={MODULE_NAME}")
    print(f"url=http://{config.host}:{config.port}/api/trace-net/router")
    print(f"chat=http://{config.host}:{config.port}/v1/chat/completions")
    print(f"normal_base_url={config.normal_base_url}")
    print(f"guided_base_url={config.guided_base_url}")
    print(f"visual_route_name=gated_image_visual")
    print(f"visual_retrieval_document_count={visual_health.get('retrieval_document_count')}")
    print(f"visual_review_only_document_count={visual_health.get('review_only_document_count')}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopping {MODULE_NAME}")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
