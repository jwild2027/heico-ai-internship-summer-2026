"""TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24.

This module serves already-final-gated live Gemma answers through an OpenAI-compatible
local endpoint shape. It does not call the LLM. It does not perform retrieval. It reads
v23 final gate artifacts and exposes only answers that already passed the final gate.
"""

import json
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

MODULE = "trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24"
VERSION = "v24"
MODEL_ID = "trace-net-e2e-live-final-gated-gemma-v24"
STATUS_READY = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_READY"
STATUS_NEEDS_REPAIR = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

_ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"]


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=False) + "\n")


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def citation_like_count(text: str) -> int:
    return len(set(int(x) for x in re.findall(r"\[(\d{1,3})\]", text or "")))


def _to_bool(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1", "yes"}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def get_final_gate_records(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("final_gate_records", "final_answer_gates", "final_gates", "records"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def record_query(record: Mapping[str, Any]) -> str:
    return str(record.get("user_query") or record.get("query") or record.get("original_query") or "")


def record_final_answer(record: Mapping[str, Any]) -> str:
    return str(record.get("final_answer") or record.get("answer") or record.get("final_answer_text") or "")


def is_final_gate_pass(record: Mapping[str, Any]) -> bool:
    status = str(record.get("final_gate_status") or record.get("status") or "")
    if status and "PASS" not in status.upper() and "READY" not in status.upper():
        return False
    if _to_int(record.get("unsupported_claim_count"), 0) > 0:
        return False
    if _to_int(record.get("final_non_direct_citation_marker_count"), 0) > 0:
        return False
    if _to_int(record.get("graph_proof_authority_violation_count"), 0) > 0:
        return False
    if _to_int(record.get("summary_proof_authority_violation_count"), 0) > 0:
        return False
    return bool(record_final_answer(record).strip())


def final_answer_has_cap_disclosure(record: Mapping[str, Any]) -> bool:
    text = record_final_answer(record).lower()
    return "results were capped" in text or "returned" in text and "matching records" in text


def final_answer_has_source_truth_citation(record: Mapping[str, Any]) -> bool:
    return citation_like_count(record_final_answer(record)) > 0


def final_answer_ready_record(record: Mapping[str, Any], idx: int) -> Dict[str, Any]:
    query = record_query(record)
    answer = record_final_answer(record)
    return {
        "final_answer_id": record.get("final_answer_id") or record.get("final_gate_id") or f"webui_final_gated_gemma_v24_{idx:04d}",
        "source_final_gate_id": record.get("final_gate_id") or record.get("final_answer_gate_id"),
        "user_query": query,
        "normalized_query": normalize_query(query),
        "final_answer": answer,
        "final_gate_status": record.get("final_gate_status") or record.get("status"),
        "ready_for_webui": is_final_gate_pass(record),
        "citation_like_count": citation_like_count(answer),
        "has_source_truth_citation": final_answer_has_source_truth_citation(record),
        "has_cap_disclosure": final_answer_has_cap_disclosure(record),
        "unsupported_claim_count": _to_int(record.get("unsupported_claim_count"), 0),
        "final_non_direct_citation_marker_count": _to_int(record.get("final_non_direct_citation_marker_count"), 0),
        "graph_proof_authority_violation_count": _to_int(record.get("graph_proof_authority_violation_count"), 0),
        "summary_proof_authority_violation_count": _to_int(record.get("summary_proof_authority_violation_count"), 0),
        "v2_summary_proof_violation_detected": _to_bool(record.get("v2_summary_proof_violation_detected")),
        "nearby_context_overstatement_detected": _to_bool(record.get("nearby_context_overstatement_detected")),
        "repaired_from_draft": _to_bool(record.get("repaired_from_draft", True)),
        "safety": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "response_is_final_gated": True,
            "response_is_gemma_draft_repaired": _to_bool(record.get("repaired_from_draft", True)),
        },
    }


def build_endpoint_state(
    live_llm_final_gate_path: Path,
    host: str = "127.0.0.1",
    port: int = 8020,
    model_id: str = MODEL_ID,
) -> Dict[str, Any]:
    source = read_json(live_llm_final_gate_path)
    source_records = get_final_gate_records(source)
    final_answers = [final_answer_ready_record(record, idx + 1) for idx, record in enumerate(source_records)]
    ready_answers = [record for record in final_answers if record["ready_for_webui"]]

    unsupported_claim_count = sum(_to_int(record.get("unsupported_claim_count"), 0) for record in final_answers)
    final_non_direct_citation_marker_count = sum(_to_int(record.get("final_non_direct_citation_marker_count"), 0) for record in final_answers)
    graph_proof_authority_violation_count = sum(_to_int(record.get("graph_proof_authority_violation_count"), 0) for record in final_answers)
    summary_proof_authority_violation_count = sum(_to_int(record.get("summary_proof_authority_violation_count"), 0) for record in final_answers)

    state: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "model_id": model_id,
        "source_artifact": str(live_llm_final_gate_path),
        "host": host,
        "port": port,
        "base_url_windows": f"http://{host}:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "endpoint_routes": list(_ENDPOINT_ROUTES),
        "endpoint_route_count": len(_ENDPOINT_ROUTES),
        "final_gate_count": len(source_records),
        "final_answer_count": len(final_answers),
        "ready_final_answer_count": len(ready_answers),
        "final_answers_with_source_truth_citations_count": sum(1 for record in ready_answers if record["has_source_truth_citation"]),
        "cap_disclosures_in_final_answers_count": sum(1 for record in ready_answers if record["has_cap_disclosure"]),
        "unsupported_claim_count": unsupported_claim_count,
        "final_non_direct_citation_marker_count": final_non_direct_citation_marker_count,
        "graph_proof_authority_violation_count": graph_proof_authority_violation_count,
        "summary_proof_authority_violation_count": summary_proof_authority_violation_count,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "contract": {
            "serves_final_gated_gemma_answers": True,
            "calls_llm_at_endpoint_request_time": False,
            "reads_v23_final_gate_artifact": True,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "nearby_context_not_direct_proof": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
        "safety": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "response_is_final_gated": True,
        },
        "final_answers": ready_answers,
        "all_final_answers": final_answers,
    }
    return state


def evaluate_quality(
    state: Mapping[str, Any],
    min_final_gates: int = 5,
    min_ready_final_answers: int = 5,
    min_endpoint_routes: int = 4,
    min_final_answers_with_source_truth_citations: int = 5,
    min_cap_disclosures_in_final_answers: int = 3,
    max_unsupported_claim_count: int = 0,
    max_final_non_direct_citation_marker_count: int = 0,
    max_graph_proof_authority_violations: int = 0,
    max_summary_proof_authority_violations: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    checks = [
        ("final_gate_count", state.get("final_gate_count", 0), ">=", min_final_gates),
        ("ready_final_answer_count", state.get("ready_final_answer_count", 0), ">=", min_ready_final_answers),
        ("endpoint_route_count", state.get("endpoint_route_count", 0), ">=", min_endpoint_routes),
        ("final_answers_with_source_truth_citations_count", state.get("final_answers_with_source_truth_citations_count", 0), ">=", min_final_answers_with_source_truth_citations),
        ("cap_disclosures_in_final_answers_count", state.get("cap_disclosures_in_final_answers_count", 0), ">=", min_cap_disclosures_in_final_answers),
        ("unsupported_claim_count", state.get("unsupported_claim_count", 0), "<=", max_unsupported_claim_count),
        ("final_non_direct_citation_marker_count", state.get("final_non_direct_citation_marker_count", 0), "<=", max_final_non_direct_citation_marker_count),
        ("graph_proof_authority_violation_count", state.get("graph_proof_authority_violation_count", 0), "<=", max_graph_proof_authority_violations),
        ("summary_proof_authority_violation_count", state.get("summary_proof_authority_violation_count", 0), "<=", max_summary_proof_authority_violations),
        ("answer_permission_count", state.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", state.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        checks.append(("require_no_answer_permission", state.get("answer_permission_count", 0), "==", 0))

    rows: List[Dict[str, Any]] = []
    for name, observed, op, expected in checks:
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:
            raise ValueError(f"Unsupported op {op}")
        rows.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": passed})
    return (QUALITY_PASS if all(row["passed"] for row in rows) else QUALITY_FAIL, rows)


def attach_quality(state: Dict[str, Any], quality_status: str, quality_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    state["quality_status"] = quality_status
    state["quality_checks"] = quality_checks
    state["status"] = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NEEDS_REPAIR
    return state


def render_markdown_report(state: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24")
    lines.append("")
    lines.append(f"Quality status: **{state.get('quality_status', 'UNKNOWN')}**")
    lines.append(f"Status: `{state.get('status', 'UNKNOWN')}`")
    lines.append("")
    lines.append("## Summary")
    for key in [
        "final_gate_count",
        "final_answer_count",
        "ready_final_answer_count",
        "endpoint_route_count",
        "final_answers_with_source_truth_citations_count",
        "cap_disclosures_in_final_answers_count",
        "unsupported_claim_count",
        "final_non_direct_citation_marker_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "base_url_windows",
        "base_url_open_webui_docker",
    ]:
        lines.append(f"- {key}: {state.get(key)}")
    lines.append("")
    lines.append("## Contract")
    lines.append("- This endpoint serves final-gated Gemma answers from the v23 artifact.")
    lines.append("- It does not call Gemma at request time; v22 already produced drafts and v23 repaired/gated them.")
    lines.append("- Source-truth evidence remains the only proof authority.")
    lines.append("- Graph/Leiden and v2 summaries remain guidance only.")
    lines.append("- Nearby OCR/table context is not direct proof for the user query.")
    lines.append("- It does not scan raw 5TB data, rebuild the graph, mutate source truth, or write to services.")
    lines.append("")
    lines.append("## Final-gated WebUI answers")
    for record in state.get("final_answers", []):
        lines.append(f"### {record.get('final_answer_id')} — ready={record.get('ready_for_webui')}")
        lines.append(f"- query: {record.get('user_query')}")
        lines.append(f"- citation_like_count: {record.get('citation_like_count')}")
        lines.append(f"- has_cap_disclosure: {record.get('has_cap_disclosure')}")
        preview = str(record.get("final_answer") or "").replace("\n", " ")[:500]
        lines.append(f"- final_answer_preview: {preview}")
        lines.append("")
    lines.append("## Quality checks")
    for check in state.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def write_endpoint_files(state: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.json"
    responses_jsonl_path = output_dir / "trace_net_e2e_live_webui_final_gated_gemma_endpoint_responses_v24.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.md"
    write_json(report_path, state)
    write_jsonl(responses_jsonl_path, state.get("final_answers", []))
    inspect_md_path.write_text(render_markdown_report(state), encoding="utf-8")
    state["report_path"] = str(report_path)
    state["responses_jsonl_path"] = str(responses_jsonl_path)
    state["inspect_md_path"] = str(inspect_md_path)
    write_json(report_path, state)
    return {
        "report_path": str(report_path),
        "responses_jsonl_path": str(responses_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }


def match_final_answer(state: Mapping[str, Any], query: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_query(query)
    for record in state.get("final_answers", []):
        if record.get("normalized_query") == normalized:
            return dict(record)
    return None


def openai_models_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": state.get("model_id", MODEL_ID),
                "object": "model",
                "created": int(time.time()),
                "owned_by": "trace-net-local",
            }
        ],
    }


def health_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": "ok" if state.get("quality_status") == QUALITY_PASS else "needs_repair",
        "module": MODULE,
        "quality_status": state.get("quality_status"),
        "ready_final_answer_count": state.get("ready_final_answer_count"),
        "endpoint_route_count": state.get("endpoint_route_count"),
        "model_id": state.get("model_id", MODEL_ID),
        "safety": state.get("safety", {}),
    }


def extract_user_message(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def chat_completion_response(state: Mapping[str, Any], request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    query = extract_user_message(request_payload.get("messages"))
    match = match_final_answer(state, query)
    matched = match is not None
    if match:
        content = match["final_answer"]
        response_status = "FINAL_GATED_GEMMA_ANSWER_READY"
        citation_like_count = match.get("citation_like_count", 0)
    else:
        content = (
            "TRACE-Net does not have a final-gated Gemma answer for this exact query in the v24 endpoint artifact. "
            "Run the live v17→v23 pipeline for this query, or narrow the query to one of the final-gated demo questions. "
            "No source-truth claim is made."
        )
        response_status = "FINAL_GATED_GEMMA_ANSWER_NOT_FOUND"
        citation_like_count = 0

    return {
        "id": "chatcmpl-tracenet-v24-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": state.get("model_id", MODEL_ID),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": "webui_final_gated_gemma_v24",
            "matched_final_gated_answer": matched,
            "response_status": response_status,
            "citation_like_count": citation_like_count,
            "source_artifact": state.get("source_artifact"),
            "safety": {
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "writes_to_postgres": False,
                "writes_to_qdrant": False,
                "writes_to_opensearch": False,
                "uploads_to_opensearch": False,
                "response_is_final_gated": matched,
                "response_is_gemma_final_gate_repaired": matched,
            },
        },
    }


class TraceNetV24Handler(BaseHTTPRequestHandler):
    state: Dict[str, Any] = {}

    def _send_json(self, payload: Mapping[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"status": "ok"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/health"}:
            self._send_json(health_response(self.state))
            return
        if self.path == "/v1/models":
            self._send_json(openai_models_response(self.state))
            return
        self._send_json({"error": f"Unknown route: {self.path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._send_json({"error": f"Unknown route: {self.path}"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            self._send_json(chat_completion_response(self.state, payload))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)


def serve(state: Dict[str, Any], host: str, port: int) -> None:
    TraceNetV24Handler.state = state
    server = HTTPServer((host, port), TraceNetV24Handler)
    print(f"TRACE-Net v24 serving {state.get('model_id', MODEL_ID)} at http://{host}:{port}/v1", flush=True)
    server.serve_forever()
