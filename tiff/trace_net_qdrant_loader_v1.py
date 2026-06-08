"""TRACE-Net Qdrant Loader v1.

Step 5 loads safe TRACE-Net embedding candidates into Qdrant as a rebuildable
vector index. Qdrant is not source truth, not answer authority, and not a
citation replacement. Every point payload carries enough trace IDs to resolve a
hit back through Postgres/source/citation/trust gates before answer use.

Default embedding mode is a deterministic local hash embedding. It is intended
for loader and smoke-test plumbing before a real local embedding model is wired
in. The loader can also consume precomputed vectors, use SentenceTransformers,
or call a local Ollama embedding model through ``/api/embed``.
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
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

SCHEMA_VERSION = "trace_net_qdrant_loader_v1"
DEFAULT_CANDIDATES_PATH = Path(
    "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/qdrant_loader")
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "trace_net_embedding_candidates_v1"
DEFAULT_EMBEDDING_MODE = "hash"
DEFAULT_EMBEDDING_DIM = 384
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
DEFAULT_MANIFEST_FILE = "trace_net_qdrant_loader_v1_manifest.json"
DEFAULT_SUMMARY_FILE = "trace_net_qdrant_loader_v1_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_qdrant_loader_v1_quality.json"
DEFAULT_REJECTED_FILE = "trace_net_qdrant_loader_v1_rejected.jsonl"
DEFAULT_POINTS_PREVIEW_FILE = "trace_net_qdrant_loader_v1_points_preview.jsonl"
DEFAULT_CANDIDATE_QUALITY_FILE = "trace_net_embedding_candidates_v1_quality.json"

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/#-]*")
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_TRANSFORMER_MODES = {"sentence-transformers", "sentence_transformers", "sbert", "bge-m3", "bge_m3", "real"}
OLLAMA_EMBEDDING_MODES = {"ollama", "ollama-embed", "ollama_embed", "ollama-embeddings", "ollama_embeddings"}
_SENTENCE_TRANSFORMER_MODEL_CACHE: dict[tuple[str, str], Any] = {}
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "trace-net/qdrant-loader/v1")

SAFE_BUCKETS = {
    "source_evidence",
    "source_text_evidence",
    "verified_part_evidence",
    "derived_context",
    "context_retrieval_helper",
}
RETRIEVAL_ONLY_BUCKETS = {"source_evidence", "derived_context", "context_retrieval_helper"}
ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
BANNED_BUCKETS = {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_candidates",
    "table_tile",
    "table_tiles",
    "excluded",
    "unsafe",
    "prompt",
    "debug",
    "feedback_only",
}
FORBIDDEN_USE = [
    "direct_answer_from_vector_hit",
    "claim_proof_from_vector_payload",
    "canonical_source_truth",
    "source_truth_mutation",
    "citation_replacement",
    "trust_tier_override",
    "answer_without_postgres_resolution",
]


class QdrantLoaderError(RuntimeError):
    """Raised when Qdrant loading or quality checks fail."""


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


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(json_safe(row), sort_keys=True, ensure_ascii=False))
            handle.write("\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_text(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def normalize_bucket(value: Any) -> str:
    text = as_text(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "source": "source_evidence",
        "source_trace": "source_evidence",
        "source_text": "source_text_evidence",
        "ocr_text": "source_text_evidence",
        "part_evidence": "verified_part_evidence",
        "verified_part": "verified_part_evidence",
        "context_v2": "context_retrieval_helper",
        "page_context_v2": "context_retrieval_helper",
        "context_helper": "context_retrieval_helper",
    }
    return aliases.get(text, text)


def point_uuid(candidate_id: Any) -> str:
    text = as_text(candidate_id).strip()
    if not text:
        raise QdrantLoaderError("missing embedding candidate ID for point UUID")
    raw = text
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return str(uuid.uuid5(UUID_NAMESPACE, raw))


def clean_text_for_embedding(text: Any, *, max_chars: int = 6000) -> str:
    raw = as_text(text).replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    compact = WHITESPACE_RE.sub(" ", raw).strip()
    if len(compact) > max_chars:
        compact = compact[: max_chars - 3].rstrip() + "..."
    return compact


def tokenize(text: str) -> list[str]:
    tokens = [match.group(0).lower() for match in TOKEN_RE.finditer(text)]
    return [token for token in tokens if token]


def deterministic_hash_embedding(text: str, *, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    """Create a deterministic local vector for plumbing/smoke tests.

    This is not a semantic production embedding. It is stable, dependency-free,
    and useful for validating Qdrant collection loading and retrieval wiring.
    """

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


def coerce_precomputed_vector(value: Any, *, expected_dim: int | None = None) -> list[float]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise QdrantLoaderError("precomputed vector string is not valid JSON") from exc
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    vector: list[float] = []
    for item in value:
        try:
            vector.append(float(item))
        except (TypeError, ValueError) as exc:
            raise QdrantLoaderError("precomputed vector contains a non-numeric value") from exc
    if expected_dim is not None and vector and len(vector) != expected_dim:
        raise QdrantLoaderError(f"precomputed vector has dim {len(vector)}, expected {expected_dim}")
    return vector


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
        raise QdrantLoaderError("Ollama embedding response did not contain embeddings or embedding")
    if isinstance(rows, Sequence) and rows and all(isinstance(item, (int, float)) for item in rows):
        rows = [rows]
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise QdrantLoaderError("Ollama embedding response embeddings field is not a list")
    if len(rows) != expected_count:
        raise QdrantLoaderError(f"Ollama returned {len(rows)} embeddings, expected {expected_count}")
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
    clean_texts = [clean_text_for_embedding(text) for text in texts]
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
                raise QdrantLoaderError(f"Ollama HTTP {exc.code} at {url}: {detail}") from exc
            except URLError as exc:
                raise QdrantLoaderError(f"Could not connect to Ollama at {url}: {exc}") from exc
            rows = coerce_ollama_embedding_rows(response_payload, expected_count=1)
            vector = normalize_dense_vector([float(item) for item in rows[0]])
            if expected_dim is not None and len(vector) != expected_dim:
                raise QdrantLoaderError(f"Ollama vector has dim {len(vector)}, expected {expected_dim}")
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
            raise QdrantLoaderError(f"Ollama HTTP {exc.code} at {url}: {detail}") from exc
        except URLError as exc:
            raise QdrantLoaderError(f"Could not connect to Ollama at {url}: {exc}") from exc
        rows = coerce_ollama_embedding_rows(response_payload, expected_count=len(batch))
        for row in rows:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
                raise QdrantLoaderError("Ollama returned a non-vector embedding")
            vector = normalize_dense_vector([float(item) for item in row])
            if expected_dim is not None and len(vector) != expected_dim:
                raise QdrantLoaderError(f"Ollama vector has dim {len(vector)}, expected {expected_dim}")
            vectors.append(vector)
    return vectors


def load_sentence_transformer_model(model_name: str, *, device: str | None = None) -> Any:
    """Load a SentenceTransformers model lazily.

    This import is intentionally lazy so TRACE-Net unit tests and hash-mode
    smoke tests do not require torch/model dependencies. For production use we
    recommend BAAI/bge-m3 with a 1024-dimensional Qdrant collection.
    """

    clean_model = as_text(model_name or DEFAULT_REAL_EMBEDDING_MODEL).strip() or DEFAULT_REAL_EMBEDDING_MODEL
    clean_device = as_text(device).strip()
    cache_key = (clean_model, clean_device)
    if cache_key in _SENTENCE_TRANSFORMER_MODEL_CACHE:
        return _SENTENCE_TRANSFORMER_MODEL_CACHE[cache_key]
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as exc:
        raise QdrantLoaderError(
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
    """Embed text with SentenceTransformers and validate the output shape."""

    clean_texts = [clean_text_for_embedding(text) for text in texts]
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
            raise QdrantLoaderError("sentence-transformers returned a non-vector embedding")
        vector = normalize_dense_vector([float(item) for item in row])
        if expected_dim is not None and len(vector) != expected_dim:
            raise QdrantLoaderError(f"sentence-transformers vector has dim {len(vector)}, expected {expected_dim}")
        vectors.append(vector)
    return vectors


def candidate_text(candidate: Mapping[str, Any]) -> str:
    for key in ("embedding_text", "text", "candidate_text", "content", "summary"):
        value = clean_text_for_embedding(candidate.get(key))
        if value:
            return value
    return ""


def candidate_bucket(candidate: Mapping[str, Any]) -> str:
    return normalize_bucket(candidate.get("rag_bucket") or candidate.get("embedding_bucket") or candidate.get("candidate_type"))


def candidate_is_safe_for_qdrant(candidate: Mapping[str, Any]) -> tuple[bool, list[str]]:
    bucket = candidate_bucket(candidate)
    reasons: list[str] = []
    if as_text(candidate.get("embedding_candidate_id")).strip() == "":
        reasons.append("missing_embedding_candidate_id")
    if as_text(candidate.get("page_id")).strip() == "":
        reasons.append("missing_page_id")
    if bucket not in SAFE_BUCKETS:
        reasons.append("bucket_not_safe_for_qdrant")
    if bucket in BANNED_BUCKETS:
        reasons.append("banned_bucket")
    if clean_text_for_embedding(candidate_text(candidate)) == "":
        reasons.append("missing_embedding_text")
    if as_bool(candidate.get("can_embed"), default=True) is not True:
        reasons.append("can_embed_false")
    if as_bool(candidate.get("can_retrieve"), default=True) is not True:
        reasons.append("can_retrieve_false")
    if as_bool(candidate.get("can_answer_directly"), default=False):
        reasons.append("candidate_can_answer_directly")
    if as_bool(candidate.get("can_prove_claims"), default=False):
        reasons.append("candidate_can_prove_claims")
    if as_bool(candidate.get("embedding_answer_authority_allowed"), default=False):
        reasons.append("embedding_answer_authority_allowed")
    if as_bool(candidate.get("canonical_source_truth"), default=False):
        reasons.append("candidate_marked_canonical_source_truth")
    if as_bool(candidate.get("can_mutate_source_truth"), default=False):
        reasons.append("candidate_can_mutate_source_truth")
    if as_bool(candidate.get("requires_source_resolution"), default=True) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(candidate.get("requires_citation"), default=True) is not True:
        reasons.append("requires_citation_false")
    if bucket in RETRIEVAL_ONLY_BUCKETS and as_bool(candidate.get("can_prove_source_truth"), default=False):
        reasons.append("retrieval_only_bucket_can_prove_source_truth")
    if as_text(candidate.get("trust_tier")).strip().upper() == "D":
        reasons.append("D_tier_not_loaded")
    if as_text(candidate.get("safety_status")).strip().lower() == "rejected":
        reasons.append("candidate_safety_status_rejected")
    return len(reasons) == 0, reasons


def build_embedding_vector(
    candidate: Mapping[str, Any],
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
        text = candidate_text(candidate)
        return deterministic_hash_embedding(text, dim=dim), "trace_net_hash_embed_v1"
    if mode in {"existing", "precomputed", "existing-vector"}:
        vector = coerce_precomputed_vector(candidate.get("embedding") or candidate.get("vector"), expected_dim=dim)
        if not vector:
            raise QdrantLoaderError("candidate does not contain a precomputed embedding/vector")
        return vector, "precomputed"
    if is_sentence_transformer_mode(mode):
        text = candidate_text(candidate)
        model_name = as_text(embedding_model or DEFAULT_REAL_EMBEDDING_MODEL).strip() or DEFAULT_REAL_EMBEDDING_MODEL
        vector = sentence_transformer_embeddings(
            [text],
            model_name=model_name,
            expected_dim=dim,
            device=embedding_device,
        )[0]
        return vector, model_name
    if is_ollama_mode(mode):
        text = candidate_text(candidate)
        model_name = as_text(embedding_model or DEFAULT_OLLAMA_EMBEDDING_MODEL).strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL
        vector = ollama_embeddings(
            [text],
            model_name=model_name,
            expected_dim=dim,
            ollama_url=ollama_url,
            endpoint=ollama_endpoint,
            timeout=ollama_timeout,
            batch_size=1,
        )[0]
        return vector, model_name
    raise QdrantLoaderError(f"unsupported embedding mode: {mode}")


def payload_preview_text(text: str, *, max_chars: int = 500) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def build_qdrant_payload(
    candidate: Mapping[str, Any],
    *,
    vector: Sequence[float],
    embedding_mode: str,
    embedding_model_name: str,
    embedding_dim: int,
    include_full_text_payload: bool = False,
) -> dict[str, Any]:
    text = candidate_text(candidate)
    bucket = candidate_bucket(candidate)
    embedding_candidate_id = as_text(candidate.get("embedding_candidate_id")).strip()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_schema_version": as_text(candidate.get("schema_version")),
        "trace_net_index_role": "rebuildable_vector_index_payload",
        "qdrant_is_source_truth": False,
        "qdrant_can_answer_directly": False,
        "qdrant_can_prove_claims": False,
        "must_resolve_through_postgres": True,
        "must_pass_authority_gate": True,
        "must_use_source_citation": True,
        "embedding_candidate_id": embedding_candidate_id,
        "source_candidate_id": as_text(candidate.get("source_candidate_id")),
        "source_kind": as_text(candidate.get("source_kind")),
        "source_table": as_text(candidate.get("source_table")),
        "page_id": as_text(candidate.get("page_id")),
        "page_number": candidate.get("page_number"),
        "document_id": as_text(candidate.get("document_id")),
        "ata_code": as_text(candidate.get("ata_code")),
        "rag_bucket": bucket,
        "embedding_bucket": normalize_bucket(candidate.get("embedding_bucket") or bucket),
        "candidate_type": normalize_bucket(candidate.get("candidate_type") or bucket),
        "evidence_layer": normalize_bucket(candidate.get("evidence_layer") or bucket),
        "authority": as_text(candidate.get("authority")),
        "answer_use_policy": as_text(candidate.get("answer_use_policy")),
        "trust_tier": as_text(candidate.get("trust_tier")),
        "final_trust_tier": as_text(candidate.get("final_trust_tier")),
        "final_rag_action": as_text(candidate.get("final_rag_action")),
        "retrieval_only": as_bool(candidate.get("retrieval_only"), default=bucket in RETRIEVAL_ONLY_BUCKETS),
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
        "allowed_use": list(candidate.get("allowed_use") or ["retrieve", "rank", "route", "candidate_discovery"]),
        "forbidden_use": list(candidate.get("forbidden_use") or FORBIDDEN_USE),
        "citation_id": as_text(candidate.get("citation_id")),
        "source_url": as_text(candidate.get("source_url")),
        "tiff_path": as_text(candidate.get("tiff_path")),
        "ocr_path": as_text(candidate.get("ocr_path")),
        "content_sha256": as_text(candidate.get("content_sha256")) or sha256_text(text),
        "text_chars": len(text),
        "embedding_text_preview": payload_preview_text(text),
        "embedding_mode": embedding_mode,
        "embedding_model_name": embedding_model_name,
        "embedding_model_version": "trace_net_loader_v1",
        "embedding_dim": embedding_dim,
        "vector_sha256": sha256_json([round(float(v), 8) for v in vector]),
        "traceability": json_safe(candidate.get("traceability") or {}),
        "loaded_at_utc": utc_now_iso(),
    }
    if bucket == "context_retrieval_helper":
        payload["query_tunnel_terms"] = list(candidate.get("query_tunnel_terms") or [])[:80]
        payload["retrieval_cues"] = list(candidate.get("retrieval_cues") or [])[:80]
    if include_full_text_payload:
        payload["embedding_text"] = text
    return payload


def build_qdrant_point(
    candidate: Mapping[str, Any],
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
    is_safe, reasons = candidate_is_safe_for_qdrant(candidate)
    if not is_safe:
        return {}, reasons
    vector, model_name = build_embedding_vector(
        candidate,
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
    embedding_candidate_id = as_text(candidate.get("embedding_candidate_id")).strip()
    point = {
        "id": as_text(candidate.get("qdrant_point_id")) or point_uuid(embedding_candidate_id),
        "vector": [float(value) for value in vector],
        "payload": build_qdrant_payload(
            candidate,
            vector=vector,
            embedding_mode=embedding_mode,
            embedding_model_name=model_name,
            embedding_dim=embedding_dim,
            include_full_text_payload=include_full_text_payload,
        ),
    }
    return point, []


def iter_batches(rows: Sequence[Any], batch_size: int) -> Iterable[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch size must be positive")
    for index in range(0, len(rows), batch_size):
        yield list(rows[index : index + batch_size])


def build_qdrant_points(
    candidates: Sequence[Mapping[str, Any]],
    *,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_model: str = DEFAULT_REAL_EMBEDDING_MODEL,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    include_full_text_payload: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    points: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        point, reasons = build_qdrant_point(
            candidate,
            embedding_mode=embedding_mode,
            embedding_dim=embedding_dim,
            embedding_model=embedding_model,
            embedding_device=embedding_device,
            ollama_url=ollama_url,
            ollama_endpoint=ollama_endpoint,
            ollama_timeout=ollama_timeout,
            include_full_text_payload=include_full_text_payload,
        )
        embedding_candidate_id = as_text(candidate.get("embedding_candidate_id")).strip()
        if point:
            if point["id"] in seen_ids:
                rejected.append(
                    {
                        "embedding_candidate_id": embedding_candidate_id,
                        "page_id": as_text(candidate.get("page_id")),
                        "rag_bucket": candidate_bucket(candidate),
                        "safety_reasons": ["duplicate_qdrant_point_id"],
                    }
                )
                continue
            seen_ids.add(point["id"])
            points.append(point)
        else:
            rejected.append(
                {
                    "embedding_candidate_id": embedding_candidate_id,
                    "page_id": as_text(candidate.get("page_id")),
                    "rag_bucket": candidate_bucket(candidate),
                    "safety_reasons": reasons,
                }
            )
    return points, rejected


def summarize_points(points: Sequence[Mapping[str, Any]], rejected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    payloads = [dict(point.get("payload") or {}) for point in points]
    bucket_counts = Counter(as_text(payload.get("rag_bucket")) for payload in payloads)
    authority_counts = Counter(as_text(payload.get("authority")) for payload in payloads)
    page_count = len({as_text(payload.get("page_id")) for payload in payloads if as_text(payload.get("page_id"))})
    return {
        "schema_version": SCHEMA_VERSION,
        "point_count": len(points),
        "rejected_count": len(rejected),
        "page_count": page_count,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "context_helper_point_count": bucket_counts.get("context_retrieval_helper", 0),
        "rag_candidate_point_count": len(points) - bucket_counts.get("context_retrieval_helper", 0),
        "retrieval_only_point_count": sum(1 for payload in payloads if as_bool(payload.get("retrieval_only"), default=False)),
        "answer_capable_payload_count": sum(1 for payload in payloads if as_bool(payload.get("can_answer_directly"), default=False)),
        "claim_proof_payload_count": sum(1 for payload in payloads if as_bool(payload.get("can_prove_claims"), default=False)),
        "source_truth_payload_count": sum(1 for payload in payloads if as_bool(payload.get("canonical_source_truth"), default=False)),
        "source_truth_mutation_payload_count": sum(1 for payload in payloads if as_bool(payload.get("can_mutate_source_truth"), default=False)),
        "missing_page_id_count": sum(1 for payload in payloads if not as_text(payload.get("page_id"))),
        "missing_embedding_candidate_id_count": sum(1 for payload in payloads if not as_text(payload.get("embedding_candidate_id"))),
        "missing_source_candidate_id_count": sum(1 for payload in payloads if not as_text(payload.get("source_candidate_id"))),
        "missing_traceability_count": sum(1 for payload in payloads if not payload.get("traceability")),
        "requires_source_resolution_false_count": sum(
            1 for payload in payloads if as_bool(payload.get("requires_source_resolution"), default=False) is not True
        ),
        "requires_citation_false_count": sum(1 for payload in payloads if as_bool(payload.get("requires_citation"), default=False) is not True),
        "embedding_answer_authority_allowed_count": sum(
            1 for payload in payloads if as_bool(payload.get("embedding_answer_authority_allowed"), default=False)
        ),
        "qdrant_source_truth_count": sum(1 for payload in payloads if as_bool(payload.get("qdrant_is_source_truth"), default=False)),
    }


def unsafe_payload_reasons(payload: Mapping[str, Any]) -> list[str]:
    bucket = normalize_bucket(payload.get("rag_bucket"))
    reasons: list[str] = []
    if not as_text(payload.get("embedding_candidate_id")):
        reasons.append("missing_embedding_candidate_id")
    if not as_text(payload.get("source_candidate_id")):
        reasons.append("missing_source_candidate_id")
    if not as_text(payload.get("page_id")):
        reasons.append("missing_page_id")
    if bucket not in SAFE_BUCKETS:
        reasons.append("unsafe_bucket")
    if bucket in BANNED_BUCKETS:
        reasons.append("banned_bucket")
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
    if as_bool(payload.get("qdrant_is_source_truth"), default=False):
        reasons.append("qdrant_is_source_truth")
    if as_bool(payload.get("must_resolve_through_postgres"), default=False) is not True:
        reasons.append("must_resolve_through_postgres_false")
    if as_bool(payload.get("requires_source_resolution"), default=False) is not True:
        reasons.append("requires_source_resolution_false")
    if as_bool(payload.get("requires_citation"), default=False) is not True:
        reasons.append("requires_citation_false")
    if as_bool(payload.get("must_pass_authority_gate"), default=False) is not True:
        reasons.append("must_pass_authority_gate_false")
    if as_bool(payload.get("must_use_source_citation"), default=False) is not True:
        reasons.append("must_use_source_citation_false")
    if bucket in RETRIEVAL_ONLY_BUCKETS and as_bool(payload.get("can_prove_source_truth"), default=False):
        reasons.append("retrieval_only_can_prove_source_truth")
    return reasons


def check_qdrant_loader_quality(
    *,
    points: Sequence[Mapping[str, Any]] | None = None,
    manifest: Mapping[str, Any] | None = None,
    candidate_quality: Mapping[str, Any] | None = None,
    qdrant_count: int | None = None,
    required_pages: Sequence[int] | None = None,
    min_loaded_points: int = 1,
    min_rag_points: int = 0,
    min_context_helper_points: int = 0,
    min_pages_with_points: int = 0,
    require_candidate_quality_pass: bool = False,
    require_exact_qdrant_count: bool = False,
) -> QualityResult:
    points = list(points or [])
    manifest = dict(manifest or {})
    payloads = [dict(point.get("payload") or {}) for point in points]
    if not payloads and manifest.get("summary"):
        # Quality can run from manifest only after loading. Manifest summary does
        # not contain every payload, so payload-specific checks are limited.
        summary_from_manifest = dict(manifest.get("summary") or {})
    else:
        summary_from_manifest = {}

    summary = summarize_points(points, []) if payloads else {
        "schema_version": SCHEMA_VERSION,
        "point_count": int(manifest.get("loaded_point_count") or summary_from_manifest.get("point_count") or 0),
        "rejected_count": int(manifest.get("rejected_count") or summary_from_manifest.get("rejected_count") or 0),
        "page_count": int(summary_from_manifest.get("page_count") or 0),
        "bucket_counts": dict(summary_from_manifest.get("bucket_counts") or {}),
        "context_helper_point_count": int(summary_from_manifest.get("context_helper_point_count") or 0),
        "rag_candidate_point_count": int(summary_from_manifest.get("rag_candidate_point_count") or 0),
        "missing_page_id_count": int(summary_from_manifest.get("missing_page_id_count") or 0),
        "missing_embedding_candidate_id_count": int(summary_from_manifest.get("missing_embedding_candidate_id_count") or 0),
        "missing_source_candidate_id_count": int(summary_from_manifest.get("missing_source_candidate_id_count") or 0),
        "missing_traceability_count": int(summary_from_manifest.get("missing_traceability_count") or 0),
        "requires_source_resolution_false_count": int(summary_from_manifest.get("requires_source_resolution_false_count") or 0),
        "requires_citation_false_count": int(summary_from_manifest.get("requires_citation_false_count") or 0),
        "embedding_answer_authority_allowed_count": int(summary_from_manifest.get("embedding_answer_authority_allowed_count") or 0),
        "qdrant_source_truth_count": int(summary_from_manifest.get("qdrant_source_truth_count") or 0),
        "answer_capable_payload_count": int(summary_from_manifest.get("answer_capable_payload_count") or 0),
        "claim_proof_payload_count": int(summary_from_manifest.get("claim_proof_payload_count") or 0),
        "source_truth_payload_count": int(summary_from_manifest.get("source_truth_payload_count") or 0),
        "source_truth_mutation_payload_count": int(summary_from_manifest.get("source_truth_mutation_payload_count") or 0),
    }

    bucket_counts = Counter(summary.get("bucket_counts") or {})
    page_ids = {as_text(payload.get("page_id")) for payload in payloads if as_text(payload.get("page_id"))}
    required_page_ids = {f"t_p_120_1176_p{page:06d}" for page in (required_pages or [])}
    missing_required_pages = sorted(required_page_ids - page_ids) if payloads else []
    unsafe_payload_count = 0
    if payloads:
        unsafe_payload_count = sum(1 for payload in payloads if unsafe_payload_reasons(payload))
    else:
        unsafe_payload_count = sum(
            int(summary.get(key) or 0)
            for key in (
                "answer_capable_payload_count",
                "claim_proof_payload_count",
                "source_truth_payload_count",
                "source_truth_mutation_payload_count",
                "embedding_answer_authority_allowed_count",
                "qdrant_source_truth_count",
                "requires_source_resolution_false_count",
                "requires_citation_false_count",
                "missing_page_id_count",
                "missing_embedding_candidate_id_count",
                "missing_source_candidate_id_count",
            )
        )

    summary.update(
        {
            "required_page_missing_count": len(missing_required_pages),
            "required_page_missing_ids": missing_required_pages[:100],
            "unsafe_qdrant_payload_count": unsafe_payload_count,
            "qdrant_count": qdrant_count,
            "candidate_quality_status": (candidate_quality or {}).get("status"),
        }
    )

    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, expected: Any, actual: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual})

    add_check("min_loaded_points", int(summary.get("point_count") or 0) >= min_loaded_points, f">= {min_loaded_points}", summary.get("point_count"))
    add_check("min_rag_points", int(summary.get("rag_candidate_point_count") or 0) >= min_rag_points, f">= {min_rag_points}", summary.get("rag_candidate_point_count"))
    add_check(
        "min_context_helper_points",
        int(summary.get("context_helper_point_count") or 0) >= min_context_helper_points,
        f">= {min_context_helper_points}",
        summary.get("context_helper_point_count"),
    )
    add_check("min_pages_with_points", int(summary.get("page_count") or 0) >= min_pages_with_points, f">= {min_pages_with_points}", summary.get("page_count"))
    add_check("unsafe_qdrant_payload_count", unsafe_payload_count == 0, 0, unsafe_payload_count)
    add_check("required_page_missing_count", len(missing_required_pages) == 0, 0, len(missing_required_pages))
    add_check("rejected_count", int(summary.get("rejected_count") or 0) == 0, 0, summary.get("rejected_count"))
    add_check("missing_traceability_count", int(summary.get("missing_traceability_count") or 0) == 0, 0, summary.get("missing_traceability_count"))
    if qdrant_count is not None:
        if require_exact_qdrant_count:
            add_check("qdrant_count_exact", int(qdrant_count) == int(summary.get("point_count") or 0), summary.get("point_count"), qdrant_count)
        else:
            add_check("qdrant_count_min", int(qdrant_count) >= int(summary.get("point_count") or 0), f">= {summary.get('point_count')}", qdrant_count)
    if require_candidate_quality_pass:
        add_check("candidate_quality_status", (candidate_quality or {}).get("status") == "PASS", "PASS", (candidate_quality or {}).get("status"))
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=summary)


class QdrantRestClient:
    """Small stdlib REST client for Qdrant.

    Avoids a qdrant-client dependency so the patch works in the existing local
    Python environment. It supports only the endpoints needed by this loader.
    """

    def __init__(self, base_url: str = DEFAULT_QDRANT_URL, *, api_key: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key or ""
        self.timeout = timeout

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None, *, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        path = path.lstrip("/")
        url = urljoin(self.base_url, path)
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
        body = None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        if payload is not None:
            body = json.dumps(json_safe(payload), ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except HTTPError as exc:
            data = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                raise KeyError(path) from exc
            raise QdrantLoaderError(f"Qdrant HTTP {exc.code} for {method} {path}: {data}") from exc
        except URLError as exc:
            raise QdrantLoaderError(f"could not reach Qdrant at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise QdrantLoaderError(f"Qdrant returned non-JSON response for {method} {path}") from exc

    def health(self) -> bool:
        try:
            self.request("GET", "/collections")
            return True
        except Exception:
            return False

    def get_collection(self, collection: str) -> dict[str, Any] | None:
        try:
            return self.request("GET", f"/collections/{quote(collection, safe='')}")
        except KeyError:
            return None

    def delete_collection(self, collection: str) -> dict[str, Any]:
        try:
            return self.request("DELETE", f"/collections/{quote(collection, safe='')}")
        except KeyError:
            return {"status": "not_found"}

    def create_collection(self, collection: str, *, vector_size: int, distance: str = DEFAULT_DISTANCE) -> dict[str, Any]:
        payload = {"vectors": {"size": vector_size, "distance": distance}}
        return self.request("PUT", f"/collections/{quote(collection, safe='')}", payload)

    def upsert_points(self, collection: str, points: Sequence[Mapping[str, Any]], *, wait: bool = True) -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/collections/{quote(collection, safe='')}/points",
            {"points": list(points)},
            query={"wait": "true" if wait else "false"},
        )

    def count_points(self, collection: str, *, exact: bool = True) -> int:
        response = self.request("POST", f"/collections/{quote(collection, safe='')}/points/count", {"exact": exact})
        result = response.get("result") or {}
        return int(result.get("count") or 0)


def extract_collection_vector_size(collection_info: Mapping[str, Any]) -> int | None:
    result = collection_info.get("result") or collection_info
    params = ((result.get("config") or {}).get("params") or {}) if isinstance(result, Mapping) else {}
    vectors = params.get("vectors")
    if isinstance(vectors, Mapping):
        if "size" in vectors:
            try:
                return int(vectors.get("size"))
            except (TypeError, ValueError):
                return None
        # Named vectors: choose the first vector definition with a size.
        for value in vectors.values():
            if isinstance(value, Mapping) and "size" in value:
                try:
                    return int(value.get("size"))
                except (TypeError, ValueError):
                    return None
    return None


def ensure_collection(
    client: QdrantRestClient,
    collection: str,
    *,
    vector_size: int,
    distance: str = DEFAULT_DISTANCE,
    recreate: bool = False,
) -> dict[str, Any]:
    existing = client.get_collection(collection)
    if existing and recreate:
        client.delete_collection(collection)
        existing = None
    if not existing:
        client.create_collection(collection, vector_size=vector_size, distance=distance)
        existing = client.get_collection(collection)
    if not existing:
        raise QdrantLoaderError(f"collection {collection!r} could not be created")
    existing_size = extract_collection_vector_size(existing)
    if existing_size is not None and existing_size != vector_size:
        raise QdrantLoaderError(
            f"collection {collection!r} vector size is {existing_size}, expected {vector_size}. "
            "Use --recreate to rebuild it."
        )
    return existing


def load_points_to_qdrant(
    client: QdrantRestClient,
    *,
    collection: str,
    points: Sequence[Mapping[str, Any]],
    vector_size: int,
    distance: str = DEFAULT_DISTANCE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    recreate: bool = False,
    wait: bool = True,
) -> dict[str, Any]:
    ensure_collection(client, collection, vector_size=vector_size, distance=distance, recreate=recreate)
    batch_results: list[dict[str, Any]] = []
    started = time.time()
    for batch_index, batch in enumerate(iter_batches(list(points), batch_size), start=1):
        response = client.upsert_points(collection, batch, wait=wait)
        batch_results.append(
            {
                "batch_index": batch_index,
                "point_count": len(batch),
                "status": response.get("status"),
                "result": response.get("result"),
            }
        )
    qdrant_count = client.count_points(collection, exact=True)
    return {
        "collection": collection,
        "batch_count": len(batch_results),
        "loaded_point_count": len(points),
        "qdrant_count": qdrant_count,
        "duration_seconds": round(time.time() - started, 3),
        "batch_results": batch_results,
    }


def load_candidates_payload(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = read_json(path)
    records = payload.get("records") if isinstance(payload, Mapping) else None
    if not isinstance(records, list):
        raise QdrantLoaderError(f"candidate artifact does not contain records list: {path}")
    return [dict(record) for record in records], dict(payload)


def read_candidate_quality(candidates_path: Path) -> dict[str, Any]:
    quality_path = candidates_path.parent / DEFAULT_CANDIDATE_QUALITY_FILE
    if quality_path.exists():
        try:
            return dict(read_json(quality_path))
        except Exception:
            return {}
    return {}


def build_and_load_qdrant_index(
    *,
    candidates_path: Path = DEFAULT_CANDIDATES_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    api_key: str | None = None,
    collection: str = DEFAULT_COLLECTION,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_model: str = DEFAULT_REAL_EMBEDDING_MODEL,
    embedding_device: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    ollama_endpoint: str = DEFAULT_OLLAMA_EMBED_ENDPOINT,
    ollama_timeout: float = DEFAULT_OLLAMA_TIMEOUT,
    distance: str = DEFAULT_DISTANCE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    recreate: bool = False,
    wait: bool = True,
    include_full_text_payload: bool = False,
    dry_run: bool = False,
    require_candidate_quality_pass: bool = False,
    required_pages: Sequence[int] | None = None,
    min_loaded_points: int = 1,
    min_rag_points: int = 0,
    min_context_helper_points: int = 0,
    min_pages_with_points: int = 0,
    require_exact_qdrant_count: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, candidates_payload = load_candidates_payload(Path(candidates_path))
    candidate_quality = read_candidate_quality(Path(candidates_path))
    points, rejected = build_qdrant_points(
        candidates,
        embedding_mode=embedding_mode,
        embedding_dim=embedding_dim,
        embedding_model=embedding_model,
        embedding_device=embedding_device,
        ollama_url=ollama_url,
        ollama_endpoint=ollama_endpoint,
        ollama_timeout=ollama_timeout,
        include_full_text_payload=include_full_text_payload,
    )
    summary = summarize_points(points, rejected)

    # Write a preview without full vectors to keep generated artifacts small.
    preview_rows = []
    for point in points:
        payload = dict(point.get("payload") or {})
        preview_rows.append({"id": point.get("id"), "payload": payload, "vector_dim": len(point.get("vector") or [])})
    points_preview_path = output_dir / DEFAULT_POINTS_PREVIEW_FILE
    rejected_path = output_dir / DEFAULT_REJECTED_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    write_jsonl(points_preview_path, preview_rows)
    write_jsonl(rejected_path, rejected)
    write_json(summary_path, summary)

    load_result: dict[str, Any] = {
        "collection": collection,
        "batch_count": 0,
        "loaded_point_count": len(points),
        "qdrant_count": None,
        "duration_seconds": 0.0,
        "dry_run": dry_run,
    }
    if not dry_run:
        client = QdrantRestClient(qdrant_url, api_key=api_key, timeout=60.0)
        load_result = load_points_to_qdrant(
            client,
            collection=collection,
            points=points,
            vector_size=embedding_dim,
            distance=distance,
            batch_size=batch_size,
            recreate=recreate,
            wait=wait,
        )
        load_result["dry_run"] = False

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "DRY_RUN" if dry_run else "LOADED",
        "created_at_utc": utc_now_iso(),
        "qdrant_url": qdrant_url,
        "collection": collection,
        "embedding_mode": embedding_mode,
        "embedding_model": embedding_model_name_for_mode(embedding_mode, embedding_model),
        "embedding_dim": embedding_dim,
        "distance": distance,
        "batch_size": batch_size,
        "recreate": recreate,
        "wait": wait,
        "include_full_text_payload": include_full_text_payload,
        "dry_run": dry_run,
        "candidates_path": str(candidates_path),
        "candidates_sha256": sha256_file(Path(candidates_path)),
        "candidate_record_count": len(candidates),
        "candidate_artifact_record_count": candidates_payload.get("record_count"),
        "candidate_quality_status": candidate_quality.get("status"),
        "loaded_point_count": len(points),
        "rejected_count": len(rejected),
        "qdrant_count": load_result.get("qdrant_count"),
        "summary": summary,
        "load_result": load_result,
        "points_preview_path": str(points_preview_path),
        "rejected_path": str(rejected_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "safety_contract": {
            "qdrant_is_source_truth": False,
            "qdrant_can_answer_directly": False,
            "qdrant_can_prove_claims": False,
            "must_resolve_through_postgres": True,
            "must_pass_authority_gate": True,
            "must_use_source_citation": True,
        },
    }
    write_json(manifest_path, manifest)

    quality = check_qdrant_loader_quality(
        points=points,
        manifest=manifest,
        candidate_quality=candidate_quality,
        qdrant_count=load_result.get("qdrant_count"),
        required_pages=required_pages,
        min_loaded_points=min_loaded_points,
        min_rag_points=min_rag_points,
        min_context_helper_points=min_context_helper_points,
        min_pages_with_points=min_pages_with_points,
        require_candidate_quality_pass=require_candidate_quality_pass,
        require_exact_qdrant_count=require_exact_qdrant_count and not dry_run,
    )
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary})
    if not quality.passed:
        raise QdrantLoaderError("Qdrant loader quality check failed")
    return {
        "manifest": manifest,
        "summary": summary,
        "quality": {"status": quality.status, "checks": quality.checks, "summary": quality.summary},
        "paths": {
            "manifest_path": str(manifest_path),
            "summary_path": str(summary_path),
            "quality_path": str(quality_path),
            "rejected_path": str(rejected_path),
            "points_preview_path": str(points_preview_path),
        },
    }


def parse_page_range(raw: str | None) -> list[int]:
    if raw is None or not str(raw).strip():
        return []
    pages: list[int] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start = int(left.strip())
            end = int(right.strip())
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"invalid page range: {token}")
            pages.extend(range(start, end + 1))
        else:
            value = int(token)
            if value <= 0:
                raise ValueError("page numbers must be positive")
            pages.append(value)
    seen: set[int] = set()
    unique: list[int] = []
    for page in pages:
        if page not in seen:
            seen.add(page)
            unique.append(page)
    return unique


def load_manifest_for_quality(manifest_path: Path) -> dict[str, Any]:
    manifest = dict(read_json(manifest_path))
    return manifest


def check_quality_from_manifest(
    *,
    manifest_path: Path,
    qdrant_url: str | None = None,
    api_key: str | None = None,
    collection: str | None = None,
    required_pages: Sequence[int] | None = None,
    min_loaded_points: int = 1,
    min_rag_points: int = 0,
    min_context_helper_points: int = 0,
    min_pages_with_points: int = 0,
    require_candidate_quality_pass: bool = False,
    require_exact_qdrant_count: bool = False,
    write_json_output: bool = False,
) -> tuple[QualityResult, Path]:
    manifest = load_manifest_for_quality(manifest_path)
    qdrant_count = manifest.get("qdrant_count")
    target_url = qdrant_url or as_text(manifest.get("qdrant_url")) or DEFAULT_QDRANT_URL
    target_collection = collection or as_text(manifest.get("collection")) or DEFAULT_COLLECTION
    if target_url and target_collection and not manifest.get("dry_run"):
        try:
            client = QdrantRestClient(target_url, api_key=api_key or os.environ.get("QDRANT_API_KEY"), timeout=30.0)
            qdrant_count = client.count_points(target_collection, exact=True)
        except Exception:
            # Keep manifest count if live Qdrant is unavailable. The check will
            # still use persisted loader output.
            qdrant_count = manifest.get("qdrant_count")
    candidate_quality_status = manifest.get("candidate_quality_status")
    candidate_quality = {"status": candidate_quality_status} if candidate_quality_status else {}
    quality = check_qdrant_loader_quality(
        points=None,
        manifest=manifest,
        candidate_quality=candidate_quality,
        qdrant_count=int(qdrant_count) if qdrant_count is not None else None,
        required_pages=required_pages,
        min_loaded_points=min_loaded_points,
        min_rag_points=min_rag_points,
        min_context_helper_points=min_context_helper_points,
        min_pages_with_points=min_pages_with_points,
        require_candidate_quality_pass=require_candidate_quality_pass,
        require_exact_qdrant_count=require_exact_qdrant_count,
    )
    quality_path = Path(manifest.get("quality_path") or (Path(manifest_path).parent / DEFAULT_QUALITY_FILE))
    if write_json_output:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary})
    return quality, quality_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load TRACE-Net embedding candidates into Qdrant safely.")
    parser.add_argument("--candidates-path", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("TRACE_NET_QDRANT_COLLECTION", DEFAULT_COLLECTION))
    parser.add_argument("--embedding-mode", default=DEFAULT_EMBEDDING_MODE, choices=["hash", "existing", "precomputed", "existing_vector", "sentence-transformers", "sentence_transformers", "bge-m3", "bge_m3", "real", "ollama", "ollama-embed", "ollama_embed", "ollama-embeddings", "ollama_embeddings"])
    parser.add_argument("--embedding-model", default=os.environ.get("TRACE_NET_EMBEDDING_MODEL", DEFAULT_REAL_EMBEDDING_MODEL))
    parser.add_argument("--embedding-device", default=os.environ.get("TRACE_NET_EMBEDDING_DEVICE", ""), help="Optional torch device, for example cuda, cpu, or cuda:0. Ignored for Ollama mode.")
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", os.environ.get("TRACE_NET_OLLAMA_URL", DEFAULT_OLLAMA_URL)), help="Local Ollama base URL for --embedding-mode ollama.")
    parser.add_argument("--ollama-endpoint", default=os.environ.get("OLLAMA_EMBED_ENDPOINT", os.environ.get("TRACE_NET_OLLAMA_EMBED_ENDPOINT", DEFAULT_OLLAMA_EMBED_ENDPOINT)), help="Ollama embedding endpoint. Default: /api/embed; legacy: /api/embeddings.")
    parser.add_argument("--ollama-timeout", type=float, default=float(os.environ.get("TRACE_NET_OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT)))
    parser.add_argument("--embedding-dim", type=int, default=int(os.environ.get("TRACE_NET_EMBEDDING_DIM", DEFAULT_EMBEDDING_DIM)))
    parser.add_argument("--distance", default=DEFAULT_DISTANCE)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the Qdrant collection before loading.")
    parser.add_argument("--no-wait", action="store_true", help="Do not wait for Qdrant upsert completion.")
    parser.add_argument("--include-full-text-payload", action="store_true", help="Store full safe embedding text in Qdrant payload. Default stores preview only.")
    parser.add_argument("--dry-run", action="store_true", help="Build points and quality artifacts without calling Qdrant.")
    parser.add_argument("--require-first-pages", default="", help="Required page range, for example 1-50.")
    parser.add_argument("--min-loaded-points", type=int, default=1)
    parser.add_argument("--min-rag-points", type=int, default=0)
    parser.add_argument("--min-context-helper-points", type=int, default=0)
    parser.add_argument("--min-pages-with-points", type=int, default=0)
    parser.add_argument("--require-candidate-quality-pass", action="store_true")
    parser.add_argument("--require-exact-qdrant-count", action="store_true")
    parser.add_argument("--quality", action="store_true", help="Write quality JSON and fail if quality gates fail.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    required_pages = parse_page_range(args.require_first_pages)
    result = build_and_load_qdrant_index(
        candidates_path=args.candidates_path,
        output_dir=args.output_dir,
        qdrant_url=args.qdrant_url,
        api_key=args.api_key,
        collection=args.collection,
        embedding_mode=args.embedding_mode,
        embedding_dim=args.embedding_dim,
        embedding_model=args.embedding_model,
        embedding_device=args.embedding_device or None,
        ollama_url=args.ollama_url,
        ollama_endpoint=args.ollama_endpoint,
        ollama_timeout=args.ollama_timeout,
        distance=args.distance,
        batch_size=args.batch_size,
        recreate=args.recreate,
        wait=not args.no_wait,
        include_full_text_payload=args.include_full_text_payload,
        dry_run=args.dry_run,
        require_candidate_quality_pass=args.require_candidate_quality_pass,
        required_pages=required_pages,
        min_loaded_points=args.min_loaded_points,
        min_rag_points=args.min_rag_points,
        min_context_helper_points=args.min_context_helper_points,
        min_pages_with_points=args.min_pages_with_points,
        require_exact_qdrant_count=args.require_exact_qdrant_count,
        write_quality=args.quality,
    )
    manifest = result["manifest"]
    summary = result["summary"]
    quality = result["quality"]
    print("TRACE-Net Qdrant loader v1")
    print(f" Status: {manifest['status']}")
    print(f" collection: {manifest['collection']}")
    print(f" qdrant_url: {manifest['qdrant_url']}")
    print(f" embedding_mode: {manifest['embedding_mode']}")
    print(f" embedding_dim: {manifest['embedding_dim']}")
    print(f" loaded_point_count: {manifest['loaded_point_count']}")
    print(f" qdrant_count: {manifest.get('qdrant_count')}")
    print(f" rag_candidate_point_count: {summary['rag_candidate_point_count']}")
    print(f" context_helper_point_count: {summary['context_helper_point_count']}")
    print(f" page_count: {summary['page_count']}")
    print(f" unsafe_qdrant_payload_count: {quality['summary']['unsafe_qdrant_payload_count']}")
    print(f" rejected_count: {summary['rejected_count']}")
    print(f" manifest_path: {result['paths']['manifest_path']}")
    print(f" summary_path: {result['paths']['summary_path']}")
    print(f" points_preview_path: {result['paths']['points_preview_path']}")
    print(f" rejected_path: {result['paths']['rejected_path']}")
    if args.quality:
        print(f" Quality status: {quality['status']}")
        print(f" quality_path: {result['paths']['quality_path']}")
    return 0


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Qdrant loader v1 quality.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_MANIFEST_FILE)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL"))
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("TRACE_NET_QDRANT_COLLECTION"))
    parser.add_argument("--require-first-pages", default="")
    parser.add_argument("--min-loaded-points", type=int, default=1)
    parser.add_argument("--min-rag-points", type=int, default=0)
    parser.add_argument("--min-context-helper-points", type=int, default=0)
    parser.add_argument("--min-pages-with-points", type=int, default=0)
    parser.add_argument("--require-candidate-quality-pass", action="store_true")
    parser.add_argument("--require-exact-qdrant-count", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    quality, quality_path = check_quality_from_manifest(
        manifest_path=args.manifest_path,
        qdrant_url=args.qdrant_url,
        api_key=args.api_key,
        collection=args.collection,
        required_pages=parse_page_range(args.require_first_pages),
        min_loaded_points=args.min_loaded_points,
        min_rag_points=args.min_rag_points,
        min_context_helper_points=args.min_context_helper_points,
        min_pages_with_points=args.min_pages_with_points,
        require_candidate_quality_pass=args.require_candidate_quality_pass,
        require_exact_qdrant_count=args.require_exact_qdrant_count,
        write_json_output=args.write_json,
    )
    summary = quality.summary
    print("TRACE-Net Qdrant loader v1 quality")
    print(f" Status: {quality.status}")
    print(f" point_count: {summary.get('point_count')}")
    print(f" qdrant_count: {summary.get('qdrant_count')}")
    print(f" rag_candidate_point_count: {summary.get('rag_candidate_point_count')}")
    print(f" context_helper_point_count: {summary.get('context_helper_point_count')}")
    print(f" page_count: {summary.get('page_count')}")
    print(f" required_page_missing_count: {summary.get('required_page_missing_count')}")
    print(f" unsafe_qdrant_payload_count: {summary.get('unsafe_qdrant_payload_count')}")
    print(f" rejected_count: {summary.get('rejected_count')}")
    print(f" candidate_quality_status: {summary.get('candidate_quality_status')}")
    if args.write_json:
        print(f" quality_path: {quality_path}")
    if not quality.passed:
        for check in quality.checks:
            if not check["passed"]:
                print(f" FAIL {check['name']}: expected {check['expected']}, actual {check['actual']}")
        return 1
    return 0


# Friendly aliases used by wrapper scripts and tests.
main_load = main
main_quality = quality_main
QdrantHTTPClient = QdrantRestClient


if __name__ == "__main__":
    raise SystemExit(main())
