"""TRACE-Net Page Retrieval Profiles v1.

Step 5.5 builds one safe page-level retrieval profile for each manual page and
optionally loads those profiles into a separate Qdrant collection.

A page retrieval profile is a coarse routing/tunnel vector. It is not source
truth, not answer authority, and not claim proof. A hit on this collection must
resolve back through Postgres/source/citation/trust gates before answer use.
The optional Qdrant loader supports hash smoke-test vectors, SentenceTransformers,
and local Ollama embeddings via ``/api/embed``.
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
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SCHEMA_VERSION = "trace_net_page_retrieval_profiles_v1"
QDRANT_SCHEMA_VERSION = "trace_net_page_retrieval_profiles_qdrant_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/page_retrieval_profiles")
DEFAULT_PROFILES_FILE = "trace_net_page_retrieval_profiles_v1.json"
DEFAULT_PROFILES_JSONL_FILE = "trace_net_page_retrieval_profiles_v1.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_page_retrieval_profiles_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_page_retrieval_profiles_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_page_retrieval_profiles_v1_quality.json"
DEFAULT_REJECTED_FILE = "trace_net_page_retrieval_profiles_v1_rejected.jsonl"
DEFAULT_QDRANT_OUTPUT_DIR = Path("local_data/organization/trace_net/qdrant_page_retrieval_profiles")
DEFAULT_QDRANT_MANIFEST_FILE = "trace_net_page_retrieval_profiles_qdrant_v1_manifest.json"
DEFAULT_QDRANT_SUMMARY_FILE = "trace_net_page_retrieval_profiles_qdrant_v1_summary.json"
DEFAULT_QDRANT_QUALITY_FILE = "trace_net_page_retrieval_profiles_qdrant_v1_quality.json"
DEFAULT_QDRANT_REJECTED_FILE = "trace_net_page_retrieval_profiles_qdrant_v1_rejected.jsonl"
DEFAULT_QDRANT_POINTS_PREVIEW_FILE = "trace_net_page_retrieval_profiles_qdrant_v1_points_preview.jsonl"
DEFAULT_COLLECTION = "trace_net_page_retrieval_profiles_v1"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_EMBEDDING_DIM = 384
DEFAULT_EMBEDDING_MODE = "hash"
DEFAULT_REAL_EMBEDDING_MODE = "sentence-transformers"
DEFAULT_REAL_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_OLLAMA_EMBEDDING_MODEL = "bge-m3:latest"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_EMBED_ENDPOINT = "/api/embed"
DEFAULT_OLLAMA_TIMEOUT = 120.0
DEFAULT_REAL_EMBEDDING_DIM = 1024
DEFAULT_EMBEDDING_BATCH_SIZE = 32
DEFAULT_DISTANCE = "Cosine"
DEFAULT_BATCH_SIZE = 128
DEFAULT_FALLBACK_DOC = "t_p_120_1176"
DEFAULT_EMBEDDING_CANDIDATES = Path(
    "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"
)
DEFAULT_CONTEXT_HELPERS = Path(
    "local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json"
)
DEFAULT_BASELINE_CHECKPOINT = Path(
    "local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/"
    "trace_net_graph_baseline_checkpoint_v1.json"
)
DEFAULT_EMBEDDING_CANDIDATE_QUALITY_FILE = "trace_net_embedding_candidates_v1_quality.json"
DEFAULT_CONTEXT_HELPER_QUALITY_FILE = "trace_net_context_retrieval_helpers_v1_quality.json"
DEFAULT_BASELINE_QUALITY_FILE = "trace_net_graph_baseline_checkpoint_v1_quality.json"

PAGE_PROFILE_BUCKET = "page_retrieval_profile"
PAGE_PROFILE_AUTHORITY = "page_route_only"
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/#-]*")
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_TRANSFORMER_MODES = {"sentence-transformers", "sentence_transformers", "sbert", "bge-m3", "bge_m3", "real"}
OLLAMA_EMBEDDING_MODES = {"ollama", "ollama-embed", "ollama_embed", "ollama-embeddings", "ollama_embeddings"}
_SENTENCE_TRANSFORMER_MODEL_CACHE: dict[tuple[str, str], Any] = {}
PAGE_NUMBER_RE = re.compile(r"(\d+)(?!.*\d)")
SAFE_SUFFIX_RE = re.compile(r"[^A-Za-z0-9_.-]+")
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "trace-net/page-retrieval-profile/v1")

SAFE_VECTOR_ALLOWED_USE = ["retrieve", "rank", "route", "candidate_discovery", "page_route"]
FORBIDDEN_USE = [
    "direct_answer_from_vector_hit",
    "claim_proof_from_vector_payload",
    "canonical_source_truth",
    "source_truth_mutation",
    "citation_replacement",
    "trust_tier_override",
    "answer_without_postgres_resolution",
]


class PageRetrievalProfileError(RuntimeError):
    """Raised when page retrieval profiles cannot be built or checked safely."""


@dataclass(frozen=True)
class QualityResult:
    status: str
    checks: list[dict[str, Any]]
    summary: dict[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(v) for v in value]
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    raw = "|".join(as_text(part) for part in parts)
    return f"{prefix}__{sha256_text(raw)[:length]}"


def stable_uuid(*parts: Any) -> str:
    raw = "|".join(as_text(part) for part in parts)
    return str(uuid.uuid5(UUID_NAMESPACE, raw))


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = as_text(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def first_text(*values: Any) -> str:
    for value in values:
        text = as_text(value).strip()
        if text:
            return text
    return ""


def compact_text(value: Any, *, max_chars: int = 6000) -> str:
    raw = as_text(value).replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    compact = WHITESPACE_RE.sub(" ", raw).strip()
    if len(compact) > max_chars:
        return compact[: max_chars - 3].rstrip() + "..."
    return compact


def normalize_bucket(value: Any) -> str:
    text = as_text(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "page_profile": PAGE_PROFILE_BUCKET,
        "page_route": PAGE_PROFILE_BUCKET,
        "page_routing_profile": PAGE_PROFILE_BUCKET,
        "source": "source_evidence",
        "source_trace": "source_evidence",
        "source_text": "source_text_evidence",
        "context_helper": "context_retrieval_helper",
        "page_context_v2": "context_retrieval_helper",
    }
    return aliases.get(text, text)


def safe_suffix(text: Any, *, fallback: str = "value") -> str:
    cleaned = SAFE_SUFFIX_RE.sub("_", as_text(text).strip()).strip("_")
    return cleaned or fallback


def parse_page_number(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
        text = as_text(value).strip()
        if not text:
            continue
        if text.isdigit():
            return int(text)
        match = PAGE_NUMBER_RE.search(text)
        if match:
            return int(match.group(1))
    return None


def canonical_page_id(value: Any, *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    text = as_text(value).strip()
    if re.search(r"_p\d{6}$", text):
        return text
    if text.startswith("page:"):
        text = text.split(":", 1)[1]
    page_num = parse_page_number(text)
    if page_num is not None:
        return f"{fallback_doc}_p{page_num:06d}"
    return text


def parse_page_range(spec: str | None) -> list[int]:
    if not spec:
        return []
    pages: set[int] = set()
    for part in spec.split(","):
        text = part.strip()
        if not text:
            continue
        if "-" in text:
            left, right = text.split("-", 1)
            start, end = int(left), int(right)
            if end < start:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(text))
    return sorted(pages)


def load_json_artifact(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {}
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        raise PageRetrievalProfileError(f"expected JSON object at {path}")
    return dict(payload)


def load_records_artifact(path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path is None or not Path(path).exists():
        return [], {}
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records, {"records": records, "record_count": len(records)}
    payload = read_json(path)
    if isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
        return [dict(row) for row in payload["records"]], dict(payload)
    if isinstance(payload, list):
        return [dict(row) for row in payload], {"records": payload, "record_count": len(payload)}
    raise PageRetrievalProfileError(f"unsupported record artifact shape: {path}")


def sibling_quality_status(path: Path | None, default_quality_file: str) -> str:
    if path is None:
        return "UNKNOWN"
    quality_path = Path(path).parent / default_quality_file
    if not quality_path.exists():
        return "UNKNOWN"
    payload = load_json_artifact(quality_path)
    return first_text(payload.get("status"), payload.get("quality_status"), payload.get("summary", {}).get("status"), "UNKNOWN")


def _table_exists(conn: Any, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
        row = cur.fetchone()
        return bool(row and row[0])


def _table_columns(conn: Any, table_name: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = %s
            order by ordinal_position
            """,
            (table_name,),
        )
        return [row[0] for row in cur.fetchall()]


def load_table_rows(database_url: str, table_name: str, *, required: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise PageRetrievalProfileError("psycopg is required. Install with: pip install 'psycopg[binary]'.") from exc
    with psycopg.connect(database_url) as conn:
        if not _table_exists(conn, table_name):
            if required:
                raise PageRetrievalProfileError(f"Postgres table {table_name} does not exist.")
            return []
        columns = _table_columns(conn, table_name)
        order_parts = [name for name in ("page_id", "page_number", "node_id", "edge_id", "id") if name in columns]
        sql = f"select * from {table_name}"
        params: tuple[Any, ...] = ()
        if order_parts:
            sql += " order by " + ", ".join(order_parts)
        if limit is not None:
            sql += " limit %s"
            params = (limit,)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            names = [desc.name if hasattr(desc, "name") else desc[0] for desc in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]


def load_postgres_profile_rows(database_url: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "pages": load_table_rows(database_url, "pages", required=True),
        "graph_nodes": load_table_rows(database_url, "graph_nodes", required=False),
        "graph_edges": load_table_rows(database_url, "graph_edges", required=False),
        "page_context_v2_records": load_table_rows(database_url, "page_context_v2_records", required=False),
    }


def page_id_from_page_row(row: Mapping[str, Any], *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    explicit = first_text(
        row.get("page_id"),
        row.get("canonical_page_id"),
        row.get("source_page_id"),
        row.get("document_page_id"),
        row.get("id"),
    )
    if explicit:
        return canonical_page_id(explicit, fallback_doc=fallback_doc)
    page_num = parse_page_number(row.get("page_number"), row.get("page"), row.get("page_label"), row.get("file_name"))
    if page_num is not None:
        return f"{fallback_doc}_p{page_num:06d}"
    return ""


def page_number_from_page_row(row: Mapping[str, Any], page_id: str) -> int | None:
    return parse_page_number(row.get("page_number"), row.get("page"), row.get("page_label"), page_id)


def document_id_from_row(row: Mapping[str, Any], *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    return first_text(row.get("document_id"), row.get("manual_id"), row.get("source_document_id"), row.get("doc_id"), fallback_doc)


def ata_code_from_row(row: Mapping[str, Any]) -> str:
    return first_text(row.get("ata_code"), row.get("ata_section"), row.get("ata"), row.get("chapter_section"), row.get("section"))


def source_text_from_candidate(candidate: Mapping[str, Any]) -> str:
    return first_text(candidate.get("embedding_text"), candidate.get("text"), candidate.get("candidate_text"), candidate.get("content"), candidate.get("summary"))


def source_evidence_by_page(embedding_records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    source_rows: dict[str, dict[str, Any]] = {}
    for row in embedding_records:
        if normalize_bucket(row.get("rag_bucket") or row.get("embedding_bucket") or row.get("candidate_type")) != "source_evidence":
            continue
        page_id = first_text(row.get("page_id"))
        if page_id and page_id not in source_rows:
            source_rows[page_id] = dict(row)
    return source_rows


def bucket_counts_by_page(embedding_records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in embedding_records:
        page_id = first_text(row.get("page_id"))
        if not page_id:
            continue
        bucket = normalize_bucket(row.get("rag_bucket") or row.get("embedding_bucket") or row.get("candidate_type"))
        if bucket:
            counts[page_id][bucket] += 1
    return {page: dict(sorted(counter.items())) for page, counter in counts.items()}


def representative_terms_by_page(embedding_records: Sequence[Mapping[str, Any]], *, max_terms_per_page: int = 20) -> dict[str, list[str]]:
    terms_by_page: dict[str, list[str]] = defaultdict(list)
    seen_by_page: dict[str, set[str]] = defaultdict(set)
    for row in embedding_records:
        page_id = first_text(row.get("page_id"))
        if not page_id:
            continue
        candidates: list[str] = []
        for key in ("query_tunnel_terms", "retrieval_cues", "known_parts", "known_nomenclature"):
            value = row.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                candidates.extend(as_text(item) for item in value)
        text = compact_text(source_text_from_candidate(row), max_chars=500)
        if text:
            candidates.extend(token for token in TOKEN_RE.findall(text)[:12])
        for term in candidates:
            clean = compact_text(term, max_chars=90)
            if len(clean) < 2 or clean.lower() in seen_by_page[page_id]:
                continue
            seen_by_page[page_id].add(clean.lower())
            terms_by_page[page_id].append(clean)
            if len(terms_by_page[page_id]) >= max_terms_per_page:
                break
    return dict(terms_by_page)


def context_by_page(context_records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_page: dict[str, dict[str, Any]] = {}
    for row in context_records:
        page_id = first_text(row.get("page_id"), row.get("canonical_page_id"), row.get("source_page_id"))
        if page_id and page_id not in by_page:
            by_page[page_id] = dict(row)
    return by_page


def context_v2_by_page(context_rows: Sequence[Mapping[str, Any]], *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> dict[str, dict[str, Any]]:
    by_page: dict[str, dict[str, Any]] = {}
    for row in context_rows:
        page_id = first_text(row.get("page_id"), row.get("canonical_page_id"), row.get("source_page_id"))
        if not page_id:
            page_id = canonical_page_id(first_text(row.get("context_id"), row.get("record_id"), row.get("id")), fallback_doc=fallback_doc)
        if page_id and page_id not in by_page:
            by_page[page_id] = dict(row)
    return by_page


def list_from_any(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                loaded = json.loads(stripped)
                return list_from_any(loaded)
            except json.JSONDecodeError:
                pass
        return [compact_text(part, max_chars=160) for part in re.split(r"[\n;|]+", stripped) if compact_text(part, max_chars=160)]
    if isinstance(value, Mapping):
        return [compact_text(f"{k}: {v}", max_chars=160) for k, v in value.items() if compact_text(v, max_chars=160)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out: list[str] = []
        for item in value:
            out.extend(list_from_any(item))
        return out
    return [compact_text(value, max_chars=160)]


def node_id(row: Mapping[str, Any]) -> str:
    return first_text(row.get("node_id"), row.get("id"))


def node_type(row: Mapping[str, Any]) -> str:
    return first_text(row.get("node_type"), row.get("type")).lower()


def node_label(row: Mapping[str, Any]) -> str:
    return first_text(
        row.get("label"),
        row.get("name"),
        row.get("title"),
        row.get("text"),
        row.get("part_number"),
        row.get("nomenclature"),
        row.get("description"),
        row.get("node_id"),
    )


def page_id_from_graph_node(row: Mapping[str, Any], *, fallback_doc: str = DEFAULT_FALLBACK_DOC) -> str:
    explicit = first_text(row.get("page_id"), row.get("canonical_page_id"), row.get("source_page_id"), row.get("document_page_id"))
    if explicit:
        return canonical_page_id(explicit, fallback_doc=fallback_doc)
    return canonical_page_id(node_label(row), fallback_doc=fallback_doc)


def endpoint(edge: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = first_text(edge.get(name))
        if value:
            return value
    return ""


def build_graph_page_terms(
    graph_nodes: Sequence[Mapping[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]],
    *,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_parts_per_page: int = 40,
    max_nomenclature_per_page: int = 40,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    by_id = {node_id(row): dict(row) for row in graph_nodes if node_id(row)}
    nomenclature_by_part: dict[str, set[str]] = defaultdict(set)
    for edge in graph_edges:
        source_id = endpoint(edge, "source_id", "source_node_id", "source", "subject")
        target_id = endpoint(edge, "target_id", "target_node_id", "target", "object")
        source_row = by_id.get(source_id)
        target_row = by_id.get(target_id)
        if not source_row or not target_row:
            continue
        source_type = node_type(source_row)
        target_type = node_type(target_row)
        edge_type = first_text(edge.get("edge_type"), edge.get("type"))
        if edge_type == "HAS_NOMENCLATURE" or {source_type, target_type} == {"part", "nomenclature"}:
            if "part" in source_type and "nomenclature" in target_type:
                part_id, nom_row = source_id, target_row
            elif "part" in target_type and "nomenclature" in source_type:
                part_id, nom_row = target_id, source_row
            else:
                continue
            label = node_label(nom_row)
            if label:
                nomenclature_by_part[part_id].add(label)

    parts_by_page: dict[str, list[str]] = defaultdict(list)
    noms_by_page: dict[str, list[str]] = defaultdict(list)
    seen_parts: dict[str, set[str]] = defaultdict(set)
    seen_noms: dict[str, set[str]] = defaultdict(set)
    for edge in graph_edges:
        source_id = endpoint(edge, "source_id", "source_node_id", "source", "subject")
        target_id = endpoint(edge, "target_id", "target_node_id", "target", "object")
        source_row = by_id.get(source_id)
        target_row = by_id.get(target_id)
        if not source_row or not target_row:
            continue
        source_type = node_type(source_row)
        target_type = node_type(target_row)
        pair_types = {source_type, target_type}
        edge_type = first_text(edge.get("edge_type"), edge.get("type")).upper()
        has_part_page_hint = any(token in edge_type for token in ("PART", "MENTION")) and ("PAGE" in edge_type or "ON_PAGE" in edge_type)
        if not (("page" in pair_types and any("part" in kind for kind in pair_types)) or has_part_page_hint):
            continue
        if "page" in source_type:
            page_row, part_row, part_node_id = source_row, target_row, target_id
        elif "page" in target_type:
            page_row, part_row, part_node_id = target_row, source_row, source_id
        else:
            continue
        if "part" not in node_type(part_row):
            continue
        page_id = page_id_from_graph_node(page_row, fallback_doc=fallback_doc)
        if not page_id:
            continue
        part_label = node_label(part_row)
        if part_label and part_label.lower() not in seen_parts[page_id] and len(parts_by_page[page_id]) < max_parts_per_page:
            seen_parts[page_id].add(part_label.lower())
            parts_by_page[page_id].append(part_label)
        for nom in sorted(nomenclature_by_part.get(part_node_id, set())):
            if nom.lower() not in seen_noms[page_id] and len(noms_by_page[page_id]) < max_nomenclature_per_page:
                seen_noms[page_id].add(nom.lower())
                noms_by_page[page_id].append(nom)
    return dict(parts_by_page), dict(noms_by_page)


def merge_terms(*groups: Iterable[Any], max_terms: int = 80) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            text = compact_text(value, max_chars=160)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= max_terms:
                return out
    return out


def profile_embedding_text(profile: Mapping[str, Any], *, max_text_chars: int = 6000) -> str:
    lines: list[str] = [
        "TRACE-Net page retrieval profile.",
        "Use: route a query to likely pages, then resolve through source-backed evidence.",
        "Authority: page_route_only. This profile cannot answer directly or prove claims.",
        f"Document: {first_text(profile.get('document_id'))}",
        f"Page ID: {first_text(profile.get('page_id'))}",
        f"Page number: {first_text(profile.get('page_number'))}",
    ]
    if first_text(profile.get("ata_code")):
        lines.append(f"ATA: {first_text(profile.get('ata_code'))}")
    if first_text(profile.get("source_url")):
        lines.append(f"Source URL: {first_text(profile.get('source_url'))}")
    if first_text(profile.get("tiff_path")):
        lines.append(f"TIFF path: {first_text(profile.get('tiff_path'))}")
    context_summary = first_text(profile.get("context_v2_summary"), profile.get("summary"))
    if context_summary:
        lines.append(f"ContextV2 retrieval summary: {context_summary}")
    parts = list_from_any(profile.get("known_parts"))[:60]
    if parts:
        lines.append("Known parts on/near page: " + "; ".join(parts))
    noms = list_from_any(profile.get("known_nomenclature"))[:60]
    if noms:
        lines.append("Known part nomenclature on/near page: " + "; ".join(noms))
    cues = list_from_any(profile.get("retrieval_cues"))[:80]
    if cues:
        lines.append("Retrieval cues: " + "; ".join(cues))
    tunnel = list_from_any(profile.get("query_tunnel_terms"))[:80]
    if tunnel:
        lines.append("Query tunnel terms: " + "; ".join(tunnel))
    bucket_counts = profile.get("safe_candidate_bucket_counts") or {}
    if isinstance(bucket_counts, Mapping) and bucket_counts:
        lines.append("Safe evidence buckets on this page: " + "; ".join(f"{k}={v}" for k, v in sorted(bucket_counts.items())))
    return compact_text("\n".join(line for line in lines if compact_text(line)), max_chars=max_text_chars)


def build_page_profile_records(
    pages: Sequence[Mapping[str, Any]],
    *,
    embedding_records: Sequence[Mapping[str, Any]] | None = None,
    context_records: Sequence[Mapping[str, Any]] | None = None,
    page_context_v2_rows: Sequence[Mapping[str, Any]] | None = None,
    graph_nodes: Sequence[Mapping[str, Any]] | None = None,
    graph_edges: Sequence[Mapping[str, Any]] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_embedding_text_chars: int = 6000,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    embedding_records = list(embedding_records or [])
    context_records = list(context_records or [])
    page_context_v2_rows = list(page_context_v2_rows or [])
    source_by_page = source_evidence_by_page(embedding_records)
    buckets_by_page = bucket_counts_by_page(embedding_records)
    representative_terms = representative_terms_by_page(embedding_records)
    context_helpers = context_by_page(context_records)
    context_v2_rows = context_v2_by_page(page_context_v2_rows, fallback_doc=fallback_doc)
    parts_by_page, noms_by_page = build_graph_page_terms(list(graph_nodes or []), list(graph_edges or []), fallback_doc=fallback_doc)

    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_pages: set[str] = set()
    sorted_pages = sorted(pages, key=lambda row: (page_number_from_page_row(row, page_id_from_page_row(row, fallback_doc=fallback_doc)) or 10**9, page_id_from_page_row(row, fallback_doc=fallback_doc)))
    for page in sorted_pages:
        page_id = page_id_from_page_row(page, fallback_doc=fallback_doc)
        page_number = page_number_from_page_row(page, page_id)
        if not page_id:
            rejected.append({"reason": "missing_page_id", "page_row": json_safe(page)})
            continue
        if page_id in seen_pages:
            rejected.append({"reason": "duplicate_page_id", "page_id": page_id})
            continue
        seen_pages.add(page_id)
        source = source_by_page.get(page_id, {})
        helper = context_helpers.get(page_id, {})
        context_v2 = context_v2_rows.get(page_id, {})
        document_id = first_text(document_id_from_row(page, fallback_doc=fallback_doc), source.get("document_id"), helper.get("document_id"), fallback_doc)
        ata_code = first_text(ata_code_from_row(page), source.get("ata_code"), helper.get("ata_code"), context_v2.get("ata_code"))
        context_summary = first_text(
            helper.get("summary"),
            helper.get("context_v2_summary"),
            context_v2.get("summary"),
            context_v2.get("context_summary"),
            context_v2.get("page_summary"),
        )
        source_candidate_id = first_text(source.get("source_candidate_id"), source.get("embedding_candidate_id"), f"page_profile:{page_id}")
        profile_id = stable_id("page_profile", page_id, document_id, page_number)
        known_parts = merge_terms(parts_by_page.get(page_id, []), list_from_any(source.get("known_parts")), max_terms=80)
        known_nomenclature = merge_terms(noms_by_page.get(page_id, []), list_from_any(source.get("known_nomenclature")), max_terms=80)
        retrieval_cues = merge_terms(
            list_from_any(helper.get("retrieval_cues")),
            list_from_any(context_v2.get("retrieval_cues")),
            representative_terms.get(page_id, []),
            known_parts,
            known_nomenclature,
            [ata_code] if ata_code else [],
            max_terms=100,
        )
        query_tunnel_terms = merge_terms(
            list_from_any(helper.get("query_tunnel_terms")),
            list_from_any(context_v2.get("query_tunnel_terms")),
            retrieval_cues,
            [document_id, page_id, f"page {page_number}" if page_number else "", ata_code],
            max_terms=120,
        )
        source_url = first_text(source.get("source_url"), source.get("citation_url"), source.get("url"), page.get("source_url"), page.get("rescarta_url"))
        tiff_path = first_text(source.get("tiff_path"), source.get("source_path"), page.get("tiff_path"), page.get("image_path"), page.get("file_path"))
        ocr_path = first_text(source.get("ocr_path"), page.get("ocr_path"), page.get("text_path"))
        citation_id = first_text(source.get("citation_id"), page.get("citation_id"))
        content_seed = {
            "page_id": page_id,
            "page_number": page_number,
            "document_id": document_id,
            "ata_code": ata_code,
            "source_url": source_url,
            "tiff_path": tiff_path,
            "ocr_path": ocr_path,
            "context_summary": context_summary,
            "known_parts": known_parts,
            "known_nomenclature": known_nomenclature,
            "retrieval_cues": retrieval_cues,
            "query_tunnel_terms": query_tunnel_terms,
        }
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "profile_id": profile_id,
            "embedding_candidate_id": f"embpage__{sha256_json(content_seed)[:24]}",
            "qdrant_point_id": stable_uuid("page_profile", page_id),
            "source_candidate_id": source_candidate_id,
            "source_kind": PAGE_PROFILE_BUCKET,
            "source_table": "pages+graph+embedding_candidates+context_retrieval_helpers",
            "record_type": PAGE_PROFILE_BUCKET,
            "rag_bucket": PAGE_PROFILE_BUCKET,
            "embedding_bucket": PAGE_PROFILE_BUCKET,
            "candidate_type": PAGE_PROFILE_BUCKET,
            "evidence_layer": PAGE_PROFILE_BUCKET,
            "safety_bucket": PAGE_PROFILE_BUCKET,
            "authority": PAGE_PROFILE_AUTHORITY,
            "answer_use_policy": "route_to_page_then_resolve_source_evidence",
            "page_id": page_id,
            "page_number": page_number,
            "document_id": document_id,
            "ata_code": ata_code,
            "retrieval_only": True,
            "page_route_only": True,
            "can_embed": True,
            "can_retrieve": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_prove_source_truth": False,
            "canonical_source_truth": False,
            "can_mutate_source_truth": False,
            "can_override_trust": False,
            "can_replace_citation": False,
            "requires_source_resolution": True,
            "requires_citation": True,
            "requires_authority_gate": True,
            "embedding_answer_authority_allowed": False,
            "allowed_use": list(SAFE_VECTOR_ALLOWED_USE),
            "forbidden_use": list(FORBIDDEN_USE),
            "source_url": source_url,
            "tiff_path": tiff_path,
            "ocr_path": ocr_path,
            "citation_id": citation_id,
            "source_trace_present": bool(source_url or tiff_path or ocr_path or citation_id or source),
            "context_v2_present": bool(helper or context_v2),
            "context_helper_id": first_text(helper.get("helper_id"), helper.get("record_id"), helper.get("id")),
            "context_v2_summary": context_summary,
            "summary": context_summary or f"Page-level retrieval profile for {document_id} page {page_number or page_id}.",
            "known_parts": known_parts,
            "known_nomenclature": known_nomenclature,
            "retrieval_cues": retrieval_cues,
            "query_tunnel_terms": query_tunnel_terms,
            "safe_candidate_bucket_counts": buckets_by_page.get(page_id, {}),
            "traceability": {
                "page_id": page_id,
                "page_table_present": True,
                "source_evidence_candidate_id": first_text(source.get("embedding_candidate_id"), source.get("source_candidate_id")),
                "source_candidate_id": source_candidate_id,
                "context_helper_id": first_text(helper.get("helper_id"), helper.get("record_id"), helper.get("id")),
                "qdrant_hit_must_resolve_to_postgres": True,
                "qdrant_hit_must_use_source_citation": True,
                "profile_is_rebuildable": True,
            },
            "content_sha256": sha256_json(content_seed),
        }
        record["embedding_text"] = profile_embedding_text(record, max_text_chars=max_embedding_text_chars)
        record["text"] = record["embedding_text"]
        records.append(record)
    return records, rejected


def summarize_profiles(
    records: Sequence[Mapping[str, Any]],
    rejected: Sequence[Mapping[str, Any]],
    *,
    required_pages: Sequence[int] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
) -> dict[str, Any]:
    required_pages = list(required_pages or [])
    page_ids = {as_text(row.get("page_id")) for row in records if as_text(row.get("page_id"))}
    required_missing = [f"{fallback_doc}_p{page_num:06d}" for page_num in required_pages if f"{fallback_doc}_p{page_num:06d}" not in page_ids]
    bucket_counts = Counter(normalize_bucket(row.get("rag_bucket")) for row in records)
    authority_counts = Counter(as_text(row.get("authority")) for row in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_count": len(records),
        "rejected_count": len(rejected),
        "page_count": len(page_ids),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "context_v2_profile_count": sum(1 for row in records if as_bool(row.get("context_v2_present"), default=False)),
        "source_trace_profile_count": sum(1 for row in records if as_bool(row.get("source_trace_present"), default=False)),
        "profiles_with_parts_count": sum(1 for row in records if list_from_any(row.get("known_parts"))),
        "profiles_with_nomenclature_count": sum(1 for row in records if list_from_any(row.get("known_nomenclature"))),
        "profiles_with_retrieval_cues_count": sum(1 for row in records if list_from_any(row.get("retrieval_cues"))),
        "profiles_with_query_tunnel_terms_count": sum(1 for row in records if list_from_any(row.get("query_tunnel_terms"))),
        "profiles_with_embedding_text_count": sum(1 for row in records if compact_text(row.get("embedding_text"))),
        "answer_capable_profile_count": sum(1 for row in records if as_bool(row.get("can_answer_directly"), default=False)),
        "claim_proof_profile_count": sum(1 for row in records if as_bool(row.get("can_prove_claims"), default=False)),
        "source_truth_profile_count": sum(1 for row in records if as_bool(row.get("canonical_source_truth"), default=False)),
        "source_truth_mutation_profile_count": sum(1 for row in records if as_bool(row.get("can_mutate_source_truth"), default=False)),
        "embedding_answer_authority_allowed_count": sum(1 for row in records if as_bool(row.get("embedding_answer_authority_allowed"), default=False)),
        "requires_source_resolution_false_count": sum(1 for row in records if as_bool(row.get("requires_source_resolution"), default=False) is not True),
        "requires_citation_false_count": sum(1 for row in records if as_bool(row.get("requires_citation"), default=False) is not True),
        "missing_page_id_count": sum(1 for row in records if not as_text(row.get("page_id"))),
        "missing_profile_id_count": sum(1 for row in records if not as_text(row.get("profile_id"))),
        "missing_embedding_candidate_id_count": sum(1 for row in records if not as_text(row.get("embedding_candidate_id"))),
        "missing_embedding_text_count": sum(1 for row in records if not compact_text(row.get("embedding_text"))),
        "required_page_missing_count": len(required_missing),
        "required_page_missing_ids": required_missing[:100],
    }


def unsafe_profile_reasons(profile: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not as_text(profile.get("profile_id")):
        reasons.append("missing_profile_id")
    if not as_text(profile.get("embedding_candidate_id")):
        reasons.append("missing_embedding_candidate_id")
    if not as_text(profile.get("page_id")):
        reasons.append("missing_page_id")
    if normalize_bucket(profile.get("rag_bucket")) != PAGE_PROFILE_BUCKET:
        reasons.append("wrong_bucket")
    if as_text(profile.get("authority")) != PAGE_PROFILE_AUTHORITY:
        reasons.append("wrong_authority")
    if compact_text(profile.get("embedding_text")) == "":
        reasons.append("missing_embedding_text")
    if as_bool(profile.get("can_embed"), default=True) is not True:
        reasons.append("can_embed_false")
    if as_bool(profile.get("can_retrieve"), default=True) is not True:
        reasons.append("can_retrieve_false")
    if as_bool(profile.get("can_answer_directly"), default=False):
        reasons.append("can_answer_directly")
    if as_bool(profile.get("can_prove_claims"), default=False):
        reasons.append("can_prove_claims")
    if as_bool(profile.get("can_prove_source_truth"), default=False):
        reasons.append("can_prove_source_truth")
    if as_bool(profile.get("canonical_source_truth"), default=False):
        reasons.append("canonical_source_truth")
    if as_bool(profile.get("can_mutate_source_truth"), default=False):
        reasons.append("can_mutate_source_truth")
    if as_bool(profile.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    if as_bool(profile.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(profile.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    return reasons


def build_page_profile_bundle(
    pages: Sequence[Mapping[str, Any]],
    *,
    embedding_records: Sequence[Mapping[str, Any]] | None = None,
    context_records: Sequence[Mapping[str, Any]] | None = None,
    page_context_v2_rows: Sequence[Mapping[str, Any]] | None = None,
    graph_nodes: Sequence[Mapping[str, Any]] | None = None,
    graph_edges: Sequence[Mapping[str, Any]] | None = None,
    baseline_checkpoint: Mapping[str, Any] | None = None,
    baseline_checkpoint_path: Path | None = None,
    embedding_candidates_path: Path | None = None,
    context_helpers_path: Path | None = None,
    require_pages: Sequence[int] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_embedding_text_chars: int = 6000,
) -> dict[str, Any]:
    records, rejected = build_page_profile_records(
        pages,
        embedding_records=embedding_records,
        context_records=context_records,
        page_context_v2_rows=page_context_v2_rows,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        fallback_doc=fallback_doc,
        max_embedding_text_chars=max_embedding_text_chars,
    )
    summary = summarize_profiles(records, rejected, required_pages=require_pages, fallback_doc=fallback_doc)
    unsafe = [
        {"profile_id": row.get("profile_id"), "page_id": row.get("page_id"), "safety_reasons": unsafe_profile_reasons(row)}
        for row in records
        if unsafe_profile_reasons(row)
    ]
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "read_only": True,
        "record_count": len(records),
        "rejected_record_count": len(rejected),
        "unsafe_profile_count": len(unsafe),
        "records": records,
        "rejected_records": rejected,
        "unsafe_profiles_sample": unsafe[:50],
        "summary": summary,
        "baseline_checkpoint": {
            "path": str(baseline_checkpoint_path) if baseline_checkpoint_path else "",
            "checkpoint_name": first_text((baseline_checkpoint or {}).get("checkpoint_name")),
            "checkpoint_sha256": first_text((baseline_checkpoint or {}).get("checkpoint_sha256")),
            "quality_status": sibling_quality_status(baseline_checkpoint_path, DEFAULT_BASELINE_QUALITY_FILE) if baseline_checkpoint_path else "UNKNOWN",
        },
        "embedding_candidate_artifact": {
            "path": str(embedding_candidates_path) if embedding_candidates_path else "",
            "quality_status": sibling_quality_status(embedding_candidates_path, DEFAULT_EMBEDDING_CANDIDATE_QUALITY_FILE) if embedding_candidates_path else "UNKNOWN",
        },
        "context_helper_artifact": {
            "path": str(context_helpers_path) if context_helpers_path else "",
            "quality_status": sibling_quality_status(context_helpers_path, DEFAULT_CONTEXT_HELPER_QUALITY_FILE) if context_helpers_path else "UNKNOWN",
        },
        "trace_net_boundary_rules": {
            "page_profiles_are_source_truth": False,
            "page_profiles_can_answer_directly": False,
            "page_profiles_can_prove_claims": False,
            "page_profiles_are_route_only": True,
            "qdrant_is_index_not_authority": True,
            "postgres_graph_trust_citation_remain_authority": True,
            "all_answer_use_requires_source_resolution": True,
            "all_answer_use_requires_citation": True,
            "source_truth_mutations_allowed": False,
        },
    }
    return bundle


def write_page_profile_outputs(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    profiles_path = output_dir / DEFAULT_PROFILES_FILE
    jsonl_path = output_dir / DEFAULT_PROFILES_JSONL_FILE
    rejected_path = output_dir / DEFAULT_REJECTED_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    write_json(profiles_path, bundle)
    write_jsonl(jsonl_path, bundle.get("records", []))
    write_jsonl(rejected_path, bundle.get("rejected_records", []))
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": bundle.get("generated_at_utc"),
        "read_only": True,
        "record_count": bundle.get("record_count"),
        "rejected_record_count": bundle.get("rejected_record_count"),
        "unsafe_profile_count": bundle.get("unsafe_profile_count"),
        "summary": bundle.get("summary", {}),
        "trace_net_boundary_rules": bundle.get("trace_net_boundary_rules", {}),
    }
    write_json(summary_path, summary_payload)
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": bundle.get("generated_at_utc"),
        "read_only": True,
        "profiles_path": str(profiles_path),
        "profiles_sha256": sha256_file(profiles_path),
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": sha256_file(jsonl_path),
        "summary_path": str(summary_path),
        "summary_sha256": sha256_file(summary_path),
        "rejected_path": str(rejected_path),
        "rejected_sha256": sha256_file(rejected_path),
        "record_count": bundle.get("record_count"),
        "summary": bundle.get("summary", {}),
        "baseline_checkpoint": bundle.get("baseline_checkpoint", {}),
        "embedding_candidate_artifact": bundle.get("embedding_candidate_artifact", {}),
        "context_helper_artifact": bundle.get("context_helper_artifact", {}),
    }
    write_json(manifest_path, manifest_payload)
    return {
        "profiles_path": profiles_path,
        "jsonl_path": jsonl_path,
        "rejected_path": rejected_path,
        "summary_path": summary_path,
        "manifest_path": manifest_path,
    }


def check_page_profile_quality(
    bundle: Mapping[str, Any],
    *,
    min_profile_records: int = 0,
    min_pages_with_profiles: int = 0,
    min_source_trace_pages: int = 0,
    min_context_v2_pages: int = 0,
    min_profiles_with_retrieval_cues: int = 0,
    require_pages: Sequence[int] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    require_baseline_quality_pass: bool = False,
    require_embedding_candidate_quality_pass: bool = False,
    require_context_helper_quality_pass: bool = False,
) -> QualityResult:
    records = list(bundle.get("records", [])) if isinstance(bundle.get("records"), list) else []
    rejected = list(bundle.get("rejected_records", [])) if isinstance(bundle.get("rejected_records"), list) else []
    summary = summarize_profiles(records, rejected, required_pages=require_pages, fallback_doc=fallback_doc)
    unsafe = [row for row in records if unsafe_profile_reasons(row)]
    summary["unsafe_profile_count"] = len(unsafe)
    summary["baseline_quality_status"] = first_text(bundle.get("baseline_checkpoint", {}).get("quality_status"), "UNKNOWN")
    summary["embedding_candidate_quality_status"] = first_text(bundle.get("embedding_candidate_artifact", {}).get("quality_status"), "UNKNOWN")
    summary["context_helper_quality_status"] = first_text(bundle.get("context_helper_artifact", {}).get("quality_status"), "UNKNOWN")

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    add("min_profile_records", summary["profile_count"] >= min_profile_records, summary["profile_count"], f">= {min_profile_records}")
    add("min_pages_with_profiles", summary["page_count"] >= min_pages_with_profiles, summary["page_count"], f">= {min_pages_with_profiles}")
    add("min_source_trace_pages", summary["source_trace_profile_count"] >= min_source_trace_pages, summary["source_trace_profile_count"], f">= {min_source_trace_pages}")
    add("min_context_v2_pages", summary["context_v2_profile_count"] >= min_context_v2_pages, summary["context_v2_profile_count"], f">= {min_context_v2_pages}")
    add("min_profiles_with_retrieval_cues", summary["profiles_with_retrieval_cues_count"] >= min_profiles_with_retrieval_cues, summary["profiles_with_retrieval_cues_count"], f">= {min_profiles_with_retrieval_cues}")
    add("required_pages_present", summary["required_page_missing_count"] == 0, summary["required_page_missing_count"], 0)
    add("unsafe_profile_count_zero", len(unsafe) == 0, len(unsafe), 0)
    add("missing_page_id_count_zero", summary["missing_page_id_count"] == 0, summary["missing_page_id_count"], 0)
    add("missing_embedding_candidate_id_count_zero", summary["missing_embedding_candidate_id_count"] == 0, summary["missing_embedding_candidate_id_count"], 0)
    add("missing_embedding_text_count_zero", summary["missing_embedding_text_count"] == 0, summary["missing_embedding_text_count"], 0)
    add("answer_capable_profile_count_zero", summary["answer_capable_profile_count"] == 0, summary["answer_capable_profile_count"], 0)
    add("claim_proof_profile_count_zero", summary["claim_proof_profile_count"] == 0, summary["claim_proof_profile_count"], 0)
    add("source_truth_profile_count_zero", summary["source_truth_profile_count"] == 0, summary["source_truth_profile_count"], 0)
    add("source_truth_mutation_profile_count_zero", summary["source_truth_mutation_profile_count"] == 0, summary["source_truth_mutation_profile_count"], 0)
    add("requires_source_resolution_false_count_zero", summary["requires_source_resolution_false_count"] == 0, summary["requires_source_resolution_false_count"], 0)
    add("requires_citation_false_count_zero", summary["requires_citation_false_count"] == 0, summary["requires_citation_false_count"], 0)
    if require_baseline_quality_pass:
        add("baseline_quality_pass", summary["baseline_quality_status"] == "PASS", summary["baseline_quality_status"], "PASS")
    if require_embedding_candidate_quality_pass:
        add("embedding_candidate_quality_pass", summary["embedding_candidate_quality_status"] == "PASS", summary["embedding_candidate_quality_status"], "PASS")
    if require_context_helper_quality_pass:
        add("context_helper_quality_pass", summary["context_helper_quality_status"] == "PASS", summary["context_helper_quality_status"], "PASS")

    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=summary)


def load_page_profile_bundle(path: Path) -> dict[str, Any]:
    payload = load_json_artifact(path)
    if not isinstance(payload.get("records"), list):
        raise PageRetrievalProfileError(f"page profile artifact missing records list: {path}")
    return payload


def write_page_profile_quality(
    quality: QualityResult,
    *,
    output_path: Path,
    profiles_path: Path | None = None,
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": quality.status,
        "profiles_path": str(profiles_path) if profiles_path else "",
        "summary": quality.summary,
        "checks": quality.checks,
    }
    write_json(output_path, payload)


# Embedding and Qdrant loading helpers.

def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def deterministic_hash_embedding(text: str, *, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    if dim <= 0:
        raise ValueError("embedding dimension must be positive")
    tokens = tokenize(text)
    if not tokens:
        tokens = [sha256_text(text or "trace-net-empty")[:16]]
    vector = [0.0] * dim
    for index, token in enumerate(tokens):
        grams = [token]
        if len(token) > 4:
            grams.extend(token[i : i + 4] for i in range(0, max(1, len(token) - 3), 2))
        for gram in grams:
            digest = hashlib.blake2b(f"{index}:{gram}".encode("utf-8"), digest_size=16).digest()
            slot = int.from_bytes(digest[:8], "big") % dim
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            weight = 1.0 / math.sqrt(1.0 + index)
            vector[slot] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        vector[0] = 1.0
        return vector
    return [round(value / norm, 8) for value in vector]


def normalized_embedding_mode(mode: str | None) -> str:
    return as_text(mode or DEFAULT_EMBEDDING_MODE).strip().lower().replace("_", "-")


def is_sentence_transformer_mode(mode: str | None) -> bool:
    normalized = normalized_embedding_mode(mode)
    return normalized in {item.replace("_", "-") for item in SENTENCE_TRANSFORMER_MODES}


def is_ollama_mode(mode: str | None) -> bool:
    normalized = normalized_embedding_mode(mode)
    return normalized in {item.replace("_", "-") for item in OLLAMA_EMBEDDING_MODES}


def embedding_model_name_for_mode(mode: str, embedding_model: str) -> str:
    normalized = normalized_embedding_mode(mode)
    if normalized == "hash":
        return "trace_net_hash_embed_v1"
    if normalized in {"existing", "precomputed", "existing-vector"}:
        return "precomputed"
    if is_ollama_mode(normalized):
        return as_text(embedding_model or DEFAULT_OLLAMA_EMBEDDING_MODEL).strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL
    if is_sentence_transformer_mode(normalized):
        return as_text(embedding_model or DEFAULT_REAL_EMBEDDING_MODEL).strip() or DEFAULT_REAL_EMBEDDING_MODEL
    return as_text(embedding_model)


def ollama_embedding_url(base_url: str = DEFAULT_OLLAMA_URL, endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT) -> str:
    clean_base = as_text(base_url or DEFAULT_OLLAMA_URL).strip() or DEFAULT_OLLAMA_URL
    clean_endpoint = as_text(endpoint or DEFAULT_OLLAMA_EMBED_ENDPOINT).strip() or DEFAULT_OLLAMA_EMBED_ENDPOINT
    if clean_base.endswith("/api/embed") or clean_base.endswith("/api/embeddings"):
        return clean_base
    if not clean_endpoint.startswith("/"):
        clean_endpoint = "/" + clean_endpoint
    return clean_base.rstrip("/") + clean_endpoint


def coerce_ollama_embedding_rows(payload: Mapping[str, Any], *, expected_count: int) -> list[Any]:
    rows = payload.get("embeddings")
    if rows is None and "embedding" in payload:
        rows = [payload.get("embedding")]
    if rows is None:
        result = payload.get("result")
        if isinstance(result, Mapping):
            rows = result.get("embeddings") or ([result.get("embedding")] if "embedding" in result else None)
    if rows is None:
        raise PageRetrievalProfileError("Ollama embedding response did not contain embeddings or embedding")
    if isinstance(rows, Sequence) and rows and all(isinstance(item, (int, float)) for item in rows):
        rows = [rows]
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise PageRetrievalProfileError("Ollama embedding response embeddings field is not a list")
    if len(rows) != expected_count:
        raise PageRetrievalProfileError(f"Ollama returned {len(rows)} embeddings, expected {expected_count}")
    return list(rows)


def ollama_embeddings(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_OLLAMA_EMBEDDING_MODEL,
    expected_dim: int | None = DEFAULT_REAL_EMBEDDING_DIM,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    truncate: bool = True,
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
) -> list[list[float]]:
    clean_texts = [compact_text(text) for text in texts]
    if not clean_texts:
        return []
    clean_model = as_text(model_name or DEFAULT_OLLAMA_EMBEDDING_MODEL).strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL
    clean_endpoint = as_text(endpoint or DEFAULT_OLLAMA_EMBED_ENDPOINT).strip() or DEFAULT_OLLAMA_EMBED_ENDPOINT
    url = ollama_embedding_url(ollama_url, clean_endpoint)
    headers = {"Content-Type": "application/json"}
    if clean_endpoint.rstrip("/").endswith("/api/embeddings") or url.rstrip("/").endswith("/api/embeddings"):
        vectors: list[list[float]] = []
        for text in clean_texts:
            request_payload: dict[str, Any] = {"model": clean_model, "prompt": text}
            request = Request(url, data=json.dumps(json_safe(request_payload)).encode("utf-8"), headers=headers, method="POST")
            try:
                with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local Ollama URL.
                    response_payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise PageRetrievalProfileError(f"Ollama HTTP {exc.code} at {url}: {detail}") from exc
            except URLError as exc:
                raise PageRetrievalProfileError(f"Could not connect to Ollama at {url}: {exc}") from exc
            rows = coerce_ollama_embedding_rows(response_payload, expected_count=1)
            vector = normalize_dense_vector([float(item) for item in rows[0]])
            if expected_dim is not None and len(vector) != expected_dim:
                raise PageRetrievalProfileError(f"Ollama vector has dim {len(vector)}, expected {expected_dim}")
            vectors.append(vector)
        return vectors
    batch_size = max(1, int(batch_size or 1))
    vectors: list[list[float]] = []
    for start in range(0, len(clean_texts), batch_size):
        batch = clean_texts[start : start + batch_size]
        request_payload = {"model": clean_model, "input": batch, "truncate": bool(truncate)}
        request = Request(url, data=json.dumps(json_safe(request_payload)).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local Ollama URL.
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PageRetrievalProfileError(f"Ollama HTTP {exc.code} at {url}: {detail}") from exc
        except URLError as exc:
            raise PageRetrievalProfileError(f"Could not connect to Ollama at {url}: {exc}") from exc
        rows = coerce_ollama_embedding_rows(response_payload, expected_count=len(batch))
        for row in rows:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
                raise PageRetrievalProfileError("Ollama returned a non-vector embedding")
            vector = normalize_dense_vector([float(item) for item in row])
            if expected_dim is not None and len(vector) != expected_dim:
                raise PageRetrievalProfileError(f"Ollama vector has dim {len(vector)}, expected {expected_dim}")
            vectors.append(vector)
    return vectors


def load_sentence_transformer_model(model_name: str, *, device: str | None = None) -> Any:
    clean_model = as_text(model_name or DEFAULT_REAL_EMBEDDING_MODEL).strip() or DEFAULT_REAL_EMBEDDING_MODEL
    clean_device = as_text(device).strip()
    cache_key = (clean_model, clean_device)
    if cache_key in _SENTENCE_TRANSFORMER_MODEL_CACHE:
        return _SENTENCE_TRANSFORMER_MODEL_CACHE[cache_key]
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as exc:
        raise PageRetrievalProfileError(
            "sentence-transformers is required for real embeddings. "
            "Install with: python -m pip install -U sentence-transformers torch"
        ) from exc
    kwargs: dict[str, Any] = {}
    if clean_device:
        kwargs["device"] = clean_device
    model = SentenceTransformer(clean_model, **kwargs)
    _SENTENCE_TRANSFORMER_MODEL_CACHE[cache_key] = model
    return model


def normalize_dense_vector(vector: Sequence[float]) -> list[float]:
    floats = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in floats))
    if norm <= 0:
        return floats
    return [float(value / norm) for value in floats]


def sentence_transformer_embeddings(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_REAL_EMBEDDING_MODEL,
    expected_dim: int | None = DEFAULT_REAL_EMBEDDING_DIM,
    device: str | None = None,
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
) -> list[list[float]]:
    clean_texts = [compact_text(text) for text in texts]
    if not clean_texts:
        return []
    model = load_sentence_transformer_model(model_name, device=device)
    try:
        raw = model.encode(clean_texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    except TypeError:
        raw = model.encode(clean_texts)
    if hasattr(raw, "tolist"):
        rows = raw.tolist()
    else:
        rows = raw
    vectors: list[list[float]] = []
    for row in rows:
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            raise PageRetrievalProfileError("sentence-transformers returned a non-vector embedding")
        vector = normalize_dense_vector([float(item) for item in row])
        if expected_dim is not None and len(vector) != expected_dim:
            raise PageRetrievalProfileError(f"sentence-transformers vector has dim {len(vector)}, expected {expected_dim}")
        vectors.append(vector)
    return vectors


def point_uuid(profile: Mapping[str, Any]) -> str:
    explicit = first_text(profile.get("qdrant_point_id"))
    if explicit:
        try:
            return str(uuid.UUID(explicit))
        except ValueError:
            return str(uuid.uuid5(UUID_NAMESPACE, explicit))
    candidate_id = first_text(profile.get("embedding_candidate_id"), profile.get("profile_id"), profile.get("page_id"))
    if not candidate_id:
        raise PageRetrievalProfileError("profile missing ID for Qdrant point")
    return str(uuid.uuid5(UUID_NAMESPACE, candidate_id))


def build_profile_vector(
    profile: Mapping[str, Any],
    *,
    mode: str = DEFAULT_EMBEDDING_MODE,
    dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_model: str = DEFAULT_REAL_EMBEDDING_MODEL,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
) -> tuple[list[float], str]:
    mode = normalized_embedding_mode(mode)
    if mode == "hash":
        return deterministic_hash_embedding(compact_text(profile.get("embedding_text")), dim=dim), "trace_net_hash_embed_v1"
    if mode in {"existing", "precomputed", "existing-vector"}:
        value = profile.get("embedding") or profile.get("vector")
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise PageRetrievalProfileError("profile does not contain a precomputed embedding/vector")
        vector = [float(item) for item in value]
        if len(vector) != dim:
            raise PageRetrievalProfileError(f"precomputed vector has dim {len(vector)}, expected {dim}")
        return vector, "precomputed"
    if is_sentence_transformer_mode(mode):
        model_name = as_text(embedding_model or DEFAULT_REAL_EMBEDDING_MODEL).strip() or DEFAULT_REAL_EMBEDDING_MODEL
        vector = sentence_transformer_embeddings(
            [compact_text(profile.get("embedding_text"))],
            model_name=model_name,
            expected_dim=dim,
            device=embedding_device,
        )[0]
        return vector, model_name
    if is_ollama_mode(mode):
        model_name = as_text(embedding_model or DEFAULT_OLLAMA_EMBEDDING_MODEL).strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL
        vector = ollama_embeddings(
            [compact_text(profile.get("embedding_text"))],
            model_name=model_name,
            expected_dim=dim,
            ollama_url=ollama_url,
            endpoint=ollama_endpoint,
            timeout=ollama_timeout,
            batch_size=1,
        )[0]
        return vector, model_name
    raise PageRetrievalProfileError(f"unsupported embedding mode: {mode}")


def payload_preview_text(text: str, *, max_chars: int = 500) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def build_page_profile_qdrant_payload(
    profile: Mapping[str, Any],
    *,
    vector: Sequence[float],
    embedding_mode: str,
    embedding_model_name: str,
    embedding_dim: int,
    include_full_text_payload: bool = False,
) -> dict[str, Any]:
    text = compact_text(profile.get("embedding_text"))
    payload = {
        "schema_version": QDRANT_SCHEMA_VERSION,
        "source_schema_version": first_text(profile.get("schema_version")),
        "trace_net_index_role": "page_route_only_rebuildable_vector_index_payload",
        "qdrant_is_source_truth": False,
        "qdrant_can_answer_directly": False,
        "qdrant_can_prove_claims": False,
        "must_resolve_through_postgres": True,
        "must_pass_authority_gate": True,
        "must_use_source_citation": True,
        "profile_id": first_text(profile.get("profile_id")),
        "embedding_candidate_id": first_text(profile.get("embedding_candidate_id")),
        "source_candidate_id": first_text(profile.get("source_candidate_id")),
        "source_kind": PAGE_PROFILE_BUCKET,
        "record_type": PAGE_PROFILE_BUCKET,
        "page_id": first_text(profile.get("page_id")),
        "page_number": profile.get("page_number"),
        "document_id": first_text(profile.get("document_id")),
        "ata_code": first_text(profile.get("ata_code")),
        "rag_bucket": PAGE_PROFILE_BUCKET,
        "embedding_bucket": PAGE_PROFILE_BUCKET,
        "candidate_type": PAGE_PROFILE_BUCKET,
        "evidence_layer": PAGE_PROFILE_BUCKET,
        "authority": PAGE_PROFILE_AUTHORITY,
        "answer_use_policy": first_text(profile.get("answer_use_policy"), "route_to_page_then_resolve_source_evidence"),
        "retrieval_only": True,
        "page_route_only": True,
        "can_embed": True,
        "can_retrieve": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_prove_source_truth": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "can_override_trust": False,
        "can_replace_citation": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "allowed_use": list(profile.get("allowed_use") or SAFE_VECTOR_ALLOWED_USE),
        "forbidden_use": list(profile.get("forbidden_use") or FORBIDDEN_USE),
        "source_url": first_text(profile.get("source_url")),
        "tiff_path": first_text(profile.get("tiff_path")),
        "ocr_path": first_text(profile.get("ocr_path")),
        "citation_id": first_text(profile.get("citation_id")),
        "source_trace_present": as_bool(profile.get("source_trace_present"), default=False),
        "context_v2_present": as_bool(profile.get("context_v2_present"), default=False),
        "context_helper_id": first_text(profile.get("context_helper_id")),
        "known_parts": list_from_any(profile.get("known_parts"))[:80],
        "known_nomenclature": list_from_any(profile.get("known_nomenclature"))[:80],
        "retrieval_cues": list_from_any(profile.get("retrieval_cues"))[:120],
        "query_tunnel_terms": list_from_any(profile.get("query_tunnel_terms"))[:120],
        "safe_candidate_bucket_counts": json_safe(profile.get("safe_candidate_bucket_counts") or {}),
        "content_sha256": first_text(profile.get("content_sha256")) or sha256_text(text),
        "text_chars": len(text),
        "embedding_text_preview": payload_preview_text(text),
        "embedding_mode": embedding_mode,
        "embedding_model_name": embedding_model_name,
        "embedding_model_version": "trace_net_page_profile_loader_v1",
        "embedding_dim": embedding_dim,
        "vector_sha256": sha256_json([round(float(v), 8) for v in vector]),
        "traceability": json_safe(profile.get("traceability") or {}),
        "loaded_at_utc": utc_now_iso(),
    }
    if include_full_text_payload:
        payload["embedding_text"] = text
    return payload


def build_page_profile_qdrant_point(
    profile: Mapping[str, Any],
    *,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_model: str = DEFAULT_REAL_EMBEDDING_MODEL,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    include_full_text_payload: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    reasons = unsafe_profile_reasons(profile)
    if reasons:
        return {}, reasons
    vector, model_name = build_profile_vector(
        profile,
        mode=embedding_mode,
        dim=embedding_dim,
        embedding_model=embedding_model,
        embedding_device=embedding_device,
        ollama_url=ollama_url,
        ollama_endpoint=ollama_endpoint,
        ollama_timeout=ollama_timeout,
    )
    if len(vector) != embedding_dim:
        return {}, [f"vector_dimension_mismatch:{len(vector)}"]
    point = {
        "id": point_uuid(profile),
        "vector": [float(value) for value in vector],
        "payload": build_page_profile_qdrant_payload(
            profile,
            vector=vector,
            embedding_mode=embedding_mode,
            embedding_model_name=model_name,
            embedding_dim=embedding_dim,
            include_full_text_payload=include_full_text_payload,
        ),
    }
    return point, []


def emit_progress(enabled: bool, message: str, *, stream: Any | None = None) -> None:
    """Emit a human-friendly progress line when progress output is enabled."""
    if not enabled:
        return
    target = stream if stream is not None else sys.stderr
    print(message, file=target, flush=True)


def should_emit_progress(done: int, total: int, every: int) -> bool:
    if total <= 0:
        return False
    every = max(1, int(every or 1))
    return done == 0 or done == total or done % every == 0


def build_page_profile_qdrant_points(
    profiles: Sequence[Mapping[str, Any]],
    *,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_model: str = DEFAULT_REAL_EMBEDDING_MODEL,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    include_full_text_payload: bool = False,
    progress: bool = False,
    progress_every: int = 50,
    progress_stream: Any | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    points: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total = len(profiles)
    emit_progress(
        progress,
        f"TRACE-Net page profile embedding progress: 0/{total} profiles vectorized",
        stream=progress_stream,
    )
    for index, profile in enumerate(profiles, start=1):
        point, reasons = build_page_profile_qdrant_point(
            profile,
            embedding_mode=embedding_mode,
            embedding_dim=embedding_dim,
            embedding_model=embedding_model,
            embedding_device=embedding_device,
            ollama_url=ollama_url,
            ollama_endpoint=ollama_endpoint,
            ollama_timeout=ollama_timeout,
            include_full_text_payload=include_full_text_payload,
        )
        if point:
            if point["id"] in seen_ids:
                rejected.append({"profile_id": profile.get("profile_id"), "page_id": profile.get("page_id"), "safety_reasons": ["duplicate_qdrant_point_id"]})
            else:
                seen_ids.add(point["id"])
                points.append(point)
        else:
            rejected.append({"profile_id": profile.get("profile_id"), "page_id": profile.get("page_id"), "safety_reasons": reasons})
        if should_emit_progress(index, total, progress_every):
            emit_progress(
                progress,
                (
                    "TRACE-Net page profile embedding progress: "
                    f"{index}/{total} profiles vectorized; "
                    f"accepted={len(points)} rejected={len(rejected)}"
                ),
                stream=progress_stream,
            )
    return points, rejected


def summarize_qdrant_points(points: Sequence[Mapping[str, Any]], rejected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    payloads = [dict(point.get("payload") or {}) for point in points]
    page_count = len({as_text(payload.get("page_id")) for payload in payloads if as_text(payload.get("page_id"))})
    return {
        "schema_version": QDRANT_SCHEMA_VERSION,
        "point_count": len(points),
        "rejected_count": len(rejected),
        "page_count": page_count,
        "page_profile_point_count": sum(1 for payload in payloads if normalize_bucket(payload.get("rag_bucket")) == PAGE_PROFILE_BUCKET),
        "context_v2_point_count": sum(1 for payload in payloads if as_bool(payload.get("context_v2_present"), default=False)),
        "source_trace_point_count": sum(1 for payload in payloads if as_bool(payload.get("source_trace_present"), default=False)),
        "answer_capable_payload_count": sum(1 for payload in payloads if as_bool(payload.get("can_answer_directly"), default=False)),
        "claim_proof_payload_count": sum(1 for payload in payloads if as_bool(payload.get("can_prove_claims"), default=False)),
        "source_truth_payload_count": sum(1 for payload in payloads if as_bool(payload.get("canonical_source_truth"), default=False)),
        "source_truth_mutation_payload_count": sum(1 for payload in payloads if as_bool(payload.get("can_mutate_source_truth"), default=False)),
        "embedding_answer_authority_allowed_count": sum(1 for payload in payloads if as_bool(payload.get("embedding_answer_authority_allowed"), default=False)),
        "requires_source_resolution_false_count": sum(1 for payload in payloads if as_bool(payload.get("requires_source_resolution"), default=False) is not True),
        "requires_citation_false_count": sum(1 for payload in payloads if as_bool(payload.get("requires_citation"), default=False) is not True),
        "missing_page_id_count": sum(1 for payload in payloads if not as_text(payload.get("page_id"))),
        "missing_profile_id_count": sum(1 for payload in payloads if not as_text(payload.get("profile_id"))),
        "missing_embedding_candidate_id_count": sum(1 for payload in payloads if not as_text(payload.get("embedding_candidate_id"))),
        "qdrant_source_truth_count": sum(1 for payload in payloads if as_bool(payload.get("qdrant_is_source_truth"), default=False)),
    }


def unsafe_qdrant_payload_reasons(payload: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if normalize_bucket(payload.get("rag_bucket")) != PAGE_PROFILE_BUCKET:
        reasons.append("wrong_bucket")
    if as_text(payload.get("authority")) != PAGE_PROFILE_AUTHORITY:
        reasons.append("wrong_authority")
    if not as_text(payload.get("profile_id")):
        reasons.append("missing_profile_id")
    if not as_text(payload.get("embedding_candidate_id")):
        reasons.append("missing_embedding_candidate_id")
    if not as_text(payload.get("page_id")):
        reasons.append("missing_page_id")
    if as_bool(payload.get("can_answer_directly"), default=False):
        reasons.append("can_answer_directly")
    if as_bool(payload.get("can_prove_claims"), default=False):
        reasons.append("can_prove_claims")
    if as_bool(payload.get("canonical_source_truth"), default=False):
        reasons.append("canonical_source_truth")
    if as_bool(payload.get("can_mutate_source_truth"), default=False):
        reasons.append("can_mutate_source_truth")
    if as_bool(payload.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    if as_bool(payload.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(payload.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    if as_bool(payload.get("qdrant_is_source_truth"), default=False):
        reasons.append("qdrant_is_source_truth")
    return reasons


class QdrantRestClient:
    def __init__(self, base_url: str = DEFAULT_QDRANT_URL, *, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(json_safe(payload)).encode("utf-8")
        request = Request(self.base_url + path, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - local dev Qdrant URL.
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PageRetrievalProfileError(f"Qdrant HTTP {exc.code} for {method} {path}: {detail}") from exc
        except URLError as exc:
            raise PageRetrievalProfileError(f"Could not connect to Qdrant at {self.base_url}: {exc}") from exc
        if not body:
            return {}
        return json.loads(body)

    def recreate_collection(self, collection: str, *, vector_size: int, distance: str = DEFAULT_DISTANCE) -> None:
        encoded = quote(collection, safe="")
        try:
            self.request("DELETE", f"/collections/{encoded}")
        except PageRetrievalProfileError:
            pass
        self.request("PUT", f"/collections/{encoded}", {"vectors": {"size": vector_size, "distance": distance}})

    def ensure_collection(self, collection: str, *, vector_size: int, distance: str = DEFAULT_DISTANCE) -> None:
        encoded = quote(collection, safe="")
        try:
            self.request("GET", f"/collections/{encoded}")
            return
        except PageRetrievalProfileError:
            self.request("PUT", f"/collections/{encoded}", {"vectors": {"size": vector_size, "distance": distance}})

    def upsert_points(self, collection: str, points: Sequence[Mapping[str, Any]], *, wait: bool = True) -> None:
        encoded = quote(collection, safe="")
        self.request("PUT", f"/collections/{encoded}/points?wait={'true' if wait else 'false'}", {"points": list(points)})

    def count_points(self, collection: str, *, exact: bool = True) -> int:
        encoded = quote(collection, safe="")
        response = self.request("POST", f"/collections/{encoded}/points/count", {"exact": exact})
        return int((response.get("result") or {}).get("count", 0))


def iter_batches(rows: Sequence[Any], batch_size: int) -> Iterable[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch size must be positive")
    for index in range(0, len(rows), batch_size):
        yield list(rows[index : index + batch_size])


def load_page_profiles_to_qdrant(
    profiles_bundle: Mapping[str, Any],
    *,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    collection: str = DEFAULT_COLLECTION,
    output_dir: Path = DEFAULT_QDRANT_OUTPUT_DIR,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_model: str = DEFAULT_REAL_EMBEDDING_MODEL,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    recreate: bool = False,
    dry_run: bool = False,
    include_full_text_payload: bool = False,
    progress: bool = False,
    progress_every: int = 50,
    progress_stream: Any | None = None,
) -> dict[str, Any]:
    profiles = list(profiles_bundle.get("records", [])) if isinstance(profiles_bundle.get("records"), list) else []
    emit_progress(
        progress,
        (
            "TRACE-Net page profile embedding load: "
            f"profiles={len(profiles)} collection={collection} mode={embedding_mode} dim={embedding_dim}"
        ),
        stream=progress_stream,
    )
    points, rejected = build_page_profile_qdrant_points(
        profiles,
        embedding_mode=embedding_mode,
        embedding_dim=embedding_dim,
        embedding_model=embedding_model,
        embedding_device=embedding_device,
        ollama_url=ollama_url,
        ollama_endpoint=ollama_endpoint,
        ollama_timeout=ollama_timeout,
        include_full_text_payload=include_full_text_payload,
        progress=progress,
        progress_every=progress_every,
        progress_stream=progress_stream,
    )
    summary = summarize_qdrant_points(points, rejected)
    qdrant_count: int | None = None
    if not dry_run:
        client = QdrantRestClient(qdrant_url)
        if recreate:
            emit_progress(progress, f"TRACE-Net Qdrant progress: recreating collection {collection}", stream=progress_stream)
            client.recreate_collection(collection, vector_size=embedding_dim)
        else:
            emit_progress(progress, f"TRACE-Net Qdrant progress: ensuring collection {collection}", stream=progress_stream)
            client.ensure_collection(collection, vector_size=embedding_dim)
        batches = list(iter_batches(points, batch_size))
        total_batches = len(batches)
        uploaded = 0
        emit_progress(
            progress,
            f"TRACE-Net Qdrant upload progress: 0/{len(points)} points uploaded in 0/{total_batches} batches",
            stream=progress_stream,
        )
        for batch_index, batch in enumerate(batches, start=1):
            client.upsert_points(collection, batch, wait=True)
            uploaded += len(batch)
            emit_progress(
                progress,
                (
                    "TRACE-Net Qdrant upload progress: "
                    f"{uploaded}/{len(points)} points uploaded in {batch_index}/{total_batches} batches"
                ),
                stream=progress_stream,
            )
        time.sleep(0.05)
        qdrant_count = client.count_points(collection, exact=True)
        emit_progress(progress, f"TRACE-Net Qdrant progress: collection count={qdrant_count}", stream=progress_stream)
    else:
        emit_progress(progress, "TRACE-Net Qdrant upload progress: dry run enabled; no points sent", stream=progress_stream)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = output_dir / DEFAULT_QDRANT_POINTS_PREVIEW_FILE
    rejected_path = output_dir / DEFAULT_QDRANT_REJECTED_FILE
    summary_path = output_dir / DEFAULT_QDRANT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_QDRANT_MANIFEST_FILE
    write_jsonl(preview_path, points[:25])
    write_jsonl(rejected_path, rejected)
    summary_payload = {
        "schema_version": QDRANT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "collection": collection,
        "qdrant_url": qdrant_url,
        "dry_run": dry_run,
        "progress_enabled": progress,
        "progress_every": progress_every,
        "embedding_mode": embedding_mode,
        "embedding_model": embedding_model_name_for_mode(embedding_mode, embedding_model),
        "embedding_dim": embedding_dim,
        "summary": summary,
        "qdrant_count": qdrant_count,
    }
    write_json(summary_path, summary_payload)
    manifest = {
        "schema_version": QDRANT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "collection": collection,
        "qdrant_url": qdrant_url,
        "dry_run": dry_run,
        "progress_enabled": progress,
        "progress_every": progress_every,
        "embedding_mode": embedding_mode,
        "embedding_model": embedding_model_name_for_mode(embedding_mode, embedding_model),
        "embedding_dim": embedding_dim,
        "loaded_point_count": len(points),
        "qdrant_count": qdrant_count,
        "rejected_count": len(rejected),
        "summary": summary,
        "profiles_record_count": profiles_bundle.get("record_count"),
        "profiles_quality_status": sibling_quality_status(Path(profiles_bundle.get("_profiles_path", "")), DEFAULT_QUALITY_FILE) if profiles_bundle.get("_profiles_path") else "UNKNOWN",
        "points_preview_path": str(preview_path),
        "points_preview_sha256": sha256_file(preview_path),
        "rejected_path": str(rejected_path),
        "rejected_sha256": sha256_file(rejected_path),
        "summary_path": str(summary_path),
        "summary_sha256": sha256_file(summary_path),
    }
    write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def check_qdrant_page_profile_quality(
    manifest: Mapping[str, Any],
    *,
    qdrant_count: int | None = None,
    min_loaded_points: int = 0,
    min_pages_with_points: int = 0,
    min_source_trace_points: int = 0,
    min_context_v2_points: int = 0,
    require_exact_qdrant_count: bool = False,
    require_profile_quality_pass: bool = False,
) -> QualityResult:
    summary = dict(manifest.get("summary") or {})
    if qdrant_count is None:
        qdrant_count = manifest.get("qdrant_count")
    point_count = int(manifest.get("loaded_point_count") or summary.get("point_count") or 0)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    add("min_loaded_points", point_count >= min_loaded_points, point_count, f">= {min_loaded_points}")
    add("min_pages_with_points", int(summary.get("page_count") or 0) >= min_pages_with_points, summary.get("page_count"), f">= {min_pages_with_points}")
    add("min_source_trace_points", int(summary.get("source_trace_point_count") or 0) >= min_source_trace_points, summary.get("source_trace_point_count"), f">= {min_source_trace_points}")
    add("min_context_v2_points", int(summary.get("context_v2_point_count") or 0) >= min_context_v2_points, summary.get("context_v2_point_count"), f">= {min_context_v2_points}")
    add("rejected_count_zero", int(manifest.get("rejected_count") or summary.get("rejected_count") or 0) == 0, manifest.get("rejected_count") or summary.get("rejected_count"), 0)
    add("answer_capable_payload_count_zero", int(summary.get("answer_capable_payload_count") or 0) == 0, summary.get("answer_capable_payload_count"), 0)
    add("claim_proof_payload_count_zero", int(summary.get("claim_proof_payload_count") or 0) == 0, summary.get("claim_proof_payload_count"), 0)
    add("source_truth_payload_count_zero", int(summary.get("source_truth_payload_count") or 0) == 0, summary.get("source_truth_payload_count"), 0)
    add("source_truth_mutation_payload_count_zero", int(summary.get("source_truth_mutation_payload_count") or 0) == 0, summary.get("source_truth_mutation_payload_count"), 0)
    add("requires_source_resolution_false_count_zero", int(summary.get("requires_source_resolution_false_count") or 0) == 0, summary.get("requires_source_resolution_false_count"), 0)
    add("requires_citation_false_count_zero", int(summary.get("requires_citation_false_count") or 0) == 0, summary.get("requires_citation_false_count"), 0)
    add("missing_page_id_count_zero", int(summary.get("missing_page_id_count") or 0) == 0, summary.get("missing_page_id_count"), 0)
    add("missing_profile_id_count_zero", int(summary.get("missing_profile_id_count") or 0) == 0, summary.get("missing_profile_id_count"), 0)
    add("missing_embedding_candidate_id_count_zero", int(summary.get("missing_embedding_candidate_id_count") or 0) == 0, summary.get("missing_embedding_candidate_id_count"), 0)
    add("qdrant_source_truth_count_zero", int(summary.get("qdrant_source_truth_count") or 0) == 0, summary.get("qdrant_source_truth_count"), 0)
    if require_exact_qdrant_count:
        add("qdrant_count_matches_loaded_points", qdrant_count == point_count, qdrant_count, point_count)
    if require_profile_quality_pass:
        add("profile_quality_pass", first_text(manifest.get("profiles_quality_status")) == "PASS", manifest.get("profiles_quality_status"), "PASS")
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    quality_summary = dict(summary)
    quality_summary.update(
        {
            "point_count": point_count,
            "qdrant_count": qdrant_count,
            "profile_quality_status": manifest.get("profiles_quality_status", "UNKNOWN"),
        }
    )
    return QualityResult(status=status, checks=checks, summary=quality_summary)


def write_qdrant_page_profile_quality(quality: QualityResult, *, output_path: Path, manifest_path: Path | None = None) -> None:
    payload = {
        "schema_version": QDRANT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": quality.status,
        "manifest_path": str(manifest_path) if manifest_path else "",
        "summary": quality.summary,
        "checks": quality.checks,
    }
    write_json(output_path, payload)


def build_profiles_from_inputs(
    *,
    database_url: str,
    embedding_candidates_path: Path,
    context_helpers_path: Path,
    baseline_checkpoint_path: Path,
    output_dir: Path,
    require_pages: Sequence[int] | None = None,
    fallback_doc: str = DEFAULT_FALLBACK_DOC,
    max_embedding_text_chars: int = 6000,
) -> tuple[dict[str, Any], dict[str, Path]]:
    db_rows = load_postgres_profile_rows(database_url)
    embedding_records, _embedding_payload = load_records_artifact(embedding_candidates_path)
    context_records, _context_payload = load_records_artifact(context_helpers_path)
    baseline = load_json_artifact(baseline_checkpoint_path)
    bundle = build_page_profile_bundle(
        db_rows["pages"],
        embedding_records=embedding_records,
        context_records=context_records,
        page_context_v2_rows=db_rows.get("page_context_v2_records", []),
        graph_nodes=db_rows.get("graph_nodes", []),
        graph_edges=db_rows.get("graph_edges", []),
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=baseline_checkpoint_path,
        embedding_candidates_path=embedding_candidates_path,
        context_helpers_path=context_helpers_path,
        require_pages=require_pages,
        fallback_doc=fallback_doc,
        max_embedding_text_chars=max_embedding_text_chars,
    )
    paths = write_page_profile_outputs(bundle, output_dir)
    return bundle, paths


def _print_profile_build(summary: Mapping[str, Any], paths: Mapping[str, Path], quality: QualityResult | None = None) -> None:
    print("TRACE-Net page retrieval profiles v1")
    print(" Status: BUILT")
    for key in [
        "profile_count",
        "page_count",
        "source_trace_profile_count",
        "context_v2_profile_count",
        "profiles_with_parts_count",
        "profiles_with_nomenclature_count",
        "profiles_with_retrieval_cues_count",
        "required_page_missing_count",
        "unsafe_profile_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    for key in ["profiles_path", "jsonl_path", "summary_path", "manifest_path"]:
        if key in paths:
            print(f" {key}: {paths[key]}")
    if quality:
        print(f" Quality status: {quality.status}")
        print(f" quality_path: {paths.get('quality_path')}")


def _print_qdrant_load(manifest: Mapping[str, Any], quality: QualityResult | None = None) -> None:
    summary = manifest.get("summary", {})
    print("TRACE-Net page retrieval profiles Qdrant v1")
    print(" Status: LOADED" if not manifest.get("dry_run") else " Status: DRY_RUN")
    print(f" collection: {manifest.get('collection')}")
    print(f" qdrant_url: {manifest.get('qdrant_url')}")
    print(f" embedding_mode: {manifest.get('embedding_mode')}")
    print(f" embedding_dim: {manifest.get('embedding_dim')}")
    print(f" loaded_point_count: {manifest.get('loaded_point_count')}")
    print(f" qdrant_count: {manifest.get('qdrant_count')}")
    print(f" page_count: {summary.get('page_count')}")
    print(f" source_trace_point_count: {summary.get('source_trace_point_count')}")
    print(f" context_v2_point_count: {summary.get('context_v2_point_count')}")
    print(f" rejected_count: {manifest.get('rejected_count')}")
    print(f" manifest_path: {manifest.get('manifest_path')}")
    if quality:
        print(f" Quality status: {quality.status}")
        print(f" quality_path: {manifest.get('quality_path')}")


def main_build(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net page retrieval profiles v1.")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--embedding-candidates", type=Path, default=DEFAULT_EMBEDDING_CANDIDATES)
    parser.add_argument("--context-helpers", type=Path, default=DEFAULT_CONTEXT_HELPERS)
    parser.add_argument("--baseline-checkpoint", type=Path, default=DEFAULT_BASELINE_CHECKPOINT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--fallback-doc", default=DEFAULT_FALLBACK_DOC)
    parser.add_argument("--require-first-pages", default="")
    parser.add_argument("--max-embedding-text-chars", type=int, default=6000)
    parser.add_argument("--min-profile-records", type=int, default=0)
    parser.add_argument("--min-pages-with-profiles", type=int, default=0)
    parser.add_argument("--min-source-trace-pages", type=int, default=0)
    parser.add_argument("--min-context-v2-pages", type=int, default=0)
    parser.add_argument("--min-profiles-with-retrieval-cues", type=int, default=0)
    parser.add_argument("--require-baseline-quality-pass", action="store_true")
    parser.add_argument("--require-embedding-candidate-quality-pass", action="store_true")
    parser.add_argument("--require-context-helper-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        raise PageRetrievalProfileError("--database-url or TRACE_NET_DATABASE_URL is required")
    require_pages = parse_page_range(args.require_first_pages)
    bundle, paths = build_profiles_from_inputs(
        database_url=args.database_url,
        embedding_candidates_path=args.embedding_candidates,
        context_helpers_path=args.context_helpers,
        baseline_checkpoint_path=args.baseline_checkpoint,
        output_dir=args.output_dir,
        require_pages=require_pages,
        fallback_doc=args.fallback_doc,
        max_embedding_text_chars=args.max_embedding_text_chars,
    )
    quality: QualityResult | None = None
    if args.quality:
        quality = check_page_profile_quality(
            bundle,
            min_profile_records=args.min_profile_records,
            min_pages_with_profiles=args.min_pages_with_profiles,
            min_source_trace_pages=args.min_source_trace_pages,
            min_context_v2_pages=args.min_context_v2_pages,
            min_profiles_with_retrieval_cues=args.min_profiles_with_retrieval_cues,
            require_pages=require_pages,
            fallback_doc=args.fallback_doc,
            require_baseline_quality_pass=args.require_baseline_quality_pass,
            require_embedding_candidate_quality_pass=args.require_embedding_candidate_quality_pass,
            require_context_helper_quality_pass=args.require_context_helper_quality_pass,
        )
        quality_path = args.output_dir / DEFAULT_QUALITY_FILE
        write_page_profile_quality(quality, output_path=quality_path, profiles_path=paths["profiles_path"])
        paths["quality_path"] = quality_path
    _print_profile_build(bundle.get("summary", {}), paths, quality)
    if quality and not quality.passed:
        return 2
    return 0


def main_check(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net page retrieval profiles v1 quality.")
    parser.add_argument("--profiles-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_PROFILES_FILE)
    parser.add_argument("--fallback-doc", default=DEFAULT_FALLBACK_DOC)
    parser.add_argument("--require-first-pages", default="")
    parser.add_argument("--min-profile-records", type=int, default=0)
    parser.add_argument("--min-pages-with-profiles", type=int, default=0)
    parser.add_argument("--min-source-trace-pages", type=int, default=0)
    parser.add_argument("--min-context-v2-pages", type=int, default=0)
    parser.add_argument("--min-profiles-with-retrieval-cues", type=int, default=0)
    parser.add_argument("--require-baseline-quality-pass", action="store_true")
    parser.add_argument("--require-embedding-candidate-quality-pass", action="store_true")
    parser.add_argument("--require-context-helper-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    bundle = load_page_profile_bundle(args.profiles_path)
    require_pages = parse_page_range(args.require_first_pages)
    quality = check_page_profile_quality(
        bundle,
        min_profile_records=args.min_profile_records,
        min_pages_with_profiles=args.min_pages_with_profiles,
        min_source_trace_pages=args.min_source_trace_pages,
        min_context_v2_pages=args.min_context_v2_pages,
        min_profiles_with_retrieval_cues=args.min_profiles_with_retrieval_cues,
        require_pages=require_pages,
        fallback_doc=args.fallback_doc,
        require_baseline_quality_pass=args.require_baseline_quality_pass,
        require_embedding_candidate_quality_pass=args.require_embedding_candidate_quality_pass,
        require_context_helper_quality_pass=args.require_context_helper_quality_pass,
    )
    quality_path = args.profiles_path.parent / DEFAULT_QUALITY_FILE
    if args.write_json:
        write_page_profile_quality(quality, output_path=quality_path, profiles_path=args.profiles_path)
    print("TRACE-Net page retrieval profiles v1 quality")
    print(f" Status: {quality.status}")
    for key in [
        "profile_count",
        "page_count",
        "source_trace_profile_count",
        "context_v2_profile_count",
        "profiles_with_retrieval_cues_count",
        "required_page_missing_count",
        "unsafe_profile_count",
        "baseline_quality_status",
        "embedding_candidate_quality_status",
        "context_helper_quality_status",
    ]:
        print(f" {key}: {quality.summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {quality_path}")
    return 0 if quality.passed else 2


def main_load_qdrant(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embed/load TRACE-Net page retrieval profiles into Qdrant v1.")
    parser.add_argument("--profiles-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_PROFILES_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_QDRANT_OUTPUT_DIR)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-mode", default=DEFAULT_EMBEDDING_MODE, choices=["hash", "existing", "precomputed", "existing_vector", "sentence-transformers", "sentence_transformers", "bge-m3", "bge_m3", "real", "ollama", "ollama-embed", "ollama_embed", "ollama-embeddings", "ollama_embeddings"])
    parser.add_argument("--embedding-model", default=os.environ.get("TRACE_NET_EMBEDDING_MODEL", DEFAULT_REAL_EMBEDDING_MODEL))
    parser.add_argument("--embedding-device", default=os.environ.get("TRACE_NET_EMBEDDING_DEVICE", ""), help="Optional torch device, for example cuda, cpu, or cuda:0. Ignored for Ollama mode.")
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", os.environ.get("TRACE_NET_OLLAMA_URL", DEFAULT_OLLAMA_URL)), help="Local Ollama base URL for --embedding-mode ollama.")
    parser.add_argument("--ollama-endpoint", default=os.environ.get("OLLAMA_EMBED_ENDPOINT", os.environ.get("TRACE_NET_OLLAMA_EMBED_ENDPOINT", DEFAULT_OLLAMA_EMBED_ENDPOINT)), help="Ollama embedding endpoint. Default: /api/embed; legacy: /api/embeddings.")
    parser.add_argument("--ollama-timeout", type=float, default=float(os.environ.get("TRACE_NET_OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT)))
    parser.add_argument("--embedding-dim", type=int, default=int(os.environ.get("TRACE_NET_EMBEDDING_DIM", DEFAULT_EMBEDDING_DIM)))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--progress", action="store_true", help="Print progress while vectorizing 509 page profiles and uploading Qdrant batches.")
    parser.add_argument("--progress-every", type=int, default=50, help="Emit vectorization progress every N page profiles when --progress is set.")
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-full-text-payload", action="store_true")
    parser.add_argument("--min-loaded-points", type=int, default=0)
    parser.add_argument("--min-pages-with-points", type=int, default=0)
    parser.add_argument("--min-source-trace-points", type=int, default=0)
    parser.add_argument("--min-context-v2-points", type=int, default=0)
    parser.add_argument("--require-profile-quality-pass", action="store_true")
    parser.add_argument("--require-exact-qdrant-count", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    bundle = load_page_profile_bundle(args.profiles_path)
    bundle["_profiles_path"] = str(args.profiles_path)
    manifest = load_page_profiles_to_qdrant(
        bundle,
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        output_dir=args.output_dir,
        embedding_mode=args.embedding_mode,
        embedding_dim=args.embedding_dim,
        embedding_model=args.embedding_model,
        embedding_device=args.embedding_device or None,
        ollama_url=args.ollama_url,
        ollama_endpoint=args.ollama_endpoint,
        ollama_timeout=args.ollama_timeout,
        batch_size=args.batch_size,
        recreate=args.recreate,
        dry_run=args.dry_run,
        include_full_text_payload=args.include_full_text_payload,
        progress=args.progress,
        progress_every=args.progress_every,
    )
    quality: QualityResult | None = None
    if args.quality:
        quality = check_qdrant_page_profile_quality(
            manifest,
            min_loaded_points=args.min_loaded_points,
            min_pages_with_points=args.min_pages_with_points,
            min_source_trace_points=args.min_source_trace_points,
            min_context_v2_points=args.min_context_v2_points,
            require_exact_qdrant_count=args.require_exact_qdrant_count and not args.dry_run,
            require_profile_quality_pass=args.require_profile_quality_pass,
        )
        quality_path = args.output_dir / DEFAULT_QDRANT_QUALITY_FILE
        write_qdrant_page_profile_quality(quality, output_path=quality_path, manifest_path=Path(manifest.get("manifest_path", "")))
        manifest["quality_path"] = str(quality_path)
    _print_qdrant_load(manifest, quality)
    if quality and not quality.passed:
        return 2
    return 0


def main_check_qdrant(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net page retrieval profiles Qdrant v1 quality.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_QDRANT_OUTPUT_DIR / DEFAULT_QDRANT_MANIFEST_FILE)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--min-loaded-points", type=int, default=0)
    parser.add_argument("--min-pages-with-points", type=int, default=0)
    parser.add_argument("--min-source-trace-points", type=int, default=0)
    parser.add_argument("--min-context-v2-points", type=int, default=0)
    parser.add_argument("--require-profile-quality-pass", action="store_true")
    parser.add_argument("--require-exact-qdrant-count", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_json_artifact(args.manifest_path)
    qdrant_count = None
    if args.require_exact_qdrant_count:
        qdrant_count = QdrantRestClient(args.qdrant_url).count_points(args.collection, exact=True)
    quality = check_qdrant_page_profile_quality(
        manifest,
        qdrant_count=qdrant_count,
        min_loaded_points=args.min_loaded_points,
        min_pages_with_points=args.min_pages_with_points,
        min_source_trace_points=args.min_source_trace_points,
        min_context_v2_points=args.min_context_v2_points,
        require_exact_qdrant_count=args.require_exact_qdrant_count,
        require_profile_quality_pass=args.require_profile_quality_pass,
    )
    quality_path = args.manifest_path.parent / DEFAULT_QDRANT_QUALITY_FILE
    if args.write_json:
        write_qdrant_page_profile_quality(quality, output_path=quality_path, manifest_path=args.manifest_path)
    print("TRACE-Net page retrieval profiles Qdrant v1 quality")
    print(f" Status: {quality.status}")
    for key in [
        "point_count",
        "qdrant_count",
        "page_count",
        "source_trace_point_count",
        "context_v2_point_count",
        "answer_capable_payload_count",
        "claim_proof_payload_count",
        "profile_quality_status",
    ]:
        print(f" {key}: {quality.summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {quality_path}")
    return 0 if quality.passed else 2


if __name__ == "__main__":
    raise SystemExit(main_build())
