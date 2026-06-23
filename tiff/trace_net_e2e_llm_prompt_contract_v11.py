"""TRACE-Net E2E LLM prompt contract v11.

This module turns dynamic context packs, Self-RAG critiques, and CRAG plans
into strict LLM prompt packets. It is prompt-construction only: it does not
call an LLM, rerun retrieval, rerun OCR, rebuild embeddings/summaries/graph,
mutate source truth, or write to external services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v11"
STATUS_BUILT = "E2E_LLM_PROMPT_CONTRACT_BUILT"
STATUS_READY = "E2E_LLM_PROMPT_CONTRACT_READY_FOR_REASONED_DRAFT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

READY_SELF_RAG_STATUSES = {"SELF_RAG_CONTEXT_READY", "READY", "PASS"}
NO_RETRY_CRAG_STATUSES = {"CRAG_NO_RETRY_NEEDED", "READY", "PASS"}

DEFAULT_CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_context_packs": True,
    "uses_prebuilt_self_rag_critiques": True,
    "uses_prebuilt_crag_plans": True,
    "prompt_contract_only": True,
    "prompt_builder_does_not_call_llm": True,
    "prompt_builder_does_not_rerun_retrieval": True,
    "prompt_builder_does_not_rerun_ocr": True,
    "prompt_builder_does_not_rerun_page_classification": True,
    "prompt_builder_does_not_rerun_embeddings": True,
    "prompt_builder_does_not_rerun_page_summaries": True,
    "prompt_builder_does_not_rerun_graph_build": True,
    "prompt_builder_does_not_rerun_table_extraction": True,
    "evidence_box_is_source_truth": True,
    "guidance_box_is_not_source_truth": True,
    "graph_is_not_proof_authority": True,
    "summaries_are_not_source_truth": True,
    "cite_every_factual_claim": True,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
}

SYSTEM_PROMPT = """You are TRACE-Net's grounded response drafter. You must use SOURCE-TRUTH EVIDENCE for factual claims and citations. Use GUIDANCE ONLY to understand route, graph, vector, summary, and table-route context. Graph/community hints, summaries, vector/page profiles, and route metadata are not proof authority. Do not invent missing part descriptions. If the evidence is insufficient, say the evidence is insufficient instead of guessing. Do not mutate source truth."""

DEVELOPER_PROMPT = """TRACE-Net contract: cite every factual claim from SOURCE-TRUTH EVIDENCE. Treat GUIDANCE ONLY as navigation context, not proof. Respect Self-RAG and CRAG statuses. If Self-RAG is not ready or CRAG requires retry/review, do not draft a final answer; return an audit-only limitation."""


def read_json(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path | str, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}
    return bool(value)


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def safe_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def extract_context_packs(context_pack_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("context_packs", "packs", "records", "context_pack_records"):
        rows = context_pack_report.get(key)
        if isinstance(rows, list):
            return [dict(r) for r in rows if isinstance(r, Mapping)]
    if "context_pack_id" in context_pack_report:
        return [dict(context_pack_report)]
    return []


def extract_critiques(self_rag_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("critiques", "self_rag_critiques", "context_critiques", "critique_records", "records"):
        rows = self_rag_report.get(key)
        if isinstance(rows, list):
            return [dict(r) for r in rows if isinstance(r, Mapping)]
    if "context_pack_id" in self_rag_report:
        return [dict(self_rag_report)]
    return []


def extract_crag_plans(crag_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("crag_plans", "plans", "records", "crag_plan_records"):
        rows = crag_report.get(key)
        if isinstance(rows, list):
            return [dict(r) for r in rows if isinstance(r, Mapping)]
    if "context_pack_id" in crag_report:
        return [dict(crag_report)]
    return []


def index_by_context_pack(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        context_pack_id = str(row.get("context_pack_id") or "").strip()
        if context_pack_id:
            index[context_pack_id] = dict(row)
    return index


def evidence_items(context_pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    box = safe_mapping(context_pack.get("evidence_box"))
    rows = box.get("items")
    if isinstance(rows, list):
        return [dict(r) for r in rows if isinstance(r, Mapping)]
    rows = context_pack.get("evidence_items")
    if isinstance(rows, list):
        return [dict(r) for r in rows if isinstance(r, Mapping)]
    return []


def guidance_items(context_pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    box = safe_mapping(context_pack.get("guidance_box"))
    rows = box.get("items")
    if isinstance(rows, list):
        return [dict(r) for r in rows if isinstance(r, Mapping)]
    rows = context_pack.get("guidance_items")
    if isinstance(rows, list):
        return [dict(r) for r in rows if isinstance(r, Mapping)]
    return []


def _fmt_evidence_item(item: Mapping[str, Any]) -> str:
    rank = item.get("rank") or item.get("evidence_id") or "?"
    field = item.get("field_name", "")
    value = item.get("normalized_value", "")
    page = item.get("page_id", "")
    source_tunnel = item.get("source_tunnel", "")
    score = item.get("total_tunnel_score", "")
    return f"- [{rank}] page={page} field={field} value={value} source_tunnel={source_tunnel} tunnel_score={score}"


def _fmt_guidance_item(item: Mapping[str, Any]) -> str:
    tunnel = item.get("tunnel_type", item.get("source_tunnel", "guidance"))
    page = item.get("page_id", "")
    text = str(item.get("guidance_text") or item.get("summary") or item.get("description") or "").strip()
    authority = item.get("authority", "guidance_only_not_source_truth")
    return f"- tunnel={tunnel} page={page} authority={authority} text={text}"


def build_prompt_text(context_pack: Mapping[str, Any], critique: Mapping[str, Any], crag_plan: Mapping[str, Any]) -> str:
    ev_items = evidence_items(context_pack)
    gd_items = guidance_items(context_pack)
    query = str(context_pack.get("user_query") or critique.get("user_query") or crag_plan.get("user_query") or "")
    intent = str(context_pack.get("query_intent") or critique.get("query_intent") or crag_plan.get("query_intent") or "unknown")
    self_status = str(critique.get("self_rag_critic_status") or "UNKNOWN")
    crag_status = str(crag_plan.get("crag_plan_status") or "UNKNOWN")

    evidence_lines = "\n".join(_fmt_evidence_item(item) for item in ev_items) or "- none"
    guidance_lines = "\n".join(_fmt_guidance_item(item) for item in gd_items) or "- none"

    return "\n".join(
        [
            "TRACE-NET LLM PROMPT CONTRACT v11",
            "",
            "USER QUESTION:",
            query,
            "",
            "QUERY INTENT:",
            intent,
            "",
            "SELF-RAG STATUS:",
            self_status,
            "",
            "CRAG STATUS:",
            crag_status,
            "",
            "SOURCE-TRUTH EVIDENCE (ONLY THIS BOX CAN SUPPORT FACTUAL CLAIMS):",
            evidence_lines,
            "",
            "GUIDANCE ONLY (not source truth, not proof):",
            guidance_lines,
            "",
            "ANSWER RULES:",
            "- Cite every factual claim using SOURCE-TRUTH EVIDENCE.",
            "- Do not cite graph/community hints, summaries, vector/page profiles, route metadata, or table-route summaries as proof; they are guidance only and not proof.",
            "- Use guidance only to understand context and navigate related evidence.",
            "- If evidence is insufficient, say the evidence is insufficient instead of guessing.",
            "- Do not invent missing part descriptions, procedures, quantities, or applicability.",
            "- Do not mutate or rewrite source truth.",
            "- Keep answer_permission=false, can_answer_directly=false, and can_prove_claims=false until a later final-answer gate changes them.",
        ]
    )


def is_self_rag_ready(critique: Mapping[str, Any]) -> bool:
    status = str(critique.get("self_rag_critic_status") or "")
    return status in READY_SELF_RAG_STATUSES and not as_bool(critique.get("needs_crag_retry")) and not as_bool(critique.get("needs_human_review"))


def is_crag_no_retry(crag_plan: Mapping[str, Any]) -> bool:
    status = str(crag_plan.get("crag_plan_status") or "")
    return status in NO_RETRY_CRAG_STATUSES and not as_bool(crag_plan.get("needs_retry")) and not as_bool(crag_plan.get("needs_human_review"))


def build_prompt_contract_record(
    context_pack: Mapping[str, Any],
    critique: Mapping[str, Any],
    crag_plan: Mapping[str, Any],
    index: int,
) -> Dict[str, Any]:
    ev_items = evidence_items(context_pack)
    gd_items = guidance_items(context_pack)
    context_pack_id = str(context_pack.get("context_pack_id") or critique.get("context_pack_id") or crag_plan.get("context_pack_id") or f"unknown_context_{index:04d}")
    user_query = str(context_pack.get("user_query") or critique.get("user_query") or crag_plan.get("user_query") or "")
    query_intent = str(context_pack.get("query_intent") or critique.get("query_intent") or crag_plan.get("query_intent") or "unknown")

    self_ready = is_self_rag_ready(critique)
    crag_ready = is_crag_no_retry(crag_plan)
    evidence_ready = bool(ev_items) and all(as_bool(item.get("citation_ready")) and as_bool(item.get("source_trace_ready")) for item in ev_items)
    guidance_safe = all("source_truth" not in str(item.get("authority", "")).lower() or "not_source_truth" in str(item.get("authority", "")).lower() for item in gd_items)
    graph_summary_proof_violation = as_int(critique.get("graph_summary_proof_violation_count")) + as_int(crag_plan.get("graph_summary_proof_violation_count"))

    prompt_ready = self_ready and crag_ready and evidence_ready and guidance_safe and graph_summary_proof_violation == 0
    prompt_text = build_prompt_text(context_pack, critique, crag_plan)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "developer", "content": DEVELOPER_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_contract_id": f"llm_prompt_contract_v11_{index:04d}",
        "context_pack_id": context_pack_id,
        "user_query": user_query,
        "query_intent": query_intent,
        "prompt_contract_status": "LLM_PROMPT_CONTRACT_READY" if prompt_ready else "LLM_PROMPT_CONTRACT_NOT_READY",
        "ready_for_reasoned_response_draft": prompt_ready,
        "source_self_rag_status": critique.get("self_rag_critic_status", "UNKNOWN"),
        "source_crag_plan_status": crag_plan.get("crag_plan_status", "UNKNOWN"),
        "self_rag_ready": self_ready,
        "crag_no_retry_needed": crag_ready,
        "evidence_ready": evidence_ready,
        "guidance_safe": guidance_safe,
        "source_truth_evidence_count": len(ev_items),
        "citation_ready_evidence_count": sum(1 for item in ev_items if as_bool(item.get("citation_ready"))),
        "source_trace_ready_evidence_count": sum(1 for item in ev_items if as_bool(item.get("source_trace_ready"))),
        "guidance_item_count": len(gd_items),
        "graph_or_summary_guidance_count": sum(
            1
            for item in gd_items
            if str(item.get("tunnel_type", "")) in {"page_summary_tunnel", "graph_community_tunnel", "graph_navigation_tunnel"}
        ),
        "graph_summary_proof_violation_count": graph_summary_proof_violation,
        "message_count": len(messages),
        "messages": messages,
        "prompt_text": prompt_text,
        "prompt_policy": {
            "source_truth_evidence_section": "SOURCE-TRUTH EVIDENCE",
            "guidance_section": "GUIDANCE ONLY",
            "rules_section": "ANSWER RULES",
            "cite_every_factual_claim": True,
            "llm_may_answer_from_guidance_only": False,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "unsupported_claim_policy": "say_evidence_is_insufficient_or_keep_audit_draft",
        },
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "contract": DEFAULT_CONTRACT,
    }


def build_llm_prompt_contract_report(
    dynamic_context_pack: Mapping[str, Any],
    self_rag_context_critic: Mapping[str, Any],
    crag_retrieval_corrector: Mapping[str, Any],
    source_paths: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    context_packs = extract_context_packs(dynamic_context_pack)
    critiques_by_id = index_by_context_pack(extract_critiques(self_rag_context_critic))
    crag_by_id = index_by_context_pack(extract_crag_plans(crag_retrieval_corrector))

    prompt_contracts: List[Dict[str, Any]] = []
    for i, pack in enumerate(context_packs, start=1):
        context_pack_id = str(pack.get("context_pack_id") or "")
        critique = critiques_by_id.get(context_pack_id, {})
        crag_plan = crag_by_id.get(context_pack_id, {})
        prompt_contracts.append(build_prompt_contract_record(pack, critique, crag_plan, i))

    ready_prompt_contract_count = sum(1 for p in prompt_contracts if as_bool(p.get("ready_for_reasoned_response_draft")))
    prompt_contract_count = len(prompt_contracts)
    total_prompt_message_count = sum(as_int(p.get("message_count")) for p in prompt_contracts)
    contracts_with_source_truth_evidence_count = sum(1 for p in prompt_contracts if as_int(p.get("source_truth_evidence_count")) > 0)
    contracts_with_guidance_box_count = sum(1 for p in prompt_contracts if as_int(p.get("guidance_item_count")) > 0)
    contracts_with_self_rag_ready_count = sum(1 for p in prompt_contracts if as_bool(p.get("self_rag_ready")))
    contracts_with_crag_no_retry_count = sum(1 for p in prompt_contracts if as_bool(p.get("crag_no_retry_needed")))
    contracts_with_graph_or_summary_guidance_count = sum(1 for p in prompt_contracts if as_int(p.get("graph_or_summary_guidance_count")) > 0)
    graph_summary_proof_violation_count = sum(as_int(p.get("graph_summary_proof_violation_count")) for p in prompt_contracts)

    answer_permission_count = sum(1 for p in prompt_contracts if as_bool(p.get("answer_permission")))
    can_answer_directly_count = sum(1 for p in prompt_contracts if as_bool(p.get("can_answer_directly")))
    can_prove_claims_count = sum(1 for p in prompt_contracts if as_bool(p.get("can_prove_claims")))
    source_truth_mutation_allowed_count = sum(1 for p in prompt_contracts if as_bool(p.get("source_truth_mutation_allowed")))

    summary = {
        "quality_status": QUALITY_PASS,
        "context_pack_count": len(context_packs),
        "prompt_contract_count": prompt_contract_count,
        "ready_prompt_contract_count": ready_prompt_contract_count,
        "total_prompt_message_count": total_prompt_message_count,
        "contracts_with_source_truth_evidence_count": contracts_with_source_truth_evidence_count,
        "contracts_with_guidance_box_count": contracts_with_guidance_box_count,
        "contracts_with_self_rag_ready_count": contracts_with_self_rag_ready_count,
        "contracts_with_crag_no_retry_count": contracts_with_crag_no_retry_count,
        "contracts_with_graph_or_summary_guidance_count": contracts_with_graph_or_summary_guidance_count,
        "graph_summary_proof_violation_count": graph_summary_proof_violation_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "e2e_llm_prompt_contract_status": STATUS_READY,
        "quality_status": QUALITY_PASS,
        "source_paths": dict(source_paths or {}),
        "llm_prompt_contract_contract": DEFAULT_CONTRACT,
        "summary": summary,
        "prompt_contracts": prompt_contracts,
    }


def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    summary = safe_mapping(report.get("summary"))
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == QUALITY_PASS)
    add("context_pack_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", as_int(summary.get("context_pack_count")) >= args.min_context_packs)
    add("prompt_contract_count", summary.get("prompt_contract_count", 0), f">= {args.min_prompt_contracts}", as_int(summary.get("prompt_contract_count")) >= args.min_prompt_contracts)
    add("ready_prompt_contract_count", summary.get("ready_prompt_contract_count", 0), f">= {args.min_ready_prompt_contracts}", as_int(summary.get("ready_prompt_contract_count")) >= args.min_ready_prompt_contracts)
    add("total_prompt_message_count", summary.get("total_prompt_message_count", 0), f">= {args.min_total_prompt_messages}", as_int(summary.get("total_prompt_message_count")) >= args.min_total_prompt_messages)
    add("contracts_with_source_truth_evidence_count", summary.get("contracts_with_source_truth_evidence_count", 0), f">= {args.min_contracts_with_source_truth_evidence}", as_int(summary.get("contracts_with_source_truth_evidence_count")) >= args.min_contracts_with_source_truth_evidence)
    add("contracts_with_guidance_box_count", summary.get("contracts_with_guidance_box_count", 0), f">= {args.min_contracts_with_guidance_box}", as_int(summary.get("contracts_with_guidance_box_count")) >= args.min_contracts_with_guidance_box)
    add("contracts_with_self_rag_ready_count", summary.get("contracts_with_self_rag_ready_count", 0), f">= {args.min_contracts_with_self_rag_ready}", as_int(summary.get("contracts_with_self_rag_ready_count")) >= args.min_contracts_with_self_rag_ready)
    add("contracts_with_crag_no_retry_count", summary.get("contracts_with_crag_no_retry_count", 0), f">= {args.min_contracts_with_crag_no_retry}", as_int(summary.get("contracts_with_crag_no_retry_count")) >= args.min_contracts_with_crag_no_retry)
    add("contracts_with_graph_or_summary_guidance_count", summary.get("contracts_with_graph_or_summary_guidance_count", 0), f">= {args.min_contracts_with_graph_or_summary_guidance}", as_int(summary.get("contracts_with_graph_or_summary_guidance_count")) >= args.min_contracts_with_graph_or_summary_guidance)
    add("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), f"<= {args.max_graph_summary_proof_violations}", as_int(summary.get("graph_summary_proof_violation_count")) <= args.max_graph_summary_proof_violations)
    add("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", as_int(summary.get("answer_permission_count")) <= args.max_answer_permission_count)
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", as_int(summary.get("source_truth_mutation_allowed_count")) <= args.max_source_truth_mutation_allowed)
    add("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", as_int(summary.get("can_answer_directly_count")) == 0)
    add("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", as_int(summary.get("can_prove_claims_count")) == 0)
    add("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", as_int(summary.get("postgres_write_attempt_count")) == 0)
    add("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", as_int(summary.get("qdrant_write_attempt_count")) == 0)
    add("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", as_int(summary.get("opensearch_write_attempt_count")) == 0)
    if args.require_no_answer_permission:
        add("require_no_answer_permission", summary.get("answer_permission_count", 0), "== 0", as_int(summary.get("answer_permission_count")) == 0)

    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def add_quality_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--min-context-packs", type=int, default=1)
    parser.add_argument("--min-prompt-contracts", type=int, default=1)
    parser.add_argument("--min-ready-prompt-contracts", type=int, default=1)
    parser.add_argument("--min-total-prompt-messages", type=int, default=3)
    parser.add_argument("--min-contracts-with-source-truth-evidence", type=int, default=1)
    parser.add_argument("--min-contracts-with-guidance-box", type=int, default=0)
    parser.add_argument("--min-contracts-with-self-rag-ready", type=int, default=0)
    parser.add_argument("--min-contracts-with-crag-no-retry", type=int, default=0)
    parser.add_argument("--min-contracts-with-graph-or-summary-guidance", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = safe_mapping(report.get("summary"))
    lines = [
        "# TRACE-Net E2E LLM Prompt Contract v11",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_llm_prompt_contract_status')}`",
        "",
        "## Contract",
        "This prompt-contract stage creates LLM-ready messages only. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
        "",
        "## Summary",
    ]
    for key in [
        "context_pack_count",
        "prompt_contract_count",
        "ready_prompt_contract_count",
        "total_prompt_message_count",
        "contracts_with_source_truth_evidence_count",
        "contracts_with_guidance_box_count",
        "contracts_with_self_rag_ready_count",
        "contracts_with_crag_no_retry_count",
        "contracts_with_graph_or_summary_guidance_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")

    lines.extend(["", "## Prompt contracts"])
    for prompt in safe_list(report.get("prompt_contracts"))[:10]:
        if not isinstance(prompt, Mapping):
            continue
        lines.append(
            f"- **{prompt.get('prompt_contract_status')}** `{prompt.get('prompt_contract_id')}` | "
            f"{prompt.get('query_intent')} | {prompt.get('user_query')} | "
            f"messages={prompt.get('message_count')} evidence={prompt.get('source_truth_evidence_count')} guidance={prompt.get('guidance_item_count')}"
        )

    lines.extend(["", "## Quality checks"])
    for check in safe_list(report.get("quality_checks")):
        if not isinstance(check, Mapping):
            continue
        prefix = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: Path | str) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_llm_prompt_contract_v11.json"
    prompts_jsonl_path = out / "trace_net_e2e_llm_prompt_contract_records_v11.jsonl"
    messages_jsonl_path = out / "trace_net_e2e_llm_prompt_messages_v11.jsonl"
    inspect_md_path = out / "trace_net_e2e_llm_prompt_contract_v11.md"

    write_json(report_path, report)
    prompt_contracts = [dict(p) for p in safe_list(report.get("prompt_contracts")) if isinstance(p, Mapping)]
    write_jsonl(prompts_jsonl_path, prompt_contracts)
    message_rows: List[Dict[str, Any]] = []
    for prompt in prompt_contracts:
        for idx, message in enumerate(safe_list(prompt.get("messages")), start=1):
            if isinstance(message, Mapping):
                row = {
                    "prompt_contract_id": prompt.get("prompt_contract_id"),
                    "context_pack_id": prompt.get("context_pack_id"),
                    "user_query": prompt.get("user_query"),
                    "query_intent": prompt.get("query_intent"),
                    "message_index": idx,
                    "role": message.get("role"),
                    "content": message.get("content"),
                }
                message_rows.append(row)
    write_jsonl(messages_jsonl_path, message_rows)
    inspect_md_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "prompts_jsonl_path": str(prompts_jsonl_path),
        "messages_jsonl_path": str(messages_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }


def print_quality_result(report: Mapping[str, Any], checks: Sequence[Mapping[str, Any]], title: str = "TRACE-Net E2E LLM Prompt Contract v11 Quality") -> None:
    print(title)
    print(f" quality_status: {report.get('quality_status')}")
    for check in checks:
        prefix = "PASS" if check.get("passed") else "FAIL"
        print(f" {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
