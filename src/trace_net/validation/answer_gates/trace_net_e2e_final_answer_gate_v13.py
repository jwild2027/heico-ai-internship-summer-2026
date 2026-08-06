"""TRACE-Net E2E Final Answer Gate v13.

This module validates deterministic reasoned response drafts before they are
allowed to be wired into a WebUI-facing final answer endpoint.  It is intentionally
non-mutating: it reads v12 draft artifacts, checks citation/source-truth safety,
and emits final-gate records plus audit summaries.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "v13"
MODULE_NAME = "trace_net_e2e_final_answer_gate_v13"
REPORT_FILENAME = "trace_net_e2e_final_answer_gate_v13.json"
RECORDS_FILENAME = "trace_net_e2e_final_answer_gate_records_v13.jsonl"
CITATIONS_FILENAME = "trace_net_e2e_final_answer_gate_citations_v13.jsonl"
INSPECT_FILENAME = "trace_net_e2e_final_answer_gate_v13.md"

DEFAULT_CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_reasoned_drafts": True,
    "final_gate_does_not_call_llm": True,
    "final_gate_does_not_rerun_retrieval": True,
    "reruns_ocr": False,
    "reruns_page_classification": False,
    "reruns_embeddings": False,
    "reruns_page_summaries": False,
    "reruns_graph_build": False,
    "reruns_table_extraction": False,
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

SUPPORTED_DRAFT_STATUSES = {
    "REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE",
    "REASONED_RESPONSE_DRAFT_READY",
}

UNSUPPORTED_DESCRIPTION_PATTERNS = [
    re.compile(r"\bis\s+(?:a|an)\s+(?:valve|bolt|screw|washer|bracket|sensor|pump|motor|filter|seal|gasket)\b", re.I),
    re.compile(r"\bused\s+to\s+(?:control|hold|attach|measure|seal|filter|pump)\b", re.I),
]

CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")


def load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")


def as_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def nested_get(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def coerce_records(payload: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key, [])
    if isinstance(value, list):
        return [dict(v) for v in value if isinstance(v, Mapping)]
    return []


def marker_numbers(content: str) -> List[int]:
    out: List[int] = []
    for match in CITATION_MARKER_RE.finditer(content or ""):
        try:
            out.append(int(match.group(1)))
        except ValueError:
            continue
    return out


def normalize_marker(citation: Mapping[str, Any], index: int) -> str:
    marker = str(citation.get("citation_marker") or f"[{index}]").strip()
    if not marker.startswith("["):
        marker = f"[{index}]"
    return marker


def evidence_value_tokens(citation: Mapping[str, Any]) -> List[str]:
    tokens: List[str] = []
    for key in ("normalized_value", "page_id", "field_name"):
        value = str(citation.get(key) or "").strip()
        if value:
            tokens.append(value)
    return tokens


def has_unsupported_description(content: str) -> bool:
    return any(pattern.search(content or "") for pattern in UNSUPPORTED_DESCRIPTION_PATTERNS)


def sentence_split(text: str) -> List[str]:
    # Keep a simple deterministic splitter. The final gate is intentionally
    # conservative but not a full NLP claim parser.
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def unsupported_sentence_count(content: str, citations: Sequence[Mapping[str, Any]]) -> int:
    """Heuristic claim coverage check.

    Counts sentences that mention extracted evidence values or page ids but do
    not carry a citation marker.  This avoids pretending to solve full formal
    claim verification while still catching the common failure mode: answer text
    names a part/page without citation support.
    """
    all_tokens: List[str] = []
    for citation in citations:
        all_tokens.extend(evidence_value_tokens(citation))
    all_tokens = [t for t in sorted(set(all_tokens), key=len, reverse=True) if len(t) >= 3]
    count = 0
    for sentence in sentence_split(content):
        if CITATION_MARKER_RE.search(sentence):
            continue
        if any(token in sentence for token in all_tokens):
            count += 1
    return count


def critique_draft(draft: Mapping[str, Any], ordinal: int) -> Dict[str, Any]:
    draft_message = draft.get("draft_message") if isinstance(draft.get("draft_message"), Mapping) else {}
    content = str(draft_message.get("content") or draft.get("draft_text") or "")
    citations = [dict(c) for c in draft.get("citations", []) if isinstance(c, Mapping)]
    limitations = list(draft.get("limitations", []) if isinstance(draft.get("limitations"), list) else [])

    blocker_reasons: List[str] = []
    warning_reasons: List[str] = []

    status = str(draft.get("reasoned_response_draft_status") or "")
    if status not in SUPPORTED_DRAFT_STATUSES:
        blocker_reasons.append(f"draft_not_ready:{status or 'missing'}")

    if not content.strip():
        blocker_reasons.append("missing_draft_content")

    if not citations:
        blocker_reasons.append("missing_citations")

    citation_ready_count = sum(1 for c in citations if c.get("citation_ready") is True)
    source_trace_ready_count = sum(1 for c in citations if c.get("source_trace_ready") is True)
    source_truth_authority_count = sum(1 for c in citations if c.get("answer_authority") == "source_truth_evidence_only")

    if citation_ready_count != len(citations):
        blocker_reasons.append("not_all_citations_ready")
    if source_trace_ready_count != len(citations):
        blocker_reasons.append("not_all_citations_source_trace_ready")
    if source_truth_authority_count != len(citations):
        blocker_reasons.append("not_all_citations_source_truth_authority")

    marker_nums = set(marker_numbers(content))
    expected_nums = set(range(1, len(citations) + 1))
    marker_count = len(marker_nums)
    if not marker_nums:
        blocker_reasons.append("draft_has_no_citation_markers")
    unknown_markers = sorted(n for n in marker_nums if n not in expected_nums)
    if unknown_markers:
        blocker_reasons.append("draft_has_unknown_citation_markers:" + ",".join(map(str, unknown_markers)))

    unsupported_claim_count = unsupported_sentence_count(content, citations)
    if unsupported_claim_count:
        blocker_reasons.append(f"unsupported_evidence_mentions:{unsupported_claim_count}")

    if has_unsupported_description(content):
        blocker_reasons.append("possible_invented_physical_part_description")

    graph_summary_proof_violation_count = int(draft.get("graph_summary_proof_violation_count") or 0)
    # Extra lexical guard: an answer can mention limitations, but graph/summary should
    # not appear as proof language in final text.
    lower_content = content.lower()
    if re.search(r"\b(graph|summary|community|qdrant|vector|route metadata)\b", lower_content):
        if not re.search(r"not enough|does not|limitation|insufficient", lower_content):
            graph_summary_proof_violation_count += 1

    if graph_summary_proof_violation_count:
        blocker_reasons.append(f"graph_summary_proof_violation:{graph_summary_proof_violation_count}")

    if not limitations:
        warning_reasons.append("missing_limitations")

    if draft.get("answer_permission") not in (False, 0, None):
        blocker_reasons.append("answer_permission_not_blocked")
    if draft.get("can_answer_directly") not in (False, 0, None):
        blocker_reasons.append("can_answer_directly_not_blocked")
    if draft.get("can_prove_claims") not in (False, 0, None):
        blocker_reasons.append("can_prove_claims_not_blocked")
    if draft.get("source_truth_mutation_allowed") not in (False, 0, None):
        blocker_reasons.append("source_truth_mutation_allowed")

    passed = not blocker_reasons
    final_status = "FINAL_ANSWER_GATE_PASSED" if passed else "FINAL_ANSWER_GATE_BLOCKED"

    final_answer = {
        "role": "assistant",
        "content": content.strip(),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "final_answer_gate_id": f"final_answer_gate_v13_{ordinal:04d}",
        "reasoned_response_draft_id": draft.get("reasoned_response_draft_id", f"reasoned_response_draft_unknown_{ordinal:04d}"),
        "prompt_contract_id": draft.get("prompt_contract_id"),
        "context_pack_id": draft.get("context_pack_id"),
        "user_query": draft.get("user_query", ""),
        "query_intent": draft.get("query_intent", ""),
        "final_answer_gate_status": final_status,
        "final_gate_passed": passed,
        "ready_for_webui_endpoint": passed,
        "ready_for_final_answer_output": passed,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "response_is_final_gated_draft": True,
        "citation_count": len(citations),
        "citation_marker_count": marker_count,
        "citation_ready_count": citation_ready_count,
        "source_trace_ready_citation_count": source_trace_ready_count,
        "source_truth_citation_count": source_truth_authority_count,
        "unsupported_claim_count": unsupported_claim_count,
        "graph_summary_proof_violation_count": graph_summary_proof_violation_count,
        "limitation_count": len(limitations),
        "has_limitations": bool(limitations),
        "blocker_count": len(blocker_reasons),
        "warning_count": len(warning_reasons),
        "blockers": blocker_reasons,
        "warnings": warning_reasons,
        "final_answer_message": final_answer,
        "citations": citations,
        "limitations": limitations,
        "page_ids": list(draft.get("page_ids", []) if isinstance(draft.get("page_ids"), list) else []),
        "field_counts": dict(draft.get("field_counts", {}) if isinstance(draft.get("field_counts"), Mapping) else {}),
        "final_gate_policy": {
            "cite_every_factual_claim": True,
            "uses_source_truth_evidence_only_for_claims": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "guidance_used_as_context_only": True,
            "unsupported_claim_policy": "block_or_downgrade_to_audit_output",
        },
        "contract": dict(DEFAULT_CONTRACT),
    }


def quality_check(
    report: Mapping[str, Any],
    *,
    min_reasoned_drafts: int = 0,
    min_final_gates: int = 0,
    min_passed_final_gates: int = 0,
    min_citation_supported_answers: int = 0,
    min_total_citations: int = 0,
    min_final_answers_ready_for_webui: int = 0,
    min_answers_with_limitations: int = 0,
    max_unsupported_claim_count: int = 0,
    max_graph_summary_proof_violations: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> Tuple[str, List[Dict[str, Any]]]:
    summary = dict(report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {})
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("quality_status", report.get("quality_status", "PASS"), "== PASS", report.get("quality_status", "PASS") == "PASS")
    add("reasoned_draft_count", summary.get("reasoned_draft_count", 0), f">= {min_reasoned_drafts}", int(summary.get("reasoned_draft_count", 0)) >= min_reasoned_drafts)
    add("final_gate_count", summary.get("final_gate_count", 0), f">= {min_final_gates}", int(summary.get("final_gate_count", 0)) >= min_final_gates)
    add("passed_final_gate_count", summary.get("passed_final_gate_count", 0), f">= {min_passed_final_gates}", int(summary.get("passed_final_gate_count", 0)) >= min_passed_final_gates)
    add("citation_supported_answer_count", summary.get("citation_supported_answer_count", 0), f">= {min_citation_supported_answers}", int(summary.get("citation_supported_answer_count", 0)) >= min_citation_supported_answers)
    add("total_citation_count", summary.get("total_citation_count", 0), f">= {min_total_citations}", int(summary.get("total_citation_count", 0)) >= min_total_citations)
    add("final_answers_ready_for_webui_count", summary.get("final_answers_ready_for_webui_count", 0), f">= {min_final_answers_ready_for_webui}", int(summary.get("final_answers_ready_for_webui_count", 0)) >= min_final_answers_ready_for_webui)
    add("answers_with_limitations_count", summary.get("answers_with_limitations_count", 0), f">= {min_answers_with_limitations}", int(summary.get("answers_with_limitations_count", 0)) >= min_answers_with_limitations)
    add("unsupported_claim_count", summary.get("unsupported_claim_count", 0), f"<= {max_unsupported_claim_count}", int(summary.get("unsupported_claim_count", 0)) <= max_unsupported_claim_count)
    add("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), f"<= {max_graph_summary_proof_violations}", int(summary.get("graph_summary_proof_violation_count", 0)) <= max_graph_summary_proof_violations)
    add("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {max_answer_permission_count}", int(summary.get("answer_permission_count", 0)) <= max_answer_permission_count)
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {max_source_truth_mutation_allowed}", int(summary.get("source_truth_mutation_allowed_count", 0)) <= max_source_truth_mutation_allowed)
    add("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", int(summary.get("can_answer_directly_count", 0)) == 0)
    add("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", int(summary.get("can_prove_claims_count", 0)) == 0)
    add("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", int(summary.get("postgres_write_attempt_count", 0)) == 0)
    add("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", int(summary.get("qdrant_write_attempt_count", 0)) == 0)
    add("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", int(summary.get("opensearch_write_attempt_count", 0)) == 0)
    if require_no_answer_permission:
        add("require_no_answer_permission", summary.get("answer_permission_count", 0), "== 0", int(summary.get("answer_permission_count", 0)) == 0)

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return status, checks


def build_final_answer_gate_report(
    *,
    reasoned_response_draft_path: str | Path,
    output_dir: str | Path,
    quality_args: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    source = load_json(reasoned_response_draft_path)
    drafts = coerce_records(source, "reasoned_response_drafts")
    gates = [critique_draft(draft, i + 1) for i, draft in enumerate(drafts)]

    citation_records: List[Dict[str, Any]] = []
    for gate in gates:
        for citation in gate.get("citations", []):
            record = dict(citation)
            record.update({
                "final_answer_gate_id": gate["final_answer_gate_id"],
                "reasoned_response_draft_id": gate.get("reasoned_response_draft_id"),
                "user_query": gate.get("user_query"),
                "query_intent": gate.get("query_intent"),
            })
            citation_records.append(record)

    summary = {
        "quality_status": "PASS",
        "reasoned_draft_count": len(drafts),
        "final_gate_count": len(gates),
        "passed_final_gate_count": sum(1 for g in gates if g.get("final_gate_passed")),
        "blocked_final_gate_count": sum(1 for g in gates if not g.get("final_gate_passed")),
        "citation_supported_answer_count": sum(1 for g in gates if g.get("citation_count", 0) > 0 and g.get("citation_marker_count", 0) > 0 and g.get("final_gate_passed")),
        "total_citation_count": sum(int(g.get("citation_count", 0)) for g in gates),
        "answers_with_limitations_count": sum(1 for g in gates if g.get("has_limitations")),
        "final_answers_ready_for_webui_count": sum(1 for g in gates if g.get("ready_for_webui_endpoint")),
        "unsupported_claim_count": sum(int(g.get("unsupported_claim_count", 0)) for g in gates),
        "graph_summary_proof_violation_count": sum(int(g.get("graph_summary_proof_violation_count", 0)) for g in gates),
        "blocker_count": sum(int(g.get("blocker_count", 0)) for g in gates),
        "warning_count": sum(int(g.get("warning_count", 0)) for g in gates),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "E2E_FINAL_ANSWER_GATE_BUILT",
        "e2e_final_answer_gate_status": "E2E_FINAL_ANSWER_GATE_READY_FOR_WEBUI_ENDPOINT" if summary["blocked_final_gate_count"] == 0 else "E2E_FINAL_ANSWER_GATE_NEEDS_REPAIR",
        "quality_status": "PASS",
        "source_reasoned_response_draft_path": str(reasoned_response_draft_path),
        "final_answer_gate_contract": dict(DEFAULT_CONTRACT),
        "final_answer_gates": gates,
        "citation_records": citation_records,
        "summary": summary,
    }

    if quality_args is not None:
        quality_status, checks = quality_check(report, **dict(quality_args))
        report["quality_status"] = quality_status
        report["summary"]["quality_status"] = quality_status
        report["quality_checks"] = checks
    else:
        report["quality_checks"] = []

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / REPORT_FILENAME
    records_path = out / RECORDS_FILENAME
    citations_path = out / CITATIONS_FILENAME
    inspect_path = out / INSPECT_FILENAME
    report["report_path"] = str(report_path)
    report["records_jsonl_path"] = str(records_path)
    report["citations_jsonl_path"] = str(citations_path)
    report["inspect_md_path"] = str(inspect_path)

    write_json(report_path, report)
    write_jsonl(records_path, gates)
    write_jsonl(citations_path, citation_records)
    inspect_path.write_text(render_inspect_markdown(report), encoding="utf-8")
    return report


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    summary = dict(report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {})
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Final Answer Gate v13")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**")
    lines.append(f"Status: `{report.get('e2e_final_answer_gate_status', report.get('status', 'UNKNOWN'))}`")
    lines.append("")
    lines.append("## Contract")
    lines.append("This stage validates reasoned response drafts before WebUI final-answer integration. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.")
    lines.append("")
    lines.append("## Summary")
    for key in [
        "reasoned_draft_count",
        "final_gate_count",
        "passed_final_gate_count",
        "blocked_final_gate_count",
        "citation_supported_answer_count",
        "total_citation_count",
        "answers_with_limitations_count",
        "final_answers_ready_for_webui_count",
        "unsupported_claim_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.append("")
    lines.append("## Final-gated answers")
    for gate in report.get("final_answer_gates", []):
        if not isinstance(gate, Mapping):
            continue
        content = str(nested_get(gate, ["final_answer_message", "content"], "")).replace("\n", " ")
        if len(content) > 260:
            content = content[:257] + "..."
        lines.append(f"- **{gate.get('final_answer_gate_status')}** `{gate.get('final_answer_gate_id')}` | {gate.get('query_intent')} | {gate.get('user_query')} | citations={gate.get('citation_count', 0)}")
        lines.append(f"  - {content}")
    lines.append("")
    lines.append("## Quality checks")
    for check in report.get("quality_checks", []):
        if not isinstance(check, Mapping):
            continue
        label = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {label} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E final answer gate v13")
    parser.add_argument("--reasoned-response-draft", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-reasoned-drafts", type=int, default=0)
    parser.add_argument("--min-final-gates", type=int, default=0)
    parser.add_argument("--min-passed-final-gates", type=int, default=0)
    parser.add_argument("--min-citation-supported-answers", type=int, default=0)
    parser.add_argument("--min-total-citations", type=int, default=0)
    parser.add_argument("--min-final-answers-ready-for-webui", type=int, default=0)
    parser.add_argument("--min-answers-with-limitations", type=int, default=0)
    parser.add_argument("--max-unsupported-claim-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def quality_args_from_namespace(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_reasoned_drafts": args.min_reasoned_drafts,
        "min_final_gates": args.min_final_gates,
        "min_passed_final_gates": args.min_passed_final_gates,
        "min_citation_supported_answers": args.min_citation_supported_answers,
        "min_total_citations": args.min_total_citations,
        "min_final_answers_ready_for_webui": args.min_final_answers_ready_for_webui,
        "min_answers_with_limitations": args.min_answers_with_limitations,
        "max_unsupported_claim_count": args.max_unsupported_claim_count,
        "max_graph_summary_proof_violations": args.max_graph_summary_proof_violations,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_final_answer_gate_report(
        reasoned_response_draft_path=args.reasoned_response_draft,
        output_dir=args.output_dir,
        quality_args=quality_args_from_namespace(args) if args.quality else None,
    )
    summary = report["summary"]
    print("TRACE-Net E2E Final Answer Gate v13")
    print(f" Status: {report['e2e_final_answer_gate_status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "reasoned_draft_count",
        "final_gate_count",
        "passed_final_gate_count",
        "citation_supported_answer_count",
        "total_citation_count",
        "answers_with_limitations_count",
        "final_answers_ready_for_webui_count",
        "unsupported_claim_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {report['report_path']}")
    print(f" records_jsonl_path: {report['records_jsonl_path']}")
    print(f" citations_jsonl_path: {report['citations_jsonl_path']}")
    print(f" inspect_md_path: {report['inspect_md_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
