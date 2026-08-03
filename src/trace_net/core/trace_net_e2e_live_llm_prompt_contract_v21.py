from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v21"
MODULE = "trace_net_e2e_live_llm_prompt_contract_v21"
STATUS_READY = "E2E_LIVE_LLM_PROMPT_CONTRACT_READY_FOR_LLM_DRAFT"
STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_PROMPT_CONTRACT_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

SYSTEM_MESSAGE = """You are the TRACE-Net answer writer. Write only from the provided TRACE-Net context pack. Source-truth evidence may support factual claims. Graph/Leiden guidance, v2 summaries, route metadata, vector hints, and aggregation metadata are guidance only and are not proof authority. Cite every factual claim with source-truth citations. If evidence is capped or incomplete, state that limitation. Do not invent physical part descriptions, missing relationships, page contents, or citations. Do not mutate source truth."""

ALLOWED_ROLES = {"system", "user", "assistant"}


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


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first_list(obj: Any, candidate_keys: Sequence[str]) -> List[Any]:
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, Mapping):
        return []
    for key in candidate_keys:
        value = obj.get(key)
        if isinstance(value, list):
            return value
    # Search one level down for common wrappers.
    for wrapper in ("report", "payload", "data"):
        nested = obj.get(wrapper)
        if isinstance(nested, Mapping):
            found = _first_list(nested, candidate_keys)
            if found:
                return found
    return []


def _truthy_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "pass", "ready"}
    return bool(value)


def _get_path(obj: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _context_packs(data: Any) -> List[Mapping[str, Any]]:
    rows = _first_list(
        data,
        [
            "context_packs",
            "executed_plan_context_packs",
            "context_pack_records",
            "packs",
            "records",
        ],
    )
    return [r for r in rows if isinstance(r, Mapping)]


def _evaluations(data: Any) -> List[Mapping[str, Any]]:
    rows = _first_list(
        data,
        [
            "self_rag_crag_records",
            "self_rag_evaluations",
            "live_self_rag_crag_evaluations",
            "evaluations",
            "records",
            "context_evaluations",
        ],
    )
    return [r for r in rows if isinstance(r, Mapping)]


def _pack_id(pack: Mapping[str, Any], fallback_index: int = 0) -> str:
    return str(
        pack.get("context_pack_id")
        or pack.get("executed_plan_context_pack_id")
        or pack.get("pack_id")
        or pack.get("query_plan_id")
        or f"context_pack_v19_{fallback_index:04d}"
    )


def _eval_pack_id(row: Mapping[str, Any]) -> Optional[str]:
    value = (
        row.get("context_pack_id")
        or row.get("executed_plan_context_pack_id")
        or row.get("pack_id")
        or row.get("query_plan_id")
    )
    return str(value) if value is not None else None


def _evaluation_index(evals: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for i, row in enumerate(evals, start=1):
        key = _eval_pack_id(row) or f"context_pack_v19_{i:04d}"
        out[key] = row
    return out


def _evidence_items(pack: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    evidence_box = pack.get("evidence_box") if isinstance(pack.get("evidence_box"), Mapping) else {}
    candidates: List[Any] = []
    for key in ("items", "source_truth_evidence", "records", "evidence", "source_truth_records"):
        value = evidence_box.get(key) if isinstance(evidence_box, Mapping) else None
        if isinstance(value, list):
            candidates = value
            break
    if not candidates:
        for key in ("source_truth_evidence", "evidence", "evidence_records"):
            value = pack.get(key)
            if isinstance(value, list):
                candidates = value
                break
    return [x for x in candidates if isinstance(x, Mapping)]


def _graph_guidance_items(pack: Mapping[str, Any]) -> List[Any]:
    guidance_box = pack.get("guidance_box") if isinstance(pack.get("guidance_box"), Mapping) else {}
    items: List[Any] = []
    for key in ("graph_guidance", "leiden_guidance", "graph_leiden_guidance", "community_guidance"):
        value = guidance_box.get(key) if isinstance(guidance_box, Mapping) else None
        if isinstance(value, list):
            items.extend(value)
        elif value:
            items.append(value)
    if not items:
        for key in ("graph_guidance", "leiden_guidance"):
            value = pack.get(key)
            if isinstance(value, list):
                items.extend(value)
            elif value:
                items.append(value)
    return items


def _summary_guidance_items(pack: Mapping[str, Any]) -> List[Any]:
    guidance_box = pack.get("guidance_box") if isinstance(pack.get("guidance_box"), Mapping) else {}
    items: List[Any] = []
    for key in ("v2_summary_guidance", "page_summary_guidance", "summary_guidance", "page_context_v2_guidance"):
        value = guidance_box.get(key) if isinstance(guidance_box, Mapping) else None
        if isinstance(value, list):
            items.extend(value)
        elif value:
            items.append(value)
    if not items:
        for key in ("v2_summary_guidance", "summary_guidance"):
            value = pack.get(key)
            if isinstance(value, list):
                items.extend(value)
            elif value:
                items.append(value)
    return items


def _aggregation_box(pack: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("aggregation_box", "aggregation", "cap_disclosure", "capping_metadata"):
        value = pack.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _answer_rules(pack: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("answer_rules_box", "answer_rules", "rules_box"):
        value = pack.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _evidence_page(item: Mapping[str, Any]) -> str:
    return str(item.get("page") or item.get("page_id") or item.get("source_page_id") or "unknown_page")


def _evidence_field(item: Mapping[str, Any]) -> str:
    return str(item.get("field") or item.get("field_name") or item.get("source_field") or "unknown_field")


def _evidence_value(item: Mapping[str, Any]) -> str:
    return str(item.get("value") or item.get("normalized_value") or item.get("text") or item.get("raw_value") or "")


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _explicit_query_terms(user_query: str) -> List[str]:
    """Extract high-signal explicit query terms used to separate exact hits from nearby context."""
    q = str(user_query or "")
    terms: List[str] = []
    # Part/manual/reference-like IDs, e.g. 120-36834-509 or 25-21-00.
    terms.extend(re.findall(r"\b[A-Z]*\d{2,4}(?:-\d{2,6}){1,4}[A-Z]*\b", q, flags=re.IGNORECASE))
    # Query after common exact-search prefixes is also a high-signal phrase.
    m = re.search(r"(?:search\s+table\s+text|find\s+text|search\s+text)\s+(.+)$", q, flags=re.IGNORECASE)
    if m:
        phrase = m.group(1).strip(" .:;\"'")
        if len(phrase) >= 4:
            terms.append(phrase)
    # Keep unique normalized terms while preserving readable values.
    seen = set()
    out: List[str] = []
    for term in terms:
        nt = _norm_text(term)
        if nt and nt not in seen:
            seen.add(nt)
            out.append(str(term))
    return out


def _is_direct_evidence_for_query(item: Mapping[str, Any], user_query: str, all_items: Sequence[Mapping[str, Any]]) -> bool:
    """True for evidence that directly matches explicit query targets.

    If the query is broad and has no explicit target value, every unique source-truth item
    remains direct evidence. If the query has exact target terms, only matching values are
    direct evidence; other records are nearby source-truth context for cautious use.
    """
    terms = _explicit_query_terms(user_query)
    if not terms:
        return True
    value = _norm_text(_evidence_value(item))
    field = _norm_text(_evidence_field(item))
    for term in terms:
        nt = _norm_text(term)
        # Direct evidence must match the explicit query target. Avoid treating tiny
        # OCR fragments such as "i" or "|" as direct just because they appear
        # inside a longer query phrase.
        if nt and (nt == value or nt in value):
            return True
        if nt and len(value) >= 4 and value in nt:
            return True
    # Field-aware broad query fallback, e.g. "covered part numbers".
    qn = _norm_text(user_query)
    if "covered part" in qn and "covered_part_number" in field:
        return True
    return False


def _evidence_key(item: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (_evidence_page(item), _evidence_field(item), _norm_text(_evidence_value(item)))


def _dedupe_and_classify_evidence(
    items: Sequence[Mapping[str, Any]],
    user_query: str,
    *,
    max_evidence_items: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int]:
    """Deduplicate evidence and split into direct evidence vs nearby context."""
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str, str]] = []
    for item in items:
        key = _evidence_key(item)
        item_occurrence_count = int(item.get("occurrence_count") or 1)
        if key not in grouped:
            copy = dict(item)
            copy["occurrence_count"] = item_occurrence_count
            grouped[key] = copy
            order.append(key)
        else:
            grouped[key]["occurrence_count"] = int(grouped[key].get("occurrence_count", 1)) + item_occurrence_count

    unique_items = [grouped[k] for k in order]
    direct: List[Dict[str, Any]] = []
    nearby: List[Dict[str, Any]] = []
    for item in unique_items:
        if _is_direct_evidence_for_query(item, user_query, unique_items):
            direct.append(item)
        else:
            item = dict(item)
            item["context_role"] = "nearby_source_truth_context_not_direct_query_match"
            nearby.append(item)

    # Allocate citation IDs after dedupe so citations stay contiguous and reliable.
    bounded_direct = direct[:max_evidence_items]
    remaining = max(0, max_evidence_items - len(bounded_direct))
    bounded_nearby = nearby[:remaining]
    all_bounded = bounded_direct + bounded_nearby
    for idx, item in enumerate(all_bounded, start=1):
        item["citation_id"] = f"[{idx}]"
    bounded_direct = all_bounded[: len(bounded_direct)]
    bounded_nearby = all_bounded[len(bounded_direct) :]
    original_record_count = sum(int(item.get("occurrence_count") or 1) for item in unique_items)
    duplicate_count = max(0, original_record_count - len(unique_items))
    return bounded_direct, bounded_nearby, duplicate_count, len(unique_items)


def _safe_evidence_line(item: Mapping[str, Any], idx: int) -> str:
    page = _evidence_page(item)
    field = _evidence_field(item)
    value = _evidence_value(item)
    citation = item.get("citation") or item.get("citation_id") or f"[{idx}]"
    occurrence_count = int(item.get("occurrence_count") or 1)
    suffix = f" occurrence_count={occurrence_count}" if occurrence_count > 1 else ""
    return f"- {citation} page={page} field={field} value={value}{suffix}"


def _compact_json(value: Any, max_chars: int = 2400) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        return json.dumps(
            {
                "truncated_for_prompt_contract": True,
                "original_character_count": len(text),
                "preview": text[:max_chars].rstrip(),
            },
            ensure_ascii=False,
            indent=2,
        )
    return text


def _compact_aggregation_json(value: Mapping[str, Any], max_group_items: int = 12) -> str:
    if not isinstance(value, Mapping):
        return _compact_json(value)
    preserved: Dict[str, Any] = {}
    for key in (
        "total_match_count",
        "returned_match_count",
        "result_was_capped",
        "more_results_available",
        "high_degree_node_detected",
        "cap_reason",
        "ranking_method",
        "available_drilldowns",
    ):
        if key in value:
            preserved[key] = value[key]
    group_counts = value.get("group_counts")
    if isinstance(group_counts, Mapping):
        compact_groups: Dict[str, Any] = {}
        truncated_groups: List[str] = []
        for group_name, counts in group_counts.items():
            if isinstance(counts, Mapping):
                items = list(counts.items())
                compact_groups[str(group_name)] = dict(items[:max_group_items])
                if len(items) > max_group_items:
                    truncated_groups.append(str(group_name))
            else:
                compact_groups[str(group_name)] = counts
        preserved["group_counts"] = compact_groups
        if truncated_groups:
            preserved["aggregation_metadata_truncated"] = True
            preserved["truncated_fields"] = truncated_groups
    return json.dumps(preserved or value, ensure_ascii=False, indent=2)


def _normalize_evaluation_for_prompt(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    if not evaluation:
        return {
            "self_rag_status": "CONTEXT_STATUS_NOT_SUPPLIED",
            "crag_status": "CRAG_STATUS_NOT_SUPPLIED",
            "ready_for_llm_prompt": True,
            "retry_required": False,
            "requires_cap_disclosure": False,
            "limitations": [],
        }
    agg = evaluation.get("aggregation_or_cap_disclosure") if isinstance(evaluation.get("aggregation_or_cap_disclosure"), Mapping) else {}
    return {
        "self_rag_record_id": evaluation.get("self_rag_crag_record_id") or evaluation.get("record_id"),
        "self_rag_status": evaluation.get("self_rag_status") or evaluation.get("context_status") or evaluation.get("status"),
        "crag_status": evaluation.get("crag_status") or evaluation.get("crag_plan_status"),
        "ready_for_llm_prompt": _truthy_bool(
            evaluation.get("ready_for_llm_prompt", evaluation.get("ready_for_llm", evaluation.get("context_ready_for_llm", True)))
        ),
        "retry_required": _truthy_bool(evaluation.get("retry_required", evaluation.get("needs_crag_retry", False))),
        "audit_only": _truthy_bool(evaluation.get("audit_only", False)),
        "requires_cap_disclosure": bool(
            (isinstance(agg, Mapping) and (agg.get("result_was_capped") or agg.get("more_results_available") or agg.get("high_degree_node_detected")))
            or evaluation.get("requires_cap_disclosure")
        ),
        "limitations": evaluation.get("limitations") or [],
        "crag_actions": evaluation.get("crag_actions") or [],
    }


def _format_context_message(pack: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str:
    user_query = str(pack.get("user_query") or pack.get("query") or pack.get("original_query") or evaluation.get("user_query") or "")
    evidence = _evidence_items(pack)
    graph = _graph_guidance_items(pack)
    summaries = _summary_guidance_items(pack)
    aggregation = _aggregation_box(pack)
    rules = _answer_rules(pack)
    direct_evidence, nearby_evidence, duplicate_count, unique_count = _dedupe_and_classify_evidence(
        evidence, user_query, max_evidence_items=int(pack.get("_max_evidence_items") or 12)
    )

    lines: List[str] = []
    lines.append("TRACE-NET CONTEXT PACK")
    lines.append("")
    lines.append("SOURCE-TRUTH EVIDENCE (direct proof authority; cite these for factual claims):")
    if direct_evidence:
        for i, item in enumerate(direct_evidence, start=1):
            lines.append(_safe_evidence_line(item, i))
    else:
        lines.append("- None available. Do not answer factual claims from guidance-only material.")

    lines.append("")
    lines.append("NEARBY SOURCE-TRUTH CONTEXT (source-truth records, but not direct query matches; use cautiously):")
    if nearby_evidence:
        start = len(direct_evidence) + 1
        for offset, item in enumerate(nearby_evidence, start=start):
            lines.append(_safe_evidence_line(item, offset))
    else:
        lines.append("- None")

    lines.append("")
    lines.append("EVIDENCE DEDUPLICATION / HYGIENE:")
    lines.append(_compact_json({
        "original_evidence_record_count": unique_count + duplicate_count,
        "unique_evidence_record_count": unique_count,
        "collapsed_duplicate_record_count": duplicate_count,
        "direct_evidence_count": len(direct_evidence),
        "nearby_context_count": len(nearby_evidence),
        "citation_numbering_after_deduplication": True,
    }, max_chars=1200))

    lines.append("")
    lines.append("GRAPH / LEIDEN GUIDANCE (navigation only; not proof):")
    if graph:
        lines.append(_compact_json(graph, max_chars=1600))
    else:
        lines.append("- None")

    lines.append("")
    lines.append("V2 SUMMARY GUIDANCE (meaning/compression only; not proof):")
    if summaries:
        lines.append(_compact_json(summaries, max_chars=1600))
    else:
        lines.append("- None")

    lines.append("")
    lines.append("AGGREGATION / CAPPING METADATA:")
    if aggregation:
        lines.append(_compact_aggregation_json(aggregation))
    else:
        lines.append("- No cap metadata supplied.")

    lines.append("")
    lines.append("SELF-RAG / CRAG STATUS:")
    lines.append(_compact_json(_normalize_evaluation_for_prompt(evaluation), max_chars=1800))

    lines.append("")
    lines.append("ANSWER RULES:")
    if rules:
        lines.append(_compact_json(rules, max_chars=1200))
    else:
        lines.append("- Cite every factual claim from source-truth evidence only.")
        lines.append("- Graph/Leiden/v2 summaries are guidance only.")
        lines.append("- Disclose capped or incomplete results.")
        lines.append("- State limitations instead of inventing missing facts.")
    return "\n".join(lines)


def _eval_ready_for_llm(evaluation: Mapping[str, Any]) -> bool:
    if not evaluation:
        return True
    for key in ("ready_for_llm_prompt", "ready_for_llm", "context_ready_for_llm", "ready", "is_ready_for_llm"):
        if key in evaluation:
            return _truthy_bool(evaluation.get(key))
    status = str(
        evaluation.get("context_status")
        or evaluation.get("self_rag_status")
        or evaluation.get("status")
        or evaluation.get("classification")
        or ""
    ).upper()
    if not status:
        return True
    return any(token in status for token in ("READY_FOR_LLM", "READY_WITH_CAP_DISCLOSURE", "CONTEXT_READY")) and "RETRY" not in status and "BLOCK" not in status


def _crag_no_retry(evaluation: Mapping[str, Any]) -> bool:
    if not evaluation:
        return True
    for key in ("retry_required", "needs_crag_retry", "crag_retry_required"):
        if key in evaluation:
            return not _truthy_bool(evaluation.get(key))
    status = str(evaluation.get("crag_status") or evaluation.get("crag_plan_status") or evaluation.get("status") or "").upper()
    if not status:
        return True
    return "RETRY" not in status or "NO_RETRY" in status


def _cap_disclosure_present(pack: Mapping[str, Any]) -> bool:
    agg = _aggregation_box(pack)
    if not agg:
        return False
    if any(k in agg for k in ("total_match_count", "returned_match_count", "result_was_capped", "more_results_available", "drilldown_options")):
        return True
    return bool(agg)


def _violates_guidance_authority(items: Sequence[Any]) -> bool:
    for item in items:
        if isinstance(item, Mapping):
            auth = str(item.get("authority") or item.get("proof_authority") or item.get("answer_authority") or "").lower()
            if auth in {"proof", "source_truth", "proof_authority", "true"}:
                return True
            if item.get("can_prove_claims") is True or item.get("proof_authority") is True:
                return True
    return False


def build_prompt_contracts(
    context_pack_report: Mapping[str, Any],
    self_rag_crag_report: Mapping[str, Any],
    *,
    max_evidence_items: int = 12,
) -> List[Dict[str, Any]]:
    packs = _context_packs(context_pack_report)
    evals = _evaluation_index(_evaluations(self_rag_crag_report))
    contracts: List[Dict[str, Any]] = []

    for idx, pack in enumerate(packs, start=1):
        pack_id = _pack_id(pack, idx)
        evaluation = evals.get(pack_id, {})
        raw_evidence = _evidence_items(pack)
        direct_evidence, nearby_evidence, duplicate_count, unique_evidence_count = _dedupe_and_classify_evidence(
            raw_evidence,
            str(pack.get("user_query") or pack.get("query") or pack.get("original_query") or evaluation.get("user_query") or ""),
            max_evidence_items=max_evidence_items,
        )
        evidence = direct_evidence + nearby_evidence
        graph = _graph_guidance_items(pack)
        summaries = _summary_guidance_items(pack)
        aggregation = _aggregation_box(pack)
        rules = _answer_rules(pack)
        user_query = str(pack.get("user_query") or pack.get("query") or pack.get("original_query") or evaluation.get("user_query") or "")
        if not user_query:
            user_query = f"TRACE-Net query for {pack_id}"

        graph_violation = _violates_guidance_authority(graph)
        summary_violation = _violates_guidance_authority(summaries)
        has_evidence = bool(evidence)
        ready_for_llm = has_evidence and _eval_ready_for_llm(evaluation) and _crag_no_retry(evaluation) and not graph_violation and not summary_violation

        # Use a copy with bounded/deduplicated evidence so context stays compact and citation-safe.
        bounded_pack = dict(pack)
        bounded_pack["_max_evidence_items"] = max_evidence_items
        ev_box = dict(bounded_pack.get("evidence_box") or {})
        ev_box["items"] = evidence
        ev_box["item_count"] = len(evidence)
        ev_box["direct_source_truth_evidence_count"] = len(direct_evidence)
        ev_box["nearby_source_truth_context_count"] = len(nearby_evidence)
        ev_box["unique_evidence_record_count"] = unique_evidence_count
        ev_box["collapsed_duplicate_record_count"] = duplicate_count
        bounded_pack["evidence_box"] = ev_box

        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_query},
            {"role": "user", "content": _format_context_message(bounded_pack, evaluation)},
        ]

        contract = {
            "prompt_contract_id": f"llm_prompt_contract_v21_{idx:04d}",
            "context_pack_id": pack_id,
            "user_query": user_query,
            "prompt_contract_status": "PROMPT_CONTRACT_READY_FOR_LLM_DRAFT" if ready_for_llm else "PROMPT_CONTRACT_NEEDS_REPAIR_OR_RETRY",
            "ready_for_llm_draft": ready_for_llm,
            "message_count": len(messages),
            "messages": messages,
            "evidence_item_count": len(evidence),
            "direct_source_truth_evidence_count": len(direct_evidence),
            "nearby_source_truth_context_count": len(nearby_evidence),
            "unique_evidence_record_count": unique_evidence_count,
            "collapsed_duplicate_record_count": duplicate_count,
            "has_source_truth_evidence": has_evidence,
            "has_graph_guidance": bool(graph),
            "has_v2_summary_guidance": bool(summaries),
            "has_aggregation_or_cap_disclosure": _cap_disclosure_present(pack),
            "has_answer_rules": bool(rules) or True,
            "self_rag_ready": _eval_ready_for_llm(evaluation),
            "crag_no_retry": _crag_no_retry(evaluation),
            "graph_proof_authority_violation": graph_violation,
            "summary_proof_authority_violation": summary_violation,
            "safety_contract": {
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
            },
            "authority_contract": {
                "source_truth_evidence_is_proof": True,
                "graph_leiden_guidance_is_proof": False,
                "v2_summary_guidance_is_proof": False,
                "aggregation_metadata_is_proof": False,
                "final_gate_required_after_llm_draft": True,
            },
        }
        contracts.append(contract)
    return contracts


def summarize_contracts(contracts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total_messages = sum(int(c.get("message_count") or len(c.get("messages") or [])) for c in contracts)
    return {
        "context_pack_count": len(contracts),
        "prompt_contract_count": len(contracts),
        "ready_prompt_contract_count": sum(1 for c in contracts if c.get("ready_for_llm_draft")),
        "total_prompt_message_count": total_messages,
        "contracts_with_source_truth_evidence_count": sum(1 for c in contracts if c.get("has_source_truth_evidence")),
        "contracts_with_graph_guidance_count": sum(1 for c in contracts if c.get("has_graph_guidance")),
        "contracts_with_v2_summary_guidance_count": sum(1 for c in contracts if c.get("has_v2_summary_guidance")),
        "contracts_with_aggregation_or_cap_disclosure_count": sum(1 for c in contracts if c.get("has_aggregation_or_cap_disclosure")),
        "contracts_with_answer_rules_count": sum(1 for c in contracts if c.get("has_answer_rules")),
        "total_collapsed_duplicate_record_count": sum(int(c.get("collapsed_duplicate_record_count") or 0) for c in contracts),
        "total_nearby_source_truth_context_count": sum(int(c.get("nearby_source_truth_context_count") or 0) for c in contracts),
        "contracts_with_self_rag_ready_count": sum(1 for c in contracts if c.get("self_rag_ready")),
        "contracts_with_crag_no_retry_count": sum(1 for c in contracts if c.get("crag_no_retry")),
        "graph_proof_authority_violation_count": sum(1 for c in contracts if c.get("graph_proof_authority_violation")),
        "summary_proof_authority_violation_count": sum(1 for c in contracts if c.get("summary_proof_authority_violation")),
        "answer_permission_count": sum(1 for c in contracts if _get_path(c, ["safety_contract", "answer_permission"], False)),
        "source_truth_mutation_allowed_count": sum(1 for c in contracts if _get_path(c, ["safety_contract", "source_truth_mutation_allowed"], False)),
    }


def make_quality_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, op: str, expected: Any) -> None:
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:
            raise ValueError(f"unknown op {op}")
        checks.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)})

    add("context_pack_count", int(summary.get("context_pack_count", 0)), ">=", int(thresholds.get("min_context_packs", 0)))
    add("prompt_contract_count", int(summary.get("prompt_contract_count", 0)), ">=", int(thresholds.get("min_prompt_contracts", 0)))
    add("ready_prompt_contract_count", int(summary.get("ready_prompt_contract_count", 0)), ">=", int(thresholds.get("min_ready_prompt_contracts", 0)))
    add("total_prompt_message_count", int(summary.get("total_prompt_message_count", 0)), ">=", int(thresholds.get("min_total_prompt_messages", 0)))
    add("contracts_with_source_truth_evidence_count", int(summary.get("contracts_with_source_truth_evidence_count", 0)), ">=", int(thresholds.get("min_contracts_with_source_truth_evidence", 0)))
    add("contracts_with_graph_guidance_count", int(summary.get("contracts_with_graph_guidance_count", 0)), ">=", int(thresholds.get("min_contracts_with_graph_guidance", 0)))
    add("contracts_with_v2_summary_guidance_count", int(summary.get("contracts_with_v2_summary_guidance_count", 0)), ">=", int(thresholds.get("min_contracts_with_v2_summary_guidance", 0)))
    add("contracts_with_aggregation_or_cap_disclosure_count", int(summary.get("contracts_with_aggregation_or_cap_disclosure_count", 0)), ">=", int(thresholds.get("min_contracts_with_aggregation_or_cap_disclosure", 0)))
    add("contracts_with_self_rag_ready_count", int(summary.get("contracts_with_self_rag_ready_count", 0)), ">=", int(thresholds.get("min_contracts_with_self_rag_ready", 0)))
    add("contracts_with_crag_no_retry_count", int(summary.get("contracts_with_crag_no_retry_count", 0)), ">=", int(thresholds.get("min_contracts_with_crag_no_retry", 0)))
    add("contracts_with_answer_rules_count", int(summary.get("contracts_with_answer_rules_count", 0)), ">=", int(thresholds.get("min_contracts_with_answer_rules", 0)))
    add("graph_proof_authority_violation_count", int(summary.get("graph_proof_authority_violation_count", 0)), "<=", int(thresholds.get("max_graph_proof_authority_violations", 0)))
    add("summary_proof_authority_violation_count", int(summary.get("summary_proof_authority_violation_count", 0)), "<=", int(thresholds.get("max_summary_proof_authority_violations", 0)))
    add("answer_permission_count", int(summary.get("answer_permission_count", 0)), "<=", int(thresholds.get("max_answer_permission_count", 0)))
    add("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count", 0)), "<=", int(thresholds.get("max_source_truth_mutation_allowed", 0)))
    if thresholds.get("require_no_answer_permission"):
        add("require_no_answer_permission", int(summary.get("answer_permission_count", 0)), "==", 0)
    return checks


def build_report(
    context_pack_report: Mapping[str, Any],
    self_rag_crag_report: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    *,
    max_evidence_items: int = 12,
) -> Dict[str, Any]:
    contracts = build_prompt_contracts(context_pack_report, self_rag_crag_report, max_evidence_items=max_evidence_items)
    summary = summarize_contracts(contracts)
    checks = make_quality_checks(summary, thresholds)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    status = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NEEDS_REPAIR
    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": status,
        "quality_status": quality_status,
        **summary,
        "contract": {
            "llm_prompt_contract_only": True,
            "llm_called": False,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "aggregation_cap_disclosure_required_when_capped": True,
            "evidence_deduplicated_before_llm_prompt": True,
            "self_rag_crag_status_included_in_prompt": True,
            "nearby_ocr_context_separated_from_direct_evidence": True,
            "final_gate_required_after_llm_draft": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
        "quality_checks": checks,
        "prompt_contracts": contracts,
    }
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Live LLM Prompt Contract v21",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for key in [
        "context_pack_count",
        "prompt_contract_count",
        "ready_prompt_contract_count",
        "total_prompt_message_count",
        "contracts_with_source_truth_evidence_count",
        "contracts_with_graph_guidance_count",
        "contracts_with_v2_summary_guidance_count",
        "contracts_with_aggregation_or_cap_disclosure_count",
        "contracts_with_self_rag_ready_count",
        "contracts_with_crag_no_retry_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {report.get(key, 0)}")
    lines.extend([
        "",
        "## Contract",
        "- This stage builds LLM-ready prompt messages but does not call an LLM.",
        "- Source-truth evidence is the only proof authority.",
        "- Graph/Leiden and v2 summaries are guidance only.",
        "- Capped/high-degree results must be disclosed to the LLM.",
        "- The LLM reads compact context packs, not raw 5TB corpus data or the full graph.",
        "",
        "## Prompt contracts",
    ])
    for contract in report.get("prompt_contracts", [])[:20]:
        lines.append(f"### {contract.get('prompt_contract_id')} — `{contract.get('prompt_contract_status')}`")
        lines.append(f"- query: {contract.get('user_query')}")
        lines.append(f"- evidence_item_count: {contract.get('evidence_item_count')}")
        lines.append(f"- has_graph_guidance: {contract.get('has_graph_guidance')}")
        lines.append(f"- has_v2_summary_guidance: {contract.get('has_v2_summary_guidance')}")
        lines.append(f"- has_aggregation_or_cap_disclosure: {contract.get('has_aggregation_or_cap_disclosure')}")
        lines.append("")
    lines.extend(["## Quality checks"])
    for check in report.get("quality_checks", []):
        lines.append(
            f"- {'PASS' if check.get('passed') else 'FAIL'} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}"
        )
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_live_llm_prompt_contract_v21.json"
    prompts_path = out / "trace_net_e2e_live_llm_prompt_contract_records_v21.jsonl"
    messages_path = out / "trace_net_e2e_live_llm_prompt_messages_v21.jsonl"
    inspect_path = out / "trace_net_e2e_live_llm_prompt_contract_v21.md"

    contracts = list(report.get("prompt_contracts", []))
    message_rows = []
    for contract in contracts:
        for idx, message in enumerate(contract.get("messages", []), start=1):
            message_rows.append({
                "prompt_contract_id": contract.get("prompt_contract_id"),
                "message_index": idx,
                **message,
            })

    write_json(report_path, report)
    write_jsonl(prompts_path, contracts)
    write_jsonl(messages_path, message_rows)
    inspect_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "prompts_jsonl_path": str(prompts_path),
        "messages_jsonl_path": str(messages_path),
        "inspect_md_path": str(inspect_path),
    }


def print_summary(report: Mapping[str, Any], paths: Optional[Mapping[str, str]] = None) -> None:
    print("TRACE-Net E2E Live LLM Prompt Contract v21")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "context_pack_count",
        "prompt_contract_count",
        "ready_prompt_contract_count",
        "total_prompt_message_count",
        "contracts_with_source_truth_evidence_count",
        "contracts_with_graph_guidance_count",
        "contracts_with_v2_summary_guidance_count",
        "contracts_with_aggregation_or_cap_disclosure_count",
        "contracts_with_self_rag_ready_count",
        "contracts_with_crag_no_retry_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {report.get(key, 0)}")
    if paths:
        for key, value in paths.items():
            print(f" {key}: {value}")


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_context_packs": args.min_context_packs,
        "min_prompt_contracts": args.min_prompt_contracts,
        "min_ready_prompt_contracts": args.min_ready_prompt_contracts,
        "min_total_prompt_messages": args.min_total_prompt_messages,
        "min_contracts_with_source_truth_evidence": args.min_contracts_with_source_truth_evidence,
        "min_contracts_with_graph_guidance": args.min_contracts_with_graph_guidance,
        "min_contracts_with_v2_summary_guidance": args.min_contracts_with_v2_summary_guidance,
        "min_contracts_with_aggregation_or_cap_disclosure": args.min_contracts_with_aggregation_or_cap_disclosure,
        "min_contracts_with_self_rag_ready": args.min_contracts_with_self_rag_ready,
        "min_contracts_with_crag_no_retry": args.min_contracts_with_crag_no_retry,
        "min_contracts_with_answer_rules": args.min_contracts_with_answer_rules,
        "max_graph_proof_authority_violations": args.max_graph_proof_authority_violations,
        "max_summary_proof_authority_violations": args.max_summary_proof_authority_violations,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-context-packs", type=int, default=0)
    parser.add_argument("--min-prompt-contracts", type=int, default=0)
    parser.add_argument("--min-ready-prompt-contracts", type=int, default=0)
    parser.add_argument("--min-total-prompt-messages", type=int, default=0)
    parser.add_argument("--min-contracts-with-source-truth-evidence", type=int, default=0)
    parser.add_argument("--min-contracts-with-graph-guidance", type=int, default=0)
    parser.add_argument("--min-contracts-with-v2-summary-guidance", type=int, default=0)
    parser.add_argument("--min-contracts-with-aggregation-or-cap-disclosure", type=int, default=0)
    parser.add_argument("--min-contracts-with-self-rag-ready", type=int, default=0)
    parser.add_argument("--min-contracts-with-crag-no-retry", type=int, default=0)
    parser.add_argument("--min-contracts-with-answer-rules", type=int, default=0)
    parser.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net live LLM prompt contract v21")
    parser.add_argument("--executed-plan-context-pack", required=True)
    parser.add_argument("--live-self-rag-crag-evaluator", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-evidence-items", type=int, default=12)
    parser.add_argument("--quality", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args(argv)

    context_pack = load_json(args.executed_plan_context_pack)
    evaluator = load_json(args.live_self_rag_crag_evaluator)
    report = build_report(context_pack, evaluator, thresholds_from_args(args), max_evidence_items=args.max_evidence_items)
    paths = write_report_files(report, args.output_dir)
    print_summary(report, paths)
    return 0 if report.get("quality_status") == QUALITY_PASS else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net live LLM prompt contract v21 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args(argv)

    report = load_json(args.report_path)
    summary = {k: report.get(k, 0) for k in summarize_contracts(report.get("prompt_contracts", [])).keys()}
    # Prefer stored summary counts when present.
    for key in list(summary.keys()):
        summary[key] = report.get(key, summary[key])
    checks = make_quality_checks(summary, thresholds_from_args(args))
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    report = dict(report)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    if args.write_json:
        write_json(args.report_path, report)

    print("TRACE-Net E2E Live LLM Prompt Contract v21 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        print(f" {'PASS' if check['passed'] else 'FAIL'} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}")
    return 0 if quality_status == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
