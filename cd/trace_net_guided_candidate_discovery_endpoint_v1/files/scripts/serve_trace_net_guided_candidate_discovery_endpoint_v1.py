#!/usr/bin/env python3
"""
TRACE-Net guided candidate discovery endpoint v1.

Purpose:
  Expose guided candidate discovery v4 through a small local HTTP API.

Routes:
  GET  /health
  GET  /api/trace-net/guided-discovery/health
  POST /api/trace-net/guided-discovery

Safety contract:
  - read-only artifact scanning
  - no Postgres/Qdrant/OpenSearch writes
  - no source-truth mutation
  - no final answer permission
  - candidate routes are discovery hints, not proof of eligibility/fit/approval/interchangeability
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SERVICE_STATUS = "TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_ENDPOINT_V1_READY"
DONE_STATUS = "TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_ENDPOINT_V1_DONE"
RUNNER_MODULE = "run_trace_net_guided_candidate_discovery_v4"


@dataclass(frozen=True)
class EndpointConfig:
    artifact_root: Path
    output_dir: Optional[Path]
    max_files: int = 250000
    default_top_k: int = 8
    default_loose_top_k: int = 8
    include_view_default: bool = True


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def load_runner_module() -> Any:
    ensure_scripts_on_path()
    return importlib.import_module(RUNNER_MODULE)


def json_safe_int(value: Any, default: int, minimum: int = 1, maximum: int = 250000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def split_routes(candidate_routes: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    strict = [r for r in candidate_routes if r.get("route_group") == "strict_prefix"]
    contains = [r for r in candidate_routes if r.get("route_group") == "contains_digits"]
    loose = [r for r in candidate_routes if r.get("route_group") in {"loose_contains", "weak_digit_overlap", "broad_candidate"}]
    return strict, contains, loose


def write_endpoint_outputs(output_dir: Optional[Path], response: Dict[str, Any], view_text: str) -> Dict[str, Optional[str]]:
    if output_dir is None:
        return {"response": None, "view": None, "summary": None}
    output_dir.mkdir(parents=True, exist_ok=True)
    response_path = output_dir / "last_guided_discovery_response.json"
    view_path = output_dir / "last_guided_discovery_view.txt"
    summary_path = output_dir / "summary.json"
    response_path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
    view_path.write_text(view_text, encoding="utf-8")
    summary = {
        "status": DONE_STATUS,
        "quality_status": response.get("quality_status", "UNKNOWN"),
        "question": response.get("question"),
        "intent": response.get("intent"),
        "strict_prefix_candidate_count": response.get("strict_prefix_candidate_count", 0),
        "contains_candidate_count": response.get("contains_candidate_count", 0),
        "loose_candidate_count": response.get("loose_candidate_count", 0),
        "total_candidate_route_count": response.get("total_candidate_route_count", 0),
        "rejected_noise_token_count": response.get("rejected_noise_token_count", 0),
        "weak_token_count": response.get("weak_token_count", 0),
        "final_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "response": str(response_path),
        "view": str(view_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"response": str(response_path), "view": str(view_path), "summary": str(summary_path)}


def discover_once(
    *,
    artifact_root: Path,
    question: str,
    top_k: int = 8,
    loose_top_k: int = 8,
    max_files: int = 250000,
    output_dir: Optional[Path] = None,
    include_view: bool = True,
) -> Dict[str, Any]:
    """Run one guided-discovery request using the v4 runner as source of truth."""
    started = time.time()
    if not question or not question.strip():
        raise ValueError("question is required")
    if not artifact_root.exists():
        raise FileNotFoundError(f"artifact_root does not exist: {artifact_root}")

    runner = load_runner_module()
    clues = runner.parse_query_clues(question)
    hits, evidence_count, rejected_noise_count, weak_token_count = runner.collect_evidence(
        artifact_root,
        clues,
        max_files=max_files,
    )
    routes = runner.merge_candidate_routes(hits, top_k=top_k, loose_top_k=loose_top_k)
    result = runner.build_result(question, routes, clues, evidence_count, rejected_noise_count, weak_token_count)
    result["question_id"] = "q01"
    view_text = runner.render_view([result])
    candidate_routes = list(result.get("candidate_routes", []))
    strict, contains, loose = split_routes(candidate_routes)

    response: Dict[str, Any] = {
        "status": DONE_STATUS,
        "quality_status": "PASS",
        "runner": "guided_candidate_discovery_v4",
        "question_id": "q01",
        "question": question,
        "intent": result.get("intent"),
        "known_clues": result.get("known_clues", {}),
        "missing_clues": result.get("missing_clues", []),
        "clarifying_questions": result.get("clarifying_questions", []),
        "strict_prefix_candidates": strict,
        "contains_candidates": contains,
        "loose_candidates": loose,
        "candidate_routes": candidate_routes,
        "strict_prefix_candidate_count": len(strict),
        "contains_candidate_count": len(contains),
        "loose_candidate_count": len(loose),
        "total_candidate_route_count": len(candidate_routes),
        "evidence_record_count": result.get("evidence_record_count", 0),
        "rejected_noise_token_count": result.get("rejected_noise_token_count", 0),
        "weak_token_count": result.get("weak_token_count", 0),
        "source_trace_status": "candidate-discovery-only",
        "final_answer_allowed": False,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission_count": 0,
        },
        "elapsed_seconds": round(time.time() - started, 2),
    }
    if include_view:
        response["view_text"] = view_text
    response["output_paths"] = write_endpoint_outputs(output_dir, response, view_text)
    return response


def build_health(config: EndpointConfig) -> Dict[str, Any]:
    runner_importable = True
    runner_error: Optional[str] = None
    try:
        load_runner_module()
    except Exception as exc:  # pragma: no cover - exercised by deployment health only
        runner_importable = False
        runner_error = str(exc)
    quality_status = "PASS" if runner_importable and config.artifact_root.exists() else "WARN"
    return {
        "status": SERVICE_STATUS,
        "quality_status": quality_status,
        "service": "trace_net_guided_candidate_discovery_endpoint_v1",
        "runner": "guided_candidate_discovery_v4",
        "artifact_root": str(config.artifact_root),
        "artifact_root_exists": config.artifact_root.exists(),
        "output_dir": str(config.output_dir) if config.output_dir else None,
        "runner_importable": runner_importable,
        "runner_error": runner_error,
        "final_answer_allowed": False,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission_count": 0,
        },
    }


def make_handler(config: EndpointConfig):
    class GuidedDiscoveryHandler(BaseHTTPRequestHandler):
        server_version = "TraceNetGuidedDiscoveryEndpoint/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # keep terminal clean
            return

        def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib name
            path = self.path.split("?", 1)[0]
            if path in {"/health", "/api/trace-net/guided-discovery/health"}:
                self._send_json(200, build_health(config))
                return
            self._send_json(404, {"quality_status": "FAIL", "error": "not_found", "path": path})

        def do_POST(self) -> None:  # noqa: N802 - stdlib name
            path = self.path.split("?", 1)[0]
            if path != "/api/trace-net/guided-discovery":
                self._send_json(404, {"quality_status": "FAIL", "error": "not_found", "path": path})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 1_000_000:
                self._send_json(400, {"quality_status": "FAIL", "error": "invalid_content_length"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                self._send_json(400, {"quality_status": "FAIL", "error": "invalid_json", "detail": str(exc)})
                return
            question = str(payload.get("question") or payload.get("query") or "").strip()
            top_k = json_safe_int(payload.get("top_k"), config.default_top_k, 1, 50)
            loose_top_k = json_safe_int(payload.get("loose_top_k"), config.default_loose_top_k, 1, 50)
            max_files = json_safe_int(payload.get("max_files"), config.max_files, 1, 250000)
            include_view = bool(payload.get("include_view", config.include_view_default))
            try:
                response = discover_once(
                    artifact_root=config.artifact_root,
                    question=question,
                    top_k=top_k,
                    loose_top_k=loose_top_k,
                    max_files=max_files,
                    output_dir=config.output_dir,
                    include_view=include_view,
                )
            except Exception as exc:
                self._send_json(
                    500,
                    {
                        "status": "TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_ENDPOINT_V1_ERROR",
                        "quality_status": "FAIL",
                        "error": type(exc).__name__,
                        "detail": str(exc),
                        "final_answer_allowed": False,
                        "source_truth_mutation_allowed_count": 0,
                        "postgres_write_attempt_count": 0,
                        "qdrant_write_attempt_count": 0,
                        "opensearch_write_attempt_count": 0,
                    },
                )
                return
            self._send_json(200, response)

    return GuidedDiscoveryHandler


def build_server(host: str, port: int, config: EndpointConfig) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(config))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net guided candidate discovery endpoint v1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8016)
    parser.add_argument("--artifact-root", default="local_data/organization/trace_net")
    parser.add_argument("--output-dir", default="/data/trace_net_runs/guided_candidate_discovery_endpoint_v1")
    parser.add_argument("--max-files", type=int, default=250000)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--loose-top-k", type=int, default=8)
    parser.add_argument("--no-view", action="store_true", help="Do not include view_text by default in JSON responses")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = EndpointConfig(
        artifact_root=Path(args.artifact_root),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        max_files=args.max_files,
        default_top_k=args.top_k,
        default_loose_top_k=args.loose_top_k,
        include_view_default=not args.no_view,
    )
    health = build_health(config)
    print(f"status={health['status']}", flush=True)
    print(f"quality_status={health['quality_status']}", flush=True)
    print(f"runner={health['runner']}", flush=True)
    print(f"artifact_root={config.artifact_root}", flush=True)
    print(f"url=http://{args.host}:{args.port}/api/trace-net/guided-discovery", flush=True)
    server = build_server(args.host, args.port, config)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutdown=keyboard_interrupt", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
