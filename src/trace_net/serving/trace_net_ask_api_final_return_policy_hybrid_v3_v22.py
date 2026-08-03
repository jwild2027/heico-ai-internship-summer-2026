"""TRACE-Net Ask API Final Return Policy Hybrid v3 v2.2.

Read-only final-return controller that consumes Hybrid Retrieval v3 routing directly.

Safety contract:
- Hybrid v3 routing groups are retrieval/navigation records, not proof.
- Corrective actions are routing metadata, not proof.
- Final answers may only be returned when an explicit final-gate artifact authorizes them.
- The module performs no Postgres, Qdrant, OpenSearch, graph, citation, trust, or source-truth writes.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "trace_net_ask_api_final_return_policy_hybrid_v3_v22"
QUALITY_SCHEMA_VERSION = f"{SCHEMA_VERSION}_quality"
DEFAULT_MODEL_NAME = "trace-net-final-return-policy-hybrid-v3-v2.2"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask_api_final_return_policy_hybrid_v3_v22")
DEFAULT_PORT = 8016

LOCAL_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)",
    re.IGNORECASE,
)
RAW_BYTES_PATTERN = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")

HARD_ZERO_COUNTER_KEYS = [
    "unsafe_group_count",
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "retrieval_only_answer_allowed_count",
    "source_truth_mutation_allowed_count",
    "feedback_as_proof_count",
    "community_as_proof_count",
    "category_as_proof_count",
    "corrective_action_as_proof_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
]


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", errors="replace"))
        h.update(b"\0")
    return f"{prefix}__{h.hexdigest()[:16]}"


def normalize_query(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def read_json(path: Optional[str | Path]) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "pass", "allowed"}:
            return True
        if v in {"0", "false", "no", "n", "fail", "blocked"}:
            return False
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip():
            return int(float(value.strip()))
    except Exception:
        return default
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            return float(value.strip())
    except Exception:
        return default
    return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def get_summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def get_quality_status(payload: Mapping[str, Any]) -> str:
    for source in (payload, get_summary(payload)):
        for key in ("quality_status", "status"):
            value = str(source.get(key, "")).strip().upper()
            if value in {"PASS", "FAIL", "ERROR"}:
                return value
    return "UNKNOWN"


def sanitize_text(text: str, max_chars: int = 12000) -> tuple[str, dict[str, int]]:
    text = text or ""
    counts = {
        "local_path_leak_count": len(LOCAL_PATH_PATTERN.findall(text)),
        "raw_bytes_repr_count": len(RAW_BYTES_PATTERN.findall(text)),
    }
    text = LOCAL_PATH_PATTERN.sub("[redacted-local-path]", text)
    text = RAW_BYTES_PATTERN.sub("[redacted-bytes]", text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[truncated by TRACE-Net final return policy hybrid v3 v2.2]"
    return text, counts


def hybrid_query_results(hybrid_v3: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = hybrid_v3.get("query_results")
    return [r for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def all_hybrid_groups(hybrid_v3: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    groups: list[Mapping[str, Any]] = []
    for result in hybrid_query_results(hybrid_v3):
        for group in as_list(result.get("ranked_groups")):
            if isinstance(group, Mapping):
                groups.append(group)
    return groups


def find_hybrid_result(query: str, hybrid_v3: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    wanted = normalize_query(query)
    query_id_guess = re.sub(r"[^a-z0-9]+", "_", wanted).strip("_")
    for result in hybrid_query_results(hybrid_v3):
        if normalize_query(result.get("query")) == wanted:
            return result
        if normalize_query(result.get("query_id")) == wanted or normalize_query(result.get("query_id")) == query_id_guess:
            return result
    # Fallback for identifier queries where the query text may appear inside query_id.
    if wanted:
        for result in hybrid_query_results(hybrid_v3):
            haystack = " ".join([str(result.get("query", "")), str(result.get("query_id", ""))]).lower()
            if wanted in haystack:
                return result
    return None


def final_gate_records(final_gate: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("query_results", "policy_records", "records", "results", "answer_records"):
        rows = final_gate.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, Mapping)]
    return []


def read_final_markdown(path: Optional[str | Path]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def find_final_gate_record(query: str, final_gate: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    wanted = normalize_query(query)
    for record in final_gate_records(final_gate):
        if normalize_query(record.get("query")) == wanted:
            return record
    if wanted:
        for record in final_gate_records(final_gate):
            haystack = " ".join([str(record.get("query", "")), str(record.get("query_id", "")), str(record.get("record_id", ""))]).lower()
            if wanted in haystack:
                return record
    return None


def final_gate_allows(record: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(record, Mapping):
        return False
    if as_bool(record.get("final_answer_allowed"), False):
        return True
    if as_bool(record.get("final_answer_return_allowed"), False):
        return True
    status = str(record.get("policy_status") or record.get("answer_status") or record.get("status") or "").strip().upper()
    return status in {"FINAL_ANSWER_RETURN_ALLOWED", "FINAL_ANSWER_ALLOWED", "PASS"}


def final_gate_answer_text(record: Optional[Mapping[str, Any]], markdown_fallback: str = "") -> str:
    if isinstance(record, Mapping):
        for key in ("user_response_text", "final_answer_text", "answer_text", "answer_markdown", "final_answer_markdown"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return markdown_fallback.strip()


def group_is_unsafe(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("can_answer_directly"), False):
        return True
    if as_bool(group.get("can_prove_claims"), False):
        return True
    if as_bool(group.get("source_truth_mutation_allowed"), False):
        return True
    if as_bool(group.get("answer_permission"), False):
        return True
    if as_bool(group.get("corrective_action_as_proof"), False):
        return True
    return False


def compact_group(group: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hybrid_v3_rank": group.get("hybrid_v3_rank") or group.get("rank"),
        "query_id": group.get("query_id"),
        "page_id": group.get("page_id"),
        "hybrid_v3_score": group.get("hybrid_v3_score"),
        "safe_routing_status": group.get("safe_routing_status"),
        "review_required_before_final_answer": as_bool(group.get("review_required_before_final_answer"), False),
        "corrective_issue_types": as_list(group.get("corrective_issue_types")),
        "corrective_recommended_actions": as_list(group.get("corrective_recommended_actions")),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "corrective_action_as_proof": False,
    }


def summarize_groups_for_user(groups: Sequence[Mapping[str, Any]], max_groups: int) -> str:
    lines: list[str] = []
    for idx, group in enumerate(groups[:max_groups], start=1):
        page_id = group.get("page_id") or "unknown-page"
        status = group.get("safe_routing_status") or "ROUTING_UNKNOWN"
        score = group.get("hybrid_v3_score")
        review = "review required" if as_bool(group.get("review_required_before_final_answer"), False) else "routing ready"
        issues = ", ".join(str(x) for x in as_list(group.get("corrective_issue_types"))[:3]) or "none"
        actions = ", ".join(str(x) for x in as_list(group.get("corrective_recommended_actions"))[:3]) or "none"
        lines.append(f"- rank {idx}: {page_id}; score={score}; status={status}; {review}; issues={issues}; actions={actions}")
    return "\n".join(lines)


def summarize_source_quality(hybrid_v3: Mapping[str, Any], final_gate: Mapping[str, Any]) -> dict[str, str]:
    summary = get_summary(hybrid_v3)
    hybrid_source = summary.get("source_quality_statuses")
    source_statuses = dict(hybrid_source) if isinstance(hybrid_source, Mapping) else {}
    source_statuses["hybrid_retrieval_v3"] = get_quality_status(hybrid_v3)
    if final_gate:
        source_statuses["final_answer_gate"] = get_quality_status(final_gate)
    return {str(k): str(v) for k, v in sorted(source_statuses.items())}


def build_summary(hybrid_v3: Mapping[str, Any], final_gate: Mapping[str, Any], *, model_name: str, max_groups: int) -> dict[str, Any]:
    groups = all_hybrid_groups(hybrid_v3)
    source_summary = get_summary(hybrid_v3)
    counters = {key: as_int(source_summary.get(key), 0) for key in HARD_ZERO_COUNTER_KEYS}
    counters["unsafe_group_count"] = max(counters["unsafe_group_count"], sum(1 for g in groups if group_is_unsafe(g)))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if get_quality_status(hybrid_v3) == "PASS" and all(v == 0 for v in counters.values()) else "REVIEW",
        "model_name": model_name,
        "default_answer_mode": "final-gate",
        "default_retrieval_mode": "hybrid-v3-final-return",
        "read_only_api": True,
        "api_endpoint_count": 5,
        "hybrid_v3_quality_status": get_quality_status(hybrid_v3),
        "final_answer_quality_status": get_quality_status(final_gate) if final_gate else "MISSING",
        "hybrid_v3_routing_available": bool(hybrid_query_results(hybrid_v3)),
        "query_count": len(hybrid_query_results(hybrid_v3)),
        "hybrid_v3_group_count": len(groups),
        "corrective_group_count": sum(1 for g in groups if as_list(g.get("corrective_issue_types")) or as_list(g.get("corrective_recommended_actions"))),
        "review_routed_group_count": sum(1 for g in groups if as_bool(g.get("review_required_before_final_answer"), False)),
        "source_quality_statuses": summarize_source_quality(hybrid_v3, final_gate),
        **counters,
    }


def build_checks(summary: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "schema_version_ok": summary.get("schema_version") == SCHEMA_VERSION,
        "api_is_read_only": as_bool(summary.get("read_only_api"), False),
        "hybrid_v3_report_quality_pass": str(summary.get("hybrid_v3_quality_status", "")).upper() == "PASS",
        "hybrid_v3_has_query_results": as_int(summary.get("query_count"), 0) > 0,
        "write_attempts_zero": all(as_int(summary.get(key), 0) == 0 for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count")),
        "source_truth_mutation_allowed_zero": as_int(summary.get("source_truth_mutation_allowed_count"), 0) == 0,
        "answer_permission_zero_from_hybrid_groups": as_int(summary.get("answer_permission_count"), 0) == 0,
        "can_answer_directly_zero_from_hybrid_groups": as_int(summary.get("can_answer_directly_count"), 0) == 0,
        "can_prove_claims_zero_from_hybrid_groups": as_int(summary.get("can_prove_claims_count"), 0) == 0,
        "corrective_action_as_proof_zero": as_int(summary.get("corrective_action_as_proof_count"), 0) == 0,
    }


def quality_from_summary(summary: Mapping[str, Any], *, require_hybrid_v3_quality_pass: bool = False) -> tuple[str, list[str]]:
    checks = build_checks(summary)
    fail_reasons = [key for key, ok in checks.items() if not ok]
    if require_hybrid_v3_quality_pass and str(summary.get("hybrid_v3_quality_status", "")).upper() != "PASS":
        fail_reasons.append("required_hybrid_v3_quality_not_pass")
    return ("PASS" if not fail_reasons else "FAIL", fail_reasons)


@dataclass(frozen=True)
class FinalReturnHybridV3Config:
    hybrid_v3_report: Path
    final_answer_report: Optional[Path] = None
    final_answer_markdown: Optional[Path] = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    model_name: str = DEFAULT_MODEL_NAME
    api_key: str = ""
    max_groups: int = 8


def build_report(config: FinalReturnHybridV3Config, *, require_hybrid_v3_quality_pass: bool = False) -> dict[str, Any]:
    hybrid_v3 = read_json(config.hybrid_v3_report)
    final_gate = read_json(config.final_answer_report)
    summary = build_summary(hybrid_v3, final_gate, model_name=config.model_name, max_groups=config.max_groups)
    quality_status, fail_reasons = quality_from_summary(summary, require_hybrid_v3_quality_pass=require_hybrid_v3_quality_pass)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_API_FINAL_RETURN_POLICY_HYBRID_V3_CONFIG_BUILT",
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "model_name": config.model_name,
        "output_dir": str(config.output_dir),
        "hybrid_v3_report": str(config.hybrid_v3_report),
        "final_answer_report": str(config.final_answer_report) if config.final_answer_report else "",
        "final_answer_markdown": str(config.final_answer_markdown) if config.final_answer_markdown else "",
        "summary": {**summary, "quality_fail_reasons": fail_reasons},
        "checks": build_checks(summary),
    }
    out = config.output_dir
    write_json(out / "trace_net_ask_api_final_return_policy_hybrid_v3_v22.json", report)
    write_json(out / "trace_net_ask_api_final_return_policy_hybrid_v3_v22_summary.json", report["summary"])
    quality = build_quality_report(report, require_hybrid_v3_quality_pass=require_hybrid_v3_quality_pass)
    write_json(out / "trace_net_ask_api_final_return_policy_hybrid_v3_v22_quality.json", quality)
    write_json(out / "trace_net_ask_api_final_return_policy_hybrid_v3_v22_manifest.json", {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "quality_status": quality["quality_status"],
        "outputs": [
            "trace_net_ask_api_final_return_policy_hybrid_v3_v22.json",
            "trace_net_ask_api_final_return_policy_hybrid_v3_v22_quality.json",
            "trace_net_ask_api_final_return_policy_hybrid_v3_v22_summary.json",
            "trace_net_ask_api_final_return_policy_hybrid_v3_v22_manifest.json",
        ],
    })
    return report


def build_quality_report(report: Mapping[str, Any], *, require_hybrid_v3_quality_pass: bool = False) -> dict[str, Any]:
    summary = dict(get_summary(report))
    quality_status, fail_reasons = quality_from_summary(summary, require_hybrid_v3_quality_pass=require_hybrid_v3_quality_pass)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "summary": {**summary, "quality_fail_reasons": fail_reasons},
        "checks": build_checks(summary),
    }


def answer_query(
    query: str,
    hybrid_v3: Mapping[str, Any],
    final_gate: Mapping[str, Any],
    final_markdown: str = "",
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    max_groups: int = 8,
) -> dict[str, Any]:
    hybrid_result = find_hybrid_result(query, hybrid_v3)
    groups = []
    if isinstance(hybrid_result, Mapping):
        groups = [g for g in as_list(hybrid_result.get("ranked_groups")) if isinstance(g, Mapping)]
    compact_groups = [compact_group(g) for g in groups[:max_groups]]
    review_required = any(as_bool(g.get("review_required_before_final_answer"), False) for g in compact_groups)
    unsafe_group_count = sum(1 for g in groups if group_is_unsafe(g))

    final_record = find_final_gate_record(query, final_gate)
    final_allowed = final_gate_allows(final_record) and unsafe_group_count == 0 and not review_required
    final_text = final_gate_answer_text(final_record, final_markdown)
    safe_text, text_counters = sanitize_text(final_text)
    if text_counters["local_path_leak_count"] or text_counters["raw_bytes_repr_count"]:
        final_allowed = False

    if final_allowed and safe_text:
        answer_status = "FINAL_ANSWER_RETURN_ALLOWED"
        response_text = safe_text
        required_action = "return_final_answer"
    elif compact_groups:
        answer_status = "RETRIEVAL_ONLY_FINAL_GATE_REQUIRED" if not review_required else "RETRIEVAL_ROUTE_REVIEW_REQUIRED"
        required_action = "run_final_gate_or_review_before_answer" if not review_required else "resolve_review_routes_before_final_answer"
        response_text = (
            "TRACE-Net found Hybrid v3 routing groups, but this response is retrieval-only. "
            "Hybrid v3 groups and corrective actions do not prove claims. Final answers still require final-gate authorization."
        )
        group_text = summarize_groups_for_user(compact_groups, max_groups=max_groups)
        if group_text:
            response_text += "\n\nHybrid v3 routing groups:\n" + group_text
    else:
        answer_status = "NO_SAFE_RETRIEVAL_GROUPS_FOUND"
        required_action = "retrieve_more_or_run_pipeline"
        response_text = "TRACE-Net did not find Hybrid v3 routing groups for this query. Run or expand retrieval before answering."

    return {
        "schema_version": SCHEMA_VERSION,
        "response_id": stable_id("final_return_hybrid_v3", query, answer_status),
        "model": model_name,
        "query": query,
        "answer_status": answer_status,
        "required_action": required_action,
        "final_answer_allowed": bool(final_allowed and safe_text),
        "final_answer_returned": bool(final_allowed and safe_text),
        "answer_mode": "final-gate",
        "retrieval_mode": "hybrid-v3-final-return",
        "message": response_text,
        "ranked_groups": compact_groups,
        "ranked_group_count": len(compact_groups),
        "review_required_group_count": sum(1 for g in compact_groups if as_bool(g.get("review_required_before_final_answer"), False)),
        "corrective_group_count": sum(1 for g in compact_groups if g.get("corrective_issue_types") or g.get("corrective_recommended_actions")),
        "unsafe_group_count": unsafe_group_count,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "corrective_action_as_proof_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "generated_at": utc_now(),
    }


class HybridV3FinalReturnServer:
    def __init__(self, config: FinalReturnHybridV3Config):
        self.config = config
        self.hybrid_v3 = read_json(config.hybrid_v3_report)
        self.final_gate = read_json(config.final_answer_report)
        self.final_markdown = read_final_markdown(config.final_answer_markdown)
        self.report = build_report(config, require_hybrid_v3_quality_pass=True)

    def ask(self, query: str, max_groups: Optional[int] = None) -> dict[str, Any]:
        return answer_query(
            query,
            self.hybrid_v3,
            self.final_gate,
            self.final_markdown,
            model_name=self.config.model_name,
            max_groups=max_groups or self.config.max_groups,
        )


def make_handler(server_state: HybridV3FinalReturnServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TRACE-Net-FinalReturnHybridV3/2.2"

        def _send(self, code: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            length = as_int(self.headers.get("Content-Length"), 0)
            if length <= 0:
                return {}
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                return {}
            return value if isinstance(value, dict) else {}

        def _authorized(self) -> bool:
            if not server_state.config.api_key:
                return True
            auth = self.headers.get("Authorization", "")
            return auth == f"Bearer {server_state.config.api_key}"

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                self._send(200, {
                    "status": "ok",
                    "schema_version": SCHEMA_VERSION,
                    "model_name": server_state.config.model_name,
                    "quality_status": server_state.report.get("quality_status"),
                    "hybrid_v3_quality_status": get_quality_status(server_state.hybrid_v3),
                    "read_only_api": True,
                })
                return
            if path == "/v1/models":
                self._send(200, {"object": "list", "data": [{"id": server_state.config.model_name, "object": "model"}]})
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            path = urlparse(self.path).path
            body = self._read_json_body()
            if path in {"/api/trace-net/ask", "/trace-net/ask"}:
                query = str(body.get("query") or body.get("question") or "").strip()
                max_groups = as_int(body.get("max_groups"), server_state.config.max_groups)
                if not query:
                    self._send(400, {"error": "missing_query"})
                    return
                self._send(200, server_state.ask(query, max_groups=max_groups))
                return
            if path == "/v1/chat/completions":
                messages = as_list(body.get("messages"))
                query = ""
                for message in reversed(messages):
                    if isinstance(message, Mapping) and message.get("role") == "user":
                        query = str(message.get("content") or "").strip()
                        break
                if not query:
                    self._send(400, {"error": "missing_user_message"})
                    return
                result = server_state.ask(query, max_groups=server_state.config.max_groups)
                self._send(200, {
                    "id": result["response_id"],
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": server_state.config.model_name,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": result["message"]},
                        "finish_reason": "stop",
                    }],
                    "trace_net": result,
                })
                return
            self._send(404, {"error": "not_found"})

    return Handler


def serve(config: FinalReturnHybridV3Config, host: str, port: int) -> None:
    state = HybridV3FinalReturnServer(config)
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"TRACE-Net final return policy hybrid v3 v2.2 listening on http://{host}:{port}", flush=True)
    httpd.serve_forever()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or run TRACE-Net final return policy with Hybrid v3 routing.")
    parser.add_argument("--hybrid-v3-report", required=True, type=Path)
    parser.add_argument("--final-answer-report", type=Path)
    parser.add_argument("--final-answer-markdown", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--max-groups", type=int, default=8)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--require-hybrid-v3-quality-pass", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = FinalReturnHybridV3Config(
        hybrid_v3_report=args.hybrid_v3_report,
        final_answer_report=args.final_answer_report,
        final_answer_markdown=args.final_answer_markdown,
        output_dir=args.output_dir,
        model_name=args.model_name,
        api_key=args.api_key,
        max_groups=args.max_groups,
    )
    if args.serve and not args.build_only:
        serve(config, args.host, args.port)
        return 0
    report = build_report(config, require_hybrid_v3_quality_pass=args.require_hybrid_v3_quality_pass or args.quality)
    print("TRACE-Net Ask API Final Return Policy Hybrid Retrieval v3 v2.2")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    print(" model_name:", report.get("model_name"))
    print(" hybrid_v3_quality_status:", report.get("summary", {}).get("hybrid_v3_quality_status"))
    print(" final_answer_quality_status:", report.get("summary", {}).get("final_answer_quality_status"))
    print(" report_path:", config.output_dir / "trace_net_ask_api_final_return_policy_hybrid_v3_v22.json")
    if report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
