"""TRACE-Net E2E Reasoned Response Draft v12.

Builds deterministic, citation-grounded draft answers from v11 LLM prompt
contracts without calling an LLM. This is the bridge between prompt-contract
construction and the later final answer gate.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v12"
STATUS_BUILT = "E2E_REASONED_RESPONSE_DRAFT_BUILT"
STATUS_READY = "E2E_REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE"
DRAFT_STATUS_READY = "REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE"
DRAFT_STATUS_AUDIT_ONLY = "REASONED_RESPONSE_DRAFT_AUDIT_ONLY"
DEFAULT_OUTPUT_BASENAME = "trace_net_e2e_reasoned_response_draft_v12"

CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_prompt_contracts": True,
    "reasoned_draft_does_not_call_llm": True,
    "reasoned_draft_is_deterministic": True,
    "reasoned_draft_only": True,
    "evidence_box_is_source_truth": True,
    "guidance_box_is_not_source_truth": True,
    "graph_is_not_proof_authority": True,
    "summaries_are_not_source_truth": True,
    "cite_every_factual_claim": True,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "reruns_ocr": False,
    "reruns_page_classification": False,
    "reruns_embeddings": False,
    "reruns_page_summaries": False,
    "reruns_graph_build": False,
    "reruns_table_extraction": False,
    "reruns_retrieval": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
}


def load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def nested_get(record: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    cur: Any = record
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def clean_text(value: Any) -> str:
    text = str(value or "")
    # Clean harmless prompt formatting artifacts from earlier prompt contracts.
    text = text.replace("everyfactual", "every factual")
    text = text.replace("route,graph", "route, graph")
    text = text.replace("texthandling", "text handling")
    text = text.replace("torelated", "to related")
    text = text.replace("asproof", "as proof")
    text = text.replace("relatedevidence", "related evidence")
    text = text.replace("-tunnel=", "- tunnel=")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_source_truth_evidence_from_prompt(prompt_text: str) -> List[Dict[str, Any]]:
    """Parse v11 SOURCE-TRUTH EVIDENCE lines when structured evidence is absent."""
    evidence: List[Dict[str, Any]] = []
    in_section = False
    for raw in str(prompt_text or "").splitlines():
        line = raw.strip()
        if line.startswith("SOURCE-TRUTH EVIDENCE"):
            in_section = True
            continue
        if line.startswith("GUIDANCE ONLY") or line.startswith("ANSWER RULES"):
            in_section = False
        if not in_section or not line.startswith("- ["):
            continue
        m = re.search(
            r"\[(?P<rank>\d+)\]\s+page=(?P<page>\S+)\s+field=(?P<field>\S+)\s+value=(?P<value>.*?)\s+source_tunnel=(?P<tunnel>\S+)(?:\s+tunnel_score=(?P<score>\d+))?",
            line,
        )
        if not m:
            continue
        evidence.append(
            {
                "evidence_id": f"evidence_{int(m.group('rank')):03d}",
                "rank": int(m.group("rank")),
                "page_id": m.group("page"),
                "field_name": m.group("field"),
                "normalized_value": clean_text(m.group("value")),
                "source_tunnel": m.group("tunnel"),
                "total_tunnel_score": int(m.group("score") or 0),
                "citation_ready": True,
                "source_trace_ready": True,
                "answer_authority": "source_truth_evidence_only",
            }
        )
    return evidence


def extract_evidence(contract: Mapping[str, Any]) -> List[Dict[str, Any]]:
    # v11 prompt contracts currently expose evidence in prompt text, not always as a separate field.
    evidence = contract.get("source_truth_evidence") or contract.get("evidence") or contract.get("evidence_box", {}).get("items")
    if isinstance(evidence, list) and evidence:
        out: List[Dict[str, Any]] = []
        for idx, item in enumerate(evidence, start=1):
            if not isinstance(item, Mapping):
                continue
            row = dict(item)
            row.setdefault("evidence_id", f"evidence_{idx:03d}")
            row.setdefault("rank", idx)
            row.setdefault("citation_ready", True)
            row.setdefault("source_trace_ready", True)
            row.setdefault("answer_authority", "source_truth_evidence_only")
            row["normalized_value"] = clean_text(row.get("normalized_value") or row.get("value") or "")
            out.append(row)
        return out
    return parse_source_truth_evidence_from_prompt(str(contract.get("prompt_text") or ""))


def citation(evidence: Mapping[str, Any]) -> str:
    rank = evidence.get("rank") or evidence.get("citation_number") or 1
    return f"[{rank}]"


def unique_pages(evidence: Sequence[Mapping[str, Any]]) -> List[str]:
    pages: List[str] = []
    for item in evidence:
        page = str(item.get("page_id") or "").strip()
        if page and page not in pages:
            pages.append(page)
    return pages


def field_counts(evidence: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    return dict(Counter(str(item.get("field_name") or "unknown") for item in evidence))


def build_reasoned_content(user_query: str, query_intent: str, evidence: Sequence[Mapping[str, Any]]) -> Tuple[str, List[str]]:
    """Build a deterministic answer-like draft from source-truth evidence only."""
    limitations: List[str] = []
    if not evidence:
        return (
            f"TRACE-Net does not have citation-ready source-truth evidence for: '{user_query}'. "
            "The current context should remain audit-only until retrieval is corrected.",
            ["No citation-ready source-truth evidence was available."],
        )

    top = evidence[0]
    top_page = str(top.get("page_id") or "")
    top_field = str(top.get("field_name") or "")
    top_value = clean_text(top.get("normalized_value") or "")
    pages = unique_pages(evidence)

    if query_intent == "covered_part_number":
        parts = [clean_text(item.get("normalized_value") or "") for item in evidence if str(item.get("field_name")) == "covered_part_number"]
        parts = [p for p in parts if p]
        if parts:
            if any(part in user_query for part in parts):
                target = next((part for part in parts if part in user_query), parts[0])
                target_item = next((item for item in evidence if clean_text(item.get("normalized_value")) == target), evidence[0])
                target_page = str(target_item.get("page_id") or top_page)
                lines = [
                    f"TRACE-Net found part number {target} as a covered part number on page {target_page} {citation(target_item)}."
                ]
                related = [p for p in parts if p != target][:2]
                if related:
                    rel_cites = []
                    for rel in related:
                        item = next((x for x in evidence if clean_text(x.get("normalized_value")) == rel), None)
                        if item:
                            rel_cites.append(f"{rel} {citation(item)}")
                    if rel_cites:
                        lines.append("The same evidence set also includes related covered part numbers: " + ", ".join(rel_cites) + ".")
                limitations.append("The available source-truth evidence confirms listing/coverage, but it does not provide a physical part description.")
                lines.append("The evidence is sufficient to confirm the listing, but not enough to describe what the part physically is.")
                return " ".join(lines), limitations
            else:
                page_text = ", ".join(pages)
                examples = []
                for item in evidence[:3]:
                    examples.append(f"{clean_text(item.get('normalized_value'))} {citation(item)}")
                lines = [
                    f"TRACE-Net found covered part numbers on page(s) {page_text}.",
                    "Examples from the source-truth evidence include " + ", ".join(examples) + ".",
                ]
                limitations.append("The draft lists cited covered-part evidence only; it does not infer full applicability beyond the cited records.")
                return " ".join(lines), limitations

    if query_intent == "manual_page_reference":
        refs = []
        for item in evidence[:5]:
            refs.append(
                f"{clean_text(item.get('field_name'))}={clean_text(item.get('normalized_value'))} on page {item.get('page_id')} {citation(item)}"
            )
        limitations.append("The draft reports where the reference appears in extracted table evidence; it does not infer procedural meaning beyond those citations.")
        return "TRACE-Net found the manual reference in these source-truth records: " + "; ".join(refs) + ".", limitations

    if query_intent == "table_text":
        phrase = top_value
        # Keep every page mention directly paired with its own citation.
        # The final answer gate intentionally rejects a sentence that lists
        # five pages but only provides three trailing citations.
        page_refs = []
        seen_pages = set()
        for item in evidence[:5]:
            page = str(item.get("page_id") or "").strip()
            if not page or page in seen_pages:
                continue
            seen_pages.add(page)
            page_refs.append(f"{page} {citation(item)}")
        page_text = ", ".join(page_refs) if page_refs else ", ".join(pages)
        limitations.append("The draft confirms the exact table text occurrence only; it does not infer surrounding table meaning without additional cited context.")
        return f"TRACE-Net found the table text '{phrase}' on page(s) {page_text}.", limitations

    # Generic fallback.
    snippets = []
    for item in evidence[:3]:
        snippets.append(
            f"{clean_text(item.get('field_name'))}={clean_text(item.get('normalized_value'))} on {item.get('page_id')} {citation(item)}"
        )
    limitations.append("The draft uses only the cited source-truth evidence and avoids unsupported interpretation.")
    return "TRACE-Net found citation-ready evidence: " + "; ".join(snippets) + ".", limitations


def build_draft(contract: Mapping[str, Any], index: int) -> Dict[str, Any]:
    evidence = extract_evidence(contract)
    user_query = clean_text(contract.get("user_query") or "")
    query_intent = clean_text(contract.get("query_intent") or "unknown")
    prompt_contract_id = str(contract.get("prompt_contract_id") or f"llm_prompt_contract_v11_{index:04d}")
    self_rag_ready = bool(contract.get("self_rag_ready") or contract.get("source_self_rag_status") == "SELF_RAG_CONTEXT_READY")
    crag_no_retry = bool(contract.get("crag_no_retry_needed") or contract.get("source_crag_plan_status") == "CRAG_NO_RETRY_NEEDED")
    graph_summary_proof_violation_count = int(contract.get("graph_summary_proof_violation_count") or 0)

    ready = bool(evidence) and self_rag_ready and crag_no_retry and graph_summary_proof_violation_count == 0
    content, limitations = build_reasoned_content(user_query, query_intent, evidence)

    citations = []
    for item in evidence:
        rank = int(item.get("rank") or len(citations) + 1)
        citations.append(
            {
                "citation_id": f"citation_{rank}",
                "citation_marker": f"[{rank}]",
                "evidence_id": item.get("evidence_id", f"evidence_{rank:03d}"),
                "page_id": item.get("page_id", ""),
                "field_name": item.get("field_name", ""),
                "normalized_value": clean_text(item.get("normalized_value", "")),
                "source_tunnel": item.get("source_tunnel", ""),
                "citation_ready": bool(item.get("citation_ready", True)),
                "source_trace_ready": bool(item.get("source_trace_ready", True)),
                "answer_authority": item.get("answer_authority", "source_truth_evidence_only"),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "reasoned_response_draft_id": f"reasoned_response_draft_v12_{index:04d}",
        "reasoned_response_draft_status": DRAFT_STATUS_READY if ready else DRAFT_STATUS_AUDIT_ONLY,
        "ready_for_final_gate": ready,
        "response_is_reasoned_draft": True,
        "prompt_contract_id": prompt_contract_id,
        "context_pack_id": contract.get("context_pack_id", ""),
        "user_query": user_query,
        "query_intent": query_intent,
        "draft_message": {
            "role": "assistant",
            "content": content,
        },
        "citations": citations,
        "citation_count": len(citations),
        "source_truth_evidence_count": len(evidence),
        "citation_ready_evidence_count": sum(1 for c in citations if c.get("citation_ready")),
        "source_trace_ready_evidence_count": sum(1 for c in citations if c.get("source_trace_ready")),
        "page_ids": unique_pages(evidence),
        "field_counts": field_counts(evidence),
        "self_rag_ready": self_rag_ready,
        "crag_no_retry_needed": crag_no_retry,
        "graph_summary_proof_violation_count": graph_summary_proof_violation_count,
        "limitations": limitations,
        "draft_policy": {
            "uses_source_truth_evidence_only_for_claims": True,
            "guidance_used_as_context_only": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "final_answer_gate_required": True,
            "unsupported_claim_policy": "state_insufficient_evidence_instead_of_guessing",
        },
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "contract": dict(CONTRACT),
    }


def quality_checks(report: Mapping[str, Any], thresholds: Mapping[str, Any]) -> List[Dict[str, Any]]:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}

    def num(name: str) -> int:
        value = summary.get(name, 0)
        try:
            return int(value)
        except Exception:
            return 0

    checks = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == "PASS")
    for key, default in [
        ("min_prompt_contracts", 1),
        ("min_reasoned_drafts", 1),
        ("min_ready_reasoned_drafts", 1),
        ("min_total_citations", 1),
        ("min_drafts_with_limitations", 1),
        ("min_drafts_ready_for_final_gate", 1),
    ]:
        min_value = int(thresholds.get(key, default))
        metric_name = key.replace("min_", "")
        if metric_name == "prompt_contracts":
            metric_name = "prompt_contract_count"
        elif metric_name == "reasoned_drafts":
            metric_name = "reasoned_draft_count"
        elif metric_name == "ready_reasoned_drafts":
            metric_name = "ready_reasoned_draft_count"
        elif metric_name == "total_citations":
            metric_name = "total_citation_count"
        elif metric_name == "drafts_with_limitations":
            metric_name = "drafts_with_limitations_count"
        elif metric_name == "drafts_ready_for_final_gate":
            metric_name = "drafts_ready_for_final_gate_count"
        observed = num(metric_name)
        add(metric_name, observed, f">= {min_value}", observed >= min_value)

    for key, metric_name in [
        ("max_graph_summary_proof_violations", "graph_summary_proof_violation_count"),
        ("max_answer_permission_count", "answer_permission_count"),
        ("max_source_truth_mutation_allowed", "source_truth_mutation_allowed_count"),
    ]:
        max_value = int(thresholds.get(key, 0))
        observed = num(metric_name)
        add(metric_name, observed, f"<= {max_value}", observed <= max_value)

    add("contract_reasoned_draft_does_not_call_llm", report.get("reasoned_response_draft_contract", {}).get("reasoned_draft_does_not_call_llm"), "is True", report.get("reasoned_response_draft_contract", {}).get("reasoned_draft_does_not_call_llm") is True)
    add("contract_can_answer_directly", num("can_answer_directly_count"), "== 0", num("can_answer_directly_count") == 0)
    add("contract_can_prove_claims", num("can_prove_claims_count"), "== 0", num("can_prove_claims_count") == 0)
    add("postgres_write_attempt_count", num("postgres_write_attempt_count"), "== 0", num("postgres_write_attempt_count") == 0)
    add("qdrant_write_attempt_count", num("qdrant_write_attempt_count"), "== 0", num("qdrant_write_attempt_count") == 0)
    add("opensearch_write_attempt_count", num("opensearch_write_attempt_count"), "== 0", num("opensearch_write_attempt_count") == 0)
    return checks


def build_report(prompt_contract_path: str | Path, thresholds: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    source = load_json(prompt_contract_path)
    contracts = source.get("prompt_contracts") or []
    if not isinstance(contracts, list):
        contracts = []

    drafts = [build_draft(contract, i) for i, contract in enumerate(contracts, start=1) if isinstance(contract, Mapping)]

    summary = {
        "quality_status": "PASS",
        "prompt_contract_count": len(contracts),
        "reasoned_draft_count": len(drafts),
        "ready_reasoned_draft_count": sum(1 for d in drafts if d.get("reasoned_response_draft_status") == DRAFT_STATUS_READY),
        "drafts_ready_for_final_gate_count": sum(1 for d in drafts if d.get("ready_for_final_gate")),
        "audit_only_draft_count": sum(1 for d in drafts if d.get("reasoned_response_draft_status") == DRAFT_STATUS_AUDIT_ONLY),
        "total_citation_count": sum(int(d.get("citation_count") or 0) for d in drafts),
        "drafts_with_limitations_count": sum(1 for d in drafts if d.get("limitations")),
        "graph_summary_proof_violation_count": sum(int(d.get("graph_summary_proof_violation_count") or 0) for d in drafts),
        "answer_permission_count": sum(1 for d in drafts if d.get("answer_permission")),
        "can_answer_directly_count": sum(1 for d in drafts if d.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for d in drafts if d.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for d in drafts if d.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "e2e_reasoned_response_draft_status": STATUS_READY,
        "quality_status": "PASS",
        "source_llm_prompt_contract_path": str(prompt_contract_path),
        "reasoned_response_draft_contract": dict(CONTRACT),
        "summary": summary,
        "reasoned_response_drafts": drafts,
    }
    checks = quality_checks(report, thresholds)
    if not all(c["passed"] for c in checks):
        report["quality_status"] = "FAIL"
        report["summary"]["quality_status"] = "FAIL"
    report["quality_checks"] = quality_checks(report, thresholds)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net E2E Reasoned Response Draft v12",
        "",
        f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
        f"Status: `{report.get('e2e_reasoned_response_draft_status', '')}`",
        "",
        "## Contract",
        "This stage creates deterministic reasoned answer drafts from v11 prompt contracts. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
        "",
        "## Summary",
    ]
    for key in [
        "prompt_contract_count",
        "reasoned_draft_count",
        "ready_reasoned_draft_count",
        "drafts_ready_for_final_gate_count",
        "audit_only_draft_count",
        "total_citation_count",
        "drafts_with_limitations_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(["", "## Drafts"])
    for draft in report.get("reasoned_response_drafts", []):
        if not isinstance(draft, Mapping):
            continue
        content = nested_get(draft, ["draft_message", "content"], "")
        lines.append(
            f"- **{draft.get('reasoned_response_draft_status')}** `{draft.get('reasoned_response_draft_id')}` | {draft.get('query_intent')} | {draft.get('user_query')} | citations={draft.get('citation_count')}"
        )
        lines.append(f"  - {content}")
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        if isinstance(check, Mapping):
            status = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / f"{DEFAULT_OUTPUT_BASENAME}.json"
    drafts_path = out / f"{DEFAULT_OUTPUT_BASENAME}_records_v12.jsonl"
    citations_path = out / f"{DEFAULT_OUTPUT_BASENAME}_citations_v12.jsonl"
    inspect_path = out / f"{DEFAULT_OUTPUT_BASENAME}.md"

    write_json(report_path, report)
    write_jsonl(drafts_path, report.get("reasoned_response_drafts", []))
    citation_records: List[Dict[str, Any]] = []
    for draft in report.get("reasoned_response_drafts", []):
        if not isinstance(draft, Mapping):
            continue
        for citation_row in draft.get("citations", []):
            if not isinstance(citation_row, Mapping):
                continue
            row = dict(citation_row)
            row["reasoned_response_draft_id"] = draft.get("reasoned_response_draft_id")
            row["user_query"] = draft.get("user_query")
            row["query_intent"] = draft.get("query_intent")
            citation_records.append(row)
    write_jsonl(citations_path, citation_records)
    inspect_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "drafts_jsonl_path": str(drafts_path),
        "citations_jsonl_path": str(citations_path),
        "inspect_md_path": str(inspect_path),
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-path", default="")
    parser.add_argument("--min-prompt-contracts", type=int, default=1)
    parser.add_argument("--min-reasoned-drafts", type=int, default=1)
    parser.add_argument("--min-ready-reasoned-drafts", type=int, default=1)
    parser.add_argument("--min-total-citations", type=int, default=1)
    parser.add_argument("--min-drafts-with-limitations", type=int, default=1)
    parser.add_argument("--min-drafts-ready-for-final-gate", type=int, default=1)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_prompt_contracts": args.min_prompt_contracts,
        "min_reasoned_drafts": args.min_reasoned_drafts,
        "min_ready_reasoned_drafts": args.min_ready_reasoned_drafts,
        "min_total_citations": args.min_total_citations,
        "min_drafts_with_limitations": args.min_drafts_with_limitations,
        "min_drafts_ready_for_final_gate": args.min_drafts_ready_for_final_gate,
        "max_graph_summary_proof_violations": args.max_graph_summary_proof_violations,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
    }


def build_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E reasoned response draft v12")
    parser.add_argument("--llm-prompt-contract", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_common_args(parser)
    args = parser.parse_args(argv)

    report = build_report(args.llm_prompt_contract, thresholds_from_args(args))
    paths = write_report_files(report, args.output_dir)
    report.update(paths)
    # Rewrite after paths are known.
    write_json(paths["report_path"], report)

    summary = report.get("summary", {})
    print("TRACE-Net E2E Reasoned Response Draft v12")
    print(f" Status: {report.get('e2e_reasoned_response_draft_status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "prompt_contract_count",
        "reasoned_draft_count",
        "ready_reasoned_draft_count",
        "drafts_ready_for_final_gate_count",
        "total_citation_count",
        "drafts_with_limitations_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    for k, v in paths.items():
        print(f" {k}: {v}")
    return 0 if report.get("quality_status") == "PASS" else 1


def check_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E reasoned response draft v12 quality")
    add_common_args(parser)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    if not args.report_path:
        parser.error("--report-path is required")
    report = load_json(args.report_path)
    checks = quality_checks(report, thresholds_from_args(args))
    all_pass = all(c["passed"] for c in checks)
    print("TRACE-Net E2E Reasoned Response Draft v12 Quality")
    print(f" quality_status: {'PASS' if all_pass else 'FAIL'}")
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['expected']}")
    if args.write_json:
        report["quality_checks"] = checks
        report["quality_status"] = "PASS" if all_pass else "FAIL"
        if isinstance(report.get("summary"), MutableMapping):
            report["summary"]["quality_status"] = report["quality_status"]
        write_json(args.report_path, report)
    return 0 if all_pass else 1


__all__ = [
    "build_report",
    "build_draft",
    "quality_checks",
    "render_markdown",
    "write_report_files",
    "build_cli",
    "check_cli",
    "parse_source_truth_evidence_from_prompt",
]
