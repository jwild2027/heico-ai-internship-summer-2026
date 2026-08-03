
"""TRACE-Net Engineering Gemma Draft Runner v1.

Controlled local runner for Gemma/Ollama draft payloads.

Reads request payload artifacts from engineering_gemma_draft_adapter_v1 and can:
- validate payloads without sending them (default dry-run)
- optionally send to local Ollama/OpenAI-compatible endpoint when --execute is set
- save draft responses as artifacts
- keep final answer permission locked off

Safety:
- no source-truth mutation
- no retrieval execution
- no DB/search/vector writes
- no final answer permission
- no direct answer permission
- draft response only; final gate required
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MODULE_VERSION = "trace_net_engineering_gemma_draft_runner_v1"
REPORT_NAME = "trace_net_engineering_gemma_draft_runner_v1.json"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _repo_path(path_text: str) -> Path:
    # Normalize Windows backslashes that may appear in JSON generated on Git Bash/Windows.
    return Path(str(path_text).replace("\\", "/"))


def _extract_ollama_text(response_payload: Mapping[str, Any]) -> str:
    message = response_payload.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message.get("content"))
    if response_payload.get("response") is not None:
        return str(response_payload.get("response"))
    return ""


def _extract_openai_text(response_payload: Mapping[str, Any]) -> str:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content"))
            if first.get("text") is not None:
                return str(first.get("text"))
    return ""


def _extract_draft_text(provider: str, response_payload: Mapping[str, Any]) -> str:
    if provider == "ollama":
        return _extract_ollama_text(response_payload)
    if provider == "openai_compatible":
        return _extract_openai_text(response_payload)
    return ""


def _post_json(
    *,
    endpoint: str,
    payload: Mapping[str, Any],
    provider: str,
    api_key: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if provider == "openai_compatible":
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _draft_safety_scan(text: str) -> Dict[str, Any]:
    lowered = text.lower()
    risky_phrases = [
        "approved replacement",
        "guaranteed fit",
        "safe to install",
        "engineering approval",
        "interchangeable",
        "drop-in replacement",
        "certified",
        "airworthy",
    ]
    hits = [phrase for phrase in risky_phrases if phrase in lowered]
    citation_markers = [
        "page_id",
        "source",
        "citation",
        "source trace",
        "trace",
        "p000",
    ]
    citation_marker_count = sum(1 for marker in citation_markers if marker in lowered)
    return {
        "risky_phrase_hits": hits,
        "risky_phrase_hit_count": len(hits),
        "citation_marker_count": citation_marker_count,
        "draft_text_char_count": len(text),
        "empty_draft": len(text.strip()) == 0,
    }


def _draft_response_status(
    *,
    sent: bool,
    response_received: bool,
    draft_text: str,
    error: Optional[str],
    risky_count: int,
) -> str:
    if not sent:
        return "dry_run_not_sent"
    if error:
        return "request_error"
    if not response_received:
        return "no_response"
    if not draft_text.strip():
        return "empty_draft_response"
    if risky_count:
        return "draft_received_final_gate_required_with_risk_flags"
    return "draft_received_final_gate_required"


def build_runner_record(
    *,
    adapter_record: Mapping[str, Any],
    index: int,
    output_dir: Path,
    execute: bool,
    timeout_seconds: int,
    api_key_override: Optional[str],
) -> Dict[str, Any]:
    provider = str(adapter_record.get("provider") or "ollama")
    endpoint = str(adapter_record.get("endpoint") or "")
    request_payload_path = _repo_path(str(adapter_record.get("request_payload_path") or ""))
    request_payload = _read_json(request_payload_path)
    api_key = api_key_override if api_key_override is not None else "ollama"

    response_payload: Dict[str, Any] = {}
    draft_text = ""
    error: Optional[str] = None
    response_received = False
    request_sent = False
    latency_ms: Optional[int] = None

    if execute:
        request_sent = True
        started = time.time()
        try:
            response_payload = _post_json(
                endpoint=endpoint,
                payload=request_payload,
                provider=provider,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
            latency_ms = int((time.time() - started) * 1000)
            response_received = True
            draft_text = _extract_draft_text(provider, response_payload)
        except Exception as exc:  # network/model errors are captured as artifact evidence, not thrown
            latency_ms = int((time.time() - started) * 1000)
            error = f"{type(exc).__name__}: {exc}"

    safety_scan = _draft_safety_scan(draft_text)
    status = _draft_response_status(
        sent=request_sent,
        response_received=response_received,
        draft_text=draft_text,
        error=error,
        risky_count=safety_scan["risky_phrase_hit_count"],
    )

    draft_payload_path = output_dir / "draft_responses" / f"engineering_gemma_draft_response_{index+1:04d}.json"
    response_artifact = {
        "source_adapter_record_id": adapter_record.get("adapter_record_id"),
        "source_draft_packet_id": adapter_record.get("source_draft_packet_id"),
        "provider": provider,
        "endpoint": endpoint,
        "model_id": adapter_record.get("model_id"),
        "request_payload_path": str(request_payload_path),
        "request_sent": request_sent,
        "response_received": response_received,
        "latency_ms": latency_ms,
        "error": error,
        "draft_text": draft_text,
        "raw_response": response_payload,
        "draft_safety_scan": safety_scan,
        "ready_for_final_answer": False,
        "answer_permission": False,
    }
    _write_json(draft_payload_path, response_artifact)

    return {
        "runner_record_version": MODULE_VERSION,
        "runner_record_id": f"engineering_gemma_draft_runner_{index+1:04d}",
        "source_adapter_record_id": adapter_record.get("adapter_record_id"),
        "source_draft_packet_id": adapter_record.get("source_draft_packet_id"),
        "question_id": adapter_record.get("question_id"),
        "user_question": adapter_record.get("user_question"),
        "intent_family": adapter_record.get("intent_family"),
        "selected_playbook_id": adapter_record.get("selected_playbook_id"),
        "provider": provider,
        "endpoint": endpoint,
        "model_id": adapter_record.get("model_id"),
        "request_payload_path": str(request_payload_path),
        "draft_response_path": str(draft_payload_path),
        "execute_requested": execute,
        "request_sent": request_sent,
        "response_received": response_received,
        "request_error": error,
        "latency_ms": latency_ms,
        "draft_text_char_count": len(draft_text),
        "draft_safety_scan": safety_scan,
        "draft_response_status": status,
        "draft_text_preview": draft_text[:1000],
        "ready_for_final_gate_review": bool(response_received and draft_text.strip()),
        "ready_for_final_answer": False,
        "requires_final_gate_after_draft": True,
        "answers_user_question": False,
        "llm_call_allowed": bool(execute),
        "retrieval_execution_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": False,
    }


def build_engineering_gemma_draft_runner(
    *,
    adapter_report_path: Path,
    output_dir: Path,
    execute: bool = False,
    timeout_seconds: int = 180,
    api_key_override: Optional[str] = None,
) -> Dict[str, Any]:
    adapter_payload = _read_json(adapter_report_path)
    adapter_records = adapter_payload.get("records") or []

    records = [
        build_runner_record(
            adapter_record=record,
            index=index,
            output_dir=output_dir,
            execute=execute,
            timeout_seconds=timeout_seconds,
            api_key_override=api_key_override,
        )
        for index, record in enumerate(adapter_records)
        if isinstance(record, dict)
    ]

    status_counts = Counter(record.get("draft_response_status") for record in records)
    provider_counts = Counter(record.get("provider") for record in records)
    intent_counts = Counter(record.get("intent_family") for record in records)

    summary = {
        "source_adapter_quality_status": adapter_payload.get("quality_status"),
        "source_adapter_record_count": len(adapter_records),
        "runner_record_count": len(records),
        "execute_requested": execute,
        "request_sent_count": sum(1 for r in records if r.get("request_sent")),
        "response_received_count": sum(1 for r in records if r.get("response_received")),
        "request_error_count": sum(1 for r in records if r.get("request_error")),
        "ready_for_final_gate_review_count": sum(1 for r in records if r.get("ready_for_final_gate_review")),
        "ready_for_final_answer_count": sum(1 for r in records if r.get("ready_for_final_answer")),
        "requires_final_gate_after_draft_count": sum(1 for r in records if r.get("requires_final_gate_after_draft")),
        "draft_response_status_counts": dict(sorted(status_counts.items())),
        "provider_counts": dict(sorted(provider_counts.items())),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "total_draft_text_char_count": sum(r.get("draft_text_char_count", 0) for r in records),
        "risky_phrase_hit_count": sum((r.get("draft_safety_scan") or {}).get("risky_phrase_hit_count", 0) for r in records),
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "llm_call_allowed_count": sum(1 for r in records if r.get("llm_call_allowed")),
        "retrieval_execution_allowed_count": sum(1 for r in records if r.get("retrieval_execution_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
    }

    quality_status = "PASS"
    if adapter_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_GEMMA_DRAFT_RUNNER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_adapter_report_path": str(adapter_report_path),
        "runner_config": {
            "execute": execute,
            "timeout_seconds": timeout_seconds,
            "api_key_override_used": api_key_override is not None,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "gemma_draft_runner_only",
            "answers_user_question": False,
            "request_sent_only_when_execute_true": True,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "ready_for_final_answer": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_gemma_draft_runner_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_gemma_draft_runner_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_gemma_draft_runner_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_gemma_draft_runner_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    config = payload.get("runner_config") or {}
    lines = [
        "# TRACE-Net Engineering Gemma Draft Runner v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Runner config",
        "",
        f"- Execute: `{config.get('execute')}`",
        f"- Timeout seconds: `{config.get('timeout_seconds')}`",
        "",
        "## Summary",
        "",
        f"- Runner records: {summary.get('runner_record_count')}",
        f"- Request sent: {summary.get('request_sent_count')}",
        f"- Response received: {summary.get('response_received_count')}",
        f"- Request errors: {summary.get('request_error_count')}",
        f"- Ready for final gate review: {summary.get('ready_for_final_gate_review_count')}",
        f"- Ready for final answer: {summary.get('ready_for_final_answer_count')}",
        f"- Draft response status counts: `{summary.get('draft_response_status_counts')}`",
        "",
        "## Records",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('runner_record_id')} — {record.get('draft_response_status')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Provider: `{record.get('provider')}`",
            f"- Endpoint: `{record.get('endpoint')}`",
            f"- Model: `{record.get('model_id')}`",
            f"- Request sent: `{record.get('request_sent')}`",
            f"- Response received: `{record.get('response_received')}`",
            f"- Draft response path: `{record.get('draft_response_path')}`",
            f"- Ready for final gate review: `{record.get('ready_for_final_gate_review')}`",
            f"- Ready for final answer: `{record.get('ready_for_final_answer')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_gemma_draft_runner_quality(
    *,
    report_path: Path,
    require_source_adapter_quality_pass: bool = False,
    min_runner_records: int = 1,
    min_request_sent: int = 0,
    min_response_received: int = 0,
    min_ready_for_final_gate_review: int = 0,
    max_ready_for_final_answer: int = 0,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_retrieval_execution: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_dry_run_no_llm_calls: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_adapter_quality_pass:
        fail_if(summary.get("source_adapter_quality_status") != "PASS", "source adapter quality is not PASS")
    fail_if(summary.get("runner_record_count", 0) < min_runner_records, "not enough runner records")
    fail_if(summary.get("request_sent_count", 0) < min_request_sent, "not enough requests sent")
    fail_if(summary.get("response_received_count", 0) < min_response_received, "not enough responses received")
    fail_if(summary.get("ready_for_final_gate_review_count", 0) < min_ready_for_final_gate_review, "not enough records ready for final gate review")
    fail_if(summary.get("ready_for_final_answer_count", 0) > max_ready_for_final_answer, "too many records ready for final answer")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_retrieval := require_no_retrieval_execution:
        fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
    if require_dry_run_no_llm_calls:
        fail_if(summary.get("request_sent_count", 0) != 0, "dry-run request sent count not zero")
        fail_if(summary.get("response_received_count", 0) != 0, "dry-run response received count not zero")
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "dry-run LLM call allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build/run TRACE-Net engineering Gemma draft runner v1.")
    parser.add_argument("--adapter-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--execute", action="store_true", help="Actually send the request to the configured local model endpoint.")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--api-key-override")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_gemma_draft_runner(
        adapter_report_path=Path(args.adapter_report),
        output_dir=Path(args.output_dir),
        execute=args.execute,
        timeout_seconds=args.timeout_seconds,
        api_key_override=args.api_key_override,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering Gemma draft runner v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-adapter-quality-pass", action="store_true")
    parser.add_argument("--min-runner-records", type=int, default=1)
    parser.add_argument("--min-request-sent", type=int, default=0)
    parser.add_argument("--min-response-received", type=int, default=0)
    parser.add_argument("--min-ready-for-final-gate-review", type=int, default=0)
    parser.add_argument("--max-ready-for-final-answer", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-dry-run-no-llm-calls", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_gemma_draft_runner_quality(
        report_path=Path(args.report_path),
        require_source_adapter_quality_pass=args.require_source_adapter_quality_pass,
        min_runner_records=args.min_runner_records,
        min_request_sent=args.min_request_sent,
        min_response_received=args.min_response_received,
        min_ready_for_final_gate_review=args.min_ready_for_final_gate_review,
        max_ready_for_final_answer=args.max_ready_for_final_answer,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_retrieval_execution=args.require_no_retrieval_execution,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_dry_run_no_llm_calls=args.require_dry_run_no_llm_calls,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_gemma_draft_runner_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
