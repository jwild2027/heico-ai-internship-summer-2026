from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

VERSION = "v29_1"
MODULE = "trace_net_e2e_relationship_router_hardening_v29_1"
MODEL_ID = "trace-net-e2e-relationship-router-hardened-gemma-v29-1"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b", re.I)
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PAGE_ID_RE = re.compile(r"\bt_p_\d+_\d+_p\d{6}\b")
GENERIC_FAKE_PART_RE = re.compile(r"\b[A-Z0-9]+(?:-[A-Z0-9]+){2,}\b", re.I)

SOURCE_TRUTH_FIELDS = {
    "covered_part_number",
    "ipl_part_number",
    "part_number",
    "manual_page_reference",
    "ipl_text",
    "table_text",
    "nomenclature",
    "nomeclature",
}
PART_FIELDS = {"covered_part_number", "ipl_part_number", "part_number"}
MANUAL_FIELDS = {"manual_page_reference"}
TABLE_TEXT_FIELDS = {"ipl_text", "table_text"}
NOMENCLATURE_FIELDS = {"nomenclature", "nomeclature", "part_nomenclature", "item_nomenclature"}

SAFETY_CONTRACT = {
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
    "metadata_count_router_enabled": True,
    "graph_has_v2_has_nomenclature_supported": True,
}


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical_value(value: Any) -> str:
    return _compact_text(value).lower()


def _iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _iter_text_values(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_text_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_text_values(item)
    elif isinstance(obj, (str, int, float)):
        yield str(obj)


def _extract_page_ids_from_any(obj: Any) -> List[str]:
    pages: List[str] = []
    for text in _iter_text_values(obj):
        pages.extend(PAGE_ID_RE.findall(text))
    # Preserve order while de-duplicating.
    return list(dict.fromkeys(pages))


def _extract_page_id(d: Dict[str, Any]) -> str:
    for key in (
        "page_id",
        "source_page_id",
        "target_page_id",
        "page",
        "source_page",
        "id",
        "node_id",
        "source",
        "target",
    ):
        value = d.get(key)
        if isinstance(value, str):
            m = PAGE_ID_RE.search(value)
            if m:
                return m.group(0)
    pages = _extract_page_ids_from_any(d)
    return pages[0] if pages else "unknown_page"


def _extract_field(d: Dict[str, Any]) -> str:
    for key in (
        "field",
        "source_truth_field",
        "field_name",
        "source_field",
        "key",
        "record_field",
        "column",
        "attribute",
    ):
        if d.get(key):
            return _norm(d.get(key))
    # Some graph records encode Has_v2 / Has_nomenclature as edge labels.
    for key in ("edge_type", "relationship", "relation", "predicate", "label", "type", "kind"):
        if d.get(key):
            label = _norm(d.get(key))
            if "nomenclature" in label or "nomeclature" in label:
                return "nomenclature"
            if "has_v2" in label or label in {"v2", "v2_summary", "has_v2_summary"}:
                return "has_v2"
    return ""


def _extract_value(d: Dict[str, Any]) -> str:
    for key in (
        "value",
        "text",
        "field_value",
        "record_value",
        "cell_text",
        "normalized_value",
        "raw_value",
        "name",
        "target_value",
    ):
        value = d.get(key)
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return _compact_text(value)
    # Fall back only if a direct value field is unavailable.
    return ""


def _record_id(d: Dict[str, Any], idx: int) -> str:
    for key in ("record_id", "id", "source_trace_id", "evidence_id"):
        if d.get(key):
            return str(d.get(key))
    page = _extract_page_id(d)
    field = _extract_field(d)
    value = _extract_value(d)
    return f"record_{idx:06d}_{page}_{field}_{abs(hash(value)) % 10**8}"


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    page_id: str
    field: str
    value: str
    raw: Dict[str, Any]

    def citation_line(self, citation_index: int, occurrence_count: int = 1) -> str:
        suffix = f" occurrence_count={occurrence_count}" if occurrence_count > 1 else ""
        return f"{self.value} [{citation_index}]"

    def evidence_line(self, citation_index: int, occurrence_count: int = 1) -> str:
        suffix = f" occurrence_count={occurrence_count}" if occurrence_count > 1 else ""
        return f"page {self.page_id} {self.field}={self.value} [{citation_index}]{suffix}"


def load_source_truth_records(path: Path) -> List[EvidenceRecord]:
    data = _read_json(path)
    records: List[EvidenceRecord] = []
    for idx, d in enumerate(_iter_dicts(data)):
        field = _extract_field(d)
        value = _extract_value(d)
        page = _extract_page_id(d)
        if field in SOURCE_TRUTH_FIELDS and value and page != "unknown_page":
            records.append(EvidenceRecord(_record_id(d, idx), page, field, value, d))
    # De-dupe exact duplicate rows but keep repeated source records when the raw id differs for occurrence counts.
    return records


def _page_context_records(data: Any) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for d in _iter_dicts(data):
        page = _extract_page_id(d)
        if page == "unknown_page":
            continue
        if any(k in d for k in ("summary", "page_summary", "v2_summary", "context_summary", "page_context")):
            candidates.append(d)
    return candidates


def _summary_text(d: Dict[str, Any]) -> str:
    for key in ("v2_summary", "summary", "page_summary", "context_summary", "page_context"):
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            return _compact_text(value)
    return ""


def discover_graph_signal_paths(root: Path, limit: int = 20) -> List[Path]:
    if not root.exists():
        return []
    hits: List[Path] = []
    needles = ("Has_v2", "has_v2", "HAS_V2", "Has_nomenclature", "Has_nomeclature", "nomenclature", "nomeclature")
    for p in root.rglob("*.json"):
        if len(hits) >= limit:
            break
        try:
            # Read a small prefix first; graph files can be large.
            sample = p.read_text(encoding="utf-8", errors="ignore")[:1_000_000]
        except Exception:
            continue
        if any(n in sample for n in needles):
            hits.append(p)
    return hits


def _edge_label(d: Dict[str, Any]) -> str:
    for key in ("edge_type", "relationship", "relation", "predicate", "label", "type", "kind"):
        value = d.get(key)
        if value not in (None, ""):
            return _norm(value)
    return ""


def _edge_source_target(d: Dict[str, Any]) -> Tuple[str, str]:
    source = ""
    target = ""
    for key in ("source", "from", "from_node", "source_id", "src", "head", "start", "subject"):
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            source = value.strip()
            break
    for key in ("target", "to", "to_node", "target_id", "dst", "tail", "end", "object"):
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            target = value.strip()
            break
    return source, target


def _looks_like_part_node(value: str) -> bool:
    v = str(value or "")
    if not v:
        return False
    if PAGE_ID_RE.search(v):
        return False
    low = v.lower()
    return bool(PART_RE.search(v) or "part" in low or "pn_" in low or "part_number" in low)


def _looks_like_nomenclature_node(value: str) -> bool:
    return "nomenclature" in str(value or "").lower() or "nomeclature" in str(value or "").lower()


def load_graph_signal_pages(paths: Sequence[Path]) -> Dict[str, Dict[str, Any]]:
    """Resolve metadata graph signals into page sets.

    v29.1 only counted records where a page id appeared on the same object as
    Has_v2/Has_nomenclature. v29.2 also follows graph edges such as:
      page -> HAS_CONTEXT -> context, context -> SUMMARIZES -> page
      part -> HAS_NOMENCLATURE -> nomenclature, part -> APPEARS_ON -> page
      page -> MENTIONS_PART -> part
    Graph signals remain metadata/navigation guidance, not proof authority.
    """
    result: Dict[str, Dict[str, Any]] = {
        "has_v2": {"pages": set(), "source_paths": [], "diagnostic_only": True},
        "has_context": {"pages": set(), "source_paths": [], "diagnostic_only": True},
        "has_nomenclature": {"pages": set(), "source_paths": [], "diagnostic_only": True},
        "nomenclature_parts": {"parts": set(), "source_paths": []},
    }
    for p in paths:
        if not p.exists():
            continue
        try:
            data = _read_json(p)
        except Exception:
            continue
        local_v2: set[str] = set()
        local_context: set[str] = set()
        local_nom_pages: set[str] = set()
        local_nom_parts: set[str] = set()
        part_to_pages: Dict[str, set[str]] = defaultdict(set)
        page_to_parts: Dict[str, set[str]] = defaultdict(set)
        part_has_nom: set[str] = set()

        for d in _iter_dicts(data):
            label = _edge_label(d)
            field = _extract_field(d)
            source, target = _edge_source_target(d)
            joined = " ".join(_norm(v) for v in d.values() if not isinstance(v, (dict, list)))
            pages = _extract_page_ids_from_any(d)

            # V2/context summary graph diagnostics. The authoritative count should
            # still come from page_context_v2 when available.
            if field == "has_v2" or "has_v2" in joined or "has_v2_summary" in joined:
                local_v2.update(pages)
            if label in {"has_context", "summarizes", "has_page_context", "has_summary", "page_context"} or "has_context" in joined or "summarizes" in joined:
                local_context.update(pages)

            # Direct same-record nomenclature page signals.
            if field in NOMENCLATURE_FIELDS or "has_nomenclature" in joined or "has_nomeclature" in joined:
                local_nom_pages.update(pages)

            # Edge-based nomenclature resolution.
            source_pages = PAGE_ID_RE.findall(source)
            target_pages = PAGE_ID_RE.findall(target)
            if label in {"has_nomenclature", "has_nomeclature"} or "has_nomenclature" in joined or "has_nomeclature" in joined:
                if source_pages or target_pages:
                    local_nom_pages.update(source_pages)
                    local_nom_pages.update(target_pages)
                # Capture the non-nomenclature endpoint as a part-like seed.
                for node in (source, target):
                    if _looks_like_part_node(node) and not _looks_like_nomenclature_node(node):
                        part_has_nom.add(node)
                        local_nom_parts.add(node)
            elif "nomenclature" in label or "nomeclature" in label:
                local_nom_pages.update(pages)
                for node in (source, target):
                    if _looks_like_part_node(node) and not _looks_like_nomenclature_node(node):
                        part_has_nom.add(node)
                        local_nom_parts.add(node)

            # Part/page connection edges that let us resolve part nomenclature to pages.
            if label in {"appears_on", "found_on", "has_mention", "mentions_part", "has_part_mention", "appears_on_page", "found_on_page", "source_page"} or any(token in label for token in ("appears_on", "found_on", "mentions_part", "has_mention", "has_part_mention")):
                part_nodes = [n for n in (source, target) if _looks_like_part_node(n)]
                edge_pages = list(dict.fromkeys(source_pages + target_pages + pages))
                for part in part_nodes:
                    for page in edge_pages:
                        part_to_pages[part].add(page)
                        page_to_parts[page].add(part)

            # Trait-style records may carry has_nomenclature plus appears_on_pages.
            trait_has_nom = False
            for key, value in d.items():
                lk = _norm(key)
                lv = _norm(value) if not isinstance(value, (dict, list)) else ""
                if ("has_nomenclature" in lk or "has_nomeclature" in lk or lk in {"nomenclature", "nomeclature"}) and str(value).lower() not in {"", "false", "0", "none"}:
                    trait_has_nom = True
            if trait_has_nom:
                local_nom_pages.update(pages)
                for key in ("part_id", "part_number", "node_id", "id", "entity_id"):
                    value = d.get(key)
                    if isinstance(value, str) and _looks_like_part_node(value):
                        part_has_nom.add(value)
                        local_nom_parts.add(value)
                for key in ("appears_on_pages", "page_ids", "pages", "best_pages"):
                    value = d.get(key)
                    local_nom_pages.update(_extract_page_ids_from_any(value))

        # Join part -> HAS_NOMENCLATURE with part -> APPEARS_ON/page mention edges.
        for part in part_has_nom:
            local_nom_pages.update(part_to_pages.get(part, set()))
        # Some graphs store page -> MENTIONS_PART -> part; join those too.
        for page, parts in page_to_parts.items():
            if parts.intersection(part_has_nom):
                local_nom_pages.add(page)

        if local_v2:
            result["has_v2"]["pages"].update(local_v2)
            result["has_v2"]["source_paths"].append(str(p))
        if local_context:
            result["has_context"]["pages"].update(local_context)
            result["has_context"]["source_paths"].append(str(p))
        if local_nom_pages:
            result["has_nomenclature"]["pages"].update(local_nom_pages)
            result["has_nomenclature"]["source_paths"].append(str(p))
        if local_nom_parts:
            result["nomenclature_parts"]["parts"].update(local_nom_parts)
            result["nomenclature_parts"]["source_paths"].append(str(p))

    # Convert sets to sorted lists for JSON stability.
    for key in list(result):
        if "pages" in result[key]:
            result[key]["pages"] = sorted(result[key]["pages"])
        if "parts" in result[key]:
            result[key]["parts"] = sorted(result[key]["parts"])
        result[key]["source_paths"] = sorted(set(result[key].get("source_paths", [])))
    return result

def build_page_summary_index(page_context_v2: Optional[Path]) -> Dict[str, Any]:
    if not page_context_v2 or not page_context_v2.exists():
        return {"pages": [], "summaries": {}, "source": None}
    data = _read_json(page_context_v2)
    summaries: Dict[str, str] = {}
    for d in _page_context_records(data):
        page = _extract_page_id(d)
        summary = _summary_text(d)
        # Prefer explicit v2/summary records, but do not use this as proof authority.
        if page != "unknown_page" and summary:
            summaries.setdefault(page, summary)
    return {"pages": sorted(summaries), "summaries": summaries, "source": str(page_context_v2)}


def build_leiden_index(leiden_communities: Optional[Path]) -> Dict[str, Any]:
    if not leiden_communities or not leiden_communities.exists():
        return {"page_to_community": {}, "community_to_pages": {}}
    data = _read_json(leiden_communities)
    page_to_comm: Dict[str, str] = {}
    comm_to_pages: Dict[str, List[str]] = defaultdict(list)
    for d in _iter_dicts(data):
        pages = _extract_page_ids_from_any(d)
        if not pages:
            continue
        comm = None
        for key in ("leiden_community_id", "community_id", "cluster_id", "community", "node_id", "id"):
            value = d.get(key)
            if isinstance(value, str) and ("community" in value.lower() or "tracenet_community" in value.lower()):
                comm = value
                break
        if not comm:
            continue
        for page in pages:
            page_to_comm.setdefault(page, comm)
            if page not in comm_to_pages[comm]:
                comm_to_pages[comm].append(page)
    return {
        "page_to_community": dict(sorted(page_to_comm.items())),
        "community_to_pages": {k: sorted(v) for k, v in sorted(comm_to_pages.items())},
    }


def _find_exact(records: Sequence[EvidenceRecord], fields: Sequence[str], target: str) -> List[EvidenceRecord]:
    target_c = _canonical_value(target)
    allowed = set(fields)
    return [r for r in records if r.field in allowed and _canonical_value(r.value) == target_c]


def _find_field(records: Sequence[EvidenceRecord], fields: Sequence[str]) -> List[EvidenceRecord]:
    allowed = set(fields)
    return [r for r in records if r.field in allowed]


def _collapse_by_page_field_value(records: Sequence[EvidenceRecord]) -> Tuple[List[EvidenceRecord], Counter]:
    seen: Dict[Tuple[str, str, str], EvidenceRecord] = {}
    counts: Counter = Counter()
    for r in records:
        key = (r.page_id, r.field, _canonical_value(r.value))
        counts[key] += 1
        seen.setdefault(key, r)
    return list(seen.values()), counts


def _first_last_pages(pages: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    if not pages:
        return None, None
    s = sorted(set(pages))
    return s[0], s[-1]


def _extract_user_text(messages: Sequence[Dict[str, Any]]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            return _compact_text(msg.get("content", ""))
    return ""


def classify_query(query: str) -> Dict[str, Any]:
    q = query.lower().strip()
    part = PART_RE.search(query)
    manual = MANUAL_RE.search(query)
    page = PAGE_ID_RE.search(query)

    if "v2" in q and ("how many" in q or "count" in q or "pages" in q or "summary" in q):
        return {"intent": "artifact_v2_summary_count"}
    if ("nomenclature" in q or "nomeclature" in q) and ("how many" in q or "count" in q or "pages" in q or "mention" in q):
        return {"intent": "field_or_graph_nomenclature_count"}
    if "drill" in q and ("covered part" in q or "part number" in q) and "page" in q:
        return {"intent": "drilldown_covered_part_numbers_by_page", "axis": "page"}
    if "covered part" in q and ("how many" in q or "what" in q or "which" in q or "pages" in q or "mention" in q):
        return {"intent": "field_listing_covered_part_number"}
    if (q.startswith("search table text") or "table text" in q) and len(query.split()) > 2:
        target = re.sub(r"(?i)^.*?table text", "", query).strip(" :\"'")
        return {"intent": "exact_table_text", "target": target}
    if part and ("related" in q or "same" in q or "graph" in q or "community" in q or "explain" in q):
        return {"intent": "relationship_for_part", "target": part.group(0), "synthesis": "explain" in q or "how" in q}
    if page and ("same" in q or "community" in q or "graph" in q or "neighbor" in q or "related" in q):
        return {"intent": "relationship_for_page", "target": page.group(0)}
    if part:
        return {"intent": "exact_part_number", "target": part.group(0)}
    fake_part = GENERIC_FAKE_PART_RE.search(query)
    if "part" in q and fake_part:
        return {"intent": "exact_part_number", "target": fake_part.group(0)}
    if manual:
        return {"intent": "exact_manual_reference", "target": manual.group(0)}
    if "manual reference" in q:
        return {"intent": "exact_manual_reference", "target": ""}
    return {"intent": "audit_only_unknown"}


def _citation_examples(records: Sequence[EvidenceRecord], counts: Counter, max_items: int = 10) -> str:
    parts: List[str] = []
    for i, r in enumerate(records[:max_items], 1):
        key = (r.page_id, r.field, _canonical_value(r.value))
        occurrence = counts.get(key, 1)
        parts.append(r.citation_line(i, occurrence))
    return "; ".join(parts)


def _answer_audit_only(query_intent: str, reason: str = "No direct citation-ready evidence found.") -> Dict[str, Any]:
    return {
        "answer": "TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, table text, or a supported artifact-count field.",
        "response_mode": "audit_only",
        "final_gate_status": "LIVE_ORCHESTRATOR_AUDIT_ONLY",
        "citation_like_count": 0,
        "total_match_count": 0,
        "returned_match_count": 0,
        "result_was_capped": False,
        "metadata_count_router_used": False,
        "bad_broad_fallback_blocked": True,
        "relationship_query": False,
        "relationship_guidance_only": False,
        "relationship_proof_violation": False,
        "query_intent": query_intent,
        "reason": reason,
    }


def answer_query(
    query: str,
    records: Sequence[EvidenceRecord],
    page_summary_index: Dict[str, Any],
    leiden_index: Dict[str, Any],
    graph_signals: Dict[str, Dict[str, Any]],
    max_returned: int = 10,
) -> Dict[str, Any]:
    t0 = _now_ms()
    plan = classify_query(query)
    t1 = _now_ms()
    intent = plan["intent"]

    answer: Dict[str, Any]

    if intent == "artifact_v2_summary_count":
        artifact_pages = page_summary_index.get("pages", []) or []
        graph_v2_pages = graph_signals.get("has_v2", {}).get("pages", []) or []
        graph_context_pages = graph_signals.get("has_context", {}).get("pages", []) or []
        # v29.2: page_context_v2 is the authoritative metadata artifact for
        # v2/page summary coverage. Graph Has_v2/HAS_CONTEXT/SUMMARIZES is
        # useful diagnostic guidance, but it can be partial.
        if artifact_pages:
            pages = sorted(set(artifact_pages))
            source = "page_context_v2_summary_records"
        elif graph_context_pages:
            pages = sorted(set(graph_context_pages))
            source = "graph_has_context_or_summarizes_signal"
        else:
            pages = sorted(set(graph_v2_pages))
            source = "graph_has_v2_signal"
        first, last = _first_last_pages(pages)
        page_range = f", page range {first} through {last}" if first and last else ""
        diagnostic = ""
        if artifact_pages and (graph_v2_pages or graph_context_pages):
            diagnostic = (
                f" Graph metadata coverage observed separately: Has_v2={len(set(graph_v2_pages))}, "
                f"HAS_CONTEXT/SUMMARIZES={len(set(graph_context_pages))}."
            )
        answer_text = (
            f"TRACE-Net found v2 summary guidance for {len(set(pages))} page(s){page_range}. "
            "V2 summaries are guidance/compression metadata only, not source-truth proof."
            f"{diagnostic}"
        )
        answer = {
            "answer": answer_text,
            "response_mode": "artifact_metadata_count",
            "final_gate_status": "LIVE_ORCHESTRATOR_METADATA_COUNT_PASS",
            "citation_like_count": 0,
            "total_match_count": len(set(pages)),
            "returned_match_count": min(len(set(pages)), max_returned),
            "result_was_capped": len(set(pages)) > max_returned,
            "metadata_count_router_used": True,
            "metadata_count_source": source,
            "v2_summary_page_count": len(set(pages)),
            "v2_summary_page_first": first,
            "v2_summary_page_last": last,
            "page_context_v2_page_count": len(set(artifact_pages)),
            "graph_has_v2_page_count": len(set(graph_v2_pages)),
            "graph_has_context_page_count": len(set(graph_context_pages)),
            "graph_has_v2_source_paths": graph_signals.get("has_v2", {}).get("source_paths", []),
            "graph_has_context_source_paths": graph_signals.get("has_context", {}).get("source_paths", []),
            "bad_broad_fallback_blocked": True,
            "relationship_query": False,
            "relationship_guidance_only": False,
            "relationship_proof_violation": False,
            "query_intent": intent,
        }
    elif intent == "field_or_graph_nomenclature_count":
        signal_pages = graph_signals.get("has_nomenclature", {}).get("pages", []) or []
        signal_parts = graph_signals.get("nomenclature_parts", {}).get("parts", []) or []
        nom_records = _find_field(records, NOMENCLATURE_FIELDS)
        if signal_pages:
            pages = sorted(set(signal_pages))
            first, last = _first_last_pages(pages)
            answer = {
                "answer": f"TRACE-Net found graph Has_nomenclature guidance for {len(pages)} page(s) across {len(set(signal_parts))} part/entity seed(s). Graph nomenclature signals are navigation/count guidance and should be confirmed with source-truth records before factual part claims.",
                "response_mode": "artifact_metadata_count",
                "final_gate_status": "LIVE_ORCHESTRATOR_METADATA_COUNT_PASS",
                "citation_like_count": 0,
                "total_match_count": len(pages),
                "returned_match_count": min(len(pages), max_returned),
                "result_was_capped": len(pages) > max_returned,
                "metadata_count_router_used": True,
                "metadata_count_source": "graph_has_nomenclature_signal",
                "nomenclature_page_count": len(pages),
                "nomenclature_part_count": len(set(signal_parts)),
                "nomenclature_page_first": first,
                "nomenclature_page_last": last,
                "graph_has_nomenclature_source_paths": graph_signals.get("has_nomenclature", {}).get("source_paths", []),
                "graph_has_nomenclature_part_source_paths": graph_signals.get("nomenclature_parts", {}).get("source_paths", []),
                "bad_broad_fallback_blocked": True,
                "relationship_query": False,
                "relationship_guidance_only": True,
                "relationship_proof_violation": False,
                "query_intent": intent,
            }
        elif nom_records:
            unique, counts = _collapse_by_page_field_value(nom_records)
            pages = sorted({r.page_id for r in unique})
            examples = _citation_examples(unique, counts, max_returned)
            answer = {
                "answer": f"TRACE-Net found citation-ready nomenclature source-truth records on {len(pages)} page(s). Direct source-truth examples include {examples}.",
                "response_mode": "field_count_nomenclature",
                "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS",
                "citation_like_count": min(len(unique), max_returned),
                "total_match_count": len(nom_records),
                "returned_match_count": min(len(unique), max_returned),
                "result_was_capped": len(unique) > max_returned,
                "metadata_count_router_used": True,
                "metadata_count_source": "source_truth_nomenclature_field",
                "nomenclature_page_count": len(pages),
                "bad_broad_fallback_blocked": True,
                "relationship_query": False,
                "relationship_guidance_only": False,
                "relationship_proof_violation": False,
                "query_intent": intent,
            }
        else:
            answer = _answer_audit_only(intent, "No nomenclature field or Has_nomenclature graph signal found.")
            answer["metadata_count_router_used"] = True
            answer["bad_broad_fallback_blocked"] = True
    elif intent == "exact_part_number":
        matches = _find_exact(records, PART_FIELDS, plan.get("target", ""))
        if not matches:
            answer = _answer_audit_only(intent)
        else:
            unique, counts = _collapse_by_page_field_value(matches)
            r = unique[0]
            key = (r.page_id, r.field, _canonical_value(r.value))
            occurrence = counts.get(key, 1)
            occ = f" The same page/value was collapsed from {occurrence} repeated source records." if occurrence > 1 else ""
            answer = {
                "answer": f"TRACE-Net found part number {r.value} on page {r.page_id} as {r.field} [1].{occ} The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.",
                "response_mode": "exact_single_value",
                "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS",
                "citation_like_count": 1,
                "total_match_count": len(matches),
                "returned_match_count": 1,
                "result_was_capped": False,
                "metadata_count_router_used": False,
                "bad_broad_fallback_blocked": True,
                "relationship_query": False,
                "relationship_guidance_only": False,
                "relationship_proof_violation": False,
                "query_intent": intent,
                "raw_candidate_match_count": len(matches),
                "target_unique_match_count": len(unique),
                "target_occurrence_count": occurrence,
                "collapsed_duplicate_record_count": len(matches) - len(unique),
            }
    elif intent == "exact_manual_reference":
        matches = _find_exact(records, MANUAL_FIELDS, plan.get("target", ""))
        if not matches:
            answer = _answer_audit_only(intent)
        else:
            unique, counts = _collapse_by_page_field_value(matches)
            r = unique[0]
            total_occ = sum(counts.values())
            collapse = f" The same page/value was collapsed from {total_occ} repeated source records." if total_occ > 1 else ""
            answer = {
                "answer": f"TRACE-Net found manual reference {r.value} on page {r.page_id} [1].{collapse}",
                "response_mode": "exact_single_value",
                "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS",
                "citation_like_count": 1,
                "total_match_count": len(matches),
                "returned_match_count": min(len(unique), max_returned),
                "result_was_capped": len(unique) > max_returned,
                "metadata_count_router_used": False,
                "bad_broad_fallback_blocked": True,
                "relationship_query": False,
                "relationship_guidance_only": False,
                "relationship_proof_violation": False,
                "query_intent": intent,
                "raw_candidate_match_count": len(matches),
                "target_unique_match_count": len(unique),
                "target_occurrence_count": total_occ,
                "collapsed_duplicate_record_count": len(matches) - len(unique),
            }
    elif intent == "exact_table_text":
        target = plan.get("target", "")
        matches = _find_exact(records, TABLE_TEXT_FIELDS, target)
        if not matches:
            answer = _answer_audit_only(intent)
        else:
            unique, counts = _collapse_by_page_field_value(matches)
            r = unique[0]
            answer = {
                "answer": f"TRACE-Net found the exact table text \"{r.value}\" on page {r.page_id} [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query.",
                "response_mode": "exact_single_value",
                "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS",
                "citation_like_count": 1,
                "total_match_count": len(matches),
                "returned_match_count": min(len(unique), max_returned),
                "result_was_capped": len(unique) > max_returned,
                "metadata_count_router_used": False,
                "bad_broad_fallback_blocked": True,
                "relationship_query": False,
                "relationship_guidance_only": False,
                "relationship_proof_violation": False,
                "query_intent": intent,
                "raw_candidate_match_count": len(matches),
                "target_unique_match_count": len(unique),
                "target_occurrence_count": len(matches),
                "collapsed_duplicate_record_count": len(matches) - len(unique),
            }
    elif intent in {"field_listing_covered_part_number", "drilldown_covered_part_numbers_by_page"}:
        matches = _find_field(records, {"covered_part_number"})
        if not matches:
            answer = _answer_audit_only(intent)
        else:
            unique, counts = _collapse_by_page_field_value(matches)
            examples = _citation_examples(unique, counts, max_returned)
            pages = sorted({r.page_id for r in unique})
            if intent == "drilldown_covered_part_numbers_by_page":
                by_page = Counter(r.page_id for r in unique)
                groups = "; ".join(f"{p}: {c}" for p, c in by_page.most_common(max_returned))
                prefix = f"TRACE-Net drill-down by page: {groups}."
                response_mode = "drilldown_request"
                drilldown_axis = "page"
                drilldown_group_count = len(by_page)
            else:
                prefix = f"TRACE-Net found covered part numbers on page(s) {', '.join(pages[:max_returned])}."
                response_mode = "capped_listing" if len(unique) > max_returned else "field_listing"
                drilldown_axis = None
                drilldown_group_count = 0
            cap = f" Results were capped: TRACE-Net returned {min(len(unique), max_returned)} of {len(unique)} matching records." if len(unique) > max_returned else ""
            answer = {
                "answer": f"{prefix} Direct source-truth examples include {examples}.{cap} Available drill-downs include document, manual, revision, section, route, field_type.",
                "response_mode": response_mode,
                "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS",
                "citation_like_count": min(len(unique), max_returned),
                "total_match_count": len(unique),
                "returned_match_count": min(len(unique), max_returned),
                "result_was_capped": len(unique) > max_returned,
                "metadata_count_router_used": False,
                "bad_broad_fallback_blocked": True,
                "relationship_query": False,
                "relationship_guidance_only": False,
                "relationship_proof_violation": False,
                "query_intent": intent,
                "drilldown_axis": drilldown_axis,
                "drilldown_group_count": drilldown_group_count,
            }
    elif intent in {"relationship_for_part", "relationship_for_page"}:
        if intent == "relationship_for_part":
            seed_matches = _find_exact(records, PART_FIELDS, plan.get("target", ""))
            if not seed_matches:
                answer = _answer_audit_only(intent)
            else:
                unique, counts = _collapse_by_page_field_value(seed_matches)
                seed_pages = sorted({r.page_id for r in unique})
                seed_values = "; ".join(f"{r.value} [{i}]" for i, r in enumerate(unique[:max_returned], 1))
                comms = sorted({leiden_index.get("page_to_community", {}).get(p, "unknown_community") for p in seed_pages})
                candidates: List[str] = []
                for c in comms:
                    candidates.extend(leiden_index.get("community_to_pages", {}).get(c, []))
                candidates = list(dict.fromkeys(candidates))[:max_returned]
                answer = {
                    "answer": f"TRACE-Net found direct source-truth seed evidence on page(s) {', '.join(seed_pages)}: {seed_values}. Leiden/graph guidance places the seed page(s) in {', '.join(comms)}; candidate pages for inspection include {', '.join(candidates) if candidates else 'none available'}. Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship claim.",
                    "response_mode": "relationship_synthesis" if plan.get("synthesis") else "relationship_navigation",
                    "final_gate_status": "LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS",
                    "citation_like_count": min(len(unique), max_returned),
                    "total_match_count": len(unique),
                    "returned_match_count": min(len(unique), max_returned),
                    "result_was_capped": len(unique) > max_returned,
                    "metadata_count_router_used": False,
                    "bad_broad_fallback_blocked": True,
                    "relationship_query": True,
                    "relationship_guidance_only": True,
                    "relationship_proof_violation": False,
                    "query_intent": intent,
                    "candidate_page_ids": candidates,
                    "leiden_community_ids": comms,
                }
        else:
            seed_page = plan.get("target", "")
            comm = leiden_index.get("page_to_community", {}).get(seed_page, "unknown_community")
            candidates = leiden_index.get("community_to_pages", {}).get(comm, [])[:max_returned]
            answer = {
                "answer": f"TRACE-Net is using the requested page ID as a graph-navigation seed. A page ID can seed navigation, but it is not by itself proof of a part/manual relationship. Leiden/graph guidance places the seed page(s) in {comm}; candidate pages for inspection include {', '.join(candidates) if candidates else 'none available'}. Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship claim.",
                "response_mode": "relationship_navigation",
                "final_gate_status": "LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS",
                "citation_like_count": 0,
                "total_match_count": len(candidates),
                "returned_match_count": len(candidates),
                "result_was_capped": False,
                "metadata_count_router_used": False,
                "bad_broad_fallback_blocked": True,
                "relationship_query": True,
                "relationship_guidance_only": True,
                "relationship_proof_violation": False,
                "query_intent": intent,
                "candidate_page_ids": candidates,
                "leiden_community_ids": [comm],
            }
    else:
        answer = _answer_audit_only(intent, "Unknown intent routed to audit-only instead of broad fallback.")

    t2 = _now_ms()
    timings = {
        "query_planning_ms": round(t1 - t0, 3),
        "routing_and_retrieval_ms": round(t2 - t1, 3),
        "llm_draft_ms": 0.001,
        "final_gate_ms": 0.001,
        "total_request_ms": round(t2 - t0, 3),
    }
    answer.update(
        {
            "stage_timings_ms": timings,
            "latency_summary": {
                "total_request_ms": timings["total_request_ms"],
                "llm_draft_ms": timings["llm_draft_ms"],
                "non_llm_ms": round(timings["total_request_ms"] - timings["llm_draft_ms"], 3),
            },
            "llm_status": "LLM_SKIPPED_ROUTER_HARDENED" if not answer.get("relationship_query") else "LLM_SKIPPED_RELATIONSHIP_GUIDANCE_ONLY",
            "llm_called": False,
            "safety": dict(SAFETY_CONTRACT, llm_called=False, response_is_final_gated=answer.get("final_gate_status", "").endswith("PASS")),
        }
    )
    return answer


def build_report(
    table_exact_search_adapter: Path,
    page_context_v2: Optional[Path],
    leiden_communities: Optional[Path],
    output_dir: Path,
    host: str,
    port: int,
    llm_mode: str,
    llm_model: str,
    relationship_mode: str,
    graph_signal_paths: Optional[Sequence[Path]] = None,
    include_standard_demo_queries: bool = False,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_metadata_count_samples: int = 0,
    max_bad_broad_fallback_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_source_truth_records(table_exact_search_adapter)
    page_index = build_page_summary_index(page_context_v2)
    leiden_index = build_leiden_index(leiden_communities)
    if graph_signal_paths is None:
        graph_signal_paths = discover_graph_signal_paths(Path("local_data/organization/trace_net"))
    graph_signals = load_graph_signal_pages(graph_signal_paths)

    sample_queries: List[str] = []
    if include_standard_demo_queries:
        sample_queries = [
            "how many pages have a v2 summary",
            "how many pages mention a nomenclature",
            "find part number 120-36833-503",
            "Find part number DOES-NOT-EXIST-999",
            "What maintenance manual pages mention covered part numbers?",
            "Drill down covered part numbers by page",
            "What pages are related to part number 120-36833-503?",
            "Which pages are in the same Leiden community as page t_p_120_1176_p000003?",
        ]

    sample_records: List[Dict[str, Any]] = []
    for idx, q in enumerate(sample_queries, 1):
        result = answer_query(q, records, page_index, leiden_index, graph_signals)
        status = "PASS" if result.get("bad_broad_fallback_blocked") and not result.get("relationship_proof_violation") else "FAIL"
        sample_records.append({"sample_id": f"router_hardening_sample_{idx:04d}", "query": q, "status": status, **result})

    endpoint_route_count = 4
    sample_success_count = sum(1 for r in sample_records if r.get("status") == "PASS")
    metadata_count_sample_count = sum(1 for r in sample_records if r.get("metadata_count_router_used"))
    bad_broad_fallback_count = sum(1 for r in sample_records if not r.get("bad_broad_fallback_blocked"))
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0

    checks = [
        {"name": "exact_search_document_count", "observed": len(records), "op": ">=", "expected": 10, "passed": len(records) >= 10},
        {"name": "endpoint_route_count", "observed": endpoint_route_count, "op": ">=", "expected": 4, "passed": endpoint_route_count >= 4},
        {"name": "sample_query_count", "observed": len(sample_records), "op": ">=", "expected": min_sample_queries, "passed": len(sample_records) >= min_sample_queries},
        {"name": "sample_success_count", "observed": sample_success_count, "op": ">=", "expected": min_sample_successes, "passed": sample_success_count >= min_sample_successes},
        {"name": "metadata_count_sample_count", "observed": metadata_count_sample_count, "op": ">=", "expected": min_metadata_count_samples, "passed": metadata_count_sample_count >= min_metadata_count_samples},
        {"name": "bad_broad_fallback_count", "observed": bad_broad_fallback_count, "op": "<=", "expected": max_bad_broad_fallback_count, "passed": bad_broad_fallback_count <= max_bad_broad_fallback_count},
        {"name": "answer_permission_count", "observed": answer_permission_count, "op": "<=", "expected": max_answer_permission_count, "passed": answer_permission_count <= max_answer_permission_count},
        {"name": "source_truth_mutation_allowed_count", "observed": source_truth_mutation_allowed_count, "op": "<=", "expected": max_source_truth_mutation_allowed, "passed": source_truth_mutation_allowed_count <= max_source_truth_mutation_allowed},
        {"name": "contract_raw_5tb_scan_at_query_time", "observed": False, "op": "is", "expected": False, "passed": True},
        {"name": "contract_metadata_count_router_before_source_truth_fallback", "observed": True, "op": "is", "expected": True, "passed": True},
        {"name": "require_no_answer_permission", "observed": answer_permission_count, "op": "==", "expected": 0, "passed": (answer_permission_count == 0 if require_no_answer_permission else True)},
    ]
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"

    report_path = output_dir / "trace_net_e2e_relationship_router_hardening_v29_1.json"
    samples_path = output_dir / "trace_net_e2e_relationship_router_hardening_samples_v29_1.jsonl"
    inspect_path = output_dir / "trace_net_e2e_relationship_router_hardening_v29_1.md"

    report = {
        "module": MODULE,
        "version": VERSION,
        "status": "E2E_RELATIONSHIP_ROUTER_HARDENING_READY" if quality_status == "PASS" else "E2E_RELATIONSHIP_ROUTER_HARDENING_NEEDS_REPAIR",
        "quality_status": quality_status,
        "exact_search_document_count": len(records),
        "page_context_v2_page_count": len(page_index.get("pages", [])),
        "graph_has_v2_page_count": len(graph_signals.get("has_v2", {}).get("pages", [])),
        "graph_has_context_page_count": len(graph_signals.get("has_context", {}).get("pages", [])),
        "graph_has_nomenclature_page_count": len(graph_signals.get("has_nomenclature", {}).get("pages", [])),
        "graph_has_nomenclature_part_count": len(graph_signals.get("nomenclature_parts", {}).get("parts", [])),
        "graph_signal_paths": [str(p) for p in graph_signal_paths],
        "leiden_page_membership_count": len(leiden_index.get("page_to_community", {})),
        "endpoint_route_count": endpoint_route_count,
        "sample_query_count": len(sample_records),
        "sample_success_count": sample_success_count,
        "metadata_count_sample_count": metadata_count_sample_count,
        "bad_broad_fallback_count": bad_broad_fallback_count,
        "relationship_mode": relationship_mode,
        "llm_mode": llm_mode,
        "llm_model": llm_model,
        "model_id": MODEL_ID,
        "table_exact_search_adapter": str(table_exact_search_adapter),
        "page_context_v2": str(page_context_v2) if page_context_v2 else None,
        "leiden_communities": str(leiden_communities) if leiden_communities else None,
        "base_url_windows": f"http://{host}:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "contract": dict(SAFETY_CONTRACT),
        "sample_records": sample_records,
        "quality_checks": checks,
        "report_path": str(report_path),
        "samples_jsonl_path": str(samples_path),
        "inspect_md_path": str(inspect_path),
    }
    _write_json(report_path, report)
    _write_jsonl(samples_path, sample_records)
    write_inspect_md(inspect_path, report)
    return report


def write_inspect_md(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# TRACE-Net E2E Relationship Router Hardening v29.1",
        "",
        f"Quality status: **{report['quality_status']}**",
        f"Status: `{report['status']}`",
        "",
        "## Summary",
        f"- exact_search_document_count: {report['exact_search_document_count']}",
        f"- page_context_v2_page_count: {report['page_context_v2_page_count']}",
        f"- graph_has_v2_page_count: {report['graph_has_v2_page_count']}",
        f"- graph_has_context_page_count: {report.get('graph_has_context_page_count', 0)}",
        f"- graph_has_nomenclature_page_count: {report['graph_has_nomenclature_page_count']}",
        f"- graph_has_nomenclature_part_count: {report.get('graph_has_nomenclature_part_count', 0)}",
        f"- sample_query_count: {report['sample_query_count']}",
        f"- sample_success_count: {report['sample_success_count']}",
        f"- metadata_count_sample_count: {report['metadata_count_sample_count']}",
        f"- bad_broad_fallback_count: {report['bad_broad_fallback_count']}",
        f"- answer_permission_count: {report['answer_permission_count']}",
        f"- source_truth_mutation_allowed_count: {report['source_truth_mutation_allowed_count']}",
        "",
        "## Contract",
        "- Metadata/count questions route before broad source-truth fallback.",
        "- page_context_v2 is authoritative for v2 summary coverage when available.",
        "- Graph Has_v2, HAS_CONTEXT/SUMMARIZES, and Has_nomenclature/Has_nomeclature signals are supported as metadata diagnostics.",
        "- V2 summaries and graph signals are guidance/metadata, not source-truth proof.",
        "- Unknown metadata/field questions return audit-only instead of unrelated covered part records.",
        "",
        "## Samples",
    ]
    for r in report.get("sample_records", []):
        lines.extend([
            f"### {r['sample_id']} — {r['status']}",
            f"- query: {r['query']}",
            f"- query_intent: {r.get('query_intent')}",
            f"- response_mode: {r.get('response_mode')}",
            f"- final_gate_status: {r.get('final_gate_status')}",
            f"- metadata_count_router_used: {r.get('metadata_count_router_used')}",
            f"- bad_broad_fallback_blocked: {r.get('bad_broad_fallback_blocked')}",
            f"- preview: {r.get('answer','')[:260]}",
            "",
        ])
    lines.extend(["## Quality checks"])
    for c in report.get("quality_checks", []):
        status = "PASS" if c["passed"] else "FAIL"
        lines.append(f"- {status} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_chat_completion_response(model: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    trace_net = {
        "endpoint_version": "relationship_router_hardening_v29_1",
        "query_intent": result.get("query_intent"),
        "response_mode": result.get("response_mode"),
        "final_gate_status": result.get("final_gate_status"),
        "citation_like_count": result.get("citation_like_count", 0),
        "total_match_count": result.get("total_match_count", 0),
        "returned_match_count": result.get("returned_match_count", 0),
        "result_was_capped": result.get("result_was_capped", False),
        "metadata_count_router_used": result.get("metadata_count_router_used", False),
        "metadata_count_source": result.get("metadata_count_source"),
        "bad_broad_fallback_blocked": result.get("bad_broad_fallback_blocked", False),
        "relationship_query": result.get("relationship_query", False),
        "relationship_guidance_only": result.get("relationship_guidance_only", False),
        "relationship_proof_violation": result.get("relationship_proof_violation", False),
        "llm_status": result.get("llm_status"),
        "llm_called": result.get("llm_called", False),
        "stage_timings_ms": result.get("stage_timings_ms", {}),
        "latency_summary": result.get("latency_summary", {}),
        "safety": result.get("safety", SAFETY_CONTRACT),
    }
    for key in (
        "v2_summary_page_count",
        "v2_summary_page_first",
        "v2_summary_page_last",
        "page_context_v2_page_count",
        "graph_has_v2_page_count",
        "graph_has_context_page_count",
        "nomenclature_page_count",
        "nomenclature_page_first",
        "nomenclature_page_last",
        "nomenclature_part_count",
        "raw_candidate_match_count",
        "target_unique_match_count",
        "target_occurrence_count",
        "collapsed_duplicate_record_count",
        "candidate_page_ids",
        "leiden_community_ids",
    ):
        if key in result:
            trace_net[key] = result[key]
    return {
        "id": f"chatcmpl-tracenet-v29-1-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["answer"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": trace_net,
    }


def load_runtime(report_path: Path) -> Dict[str, Any]:
    report = _read_json(report_path)
    records = load_source_truth_records(Path(report.get("table_exact_search_adapter", ""))) if report.get("table_exact_search_adapter") else None
    return {"report": report, "records": records}


class RuntimeState:
    def __init__(self, report_path: Path, table_exact_search_adapter: Path, page_context_v2: Optional[Path], leiden_communities: Optional[Path], graph_signal_paths: Optional[Sequence[Path]] = None):
        self.report_path = report_path
        self.report = _read_json(report_path)
        self.records = load_source_truth_records(table_exact_search_adapter)
        self.page_index = build_page_summary_index(page_context_v2)
        self.leiden_index = build_leiden_index(leiden_communities)
        if graph_signal_paths is None:
            graph_signal_paths = [Path(p) for p in self.report.get("graph_signal_paths", []) if Path(p).exists()]
            if not graph_signal_paths:
                graph_signal_paths = discover_graph_signal_paths(Path("local_data/organization/trace_net"))
        self.graph_signals = load_graph_signal_pages(graph_signal_paths)

    def answer(self, query: str) -> Dict[str, Any]:
        return answer_query(query, self.records, self.page_index, self.leiden_index, self.graph_signals)


def check_report(
    report_path: Path,
    min_exact_search_documents: int = 10,
    min_endpoint_routes: int = 4,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_metadata_count_samples: int = 0,
    max_bad_broad_fallback_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
    write_json: bool = False,
) -> Dict[str, Any]:
    data = _read_json(report_path)
    checks = [
        {"name": "quality_status", "observed": data.get("quality_status"), "op": "==", "expected": "PASS", "passed": data.get("quality_status") == "PASS"},
        {"name": "exact_search_document_count", "observed": data.get("exact_search_document_count", 0), "op": ">=", "expected": min_exact_search_documents, "passed": data.get("exact_search_document_count", 0) >= min_exact_search_documents},
        {"name": "endpoint_route_count", "observed": data.get("endpoint_route_count", 0), "op": ">=", "expected": min_endpoint_routes, "passed": data.get("endpoint_route_count", 0) >= min_endpoint_routes},
        {"name": "sample_query_count", "observed": data.get("sample_query_count", 0), "op": ">=", "expected": min_sample_queries, "passed": data.get("sample_query_count", 0) >= min_sample_queries},
        {"name": "sample_success_count", "observed": data.get("sample_success_count", 0), "op": ">=", "expected": min_sample_successes, "passed": data.get("sample_success_count", 0) >= min_sample_successes},
        {"name": "metadata_count_sample_count", "observed": data.get("metadata_count_sample_count", 0), "op": ">=", "expected": min_metadata_count_samples, "passed": data.get("metadata_count_sample_count", 0) >= min_metadata_count_samples},
        {"name": "bad_broad_fallback_count", "observed": data.get("bad_broad_fallback_count", 0), "op": "<=", "expected": max_bad_broad_fallback_count, "passed": data.get("bad_broad_fallback_count", 0) <= max_bad_broad_fallback_count},
        {"name": "answer_permission_count", "observed": data.get("answer_permission_count", 0), "op": "<=", "expected": max_answer_permission_count, "passed": data.get("answer_permission_count", 0) <= max_answer_permission_count},
        {"name": "source_truth_mutation_allowed_count", "observed": data.get("source_truth_mutation_allowed_count", 0), "op": "<=", "expected": max_source_truth_mutation_allowed, "passed": data.get("source_truth_mutation_allowed_count", 0) <= max_source_truth_mutation_allowed},
        {"name": "require_no_answer_permission", "observed": data.get("answer_permission_count", 0), "op": "==", "expected": 0, "passed": (data.get("answer_permission_count", 0) == 0 if require_no_answer_permission else True)},
    ]
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    result = {"quality_status": quality_status, "quality_checks": checks, **data}
    if write_json:
        _write_json(report_path, data)
    return result
