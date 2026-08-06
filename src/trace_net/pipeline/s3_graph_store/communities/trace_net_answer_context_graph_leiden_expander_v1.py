"""TRACE-Net answer context graph/Leiden expander v1.

This module adds graph and Leiden-community context to an enriched TRACE-Net
answer context pack. Graph/community context is used only to rank and explain
nearby/similar evidence; it never upgrades a record to source-truth proof unless
there is direct source text evidence from the enriched context record itself.

The module is dry-run only: no Postgres, Qdrant, or OpenSearch writes; no source
truth mutation; no answer permission.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

MODULE = "trace_net_answer_context_graph_leiden_expander_v1"
VERSION = "v1"

PAGE_ID_RE = re.compile(r"t_p_[A-Za-z0-9_]+_p\d{6}")
PART_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-\d{2,4})?\b")

PAGE_ID_KEYS = (
    "page_id",
    "source_page_id",
    "target_page_id",
    "neighbor_page_id",
    "related_page_id",
    "canonical_page_id",
)
PAGE_NUMBER_KEYS = ("page_number", "canonical_page_number", "page")
COMMUNITY_KEYS = (
    "community_id",
    "leiden_community_id",
    "graph_community_id",
    "community",
    "community_label",
    "partition_id",
    "cluster_id",
    "modularity_class",
    "community_index",
)
COMMUNITY_LIST_KEYS = (
    "community_ids",
    "leiden_community_ids",
    "graph_community_ids",
    "communities",
    "partition_ids",
    "cluster_ids",
)
SOURCE_MEMBER_KEYS = (
    "source_member",
    "raw_tiff_reference",
    "source_image_path",
    "image_path",
    "source_file",
    "filename",
    "member",
)
NODE_LIST_KEYS = (
    "records",
    "community_records",
    "graph_records",
    "retrieval_records",
    "evidence_records",
    "nodes",
    "graph_nodes",
    "node_records",
    "community_assignments",
    "community_assignment_records",
    "community_membership_records",
    "page_community_records",
    "part_community_records",
    "table_cell_community_records",
    "leiden_records",
    "assignments",
    "memberships",
    "communities",
    "members",
)
NEIGHBOR_KEYS = (
    "neighbor_page_ids",
    "related_page_ids",
    "graph_neighbor_page_ids",
    "community_page_ids",
    "member_page_ids",
    "page_ids",
    "pages",
    "neighbors",
    "related_pages",
)
RELATION_KEYS = (
    "relation_type",
    "edge_type",
    "graph_relation_type",
    "relationship",
    "relation",
)
SAFETY_ZERO_KEYS = (
    "answer_permission_count",
    "source_truth_mutation_allowed_count",
    "unsafe_record_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "write_attempt_count",
)


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for record in records:
        for key in record:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({k: _csv_value(record.get(k)) for k in fieldnames})


def _iter_dict_records(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    """Return dict records from common graph/community containers.

    Some TRACE-Net graph artifacts summarize communities at the top level and do
    not use a `records` key. This helper intentionally scans common graph node
    containers such as `nodes`, `graph_nodes`, `community_assignments`, and
    nested `graph`/`data` dictionaries so page-community joins do not silently
    miss valid artifacts.
    """
    if value is None or depth > 4:
        return []
    out: list[dict[str, Any]] = []
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            out.extend(item for item in value if isinstance(item, dict))
        else:
            for item in value:
                out.extend(_iter_dict_records(item, depth=depth + 1))
    elif isinstance(value, dict):
        for key in NODE_LIST_KEYS:
            child = value.get(key)
            if isinstance(child, list):
                out.extend(item for item in child if isinstance(item, dict))
            elif isinstance(child, dict):
                out.extend(_iter_dict_records(child, depth=depth + 1))
        for key in ("graph", "data", "payload", "leiden", "community_graph", "community_payload"):
            child = value.get(key)
            if isinstance(child, (dict, list)):
                out.extend(_iter_dict_records(child, depth=depth + 1))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in out:
        ident = json.dumps(record, sort_keys=True, default=str)[:1000]
        if ident not in seen:
            seen.add(ident)
            deduped.append(record)
    return deduped


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _iter_dict_records(payload)


def _page_id(record: dict[str, Any]) -> str:
    for key in PAGE_ID_KEYS:
        value = record.get(key)
        if value:
            text = str(value)
            match = PAGE_ID_RE.search(text)
            return match.group(0) if match else text
    # fallback: mine strings in the record for a page id
    for page_id in _collect_page_ids(record):
        return page_id
    return ""


def _page_number(record: dict[str, Any]) -> int | None:
    for key in PAGE_NUMBER_KEYS:
        value = record.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _community_ids(record: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in COMMUNITY_KEYS:
        value = record.get(key)
        if value not in (None, "", [], {}):
            out.append(str(value))
    for key in COMMUNITY_LIST_KEYS:
        value = record.get(key)
        if isinstance(value, list):
            out.extend(str(v) for v in value if v not in (None, "", [], {}))
        elif value not in (None, "", [], {}):
            out.append(str(value))
    deduped: list[str] = []
    for cid in out:
        if cid and cid not in deduped:
            deduped.append(cid)
    return deduped


def _community_id(record: dict[str, Any]) -> str:
    values = _community_ids(record)
    return values[0] if values else ""


def _relation_type(record: dict[str, Any]) -> str:
    for key in RELATION_KEYS:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return "graph_neighbor"


def _collect_page_ids(value: Any, *, depth: int = 0) -> list[str]:
    if value is None or depth > 5:
        return []
    out: list[str] = []
    if isinstance(value, str):
        out.extend(PAGE_ID_RE.findall(value))
    elif isinstance(value, dict):
        for child in value.values():
            out.extend(_collect_page_ids(child, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            out.extend(_collect_page_ids(child, depth=depth + 1))
    deduped: list[str] = []
    for pid in out:
        if pid not in deduped:
            deduped.append(pid)
    return deduped


def _collect_neighbor_page_ids(record: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in NEIGHBOR_KEYS:
        if key in record:
            out.extend(_collect_page_ids(record.get(key)))
            value = record.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and PAGE_ID_RE.match(item):
                        out.append(item)
                    elif isinstance(item, dict):
                        pid = _page_id(item)
                        if pid:
                            out.append(pid)
    for key in ("target_page_id", "neighbor_page_id", "related_page_id"):
        if record.get(key):
            out.append(str(record[key]))
    deduped: list[str] = []
    for pid in out:
        match = PAGE_ID_RE.search(pid)
        clean = match.group(0) if match else pid
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped


def _source_members(record: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in SOURCE_MEMBER_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            out.append(Path(value).name.replace("\\", "/").split("/")[-1])
    # fallback: mine TIFF-looking members anywhere in the record
    blob = json.dumps(record, sort_keys=True, default=str)
    out.extend(re.findall(r"\b\d{5,8}\.tif(?:f)?\b", blob, flags=re.IGNORECASE))
    deduped: list[str] = []
    for member in out:
        member = member.strip()
        if member and member not in deduped:
            deduped.append(member)
    return deduped


def _join_keys(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    pid = _page_id(record)
    if pid:
        keys.append(f"page_id:{pid}")
    page_no = _page_number(record)
    if page_no is not None:
        keys.append(f"page_number:{page_no}")
        keys.append(f"source_member:{page_no:08d}.tif")
    for member in _source_members(record):
        keys.append(f"source_member:{member}")
    deduped: list[str] = []
    for key in keys:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def _get_indexed_communities(index: dict[str, set[str]], record: dict[str, Any]) -> set[str]:
    communities: set[str] = set()
    for key in _join_keys(record):
        communities.update(index.get(key, set()))
    return communities


def _load_optional_json(path: str | Path | None) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {"records": []}, None
    p = Path(path)
    if not p.exists():
        return {"records": [], "quality_status": "MISSING_OPTIONAL_INPUT"}, str(p)
    return _read_json(p), str(p)


def _build_graph_indexes(*payloads: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[tuple[str, str], list[str]], dict[str, Any]]:
    community_index: dict[str, set[str]] = {}
    community_to_keys: dict[str, set[str]] = {}
    relation_index: dict[tuple[str, str], list[str]] = {}
    stats = {
        "graph_input_record_count": 0,
        "community_index_key_count": 0,
        "page_id_join_key_count": 0,
        "page_number_join_key_count": 0,
        "source_member_join_key_count": 0,
        "community_assignment_record_count": 0,
        "relation_record_count": 0,
    }

    def add_community(key: str, community_id: str) -> None:
        if not key or not community_id:
            return
        community_index.setdefault(key, set()).add(community_id)
        community_to_keys.setdefault(community_id, set()).add(key)
        if key.startswith("page_id:"):
            stats["page_id_join_key_count"] += 1
        elif key.startswith("page_number:"):
            stats["page_number_join_key_count"] += 1
        elif key.startswith("source_member:"):
            stats["source_member_join_key_count"] += 1

    def add_relation(a: str, b: str, relation: str) -> None:
        if not a or not b or a == b:
            return
        relation_index.setdefault((a, b), []).append(relation)
        relation_index.setdefault((b, a), []).append(relation)

    for payload in payloads:
        records = _records(payload)
        stats["graph_input_record_count"] += len(records)
        for record in records:
            join_keys = _join_keys(record)
            community_ids = _community_ids(record)
            if community_ids and join_keys:
                stats["community_assignment_record_count"] += 1
                for cid in community_ids:
                    for key in join_keys:
                        add_community(key, cid)

            # Connect explicit neighbor relationships using all available join keys.
            relation = _relation_type(record)
            neighbor_page_ids = _collect_neighbor_page_ids(record)
            primary_pid = _page_id(record)
            if primary_pid and neighbor_page_ids:
                for neighbor in neighbor_page_ids:
                    add_relation(f"page_id:{primary_pid}", f"page_id:{neighbor}", relation)
                    stats["relation_record_count"] += 1

            page_ids = _collect_page_ids(record)
            if len(page_ids) >= 2:
                add_relation(f"page_id:{page_ids[0]}", f"page_id:{page_ids[1]}", relation)
                stats["relation_record_count"] += 1

    stats["community_index_key_count"] = len(community_index)
    return community_index, community_to_keys, relation_index, stats

def _query_part_numbers(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("summary") or {}
    values = summary.get("query_part_numbers") or payload.get("query_part_numbers") or []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values:
        value_s = str(value).strip()
        if value_s and value_s not in out:
            out.append(value_s)
    question = str(summary.get("question") or payload.get("question") or "")
    for match in PART_RE.findall(question):
        if match not in out:
            out.append(match)
    return out


def _question(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    return str(summary.get("question") or payload.get("question") or "")


def _relation_role(
    *,
    record: dict[str, Any],
    is_anchor: bool,
    same_anchor_community: bool,
    graph_neighbor: bool,
    anchor_page_distance: int | None,
) -> tuple[str, str, int | None, str]:
    enriched_role = str(record.get("enriched_context_role") or record.get("context_role") or "")
    route = str(record.get("route") or "")
    direct_text_match = bool(record.get("direct_text_match"))

    if direct_text_match:
        return "direct_exact_match_proven", "direct_proof", 0, "direct_text_match"
    if enriched_role.startswith("direct") or is_anchor:
        return "direct_exact_match_candidate", "direct_candidate", 0, "direct_candidate_anchor"
    if same_anchor_community:
        return "same_leiden_community_neighbor", "graph_related_candidate", 1, "shared_leiden_community"
    if graph_neighbor:
        return "graph_neighbor_candidate", "graph_related_candidate", 1, "explicit_graph_neighbor"
    if anchor_page_distance is not None and anchor_page_distance <= 10:
        return "nearby_page_neighbor", "related_candidate", 2, "nearby_page_number"
    if route == "table":
        return "similar_table_candidate", "weak_candidate", None, "retrieval_similarity_table"
    if route == "image":
        return "visual_context_candidate", "weak_candidate", None, "retrieval_similarity_visual"
    return "supporting_context_candidate", "weak_candidate", None, "retrieval_similarity"


def _priority(record: dict[str, Any], role: str, proof_strength: str, same_anchor_community: bool, graph_neighbor: bool) -> float:
    try:
        score = float(record.get("retrieval_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    if role == "direct_exact_match_proven":
        score += 1000
    elif role == "direct_exact_match_candidate":
        score += 500
    if same_anchor_community:
        score += 75
    if graph_neighbor:
        score += 50
    if proof_strength == "weak_candidate":
        score -= 10
    return round(score, 3)


def _source_trace_ready(record: dict[str, Any]) -> bool:
    return bool(record.get("page_id") and record.get("page_number") is not None and record.get("source_member") and record.get("source_image_sha256"))


def _prompt_line(record: dict[str, Any]) -> str:
    excerpt = str(record.get("enriched_excerpt") or "No enriched excerpt available.").replace("\n", " ")
    if len(excerpt) > 650:
        excerpt = excerpt[:647] + "..."
    communities = ",".join(record.get("leiden_community_ids") or []) or "none"
    return (
        f"{record.get('citation_label')}: graph_role={record.get('graph_context_role')}, "
        f"proof_strength={record.get('proof_strength')}, relation={record.get('graph_relation_type')}, "
        f"page={record.get('page_number')}, page_id={record.get('page_id')}, route={record.get('route')}, "
        f"communities={communities}, priority={record.get('context_priority')}. Evidence: {excerpt}"
    )


def _build_prompt(question: str, query_parts: list[str], records: list[dict[str, Any]], citation_map: list[dict[str, Any]]) -> str:
    direct = [r for r in records if str(r.get("graph_context_role", "")).startswith("direct")]
    community = [r for r in records if r.get("graph_context_role") in {"same_leiden_community_neighbor", "graph_neighbor_candidate", "nearby_page_neighbor"}]
    weak = [r for r in records if r not in direct and r not in community]

    lines = [
        "You are TRACE-Net's final answer drafter for scanned technical manuals.",
        "Use only the provided evidence. Do not invent part numbers, pages, effectivity, quantities, or applicability.",
        "Every factual claim must cite one or more citation labels like [E1].",
        "Graph and Leiden community context may rank related/nearby evidence, but it does not prove exact part identity or interchangeability by itself.",
        "Only direct source text/table evidence can prove the requested part number. If direct evidence is candidate-level, say so.",
        "Keep the answer short and operational: direct finding, graph/Leiden nearby evidence, limitations, citations, and safety note.",
        "",
        f"QUESTION: {question}",
        f"QUERY_PART_NUMBERS: {', '.join(query_parts) if query_parts else 'None detected'}",
        "",
        "DIRECT / EXACT EVIDENCE:",
    ]
    if direct:
        lines.extend(_prompt_line(r) for r in direct)
    else:
        lines.append("None.")
    lines.extend(["", "GRAPH / LEIDEN EXPANSION:"])
    if community:
        lines.extend(_prompt_line(r) for r in community)
    else:
        lines.append("No same-community or explicit graph-neighbor evidence found among retrieved records.")
    lines.extend(["", "OTHER RETRIEVED / WEAK SIMILARITY EVIDENCE:"])
    if weak:
        lines.extend(_prompt_line(r) for r in weak)
    else:
        lines.append("None.")
    lines.extend(["", "CITATION MAP:"])
    for c in citation_map:
        lines.append(
            f"{c.get('citation_label')} => page_id={c.get('page_id')}, page={c.get('page_number')}, "
            f"source_member={c.get('source_member')}, sha256={c.get('source_image_sha256')}, "
            f"graph_role={c.get('graph_context_role')}, communities={','.join(c.get('leiden_community_ids') or []) or 'none'}"
        )
    lines.extend(["", "SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true."])
    return "\n".join(lines)


def build_answer_context_graph_leiden_expander(
    *,
    evidence_enricher: str | Path,
    output_dir: str | Path,
    leiden_communities: str | Path | None = None,
    community_aware_retrieval: str | Path | None = None,
    graph_report: str | Path | None = None,
    max_graph_neighbors: int = 12,
    require_source_quality_pass: bool = False,
    require_graph_context: bool = False,
    quality: bool = False,
) -> dict[str, Any]:
    enricher_path = Path(evidence_enricher)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    enricher_payload = _read_json(enricher_path)
    leiden_payload, leiden_path_s = _load_optional_json(leiden_communities)
    community_payload, community_path_s = _load_optional_json(community_aware_retrieval)
    graph_payload, graph_path_s = _load_optional_json(graph_report)

    community_index, community_to_keys, relation_index, graph_join_stats = _build_graph_indexes(
        leiden_payload,
        community_payload,
        graph_payload,
    )

    source_quality_ok = enricher_payload.get("quality_status") == "PASS"
    query_parts = _query_part_numbers(enricher_payload)
    question = _question(enricher_payload)
    source_records = [r for r in _records(enricher_payload) if isinstance(r, dict)]

    anchor_records = [r for r in source_records if str(r.get("enriched_context_role", "")).startswith("direct") or r.get("direct_text_match")]
    if not anchor_records and source_records:
        anchor_records = [source_records[0]]
    anchor_page_ids = {_page_id(r) for r in anchor_records if _page_id(r)}
    anchor_page_numbers = [_page_number(r) for r in anchor_records if _page_number(r) is not None]
    anchor_communities: set[str] = set()
    for anchor_record in anchor_records:
        anchor_communities.update(_get_indexed_communities(community_index, anchor_record))

    expanded_records: list[dict[str, Any]] = []
    violation_records: list[dict[str, Any]] = []

    for record in source_records[: max(1, max_graph_neighbors)]:
        pid = _page_id(record)
        page_no = _page_number(record)
        communities = sorted(_get_indexed_communities(community_index, record))
        same_anchor_communities = sorted(set(communities).intersection(anchor_communities))
        is_anchor = pid in anchor_page_ids
        relation_notes: list[str] = []
        graph_neighbor = False
        record_join_keys = _join_keys(record)
        anchor_join_keys = []
        for anchor_record in anchor_records:
            anchor_join_keys.extend(_join_keys(anchor_record))
        for source_key in record_join_keys:
            for anchor_key in anchor_join_keys:
                rels = relation_index.get((source_key, anchor_key), [])
                if rels:
                    graph_neighbor = True
                    relation_notes.extend(rels)
        anchor_page_distance: int | None = None
        if page_no is not None and anchor_page_numbers:
            anchor_page_distance = min(abs(page_no - a) for a in anchor_page_numbers)

        role, proof_strength, graph_distance, relation_type = _relation_role(
            record=record,
            is_anchor=is_anchor,
            same_anchor_community=bool(same_anchor_communities),
            graph_neighbor=graph_neighbor,
            anchor_page_distance=anchor_page_distance,
        )
        priority = _priority(record, role, proof_strength, bool(same_anchor_communities), graph_neighbor)
        lineage_ready = _source_trace_ready(record)
        warnings: list[str] = []
        if not communities:
            warnings.append("no_leiden_community_annotation")
        if not same_anchor_communities and not is_anchor and not graph_neighbor:
            warnings.append("no_graph_relation_to_direct_anchor")
        if not lineage_ready:
            warnings.append("missing_lineage")

        expanded = dict(record)
        expanded.update(
            {
                "graph_context_role": role,
                "proof_strength": proof_strength,
                "graph_relation_type": relation_type,
                "graph_relation_notes": sorted(set(relation_notes)),
                "graph_distance_from_direct_anchor": graph_distance,
                "anchor_page_ids": sorted(anchor_page_ids),
                "anchor_leiden_community_ids": sorted(anchor_communities),
                "leiden_community_ids": communities,
                "same_anchor_leiden_community_ids": same_anchor_communities,
                "same_anchor_leiden_community": bool(same_anchor_communities),
                "explicit_graph_neighbor": graph_neighbor,
                "anchor_page_distance": anchor_page_distance,
                "context_priority": priority,
                "graph_context_warnings": warnings,
                "graph_context_status": "PASS" if lineage_ready else "WARNING",
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "dry_run_only": True,
                "human_review_required": False,
                "manual_review_required": False,
                "unsafe_record": False,
            }
        )
        expanded_records.append(expanded)
        if not lineage_ready:
            violation_records.append({**expanded, "violation_reason": "missing_lineage"})

    expanded_records.sort(key=lambda r: float(r.get("context_priority") or 0.0), reverse=True)
    citation_map = [
        {
            "citation_label": r.get("citation_label"),
            "graph_context_role": r.get("graph_context_role"),
            "proof_strength": r.get("proof_strength"),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "route": r.get("route"),
            "source_member": r.get("source_member"),
            "raw_tiff_reference": r.get("raw_tiff_reference"),
            "source_image_sha256": r.get("source_image_sha256"),
            "leiden_community_ids": r.get("leiden_community_ids") or [],
            "same_anchor_leiden_community_ids": r.get("same_anchor_leiden_community_ids") or [],
            "graph_relation_type": r.get("graph_relation_type"),
            "context_priority": r.get("context_priority"),
        }
        for r in expanded_records
    ]
    prompt = _build_prompt(question, query_parts, expanded_records, citation_map)

    community_annotation_count = sum(1 for r in expanded_records if r.get("leiden_community_ids"))
    same_anchor_community_count = sum(1 for r in expanded_records if r.get("same_anchor_leiden_community"))
    graph_neighbor_count = sum(1 for r in expanded_records if r.get("explicit_graph_neighbor"))
    graph_relation_annotation_count = sum(
        1
        for r in expanded_records
        if r.get("same_anchor_leiden_community") or r.get("explicit_graph_neighbor") or r.get("graph_context_role", "").startswith("direct")
    )
    role_counts: dict[str, int] = {}
    proof_counts: dict[str, int] = {}
    for r in expanded_records:
        role_counts[str(r.get("graph_context_role"))] = role_counts.get(str(r.get("graph_context_role")), 0) + 1
        proof_counts[str(r.get("proof_strength"))] = proof_counts.get(str(r.get("proof_strength")), 0) + 1

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_evidence_enricher": str(enricher_path),
        "source_evidence_enricher_quality_status": enricher_payload.get("quality_status"),
        "source_leiden_communities": leiden_path_s,
        "source_leiden_communities_quality_status": leiden_payload.get("quality_status"),
        "source_community_aware_retrieval": community_path_s,
        "source_community_aware_retrieval_quality_status": community_payload.get("quality_status"),
        "source_graph_report": graph_path_s,
        "source_graph_report_quality_status": graph_payload.get("quality_status"),
        "graph_input_record_count": graph_join_stats.get("graph_input_record_count", 0),
        "community_index_key_count": graph_join_stats.get("community_index_key_count", 0),
        "page_id_join_key_count": graph_join_stats.get("page_id_join_key_count", 0),
        "page_number_join_key_count": graph_join_stats.get("page_number_join_key_count", 0),
        "source_member_join_key_count": graph_join_stats.get("source_member_join_key_count", 0),
        "community_assignment_record_count": graph_join_stats.get("community_assignment_record_count", 0),
        "relation_record_count": graph_join_stats.get("relation_record_count", 0),
        "question": question,
        "query_part_numbers": query_parts,
        "query_part_number_count": len(query_parts),
        "graph_expanded_context_record_count": len(expanded_records),
        "citation_count": len(citation_map),
        "community_annotation_count": community_annotation_count,
        "same_anchor_leiden_community_count": same_anchor_community_count,
        "explicit_graph_neighbor_count": graph_neighbor_count,
        "graph_relation_annotation_count": graph_relation_annotation_count,
        "direct_exact_match_proven_count": role_counts.get("direct_exact_match_proven", 0),
        "direct_exact_match_candidate_count": role_counts.get("direct_exact_match_candidate", 0),
        "graph_context_role_counts": role_counts,
        "proof_strength_counts": proof_counts,
        "context_prompt_char_count": len(prompt),
        "graph_context_ready": len(expanded_records) > 0,
        "ready_for_gemma_graph_context_prompt": len(expanded_records) > 0 and not violation_records,
        "violation_record_count": len(violation_records),
        "lineage_ready_count": sum(1 for r in expanded_records if _source_trace_ready(r)),
        "missing_lineage_count": sum(1 for r in expanded_records if not _source_trace_ready(r)),
        "dry_run_only": True,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
    }
    quality_status = "PASS"
    if require_source_quality_pass and not source_quality_ok:
        quality_status = "FAIL"
    if require_graph_context and graph_relation_annotation_count == 0:
        quality_status = "FAIL"
    if violation_records:
        quality_status = "FAIL"
    if quality and not expanded_records:
        quality_status = "FAIL"

    payload = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "records": expanded_records,
        "citation_map": citation_map,
        "violation_records": violation_records,
        "llm_context_prompt": prompt,
    }
    report_path = output / "trace_net_answer_context_graph_leiden_expander_v1.json"
    _write_json(report_path, payload)
    _write_json(output / "trace_net_answer_context_graph_leiden_expander_v1_summary.json", summary)
    _write_jsonl(output / "trace_net_answer_context_graph_leiden_expander_v1_records.jsonl", expanded_records)
    _write_csv(output / "trace_net_answer_context_graph_leiden_expander_v1_records.csv", expanded_records)
    _write_jsonl(output / "trace_net_answer_context_graph_leiden_expander_v1_citation_map.jsonl", citation_map)
    _write_csv(output / "trace_net_answer_context_graph_leiden_expander_v1_violations.csv", violation_records)
    (output / "trace_net_answer_context_graph_leiden_expander_v1_prompt.txt").write_text(prompt, encoding="utf-8")
    (output / "trace_net_answer_context_graph_leiden_expander_v1.md").write_text(_markdown_report(payload), encoding="utf-8")
    if quality:
        _write_json(output / "trace_net_answer_context_graph_leiden_expander_v1_quality_check.json", payload)
        print(f"Wrote: {output / 'trace_net_answer_context_graph_leiden_expander_v1_quality_check.json'}")
    print("Status: TRACE_NET_ANSWER_CONTEXT_GRAPH_LEIDEN_EXPANDER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def _markdown_report(payload: dict[str, Any]) -> str:
    s = payload.get("summary", {})
    lines = [
        "# TRACE-Net Answer Context Graph/Leiden Expander v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "graph_expanded_context_record_count",
        "community_annotation_count",
        "same_anchor_leiden_community_count",
        "explicit_graph_neighbor_count",
        "graph_relation_annotation_count",
        "direct_exact_match_proven_count",
        "direct_exact_match_candidate_count",
        "context_prompt_char_count",
        "violation_record_count",
    ):
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Safety", "", "Dry-run only; graph/Leiden ranks context but does not grant answer permission or prove claims."])
    return "\n".join(lines) + "\n"


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_citations: int = 1,
    min_prompt_chars: int = 500,
    min_community_annotations: int = 0,
    min_graph_relation_annotations: int = 1,
    max_violation_records: int = 0,
    require_source_quality_pass: bool = False,
    require_graph_prompt: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary", {})
    failures: list[str] = []

    def count(key: str) -> int:
        try:
            return int(summary.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    if payload.get("quality_status") != "PASS":
        failures.append("source_report_quality_not_pass")
    if count("graph_expanded_context_record_count") < min_records:
        failures.append("min_records")
    if count("citation_count") < min_citations:
        failures.append("min_citations")
    if count("context_prompt_char_count") < min_prompt_chars:
        failures.append("min_prompt_chars")
    if count("community_annotation_count") < min_community_annotations:
        failures.append("min_community_annotations")
    if count("graph_relation_annotation_count") < min_graph_relation_annotations:
        failures.append("min_graph_relation_annotations")
    if count("violation_record_count") > max_violation_records:
        failures.append("max_violation_records")
    if require_source_quality_pass and summary.get("source_evidence_enricher_quality_status") != "PASS":
        failures.append("source_quality_not_pass")
    if require_graph_prompt and not payload.get("llm_context_prompt"):
        failures.append("missing_graph_prompt")
    if require_no_human_review_required and (count("human_review_required_count") or count("manual_review_required_count")):
        failures.append("human_review_required")
    if max_unsafe is not None and count("unsafe_record_count") > max_unsafe:
        failures.append("unsafe_record_count")
    if require_no_answer_permission and count("answer_permission_count"):
        failures.append("answer_permission_count")
    if require_no_source_truth_mutation and count("source_truth_mutation_allowed_count"):
        failures.append("source_truth_mutation_allowed_count")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count", "write_attempt_count"):
            if count(key):
                failures.append(key)

    result = dict(payload)
    result["quality_status"] = "FAIL" if failures else "PASS"
    result["quality_check_failures"] = failures
    if write_json:
        out = path.with_name(path.stem + "_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer context graph/Leiden expander v1")
    parser.add_argument("--evidence-enricher", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--leiden-communities")
    parser.add_argument("--community-aware-retrieval")
    parser.add_argument("--graph-report")
    parser.add_argument("--max-graph-neighbors", type=int, default=12)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-graph-context", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_answer_context_graph_leiden_expander(
        evidence_enricher=args.evidence_enricher,
        output_dir=args.output_dir,
        leiden_communities=args.leiden_communities,
        community_aware_retrieval=args.community_aware_retrieval,
        graph_report=args.graph_report,
        max_graph_neighbors=args.max_graph_neighbors,
        require_source_quality_pass=args.require_source_quality_pass,
        require_graph_context=args.require_graph_context,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer context graph/Leiden expander v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-prompt-chars", type=int, default=500)
    parser.add_argument("--min-community-annotations", type=int, default=0)
    parser.add_argument("--min-graph-relation-annotations", type=int, default=1)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-graph-prompt", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_citations=args.min_citations,
        min_prompt_chars=args.min_prompt_chars,
        min_community_annotations=args.min_community_annotations,
        min_graph_relation_annotations=args.min_graph_relation_annotations,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_graph_prompt=args.require_graph_prompt,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
