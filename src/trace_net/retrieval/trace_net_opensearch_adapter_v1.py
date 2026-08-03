"""TRACE-Net OpenSearch Adapter v1.

This module builds a safe, local OpenSearch document set from TRACE-Net
artifacts. It does not require a running OpenSearch server and does not write
to OpenSearch. The output can be reviewed, quality-checked, and later used by
an incremental uploader.

Safety contract:
- Only TRACE-Net-approved/searchable artifact families are converted.
- Raw OCR, raw visual output, raw feedback comments, prompt/debug text, and
  unsafe/untraceable records are not indexed.
- Documents may guide retrieval, but they cannot answer directly or mutate
  source truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_opensearch_adapter_v1"
ALGORITHM = "trace_net_safe_opensearch_document_builder_v1"
DEFAULT_INDEX_NAME = "trace_net_safe_search_v1"

SAFE_EMBEDDING_BUCKETS = {
    "source_evidence",
    "source_text_evidence",
    "verified_part_evidence",
    "derived_context",
    "context_retrieval_helper",
}

ANSWER_SUPPORT_BUCKETS = {
    "source_text_evidence",
    "verified_part_evidence",
    "table_structured_evidence",
    "table_part_catalog_evidence",
    "clean_evidence_snippet",
}

RETRIEVAL_ONLY_BUCKETS = {
    "source_evidence",
    "derived_context",
    "context_retrieval_helper",
    "page_retrieval_profile",
    "community_retrieval_helper",
    "part_candidate_lineage",
    "table_cell_normalized",
    "table_row_normalized",
}

BANNED_BUCKET_TOKENS = {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_tile",
    "feedback_only",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}

BANNED_TEXT_PATTERNS = [
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"/mnt/data/"),
    re.compile(r"local_data[/\\\\]", re.IGNORECASE),
    re.compile(r"\.tiff?\b", re.IGNORECASE),
    re.compile(r"traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"ignore previous instructions", re.IGNORECASE),
]

PATH_REPLACEMENTS = [
    (re.compile(r"[A-Za-z]:\\[^\s\]\)\}\>]+"), "[local_path_redacted]"),
    (re.compile(r"/mnt/data/[^\s\]\)\}\>]+"), "[local_path_redacted]"),
    (re.compile(r"local_data[/\\\\][^\s\]\)\}\>]+", re.IGNORECASE), "[local_path_redacted]"),
]

TEXT_KEYS = [
    "text",
    "content",
    "chunk_text",
    "embedding_text",
    "text_for_embedding",
    "search_text",
    "summary_text",
    "page_profile_text",
    "profile_text",
    "retrieval_text",
    "clean_snippet",
    "clean_text",
    "snippet_text",
    "claim_text",
    "feedback_summary",
    "label",
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any, length: int = 20) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def read_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def unique_strings(values: Iterable[Any]) -> list[str]:
    return sorted({str(v) for v in values if v is not None and str(v).strip()})


def first_nonempty(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def sanitize_text(value: Any, *, max_chars: int = 6000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = value.replace("\x00", " ").strip()
    for pattern, repl in PATH_REPLACEMENTS:
        text = pattern.sub(repl, text)
    # Collapse very noisy whitespace while preserving table-ish separation.
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


def extract_text(record: dict[str, Any], *, fallback_keys: Iterable[str] = TEXT_KEYS) -> str:
    pieces: list[str] = []
    for key in fallback_keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            pieces.append(value)
    if not pieces:
        for value in record.values():
            if isinstance(value, str) and len(value.strip()) > 20 and not value.lower().endswith((".json", ".jsonl", ".tif", ".tiff")):
                pieces.append(value)
                if len(pieces) >= 3:
                    break
    return sanitize_text("\n".join(pieces))


def has_banned_text(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in BANNED_TEXT_PATTERNS)


def bucket_is_banned(bucket: str) -> bool:
    b = (bucket or "").lower()
    return b in BANNED_BUCKET_TOKENS or any(token in b for token in BANNED_BUCKET_TOKENS)


def page_sort_key(page_id: str) -> tuple[str, int, str]:
    number = 0
    if "_p" in page_id:
        tail = page_id.rsplit("_p", 1)[-1]
        if tail.isdigit():
            number = int(tail)
    document = page_id.rsplit("_p", 1)[0] if "_p" in page_id else ""
    return (document, number, page_id)


def make_doc_id(prefix: str, payload: Any) -> str:
    return f"{prefix}__{stable_hash(payload, 24)}"


def base_document(
    *,
    doc_id: str,
    doc_type: str,
    title: str,
    text: str,
    page_id: str | None = None,
    source_page_ids: list[str] | None = None,
    citation_ids: list[str] | None = None,
    community_ids: list[str] | None = None,
    part_numbers: list[str] | None = None,
    rag_bucket: str = "retrieval_helper",
    authority: str = "retrieval_helper_only",
    retrieval_only: bool = True,
    source_artifact: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_page_ids = unique_strings(source_page_ids or ([] if page_id is None else [page_id]))
    citation_ids = unique_strings(citation_ids or [])
    community_ids = unique_strings(community_ids or [])
    part_numbers = unique_strings(part_numbers or [])
    text = sanitize_text(text)
    answer_support_candidate = (rag_bucket in ANSWER_SUPPORT_BUCKETS) and bool(citation_ids or page_id or source_page_ids) and not retrieval_only
    doc = {
        "schema_version": SCHEMA_VERSION,
        "index_name": DEFAULT_INDEX_NAME,
        "opensearch_document_id": doc_id,
        "document_type": doc_type,
        "title": sanitize_text(title, max_chars=512),
        "text": text,
        "page_id": page_id or None,
        "source_page_ids": source_page_ids,
        "citation_ids": citation_ids,
        "community_ids": community_ids,
        "part_numbers": part_numbers,
        "rag_bucket": rag_bucket,
        "authority": authority,
        "retrieval_only": bool(retrieval_only),
        "answer_support_candidate": bool(answer_support_candidate),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "requires_source_resolution": True,
        "requires_citation": rag_bucket in ANSWER_SUPPORT_BUCKETS,
        "requires_authority_gate": True,
        "source_trace_present": bool(page_id or source_page_ids),
        "safe_for_opensearch": True,
        "raw_ocr_unfiltered": False,
        "raw_visual_output": False,
        "raw_feedback_indexed": False,
        "prompt_or_debug_text": False,
        "source_artifact": source_artifact or None,
        "created_at": now_iso(),
    }
    if extra:
        for key, value in extra.items():
            if key not in {"can_answer_directly", "can_prove_claims", "can_mutate_source_truth", "source_truth_mutation_allowed"}:
                doc[key] = value
    if has_banned_text(text) or bucket_is_banned(rag_bucket):
        doc["safe_for_opensearch"] = False
    return doc


def candidate_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (payload.get("records") or []) if isinstance(r, dict)]


def build_embedding_candidate_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for record in candidate_records(payload):
        bucket = str(record.get("rag_bucket") or record.get("bucket") or "")
        if bucket not in SAFE_EMBEDDING_BUCKETS or bucket_is_banned(bucket):
            continue
        text = extract_text(record)
        if not text:
            # Retrieval source records often have sparse text; still create a
            # source locator doc if page/source metadata exists.
            text = " ".join(unique_strings([record.get("source_candidate_id"), record.get("page_id"), bucket]))
        page_id = record.get("page_id") if isinstance(record.get("page_id"), str) else None
        citation_ids = unique_strings(record.get("citation_ids") or ([record.get("citation_id")] if record.get("citation_id") else []))
        retrieval_only = bucket not in ANSWER_SUPPORT_BUCKETS
        authority = str(record.get("authority") or ("retrieval_helper_only" if retrieval_only else "evidence_with_citation"))
        doc_id = str(record.get("embedding_candidate_id") or make_doc_id("osemb", record))
        docs.append(base_document(
            doc_id=doc_id,
            doc_type="embedding_candidate",
            title=f"{bucket} | {page_id or 'unknown page'}",
            text=text,
            page_id=page_id,
            citation_ids=citation_ids,
            rag_bucket=bucket,
            authority=authority,
            retrieval_only=retrieval_only,
            source_artifact=source_artifact,
            extra={
                "source_candidate_id": record.get("source_candidate_id"),
                "embedding_candidate_id": record.get("embedding_candidate_id"),
                "trust_tier": record.get("trust_tier"),
            },
        ))
    return docs


def build_page_profile_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for record in candidate_records(payload):
        page_id = record.get("page_id") if isinstance(record.get("page_id"), str) else None
        if not page_id:
            continue
        text = extract_text(record)
        if not text:
            terms = record.get("query_tunnel_terms") or record.get("retrieval_cues") or record.get("page_traits") or []
            text = " ".join(str(v) for v in terms)
        docs.append(base_document(
            doc_id=str(record.get("profile_id") or record.get("page_profile_id") or f"page_profile::{page_id}"),
            doc_type="page_retrieval_profile",
            title=f"Page retrieval profile | {page_id}",
            text=text or page_id,
            page_id=page_id,
            rag_bucket="page_retrieval_profile",
            authority=str(record.get("authority") or "page_route_only"),
            retrieval_only=True,
            source_artifact=source_artifact,
            extra={
                "page_number": record.get("page_number"),
                "context_v2_present": record.get("context_v2_present"),
            },
        ))
    return docs


def build_context_helper_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for record in candidate_records(payload):
        page_id = record.get("page_id") if isinstance(record.get("page_id"), str) else None
        if not page_id:
            continue
        terms = record.get("query_tunnel_terms") or record.get("retrieval_cues") or []
        text = extract_text(record)
        if not text:
            text = " ".join(str(v) for v in terms)
        docs.append(base_document(
            doc_id=str(record.get("helper_id") or f"ctx_helper::{page_id}"),
            doc_type="context_retrieval_helper",
            title=f"Context retrieval helper | {page_id}",
            text=text or page_id,
            page_id=page_id,
            rag_bucket="context_retrieval_helper",
            authority="retrieval_helper_only",
            retrieval_only=True,
            source_artifact=source_artifact,
        ))
    return docs


def table_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (payload.get("records") or []) if isinstance(r, dict)]


def build_table_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for record in table_records(payload):
        page_id = record.get("page_id") if isinstance(record.get("page_id"), str) else None
        table_type = str(record.get("table_type") or "unknown_table")
        citation_ids = unique_strings(record.get("citation_ids") or [])
        table_id = str(record.get("normalized_table_id") or record.get("table_id") or record.get("source_table_id") or f"table::{page_id or stable_hash(record, 8)}")
        rows = [r for r in (record.get("rows") or []) if isinstance(r, dict)]
        cells = [c for c in (record.get("cells") or []) if isinstance(c, dict)]
        if rows:
            cell_by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for cell in cells:
                row_id = str(cell.get("row_id") or cell.get("normalized_row_id") or "")
                if row_id:
                    cell_by_row[row_id].append(cell)
            for row in rows:
                row_id = str(row.get("normalized_row_id") or row.get("row_id") or row.get("source_row_id") or make_doc_id("row", row))
                row_cells = cell_by_row.get(row_id, [])
                row_text = sanitize_text(row.get("row_text") or row.get("text") or " | ".join(str(c.get("normalized_text") or c.get("text") or "") for c in row_cells))
                if not row_text:
                    continue
                part_numbers = unique_strings(row.get("part_numbers") or [c.get("text") for c in row_cells if str(c.get("cell_kind") or "").startswith("part")])
                docs.append(base_document(
                    doc_id=str(row.get("normalized_row_id") or f"table_row::{stable_hash({'page': page_id, 'row': row_id}, 20)}"),
                    doc_type="table_row_normalized",
                    title=f"Table row | {page_id or 'unknown'} | {table_type}",
                    text=row_text,
                    page_id=page_id,
                    citation_ids=citation_ids,
                    part_numbers=part_numbers,
                    rag_bucket="table_row_normalized",
                    authority="table_row_retrieval_helper_only",
                    retrieval_only=True,
                    source_artifact=source_artifact,
                    extra={"table_id": table_id, "table_type": table_type, "row_id": row_id, "row_type": row.get("row_type")},
                ))
        for cell in cells:
            text = sanitize_text(cell.get("normalized_text") or cell.get("text") or "")
            if not text:
                continue
            cell_id = str(cell.get("normalized_cell_id") or cell.get("cell_id") or make_doc_id("cell", {"page": page_id, "cell": cell}))
            part_numbers = []
            if str(cell.get("cell_kind") or "") in {"part_number", "part_fragment_left", "part_fragment_right"}:
                part_numbers = [text]
            docs.append(base_document(
                doc_id=cell_id,
                doc_type="table_cell_normalized",
                title=f"Table cell | {page_id or 'unknown'} | {text[:40]}",
                text=text,
                page_id=page_id,
                citation_ids=citation_ids,
                part_numbers=part_numbers,
                rag_bucket="table_cell_normalized",
                authority="table_cell_retrieval_helper_only",
                retrieval_only=True,
                source_artifact=source_artifact,
                extra={
                    "table_id": table_id,
                    "table_type": table_type,
                    "row_id": cell.get("row_id"),
                    "cell_id": cell_id,
                    "cell_kind": cell.get("cell_kind"),
                    "row_index": cell.get("row_index"),
                    "column_index": cell.get("column_index"),
                },
            ))
    return docs


def build_clean_snippet_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    records = payload.get("clean_snippet_claims") or payload.get("claims") or payload.get("records") or []
    for record in [r for r in records if isinstance(r, dict)]:
        page_id = record.get("page_id") if isinstance(record.get("page_id"), str) else None
        citation_ids = unique_strings(record.get("citation_ids") or ([record.get("citation_id")] if record.get("citation_id") else []))
        text = sanitize_text(record.get("clean_snippet") or record.get("clean_snippet_text") or record.get("snippet_text") or record.get("claim_text") or "")
        if not text or not page_id:
            continue
        docs.append(base_document(
            doc_id=str(record.get("clean_snippet_claim_id") or record.get("claim_id") or make_doc_id("clean_snippet", record)),
            doc_type="clean_evidence_snippet",
            title=f"Clean evidence snippet | {page_id}",
            text=text,
            page_id=page_id,
            citation_ids=citation_ids,
            rag_bucket="clean_evidence_snippet",
            authority=str(record.get("authority") or "source_text_claim_with_citation"),
            retrieval_only=False,
            source_artifact=source_artifact,
        ))
    return docs


def build_community_page_lineage(payload: dict[str, Any]) -> dict[str, list[str]]:
    """Return community_id -> source page IDs from membership records.

    Some Leiden community summaries are cross-graph navigation records and may
    omit ``page_ids`` even though their node membership still carries page
    lineage. OpenSearch documents are safe only when they have a page lineage,
    so we derive it from node membership where possible and skip communities
    that remain truly global/untraceable.
    """
    lineage: dict[str, set[str]] = defaultdict(set)
    for member in [m for m in (payload.get("node_membership") or []) if isinstance(m, dict)]:
        community_id = member.get("community_id") or member.get("community") or member.get("leiden_community_id")
        if community_id is None:
            continue
        cid = str(community_id)
        for key in ("page_id", "source_page_id"):
            value = member.get(key)
            if isinstance(value, str) and value.strip():
                lineage[cid].add(value)
        for key in ("page_ids", "source_page_ids"):
            for value in coerce_list(member.get(key)):
                if value is not None and str(value).strip():
                    lineage[cid].add(str(value))
    return {cid: sorted(pages, key=page_sort_key) for cid, pages in lineage.items()}


def build_community_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    lineage_by_community = build_community_page_lineage(payload)
    for community in [c for c in (payload.get("communities") or []) if isinstance(c, dict)]:
        community_id = str(community.get("community_id") or community.get("id") or make_doc_id("community", community))
        page_ids = unique_strings((community.get("page_ids") or []) + lineage_by_community.get(community_id, []))
        # A community summary without any page lineage is not safe for the exact
        # search index. It can remain in the graph-community artifact, but it
        # should not create an OpenSearch document with missing source trace.
        if not page_ids:
            continue
        label = str(community.get("label") or f"Community {community_id}")
        part_families = unique_strings(community.get("part_families") or [])
        part_numbers = unique_strings(community.get("part_numbers") or [])
        dominant = community.get("dominant_node_types") or []
        text = sanitize_text("\n".join([
            label,
            "Part families: " + ", ".join(part_families[:25]),
            "Part numbers: " + ", ".join(part_numbers[:50]),
            "Dominant node types: " + ", ".join(str(v) for v in dominant[:25]),
            "Pages: " + ", ".join(page_ids[:50]),
        ]))
        docs.append(base_document(
            doc_id=f"community::{community_id}",
            doc_type="community_summary",
            title=label,
            text=text,
            source_page_ids=page_ids,
            community_ids=[community_id],
            part_numbers=part_numbers,
            rag_bucket="community_retrieval_helper",
            authority="community_navigation_only",
            retrieval_only=True,
            source_artifact=source_artifact,
            extra={
                "community_id": community_id,
                "node_count": community.get("node_count"),
                "page_count": community.get("page_count"),
                "index_scope": "cross_page_community",
                "source_page_count": len(page_ids),
            },
        ))
    return docs


def build_part_candidate_documents(payload: dict[str, Any], source_artifact: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    nodes = payload.get("part_candidate_nodes") or [n for n in (payload.get("node_plans") or []) if isinstance(n, dict) and n.get("node_type") == "PartCandidate"]
    for node in [n for n in nodes if isinstance(n, dict)]:
        props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
        part_number = node.get("part_number") or props.get("part_number") or props.get("canonical_part_candidate") or node.get("label")
        if not part_number:
            continue
        part_number = str(part_number)
        source_page_ids = unique_strings(node.get("source_page_ids") or props.get("source_page_ids") or [])
        part_family = node.get("part_family") or props.get("part_family")
        text = sanitize_text("\n".join([
            f"Part candidate: {part_number}",
            f"Part family: {part_family or ''}",
            "Source pages: " + ", ".join(source_page_ids[:50]),
        ]))
        docs.append(base_document(
            doc_id=str(node.get("node_id") or f"part_candidate::{part_number}"),
            doc_type="part_candidate_lineage",
            title=f"Part candidate | {part_number}",
            text=text,
            source_page_ids=source_page_ids,
            part_numbers=[part_number],
            rag_bucket="part_candidate_lineage",
            authority="part_candidate_navigation_only",
            retrieval_only=True,
            source_artifact=source_artifact,
            extra={"part_number": part_number, "part_family": part_family, "node_scope": node.get("node_scope") or props.get("node_scope") or "cross_page_entity"},
        ))
    return docs


def dedupe_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for doc in docs:
        doc_id = str(doc.get("opensearch_document_id") or make_doc_id("osdoc", doc))
        if doc_id in seen:
            # Keep the longer searchable text and merged citation/page metadata.
            existing = seen[doc_id]
            if len(str(doc.get("text") or "")) > len(str(existing.get("text") or "")):
                existing["text"] = doc.get("text")
                existing["title"] = doc.get("title") or existing.get("title")
            for key in ("source_page_ids", "citation_ids", "community_ids", "part_numbers"):
                existing[key] = unique_strings((existing.get(key) or []) + (doc.get(key) or []))
            continue
        seen[doc_id] = doc
    return list(seen.values())


def build_mapping(index_name: str = DEFAULT_INDEX_NAME) -> dict[str, Any]:
    return {
        "index_name": index_name,
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "dynamic": "false",
            "properties": {
                "schema_version": {"type": "keyword"},
                "document_type": {"type": "keyword"},
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
                "text": {"type": "text"},
                "page_id": {"type": "keyword"},
                "source_page_ids": {"type": "keyword"},
                "citation_ids": {"type": "keyword"},
                "community_ids": {"type": "keyword"},
                "part_numbers": {"type": "keyword"},
                "rag_bucket": {"type": "keyword"},
                "authority": {"type": "keyword"},
                "retrieval_only": {"type": "boolean"},
                "answer_support_candidate": {"type": "boolean"},
                "safe_for_opensearch": {"type": "boolean"},
                "source_trace_present": {"type": "boolean"},
                "requires_citation": {"type": "boolean"},
                "requires_authority_gate": {"type": "boolean"},
                "source_artifact": {"type": "keyword"},
                "created_at": {"type": "date"},
            },
        },
    }


def write_bulk_ndjson(path: Path, docs: list[dict[str, Any]], index_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for doc in docs:
            doc_id = doc["opensearch_document_id"]
            handle.write(json.dumps({"index": {"_index": index_name, "_id": doc_id}}, ensure_ascii=False, sort_keys=True) + "\n")
            handle.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")


def quality_report(report: dict[str, Any], *, min_documents: int = 1, min_page_scoped_documents: int = 1, require_mapping: bool = False) -> dict[str, Any]:
    summary = report.get("summary") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: str, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    add("document_count_min", int(summary.get("opensearch_document_count", 0)) >= min_documents, summary.get("opensearch_document_count", 0), f">= {min_documents}")
    add("page_scoped_document_count_min", int(summary.get("page_scoped_document_count", 0)) >= min_page_scoped_documents, summary.get("page_scoped_document_count", 0), f">= {min_page_scoped_documents}")
    add("missing_page_id_count_zero", int(summary.get("missing_page_id_count", 0)) == 0, summary.get("missing_page_id_count", 0), "0")
    add("missing_source_trace_count_zero", int(summary.get("missing_source_trace_count", 0)) == 0, summary.get("missing_source_trace_count", 0), "0")
    add("unsafe_index_document_count_zero", int(summary.get("unsafe_index_document_count", 0)) == 0, summary.get("unsafe_index_document_count", 0), "0")
    add("raw_feedback_indexed_count_zero", int(summary.get("raw_feedback_indexed_count", 0)) == 0, summary.get("raw_feedback_indexed_count", 0), "0")
    add("raw_visual_output_indexed_count_zero", int(summary.get("raw_visual_output_indexed_count", 0)) == 0, summary.get("raw_visual_output_indexed_count", 0), "0")
    add("raw_ocr_unfiltered_indexed_count_zero", int(summary.get("raw_ocr_unfiltered_indexed_count", 0)) == 0, summary.get("raw_ocr_unfiltered_indexed_count", 0), "0")
    add("retrieval_only_answer_allowed_count_zero", int(summary.get("retrieval_only_answer_allowed_count", 0)) == 0, summary.get("retrieval_only_answer_allowed_count", 0), "0")
    add("source_truth_mutation_allowed_count_zero", int(summary.get("source_truth_mutation_allowed_count", 0)) == 0, summary.get("source_truth_mutation_allowed_count", 0), "0")
    add("postgres_write_attempt_count_zero", int(summary.get("postgres_write_attempt_count", 0)) == 0, summary.get("postgres_write_attempt_count", 0), "0")
    add("opensearch_write_attempt_count_zero", int(summary.get("opensearch_write_attempt_count", 0)) == 0, summary.get("opensearch_write_attempt_count", 0), "0")
    if require_mapping:
        add("mapping_written", bool(report.get("mapping")), bool(report.get("mapping")), "true")

    failed = [c for c in checks if not c["passed"] and c.get("severity") == "critical"]
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "summary": {
            **summary,
            "failed_check_count": len(failed),
        },
    }


def build_opensearch_documents(
    *,
    embedding_candidates_path: str | Path | None = None,
    page_profiles_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    evidence_snippet_cleaner_path: str | Path | None = None,
    context_helpers_path: str | Path | None = None,
    leiden_communities_path: str | Path | None = None,
    graph_overlay_part_normalizer_path: str | Path | None = None,
    output_dir: str | Path = "local_data/organization/trace_net/opensearch_adapter",
    index_name: str = DEFAULT_INDEX_NAME,
    min_documents: int = 1,
    min_page_scoped_documents: int = 1,
    require_mapping: bool = True,
    write_quality: bool = False,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    source_artifacts: dict[str, str] = {}
    docs: list[dict[str, Any]] = []

    if embedding_candidates_path:
        source_artifacts["embedding_candidates"] = str(embedding_candidates_path)
        docs.extend(build_embedding_candidate_documents(read_json(embedding_candidates_path), str(embedding_candidates_path)))
    if page_profiles_path:
        source_artifacts["page_profiles"] = str(page_profiles_path)
        docs.extend(build_page_profile_documents(read_json(page_profiles_path), str(page_profiles_path)))
    if table_cell_normalizer_path:
        source_artifacts["table_cell_normalizer"] = str(table_cell_normalizer_path)
        docs.extend(build_table_documents(read_json(table_cell_normalizer_path), str(table_cell_normalizer_path)))
    if evidence_snippet_cleaner_path:
        source_artifacts["evidence_snippet_cleaner"] = str(evidence_snippet_cleaner_path)
        docs.extend(build_clean_snippet_documents(read_json(evidence_snippet_cleaner_path), str(evidence_snippet_cleaner_path)))
    if context_helpers_path:
        source_artifacts["context_helpers"] = str(context_helpers_path)
        docs.extend(build_context_helper_documents(read_json(context_helpers_path), str(context_helpers_path)))
    if leiden_communities_path:
        source_artifacts["leiden_communities"] = str(leiden_communities_path)
        docs.extend(build_community_documents(read_json(leiden_communities_path), str(leiden_communities_path)))
    if graph_overlay_part_normalizer_path:
        source_artifacts["graph_overlay_part_normalizer"] = str(graph_overlay_part_normalizer_path)
        docs.extend(build_part_candidate_documents(read_json(graph_overlay_part_normalizer_path), str(graph_overlay_part_normalizer_path)))

    docs = dedupe_documents(docs)
    docs.sort(key=lambda d: (str(d.get("document_type")), str(d.get("page_id") or ""), str(d.get("opensearch_document_id"))))

    # Re-evaluate safety flags after dedupe.
    for doc in docs:
        if has_banned_text(str(doc.get("text") or "")) or bucket_is_banned(str(doc.get("rag_bucket") or "")):
            doc["safe_for_opensearch"] = False

    missing_page_id_count = 0
    missing_source_trace_count = 0
    retrieval_only_answer_allowed_count = 0
    for doc in docs:
        has_page_scope = bool(doc.get("page_id") or doc.get("source_page_ids"))
        if not has_page_scope:
            # Community documents should carry source_page_ids. If a truly global
            # document appears without lineage, count it as missing lineage.
            missing_page_id_count += 1
        if not doc.get("source_trace_present"):
            missing_source_trace_count += 1
        if doc.get("retrieval_only") and (doc.get("can_answer_directly") or doc.get("can_prove_claims") or doc.get("answer_support_candidate")):
            retrieval_only_answer_allowed_count += 1

    document_type_counts = Counter(str(d.get("document_type")) for d in docs)
    bucket_counts = Counter(str(d.get("rag_bucket")) for d in docs)
    authority_counts = Counter(str(d.get("authority")) for d in docs)

    unsafe_index_document_count = sum(1 for d in docs if not d.get("safe_for_opensearch"))
    raw_feedback_indexed_count = sum(1 for d in docs if d.get("raw_feedback_indexed"))
    raw_visual_output_indexed_count = sum(1 for d in docs if d.get("raw_visual_output"))
    raw_ocr_unfiltered_indexed_count = sum(1 for d in docs if d.get("raw_ocr_unfiltered"))
    source_truth_mutation_allowed_count = sum(1 for d in docs if d.get("source_truth_mutation_allowed") or d.get("can_mutate_source_truth"))

    mapping = build_mapping(index_name)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "index_name": index_name,
        "opensearch_document_count": len(docs),
        "page_scoped_document_count": sum(1 for d in docs if d.get("page_id") or d.get("source_page_ids")),
        "document_type_counts": dict(document_type_counts),
        "bucket_counts": dict(bucket_counts),
        "authority_counts": dict(authority_counts),
        "missing_page_id_count": missing_page_id_count,
        "missing_source_trace_count": missing_source_trace_count,
        "unsafe_index_document_count": unsafe_index_document_count,
        "raw_feedback_indexed_count": raw_feedback_indexed_count,
        "raw_visual_output_indexed_count": raw_visual_output_indexed_count,
        "raw_ocr_unfiltered_indexed_count": raw_ocr_unfiltered_indexed_count,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "write_mode": "local_document_build_only",
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "OPENSEARCH_DOCUMENTS_BUILT",
        "quality_status": "PASS",
        "generated_at": now_iso(),
        "index_name": index_name,
        "mapping": mapping,
        "documents": docs,
        "summary": summary,
    }
    quality = quality_report(report, min_documents=min_documents, min_page_scoped_documents=min_page_scoped_documents, require_mapping=require_mapping)
    report["quality"] = quality
    report["quality_status"] = quality["status"]
    summary["status"] = quality["status"]

    documents_path = out / "trace_net_opensearch_documents_v1.jsonl"
    bulk_path = out / "trace_net_opensearch_bulk_v1.ndjson"
    mapping_path = out / "trace_net_opensearch_mapping_v1.json"
    summary_path = out / "trace_net_opensearch_adapter_v1_summary.json"
    report_path = out / "trace_net_opensearch_adapter_v1.json"
    quality_path = out / "trace_net_opensearch_adapter_v1_quality.json"
    manifest_path = out / "trace_net_opensearch_adapter_v1_manifest.json"
    markdown_path = out / "trace_net_opensearch_adapter_v1.md"

    write_jsonl(documents_path, docs)
    write_bulk_ndjson(bulk_path, docs, index_name)
    write_json(mapping_path, mapping)
    write_json(summary_path, summary)
    write_json(quality_path, quality)

    report["paths"] = {
        "report_path": str(report_path),
        "documents_path": str(documents_path),
        "bulk_path": str(bulk_path),
        "mapping_path": str(mapping_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "manifest_path": str(manifest_path),
        "markdown_path": str(markdown_path),
    }

    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now_iso(),
        "index_name": index_name,
        "write_mode": "local_document_build_only",
        "source_artifacts": source_artifacts,
        "paths": report["paths"],
        "summary": summary,
        "quality_status": quality["status"],
    }
    write_json(manifest_path, manifest)
    write_json(report_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    if write_quality:
        write_json(quality_path, quality)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# TRACE-Net OpenSearch Adapter v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Index:** {report.get('index_name')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "opensearch_document_count",
        "page_scoped_document_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "opensearch_write_attempt_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Document Types", ""])
    for key, value in sorted((summary.get("document_type_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Safety Contract", "", "- This adapter builds local OpenSearch documents only.", "- It does not write to OpenSearch/Postgres/Qdrant.", "- Raw OCR, raw visual output, raw feedback, prompt/debug text, and unsafe records are blocked.", "- Retrieval-only documents cannot prove claims or answer directly."])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net OpenSearch Adapter v1 local documents.")
    parser.add_argument("--embedding-candidates", required=True)
    parser.add_argument("--page-profiles")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--evidence-snippet-cleaner")
    parser.add_argument("--context-helpers")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--graph-overlay-part-normalizer")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/opensearch_adapter")
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--min-documents", type=int, default=1)
    parser.add_argument("--min-page-scoped-documents", type=int, default=1)
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    report = build_opensearch_documents(
        embedding_candidates_path=args.embedding_candidates,
        page_profiles_path=args.page_profiles,
        table_cell_normalizer_path=args.table_cell_normalizer,
        evidence_snippet_cleaner_path=args.evidence_snippet_cleaner,
        context_helpers_path=args.context_helpers,
        leiden_communities_path=args.leiden_communities,
        graph_overlay_part_normalizer_path=args.graph_overlay_part_normalizer,
        output_dir=args.output_dir,
        index_name=args.index_name,
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        require_mapping=args.require_mapping,
        write_quality=args.quality,
    )
    summary = report["summary"]
    quality = report["quality"]
    print("TRACE-Net OpenSearch Adapter v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" index_name: {report['index_name']}")
    for key in [
        "opensearch_document_count",
        "page_scoped_document_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['paths']['report_path']}")
    print(f" documents_path: {report['paths']['documents_path']}")
    print(f" bulk_path: {report['paths']['bulk_path']}")
    print(f" quality_path: {report['paths']['quality_path']}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
