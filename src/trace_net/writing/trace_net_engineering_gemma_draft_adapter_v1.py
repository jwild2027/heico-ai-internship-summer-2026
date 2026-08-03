
"""TRACE-Net Engineering Gemma Draft Adapter v1.

Converts Self-RAG-approved draft packets into local Gemma/Ollama or
OpenAI-compatible request payloads.

v1.1:
- adds Ollama top-level `think` control
- defaults Ollama thinking to false so thinking-capable models like gemma4:26b
  produce final `message.content` instead of a thinking-only response
- records ollama_think in adapter config and records

This module DOES NOT send requests.
It only writes request payload artifacts that a later runner/API can use.

Safety:
- no LLM calls
- no network calls
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
- no direct answer permission
"""

from __future__ import annotations

import argparse
import json
import shlex
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union


MODULE_VERSION = "trace_net_engineering_gemma_draft_adapter_v1"
REPORT_NAME = "trace_net_engineering_gemma_draft_adapter_v1.json"


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


def _parse_ollama_think(value: str) -> Union[bool, str]:
    text = str(value).strip().lower()
    if text in {"false", "0", "no", "off", "none", ""}:
        return False
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"low", "medium", "high"}:
        return text
    raise ValueError("--ollama-think must be one of false,true,low,medium,high")


def _compact_json(value: Any, *, limit: int = 6000) -> str:
    text = json.dumps(value, indent=2, sort_keys=True)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...TRUNCATED_FOR_DRAFT_PACKET_ADAPTER..."


def _packet_prompt_contract(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = packet.get("prompt_contract") or {}
    return contract if isinstance(contract, dict) else {}


def _system_message(packet: Mapping[str, Any]) -> str:
    pc = _packet_prompt_contract(packet)
    rules = pc.get("non_negotiable_rules") or []
    rules_text = "\n".join(f"- {rule}" for rule in rules)
    return (
        f"{pc.get('system_role') or 'You are an engineering evidence drafting assistant for TRACE-Net.'}\n\n"
        "Non-negotiable TRACE-Net rules:\n"
        f"{rules_text}\n\n"
        "Draft-only boundary:\n"
        "- You are preparing a draft from a context packet only.\n"
        "- Final answer permission is NOT granted.\n"
        "- Do not claim that TRACE-Net can prove anything unless the final gate later grants that permission.\n"
        "- Keep exact source-backed facts, candidate/related evidence, and missing evidence separate.\n"
        "- Put the actual draft in the final answer content, not in hidden thinking.\n"
    )


def _user_message(packet: Mapping[str, Any]) -> str:
    pc = _packet_prompt_contract(packet)
    sections = {
        "user_question": pc.get("user_question") or packet.get("user_question"),
        "selected_playbook": pc.get("selected_playbook"),
        "structured_user_intent": pc.get("structured_user_intent"),
        "draft_instruction_block": pc.get("draft_instruction_block"),
        "source_truth_evidence": pc.get("source_truth_evidence"),
        "candidate_evidence": pc.get("candidate_evidence"),
        "missing_evidence": pc.get("missing_evidence"),
        "forbidden_claims": pc.get("forbidden_claims"),
        "answer_format_contract": pc.get("answer_format_contract"),
        "self_rag_summary": pc.get("self_rag_summary"),
    }
    return (
        "TRACE-Net Gemma draft packet follows.\n"
        "Use only this packet. Produce a draft, not a final answer.\n"
        "Important: output the draft in normal assistant content. Do not output only thinking.\n\n"
        f"{_compact_json(sections, limit=14000)}\n\n"
        "Required draft shape:\n"
        "1. Source-backed facts\n"
        "2. Related/candidate context, clearly labeled\n"
        "3. Missing evidence / review boundaries\n"
        "4. Source trace/citation notes from the packet\n"
        "5. Do-not-claim boundary\n"
    )


def _messages(packet: Mapping[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": _system_message(packet)},
        {"role": "user", "content": _user_message(packet)},
    ]


def _ollama_payload(
    packet: Mapping[str, Any],
    *,
    model_id: str,
    temperature: float,
    max_output_tokens: int,
    ollama_think: Union[bool, str],
) -> Dict[str, Any]:
    return {
        "model": model_id,
        "messages": _messages(packet),
        "stream": False,
        "think": ollama_think,
        "options": {
            "temperature": temperature,
            "num_predict": max_output_tokens,
        },
    }


def _openai_compatible_payload(packet: Mapping[str, Any], *, model_id: str, temperature: float, max_output_tokens: int) -> Dict[str, Any]:
    return {
        "model": model_id,
        "messages": _messages(packet),
        "temperature": temperature,
        "max_tokens": max_output_tokens,
        "stream": False,
    }


def _endpoint(base_url: str, provider: str) -> str:
    base = base_url.rstrip("/")
    if provider == "ollama":
        return f"{base}/api/chat"
    if provider == "openai_compatible":
        return f"{base}/v1/chat/completions"
    raise ValueError(f"unsupported provider: {provider}")


def _curl_command(*, endpoint: str, payload_path: str, provider: str, api_key: str) -> str:
    quoted_endpoint = shlex.quote(endpoint)
    quoted_payload = shlex.quote("@" + payload_path)
    if provider == "ollama":
        return f"curl -s {quoted_endpoint} -H 'Content-Type: application/json' -d {quoted_payload} | python -m json.tool"
    return (
        f"curl -s {quoted_endpoint} "
        f"-H 'Content-Type: application/json' "
        f"-H 'Authorization: Bearer {shlex.quote(api_key)}' "
        f"-d {quoted_payload} | python -m json.tool"
    )


def build_adapter_record(
    *,
    packet: Mapping[str, Any],
    index: int,
    provider: str,
    base_url: str,
    model_id: str,
    api_key: str,
    temperature: float,
    max_output_tokens: int,
    request_output_dir: Path,
    ollama_think: Union[bool, str],
) -> Dict[str, Any]:
    if provider == "ollama":
        request_payload = _ollama_payload(
            packet,
            model_id=model_id,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            ollama_think=ollama_think,
        )
    elif provider == "openai_compatible":
        request_payload = _openai_compatible_payload(
            packet,
            model_id=model_id,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    else:
        raise ValueError(f"unsupported provider: {provider}")

    draft_packet_id = str(packet.get("draft_packet_id") or f"draft_packet_{index+1:04d}")
    request_path = request_output_dir / f"{draft_packet_id}_{provider}_request.json"
    _write_json(request_path, request_payload)

    endpoint = _endpoint(base_url, provider)
    curl = _curl_command(endpoint=endpoint, payload_path=str(request_path), provider=provider, api_key=api_key)

    message_chars = sum(len(m.get("content", "")) for m in request_payload.get("messages", []))
    prompt_contract = _packet_prompt_contract(packet)

    return {
        "adapter_record_version": MODULE_VERSION,
        "adapter_record_id": f"engineering_gemma_draft_adapter_{index+1:04d}",
        "source_draft_packet_id": packet.get("draft_packet_id"),
        "question_id": packet.get("question_id"),
        "user_question": packet.get("user_question"),
        "intent_family": packet.get("intent_family"),
        "selected_playbook_id": packet.get("selected_playbook_id"),
        "provider": provider,
        "base_url": base_url,
        "endpoint": endpoint,
        "model_id": model_id,
        "api_key_mode": "provided_to_payload_runner_only",
        "api_key_is_blank": api_key == "",
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "ollama_think": ollama_think if provider == "ollama" else None,
        "request_payload_path": str(request_path),
        "request_payload": request_payload,
        "curl_command": curl,
        "message_count": len(request_payload.get("messages", [])),
        "message_character_count": message_chars,
        "source_truth_evidence_count": len(prompt_contract.get("source_truth_evidence") or []),
        "candidate_evidence_count": len(prompt_contract.get("candidate_evidence") or []),
        "forbidden_claim_count": len(prompt_contract.get("forbidden_claims") or []),
        "missing_evidence_count": len(prompt_contract.get("missing_evidence") or []),
        "ready_for_gemma_request_payload": True,
        "request_payload_written": True,
        "request_sent": False,
        "response_received": False,
        "ready_for_final_answer": False,
        "requires_final_gate_after_draft": True,
        "answers_user_question": False,
        "llm_call_allowed": False,
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


def build_engineering_gemma_draft_adapter(
    *,
    draft_packet_path: Path,
    output_dir: Path,
    provider: str = "ollama",
    base_url: str = "http://127.0.0.1:11434",
    model_id: str = "gemma4:26b",
    api_key: str = "ollama",
    temperature: float = 0.0,
    max_output_tokens: int = 700,
    ollama_think: Union[bool, str] = False,
) -> Dict[str, Any]:
    draft_payload = _read_json(draft_packet_path)
    packets = draft_payload.get("records") or []

    request_output_dir = output_dir / "request_payloads"
    records = [
        build_adapter_record(
            packet=packet,
            index=index,
            provider=provider,
            base_url=base_url,
            model_id=model_id,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            request_output_dir=request_output_dir,
            ollama_think=ollama_think,
        )
        for index, packet in enumerate(packets)
        if isinstance(packet, dict)
    ]

    provider_counts = Counter(record.get("provider") for record in records)
    intent_counts = Counter(record.get("intent_family") for record in records)
    ollama_think_counts = Counter(str(record.get("ollama_think")) for record in records if record.get("provider") == "ollama")

    summary = {
        "source_draft_packet_quality_status": draft_payload.get("quality_status"),
        "source_draft_packet_count": len(packets),
        "adapter_record_count": len(records),
        "ready_for_gemma_request_payload_count": sum(1 for r in records if r.get("ready_for_gemma_request_payload")),
        "request_payload_written_count": sum(1 for r in records if r.get("request_payload_written")),
        "request_sent_count": sum(1 for r in records if r.get("request_sent")),
        "response_received_count": sum(1 for r in records if r.get("response_received")),
        "ready_for_final_answer_count": sum(1 for r in records if r.get("ready_for_final_answer")),
        "requires_final_gate_after_draft_count": sum(1 for r in records if r.get("requires_final_gate_after_draft")),
        "provider_counts": dict(sorted(provider_counts.items())),
        "ollama_think_counts": dict(sorted(ollama_think_counts.items())),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "total_message_character_count": sum(r.get("message_character_count", 0) for r in records),
        "total_source_truth_evidence_count": sum(r.get("source_truth_evidence_count", 0) for r in records),
        "total_candidate_evidence_count": sum(r.get("candidate_evidence_count", 0) for r in records),
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
    if draft_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["request_sent_count"] != 0:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_GEMMA_DRAFT_ADAPTER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_draft_packet_path": str(draft_packet_path),
        "adapter_config": {
            "provider": provider,
            "base_url": base_url,
            "model_id": model_id,
            "api_key_mode": "provided_to_payload_runner_only",
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "ollama_think": ollama_think if provider == "ollama" else None,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "gemma_request_payload_builder_only",
            "answers_user_question": False,
            "llm_call_allowed": False,
            "request_sent": False,
            "response_received": False,
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
    _write_jsonl(output_dir / "trace_net_engineering_gemma_draft_adapter_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_gemma_draft_adapter_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_gemma_draft_adapter_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_curl_examples(output_dir / "trace_net_engineering_gemma_draft_adapter_v1_curl_examples.sh", records)
    _write_markdown(output_dir / "trace_net_engineering_gemma_draft_adapter_v1.md", payload)
    return payload


def _write_curl_examples(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# TRACE-Net Engineering Gemma Draft Adapter v1 curl examples",
        "# These commands are NOT run by the adapter.",
        "# Running them manually will call the configured local model endpoint.",
        "",
    ]
    for record in records:
        lines.append(f"# {record.get('adapter_record_id')} / {record.get('source_draft_packet_id')}")
        lines.append(str(record.get("curl_command") or ""))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    config = payload.get("adapter_config") or {}
    lines = [
        "# TRACE-Net Engineering Gemma Draft Adapter v1.1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Adapter config",
        "",
        f"- Provider: `{config.get('provider')}`",
        f"- Base URL: `{config.get('base_url')}`",
        f"- Model ID: `{config.get('model_id')}`",
        f"- Ollama think: `{config.get('ollama_think')}`",
        f"- Temperature: `{config.get('temperature')}`",
        f"- Max output tokens: `{config.get('max_output_tokens')}`",
        "",
        "## Summary",
        "",
        f"- Adapter records: {summary.get('adapter_record_count')}",
        f"- Request payloads written: {summary.get('request_payload_written_count')}",
        f"- Request payloads sent: {summary.get('request_sent_count')}",
        f"- Ready for final answer: {summary.get('ready_for_final_answer_count')}",
        f"- Requires final gate after draft: {summary.get('requires_final_gate_after_draft_count')}",
        f"- Ollama think counts: `{summary.get('ollama_think_counts')}`",
        f"- Source-truth evidence total: {summary.get('total_source_truth_evidence_count')}",
        f"- Candidate evidence total: {summary.get('total_candidate_evidence_count')}",
        "",
        "## Records",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('adapter_record_id')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Provider: `{record.get('provider')}`",
            f"- Endpoint: `{record.get('endpoint')}`",
            f"- Model: `{record.get('model_id')}`",
            f"- Ollama think: `{record.get('ollama_think')}`",
            f"- Request payload: `{record.get('request_payload_path')}`",
            f"- Request sent: `{record.get('request_sent')}`",
            f"- Ready for final answer: `{record.get('ready_for_final_answer')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_gemma_draft_adapter_quality(
    *,
    report_path: Path,
    require_source_draft_packet_quality_pass: bool = False,
    min_adapter_records: int = 1,
    min_request_payloads_written: int = 1,
    max_request_sent: int = 0,
    max_ready_for_final_answer: int = 0,
    max_unsafe: int = 0,
    require_ollama_think_false: bool = False,
    require_no_answer_permission: bool = False,
    require_no_llm_calls: bool = False,
    require_no_retrieval_execution: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_draft_packet_quality_pass:
        fail_if(summary.get("source_draft_packet_quality_status") != "PASS", "source draft packet quality is not PASS")
    fail_if(summary.get("adapter_record_count", 0) < min_adapter_records, "not enough adapter records")
    fail_if(summary.get("request_payload_written_count", 0) < min_request_payloads_written, "not enough request payloads written")
    fail_if(summary.get("request_sent_count", 0) > max_request_sent, "too many requests sent")
    fail_if(summary.get("ready_for_final_answer_count", 0) > max_ready_for_final_answer, "too many records ready for final answer")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_ollama_think_false:
        records = payload.get("records") or []
        for record in records:
            if record.get("provider") == "ollama":
                fail_if(record.get("ollama_think") is not False, "Ollama adapter record does not have think=false")
                request_payload = record.get("request_payload") or {}
                fail_if(request_payload.get("think") is not False, "Ollama request payload does not have think=false")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "LLM call allowed count not zero")
        fail_if(summary.get("request_sent_count", 0) != 0, "request sent count not zero")
        fail_if(summary.get("response_received_count", 0) != 0, "response received count not zero")
    if require_no_retrieval_execution:
        fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering Gemma draft adapter v1.")
    parser.add_argument("--draft-packet", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--provider", choices=["ollama", "openai_compatible"], default="ollama")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model-id", default="gemma4:26b")
    parser.add_argument("--api-key", default="ollama")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=700)
    parser.add_argument("--ollama-think", default="false", help="Ollama /api/chat think value: false,true,low,medium,high. Defaults to false.")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_gemma_draft_adapter(
        draft_packet_path=Path(args.draft_packet),
        output_dir=Path(args.output_dir),
        provider=args.provider,
        base_url=args.base_url,
        model_id=args.model_id,
        api_key=args.api_key,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        ollama_think=_parse_ollama_think(args.ollama_think),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering Gemma draft adapter v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-draft-packet-quality-pass", action="store_true")
    parser.add_argument("--min-adapter-records", type=int, default=1)
    parser.add_argument("--min-request-payloads-written", type=int, default=1)
    parser.add_argument("--max-request-sent", type=int, default=0)
    parser.add_argument("--max-ready-for-final-answer", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-ollama-think-false", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_gemma_draft_adapter_quality(
        report_path=Path(args.report_path),
        require_source_draft_packet_quality_pass=args.require_source_draft_packet_quality_pass,
        min_adapter_records=args.min_adapter_records,
        min_request_payloads_written=args.min_request_payloads_written,
        max_request_sent=args.max_request_sent,
        max_ready_for_final_answer=args.max_ready_for_final_answer,
        max_unsafe=args.max_unsafe,
        require_ollama_think_false=args.require_ollama_think_false,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_llm_calls=args.require_no_llm_calls,
        require_no_retrieval_execution=args.require_no_retrieval_execution,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_gemma_draft_adapter_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
