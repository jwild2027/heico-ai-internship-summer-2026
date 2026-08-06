from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v22"
MODULE = "trace_net_e2e_live_llm_draft_adapter_v22"
STATUS_READY = "E2E_LIVE_LLM_DRAFT_ADAPTER_READY_FOR_FINAL_GATE"
STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_DRAFT_ADAPTER_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

DEFAULT_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_LLM_MODEL = "gemma4:26b"
DEFAULT_LLM_API_KEY = "ollama"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}
    return bool(value)


def _first_list(obj: Any, candidate_keys: Sequence[str]) -> List[Any]:
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, Mapping):
        return []
    for key in candidate_keys:
        value = obj.get(key)
        if isinstance(value, list):
            return value
    for wrapper in ("report", "payload", "data"):
        nested = obj.get(wrapper)
        if isinstance(nested, Mapping):
            found = _first_list(nested, candidate_keys)
            if found:
                return found
    return []


def prompt_contracts(data: Any) -> List[Mapping[str, Any]]:
    rows = _first_list(data, ["prompt_contracts", "llm_prompt_contracts", "records", "prompts"])
    return [r for r in rows if isinstance(r, Mapping)]


def _contract_id(row: Mapping[str, Any], index: int) -> str:
    return str(row.get("prompt_contract_id") or row.get("contract_id") or row.get("record_id") or f"llm_prompt_contract_v21_{index:04d}")


def _contract_ready(row: Mapping[str, Any]) -> bool:
    if "ready_for_llm_draft" in row:
        return _as_bool(row.get("ready_for_llm_draft"))
    status = str(row.get("prompt_contract_status") or row.get("status") or "").upper()
    if status:
        return "READY" in status and "REPAIR" not in status and "BLOCK" not in status
    return bool(row.get("messages"))


def _messages(row: Mapping[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for msg in row.get("messages") or []:
        if not isinstance(msg, Mapping):
            continue
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        if role not in {"system", "user", "assistant"}:
            role = "user"
        out.append({"role": role, "content": content})
    return out


def _context_message(row: Mapping[str, Any]) -> str:
    for msg in reversed(_messages(row)):
        if "TRACE-NET CONTEXT PACK" in msg.get("content", ""):
            return msg["content"]
    return _messages(row)[-1]["content"] if _messages(row) else ""


def _extract_direct_evidence_lines(context: str) -> List[str]:
    lines = context.splitlines()
    in_direct = False
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SOURCE-TRUTH EVIDENCE"):
            in_direct = True
            continue
        if in_direct and stripped.startswith("NEARBY SOURCE-TRUTH CONTEXT"):
            break
        if in_direct and stripped.startswith("- ["):
            out.append(stripped)
    return out


def _extract_aggregation(context: str) -> Dict[str, Any]:
    marker = "AGGREGATION / CAPPING METADATA:"
    start = context.find(marker)
    if start < 0:
        return {}
    rest = context[start + len(marker):]
    end_markers = ["SELF-RAG / CRAG STATUS:", "ANSWER RULES:"]
    end = len(rest)
    for m in end_markers:
        idx = rest.find(m)
        if idx >= 0:
            end = min(end, idx)
    block = rest[:end].strip()
    if not block.startswith("{"):
        return {}
    try:
        return json.loads(block)
    except Exception:
        return {}


def _citation_like_count(text: str) -> int:
    return len(re.findall(r"\[\d+\]", text or ""))


def _has_cap_disclosure(text: str) -> bool:
    nt = (text or "").lower()
    return any(term in nt for term in ("capped", "more results", "showing", "returned", "total match", "high-degree", "high degree", "drilldown"))


def _simulate_draft(row: Mapping[str, Any]) -> str:
    query = str(row.get("user_query") or "")
    context = _context_message(row)
    evidence_lines = _extract_direct_evidence_lines(context)
    aggregation = _extract_aggregation(context)
    if not evidence_lines:
        return (
            f"TRACE-Net could not find direct source-truth evidence for: {query}. "
            "The graph, Leiden communities, v2 summaries, and aggregation metadata are guidance only, so they are not enough to support a factual answer."
        )
    first = evidence_lines[0].lstrip("- ")
    evidence_preview = "; ".join(line.lstrip("- ") for line in evidence_lines[:3])
    if len(evidence_lines) > 3:
        evidence_preview += f"; plus {len(evidence_lines) - 3} additional direct evidence item(s)."
    else:
        evidence_preview += "."
    cap_sentence = ""
    if aggregation.get("result_was_capped") or aggregation.get("more_results_available") or aggregation.get("high_degree_node_detected"):
        cap_sentence = (
            f" Results were capped: TRACE-Net returned {aggregation.get('returned_match_count')} "
            f"of {aggregation.get('total_match_count')} matches; more results may be available through drill-down filters."
        )
    return (
        f"TRACE-Net found citation-backed source-truth evidence for the query '{query}'. "
        f"Primary evidence: {first}. Related direct evidence includes {evidence_preview}"
        f"{cap_sentence} Graph/Leiden and v2 summary information were used only as guidance, not proof."
    )


def _call_openai_compatible_llm(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: Sequence[Mapping[str, str]],
    temperature: float,
    timeout: float,
) -> Tuple[str, Dict[str, Any]]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response did not include choices")
    msg = choices[0].get("message") or {}
    content = str(msg.get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM response message content was empty")
    metadata = {
        "raw_response_id": data.get("id"),
        "finish_reason": choices[0].get("finish_reason"),
        "usage": data.get("usage") or {},
        "reasoning_present": bool(msg.get("reasoning")),
        "reasoning_omitted_from_draft": bool(msg.get("reasoning")),
        "model_returned": data.get("model"),
    }
    return content, metadata


@dataclass(frozen=True)
class LlmConfig:
    mode: str = "simulate"
    base_url: str = DEFAULT_LLM_BASE_URL
    model: str = DEFAULT_LLM_MODEL
    api_key: str = DEFAULT_LLM_API_KEY
    temperature: float = 0.0
    timeout: float = 120.0
    max_contracts: int = 0


def build_drafts(
    contracts: Sequence[Mapping[str, Any]],
    *,
    config: LlmConfig,
) -> List[Dict[str, Any]]:
    drafts: List[Dict[str, Any]] = []
    selected = list(contracts)
    if config.max_contracts and config.max_contracts > 0:
        selected = selected[: config.max_contracts]
    for idx, contract in enumerate(selected, start=1):
        contract_id = _contract_id(contract, idx)
        ready_contract = _contract_ready(contract)
        context = _context_message(contract)
        direct_evidence_count = len(_extract_direct_evidence_lines(context))
        aggregation = _extract_aggregation(context)
        messages = _messages(contract)
        draft_id = f"llm_draft_v22_{idx:04d}"
        base_record: Dict[str, Any] = {
            "llm_draft_id": draft_id,
            "prompt_contract_id": contract_id,
            "context_pack_id": contract.get("context_pack_id"),
            "user_query": contract.get("user_query"),
            "draft_adapter_status": "LLM_DRAFT_PENDING",
            "prompt_contract_ready": ready_contract,
            "llm_mode": config.mode,
            "llm_provider": "ollama_openai_compatible" if config.mode == "ollama" else "simulated_deterministic_adapter",
            "llm_base_url": config.base_url,
            "llm_model": config.model,
            "llm_called": config.mode == "ollama",
            "source_truth_evidence_count": direct_evidence_count,
            "requires_final_gate": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "llm_reads_context_pack_only": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "aggregation_cap_disclosure": {
                "result_was_capped": bool(aggregation.get("result_was_capped")),
                "more_results_available": bool(aggregation.get("more_results_available")),
                "high_degree_node_detected": bool(aggregation.get("high_degree_node_detected")),
                "total_match_count": aggregation.get("total_match_count"),
                "returned_match_count": aggregation.get("returned_match_count"),
            },
        }
        if not ready_contract or not messages:
            record = dict(base_record)
            record.update({
                "draft_adapter_status": "LLM_DRAFT_SKIPPED_PROMPT_CONTRACT_NOT_READY",
                "ready_for_final_gate": False,
                "draft_text": "",
                "llm_call_status": "SKIPPED",
            })
            drafts.append(record)
            continue
        started = time.time()
        try:
            if config.mode == "simulate":
                content = _simulate_draft(contract)
                meta: Dict[str, Any] = {
                    "finish_reason": "simulated",
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "reasoning_present": False,
                    "reasoning_omitted_from_draft": False,
                    "model_returned": config.model,
                }
                call_status = "SIMULATED_DRAFT_BUILT"
            elif config.mode == "ollama":
                content, meta = _call_openai_compatible_llm(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    model=config.model,
                    messages=messages,
                    temperature=config.temperature,
                    timeout=config.timeout,
                )
                call_status = "LLM_CALL_SUCCEEDED"
            else:
                raise ValueError(f"Unsupported llm mode: {config.mode}")
            elapsed = round(time.time() - started, 3)
            record = dict(base_record)
            record.update({
                "draft_adapter_status": "LLM_DRAFT_READY_FOR_FINAL_GATE",
                "llm_call_status": call_status,
                "ready_for_final_gate": bool(content.strip()),
                "draft_text": content,
                "draft_character_count": len(content),
                "citation_like_count": _citation_like_count(content),
                "cap_disclosure_detected_in_draft": _has_cap_disclosure(content),
                "llm_elapsed_seconds": elapsed,
                "llm_response_metadata": meta,
            })
        except Exception as exc:
            elapsed = round(time.time() - started, 3)
            record = dict(base_record)
            record.update({
                "draft_adapter_status": "LLM_DRAFT_ADAPTER_ERROR",
                "llm_call_status": "LLM_CALL_FAILED" if config.mode == "ollama" else "SIMULATED_DRAFT_FAILED",
                "ready_for_final_gate": False,
                "draft_text": "",
                "draft_character_count": 0,
                "citation_like_count": 0,
                "cap_disclosure_detected_in_draft": False,
                "llm_elapsed_seconds": elapsed,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
        drafts.append(record)
    return drafts


def evaluate_quality(report: Dict[str, Any], thresholds: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)})

    def min_check(name: str, key: str) -> None:
        expected = int(thresholds.get(key, 0) or 0)
        observed = int(report.get(name, 0) or 0)
        add(name, observed, ">=", expected, observed >= expected)

    def max_check(name: str, key: str) -> None:
        expected = int(thresholds.get(key, 10**9) if thresholds.get(key, None) is not None else 10**9)
        observed = int(report.get(name, 0) or 0)
        add(name, observed, "<=", expected, observed <= expected)

    min_check("prompt_contract_count", "min_prompt_contracts")
    min_check("llm_draft_count", "min_llm_drafts")
    min_check("drafts_ready_for_final_gate_count", "min_drafts_ready_for_final_gate")
    min_check("drafts_with_nonempty_content_count", "min_drafts_with_nonempty_content")
    min_check("source_truth_supported_prompt_count", "min_source_truth_supported_prompts")
    min_check("successful_llm_call_count", "min_successful_llm_calls")
    min_check("live_llm_call_count", "min_live_llm_calls")
    min_check("simulated_llm_draft_count", "min_simulated_llm_drafts")
    max_check("llm_call_error_count", "max_llm_call_errors")
    max_check("answer_permission_count", "max_answer_permission_count")
    max_check("source_truth_mutation_allowed_count", "max_source_truth_mutation_allowed")
    if thresholds.get("require_no_answer_permission"):
        observed = int(report.get("answer_permission_count", 0) or 0)
        add("require_no_answer_permission", observed, "==", 0, observed == 0)
    return checks


def build_report(prompt_contract_report: Any, *, config: LlmConfig, thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    contracts = prompt_contracts(prompt_contract_report)
    drafts = build_drafts(contracts, config=config)
    prompt_contract_count = len(contracts)
    ready_prompt_contract_count = sum(1 for c in contracts if _contract_ready(c))
    llm_draft_count = len(drafts)
    drafts_ready = sum(1 for d in drafts if d.get("ready_for_final_gate"))
    nonempty = sum(1 for d in drafts if d.get("draft_text"))
    source_truth_supported = sum(1 for d in drafts if int(d.get("source_truth_evidence_count") or 0) > 0)
    successful = sum(1 for d in drafts if d.get("llm_call_status") in {"LLM_CALL_SUCCEEDED", "SIMULATED_DRAFT_BUILT"})
    live_calls = sum(1 for d in drafts if d.get("llm_call_status") == "LLM_CALL_SUCCEEDED")
    simulated = sum(1 for d in drafts if d.get("llm_call_status") == "SIMULATED_DRAFT_BUILT")
    errors = sum(1 for d in drafts if str(d.get("draft_adapter_status")) == "LLM_DRAFT_ADAPTER_ERROR")
    reasoning_omitted = sum(1 for d in drafts if (d.get("llm_response_metadata") or {}).get("reasoning_omitted_from_draft"))
    citation_like = sum(1 for d in drafts if int(d.get("citation_like_count") or 0) > 0)
    cap_disclosure_needed = sum(
        1 for d in drafts if any(d.get("aggregation_cap_disclosure", {}).get(k) for k in ("result_was_capped", "more_results_available", "high_degree_node_detected"))
    )
    cap_disclosure_detected = sum(1 for d in drafts if d.get("cap_disclosure_detected_in_draft"))

    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": QUALITY_PASS,
        "prompt_contract_count": prompt_contract_count,
        "ready_prompt_contract_count": ready_prompt_contract_count,
        "llm_draft_count": llm_draft_count,
        "drafts_ready_for_final_gate_count": drafts_ready,
        "drafts_with_nonempty_content_count": nonempty,
        "source_truth_supported_prompt_count": source_truth_supported,
        "successful_llm_call_count": successful,
        "live_llm_call_count": live_calls,
        "simulated_llm_draft_count": simulated,
        "llm_call_error_count": errors,
        "drafts_with_citation_like_tokens_count": citation_like,
        "drafts_needing_cap_disclosure_count": cap_disclosure_needed,
        "drafts_with_cap_disclosure_detected_count": cap_disclosure_detected,
        "llm_reasoning_omitted_count": reasoning_omitted,
        "answer_permission_count": sum(1 for d in drafts if d.get("answer_permission")),
        "source_truth_mutation_allowed_count": sum(1 for d in drafts if d.get("source_truth_mutation_allowed")),
        "contract": {
            "llm_draft_adapter_stage": True,
            "real_llm_call_supported": True,
            "llm_mode": config.mode,
            "llm_model": config.model,
            "llm_base_url": config.base_url,
            "final_gate_required_after_llm_draft": True,
            "draft_is_not_final_answer": True,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "llm_reasoning_field_is_not_passed_to_final_gate": True,
        },
        "llm_drafts": drafts,
    }
    checks = evaluate_quality(report, thresholds)
    report["quality_checks"] = checks
    if not all(c["passed"] for c in checks):
        report["quality_status"] = QUALITY_FAIL
        report["status"] = STATUS_NEEDS_REPAIR
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Live LLM Draft Adapter v22")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status')}**")
    lines.append(f"Status: `{report.get('status')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "prompt_contract_count",
        "ready_prompt_contract_count",
        "llm_draft_count",
        "drafts_ready_for_final_gate_count",
        "drafts_with_nonempty_content_count",
        "source_truth_supported_prompt_count",
        "successful_llm_call_count",
        "live_llm_call_count",
        "simulated_llm_draft_count",
        "llm_call_error_count",
        "drafts_with_citation_like_tokens_count",
        "drafts_needing_cap_disclosure_count",
        "drafts_with_cap_disclosure_detected_count",
        "llm_reasoning_omitted_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {report.get(key)}")
    lines.append("")
    lines.append("## Contract")
    lines.append("- This stage may call the configured LLM, but the output is only a draft.")
    lines.append("- The draft must pass a later TRACE-Net final gate before WebUI final answer use.")
    lines.append("- The LLM receives compact v21 context packs, not the raw 5TB corpus or full graph.")
    lines.append("- Source-truth evidence remains the only proof authority; graph/Leiden and v2 summaries remain guidance only.")
    lines.append("- Any provider reasoning field is stored as metadata only and is not passed as answer text.")
    lines.append("")
    lines.append("## Drafts")
    for d in report.get("llm_drafts", []):
        lines.append(f"### {d.get('llm_draft_id')} — `{d.get('draft_adapter_status')}`")
        lines.append(f"- query: {d.get('user_query')}")
        lines.append(f"- mode/model: {d.get('llm_mode')} / {d.get('llm_model')}")
        lines.append(f"- llm_call_status: {d.get('llm_call_status')}")
        lines.append(f"- ready_for_final_gate: {d.get('ready_for_final_gate')}")
        lines.append(f"- citation_like_count: {d.get('citation_like_count')}")
        if d.get("error_message"):
            lines.append(f"- error: {d.get('error_type')}: {d.get('error_message')}")
        text = str(d.get("draft_text") or "").strip().replace("\n", " ")
        if text:
            lines.append(f"- draft_preview: {text[:280]}")
        lines.append("")
    lines.append("## Quality checks")
    for check in report.get("quality_checks", []):
        prefix = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_live_llm_draft_adapter_v22.json"
    drafts_path = out / "trace_net_e2e_live_llm_draft_adapter_records_v22.jsonl"
    inspect_path = out / "trace_net_e2e_live_llm_draft_adapter_v22.md"
    write_json(report_path, report)
    write_jsonl(drafts_path, report.get("llm_drafts", []))
    inspect_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "drafts_jsonl_path": str(drafts_path),
        "inspect_md_path": str(inspect_path),
    }


def print_summary(report: Mapping[str, Any]) -> None:
    print("TRACE-Net E2E Live LLM Draft Adapter v22")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "prompt_contract_count",
        "ready_prompt_contract_count",
        "llm_draft_count",
        "drafts_ready_for_final_gate_count",
        "successful_llm_call_count",
        "live_llm_call_count",
        "simulated_llm_draft_count",
        "llm_call_error_count",
        "drafts_with_citation_like_tokens_count",
        "llm_reasoning_omitted_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {report.get(key)}")
    for key in ("report_path", "drafts_jsonl_path", "inspect_md_path"):
        if key in report:
            print(f" {key}: {report[key]}")


def _thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_prompt_contracts": args.min_prompt_contracts,
        "min_llm_drafts": args.min_llm_drafts,
        "min_drafts_ready_for_final_gate": args.min_drafts_ready_for_final_gate,
        "min_drafts_with_nonempty_content": args.min_drafts_with_nonempty_content,
        "min_source_truth_supported_prompts": args.min_source_truth_supported_prompts,
        "min_successful_llm_calls": args.min_successful_llm_calls,
        "min_live_llm_calls": args.min_live_llm_calls,
        "min_simulated_llm_drafts": args.min_simulated_llm_drafts,
        "max_llm_call_errors": args.max_llm_call_errors,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E Live LLM Draft Adapter v22")
    parser.add_argument("--live-llm-prompt-contract", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--llm-mode", choices=["simulate", "ollama"], default="simulate")
    parser.add_argument("--llm-base-url", default=DEFAULT_LLM_BASE_URL)
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--llm-api-key", default=DEFAULT_LLM_API_KEY)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--max-contracts", type=int, default=0)
    parser.add_argument("--min-prompt-contracts", type=int, default=5)
    parser.add_argument("--min-llm-drafts", type=int, default=5)
    parser.add_argument("--min-drafts-ready-for-final-gate", type=int, default=5)
    parser.add_argument("--min-drafts-with-nonempty-content", type=int, default=5)
    parser.add_argument("--min-source-truth-supported-prompts", type=int, default=5)
    parser.add_argument("--min-successful-llm-calls", type=int, default=5)
    parser.add_argument("--min-live-llm-calls", type=int, default=0)
    parser.add_argument("--min-simulated-llm-drafts", type=int, default=0)
    parser.add_argument("--max-llm-call-errors", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    data = load_json(args.live_llm_prompt_contract)
    config = LlmConfig(
        mode=args.llm_mode,
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        temperature=args.temperature,
        timeout=args.request_timeout,
        max_contracts=args.max_contracts,
    )
    report = build_report(data, config=config, thresholds=_thresholds_from_args(args))
    paths = write_report_files(report, args.output_dir)
    report.update(paths)
    write_json(paths["report_path"], report)
    Path(paths["inspect_md_path"]).write_text(render_markdown(report), encoding="utf-8")
    print_summary(report)
    if args.quality and report.get("quality_status") != QUALITY_PASS:
        return 1
    return 0


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E Live LLM Draft Adapter v22 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-prompt-contracts", type=int, default=5)
    parser.add_argument("--min-llm-drafts", type=int, default=5)
    parser.add_argument("--min-drafts-ready-for-final-gate", type=int, default=5)
    parser.add_argument("--min-drafts-with-nonempty-content", type=int, default=5)
    parser.add_argument("--min-source-truth-supported-prompts", type=int, default=5)
    parser.add_argument("--min-successful-llm-calls", type=int, default=5)
    parser.add_argument("--min-live-llm-calls", type=int, default=0)
    parser.add_argument("--min-simulated-llm-drafts", type=int, default=0)
    parser.add_argument("--max-llm-call-errors", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    report = load_json(args.report_path)
    checks = evaluate_quality(report, _thresholds_from_args(args))
    report["quality_checks"] = checks
    report["quality_status"] = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    report["status"] = STATUS_READY if report["quality_status"] == QUALITY_PASS else STATUS_NEEDS_REPAIR
    print("TRACE-Net E2E Live LLM Draft Adapter v22 Quality")
    print(f" quality_status: {report['quality_status']}")
    for c in checks:
        prefix = "PASS" if c["passed"] else "FAIL"
        print(f" {prefix} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    if args.write_json:
        write_json(args.report_path, report)
    return 0 if report["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
