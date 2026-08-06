"""TRACE-Net Page Retrieval Large Eval v2.

This module builds one graph-path-constrained retrieval/LLM test card per page.
It is read-only: it never writes to Postgres, Qdrant, OpenSearch, or source truth.

The v2 eval differs from the earlier large eval by explicitly checking that every
LLM-facing question has a required graph route, source identity, and answer-safety
contract. Optional Qdrant evaluation measures semantic routing, but the expected
LLM behavior is graph-first/source-resolved rather than vector-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_page_retrieval_large_eval_v2"
STATUS_BUILT = "PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

DEFAULT_COLLECTION = "trace_net_page_retrieval_profiles_ollama_bge_m3_v1"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "bge-m3:latest"

PAGE_ID_RE = re.compile(r"^(?P<prefix>.+)_p(?P<num>\d{6})$")
TIFF_RE = re.compile(r"(?P<num>\d{6})\.tif$", re.IGNORECASE)


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def stable_id(*parts: Any, prefix: str = "evalv2") -> str:
    text = "::".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{digest}"


def page_num_to_id(page_number: int, doc_prefix: str = "t_p_120_1176") -> str:
    return f"{doc_prefix}_p{page_number:06d}"


def page_id_to_number(page_id: str) -> int | None:
    m = PAGE_ID_RE.match(page_id or "")
    if not m:
        return None
    try:
        return int(m.group("num"))
    except ValueError:
        return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def compact_text(value: Any, *, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        text = "; ".join(compact_text(v, max_chars=max_chars) for v in value)
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def find_first(record: dict[str, Any], candidates: list[str]) -> Any:
    for key in candidates:
        if key in record and record[key] not in (None, "", [], {}):
            return record[key]
    return None


def recursive_find_values(obj: Any, key_patterns: tuple[str, ...]) -> list[Any]:
    out: list[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if any(pattern in key_l for pattern in key_patterns) and value not in (None, "", [], {}):
                out.append(value)
            out.extend(recursive_find_values(value, key_patterns))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(recursive_find_values(value, key_patterns))
    return out


def flatten_string_values(values: Iterable[Any], *, limit: int = 20) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                # Prefer readable dict fields before raw JSON.
                for k in ("text", "label", "value", "part_number", "query", "question", "cue", "summary"):
                    if k in item:
                        s = compact_text(item[k], max_chars=200)
                        if s and s not in seen:
                            seen.add(s)
                            out.append(s)
                            break
            else:
                s = compact_text(item, max_chars=200)
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)
            if len(out) >= limit:
                return out
    return out


def load_metadata_zip_pages(metadata_zip: str | Path, first_pages: int) -> dict[str, dict[str, Any]]:
    path = Path(metadata_zip)
    if not path.exists():
        raise FileNotFoundError(f"Missing metadata zip: {path}")

    pages: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            m = TIFF_RE.search(name)
            if not m:
                continue
            page_number = int(m.group("num"))
            if page_number < 1 or page_number > first_pages:
                continue
            page_id = page_num_to_id(page_number)
            pages[page_id] = {
                "page_id": page_id,
                "page_number": page_number,
                "zip_entry_name": name,
                "zip_entry_size_bytes": info.file_size,
                "zip_entry_compressed_size_bytes": info.compress_size,
                "blank_by_zip_size": info.file_size <= 6000,
            }
    return pages


def load_profiles(profiles_path: str | Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], str | None]:
    payload = load_json(profiles_path)
    records = payload.get("page_profiles") or payload.get("records") or payload.get("profiles") or []
    if not isinstance(records, list):
        raise TypeError("Expected page profile list under page_profiles/records/profiles")
    by_page: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        page_id = record.get("page_id") or record.get("id") or record.get("page")
        if page_id:
            by_page[str(page_id)] = record
    quality_status = (
        payload.get("quality_status")
        or (payload.get("summary") or {}).get("status")
        or (payload.get("summary") or {}).get("quality_status")
    )
    return records, by_page, quality_status


def extract_profile_signals(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {
            "role": None,
            "subrole": None,
            "retrieval_summary": "",
            "retrieval_cues": [],
            "answerable_questions": [],
            "part_numbers": [],
            "ata_codes": [],
            "has_context_v2": False,
            "has_source_trace": False,
        }

    text_all = json.dumps(profile, ensure_ascii=False).lower()
    role = find_first(profile, ["role", "page_role", "page_context_role"])
    subrole = find_first(profile, ["subrole", "page_subrole", "page_context_subrole"])

    retrieval_summary = find_first(
        profile,
        ["retrieval_summary", "summary", "short_summary", "page_summary", "context_v2_summary"],
    )
    if not retrieval_summary:
        values = recursive_find_values(profile, ("retrieval_summary", "short_summary", "summary"))
        retrieval_summary = values[0] if values else ""

    cues = flatten_string_values(
        recursive_find_values(profile, ("retrieval_cue", "query_cue", "cue")),
        limit=12,
    )
    questions = flatten_string_values(
        recursive_find_values(profile, ("answerable_question", "question")),
        limit=8,
    )
    part_values = recursive_find_values(profile, ("part_number", "part_numbers", "highlighted_part"))
    part_numbers: list[str] = []
    for item in flatten_string_values(part_values, limit=30):
        for match in re.findall(r"\b\d{3}-\d{5}-\d{3}\b", item):
            if match not in part_numbers:
                part_numbers.append(match)
    ata_codes = []
    for item in flatten_string_values(recursive_find_values(profile, ("ata",)), limit=20):
        for match in re.findall(r"\b\d{2}-\d{2}-\d{2}\b", item):
            if match not in ata_codes:
                ata_codes.append(match)

    has_context_v2 = "context_v2" in text_all or "page_context_v2" in text_all or "context v2" in text_all
    has_source_trace = (
        "source_trace" in text_all
        or "source_trace_status" in text_all
        or "source_trace_present" in text_all
        or "has_source_trace" in text_all
    )

    return {
        "role": compact_text(role, max_chars=120) or None,
        "subrole": compact_text(subrole, max_chars=160) or None,
        "retrieval_summary": compact_text(retrieval_summary, max_chars=600),
        "retrieval_cues": cues,
        "answerable_questions": questions,
        "part_numbers": part_numbers[:20],
        "ata_codes": ata_codes[:10],
        "has_context_v2": has_context_v2,
        "has_source_trace": has_source_trace,
    }


def is_blank_page(signals: dict[str, Any], zip_page: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
    role_text = f"{signals.get('role') or ''} {signals.get('subrole') or ''} {signals.get('retrieval_summary') or ''}".lower()
    blank_by_profile = any(token in role_text for token in ["blank", "empty", "no content", "empty_or_blank_page"])
    blank_by_zip_size = bool(zip_page and zip_page.get("blank_by_zip_size"))
    blank_expected = blank_by_profile or blank_by_zip_size
    return blank_expected, {
        "blank_by_profile": blank_by_profile,
        "blank_by_zip_size": blank_by_zip_size,
        "zip_entry_size_bytes": (zip_page or {}).get("zip_entry_size_bytes"),
    }


def load_graph(graph_nodes: str | Path | None, graph_edges: str | Path | None) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], str]:
    if not graph_nodes or not graph_edges:
        return {}, [], "NOT_PROVIDED"
    node_path = Path(graph_nodes)
    edge_path = Path(graph_edges)
    if not node_path.exists() or not edge_path.exists():
        return {}, [], "MISSING"

    def _load_list(path: Path) -> list[dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in ("nodes", "graph_nodes", "records", "edges", "graph_edges"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
        return []

    node_records = _load_list(node_path)
    edge_records = _load_list(edge_path)
    nodes: dict[str, dict[str, Any]] = {}
    for node in node_records:
        node_id = node.get("node_id") or node.get("id")
        if node_id:
            nodes[str(node_id)] = node
    return nodes, edge_records, "LOADED"


def edge_source(edge: dict[str, Any]) -> str:
    return str(edge.get("source_id") or edge.get("source") or edge.get("from") or "")


def edge_target(edge: dict[str, Any]) -> str:
    return str(edge.get("target_id") or edge.get("target") or edge.get("to") or "")


def edge_type(edge: dict[str, Any]) -> str:
    return str(edge.get("edge_type") or edge.get("type") or edge.get("label") or "")


def node_type(node: dict[str, Any] | None) -> str | None:
    if not node:
        return None
    return node.get("node_type") or node.get("type")


def node_label(node: dict[str, Any] | None) -> str | None:
    if not node:
        return None
    value = node.get("label") or node.get("name") or node.get("title")
    return compact_text(value, max_chars=300) if value else None


def build_graph_indexes(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    out_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    in_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        src = edge_source(edge)
        tgt = edge_target(edge)
        if src:
            out_edges[src].append(edge)
        if tgt:
            in_edges[tgt].append(edge)
    return {"out_edges": out_edges, "in_edges": in_edges, "nodes": nodes}


def build_page_graph_path(page_id: str, graph_idx: dict[str, Any], dublin_by_page: dict[str, dict[str, Any]]) -> dict[str, Any]:
    page_node_id = f"page:{page_id}"
    nodes: dict[str, dict[str, Any]] = graph_idx.get("nodes") or {}
    out_edges: dict[str, list[dict[str, Any]]] = graph_idx.get("out_edges") or {}
    page_node = nodes.get(page_node_id)
    source_links: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    ata_codes: list[str] = []
    context_v2_nodes: list[dict[str, Any]] = []
    part_mentions: list[dict[str, Any]] = []

    for edge in out_edges.get(page_node_id, []):
        et = edge_type(edge)
        tgt = edge_target(edge)
        tgt_node = nodes.get(tgt)
        tgt_type = node_type(tgt_node)
        if et in {"HAS_SOURCE_LINK", "OPENS", "HAS_SOURCE"} or tgt_type == "source_link":
            source_links.append(
                {
                    "source_link_id": tgt,
                    "label": node_label(tgt_node),
                    "via_edge": et,
                    "source_uri": (tgt_node or {}).get("source_uri") or (tgt_node or {}).get("url") or (tgt_node or {}).get("uri"),
                }
            )
        if et in {"HAS_TIFF", "POINTS_TO_TIFF", "HAS_SOURCE_FILE"} or tgt_type == "source_file":
            source_files.append(
                {
                    "source_file_id": tgt,
                    "label": node_label(tgt_node),
                    "via_edge": et,
                    "file_path": (tgt_node or {}).get("file_path") or (tgt_node or {}).get("path"),
                }
            )
        if et in {"BELONGS_TO_ATA", "HAS_ATA", "IN_ATA"} or tgt_type == "ata_section":
            label = node_label(tgt_node) or tgt
            for match in re.findall(r"\b\d{2}-\d{2}-\d{2}\b", label):
                if match not in ata_codes:
                    ata_codes.append(match)
        if et == "HAS_CONTEXT_V2" or tgt_type == "page_context_v2":
            context_v2_nodes.append({"node_id": tgt, "label": node_label(tgt_node), "via_edge": et})
        if et in {"MENTIONS_PART", "HAS_PART_MENTION", "REFERS_TO_PART"} or tgt_type in {"part", "part_mention"}:
            label = node_label(tgt_node) or tgt
            part_numbers = re.findall(r"\b\d{3}-\d{5}-\d{3}\b", label)
            part_mentions.append({"node_id": tgt, "label": label, "via_edge": et, "part_numbers": part_numbers})

    dc = dublin_by_page.get(page_id)
    dublin_present = bool(dc)
    if not source_links and dc:
        source_pkg = dc.get("source_package") or dc.get("trace_net:source_package") or {}
        href = source_pkg.get("trace_net:source_package_entry_href") or source_pkg.get("source_package_entry_href")
        if href:
            source_links.append({"source_kind": "dublin_core_source_package", "source_uri": href, "via_edge": "DUBLIN_CORE_SOURCE_IDENTITY"})

    return {
        "page_id": page_id,
        "page_node_id": page_node_id,
        "page_node_present": bool(page_node),
        "page_label": node_label(page_node),
        "ata_codes": ata_codes,
        "source_links": source_links,
        "source_files": source_files,
        "context_v2_nodes": context_v2_nodes,
        "part_mentions": part_mentions[:20],
        "dublin_core_source_identity_present": dublin_present,
        "dublin_core_source_identity": compact_dublin_identity(dc),
        "graph_path_resolved": bool(page_node and (source_links or source_files or dublin_present)),
        "required_path_template": "page_source_context_v1",
        "required_path_steps": [
            f"page:{page_id}",
            "HAS_SOURCE_LINK or DUBLIN_CORE_SOURCE_IDENTITY",
            "source_link/source_package_entry",
            "retrieval/evidence record remains retrieval-only until final gate",
        ],
    }


def compact_dublin_identity(dc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dc:
        return None
    source_pkg = dc.get("source_package") or dc.get("trace_net:source_package") or {}
    return {
        "page_id": dc.get("page_id") or dc.get("dc_identifier") or dc.get("dc:identifier"),
        "dc_title": dc.get("dc_title") or dc.get("dc:title") or dc.get("title"),
        "dc_type": dc.get("dc_type") or dc.get("dc:type") or dc.get("type"),
        "source_identity_status": dc.get("source_identity_status"),
        "source_package_entry_name": source_pkg.get("trace_net:source_package_entry_name") or source_pkg.get("source_package_entry_name"),
        "source_package_entry_href": source_pkg.get("trace_net:source_package_entry_href") or source_pkg.get("source_package_entry_href"),
        "source_package_entry_checksum_match": source_pkg.get("trace_net:source_package_entry_checksum_match") or source_pkg.get("source_package_entry_checksum_match"),
    }


def load_dublin_by_page(path: str | Path | None) -> tuple[dict[str, dict[str, Any]], str]:
    if not path:
        return {}, "NOT_PROVIDED"
    p = Path(path)
    if not p.exists():
        return {}, "MISSING"
    payload = load_json(p)
    records = payload.get("page_records") or payload.get("records") or payload.get("pages") or []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            page_id = record.get("page_id") or record.get("dc_identifier") or record.get("dc:identifier")
            if page_id:
                out[str(page_id)] = record
    return out, "LOADED"


def build_llm_prompt(record: dict[str, Any]) -> str:
    page_id = record["page_id"]
    page_number = record["page_number"]
    blank_expected = record.get("blank_expected")
    signals = record.get("profile_signals") or {}
    graph_path = record.get("graph_path") or {}

    summary = signals.get("retrieval_summary") or "No page summary available."
    cues = "; ".join(signals.get("retrieval_cues") or []) or "No retrieval cues available."
    expected = record.get("expected_answer_behavior")
    source_hint = graph_path.get("dublin_core_source_identity") or {}
    source_entry = source_hint.get("source_package_entry_name") or "source package entry unavailable"

    return compact_text(
        f"""
You are TRACE-Net. You must locate the answer by following the approved graph path before answering.

User question:
{record.get('llm_question')}

Required graph path:
1. Resolve target page node: page:{page_id}
2. Follow page_source_context_v1: Page -> SourceLink / Dublin Core source package entry
3. Confirm source identity before summarizing.
4. Use retrieval/Qdrant only as routing help, not proof.
5. Do not use Leiden/community/category hints as proof.
6. Do not answer if the graph/source path is missing; return NEEDS_REVIEW instead.

Target page: {page_id}
Target page number: {page_number}
Source package entry: {source_entry}
Page context summary: {summary}
Retrieval cues: {cues}
Expected answer behavior: {expected}
Blank expected: {blank_expected}

Return compact JSON only with keys:
status, graph_path_followed, page_id, source_identity_checked, answer, citations, needs_review, reason_codes.
If the page is blank, the answer must explicitly say the page is blank or empty.
""",
        max_chars=5000,
    )


def classify_query_type(blank_expected: bool, signals: dict[str, Any]) -> tuple[str, str, list[str]]:
    if blank_expected:
        return "blank_page_graph_check", "graph_first_blank_confirmation", ["graph_page_lookup", "dublin_core_source_identity"]
    if signals.get("part_numbers"):
        return "page_part_context_graph_check", "graph_plus_opensearch_part_context", ["graph_page_lookup", "opensearch_exact", "dublin_core_source_identity"]
    role_text = f"{signals.get('role') or ''} {signals.get('subrole') or ''}".lower()
    if "table" in role_text or "parts" in role_text or "list" in role_text:
        return "page_table_or_parts_graph_check", "graph_plus_semantic_context", ["graph_page_lookup", "qdrant_semantic", "opensearch_exact"]
    return "page_source_context_graph_check", "graph_first_page_source_context", ["graph_page_lookup", "qdrant_semantic", "dublin_core_source_identity"]


def build_query_record(
    page_number: int,
    page_id: str,
    profile: dict[str, Any] | None,
    zip_page: dict[str, Any] | None,
    graph_path: dict[str, Any],
) -> dict[str, Any]:
    signals = extract_profile_signals(profile)
    blank_expected, blank_detection = is_blank_page(signals, zip_page)
    query_type, retrieval_route, required_channels = classify_query_type(blank_expected, signals)

    summary = signals.get("retrieval_summary") or f"Page-level retrieval profile for {page_id}."
    cues = signals.get("retrieval_cues") or []
    cue_text = "; ".join(cues[:8]) if cues else "source page; technical manual; ATA 25-21-00"

    if blank_expected:
        question = f"Using the TRACE-Net graph path, locate page {page_number} of EMB CMM ATA 25-21-00 REV.4. What is on this page? If it is blank, say the page is blank."
        semantic_query = f"blank empty page {page_number} EMB CMM ATA 25-21-00 REV.4 source page"
        expected_behavior = "LLM_MUST_FOLLOW_GRAPH_PATH_AND_STATE_PAGE_IS_BLANK_OR_EMPTY"
    else:
        question = f"Using the TRACE-Net graph path, locate page {page_number} of EMB CMM ATA 25-21-00 REV.4 and summarize what the source-linked page contains."
        semantic_query = compact_text(
            f"Find the page whose graph path resolves to page {page_number} ({page_id}) in EMB CMM ATA 25-21-00 REV.4. Page context summary: {summary}. Retrieval cues: {cue_text}.",
            max_chars=1400,
        )
        expected_behavior = "LLM_MUST_FOLLOW_GRAPH_PATH_AND_SUMMARIZE_SOURCE_LINKED_PAGE_ONLY"

    record: dict[str, Any] = {
        "eval_record_id": stable_id(SCHEMA_VERSION, page_id, prefix="page_retrieval_large_eval_v2"),
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "page_number": page_number,
        "query_type": query_type,
        "retrieval_route": retrieval_route,
        "required_channels": required_channels,
        "semantic_retrieval_query": semantic_query,
        "llm_question": question,
        "expected_answer_behavior": expected_behavior,
        "profile_signals": signals,
        "blank_expected": blank_expected,
        "blank_detection": blank_detection,
        "graph_path": graph_path,
        "graph_path_resolved": bool(graph_path.get("graph_path_resolved")),
        "llm_must_follow_graph_path": True,
        "llm_graph_path_prompt": None,  # filled after record is complete
        "evaluated": False,
        "top_hits": [],
        "target_rank": None,
        "target_hit_at_1": False,
        "target_hit_at_3": False,
        "target_hit_at_5": False,
        "target_hit_at_10": False,
        "target_hit_at_k": False,
        "answer_capable_payload_count": 0,
        "claim_proof_payload_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only": True,
        "source_truth_mutation_allowed": False,
    }
    record["llm_graph_path_prompt"] = build_llm_prompt(record)
    return record


def ollama_embed_batch(texts: list[str], *, ollama_url: str, model: str, timeout: int = 240) -> list[list[float]]:
    base = ollama_url.rstrip("/")
    payload = {"model": model, "input": texts}
    req = urllib.request.Request(
        f"{base}/api/embed",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    embeddings = data.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise RuntimeError(f"Expected {len(texts)} embeddings from Ollama, got {len(embeddings)}")
    return embeddings

def query_embedding_cache_key(text: str, *, model: str, embedding_source: str = "ollama") -> str:
    """Stable cache key for a query embedding.

    The key intentionally includes the model and embedding source so caches are not
    reused across incompatible embedding backends. The raw query text is stored in
    the JSONL cache for auditability, but the key uses a SHA-256 digest.
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "embedding_source": embedding_source,
        "model": model,
        "text": text,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_query_embedding_cache(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record.get("cache_key")
            vector = record.get("vector")
            if not isinstance(key, str) or not isinstance(vector, list) or not vector:
                continue
            if not all(isinstance(x, (int, float)) for x in vector):
                continue
            records[key] = record
    return records


def append_query_embedding_cache_records(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def embed_texts_with_query_cache(
    texts: list[str],
    *,
    ollama_url: str,
    model: str,
    cache_path: str | Path | None = None,
    cache_records: dict[str, dict[str, Any]] | None = None,
    stats: dict[str, Any] | None = None,
    embedder: Any | None = None,
) -> list[list[float]]:
    """Embed query texts, optionally reusing/appending a JSONL cache.

    This cache is for eval/user-query embeddings only. It does not write to
    Qdrant and does not change the corpus vectors.
    """
    embedder = embedder or ollama_embed_batch
    stats = stats if stats is not None else {}
    stats.setdefault("enabled", bool(cache_path))
    stats.setdefault("hit_count", 0)
    stats.setdefault("miss_count", 0)
    stats.setdefault("write_count", 0)
    stats.setdefault("ollama_request_count", 0)

    if not cache_path:
        stats["miss_count"] += len(texts)
        stats["ollama_request_count"] += 1 if texts else 0
        return embedder(texts, ollama_url=ollama_url, model=model)

    cache_records = cache_records if cache_records is not None else load_query_embedding_cache(cache_path)
    embeddings: list[list[float] | None] = [None for _ in texts]
    misses: list[tuple[int, str, str]] = []

    for index, text in enumerate(texts):
        key = query_embedding_cache_key(text, model=model)
        cached = cache_records.get(key)
        if cached and isinstance(cached.get("vector"), list):
            embeddings[index] = [float(x) for x in cached["vector"]]
            stats["hit_count"] += 1
        else:
            misses.append((index, text, key))
            stats["miss_count"] += 1

    if misses:
        stats["ollama_request_count"] += 1
        miss_vectors = embedder([text for _, text, _ in misses], ollama_url=ollama_url, model=model)
        new_records: list[dict[str, Any]] = []
        now = int(time.time())
        for (index, text, key), vector in zip(misses, miss_vectors):
            clean_vector = [float(x) for x in vector]
            embeddings[index] = clean_vector
            record = {
                "schema_version": SCHEMA_VERSION,
                "cache_key": key,
                "embedding_source": "ollama",
                "embedding_model": model,
                "embedding_dim": len(clean_vector),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "text": text,
                "created_at_epoch": now,
                "vector": clean_vector,
            }
            cache_records[key] = record
            new_records.append(record)
        append_query_embedding_cache_records(cache_path, new_records)
        stats["write_count"] += len(new_records)

    return [vector if vector is not None else [] for vector in embeddings]


def is_answer_capable_payload(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    return '"can_answer_directly": true' in text or "can_answer_directly true" in text or payload.get("can_answer_directly") is True


def is_claim_proof_payload(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    return '"can_prove_claims": true' in text or "can_prove_claims true" in text or payload.get("can_prove_claims") is True


def has_source_truth_mutation(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    return '"source_truth_mutation_allowed": true' in text or payload.get("source_truth_mutation_allowed") is True


def query_qdrant_points(
    client: Any,
    *,
    collection: str,
    vector: list[float],
    top_k: int,
) -> list[Any]:
    if hasattr(client, "query_points"):
        result = client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return list(getattr(result, "points", result))
    return list(
        client.search(
            collection_name=collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
    )


def run_qdrant_eval(
    records: list[dict[str, Any]],
    *,
    qdrant_url: str,
    collection: str,
    ollama_url: str,
    ollama_model: str,
    top_k: int,
    batch_size: int,
    progress: bool = False,
    use_query_embedding_cache: bool = False,
    query_embedding_cache_path: str | Path | None = None,
    reset_query_embedding_cache: bool = False,
) -> dict[str, Any]:
    try:
        from qdrant_client import QdrantClient  # type: ignore
    except Exception as exc:  # pragma: no cover - env-specific
        raise RuntimeError("qdrant_client is required for --run-qdrant-eval") from exc

    client = QdrantClient(url=qdrant_url)
    total = len(records)

    cache_path: Path | None = Path(query_embedding_cache_path) if use_query_embedding_cache and query_embedding_cache_path else None
    if cache_path and reset_query_embedding_cache and cache_path.exists():
        cache_path.unlink()
    cache_records = load_query_embedding_cache(cache_path) if cache_path else {}
    cache_stats: dict[str, Any] = {
        "enabled": bool(cache_path),
        "path": str(cache_path) if cache_path else None,
        "initial_record_count": len(cache_records),
        "hit_count": 0,
        "miss_count": 0,
        "write_count": 0,
        "ollama_request_count": 0,
        "reset": bool(reset_query_embedding_cache and cache_path),
    }

    for start in range(0, total, max(1, batch_size)):
        batch = records[start : start + max(1, batch_size)]
        if progress:
            if cache_path:
                print(
                    "TRACE-Net page retrieval eval v2: embedding/querying "
                    f"{start}/{total} cache_hits={cache_stats['hit_count']} cache_misses={cache_stats['miss_count']}",
                    flush=True,
                )
            else:
                print(f"TRACE-Net page retrieval eval v2: embedding/querying {start}/{total}", flush=True)
        embeddings = embed_texts_with_query_cache(
            [str(r["semantic_retrieval_query"]) for r in batch],
            ollama_url=ollama_url,
            model=ollama_model,
            cache_path=cache_path,
            cache_records=cache_records,
            stats=cache_stats,
        )
        for record, vector in zip(batch, embeddings):
            points = query_qdrant_points(client, collection=collection, vector=vector, top_k=top_k)
            hits: list[dict[str, Any]] = []
            target_rank: int | None = None
            answer_capable_count = 0
            proof_count = 0
            source_mutation_count = 0
            for rank, point in enumerate(points, 1):
                payload = getattr(point, "payload", None) or {}
                page_id = payload.get("page_id")
                score = getattr(point, "score", None)
                if page_id == record["page_id"] and target_rank is None:
                    target_rank = rank
                if isinstance(payload, dict):
                    answer_capable_count += int(is_answer_capable_payload(payload))
                    proof_count += int(is_claim_proof_payload(payload))
                    source_mutation_count += int(has_source_truth_mutation(payload))
                hits.append(
                    {
                        "rank": rank,
                        "point_id": str(getattr(point, "id", "")),
                        "page_id": page_id,
                        "score": score,
                        "has_context_v2": payload.get("has_context_v2") or payload.get("context_v2_present"),
                        "payload_keys": sorted(payload.keys())[:80] if isinstance(payload, dict) else [],
                    }
                )
            record["evaluated"] = True
            record["qdrant_collection"] = collection
            record["qdrant_top_k"] = top_k
            record["embedding_model"] = ollama_model
            record["embedding_dim"] = len(vector)
            record["top_hits"] = hits
            record["target_rank"] = target_rank
            record["target_hit_at_1"] = target_rank is not None and target_rank <= 1
            record["target_hit_at_3"] = target_rank is not None and target_rank <= 3
            record["target_hit_at_5"] = target_rank is not None and target_rank <= 5
            record["target_hit_at_10"] = target_rank is not None and target_rank <= 10
            record["target_hit_at_k"] = target_rank is not None and target_rank <= top_k
            record["answer_capable_payload_count"] = answer_capable_count
            record["claim_proof_payload_count"] = proof_count
            record["source_truth_mutation_allowed_count"] = source_mutation_count

    cache_stats["final_record_count"] = len(cache_records)
    return cache_stats


def build_summary(records: list[dict[str, Any]], *, source_statuses: dict[str, Any], top_k: int | None = None) -> dict[str, Any]:
    total = len(records)
    evaluated = [r for r in records if r.get("evaluated")]
    blank_records = [r for r in records if r.get("blank_expected")]
    blank_eval = [r for r in blank_records if r.get("evaluated")]
    graph_resolved = [r for r in records if r.get("graph_path_resolved")]
    qtype_counts = Counter(r.get("query_type") for r in records)
    route_counts = Counter(r.get("retrieval_route") for r in records)
    miss_reason_counts = Counter()
    for r in records:
        if not r.get("graph_path_resolved"):
            miss_reason_counts["missing_graph_source_path"] += 1
        if r.get("evaluated") and not r.get("target_hit_at_k"):
            if r.get("blank_expected"):
                miss_reason_counts["blank_target_not_in_top_k"] += 1
            elif r.get("query_type") == "page_part_context_graph_check":
                miss_reason_counts["part_context_semantic_miss"] += 1
            else:
                miss_reason_counts["semantic_page_target_miss"] += 1

    def count(key: str) -> int:
        return sum(1 for r in records if r.get(key))

    def eval_count(key: str) -> int:
        return sum(1 for r in evaluated if r.get(key))

    def rate(n: int, d: int) -> float:
        return round(n / d, 6) if d else 0.0

    answer_capable_payload_count = sum(int(r.get("answer_capable_payload_count") or 0) for r in records)
    claim_proof_payload_count = sum(int(r.get("claim_proof_payload_count") or 0) for r in records)
    source_truth_mutation_allowed_count = sum(int(r.get("source_truth_mutation_allowed_count") or 0) for r in records)
    cache_stats = source_statuses.get("query_embedding_cache") or {}

    return {
        "schema_version": SCHEMA_VERSION,
        "query_record_count": total,
        "evaluated_record_count": len(evaluated),
        "blank_expected_count": len(blank_records),
        "context_v2_query_count": sum(1 for r in records if (r.get("profile_signals") or {}).get("has_context_v2")),
        "llm_graph_path_card_count": sum(1 for r in records if r.get("llm_graph_path_prompt")),
        "llm_must_follow_graph_path_count": sum(1 for r in records if r.get("llm_must_follow_graph_path")),
        "graph_path_resolved_count": len(graph_resolved),
        "graph_path_missing_count": total - len(graph_resolved),
        "source_identity_resolved_count": sum(1 for r in records if ((r.get("graph_path") or {}).get("dublin_core_source_identity_present"))),
        "source_link_resolved_count": sum(1 for r in records if ((r.get("graph_path") or {}).get("source_links"))),
        "target_hit_at_1_count": eval_count("target_hit_at_1"),
        "target_hit_at_3_count": eval_count("target_hit_at_3"),
        "target_hit_at_5_count": eval_count("target_hit_at_5"),
        "target_hit_at_10_count": eval_count("target_hit_at_10"),
        "target_hit_at_k_count": eval_count("target_hit_at_k"),
        "target_hit_at_1_rate": rate(eval_count("target_hit_at_1"), len(evaluated)),
        "target_hit_at_10_rate": rate(eval_count("target_hit_at_10"), len(evaluated)),
        "target_hit_at_k_rate": rate(eval_count("target_hit_at_k"), len(evaluated)),
        "blank_evaluated_count": len(blank_eval),
        "blank_target_hit_at_k_count": sum(1 for r in blank_eval if r.get("target_hit_at_k")),
        "query_type_counts": dict(qtype_counts),
        "retrieval_route_counts": dict(route_counts),
        "miss_reason_counts": dict(miss_reason_counts),
        "top_k": top_k,
        "answer_capable_payload_count": answer_capable_payload_count,
        "claim_proof_payload_count": claim_proof_payload_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "query_embedding_cache_enabled": bool(cache_stats.get("enabled")),
        "query_embedding_cache_path": cache_stats.get("path"),
        "query_embedding_cache_initial_record_count": cache_stats.get("initial_record_count", 0),
        "query_embedding_cache_final_record_count": cache_stats.get("final_record_count", cache_stats.get("initial_record_count", 0)),
        "query_embedding_cache_hit_count": cache_stats.get("hit_count", 0),
        "query_embedding_cache_miss_count": cache_stats.get("miss_count", 0),
        "query_embedding_cache_write_count": cache_stats.get("write_count", 0),
        "query_embedding_ollama_request_count": cache_stats.get("ollama_request_count", 0),
        "can_answer_directly_count": count("can_answer_directly"),
        "can_prove_claims_count": count("can_prove_claims"),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_load_statuses": source_statuses,
    }


def parse_thresholds(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_query_records": args.min_query_records,
        "min_blank_queries": args.min_blank_queries,
        "min_context_v2_queries": args.min_context_v2_queries,
        "min_graph_path_resolved": args.min_graph_path_resolved,
        "min_llm_graph_path_cards": args.min_llm_graph_path_cards,
        "min_evaluated_records": args.min_evaluated_records,
        "min_target_hit_at_k": args.min_target_hit_at_k,
        "max_answer_capable_payloads": args.max_answer_capable_payloads,
        "max_claim_proof_payloads": args.max_claim_proof_payloads,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_profile_quality_pass": args.require_profile_quality_pass,
        "require_graph_paths": args.require_graph_paths,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def check_quality(payload: dict[str, Any], thresholds: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    summary = payload.get("summary") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("status", payload.get("status") == STATUS_BUILT, f"status={payload.get('status')}")
    add(
        "query_record_count",
        summary.get("query_record_count", 0) >= thresholds.get("min_query_records", 0),
        f"records={summary.get('query_record_count')}; minimum={thresholds.get('min_query_records')}",
    )
    add(
        "blank_expected_count",
        summary.get("blank_expected_count", 0) >= thresholds.get("min_blank_queries", 0),
        f"blank={summary.get('blank_expected_count')}; minimum={thresholds.get('min_blank_queries')}",
    )
    add(
        "context_v2_query_count",
        summary.get("context_v2_query_count", 0) >= thresholds.get("min_context_v2_queries", 0),
        f"context_v2={summary.get('context_v2_query_count')}; minimum={thresholds.get('min_context_v2_queries')}",
    )
    add(
        "graph_path_resolved_count",
        summary.get("graph_path_resolved_count", 0) >= thresholds.get("min_graph_path_resolved", 0),
        f"graph_paths={summary.get('graph_path_resolved_count')}; minimum={thresholds.get('min_graph_path_resolved')}",
    )
    add(
        "llm_graph_path_card_count",
        summary.get("llm_graph_path_card_count", 0) >= thresholds.get("min_llm_graph_path_cards", 0),
        f"cards={summary.get('llm_graph_path_card_count')}; minimum={thresholds.get('min_llm_graph_path_cards')}",
    )

    if thresholds.get("min_evaluated_records", 0):
        add(
            "evaluated_record_count",
            summary.get("evaluated_record_count", 0) >= thresholds.get("min_evaluated_records", 0),
            f"evaluated={summary.get('evaluated_record_count')}; minimum={thresholds.get('min_evaluated_records')}",
        )
    if thresholds.get("min_target_hit_at_k", 0):
        add(
            "target_hit_at_k_count",
            summary.get("target_hit_at_k_count", 0) >= thresholds.get("min_target_hit_at_k", 0),
            f"hits={summary.get('target_hit_at_k_count')}; minimum={thresholds.get('min_target_hit_at_k')}",
        )

    add(
        "answer_capable_payload_count",
        summary.get("answer_capable_payload_count", 0) <= thresholds.get("max_answer_capable_payloads", 0),
        f"answer_capable={summary.get('answer_capable_payload_count')}; max={thresholds.get('max_answer_capable_payloads')}",
    )
    add(
        "claim_proof_payload_count",
        summary.get("claim_proof_payload_count", 0) <= thresholds.get("max_claim_proof_payloads", 0),
        f"claim_proof={summary.get('claim_proof_payload_count')}; max={thresholds.get('max_claim_proof_payloads')}",
    )
    add(
        "source_truth_mutation_allowed_count",
        summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.get("max_source_truth_mutation_allowed", 0),
        f"source_truth_mutation={summary.get('source_truth_mutation_allowed_count')}; max={thresholds.get('max_source_truth_mutation_allowed')}",
    )
    if thresholds.get("require_no_answer_permission"):
        add(
            "no_answer_permission",
            summary.get("can_answer_directly_count", 0) == 0 and summary.get("can_prove_claims_count", 0) == 0,
            f"can_answer={summary.get('can_answer_directly_count')}; can_prove={summary.get('can_prove_claims_count')}",
        )
    if thresholds.get("require_graph_paths"):
        add(
            "all_graph_paths_resolved",
            summary.get("graph_path_missing_count", 0) == 0,
            f"missing_graph_paths={summary.get('graph_path_missing_count')}",
        )
    if thresholds.get("require_profile_quality_pass"):
        source_statuses = summary.get("source_load_statuses") or {}
        profile_quality = source_statuses.get("profile_quality_status")
        add(
            "profile_quality_pass",
            profile_quality in {QUALITY_PASS, "PASS", "OK", None},
            f"profile_quality_status={profile_quality}",
        )

    status = QUALITY_PASS if all(check["ok"] for check in checks) else QUALITY_FAIL
    return status, checks


def build_large_eval_v2(
    *,
    metadata_zip: str | Path,
    profiles_path: str | Path,
    output_dir: str | Path,
    first_pages: int,
    graph_nodes: str | Path | None = None,
    graph_edges: str | Path | None = None,
    dublin_core_source_package_extension: str | Path | None = None,
    run_qdrant_eval_flag: bool = False,
    qdrant_url: str = "http://localhost:6333",
    collection: str = DEFAULT_COLLECTION,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    top_k: int = 20,
    batch_size: int = 16,
    progress: bool = False,
    use_query_embedding_cache: bool = False,
    query_embedding_cache_path: str | Path | None = None,
    reset_query_embedding_cache: bool = False,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    zip_pages = load_metadata_zip_pages(metadata_zip, first_pages)
    profile_records, profiles_by_page, profile_quality_status = load_profiles(profiles_path)
    dublin_by_page, dublin_status = load_dublin_by_page(dublin_core_source_package_extension)
    nodes, edges, graph_status = load_graph(graph_nodes, graph_edges)
    graph_idx = build_graph_indexes(nodes, edges)

    records: list[dict[str, Any]] = []
    for page_number in range(1, first_pages + 1):
        page_id = page_num_to_id(page_number)
        profile = profiles_by_page.get(page_id)
        zip_page = zip_pages.get(page_id)
        graph_path = build_page_graph_path(page_id, graph_idx, dublin_by_page)
        record = build_query_record(page_number, page_id, profile, zip_page, graph_path)
        records.append(record)

    cache_stats: dict[str, Any] = {"enabled": False}
    resolved_cache_path: Path | None = None
    if use_query_embedding_cache:
        resolved_cache_path = (
            Path(query_embedding_cache_path)
            if query_embedding_cache_path
            else outdir / "trace_net_page_retrieval_large_eval_v2_query_embedding_cache_ollama_bge_m3.jsonl"
        )

    if run_qdrant_eval_flag:
        cache_stats = run_qdrant_eval(
            records,
            qdrant_url=qdrant_url,
            collection=collection,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            top_k=top_k,
            batch_size=batch_size,
            progress=progress,
            use_query_embedding_cache=use_query_embedding_cache,
            query_embedding_cache_path=resolved_cache_path,
            reset_query_embedding_cache=reset_query_embedding_cache,
        )

    source_statuses = {
        "metadata_zip": "LOADED",
        "profiles": "LOADED",
        "profile_quality_status": profile_quality_status,
        "graph_nodes_edges": graph_status,
        "dublin_core_source_package_extension": dublin_status,
        "qdrant_eval": "EVALUATED" if run_qdrant_eval_flag else "NOT_RUN",
        "qdrant_collection": collection if run_qdrant_eval_flag else None,
        "ollama_model": ollama_model if run_qdrant_eval_flag else None,
        "query_embedding_cache": cache_stats if run_qdrant_eval_flag else {"enabled": False},
    }
    summary = build_summary(records, source_statuses=source_statuses, top_k=top_k if run_qdrant_eval_flag else None)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": None,
        "generated_at_epoch": int(time.time()),
        "inputs": {
            "metadata_zip": str(metadata_zip),
            "profiles_path": str(profiles_path),
            "graph_nodes": str(graph_nodes) if graph_nodes else None,
            "graph_edges": str(graph_edges) if graph_edges else None,
            "dublin_core_source_package_extension": str(dublin_core_source_package_extension) if dublin_core_source_package_extension else None,
            "first_pages": first_pages,
            "run_qdrant_eval": run_qdrant_eval_flag,
            "qdrant_url": qdrant_url if run_qdrant_eval_flag else None,
            "collection": collection if run_qdrant_eval_flag else None,
            "ollama_url": ollama_url if run_qdrant_eval_flag else None,
            "ollama_model": ollama_model if run_qdrant_eval_flag else None,
            "top_k": top_k if run_qdrant_eval_flag else None,
            "use_query_embedding_cache": use_query_embedding_cache if run_qdrant_eval_flag else False,
            "query_embedding_cache_path": str(resolved_cache_path) if resolved_cache_path else None,
            "reset_query_embedding_cache": reset_query_embedding_cache if run_qdrant_eval_flag else False,
        },
        "summary": summary,
        "query_records": records,
        "llm_graph_path_cards": [
            {
                "page_id": r["page_id"],
                "page_number": r["page_number"],
                "query_type": r["query_type"],
                "graph_path_resolved": r["graph_path_resolved"],
                "llm_question": r["llm_question"],
                "llm_graph_path_prompt": r["llm_graph_path_prompt"],
                "expected_answer_behavior": r["expected_answer_behavior"],
            }
            for r in records
        ],
        "miss_records": [r for r in records if r.get("evaluated") and not r.get("target_hit_at_k")],
        "blank_records": [r for r in records if r.get("blank_expected")],
    }
    quality_status, checks = check_quality(payload, thresholds)
    payload["quality_status"] = quality_status
    payload["quality_checks"] = checks
    payload["summary"]["status"] = quality_status

    report_path = outdir / "trace_net_page_retrieval_large_eval_v2.json"
    quality_path = outdir / "trace_net_page_retrieval_large_eval_v2_quality.json"
    query_path = outdir / "trace_net_page_retrieval_large_eval_v2_queries.jsonl"
    card_path = outdir / "trace_net_page_retrieval_large_eval_v2_llm_graph_path_cards.jsonl"
    markdown_path = outdir / "trace_net_page_retrieval_large_eval_v2.md"

    write_json(report_path, payload)
    write_json(quality_path, {"quality_status": quality_status, "summary": summary, "quality_checks": checks})
    write_jsonl(query_path, records)
    write_jsonl(card_path, payload["llm_graph_path_cards"])
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")

    payload["report_path"] = str(report_path)
    payload["quality_path"] = str(quality_path)
    payload["query_records_path"] = str(query_path)
    payload["llm_graph_path_cards_path"] = str(card_path)
    payload["markdown_path"] = str(markdown_path)
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Page Retrieval Large Eval v2",
        "",
        f"Status: `{payload.get('status')}`",
        f"Quality status: `{payload.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "query_record_count",
        "evaluated_record_count",
        "blank_expected_count",
        "context_v2_query_count",
        "graph_path_resolved_count",
        "llm_graph_path_card_count",
        "target_hit_at_1_count",
        "target_hit_at_10_count",
        "target_hit_at_k_count",
        "target_hit_at_k_rate",
        "answer_capable_payload_count",
        "claim_proof_payload_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- `{key}`: `{summary.get(key)}`")
    lines.extend(
        [
            "",
            "## Safety contract",
            "",
            "This artifact is read-only. It creates retrieval and LLM graph-path test cards only. It does not write to Postgres, Qdrant, OpenSearch, or source truth, and it does not grant answer permission.",
        ]
    )
    return "\n".join(lines) + "\n"


def print_summary(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("TRACE-Net Page Retrieval Large Eval v2")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "query_record_count",
        "evaluated_record_count",
        "blank_expected_count",
        "context_v2_query_count",
        "graph_path_resolved_count",
        "graph_path_missing_count",
        "llm_graph_path_card_count",
        "target_hit_at_1_count",
        "target_hit_at_3_count",
        "target_hit_at_5_count",
        "target_hit_at_10_count",
        "target_hit_at_k_count",
        "target_hit_at_k_rate",
        "answer_capable_payload_count",
        "claim_proof_payload_count",
        "source_truth_mutation_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    for key in ["report_path", "quality_path", "query_records_path", "llm_graph_path_cards_path"]:
        if payload.get(key):
            print(f" {key}: {payload.get(key)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Page Retrieval Large Eval v2")
    parser.add_argument("--metadata-zip", required=True)
    parser.add_argument("--profiles-path", required=True)
    parser.add_argument("--graph-nodes")
    parser.add_argument("--graph-edges")
    parser.add_argument("--dublin-core-source-package-extension")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--first-pages", type=int, default=170)
    parser.add_argument("--run-qdrant-eval", action="store_true")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--use-query-embedding-cache", action="store_true", help="Cache eval query embeddings in JSONL so reruns avoid repeated Ollama embedding calls")
    parser.add_argument("--query-embedding-cache-path", help="Optional JSONL cache path; defaults under --output-dir when cache is enabled")
    parser.add_argument("--reset-query-embedding-cache", action="store_true", help="Delete the query embedding cache before the eval run")

    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-blank-queries", type=int, default=0)
    parser.add_argument("--min-context-v2-queries", type=int, default=0)
    parser.add_argument("--min-graph-path-resolved", type=int, default=0)
    parser.add_argument("--min-llm-graph-path-cards", type=int, default=0)
    parser.add_argument("--min-evaluated-records", type=int, default=0)
    parser.add_argument("--min-target-hit-at-k", type=int, default=0)
    parser.add_argument("--max-answer-capable-payloads", type=int, default=0)
    parser.add_argument("--max-claim-proof-payloads", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-profile-quality-pass", action="store_true")
    parser.add_argument("--require-graph-paths", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main_build(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    thresholds = parse_thresholds(args)
    payload = build_large_eval_v2(
        metadata_zip=args.metadata_zip,
        profiles_path=args.profiles_path,
        graph_nodes=args.graph_nodes,
        graph_edges=args.graph_edges,
        dublin_core_source_package_extension=args.dublin_core_source_package_extension,
        output_dir=args.output_dir,
        first_pages=args.first_pages,
        run_qdrant_eval_flag=args.run_qdrant_eval,
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        top_k=args.top_k,
        batch_size=args.batch_size,
        progress=args.progress,
        use_query_embedding_cache=args.use_query_embedding_cache,
        query_embedding_cache_path=args.query_embedding_cache_path,
        reset_query_embedding_cache=args.reset_query_embedding_cache,
        thresholds=thresholds,
    )
    print_summary(payload)
    return 0 if payload.get("quality_status") == QUALITY_PASS else 2


def check_report_quality(
    *,
    report_path: str | Path,
    thresholds: dict[str, Any],
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = load_json(report_path)
    status, checks = check_quality(payload, thresholds)
    payload["quality_status"] = status
    payload["quality_checks"] = checks
    payload.setdefault("summary", {})["status"] = status
    if write_json_report:
        quality_path = Path(report_path).with_name("trace_net_page_retrieval_large_eval_v2_quality.json")
        write_json(quality_path, {"quality_status": status, "summary": payload.get("summary"), "quality_checks": checks})
    return payload


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Page Retrieval Large Eval v2 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-query-records", type=int, default=1)
    parser.add_argument("--min-blank-queries", type=int, default=0)
    parser.add_argument("--min-context-v2-queries", type=int, default=0)
    parser.add_argument("--min-graph-path-resolved", type=int, default=0)
    parser.add_argument("--min-llm-graph-path-cards", type=int, default=0)
    parser.add_argument("--min-evaluated-records", type=int, default=0)
    parser.add_argument("--min-target-hit-at-k", type=int, default=0)
    parser.add_argument("--max-answer-capable-payloads", type=int, default=0)
    parser.add_argument("--max-claim-proof-payloads", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-profile-quality-pass", action="store_true")
    parser.add_argument("--require-graph-paths", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main_check(argv: list[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    thresholds = parse_thresholds(args)
    payload = check_report_quality(report_path=args.report_path, thresholds=thresholds, write_json_report=args.write_json)
    print_summary(payload)
    return 0 if payload.get("quality_status") == QUALITY_PASS else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
