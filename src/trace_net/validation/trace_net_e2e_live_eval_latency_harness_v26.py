from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_live_eval_latency_harness_v26"
VERSION = "v26"
MODEL_ID_DEFAULT = "trace-net-e2e-live-orchestrator-gemma-v25"


@dataclass(frozen=True)
class EvalQuery:
    eval_query_id: str
    user_query: str
    expected_behavior: str  # "final_gated_answer" or "audit_only"
    expected_intent: str
    expected_value: str = ""
    notes: str = ""


def standard_eval_queries() -> List[EvalQuery]:
    """Return a compact deterministic suite for the live v25 endpoint."""
    return [
        EvalQuery(
            "eval_v26_0001",
            "Find part number 120-36833-503",
            "final_gated_answer",
            "part_number",
            "120-36833-503",
            "present exact part number should cite direct source-truth evidence",
        ),
        EvalQuery(
            "eval_v26_0002",
            "Find part number DOES-NOT-EXIST-999",
            "audit_only",
            "part_number",
            "DOES-NOT-EXIST-999",
            "missing exact part number must not return broad noisy matches",
        ),
        EvalQuery(
            "eval_v26_0003",
            "Where is manual reference 25-21-00 used?",
            "final_gated_answer",
            "manual_page_reference",
            "25-21-00",
            "present manual reference should cite direct source-truth evidence",
        ),
        EvalQuery(
            "eval_v26_0004",
            "Where is manual reference 99-99-99 used?",
            "audit_only",
            "manual_page_reference",
            "99-99-99",
            "missing manual reference must be audit-only",
        ),
        EvalQuery(
            "eval_v26_0005",
            "Search table text ILLUSTRATED PARTS LIST",
            "final_gated_answer",
            "table_text",
            "ILLUSTRATED PARTS LIST",
            "present table text should cite exact source-truth text",
        ),
        EvalQuery(
            "eval_v26_0006",
            "Search table text THIS TEXT DOES NOT EXIST",
            "audit_only",
            "table_text",
            "THIS TEXT DOES NOT EXIST",
            "missing table text must not match nearby OCR noise",
        ),
    ]


def load_eval_queries_from_jsonl(path: Path) -> List[EvalQuery]:
    queries: List[EvalQuery] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        queries.append(
            EvalQuery(
                eval_query_id=str(row.get("eval_query_id") or f"eval_v26_custom_{i:04d}"),
                user_query=str(row["user_query"]),
                expected_behavior=str(row.get("expected_behavior") or "final_gated_answer"),
                expected_intent=str(row.get("expected_intent") or "unknown"),
                expected_value=str(row.get("expected_value") or ""),
                notes=str(row.get("notes") or ""),
            )
        )
    return queries


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _endpoint_root(endpoint_base_url: str) -> str:
    s = endpoint_base_url.rstrip("/")
    if s.endswith("/v1"):
        return s[:-3]
    return s


def _post_chat_completion(
    *,
    endpoint_base_url: str,
    model: str,
    user_query: str,
    request_timeout: float,
    api_key: str,
) -> Dict[str, Any]:
    url = endpoint_base_url.rstrip("/") + "/v1/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": user_query}],
            "temperature": 0,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=request_timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _get_health(endpoint_base_url: str, request_timeout: float) -> Dict[str, Any]:
    url = _endpoint_root(endpoint_base_url).rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=request_timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except Exception as exc:  # pragma: no cover - diagnostics only
        return {"status": "unreachable", "error": str(exc)}


def _extract_assistant_content(payload: Mapping[str, Any]) -> str:
    try:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        return str(msg.get("content") or "")
    except Exception:
        return ""


def _extract_trace_net(payload: Mapping[str, Any]) -> Dict[str, Any]:
    tn = payload.get("trace_net")
    return dict(tn) if isinstance(tn, Mapping) else {}


def _is_audit_only(trace_net: Mapping[str, Any], content: str) -> bool:
    status = str(trace_net.get("final_gate_status") or "")
    if "AUDIT_ONLY" in status:
        return True
    low = content.lower()
    return "did not find direct citation-ready source-truth evidence" in low or "no source-truth claim is made" in low


def _looks_like_final_answer(trace_net: Mapping[str, Any], content: str) -> bool:
    status = str(trace_net.get("final_gate_status") or "")
    if status.endswith("PASS") or "FINAL_GATE_PASS" in status:
        return True
    return bool(content.strip()) and not _is_audit_only(trace_net, content)


def _citation_like_count(trace_net: Mapping[str, Any], content: str) -> int:
    value = trace_net.get("citation_like_count")
    if isinstance(value, int):
        return value
    # lightweight fallback without regex dependency quirks
    count = 0
    for i in range(1, 51):
        if f"[{i}]" in content:
            count += 1
    return count


def evaluate_response(eval_query: EvalQuery, payload: Optional[Mapping[str, Any]], error: str, latency_ms: float) -> Dict[str, Any]:
    payload = payload or {}
    content = _extract_assistant_content(payload)
    trace_net = _extract_trace_net(payload)
    citation_count = _citation_like_count(trace_net, content)
    final_answer = _looks_like_final_answer(trace_net, content)
    audit_only = _is_audit_only(trace_net, content)
    total_match_count = trace_net.get("total_match_count", 0)
    returned_match_count = trace_net.get("returned_match_count", 0)
    result_was_capped = bool(trace_net.get("result_was_capped"))
    final_gate_status = str(trace_net.get("final_gate_status") or "")
    llm_status = str(trace_net.get("llm_status") or "")

    response_ok = not error and bool(content.strip())
    expected_final = eval_query.expected_behavior == "final_gated_answer"
    expected_audit = eval_query.expected_behavior == "audit_only"

    contains_expected_value = True
    if eval_query.expected_value:
        contains_expected_value = eval_query.expected_value.lower() in content.lower()

    false_positive = False
    false_negative = False

    if expected_audit:
        false_positive = bool(
            response_ok
            and not audit_only
            and (final_answer or citation_count > 0 or int(total_match_count or 0) > 0)
        )
    if expected_final:
        false_negative = bool(
            (not response_ok)
            or audit_only
            or not final_answer
            or citation_count < 1
            or not contains_expected_value
        )

    unsupported_claim_detected = false_positive or False
    cap_disclosure_detected = True
    if result_was_capped:
        low = content.lower()
        cap_disclosure_detected = "capped" in low or "returned" in low or "additional" in low

    passed = bool(response_ok and not false_positive and not false_negative and not unsupported_claim_detected and cap_disclosure_detected)

    return {
        "eval_query_id": eval_query.eval_query_id,
        "user_query": eval_query.user_query,
        "expected_behavior": eval_query.expected_behavior,
        "expected_intent": eval_query.expected_intent,
        "expected_value": eval_query.expected_value,
        "notes": eval_query.notes,
        "passed": passed,
        "response_ok": response_ok,
        "latency_ms": round(latency_ms, 3),
        "assistant_content": content,
        "assistant_preview": content[:500],
        "trace_net": trace_net,
        "query_intent_observed": trace_net.get("query_intent"),
        "final_gate_status": final_gate_status,
        "llm_status": llm_status,
        "audit_only": audit_only,
        "final_answer": final_answer,
        "citation_like_count": citation_count,
        "total_match_count": total_match_count,
        "returned_match_count": returned_match_count,
        "result_was_capped": result_was_capped,
        "cap_disclosure_detected": cap_disclosure_detected,
        "contains_expected_value": contains_expected_value,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "unsupported_claim_detected": unsupported_claim_detected,
        "error": error,
    }


def run_eval_queries(
    *,
    endpoint_base_url: str,
    model: str,
    queries: Sequence[EvalQuery],
    request_timeout: float,
    api_key: str = "trace-net-local",
    chat_fn: Optional[Callable[[str], Mapping[str, Any]]] = None,
    clock: Callable[[], float] = time.perf_counter,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for q in queries:
        start = clock()
        payload: Optional[Mapping[str, Any]] = None
        error = ""
        try:
            if chat_fn is not None:
                payload = chat_fn(q.user_query)
            else:
                payload = _post_chat_completion(
                    endpoint_base_url=endpoint_base_url,
                    model=model,
                    user_query=q.user_query,
                    request_timeout=request_timeout,
                    api_key=api_key,
                )
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            error = f"HTTPError {exc.code}: {body[:500]}"
        except Exception as exc:  # pragma: no cover - exercised by live diagnostics
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = (clock() - start) * 1000.0
        records.append(evaluate_response(q, payload, error, latency_ms))
    return records


def summarize_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    latencies = [float(r.get("latency_ms") or 0.0) for r in records if r.get("response_ok")]
    total_latency = sum(latencies)
    avg_latency = (total_latency / len(latencies)) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    return {
        "eval_query_count": len(records),
        "success_count": sum(1 for r in records if r.get("passed")),
        "response_ok_count": sum(1 for r in records if r.get("response_ok")),
        "audit_only_count": sum(1 for r in records if r.get("audit_only")),
        "final_answer_count": sum(1 for r in records if r.get("final_answer")),
        "false_positive_count": sum(1 for r in records if r.get("false_positive")),
        "false_negative_count": sum(1 for r in records if r.get("false_negative")),
        "unsupported_claim_count": sum(1 for r in records if r.get("unsupported_claim_detected")),
        "llm_call_error_count": sum(1 for r in records if r.get("error")),
        "cap_disclosure_required_count": sum(1 for r in records if r.get("result_was_capped")),
        "cap_disclosure_detected_count": sum(1 for r in records if r.get("result_was_capped") and r.get("cap_disclosure_detected")),
        "citation_supported_final_answer_count": sum(
            1 for r in records if r.get("final_answer") and int(r.get("citation_like_count") or 0) >= 1
        ),
        "latency_record_count": len(latencies),
        "total_latency_ms": round(total_latency, 3),
        "avg_latency_ms": round(avg_latency, 3),
        "max_latency_ms": round(max_latency, 3),
    }


def quality_checks(
    report: Mapping[str, Any],
    *,
    min_eval_queries: int = 1,
    min_success_count: int = 1,
    min_latency_records: int = 1,
    max_false_positive_count: int = 0,
    max_false_negative_count: int = 0,
    max_unsupported_claim_count: int = 0,
    max_llm_call_errors: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> List[Dict[str, Any]]:
    def get(name: str) -> Any:
        return report.get(name, 0)

    checks: List[Tuple[str, Any, str, Any]] = [
        ("eval_query_count", get("eval_query_count"), ">=", min_eval_queries),
        ("success_count", get("success_count"), ">=", min_success_count),
        ("latency_record_count", get("latency_record_count"), ">=", min_latency_records),
        ("false_positive_count", get("false_positive_count"), "<=", max_false_positive_count),
        ("false_negative_count", get("false_negative_count"), "<=", max_false_negative_count),
        ("unsupported_claim_count", get("unsupported_claim_count"), "<=", max_unsupported_claim_count),
        ("llm_call_error_count", get("llm_call_error_count"), "<=", max_llm_call_errors),
        ("answer_permission_count", get("answer_permission_count"), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", get("source_truth_mutation_allowed_count"), "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        checks.append(("require_no_answer_permission", get("answer_permission_count"), "==", 0))

    out: List[Dict[str, Any]] = []
    for name, observed, op, expected in checks:
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:  # pragma: no cover
            raise ValueError(op)
        out.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)})
    return out


def quality_status(checks: Sequence[Mapping[str, Any]]) -> str:
    return "PASS" if all(bool(c.get("passed")) for c in checks) else "FAIL"


def build_report(
    *,
    endpoint_base_url: str,
    model: str,
    output_dir: Path,
    queries: Sequence[EvalQuery],
    request_timeout: float,
    api_key: str = "trace-net-local",
    min_eval_queries: int = 1,
    min_success_count: int = 1,
    min_latency_records: int = 1,
    max_false_positive_count: int = 0,
    max_false_negative_count: int = 0,
    max_unsupported_claim_count: int = 0,
    max_llm_call_errors: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    run_health_check: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    health = _get_health(endpoint_base_url, min(request_timeout, 15.0)) if run_health_check else {}
    records = run_eval_queries(
        endpoint_base_url=endpoint_base_url,
        model=model,
        queries=queries,
        request_timeout=request_timeout,
        api_key=api_key,
    )
    summary = summarize_records(records)
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0
    raw_scan_count = 0
    graph_rebuild_count = 0
    for r in records:
        safety = ((r.get("trace_net") or {}).get("safety") or {}) if isinstance(r.get("trace_net"), Mapping) else {}
        answer_permission_count += 1 if safety.get("answer_permission") else 0
        source_truth_mutation_allowed_count += 1 if safety.get("source_truth_mutation_allowed") else 0
        raw_scan_count += 1 if safety.get("raw_5tb_scan_at_query_time") else 0
        graph_rebuild_count += 1 if safety.get("graph_rebuild_at_query_time") else 0

    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "E2E_LIVE_EVAL_LATENCY_HARNESS_READY",
        "endpoint_base_url": endpoint_base_url,
        "model": model,
        "health": health,
        "contract": {
            "evaluation_only": True,
            "llm_called_by_endpoint": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "measures_live_endpoint_latency": True,
            "missing_exact_values_must_be_audit_only": True,
        },
        **summary,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "raw_5tb_scan_observed_count": raw_scan_count,
        "graph_rebuild_observed_count": graph_rebuild_count,
        "eval_records": records,
    }
    checks = quality_checks(
        report,
        min_eval_queries=min_eval_queries,
        min_success_count=min_success_count,
        min_latency_records=min_latency_records,
        max_false_positive_count=max_false_positive_count,
        max_false_negative_count=max_false_negative_count,
        max_unsupported_claim_count=max_unsupported_claim_count,
        max_llm_call_errors=max_llm_call_errors,
        max_answer_permission_count=max_answer_permission_count,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        require_no_answer_permission=require_no_answer_permission,
    )
    report["quality_checks"] = checks
    report["quality_status"] = quality_status(checks)

    report_path = output_dir / "trace_net_e2e_live_eval_latency_harness_v26.json"
    records_path = output_dir / "trace_net_e2e_live_eval_latency_harness_records_v26.jsonl"
    inspect_path = output_dir / "trace_net_e2e_live_eval_latency_harness_v26.md"
    write_json(report_path, report)
    write_jsonl(records_path, records)
    inspect_path.write_text(render_markdown(report, report_path, records_path), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["records_jsonl_path"] = str(records_path)
    report["inspect_md_path"] = str(inspect_path)
    write_json(report_path, report)
    return report


def render_markdown(report: Mapping[str, Any], report_path: Path, records_path: Path) -> str:
    lines = [
        "# TRACE-Net E2E Live Eval + Latency Harness v26",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
        f"- endpoint_base_url: {report.get('endpoint_base_url')}",
        f"- model: {report.get('model')}",
        f"- eval_query_count: {report.get('eval_query_count')}",
        f"- success_count: {report.get('success_count')}",
        f"- false_positive_count: {report.get('false_positive_count')}",
        f"- false_negative_count: {report.get('false_negative_count')}",
        f"- unsupported_claim_count: {report.get('unsupported_claim_count')}",
        f"- llm_call_error_count: {report.get('llm_call_error_count')}",
        f"- audit_only_count: {report.get('audit_only_count')}",
        f"- final_answer_count: {report.get('final_answer_count')}",
        f"- cap_disclosure_required_count: {report.get('cap_disclosure_required_count')}",
        f"- cap_disclosure_detected_count: {report.get('cap_disclosure_detected_count')}",
        f"- avg_latency_ms: {report.get('avg_latency_ms')}",
        f"- max_latency_ms: {report.get('max_latency_ms')}",
        f"- total_latency_ms: {report.get('total_latency_ms')}",
        f"- answer_permission_count: {report.get('answer_permission_count')}",
        f"- source_truth_mutation_allowed_count: {report.get('source_truth_mutation_allowed_count')}",
        "",
        "## Contract",
        "- This harness evaluates the live v25 endpoint; it does not mutate source truth.",
        "- Missing exact values must return audit-only rather than broad/noisy matches.",
        "- Present exact values should return source-truth citations.",
        "- Latency is measured for the complete endpoint call; v26 does not yet split retrieval vs Gemma timing unless the endpoint exposes those timings.",
        "",
        "## Evaluation records",
    ]
    for r in report.get("eval_records", []):
        lines.extend(
            [
                f"### {r.get('eval_query_id')} — {'PASS' if r.get('passed') else 'FAIL'}",
                f"- query: {r.get('user_query')}",
                f"- expected_behavior: {r.get('expected_behavior')}",
                f"- final_gate_status: {r.get('final_gate_status')}",
                f"- citation_like_count: {r.get('citation_like_count')}",
                f"- total_match_count: {r.get('total_match_count')}",
                f"- returned_match_count: {r.get('returned_match_count')}",
                f"- result_was_capped: {r.get('result_was_capped')}",
                f"- latency_ms: {r.get('latency_ms')}",
                f"- false_positive: {r.get('false_positive')}",
                f"- false_negative: {r.get('false_negative')}",
                f"- preview: {str(r.get('assistant_preview') or '').replace(chr(10), ' ')[:500]}",
                "",
            ]
        )
    lines.extend(["## Quality checks"])
    for c in report.get("quality_checks", []):
        prefix = "PASS" if c.get("passed") else "FAIL"
        lines.append(f"- {prefix} {c.get('name')}: observed={c.get('observed')} expected={c.get('op')} {c.get('expected')}")
    lines.extend(["", f"report_path: `{report_path}`", f"records_jsonl_path: `{records_path}`", ""])
    return "\n".join(lines)
