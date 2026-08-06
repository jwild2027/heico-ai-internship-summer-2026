
"""TRACE-Net Engineering Gemma Draft Retry Prompt v1.

Builds a stricter, shorter Gemma retry request for drafts blocked by the final gate.

v1.1:
- adds micro prompt mode for Gemma4 fragment failures such as "Based" or "###"
- removes JSON blob from the default retry prompt
- avoids Markdown heading symbols
- lowers evidence item defaults to keep the request smaller
- adds target sentence requirements

This module is adapter-compatible with engineering_gemma_draft_runner_v1:
- it writes request payload JSON files
- it emits records with provider/endpoint/model_id/request_payload_path
- the existing runner can execute it using --adapter-report <retry_prompt_report>

Safety:
- no LLM calls
- no network calls
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union


MODULE_VERSION = "trace_net_engineering_gemma_draft_retry_prompt_v1"
REPORT_NAME = "trace_net_engineering_gemma_draft_retry_prompt_v1.json"


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


def _find_by(records: Sequence[Mapping[str, Any]], key: str, value: Any) -> Optional[Mapping[str, Any]]:
    for record in records:
        if record.get(key) == value:
            return record
    return None


def _prompt_contract(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    pc = packet.get("prompt_contract") or {}
    return pc if isinstance(pc, dict) else {}


def _trim_excerpt(text: Any, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    return compact[:limit]


def _condense_evidence(items: Sequence[Mapping[str, Any]], *, max_items: int, max_excerpt_chars: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue
        out.append({
            "route": item.get("route"),
            "trust_tier": item.get("trust_tier"),
            "page_id": item.get("page_id"),
            "source_artifact": item.get("source_artifact"),
            "match_score": item.get("match_score"),
            "source_trace_ready": item.get("source_trace_ready"),
            "excerpt": _trim_excerpt(item.get("excerpt") or item.get("source_text_excerpt"), max_excerpt_chars),
        })
    return out


def _evidence_lines(items: Sequence[Mapping[str, Any]]) -> List[str]:
    lines: List[str] = []
    for idx, item in enumerate(items, start=1):
        page = item.get("page_id") or "unknown_page"
        route = item.get("route") or "unknown_route"
        trust = item.get("trust_tier") or "unknown_trust"
        excerpt = _trim_excerpt(item.get("excerpt"), 220)
        lines.append(f"{idx}. page_id={page}; route={route}; trust={trust}; excerpt={excerpt}")
    return lines


def _retry_system_message() -> str:
    return (
        "You are Gemma4 drafting inside TRACE-Net. "
        "Return normal assistant content only. "
        "Do not return hidden thinking only. "
        "Do not output a fragment. "
        "Do not use Markdown heading symbols like ###. "
        "Use only the provided evidence. "
        "This is draft-only, not a final answer."
    )


def _micro_retry_user_message(
    *,
    packet: Mapping[str, Any],
    final_gate_record: Mapping[str, Any],
    min_draft_chars: int,
    max_source_truth_items: int,
    max_candidate_items: int,
    target_sentences: int,
) -> str:
    pc = _prompt_contract(packet)
    source_truth = _condense_evidence(
        pc.get("source_truth_evidence") or [],
        max_items=max_source_truth_items,
        max_excerpt_chars=220,
    )
    candidate = _condense_evidence(
        pc.get("candidate_evidence") or [],
        max_items=max_candidate_items,
        max_excerpt_chars=180,
    )
    forbidden = pc.get("forbidden_claims") or []
    missing = pc.get("missing_evidence") or []
    source_lines = _evidence_lines(source_truth)
    candidate_lines = _evidence_lines(candidate)
    forbidden_text = "; ".join(str(x) for x in forbidden[:8]) or "approved replacement; guaranteed fit; safe to install; engineering approval; interchangeability"
    missing_text = "; ".join(str(x) for x in missing[:5]) or "No extra missing-evidence note in packet; still avoid approval/interchangeability claims."

    return "\n".join([
        "The previous draft was blocked because it was too short.",
        f"Previous draft preview: {final_gate_record.get('draft_preview')!r}",
        "",
        f"Question: {pc.get('user_question') or packet.get('user_question')}",
        "",
        "Write a complete draft using EXACTLY these five plain-text labels. Do not use ###.",
        "Source-backed facts:",
        "Related candidate context:",
        "Missing evidence and review boundaries:",
        "Source trace notes:",
        "Do-not-claim boundary:",
        "",
        f"Minimum length: {min_draft_chars} characters.",
        f"Minimum sentences: {target_sentences}.",
        "Use complete sentences. Do not stop after one word or one label.",
        "",
        "Source-backed evidence:",
        *source_lines,
        "",
        "Candidate evidence:",
        *candidate_lines,
        "",
        f"Missing evidence notes: {missing_text}",
        f"Forbidden claims: {forbidden_text}",
        "",
        "Important: Write the actual draft now in normal final content. Do not only write 'Based' or '###'.",
    ])


def _compact_retry_user_message(
    *,
    packet: Mapping[str, Any],
    final_gate_record: Mapping[str, Any],
    min_draft_chars: int,
    max_source_truth_items: int,
    max_candidate_items: int,
    target_sentences: int,
) -> str:
    pc = _prompt_contract(packet)
    source_truth = _condense_evidence(
        pc.get("source_truth_evidence") or [],
        max_items=max_source_truth_items,
        max_excerpt_chars=500,
    )
    candidate = _condense_evidence(
        pc.get("candidate_evidence") or [],
        max_items=max_candidate_items,
        max_excerpt_chars=360,
    )
    compact_packet = {
        "user_question": pc.get("user_question") or packet.get("user_question"),
        "intent_family": packet.get("intent_family"),
        "selected_playbook_id": packet.get("selected_playbook_id"),
        "previous_final_gate_blocking_reasons": final_gate_record.get("blocking_reasons") or [],
        "previous_draft_preview": final_gate_record.get("draft_preview"),
        "source_truth_evidence": source_truth,
        "candidate_evidence": candidate,
        "missing_evidence": pc.get("missing_evidence") or [],
        "forbidden_claims": pc.get("forbidden_claims") or [],
        "answer_format_contract": pc.get("answer_format_contract") or {},
    }
    return (
        "The previous Gemma draft was blocked by TRACE-Net final gate. "
        "Regenerate a complete draft using the compact packet below.\n\n"
        f"Minimum draft length: {min_draft_chars} characters.\n"
        f"Minimum sentences: {target_sentences}.\n"
        "Output exactly these sections with plain headings, no ### symbols:\n"
        "Source-backed facts\n"
        "Related candidate context\n"
        "Missing evidence / review boundaries\n"
        "Source trace notes\n"
        "Do-not-claim boundary\n\n"
        "Do not answer with a single word or fragment. Do not begin and then stop after 'Based' or '###'.\n\n"
        "Compact TRACE-Net packet:\n"
        f"{json.dumps(compact_packet, indent=2, sort_keys=True)}\n"
    )


def _messages(
    *,
    packet: Mapping[str, Any],
    final_gate_record: Mapping[str, Any],
    min_draft_chars: int,
    max_source_truth_items: int,
    max_candidate_items: int,
    target_sentences: int,
    prompt_style: str,
) -> List[Dict[str, str]]:
    if prompt_style == "micro":
        user_content = _micro_retry_user_message(
            packet=packet,
            final_gate_record=final_gate_record,
            min_draft_chars=min_draft_chars,
            max_source_truth_items=max_source_truth_items,
            max_candidate_items=max_candidate_items,
            target_sentences=target_sentences,
        )
    elif prompt_style == "compact_json":
        user_content = _compact_retry_user_message(
            packet=packet,
            final_gate_record=final_gate_record,
            min_draft_chars=min_draft_chars,
            max_source_truth_items=max_source_truth_items,
            max_candidate_items=max_candidate_items,
            target_sentences=target_sentences,
        )
    else:
        raise ValueError("--prompt-style must be micro or compact_json")

    return [
        {"role": "system", "content": _retry_system_message()},
        {"role": "user", "content": user_content},
    ]


def _endpoint(base_url: str, provider: str) -> str:
    base = base_url.rstrip("/")
    if provider == "ollama":
        return f"{base}/api/chat"
    if provider == "openai_compatible":
        return f"{base}/v1/chat/completions"
    raise ValueError(f"unsupported provider: {provider}")


def _request_payload(
    *,
    provider: str,
    model_id: str,
    messages: Sequence[Mapping[str, str]],
    temperature: float,
    max_output_tokens: int,
    ollama_think: Union[bool, str],
    repeat_last_n: int,
) -> Dict[str, Any]:
    if provider == "ollama":
        return {
            "model": model_id,
            "messages": list(messages),
            "stream": False,
            "think": ollama_think,
            "options": {
                "temperature": temperature,
                "num_predict": max_output_tokens,
                "repeat_last_n": repeat_last_n,
            },
        }
    if provider == "openai_compatible":
        return {
            "model": model_id,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "stream": False,
        }
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


def build_retry_record(
    *,
    final_gate_record: Mapping[str, Any],
    packet: Mapping[str, Any],
    index: int,
    output_dir: Path,
    provider: str,
    base_url: str,
    model_id: str,
    api_key: str,
    temperature: float,
    max_output_tokens: int,
    ollama_think: Union[bool, str],
    min_draft_chars: int,
    max_source_truth_items: int,
    max_candidate_items: int,
    target_sentences: int,
    prompt_style: str,
    repeat_last_n: int,
) -> Dict[str, Any]:
    messages = _messages(
        packet=packet,
        final_gate_record=final_gate_record,
        min_draft_chars=min_draft_chars,
        max_source_truth_items=max_source_truth_items,
        max_candidate_items=max_candidate_items,
        target_sentences=target_sentences,
        prompt_style=prompt_style,
    )
    payload = _request_payload(
        provider=provider,
        model_id=model_id,
        messages=messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        ollama_think=ollama_think,
        repeat_last_n=repeat_last_n,
    )
    request_dir = output_dir / "request_payloads"
    request_path = request_dir / f"engineering_gemma_draft_retry_{index+1:04d}_{provider}_request.json"
    _write_json(request_path, payload)

    endpoint = _endpoint(base_url, provider)
    message_chars = sum(len(m.get("content", "")) for m in messages)

    return {
        "adapter_record_version": MODULE_VERSION,
        "adapter_record_id": f"engineering_gemma_draft_retry_prompt_{index+1:04d}",
        "retry_prompt_record_id": f"engineering_gemma_draft_retry_prompt_{index+1:04d}",
        "source_final_gate_record_id": final_gate_record.get("final_gate_record_id"),
        "source_draft_packet_id": packet.get("draft_packet_id") or final_gate_record.get("source_draft_packet_id"),
        "source_runner_record_id": final_gate_record.get("source_runner_record_id"),
        "question_id": final_gate_record.get("question_id") or packet.get("question_id"),
        "user_question": final_gate_record.get("user_question") or packet.get("user_question"),
        "intent_family": final_gate_record.get("intent_family") or packet.get("intent_family"),
        "selected_playbook_id": final_gate_record.get("selected_playbook_id") or packet.get("selected_playbook_id"),
        "previous_blocking_reasons": final_gate_record.get("blocking_reasons") or [],
        "previous_draft_text_char_count": final_gate_record.get("draft_text_char_count"),
        "provider": provider,
        "base_url": base_url,
        "endpoint": endpoint,
        "model_id": model_id,
        "api_key_mode": "provided_to_payload_runner_only",
        "api_key_is_blank": api_key == "",
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "ollama_think": ollama_think if provider == "ollama" else None,
        "prompt_style": prompt_style,
        "target_sentences": target_sentences,
        "repeat_last_n": repeat_last_n if provider == "ollama" else None,
        "request_payload_path": str(request_path),
        "request_payload": payload,
        "curl_command": _curl_command(endpoint=endpoint, payload_path=str(request_path), provider=provider, api_key=api_key),
        "message_count": len(messages),
        "message_character_count": message_chars,
        "retry_prompt_strategy": "micro_plain_text_no_markdown_hashes" if prompt_style == "micro" else "shorter_stricter_structured_final_content",
        "min_draft_chars": min_draft_chars,
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


def build_engineering_gemma_draft_retry_prompt(
    *,
    final_gate_report_path: Path,
    draft_packet_path: Path,
    output_dir: Path,
    provider: str = "ollama",
    base_url: str = "http://127.0.0.1:11434",
    model_id: str = "gemma4:26b",
    api_key: str = "ollama",
    temperature: float = 0.0,
    max_output_tokens: int = 1200,
    ollama_think: Union[bool, str] = False,
    min_draft_chars: int = 300,
    max_source_truth_items: int = 3,
    max_candidate_items: int = 2,
    target_sentences: int = 8,
    prompt_style: str = "micro",
    repeat_last_n: int = 64,
) -> Dict[str, Any]:
    final_gate_payload = _read_json(final_gate_report_path)
    draft_packet_payload = _read_json(draft_packet_path)

    final_gate_records = final_gate_payload.get("records") or []
    draft_packets = draft_packet_payload.get("records") or []

    retry_sources = [
        record for record in final_gate_records
        if isinstance(record, dict) and record.get("final_gate_status") == "FINAL_GATE_BLOCKED"
    ]

    records: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for record in retry_sources:
        packet_id = record.get("source_draft_packet_id")
        packet = _find_by(draft_packets, "draft_packet_id", packet_id)
        if packet is None:
            skipped.append({
                "source_final_gate_record_id": record.get("final_gate_record_id"),
                "source_draft_packet_id": packet_id,
                "reason": "missing_source_draft_packet",
            })
            continue
        records.append(build_retry_record(
            final_gate_record=record,
            packet=packet,
            index=len(records),
            output_dir=output_dir,
            provider=provider,
            base_url=base_url,
            model_id=model_id,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            ollama_think=ollama_think,
            min_draft_chars=min_draft_chars,
            max_source_truth_items=max_source_truth_items,
            max_candidate_items=max_candidate_items,
            target_sentences=target_sentences,
            prompt_style=prompt_style,
            repeat_last_n=repeat_last_n,
        ))

    provider_counts = Counter(record.get("provider") for record in records)
    block_counts = Counter(reason for record in records for reason in record.get("previous_blocking_reasons", []))
    intent_counts = Counter(record.get("intent_family") for record in records)
    ollama_think_counts = Counter(str(record.get("ollama_think")) for record in records if record.get("provider") == "ollama")
    prompt_style_counts = Counter(record.get("prompt_style") for record in records)

    summary = {
        "source_final_gate_quality_status": final_gate_payload.get("quality_status"),
        "source_draft_packet_quality_status": draft_packet_payload.get("quality_status"),
        "source_final_gate_record_count": len(final_gate_records),
        "source_blocked_final_gate_record_count": len(retry_sources),
        "retry_prompt_record_count": len(records),
        "skipped_retry_source_count": len(skipped),
        "ready_for_gemma_request_payload_count": sum(1 for r in records if r.get("ready_for_gemma_request_payload")),
        "request_payload_written_count": sum(1 for r in records if r.get("request_payload_written")),
        "request_sent_count": sum(1 for r in records if r.get("request_sent")),
        "response_received_count": sum(1 for r in records if r.get("response_received")),
        "ready_for_final_answer_count": sum(1 for r in records if r.get("ready_for_final_answer")),
        "requires_final_gate_after_draft_count": sum(1 for r in records if r.get("requires_final_gate_after_draft")),
        "provider_counts": dict(sorted(provider_counts.items())),
        "ollama_think_counts": dict(sorted(ollama_think_counts.items())),
        "prompt_style_counts": dict(sorted(prompt_style_counts.items())),
        "previous_blocking_reason_counts": dict(sorted(block_counts.items())),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "skipped_retry_sources": skipped,
        "total_message_character_count": sum(r.get("message_character_count", 0) for r in records),
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
    if final_gate_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if draft_packet_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_GEMMA_DRAFT_RETRY_PROMPT_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_final_gate_report_path": str(final_gate_report_path),
        "source_draft_packet_path": str(draft_packet_path),
        "retry_prompt_config": {
            "provider": provider,
            "base_url": base_url,
            "model_id": model_id,
            "api_key_mode": "provided_to_payload_runner_only",
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "ollama_think": ollama_think if provider == "ollama" else None,
            "min_draft_chars": min_draft_chars,
            "max_source_truth_items": max_source_truth_items,
            "max_candidate_items": max_candidate_items,
            "target_sentences": target_sentences,
            "prompt_style": prompt_style,
            "repeat_last_n": repeat_last_n if provider == "ollama" else None,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "gemma_retry_request_payload_builder_only",
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
    _write_jsonl(output_dir / "trace_net_engineering_gemma_draft_retry_prompt_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_gemma_draft_retry_prompt_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_gemma_draft_retry_prompt_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_curl_examples(output_dir / "trace_net_engineering_gemma_draft_retry_prompt_v1_curl_examples.sh", records)
    _write_markdown(output_dir / "trace_net_engineering_gemma_draft_retry_prompt_v1.md", payload)
    return payload


def _write_curl_examples(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# TRACE-Net Engineering Gemma Draft Retry Prompt v1.1 curl examples",
        "# These commands are NOT run by the retry prompt builder.",
        "",
    ]
    for record in records:
        lines.append(f"# {record.get('retry_prompt_record_id')} / {record.get('source_draft_packet_id')}")
        lines.append(str(record.get("curl_command") or ""))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    config = payload.get("retry_prompt_config") or {}
    lines = [
        "# TRACE-Net Engineering Gemma Draft Retry Prompt v1.1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Config",
        "",
        f"- Provider: `{config.get('provider')}`",
        f"- Model ID: `{config.get('model_id')}`",
        f"- Prompt style: `{config.get('prompt_style')}`",
        f"- Ollama think: `{config.get('ollama_think')}`",
        f"- Min draft chars: `{config.get('min_draft_chars')}`",
        f"- Target sentences: `{config.get('target_sentences')}`",
        f"- Max output tokens: `{config.get('max_output_tokens')}`",
        "",
        "## Summary",
        "",
        f"- Retry prompt records: {summary.get('retry_prompt_record_count')}",
        f"- Request payloads written: {summary.get('request_payload_written_count')}",
        f"- Prompt style counts: `{summary.get('prompt_style_counts')}`",
        f"- Previous blocking reasons: `{summary.get('previous_blocking_reason_counts')}`",
        f"- Total message chars: {summary.get('total_message_character_count')}",
        f"- Ready for final answer: {summary.get('ready_for_final_answer_count')}",
        "",
        "## Records",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('retry_prompt_record_id')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Prompt style: `{record.get('prompt_style')}`",
            f"- Previous blocking reasons: `{record.get('previous_blocking_reasons')}`",
            f"- Request payload: `{record.get('request_payload_path')}`",
            f"- Message chars: `{record.get('message_character_count')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_gemma_draft_retry_prompt_quality(
    *,
    report_path: Path,
    require_source_final_gate_quality_pass: bool = False,
    require_source_draft_packet_quality_pass: bool = False,
    min_retry_prompt_records: int = 1,
    min_request_payloads_written: int = 1,
    max_request_sent: int = 0,
    max_ready_for_final_answer: int = 0,
    max_unsafe: int = 0,
    require_ollama_think_false: bool = False,
    require_prompt_style: Optional[str] = None,
    max_total_message_chars: Optional[int] = None,
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

    if require_source_final_gate_quality_pass:
        fail_if(summary.get("source_final_gate_quality_status") != "PASS", "source final gate quality is not PASS")
    if require_source_draft_packet_quality_pass:
        fail_if(summary.get("source_draft_packet_quality_status") != "PASS", "source draft packet quality is not PASS")
    fail_if(summary.get("retry_prompt_record_count", 0) < min_retry_prompt_records, "not enough retry prompt records")
    fail_if(summary.get("request_payload_written_count", 0) < min_request_payloads_written, "not enough request payloads written")
    fail_if(summary.get("request_sent_count", 0) > max_request_sent, "too many requests sent")
    fail_if(summary.get("ready_for_final_answer_count", 0) > max_ready_for_final_answer, "too many final-answer-ready records")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if max_total_message_chars is not None:
        fail_if(summary.get("total_message_character_count", 0) > max_total_message_chars, "retry prompt too large")
    if require_prompt_style:
        for record in payload.get("records") or []:
            fail_if(record.get("prompt_style") != require_prompt_style, f"record prompt_style is not {require_prompt_style}")
    if require_ollama_think_false:
        for record in payload.get("records") or []:
            if record.get("provider") == "ollama":
                fail_if(record.get("ollama_think") is not False, "Ollama retry prompt does not have think=false")
                request_payload = record.get("request_payload") or {}
                fail_if(request_payload.get("think") is not False, "Ollama retry request payload does not have think=false")
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering Gemma draft retry prompt v1.")
    parser.add_argument("--final-gate", required=True)
    parser.add_argument("--draft-packet", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--provider", choices=["ollama", "openai_compatible"], default="ollama")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model-id", default="gemma4:26b")
    parser.add_argument("--api-key", default="ollama")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=1200)
    parser.add_argument("--ollama-think", default="false")
    parser.add_argument("--min-draft-chars", type=int, default=300)
    parser.add_argument("--max-source-truth-items", type=int, default=3)
    parser.add_argument("--max-candidate-items", type=int, default=2)
    parser.add_argument("--target-sentences", type=int, default=8)
    parser.add_argument("--prompt-style", choices=["micro", "compact_json"], default="micro")
    parser.add_argument("--repeat-last-n", type=int, default=64)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_gemma_draft_retry_prompt(
        final_gate_report_path=Path(args.final_gate),
        draft_packet_path=Path(args.draft_packet),
        output_dir=Path(args.output_dir),
        provider=args.provider,
        base_url=args.base_url,
        model_id=args.model_id,
        api_key=args.api_key,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        ollama_think=_parse_ollama_think(args.ollama_think),
        min_draft_chars=args.min_draft_chars,
        max_source_truth_items=args.max_source_truth_items,
        max_candidate_items=args.max_candidate_items,
        target_sentences=args.target_sentences,
        prompt_style=args.prompt_style,
        repeat_last_n=args.repeat_last_n,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering Gemma draft retry prompt v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-source-draft-packet-quality-pass", action="store_true")
    parser.add_argument("--min-retry-prompt-records", type=int, default=1)
    parser.add_argument("--min-request-payloads-written", type=int, default=1)
    parser.add_argument("--max-request-sent", type=int, default=0)
    parser.add_argument("--max-ready-for-final-answer", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-ollama-think-false", action="store_true")
    parser.add_argument("--require-prompt-style")
    parser.add_argument("--max-total-message-chars", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_gemma_draft_retry_prompt_quality(
        report_path=Path(args.report_path),
        require_source_final_gate_quality_pass=args.require_source_final_gate_quality_pass,
        require_source_draft_packet_quality_pass=args.require_source_draft_packet_quality_pass,
        min_retry_prompt_records=args.min_retry_prompt_records,
        min_request_payloads_written=args.min_request_payloads_written,
        max_request_sent=args.max_request_sent,
        max_ready_for_final_answer=args.max_ready_for_final_answer,
        max_unsafe=args.max_unsafe,
        require_ollama_think_false=args.require_ollama_think_false,
        require_prompt_style=args.require_prompt_style,
        max_total_message_chars=args.max_total_message_chars,
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
        out = Path(args.report_path).with_name("trace_net_engineering_gemma_draft_retry_prompt_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
