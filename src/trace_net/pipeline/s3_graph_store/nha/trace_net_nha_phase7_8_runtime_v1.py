#!/usr/bin/env python3
"""TRACE-Net NHA N7-N8 shadow and gated production-sidecar runtime.

N7 observes recognized real-source NHA queries without changing the upstream
answer. N8 can deterministically answer only gated, real-source NHA queries.
Synthetic N5 data is never loaded by this runtime and synthetic part numbers
are explicitly blocked from the NHA route.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_nha_phase7_8_runtime_v1"
STATUS = "TRACE_NET_NHA_PHASE7_8_RUNTIME_V1"
SCHEMA_VERSION = "trace_net_nha_phase7_8_runtime_v1"
ROUTE_ID = "assembly_relationship_reasoning"

SYNTHETIC_PART_RE = re.compile(r"\b990-\d{5}-\d{3}\b", re.I)
REAL_PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}-\d{3}|\d{4,6}-\d{1,4}|[A-Z]{2,}\d{3,}[A-Z0-9-]*)\b",
    re.I,
)

INTENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "relationship_evidence_page",
        (
            "which page proves",
            "what page proves",
            "relationship evidence",
            "evidence page",
            "source page for",
            "where is the nha",
        ),
    ),
    (
        "direct_vs_descendant",
        (
            "direct versus descendant",
            "direct vs descendant",
            "lower descendants",
            "all descendants",
            "all components below",
            "full assembly breakdown",
            "entire assembly breakdown",
        ),
    ),
    (
        "direct_children",
        (
            "direct children",
            "direct components",
            "parts directly below",
            "components directly below",
            "parts directly under",
            "components directly under",
            "immediate children",
        ),
    ),
    (
        "ancestor_chain",
        (
            "assembly chain",
            "complete chain",
            "full chain",
            "upward chain",
            "all higher assemblies",
            "ancestor chain",
            "higher assembly chain",
        ),
    ),
    (
        "direct_nha",
        (
            "direct nha",
            "next higher assembly",
            "nha of",
            "nha for",
            "parent assembly of",
            "direct parent assembly",
            "belongs to which assembly",
            "part of which assembly",
        ),
    ),
)

ELIGIBLE_BEHAVIORS = {
    "direct_answer",
    "ordered_chain_answer",
    "direct_children_answer",
    "tree_answer",
    "conflict_limited",
    "candidate_or_clarification",
    "page_and_trait_answer",
    "conflict_evidence_answer",
}


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "items", "rows", "cases", "questions"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def extract_user_query(payload: Mapping[str, Any]) -> str:
    """Extract the last user-facing query from TRACE-Net/OpenAI request shapes."""
    for key in ("question", "query", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, Mapping) or str(message.get("role") or "") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                pieces: list[str] = []
                for item in content:
                    if isinstance(item, Mapping) and item.get("type") in {"text", "input_text"}:
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            pieces.append(text.strip())
                if pieces:
                    return "\n".join(pieces)
    return ""


def classify_nha_intent(query: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", str(query or "")).strip()
    lowered = text.casefold()
    synthetic_match = SYNTHETIC_PART_RE.search(text)
    real_match = REAL_PART_RE.search(text)
    intent = ""
    for candidate, phrases in INTENT_PATTERNS:
        if any(phrase in lowered for phrase in phrases):
            intent = candidate
            break
    recognized = bool(intent and real_match and not synthetic_match)
    return {
        "schema_version": SCHEMA_VERSION,
        "route_id": ROUTE_ID if recognized else "",
        "recognized": recognized,
        "intent": intent,
        "part_number": real_match.group(0).upper() if real_match else "",
        "synthetic_part_detected": bool(synthetic_match),
        "synthetic_part_number": synthetic_match.group(0).upper() if synthetic_match else "",
        "reason": (
            "synthetic_identifier_blocked"
            if synthetic_match
            else "recognized_real_nha_query"
            if recognized
            else "nha_intent_without_part"
            if intent and not real_match
            else "not_an_nha_query"
        ),
    }


def _question_for_classification(classification: Mapping[str, Any], query: str) -> dict[str, Any]:
    return {
        "category": classification.get("intent") or "",
        "query": query,
    }


def _citation_tokens(count: int) -> str:
    return " ".join(f"[{index}]" for index in range(1, count + 1))


def render_gated_answer(result: Mapping[str, Any]) -> str:
    """Render a public Answer/Evidence/Limits contract with page citations."""
    behavior = str(result.get("behavior") or "")
    child = str(result.get("child") or "")
    parent = str(result.get("parent") or "")
    direct = str(result.get("direct_nha") or "")
    chain = [str(value) for value in result.get("chain") or []]
    children = [str(value) for value in result.get("direct_children") or []]
    descendants = [str(value) for value in result.get("descendants") or []]
    candidates = [str(value) for value in result.get("parent_candidates") or []]
    pages = _dedupe(result.get("pages") or [])
    citation = _citation_tokens(len(pages))

    if behavior == "direct_answer":
        sentence = f"The direct NHA of `{child}` is `{direct}`"
    elif behavior == "ordered_chain_answer":
        sentence = "The ordered assembly chain is " + " → ".join(f"`{value}`" for value in chain)
    elif behavior == "direct_children_answer":
        sentence = (
            f"Assembly `{parent}` has {len(children)} direct child relationship(s): "
            + ", ".join(f"`{value}`" for value in children)
        )
    elif behavior == "tree_answer":
        sentence = (
            f"Direct children of `{parent}`: "
            + (", ".join(f"`{value}`" for value in children) or "none")
            + ". Lower descendants: "
            + (", ".join(f"`{value}`" for value in descendants) or "none")
        )
    elif behavior in {"conflict_limited", "candidate_or_clarification", "conflict_evidence_answer"}:
        sentence = (
            f"No single direct NHA can be confirmed for `{child}`. Candidate parent assemblies: "
            + (", ".join(f"`{value}`" for value in candidates) or "none")
        )
    elif behavior == "page_and_trait_answer":
        sentence = f"The source-backed NHA relationship for `{child}` is carried by the cited page record(s)"
    else:
        sentence = "No source-backed NHA answer is released"
    answer_line = sentence.rstrip(".") + (f" {citation}." if citation else ".")

    evidence = [
        f"- [{index}] Source page `{page}`."
        for index, page in enumerate(pages, 1)
    ] or ["- No source-backed relationship page was returned."]

    limits = [
        "Only real N4 assembly relationships are available to this production route.",
        "A higher ancestor is not treated as the direct NHA unless every intermediate hop is supported.",
    ]
    if behavior in {"conflict_limited", "candidate_or_clarification", "conflict_evidence_answer"}:
        limits.append("Project, configuration, usage-code, revision, or effectivity context is required before choosing one candidate.")
    if result.get("limits"):
        limits.extend(str(value) for value in result.get("limits") or [])

    return "\n".join([
        "## Answer",
        "",
        answer_line,
        "",
        "## Evidence",
        "",
        *evidence,
        "",
        "## Limits",
        "",
        *[f"- {value}" for value in _dedupe(limits)],
    ])


def public_contract_valid(answer: str, pages: Sequence[str]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    text = str(answer or "")
    for heading in ("## Answer", "## Evidence", "## Limits"):
        if heading not in text:
            failures.append(f"missing_heading:{heading}")
    lowered = text.casefold()
    if "synthetic benchmark" in lowered or SYNTHETIC_PART_RE.search(text):
        failures.append("synthetic_leak")
    for marker in ("relationship_id", "row_id", "truth_mode", "benchmark_truth_status"):
        if marker in lowered:
            failures.append(f"internal_leak:{marker}")
    for page in pages:
        if str(page) and str(page) not in text:
            failures.append(f"missing_page:{page}")
    if pages and "[1]" not in text:
        failures.append("missing_citation_marker")
    return not failures, failures


@dataclass
class NHAIntegrationAdapter:
    engine: Any
    mode: str = "shadow"
    telemetry_path: Path | None = None
    telemetry_include_query: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"shadow", "gated"}:
            raise ValueError("mode_must_be_shadow_or_gated")
        self._telemetry_lock = threading.Lock()

    def evaluate(self, query: str) -> dict[str, Any]:
        classification = classify_nha_intent(query)
        decision: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "module": MODULE,
            "status": STATUS,
            "mode": self.mode,
            "route_id": classification.get("route_id") or "",
            "intent": classification.get("intent") or "",
            "part_number": classification.get("part_number") or "",
            "recognized": bool(classification.get("recognized")),
            "synthetic_blocked": bool(classification.get("synthetic_part_detected")),
            "action": "passthrough",
            "shadow_candidate": False,
            "override": False,
            "override_eligible": False,
            "result_behavior": "",
            "pages": [],
            "public_answer": "",
            "query_sha256": _sha256_text(query),
            "production_graph_write_count": 0,
            "llm_call_count": 0,
            "synthetic_access_count": 0,
        }
        if classification.get("synthetic_part_detected"):
            decision["action"] = "synthetic_blocked"
            self._record(decision, query)
            return decision
        if not classification.get("recognized"):
            self._record(decision, query)
            return decision

        part = str(classification.get("part_number") or "")
        intent = str(classification.get("intent") or "")
        method_name = {
            "direct_nha": "direct_nha",
            "ancestor_chain": "ancestor_chain",
            "direct_children": "direct_children",
            "direct_vs_descendant": "descendants",
            "relationship_evidence_page": "page_evidence",
        }.get(intent, "")
        method = getattr(self.engine, method_name, None) if method_name else None
        if callable(method):
            result = method(part)
        else:
            result = self.engine.execute_question(_question_for_classification(classification, query))
        behavior = str(result.get("behavior") or "")
        pages = _dedupe(result.get("pages") or [])
        eligible = behavior in ELIGIBLE_BEHAVIORS and bool(pages)
        decision.update({
            "result_behavior": behavior,
            "pages": pages,
            "override_eligible": eligible,
            "result_summary": {
                "direct_nha": str(result.get("direct_nha") or ""),
                "parent_candidates": _dedupe(result.get("parent_candidates") or []),
                "chain": _dedupe(result.get("chain") or []),
                "direct_children": _dedupe(result.get("direct_children") or []),
                "descendants": _dedupe(result.get("descendants") or []),
            },
        })
        if eligible and self.mode == "shadow":
            decision["action"] = "shadow_candidate"
            decision["shadow_candidate"] = True
        elif eligible and self.mode == "gated":
            decision["action"] = "override"
            decision["override"] = True
            decision["public_answer"] = render_gated_answer(result)
        self._record(decision, query)
        return decision

    def _record(self, decision: Mapping[str, Any], query: str) -> None:
        if not self.telemetry_path:
            return
        payload = {
            key: value
            for key, value in decision.items()
            if key not in {"public_answer", "result_rows"}
        }
        payload["timestamp_unix"] = round(time.time(), 3)
        if self.telemetry_include_query:
            payload["query"] = query
        path = Path(self.telemetry_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._telemetry_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def build_gate_bank(
    real_cases: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    *,
    total: int = 40,
) -> list[dict[str, Any]]:
    """Build a deterministic 34-real + 6-control N7/N8 gate bank."""
    bank: list[dict[str, Any]] = []

    def add(kind: str, query: str, expected_real_route: bool, source: Mapping[str, Any] | None = None) -> None:
        bank.append({
            "case_id": f"NHA78-{len(bank) + 1:03d}",
            "kind": kind,
            "query": query,
            "expected_real_route": expected_real_route,
            "source_case_id": str((source or {}).get("case_id") or ""),
        })

    for case in list(real_cases)[:20]:
        child = str(case.get("child_part") or "")
        if child:
            add("direct_nha", f"What is the direct NHA of part {child}?", True, case)

    supported = [
        dict(row)
        for row in relationships
        if row.get("relationship_status") == "source_supported" and row.get("direct_nha")
    ]
    supported.sort(key=lambda row: (
        -int(row.get("hierarchy_depth") or 0),
        str(row.get("child_part") or ""),
        str(row.get("direct_nha") or ""),
    ))

    seen_chain: set[str] = set()
    for row in supported:
        child = str(row.get("child_part") or "")
        if int(row.get("hierarchy_depth") or 0) < 2 or not child or child in seen_chain:
            continue
        seen_chain.add(child)
        add("ancestor_chain", f"Show the complete assembly chain above {child}.", True, row)
        if len(seen_chain) >= 5:
            break

    seen_parent: set[str] = set()
    for row in supported:
        parent = str(row.get("direct_nha") or "")
        if not parent or parent in seen_parent:
            continue
        seen_parent.add(parent)
        add("direct_children", f"List the direct children of assembly {parent}.", True, row)
        if len(seen_parent) >= 5:
            break

    adjacency: dict[str, set[str]] = {}
    for row in supported:
        parent = str(row.get("direct_nha") or "")
        child = str(row.get("child_part") or "")
        adjacency.setdefault(parent, set()).add(child)
    roots = sorted(
        parent
        for parent, children in adjacency.items()
        if any(child in adjacency for child in children)
    )
    for parent in roots[:2]:
        add("direct_vs_descendant", f"Show direct versus lower descendants below assembly {parent}.", True)

    real_target = max(0, total - 6)
    evidence_index = 0
    direct_sources = list(real_cases)
    while len(bank) < real_target and direct_sources:
        source = direct_sources[evidence_index % len(direct_sources)]
        child = str(source.get("child_part") or "")
        add("relationship_evidence_page", f"Which page proves the NHA relationship for {child}?", True, source)
        evidence_index += 1

    for query in (
        "Show the warning on page t_p_120_1176_p000470.",
        "Find part 120-29067-003 and cite its strongest page.",
        "What can TRACE-Net do?",
    ):
        add("non_nha_control", query, False)

    for query in (
        "What is the direct NHA of synthetic part 990-91001-001?",
        "Show the complete assembly chain above 990-92001-001.",
        "List the direct children of synthetic assembly 990-93001-001.",
    ):
        add("synthetic_block_control", query, False)
    return bank[:total]


def evaluate_gate_bank(
    bank: Sequence[Mapping[str, Any]],
    adapter: NHAIntegrationAdapter,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in bank:
        started = time.perf_counter()
        decision = adapter.evaluate(str(case.get("query") or ""))
        failures: list[str] = []
        expected_real = bool(case.get("expected_real_route"))
        kind = str(case.get("kind") or "")
        if expected_real:
            if not decision.get("recognized"):
                failures.append("real_nha_not_recognized")
            if not decision.get("override_eligible"):
                failures.append(f"real_nha_not_eligible:{decision.get('result_behavior')}")
            expected_action = "shadow_candidate" if adapter.mode == "shadow" else "override"
            if decision.get("action") != expected_action:
                failures.append(f"action expected={expected_action} actual={decision.get('action')}")
            if adapter.mode == "shadow" and decision.get("override"):
                failures.append("shadow_mode_override")
            if adapter.mode == "gated":
                valid, contract_failures = public_contract_valid(
                    str(decision.get("public_answer") or ""),
                    decision.get("pages") or [],
                )
                if not valid:
                    failures.extend(contract_failures)
        elif kind == "synthetic_block_control":
            if decision.get("action") != "synthetic_blocked":
                failures.append("synthetic_not_blocked")
            if decision.get("override") or decision.get("synthetic_access_count"):
                failures.append("synthetic_overlay_accessed")
        else:
            if decision.get("action") != "passthrough":
                failures.append(f"non_nha_false_route:{decision.get('action')}")
        results.append({
            "case_id": case.get("case_id") or "",
            "kind": kind,
            "query": case.get("query") or "",
            "mode": adapter.mode,
            "passed": not failures,
            "failures": failures,
            "decision": decision,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        })
    return results


def validate_gate_results(
    shadow_results: Sequence[Mapping[str, Any]],
    gated_results: Sequence[Mapping[str, Any]],
    *,
    expected_count: int = 40,
) -> dict[str, Any]:
    failures: list[str] = []
    if len(shadow_results) != expected_count:
        failures.append(f"shadow_count expected={expected_count} actual={len(shadow_results)}")
    if len(gated_results) != expected_count:
        failures.append(f"gated_count expected={expected_count} actual={len(gated_results)}")
    shadow_pass = sum(bool(row.get("passed")) for row in shadow_results)
    gated_pass = sum(bool(row.get("passed")) for row in gated_results)
    if shadow_pass != len(shadow_results):
        failures.append(f"shadow_fail_count:{len(shadow_results) - shadow_pass}")
    if gated_pass != len(gated_results):
        failures.append(f"gated_fail_count:{len(gated_results) - gated_pass}")
    shadow_overrides = sum(bool((row.get("decision") or {}).get("override")) for row in shadow_results)
    if shadow_overrides:
        failures.append(f"shadow_override_count:{shadow_overrides}")
    false_gated_overrides = sum(
        bool((row.get("decision") or {}).get("override"))
        for row in gated_results
        if row.get("kind") in {"non_nha_control", "synthetic_block_control"}
    )
    if false_gated_overrides:
        failures.append(f"false_gated_override_count:{false_gated_overrides}")
    synthetic_access = sum(
        int((row.get("decision") or {}).get("synthetic_access_count") or 0)
        for row in [*shadow_results, *gated_results]
    )
    if synthetic_access:
        failures.append(f"synthetic_access_count:{synthetic_access}")
    gated_overrides = sum(bool((row.get("decision") or {}).get("override")) for row in gated_results)
    public_contract_pass = sum(
        public_contract_valid(
            str((row.get("decision") or {}).get("public_answer") or ""),
            (row.get("decision") or {}).get("pages") or [],
        )[0]
        for row in gated_results
        if (row.get("decision") or {}).get("override")
    )
    if public_contract_pass != gated_overrides:
        failures.append("gated_public_contract_failure")
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": [],
        "counts": {
            "shadow_case_count": len(shadow_results),
            "shadow_pass_count": shadow_pass,
            "shadow_fail_count": len(shadow_results) - shadow_pass,
            "shadow_candidate_count": sum(
                bool((row.get("decision") or {}).get("shadow_candidate")) for row in shadow_results
            ),
            "shadow_override_count": shadow_overrides,
            "gated_case_count": len(gated_results),
            "gated_pass_count": gated_pass,
            "gated_fail_count": len(gated_results) - gated_pass,
            "gated_override_count": gated_overrides,
            "gated_public_contract_pass_count": public_contract_pass,
            "false_gated_override_count": false_gated_overrides,
            "synthetic_block_count": sum(
                (row.get("decision") or {}).get("action") == "synthetic_blocked"
                for row in [*shadow_results, *gated_results]
            ),
            "synthetic_access_count": synthetic_access,
            "llm_call_count_for_nha_overrides": 0,
            "production_graph_write_count": 0,
            "source_artifact_mutation_count": 0,
        },
        "safety_contract": {
            "read_only": True,
            "shadow_never_overrides": True,
            "synthetic_artifacts_loaded": False,
            "synthetic_identifier_blocked": True,
            "only_real_phase4_relationships_loaded": True,
            "non_nha_passthrough": True,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "llm_call_count_for_nha_overrides": 0,
        },
    }


def http_json(
    url: str,
    payload: Mapping[str, Any] | None,
    *,
    api_key: str,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def openai_completion(answer: str, model: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-trace-nha-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def extract_answer(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message")
    return str(message.get("content") or "") if isinstance(message, Mapping) else ""


def stream_body(answer: str, model: str) -> bytes:
    completion_id = "chatcmpl-trace-nha-" + uuid.uuid4().hex[:16]
    created = int(time.time())
    events = ["data: " + json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }, ensure_ascii=False) + "\n\n"]
    for offset in range(0, len(answer), 240):
        events.append("data: " + json.dumps({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": answer[offset:offset + 240]}, "finish_reason": None}],
        }, ensure_ascii=False) + "\n\n")
    events.append("data: " + json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }, ensure_ascii=False) + "\n\n")
    events.append("data: [DONE]\n\n")
    return "".join(events).encode("utf-8")


def load_real_engine(phase4_dir: str | Path, *, max_depth: int = 8) -> tuple[Any, dict[str, Any]]:
    """Load only real N4 artifacts and instantiate the established N6 engine."""
    from src.trace_net.graph.trace_net_nha_phase6_query_benchmark_v1 import NHAQueryEngine

    root = Path(phase4_dir).resolve()
    relationship_path = root / "trace_net_nha_hierarchy_relationships_v1.json"
    quality_path = root / "trace_net_nha_phase4_quality_v1.json"
    answer_key_path = root / "trace_net_nha_phase4_answer_key_v1.json"
    missing = [str(path) for path in (relationship_path, quality_path, answer_key_path) if not path.exists()]
    if missing:
        raise FileNotFoundError("missing_nha_phase7_8_inputs: " + ", ".join(missing))
    quality = _read_json(quality_path)
    if str(quality.get("quality_status") or "") != "PASS":
        raise ValueError("phase4_quality_status_not_pass")
    relationships = _records(_read_json(relationship_path))
    answer_key = _records(_read_json(answer_key_path))
    engine = NHAQueryEngine(relationships, truth_mode="real_source", max_depth=max_depth)
    return engine, {
        "phase4_dir": str(root),
        "relationships": relationships,
        "answer_key": answer_key,
        "relationship_sha256": hashlib.sha256(relationship_path.read_bytes()).hexdigest(),
        "quality_sha256": hashlib.sha256(quality_path.read_bytes()).hexdigest(),
        "answer_key_sha256": hashlib.sha256(answer_key_path.read_bytes()).hexdigest(),
    }
