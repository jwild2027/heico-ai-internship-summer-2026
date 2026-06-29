"""TRACE-Net anchor-aware graph/Leiden context expansion v1.

This module sits after trace_net_answer_context_anchor_injector_v1.
It uses proven exact-match anchors as the center of context expansion, then
annotates exact anchors, family variants, reference anchors, and retained
support context with graph/Leiden community relation signals.

Safety contract:
- dry-run only
- no writes to Postgres, Qdrant, or OpenSearch
- no source-truth mutation
- no answer permission
- graph/Leiden context ranks/expands nearby evidence; it never proves exact
  part identity by itself
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

MODULE = "trace_net_anchor_aware_graph_leiden_expander_v1"
VERSION = "v1"

OUTPUT_JSON = f"{MODULE}.json"
OUTPUT_SUMMARY = f"{MODULE}_summary.json"
OUTPUT_PROMPT = f"{MODULE}_prompt.txt"
OUTPUT_JSONL = f"{MODULE}_records.jsonl"
OUTPUT_CSV = f"{MODULE}_records.csv"
OUTPUT_CITATIONS = f"{MODULE}_citation_map.jsonl"
OUTPUT_VIOLATIONS = f"{MODULE}_violations.csv"
QUALITY_JSON = f"{MODULE}_quality_check.json"

SAFE_FLAGS = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "human_review_required": False,
    "manual_review_required": False,
    "unsafe_record": False,
}

PAGE_ID_RE = re.compile(r"(?:t_p_[A-Za-z0-9_]+_p\d{6}|p\d{6})", re.IGNORECASE)
COMMUNITY_RE = re.compile(r"(?:tracenet_community_)?0*(\d+)$", re.IGNORECASE)


def _read_json(path: Path | str | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    seen: Set[str] = set()
    for r in records:
        for k in r.keys():
            if k not in seen:
                keys.append(k)
                seen.add(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys or ["empty"])
        writer.writeheader()
        for r in records:
            row: Dict[str, Any] = {}
            for k in keys:
                v = r.get(k)
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
                else:
                    row[k] = v
            writer.writerow(row)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False, sort_keys=True)).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y", "pass"}


def _page_number_from_page_id(page_id: Any) -> Optional[int]:
    if not page_id:
        return None
    m = re.search(r"p(\d{6})$", str(page_id))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _normalize_page_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"\d+", text)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            return None
    return None


def _source_member_variants(source_member: Any) -> List[str]:
    if not source_member:
        return []
    raw = str(source_member).replace("\\", "/").split("/")[-1]
    variants = {raw, raw.lower()}
    stem = raw.rsplit(".", 1)[0]
    variants.add(stem)
    variants.add(stem.lower())
    try:
        n = int(re.sub(r"\D", "", stem))
        variants.add(str(n))
        variants.add(f"{n:06d}.tif")
        variants.add(f"{n:08d}.tif")
    except ValueError:
        pass
    return sorted(v for v in variants if v)


def _community_variants(value: Any) -> List[str]:
    values: Set[str] = set()
    for v in _as_list(value):
        if v is None:
            continue
        text = str(v).strip()
        if not text:
            continue
        values.add(text)
        m = COMMUNITY_RE.search(text)
        if m:
            n = int(m.group(1))
            values.add(str(n))
            values.add(f"tracenet_community_{n:05d}")
    return sorted(values)


def _extract_community_values(record: Mapping[str, Any]) -> List[str]:
    keys = [
        "community_id",
        "leiden_community_id",
        "community",
        "community_label",
        "community_key",
        "leiden_community",
        "community_ids",
        "leiden_community_ids",
        "same_anchor_leiden_community_ids",
        "cluster_id",
    ]
    values: Set[str] = set()
    for key in keys:
        for v in _as_list(record.get(key)):
            for variant in _community_variants(v):
                values.add(variant)
    # Some graph node records store community under nested metadata/properties.
    for nested_key in ("metadata", "properties", "data", "attrs"):
        nested = record.get(nested_key)
        if isinstance(nested, Mapping):
            for v in _extract_community_values(nested):
                values.add(v)
    return sorted(values)


def _extract_page_ids_from_record(record: Mapping[str, Any]) -> List[str]:
    keys = [
        "page_id", "canonical_page_id", "source_page_id", "target_page_id", "from_page_id", "to_page_id",
        "source_id", "target_id", "node_id", "id", "subject_id", "object_id",
    ]
    values: Set[str] = set()
    for key in keys:
        v = record.get(key)
        if isinstance(v, str):
            for m in PAGE_ID_RE.findall(v):
                values.add(m)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    for m in PAGE_ID_RE.findall(item):
                        values.add(m)
    for key in ("metadata", "properties", "data", "attrs"):
        nested = record.get(key)
        if isinstance(nested, Mapping):
            values.update(_extract_page_ids_from_record(nested))
    return sorted(values)


def _extract_page_numbers_from_record(record: Mapping[str, Any]) -> List[int]:
    keys = ["page_number", "canonical_page_number", "page", "source_page_number", "target_page_number"]
    values: Set[int] = set()
    for key in keys:
        for v in _as_list(record.get(key)):
            n = _normalize_page_number(v)
            if n is not None:
                values.add(n)
    for pid in _extract_page_ids_from_record(record):
        n = _page_number_from_page_id(pid)
        if n is not None:
            values.add(n)
    for key in ("metadata", "properties", "data", "attrs"):
        nested = record.get(key)
        if isinstance(nested, Mapping):
            values.update(_extract_page_numbers_from_record(nested))
    return sorted(values)


def _extract_source_members_from_record(record: Mapping[str, Any]) -> List[str]:
    keys = ["source_member", "raw_tiff_reference", "source_trace", "image_member", "filename", "file_name"]
    values: Set[str] = set()
    for key in keys:
        for v in _as_list(record.get(key)):
            values.update(_source_member_variants(v))
    for key in ("metadata", "properties", "data", "attrs"):
        nested = record.get(key)
        if isinstance(nested, Mapping):
            values.update(_extract_source_members_from_record(nested))
    return sorted(values)


def _iter_dicts(obj: Any, *, max_depth: int = 8, _depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if _depth > max_depth:
        return
    if isinstance(obj, Mapping):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v, max_depth=max_depth, _depth=_depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item, max_depth=max_depth, _depth=_depth + 1)


def _looks_like_graph_record(record: Mapping[str, Any]) -> bool:
    if _extract_community_values(record):
        return True
    if _extract_page_ids_from_record(record):
        return True
    rel_keys = {"source", "target", "source_id", "target_id", "relation", "edge_type", "relationship"}
    return any(k in record for k in rel_keys)


def _build_community_index(*payloads: Mapping[str, Any]) -> Tuple[Dict[str, Set[str]], Dict[str, int]]:
    """Build a page/source lookup to Leiden/community IDs from graph-like payloads."""
    index: Dict[str, Set[str]] = defaultdict(set)
    diag = Counter()
    for payload in payloads:
        if not payload:
            continue
        for record in _iter_dicts(payload):
            if not isinstance(record, Mapping) or not _looks_like_graph_record(record):
                continue
            communities = _extract_community_values(record)
            if not communities:
                continue
            diag["community_assignment_record_count"] += 1
            keys: Set[str] = set()
            for pid in _extract_page_ids_from_record(record):
                keys.add(f"page_id:{pid}")
                diag["page_id_join_key_count"] += 1
                n = _page_number_from_page_id(pid)
                if n is not None:
                    keys.add(f"page_number:{n}")
            for n in _extract_page_numbers_from_record(record):
                keys.add(f"page_number:{n}")
                diag["page_number_join_key_count"] += 1
            for sm in _extract_source_members_from_record(record):
                keys.add(f"source_member:{sm}")
                diag["source_member_join_key_count"] += 1
            if not keys:
                continue
            for key in keys:
                index[key].update(communities)
    diag["community_index_key_count"] = len(index)
    return index, dict(diag)


def _record_join_keys(record: Mapping[str, Any]) -> List[str]:
    keys: Set[str] = set()
    pid = record.get("page_id") or record.get("canonical_page_id")
    if pid:
        keys.add(f"page_id:{pid}")
        n = _page_number_from_page_id(pid)
        if n is not None:
            keys.add(f"page_number:{n}")
    n = _normalize_page_number(record.get("page_number") or record.get("canonical_page_number"))
    if n is not None:
        keys.add(f"page_number:{n}")
    for sm in _source_member_variants(record.get("source_member") or record.get("raw_tiff_reference")):
        keys.add(f"source_member:{sm}")
    return sorted(keys)


def _communities_for_record(record: Mapping[str, Any], community_index: Mapping[str, Set[str]]) -> List[str]:
    values: Set[str] = set(_extract_community_values(record))
    for key in _record_join_keys(record):
        values.update(community_index.get(key, set()))
    return sorted(values, key=lambda x: (len(x), x))


def _relation_score(record: Mapping[str, Any], anchor_communities: Set[str], anchor_page_numbers: Set[int], anchor_page_ids: Set[str]) -> Tuple[str, str, float, List[str], List[str]]:
    """Return role, relation type, priority, shared communities, warnings."""
    role = str(record.get("anchor_role") or record.get("graph_context_role") or "support_context")
    proof = str(record.get("proof_strength") or "")
    page_id = str(record.get("page_id") or "")
    page_number = _normalize_page_number(record.get("page_number"))
    communities = set(_as_list(record.get("leiden_community_ids")))
    shared = sorted(communities.intersection(anchor_communities))
    warnings: List[str] = []

    if role == "direct_exact_match_anchor" or proof == "direct_exact_proof":
        return "direct_exact_match_anchor", "exact_anchor", 1000.0, shared or sorted(communities), warnings
    if role == "exact_reference_anchor":
        return "exact_reference_anchor", "exact_reference", 800.0, shared, warnings
    if role == "family_variant_anchor":
        if shared:
            return "same_anchor_community_variant", "same_anchor_leiden_community_variant", 700.0, shared, warnings
        if page_id in anchor_page_ids or page_number in anchor_page_numbers:
            return "same_anchor_page_variant", "same_page_family_variant", 680.0, shared, warnings
        if page_number is not None:
            deltas = [abs(page_number - a) for a in anchor_page_numbers]
            if deltas and min(deltas) <= 3:
                return "same_anchor_page_variant", "nearby_page_family_variant", 660.0, shared, warnings
        warnings.append("family_variant_without_anchor_community")
        return "family_variant_anchor", "part_family_variant", 620.0, shared, warnings
    if shared:
        return "same_anchor_leiden_community_neighbor", "same_anchor_leiden_community", 560.0, shared, warnings
    if page_number is not None:
        # Nearby physical page neighborhood; conservative and lower than graph/community.
        deltas = [abs(page_number - a) for a in anchor_page_numbers]
        if deltas and min(deltas) <= 3:
            return "nearby_anchor_page_neighbor", "nearby_page_window", 420.0, shared, warnings
    if role == "direct_exact_match_candidate":
        warnings.append("retained_old_direct_candidate_demoted_by_exact_anchors")
        return "superseded_direct_candidate", "superseded_by_exact_anchors", 240.0, shared, warnings
    warnings.append("no_anchor_graph_relation")
    return role or "support_context_candidate", "retained_support_context", 120.0, shared, warnings


def _citation_map(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in records:
        out.append({
            "citation_label": r.get("citation_label"),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "source_member": r.get("source_member"),
            "anchor_aware_role": r.get("anchor_aware_role"),
            "proof_strength": r.get("proof_strength"),
            "leiden_community_ids": r.get("leiden_community_ids") or [],
            "same_anchor_leiden_community_ids": r.get("same_anchor_leiden_community_ids") or [],
        })
    return out


def _build_prompt(question: str, part_numbers: Sequence[str], records: Sequence[Mapping[str, Any]], max_chars: int = 24000) -> str:
    lines: List[str] = []
    lines.append("You are TRACE-Net's final context organizer for exact part-number questions.")
    lines.append("Use DIRECT EXACT ANCHORS first. They are the only evidence that can prove the queried part identity.")
    lines.append("Graph and Leiden community context may rank nearby/similar parts, but never proves identity or interchangeability by itself.")
    lines.append("Every factual claim in the final answer must cite the provided labels like [E1].")
    lines.append("Do not invent effectivity, quantities, applicability, substitutions, or interchangeability.")
    lines.append("")
    lines.append(f"QUESTION: {question}")
    lines.append("QUERY_PART_NUMBERS: " + ", ".join(part_numbers))
    lines.append("")

    groups = [
        ("DIRECT EXACT ANCHORS", {"direct_exact_match_anchor"}),
        ("EXACT REFERENCES", {"exact_reference_anchor"}),
        ("ANCHOR-AWARE NEARBY / VARIANT EVIDENCE", {"same_anchor_community_variant", "same_anchor_page_variant", "family_variant_anchor", "same_anchor_leiden_community_neighbor", "nearby_anchor_page_neighbor"}),
        ("RETAINED LOW-PRIORITY SUPPORT", {"superseded_direct_candidate", "similar_table_candidate", "support_context_candidate"}),
    ]
    for title, roles in groups:
        subset = [r for r in records if r.get("anchor_aware_role") in roles]
        if not subset:
            continue
        lines.append(title + ":")
        for r in subset:
            excerpt = _clean_text(r.get("excerpt") or r.get("enriched_excerpt") or r.get("evidence") or "")
            if len(excerpt) > 900:
                excerpt = excerpt[:900].rstrip() + "..."
            communities = ",".join(r.get("leiden_community_ids") or []) or "none"
            shared = ",".join(r.get("same_anchor_leiden_community_ids") or []) or "none"
            page = r.get("page_number") if r.get("page_number") is not None else "unknown"
            lines.append(
                f"{r.get('citation_label')}: role={r.get('anchor_aware_role')}, proof={r.get('proof_strength')}, "
                f"relation={r.get('anchor_relation_type')}, page={page}, page_id={r.get('page_id')}, "
                f"communities={communities}, same_anchor_communities={shared}. Evidence: {excerpt}"
            )
        lines.append("")
    lines.append("SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    prompt = "\n".join(lines)
    if len(prompt) > max_chars:
        prompt = prompt[: max_chars - 80].rstrip() + "\n...[TRUNCATED: prompt too long for configured cap]"
    return prompt


def _source_quality(payload: Mapping[str, Any]) -> Optional[str]:
    return payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status")


def build_anchor_aware_graph_leiden_expander(
    *,
    anchor_injector: str | Path,
    leiden_communities: str | Path | None = None,
    community_aware_retrieval: str | Path | None = None,
    graph_report: str | Path | None = None,
    output_dir: str | Path,
    max_records: int = 40,
    require_source_quality_pass: bool = False,
    require_anchor_communities: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    anchor_payload = _read_json(anchor_injector)
    leiden_payload = _read_json(leiden_communities)
    community_payload = _read_json(community_aware_retrieval)
    graph_payload = _read_json(graph_report)

    violations: List[Dict[str, Any]] = []
    source_statuses = {
        "anchor_injector": _source_quality(anchor_payload),
        "leiden_communities": _source_quality(leiden_payload) if leiden_communities else None,
        "community_aware_retrieval": _source_quality(community_payload) if community_aware_retrieval else None,
        "graph_report": _source_quality(graph_payload) if graph_report else None,
    }
    if require_source_quality_pass:
        for name, status in source_statuses.items():
            if name == "anchor_injector" and status != "PASS":
                violations.append({"violation_type": "source_quality_not_pass", "source": name, "status": status})
            if name != "anchor_injector" and status not in (None, "PASS"):
                violations.append({"violation_type": "source_quality_not_pass", "source": name, "status": status})

    source_records = list(anchor_payload.get("records") or [])
    question = str(anchor_payload.get("question") or (anchor_payload.get("summary") or {}).get("question") or "")
    query_parts = list(anchor_payload.get("query_part_numbers") or (anchor_payload.get("summary") or {}).get("query_part_numbers") or [])

    community_index, join_diag = _build_community_index(leiden_payload, community_payload, graph_payload)

    # First annotate all records with communities.
    annotated: List[Dict[str, Any]] = []
    for idx, r0 in enumerate(source_records):
        r = dict(r0)
        r.setdefault("citation_label", f"E{idx+1}")
        r.setdefault("proof_strength", r.get("proof_strength") or "")
        communities = _communities_for_record(r, community_index)
        r["leiden_community_ids"] = communities
        annotated.append(r)

    direct_anchors = [r for r in annotated if r.get("anchor_role") == "direct_exact_match_anchor" or r.get("proof_strength") == "direct_exact_proof"]
    anchor_communities: Set[str] = set()
    anchor_page_numbers: Set[int] = set()
    anchor_page_ids: Set[str] = set()
    for r in direct_anchors:
        anchor_communities.update(r.get("leiden_community_ids") or [])
        pid = r.get("page_id")
        if pid:
            anchor_page_ids.add(str(pid))
        n = _normalize_page_number(r.get("page_number"))
        if n is not None:
            anchor_page_numbers.add(n)

    expanded: List[Dict[str, Any]] = []
    for r0 in annotated:
        r = dict(r0)
        role, relation, priority, shared, warnings = _relation_score(r, anchor_communities, anchor_page_numbers, anchor_page_ids)
        r["anchor_aware_role"] = role
        r["anchor_relation_type"] = relation
        r["anchor_context_priority"] = priority
        r["same_anchor_leiden_community"] = bool(shared)
        r["same_anchor_leiden_community_ids"] = shared
        base_warnings = list(r.get("graph_context_warnings") or r.get("exact_row_proof_warnings") or [])
        r["anchor_aware_warnings"] = sorted(set(base_warnings + warnings))
        r["answer_permission"] = False
        r["can_answer_directly"] = False
        r["can_prove_claims"] = False
        r["source_truth_mutation_allowed"] = False
        r["postgres_write_attempt"] = False
        r["qdrant_write_attempt"] = False
        r["opensearch_write_attempt"] = False
        r["human_review_required"] = False
        r["manual_review_required"] = False
        r["unsafe_record"] = False
        expanded.append(r)

    expanded.sort(key=lambda r: (-float(r.get("anchor_context_priority") or 0), str(r.get("citation_label") or "")))
    if max_records and max_records > 0:
        expanded = expanded[:max_records]

    citation_map = _citation_map(expanded)
    prompt = _build_prompt(question, query_parts, expanded)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_anchor_injector": str(anchor_injector),
        "source_leiden_communities": str(leiden_communities) if leiden_communities else None,
        "source_community_aware_retrieval": str(community_aware_retrieval) if community_aware_retrieval else None,
        "source_graph_report": str(graph_report) if graph_report else None,
        "source_quality_statuses": source_statuses,
        "question": question,
        "query_part_numbers": query_parts,
        "source_record_count": len(source_records),
        "anchor_aware_record_count": len(expanded),
        "citation_count": len(citation_map),
        "context_prompt_char_count": len(prompt),
        "direct_exact_anchor_count": sum(1 for r in expanded if r.get("anchor_aware_role") == "direct_exact_match_anchor"),
        "direct_exact_anchor_page_count": len({r.get("page_id") for r in expanded if r.get("anchor_aware_role") == "direct_exact_match_anchor" and r.get("page_id")}),
        "direct_exact_anchor_page_numbers": sorted({r.get("page_number") for r in expanded if r.get("anchor_aware_role") == "direct_exact_match_anchor" and r.get("page_number") is not None}),
        "anchor_community_count": len(anchor_communities),
        "anchor_community_ids": sorted(anchor_communities),
        "community_annotation_count": sum(1 for r in expanded if r.get("leiden_community_ids")),
        "same_anchor_leiden_community_count": sum(1 for r in expanded if r.get("same_anchor_leiden_community")),
        "same_anchor_variant_count": sum(1 for r in expanded if r.get("anchor_aware_role") in {"same_anchor_community_variant", "same_anchor_page_variant"}),
        "nearby_anchor_page_neighbor_count": sum(1 for r in expanded if r.get("anchor_aware_role") == "nearby_anchor_page_neighbor"),
        "superseded_old_direct_candidate_count": sum(1 for r in expanded if r.get("anchor_aware_role") == "superseded_direct_candidate"),
        "anchor_aware_role_counts": dict(Counter(r.get("anchor_aware_role") for r in expanded)),
        "anchor_relation_type_counts": dict(Counter(r.get("anchor_relation_type") for r in expanded)),
        "proof_strength_counts": dict(Counter(r.get("proof_strength") for r in expanded)),
        "ready_for_gemma_anchor_aware_prompt": True,
        "ready_for_answer_quality_gate": True,
        "dry_run_only": True,
        **join_diag,
    }
    for k, v in SAFE_FLAGS.items():
        summary[f"{k}_count"] = sum(1 for r in expanded if _bool(r.get(k)))
    summary["write_attempt_count"] = summary["postgres_write_attempt_count"] + summary["qdrant_write_attempt_count"] + summary["opensearch_write_attempt_count"]
    summary["violation_record_count"] = len(violations)

    if require_anchor_communities and not anchor_communities:
        violations.append({"violation_type": "missing_anchor_community_annotations", "detail": "No direct exact anchors joined to graph/Leiden communities."})
        summary["violation_record_count"] = len(violations)

    quality_status = "PASS" if not violations else "FAIL"
    payload = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "question": question,
        "query_part_numbers": query_parts,
        "records": expanded,
        "citation_map": citation_map,
        "llm_context_prompt": prompt,
        "violations": violations,
        "safety_contract": {
            "dry_run_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "graph_leiden_proves_exact_identity": False,
            "exact_source_text_proves_identity": True,
        },
    }

    _write_json(output / OUTPUT_JSON, payload)
    _write_json(output / OUTPUT_SUMMARY, summary)
    (output / OUTPUT_PROMPT).write_text(prompt, encoding="utf-8")
    _write_jsonl(output / OUTPUT_JSONL, expanded)
    _write_jsonl(output / OUTPUT_CITATIONS, citation_map)
    _write_csv(output / OUTPUT_CSV, expanded)
    _write_csv(output / OUTPUT_VIOLATIONS, violations)
    if quality:
        _write_json(output / QUALITY_JSON, {"quality_status": quality_status, "summary": summary, "failures": [v.get("violation_type") for v in violations]})
        print(f"Wrote: {output / QUALITY_JSON}")
    print("Status: TRACE_NET_ANCHOR_AWARE_GRAPH_LEIDEN_EXPANDER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary: " + json.dumps(summary, sort_keys=True))
    return payload


def check_anchor_aware_graph_leiden_expander_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_direct_anchors: int = 1,
    min_anchor_communities: int = 0,
    min_same_anchor_relations: int = 0,
    min_citations: int = 1,
    min_prompt_chars: int = 500,
    max_violation_records: int = 0,
    require_source_quality_pass: bool = False,
    require_anchor_aware_prompt: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = dict(payload.get("summary") or {})
    failures: List[str] = []

    def fail_if(cond: bool, name: str) -> None:
        if cond:
            failures.append(name)

    fail_if(summary.get("anchor_aware_record_count", 0) < min_records, "min_records")
    fail_if(summary.get("direct_exact_anchor_count", 0) < min_direct_anchors, "min_direct_anchors")
    fail_if(summary.get("anchor_community_count", 0) < min_anchor_communities, "min_anchor_communities")
    fail_if(summary.get("same_anchor_leiden_community_count", 0) < min_same_anchor_relations, "min_same_anchor_relations")
    fail_if(summary.get("citation_count", 0) < min_citations, "min_citations")
    fail_if(summary.get("context_prompt_char_count", 0) < min_prompt_chars, "min_prompt_chars")
    fail_if(summary.get("violation_record_count", 0) > max_violation_records, "max_violation_records")

    if require_source_quality_pass:
        statuses = summary.get("source_quality_statuses") or {}
        for name, status in statuses.items():
            if name == "anchor_injector" and status != "PASS":
                failures.append(f"source_quality_{name}")
            elif name != "anchor_injector" and status not in (None, "PASS"):
                failures.append(f"source_quality_{name}")
    if require_anchor_aware_prompt:
        fail_if(not summary.get("ready_for_gemma_anchor_aware_prompt"), "require_anchor_aware_prompt")
    if require_no_human_review_required:
        fail_if(summary.get("human_review_required_count", 0) != 0 or summary.get("manual_review_required_count", 0) != 0, "require_no_human_review_required")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "max_unsafe")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "require_no_answer_permission")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "require_no_source_truth_mutation")
    if require_no_write_attempts:
        fail_if(summary.get("write_attempt_count", 0) != 0, "require_no_write_attempts")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name(QUALITY_JSON)
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary: " + json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures: " + json.dumps(failures, indent=2))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net anchor-aware graph/Leiden context expansion v1.")
    parser.add_argument("--anchor-injector", required=True)
    parser.add_argument("--leiden-communities")
    parser.add_argument("--community-aware-retrieval")
    parser.add_argument("--graph-report")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-records", type=int, default=40)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-anchor-communities", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_anchor_aware_graph_leiden_expander(
        anchor_injector=args.anchor_injector,
        leiden_communities=args.leiden_communities,
        community_aware_retrieval=args.community_aware_retrieval,
        graph_report=args.graph_report,
        output_dir=args.output_dir,
        max_records=args.max_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_anchor_communities=args.require_anchor_communities,
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net anchor-aware graph/Leiden expansion quality v1.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-direct-anchors", type=int, default=1)
    parser.add_argument("--min-anchor-communities", type=int, default=0)
    parser.add_argument("--min-same-anchor-relations", type=int, default=0)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-prompt-chars", type=int, default=500)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-anchor-aware-prompt", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_anchor_aware_graph_leiden_expander_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_direct_anchors=args.min_direct_anchors,
        min_anchor_communities=args.min_anchor_communities,
        min_same_anchor_relations=args.min_same_anchor_relations,
        min_citations=args.min_citations,
        min_prompt_chars=args.min_prompt_chars,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_anchor_aware_prompt=args.require_anchor_aware_prompt,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":  # pragma: no cover
    main_build()
