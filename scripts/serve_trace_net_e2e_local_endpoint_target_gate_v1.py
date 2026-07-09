#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_local_endpoint_target_gate_v1"
VERSION = "v1"

PART_PATTERNS = [
    # Examples: 120-36833-001, 120-36833-003
    re.compile(r"\b\d{2,5}-\d{3,8}-\d{2,5}\b", re.I),
    # Examples: DF250040-501, ABC123456-789
    re.compile(r"\b[A-Z]{1,5}\s*\d{5,8}(?:-\d{2,5})?\b", re.I),
    # Examples: DF250040501. Require a letter prefix so aircraft A319 is not captured.
    re.compile(r"\b[A-Z]{1,5}\s*\d{7,12}\b", re.I),
]

AIRCRAFT_LIKE = re.compile(r"\bA\d{3}\b|\bB\d{3}\b", re.I)


def norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def norm_target(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def extract_explicit_part_targets(text: str) -> List[Dict[str, str]]:
    """Extract explicit part-like targets from a user query.

    This intentionally favors specific part-number shapes and avoids short aircraft
    model strings such as A319/A320/B737. The result is deterministic and does
    not call an LLM.
    """
    text = norm_text(text)
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for pattern in PART_PATTERNS:
        for match in pattern.finditer(text):
            raw = norm_text(match.group(0)).replace(" ", "")
            if AIRCRAFT_LIKE.fullmatch(raw):
                continue
            target_norm = norm_target(raw)
            # Avoid tiny alphanumeric matches and pure aircraft-like captures.
            if len(target_norm) < 8:
                continue
            if target_norm not in seen:
                seen.add(target_norm)
                out.append({"target_type": "part_number", "target_text": raw, "target_norm": target_norm})
    return out


def walk(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, Mapping):
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def extract_citation_like_records(data: Any) -> List[Any]:
    """Find citation/proof records from several TRACE-Net response shapes."""
    found: List[Any] = []
    seen: set[str] = set()

    def add(item: Any) -> None:
        try:
            key = json.dumps(item, sort_keys=True, default=str)[:4000]
        except Exception:
            key = repr(item)[:4000]
        if key not in seen:
            seen.add(key)
            found.append(item)

    for obj in walk(data):
        if isinstance(obj, Mapping):
            keys = {str(k).lower() for k in obj.keys()}
            if (
                "citation_id" in keys
                or "page_id" in keys
                or "source_trace_ready" in keys
                or "citation_ready" in keys
                or "generated_citation_id" in keys
            ):
                add(dict(obj))
            for key, value in obj.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in ["citations", "proof_context", "evidence_record"]):
                    if isinstance(value, list):
                        for row in value:
                            if isinstance(row, (Mapping, str)):
                                add(dict(row) if isinstance(row, Mapping) else row)
                    elif isinstance(value, Mapping):
                        add(dict(value))
        elif isinstance(obj, str):
            if re.search(r"generated_citation_\d+|source_trace_ready|citation_ready", obj, re.I):
                add(obj[:2000])
    return found


def citation_record_matches_any_target(record: Any, targets: Sequence[Mapping[str, str]]) -> bool:
    if not targets:
        return True
    try:
        text = json.dumps(record, sort_keys=True, default=str)
    except Exception:
        text = repr(record)
    text_norm = norm_target(text)
    return any(str(t.get("target_norm") or "") in text_norm for t in targets)


def has_target_matching_citation(data: Any, targets: Sequence[Mapping[str, str]]) -> bool:
    citations = extract_citation_like_records(data)
    return any(citation_record_matches_any_target(c, targets) for c in citations)


def strip_known_citations(data: Any) -> Any:
    """Return a copy with common citation containers emptied.

    The wrapper returns an audit-only response, but this helper is used in tests
    and for defensive nested cleanup when needed.
    """
    if isinstance(data, list):
        return [strip_known_citations(x) for x in data]
    if isinstance(data, Mapping):
        out: Dict[str, Any] = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in {"citations", "proof_context", "evidence_records", "page_ids"}:
                out[key] = []
            elif key_lower in {"citation_count", "match_score"}:
                out[key] = 0
            elif key_lower in {"matched_artifact_response", "can_answer_directly", "can_prove_claims"}:
                out[key] = False
            elif key_lower == "api_response_status":
                out[key] = "AUDIT_ONLY_TARGET_NOT_FOUND"
            elif key_lower == "query_intent":
                out[key] = "target_part_not_found"
            else:
                out[key] = strip_known_citations(value)
        return out
    return data


def build_target_not_found_response(query: str, targets: Sequence[Mapping[str, str]], original: Mapping[str, Any]) -> Dict[str, Any]:
    target_texts = [str(t.get("target_text") or t.get("target_norm") or "") for t in targets]
    target_label = ", ".join([t for t in target_texts if t]) or "requested target"
    original_citation_count = len(extract_citation_like_records(original))
    original_page_ids = []
    try:
        original_page_ids = list(original.get("page_ids") or original.get("response", {}).get("page_ids") or [])
    except Exception:
        original_page_ids = []

    message = (
        f"TRACE-Net target gate found no citation/source-trace-ready evidence matching {target_label!r}. "
        "Off-target citations from the downstream endpoint were not promoted. No final answer is provided."
    )
    return {
        "object": "trace_net.e2e.local_endpoint.target_gate.response",
        "model": MODULE,
        "endpoint_version": VERSION,
        "query": query,
        "matched_artifact_response": False,
        "match_score": 0.0,
        "citations": [],
        "page_ids": [],
        "message": {"role": "assistant", "content": message},
        "response": {
            "api_response_status": "AUDIT_ONLY_TARGET_NOT_FOUND",
            "audit_reasons": [
                "Explicit part-number target was present in the user query.",
                "Downstream citations did not contain the requested target.",
                "Off-target citations were suppressed by TRACE-Net target gate.",
            ],
            "query_id": "audit_only_target_gate_v1",
            "query_intent": "target_part_not_found",
            "user_query": query,
            "citation_count": 0,
            "citations": [],
            "page_ids": [],
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "retrieval_permission": "audit_only",
            "source_truth_mutation_allowed": False,
            "response_is_smoke_draft": True,
            "message": {"role": "assistant", "content": message},
        },
        "safety": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "response_is_smoke_draft": True,
            "source_truth_mutation_allowed": False,
            "uploads_to_opensearch": False,
            "writes_to_opensearch": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
        },
        "target_gate": {
            "module": MODULE,
            "version": VERSION,
            "target_gate_applied": True,
            "target_quality_status": "TARGET_NOT_FOUND",
            "explicit_part_targets": list(targets),
            "original_citation_count": original_citation_count,
            "original_page_ids": original_page_ids,
            "off_target_citations_suppressed": original_citation_count,
        },
    }


def gate_trace_response(query: str, response: Mapping[str, Any]) -> Dict[str, Any]:
    """Suppress citations when explicit part target and returned citations do not match."""
    targets = extract_explicit_part_targets(query)
    out = json.loads(json.dumps(response, default=str))
    if not targets:
        out.setdefault("target_gate", {"module": MODULE, "version": VERSION, "target_gate_applied": False})
        return out

    citations = extract_citation_like_records(out)
    if not citations:
        out.setdefault(
            "target_gate",
            {
                "module": MODULE,
                "version": VERSION,
                "target_gate_applied": False,
                "explicit_part_targets": targets,
                "target_quality_status": "NO_CITATIONS_RETURNED",
            },
        )
        return out

    if has_target_matching_citation(out, targets):
        out.setdefault(
            "target_gate",
            {
                "module": MODULE,
                "version": VERSION,
                "target_gate_applied": False,
                "explicit_part_targets": targets,
                "target_quality_status": "TARGET_CITATION_MATCHED",
            },
        )
        return out

    return build_target_not_found_response(query, targets, out)


def extract_query_from_payload(path: str, payload: Mapping[str, Any]) -> str:
    for key in ("question", "query", "user_query", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and norm_text(value):
            return norm_text(value)

    messages = payload.get("messages")
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, Mapping) and str(msg.get("role") or "").lower() == "user":
                content = msg.get("content")
                if isinstance(content, str) and norm_text(content):
                    return norm_text(content)
    return ""


def forward_json(base_url: str, path: str, payload: Mapping[str, Any], timeout: int) -> Tuple[int, Dict[str, Any]]:
    url = base_url.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code or 500)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw_response": raw}
    if not isinstance(data, dict):
        data = {"response": data}
    return status, data


def fetch_base_health(base_url: str, timeout: int) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {"base_health": data}
    except Exception as exc:
        return {"base_health_error": str(exc)}


class TargetGateHandler(BaseHTTPRequestHandler):
    server_version = MODULE

    def _write_json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @property
    def base_url(self) -> str:
        return str(getattr(self.server, "base_url"))

    @property
    def upstream_timeout(self) -> int:
        return int(getattr(self.server, "upstream_timeout"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/health":
            self._write_json(404, {"status": "not_found", "module": MODULE})
            return
        base = fetch_base_health(self.base_url, self.upstream_timeout)
        self._write_json(
            200,
            {
                "status": "ok",
                "module": MODULE,
                "version": VERSION,
                "base_url": self.base_url,
                "base_health": base,
                "target_gate": "explicit_part_target_citations_must_match",
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            self._write_json(400, {"status": "bad_json", "error": str(exc), "module": MODULE})
            return
        if not isinstance(payload, dict):
            self._write_json(400, {"status": "bad_payload", "error": "Expected JSON object", "module": MODULE})
            return

        status, upstream = forward_json(self.base_url, path, payload, self.upstream_timeout)
        query = extract_query_from_payload(path, payload)
        gated = gate_trace_response(query, upstream)
        gated.setdefault("target_gate_proxy", {"module": MODULE, "version": VERSION, "base_url": self.base_url})
        self._write_json(status, gated)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (MODULE, fmt % args))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TRACE-Net endpoint target-match gate proxy")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8015)
    p.add_argument("--base-url", default="http://127.0.0.1:8014")
    p.add_argument("--upstream-timeout", type=int, default=120)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), TargetGateHandler)
    server.base_url = args.base_url
    server.upstream_timeout = args.upstream_timeout
    print(
        json.dumps(
            {
                "status": "TRACE_NET_ENDPOINT_TARGET_GATE_SERVING",
                "module": MODULE,
                "version": VERSION,
                "host": args.host,
                "port": args.port,
                "base_url": args.base_url,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("TRACE_NET_ENDPOINT_TARGET_GATE_STOPPED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
