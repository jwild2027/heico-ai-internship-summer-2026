"""TRACE-Net Evidence Snippet Cleaner / Source Text Extractor v1.

Step 11.6 consumes Step 11.5 snippet-claim artifacts and produces cleaned,
source-facing evidence snippets. It is deliberately not a final answer gate.

Safety contract:

* only source_text_evidence and meaningful verified_part_evidence may become
  cleaned snippet claims;
* page_retrieval_profile, context_retrieval_helper, source_evidence, and
  derived_context remain retrieval-only and cannot become cleaned claims;
* local file paths, TRACE-Net boilerplate, raw byte wrappers, source URL/path
  metadata, and debug/prompt text are removed from user-facing snippets;
* source_text_evidence may read its traceable OCR file path when available to
  recover actual manual text from metadata-wrapped source snippets;
* every cleaned snippet remains final-answer-blocked until a later final-answer
  gate explicitly authorizes it.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_evidence_snippet_cleaner_v1"
DEFAULT_SNIPPET_CLAIMS = Path(
    "local_data/organization/trace_net/evidence_snippet_claims/trace_net_evidence_snippet_claims_v1.json"
)
DEFAULT_CONTEXT_PACK = Path(
    "local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json"
)
DEFAULT_EMBEDDING_CANDIDATES = Path(
    "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/evidence_snippet_cleaner")
DEFAULT_REPORT_FILE = "trace_net_evidence_snippet_cleaner_v1.json"
DEFAULT_CLAIMS_FILE = "trace_net_evidence_snippet_cleaner_v1_claims.jsonl"
DEFAULT_BLOCKED_FILE = "trace_net_evidence_snippet_cleaner_v1_blocked_records.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_evidence_snippet_cleaner_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_evidence_snippet_cleaner_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_evidence_snippet_cleaner_v1_quality.json"
DEFAULT_MD_FILE = "trace_net_evidence_snippet_cleaner_v1.md"
DEFAULT_HTML_FILE = "trace_net_evidence_snippet_cleaner_v1.html"

ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "derived_context",
}
BANNED_SNIPPET_BUCKETS = RETRIEVAL_ONLY_BUCKETS | {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_candidates",
    "table_tile",
    "table_tiles",
    "feedback_only",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}

BOILERPLATE_PHRASES = [
    "source text evidence for page",
    "this chunk is source-backed ocr/page-context text",
    "this chunk is source-backed",
    "verified part evidence for page",
    "this record comes from the verified part evidence pool",
    "verified part evidence is present for this page, but no page-index part list was available",
    "no page-index part list was available",
    "can be searched as source text evidence",
    "source-traceable",
    "trace-net",
]

FORBIDDEN_CLEAN_MARKERS = [
    "source text evidence for page",
    "this chunk is source-backed",
    "verified part evidence for page",
    "this record comes from the verified part evidence pool",
    "source url:",
    "tiff path:",
    "ocr path:",
    "source path:",
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "ocr text: [b",
    "[b'",
    '[b"',
    "b'",
    'b"',
    "c:\\users\\",
    "prompt:",
    "debug:",
]

METADATA_LINE_PREFIXES = [
    "source text evidence for page",
    "this chunk is source-backed",
    "verified part evidence for page",
    "this record comes from the verified part evidence pool",
    "document:",
    "ata:",
    "source url:",
    "tiff path:",
    "ocr path:",
    "source path:",
    "local path:",
    "embedding text:",
    "text preview:",
    "trace-net:",
    "candidate id:",
    "citation id:",
    "page id:",
    "document id:",
    "authority:",
    "trust tier:",
]

PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>]+|(?:^|\s)(?:local_data|rescarta_exports)[\\/][^\s\"'<>]+|[^\s\"'<>]*(?:\\|/)(?:local_data|rescarta_exports)(?:\\|/)[^\s\"'<>]*)",
    flags=re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", flags=re.IGNORECASE)
RAW_BYTES_RE = re.compile(r"\bb(['\"])(.*?)(?<!\\)\1", flags=re.DOTALL)
PART_NUMBER_RE = re.compile(r"\b[A-Z0-9]{2,}[-/][A-Z0-9][A-Z0-9-/]{2,}\b", flags=re.IGNORECASE)

FORBIDDEN_USE = [
    "final_answer_without_final_gate",
    "uncited_clean_snippet_claim",
    "clean_snippet_claim_from_page_profile",
    "clean_snippet_claim_from_context_retrieval_helper",
    "clean_snippet_claim_from_source_evidence_locator",
    "clean_snippet_claim_from_derived_context",
    "clean_snippet_claim_from_raw_ocr_or_raw_visual_extraction",
    "clean_snippet_contains_local_path",
    "clean_snippet_contains_trace_net_boilerplate",
    "clean_snippet_contains_raw_bytes_repr",
    "source_truth_mutation",
    "trust_tier_override",
    "citation_replacement",
    "llm_freeform_claim_generation",
]


class EvidenceSnippetCleanerError(RuntimeError):
    """Raised when cleaner artifacts cannot be built safely."""


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


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = as_text(value).lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


def as_int(value: Any, *, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def normalize_bucket(value: Any) -> str:
    return as_text(value).strip().lower().replace("-", "_").replace(" ", "_")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
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
    return hashlib.sha256(as_text(text).encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    text = "|".join(as_text(part) for part in parts)
    return f"{prefix}__{hashlib.sha256(text.encode('utf-8')).hexdigest()[:length]}"


def compact_text(value: Any, *, max_chars: int = 900) -> str:
    text = " ".join(as_text(value).replace("\x00", " ").split())
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def load_mapping_artifact(path: Path, *, name: str) -> dict[str, Any]:
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        raise EvidenceSnippetCleanerError(f"{name} is not a JSON object: {path}")
    return dict(payload)


def artifact_quality_status(payload: Mapping[str, Any]) -> str:
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return as_text(quality.get("status") or payload.get("quality_status") or summary.get("quality_status"))


def artifact_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload.get("summary") or {}) if isinstance(payload.get("summary"), Mapping) else {}


def record_bucket(record: Mapping[str, Any]) -> str:
    return normalize_bucket(record.get("rag_bucket") or record.get("bucket") or record.get("safety_bucket"))


def citation_ids_from(record: Mapping[str, Any]) -> list[str]:
    raw = record.get("citation_ids")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        ids = [as_text(item) for item in raw if as_text(item)]
    else:
        ids = []
    if as_text(record.get("citation_id")):
        ids.append(as_text(record.get("citation_id")))
    return sorted(set(ids))


def page_label(page_id: str, page_number: Any = None) -> str:
    if page_number not in (None, ""):
        return f"page {page_number} ({page_id})"
    if page_id:
        tail = page_id.rsplit("p", 1)[-1]
        if tail.isdigit():
            return f"page {int(tail)} ({page_id})"
        return page_id
    return "an unresolved page"


def looks_like_raw_bytes_repr(text: str) -> bool:
    lower = as_text(text).lower()
    return bool(re.search(r"(^|[\[\s,])b['\"]", text)) or "ocr text: [b" in lower


def decode_raw_bytes_repr(text: str) -> str:
    """Decode Python bytes repr fragments like [b'...'] when present."""
    value = as_text(text)
    matches = RAW_BYTES_RE.findall(value)
    if not matches:
        # Handle a partially-truncated marker such as "[b..." by removing it.
        return re.sub(r"\[?b['\"]?", " ", value).strip()
    decoded: list[str] = []
    for _quote, body in matches:
        try:
            decoded.append(codecs.decode(body, "unicode_escape"))
        except Exception:
            decoded.append(body)
    return "\n".join(decoded)


def remove_metadata_sentences(text: str) -> str:
    # Treat common metadata labels as sentence starts because Step 11.5 snippets
    # are often compacted into one paragraph rather than line-separated text.
    normalized = as_text(text).replace("\r", "\n")
    normalized = re.sub(r"\s+(Document:|ATA:|Source URL:|TIFF path:|OCR path:|Source path:|OCR text:)", r"\n\1", normalized, flags=re.IGNORECASE)
    lines = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip(" .\t")
        if not line:
            continue
        lower = line.lower()
        if any(lower.startswith(prefix) for prefix in METADATA_LINE_PREFIXES):
            # OCR text is handled before this function when possible; line-level
            # removal prevents the label itself from leaking if no OCR body exists.
            continue
        if PATH_RE.search(line) or URL_RE.search(line):
            continue
        lines.append(line)
    return " ".join(lines)


def strip_forbidden_paths_and_urls(text: str) -> str:
    value = PATH_RE.sub(" ", as_text(text))
    value = URL_RE.sub(" ", value)
    value = re.sub(r"\b(?:Source URL|TIFF path|OCR path|Source path)\s*:\s*\S+", " ", value, flags=re.IGNORECASE)
    return value


def extract_after_text_marker(text: str) -> str:
    value = as_text(text)
    markers = ["OCR text:", "Source text:", "Evidence text:", "Candidate text:", "Text:"]
    best = value
    for marker in markers:
        index = value.lower().rfind(marker.lower())
        if index >= 0:
            tail = value[index + len(marker) :].strip()
            if len(tail) >= 2:
                best = tail
                break
    return best


def clean_manual_text(raw_text: Any, *, max_chars: int = 700) -> str:
    """Return source-facing snippet text with TRACE-Net wrappers removed."""
    text = as_text(raw_text)
    if not text:
        return ""
    text = text.replace("\ufeff", " ").replace("\x00", " ")
    # Prefer the actual text tail when a metadata wrapper contains OCR text.
    if re.search(r"\b(?:OCR text|Source text|Evidence text|Candidate text|Text)\s*:", text, flags=re.IGNORECASE):
        text = extract_after_text_marker(text)
    if looks_like_raw_bytes_repr(text):
        text = decode_raw_bytes_repr(text)
    text = text.replace("\\r", "\n").replace("\\n", "\n")
    text = strip_forbidden_paths_and_urls(text)
    text = remove_metadata_sentences(text)
    for phrase in BOILERPLATE_PHRASES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .\t\n\r;:")
    # Remove remaining naked bytes wrappers that may survive malformed input.
    text = re.sub(r"(^|\s)\[?b['\"]", " ", text).strip()
    text = re.sub(r"['\"]\]?($|\s)", " ", text).strip()
    return compact_text(text, max_chars=max_chars)


def clean_snippet_contains_forbidden_text(text: Any) -> bool:
    lower = as_text(text).lower()
    if not lower:
        return False
    if PATH_RE.search(as_text(text)) or URL_RE.search(as_text(text)):
        return True
    return any(marker in lower for marker in FORBIDDEN_CLEAN_MARKERS)


def clean_snippet_forbidden_markers(text: Any) -> list[str]:
    value = as_text(text)
    lower = value.lower()
    markers = [marker for marker in FORBIDDEN_CLEAN_MARKERS if marker in lower]
    if PATH_RE.search(value):
        markers.append("local_or_rescarta_path")
    if URL_RE.search(value):
        markers.append("url")
    return sorted(set(markers))


def safe_read_text_file(path_value: Any, *, repo_root: Path | None = None, max_chars: int = 20000) -> tuple[str, str]:
    """Read a traceable local text file if available. Returns (text, resolved_path)."""
    raw = as_text(path_value)
    if not raw:
        return "", ""
    # Windows paths are valid on the user's machine. In tests/Linux, replace
    # backslashes only for relative paths so both styles work.
    candidates: list[Path] = []
    candidates.append(Path(raw))
    if "\\" in raw and not re.match(r"^[A-Za-z]:\\", raw):
        candidates.append(Path(raw.replace("\\", "/")))
    if repo_root is not None:
        candidates.extend([repo_root / c for c in list(candidates) if not c.is_absolute()])
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if not candidate.exists() or not candidate.is_file():
                continue
            data = candidate.read_bytes()[:max_chars]
            try:
                return data.decode("utf-8", errors="replace"), str(candidate)
            except Exception:
                return data.decode("latin-1", errors="replace"), str(candidate)
        except Exception:
            continue
    return "", ""


def load_embedding_candidate_index(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not Path(path).exists():
        return {}
    try:
        payload = read_json(Path(path))
    except Exception:
        return {}
    records = payload.get("records") if isinstance(payload, Mapping) else None
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping):
            continue
        record = dict(item)
        for key in ("embedding_candidate_id", "source_candidate_id", "citation_id"):
            value = as_text(record.get(key))
            if value:
                index[value] = record
    return index


def find_candidate_enrichment(claim: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for key in ("embedding_candidate_id", "source_candidate_id", "citation_id"):
        value = as_text(claim.get(key))
        if value and value in index:
            return dict(index[value])
    for citation_id in citation_ids_from(claim):
        if citation_id in index:
            return dict(index[citation_id])
    return {}


def source_text_for_cleaning(
    claim: Mapping[str, Any],
    *,
    candidate_enrichment: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
    allow_local_ocr_read: bool = True,
) -> tuple[str, str, str]:
    """Return raw text to clean, source kind, and path if read from a file."""
    enrichment = candidate_enrichment or {}
    bucket = record_bucket(claim)
    if allow_local_ocr_read and bucket == "source_text_evidence":
        for field in ("ocr_path", "source_path", "text_path"):
            text, used_path = safe_read_text_file(claim.get(field) or enrichment.get(field), repo_root=repo_root)
            if as_text(text):
                return text, f"local_{field}", used_path
    for field in (
        "source_text",
        "clean_text",
        "ocr_text",
        "manual_text",
        "source_snippet",
        "text_preview",
        "embedding_text",
        "text_for_embedding",
    ):
        value = claim.get(field)
        if as_text(value):
            return as_text(value), f"claim_{field}", ""
        value = enrichment.get(field)
        if as_text(value):
            return as_text(value), f"candidate_{field}", ""
    return "", "missing", ""


def verified_part_has_meaningful_content(claim: Mapping[str, Any], clean_text: str) -> bool:
    lower = as_text(clean_text).lower()
    if not clean_text:
        return False
    if "no page-index part list" in lower or "no part list" in lower:
        return False
    if PART_NUMBER_RE.search(clean_text):
        return True
    # Also allow explicitly provided part/nomenclature fields if they survived.
    for key in ("part_number", "part_id", "nomenclature", "known_parts", "known_nomenclature"):
        if as_text(claim.get(key)):
            return True
    return len(clean_text) >= 40 and any(word in lower for word in ("part", "nomenclature", "assembly", "placard", "label"))


def cleaner_block_reasons(
    claim: Mapping[str, Any],
    *,
    clean_snippet: str,
    source_kind: str,
    min_clean_snippet_chars: int = 20,
) -> list[str]:
    reasons: list[str] = []
    bucket = record_bucket(claim)
    if bucket not in ANSWER_SUPPORT_BUCKETS:
        reasons.append(f"bucket_not_clean_snippet_allowed:{bucket or 'missing'}")
    if bucket in BANNED_SNIPPET_BUCKETS:
        reasons.append(f"retrieval_or_banned_bucket:{bucket}")
    if not as_text(claim.get("page_id")):
        reasons.append("missing_page_id")
    if not citation_ids_from(claim):
        reasons.append("missing_citation")
    if not as_text(claim.get("authority")):
        reasons.append("missing_authority")
    if not as_bool(claim.get("requires_source_resolution"), default=True):
        reasons.append("missing_source_resolution_requirement")
    if not as_bool(claim.get("requires_citation"), default=True):
        reasons.append("missing_citation_requirement")
    if not as_bool(claim.get("requires_authority_gate"), default=True):
        reasons.append("missing_authority_gate_requirement")
    if as_bool(claim.get("final_answer_allowed"), default=False):
        reasons.append("final_answer_already_allowed")
    if as_bool(claim.get("llm_freeform_answer_allowed"), default=False):
        reasons.append("llm_freeform_answer_allowed")
    if as_bool(claim.get("can_mutate_source_truth"), default=False) or as_bool(claim.get("source_truth_mutation_allowed"), default=False):
        reasons.append("source_truth_mutation_allowed")
    if len(as_text(clean_snippet)) < int(min_clean_snippet_chars):
        reasons.append("clean_snippet_too_short")
    if clean_snippet_contains_forbidden_text(clean_snippet):
        reasons.append("clean_snippet_contains_forbidden_metadata_or_path")
    if looks_like_raw_bytes_repr(clean_snippet):
        reasons.append("clean_snippet_contains_raw_bytes_repr")
    if bucket == "verified_part_evidence" and not verified_part_has_meaningful_content(claim, clean_snippet):
        reasons.append("verified_part_evidence_low_content")
        # Low-content verified-part wrapper text is the actionable reason; avoid
        # double-counting it as a generic short-snippet failure.
        reasons = [reason for reason in reasons if reason != "clean_snippet_too_short"]
    if source_kind == "missing":
        reasons.append("missing_source_text_for_cleaning")
    return sorted(set(reasons))


def build_clean_snippet_claim(
    claim: Mapping[str, Any],
    *,
    clean_snippet: str,
    raw_source_kind: str,
    raw_source_path: str,
    clean_rank: int,
) -> dict[str, Any]:
    bucket = record_bucket(claim)
    citation_ids = citation_ids_from(claim)
    page_id = as_text(claim.get("page_id"))
    page_number = claim.get("page_number")
    claim_type = "clean_source_text_snippet" if bucket == "source_text_evidence" else "clean_verified_part_snippet"
    cleaned_claim_text = (
        f"{page_label(page_id, page_number)} has citation-backed cleaned source-text evidence: \"{compact_text(clean_snippet, max_chars=240)}\""
        if bucket == "source_text_evidence"
        else f"{page_label(page_id, page_number)} has citation-backed cleaned verified part/page evidence: \"{compact_text(clean_snippet, max_chars=240)}\""
    )
    return {
        "clean_snippet_claim_id": stable_id("clean_snip_claim", claim.get("snippet_claim_id"), page_id, citation_ids[0] if citation_ids else "", clean_snippet),
        "schema_version": SCHEMA_VERSION,
        "clean_snippet_status": "CLEAN_SNIPPET_MATERIALIZED",
        "answer_status": "CLEAN_SNIPPETS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "requires_final_answer_gate": True,
        "claim_type": claim_type,
        "query": as_text(claim.get("query")),
        "clean_materialized_claim_text": cleaned_claim_text,
        "source_materialized_claim_text": as_text(claim.get("materialized_claim_text")),
        "source_snippet_claim_id": as_text(claim.get("snippet_claim_id")),
        "source_snippet_claim_rank": as_int(claim.get("snippet_claim_rank")),
        "clean_snippet_rank": clean_rank,
        "page_id": page_id,
        "page_number": page_number,
        "document_id": as_text(claim.get("document_id")),
        "ata_code": as_text(claim.get("ata_code")),
        "rag_bucket": bucket,
        "authority": as_text(claim.get("authority")),
        "trust_tier": as_text(claim.get("trust_tier")),
        "citation_ids": citation_ids,
        "citation_id": citation_ids[0] if citation_ids else "",
        "clean_source_snippet": clean_snippet,
        "clean_source_snippet_sha256": sha256_text(clean_snippet),
        "clean_source_snippet_char_count": len(clean_snippet),
        "raw_source_kind": raw_source_kind,
        "raw_source_path_read": bool(raw_source_path),
        # Keep only a boolean and digest for local file reads; do not emit paths.
        "raw_source_path_sha256": sha256_text(raw_source_path) if raw_source_path else "",
        "original_source_snippet_sha256": sha256_text(claim.get("source_snippet")),
        "original_source_snippet_char_count": len(as_text(claim.get("source_snippet"))),
        "draft_claim_id": as_text(claim.get("draft_claim_id")),
        "context_record_id": as_text(claim.get("context_record_id")),
        "context_group_id": as_text(claim.get("context_group_id")),
        "context_group_rank": as_int(claim.get("context_group_rank")),
        "embedding_candidate_id": as_text(claim.get("embedding_candidate_id")),
        "source_candidate_id": as_text(claim.get("source_candidate_id")),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "canonical_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "source_truth_mutation_allowed": False,
        "retrieval_only_source_used_as_claim": False,
        "cleaning_policy": "remove_metadata_paths_raw_bytes_and_boilerplate_require_final_answer_gate",
        "forbidden_use": list(FORBIDDEN_USE),
        "unsafe_reasons": [],
    }


def build_blocked_clean_snippet(
    claim: Mapping[str, Any],
    *,
    clean_snippet: str,
    raw_source_kind: str,
    block_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "blocked_clean_snippet_id": stable_id("blocked_clean_snip", claim.get("snippet_claim_id"), claim.get("page_id"), citation_ids_from(claim), block_reasons),
        "schema_version": SCHEMA_VERSION,
        "blocked_from_clean_snippet": True,
        "block_reasons": sorted(set(as_text(reason) for reason in block_reasons if as_text(reason))),
        "source_snippet_claim_id": as_text(claim.get("snippet_claim_id")),
        "source_snippet_claim_rank": as_int(claim.get("snippet_claim_rank")),
        "page_id": as_text(claim.get("page_id")),
        "rag_bucket": record_bucket(claim),
        "authority": as_text(claim.get("authority")),
        "citation_ids": citation_ids_from(claim),
        "clean_snippet_preview": compact_text(clean_snippet, max_chars=240),
        "clean_snippet_char_count": len(as_text(clean_snippet)),
        "raw_source_kind": raw_source_kind,
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
    }


def build_clean_snippets_from_artifacts(
    *,
    snippet_claims_payload: Mapping[str, Any],
    embedding_candidate_index: Mapping[str, Mapping[str, Any]] | None = None,
    max_claims: int = 12,
    max_clean_snippet_chars: int = 700,
    min_clean_snippet_chars: int = 20,
    repo_root: Path | None = None,
    allow_local_ocr_read: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_claims = snippet_claims_payload.get("snippet_claims") or snippet_claims_payload.get("claims") or []
    claims = [dict(item) for item in raw_claims if isinstance(item, Mapping)]
    index = embedding_candidate_index or {}
    clean_claims: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        enrichment = find_candidate_enrichment(claim, index)
        raw_text, raw_kind, raw_path = source_text_for_cleaning(
            claim,
            candidate_enrichment=enrichment,
            repo_root=repo_root,
            allow_local_ocr_read=allow_local_ocr_read,
        )
        clean_snippet = clean_manual_text(raw_text, max_chars=max_clean_snippet_chars)
        reasons = cleaner_block_reasons(
            claim,
            clean_snippet=clean_snippet,
            source_kind=raw_kind,
            min_clean_snippet_chars=min_clean_snippet_chars,
        )
        if reasons:
            blocked.append(
                build_blocked_clean_snippet(
                    claim,
                    clean_snippet=clean_snippet,
                    raw_source_kind=raw_kind,
                    block_reasons=reasons,
                )
            )
            continue
        source_key = "|".join([as_text(claim.get("snippet_claim_id")), as_text(claim.get("page_id")), (citation_ids_from(claim) or [""])[0]])
        if source_key in seen:
            continue
        clean_claims.append(
            build_clean_snippet_claim(
                claim,
                clean_snippet=clean_snippet,
                raw_source_kind=raw_kind,
                raw_source_path=raw_path,
                clean_rank=len(clean_claims) + 1,
            )
        )
        seen.add(source_key)
        if len(clean_claims) >= int(max_claims):
            break
    return clean_claims, blocked


def summarize_clean_snippets(
    *,
    snippet_claims_payload: Mapping[str, Any],
    context_pack: Mapping[str, Any] | None,
    clean_claims: Sequence[Mapping[str, Any]],
    blocked_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    snippet_summary = artifact_summary(snippet_claims_payload)
    context_summary = artifact_summary(context_pack or {})
    bucket_counts = Counter(record_bucket(claim) for claim in clean_claims)
    authority_counts = Counter(as_text(claim.get("authority")) for claim in clean_claims)
    citation_ids = sorted({as_text(cid) for claim in clean_claims for cid in claim.get("citation_ids") or [] if as_text(cid)})
    page_ids = sorted({as_text(claim.get("page_id")) for claim in clean_claims if as_text(claim.get("page_id"))})

    uncited_count = sum(1 for claim in clean_claims if not citation_ids_from(claim))
    missing_page_id_count = sum(1 for claim in clean_claims if not as_text(claim.get("page_id")))
    missing_clean_snippet_count = sum(1 for claim in clean_claims if not as_text(claim.get("clean_source_snippet")))
    clean_boilerplate_count = sum(1 for claim in clean_claims if clean_snippet_contains_forbidden_text(claim.get("clean_source_snippet")))
    local_path_leak_count = sum(1 for claim in clean_claims if PATH_RE.search(as_text(claim.get("clean_source_snippet"))) or URL_RE.search(as_text(claim.get("clean_source_snippet"))))
    raw_bytes_repr_count = sum(1 for claim in clean_claims if looks_like_raw_bytes_repr(as_text(claim.get("clean_source_snippet"))))
    forbidden_marker_count = sum(1 for claim in clean_claims if clean_snippet_forbidden_markers(claim.get("clean_source_snippet")))
    retrieval_only_count = sum(1 for claim in clean_claims if record_bucket(claim) in RETRIEVAL_ONLY_BUCKETS or as_bool(claim.get("retrieval_only_source_used_as_claim"), default=False))
    page_profile_count = sum(1 for claim in clean_claims if record_bucket(claim) == "page_retrieval_profile")
    context_helper_count = sum(1 for claim in clean_claims if record_bucket(claim) == "context_retrieval_helper")
    source_evidence_count = sum(1 for claim in clean_claims if record_bucket(claim) == "source_evidence")
    derived_context_count = sum(1 for claim in clean_claims if record_bucket(claim) == "derived_context")
    source_text_count = sum(1 for claim in clean_claims if record_bucket(claim) == "source_text_evidence")
    verified_part_count = sum(1 for claim in clean_claims if record_bucket(claim) == "verified_part_evidence")
    claim_without_authority_count = sum(1 for claim in clean_claims if not as_text(claim.get("authority")))
    direct_answer_allowed_count = sum(1 for claim in clean_claims if as_bool(claim.get("can_answer_directly"), default=False))
    claim_proof_direct_count = sum(1 for claim in clean_claims if as_bool(claim.get("can_prove_claims"), default=False))
    source_truth_mutation_allowed_count = sum(1 for claim in clean_claims if as_bool(claim.get("can_mutate_source_truth"), default=False) or as_bool(claim.get("source_truth_mutation_allowed"), default=False))
    final_answer_allowed_count = sum(1 for claim in clean_claims if as_bool(claim.get("final_answer_allowed"), default=False))
    llm_freeform_answer_allowed_count = sum(1 for claim in clean_claims if as_bool(claim.get("llm_freeform_answer_allowed"), default=False))
    missing_source_resolution_count = sum(1 for claim in clean_claims if as_bool(claim.get("requires_source_resolution"), default=False) is not True)
    missing_authority_gate_count = sum(1 for claim in clean_claims if as_bool(claim.get("requires_authority_gate"), default=False) is not True)
    missing_citation_requirement_count = sum(1 for claim in clean_claims if as_bool(claim.get("requires_citation"), default=False) is not True)
    source_path_read_count = sum(1 for claim in clean_claims if as_bool(claim.get("raw_source_path_read"), default=False))

    return {
        "schema_version": SCHEMA_VERSION,
        "query": as_text(snippet_summary.get("query") or snippet_claims_payload.get("query")),
        "answer_status": "CLEAN_SNIPPETS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "snippet_claims_quality_status": artifact_quality_status(snippet_claims_payload),
        "snippet_claims_answer_status": as_text(snippet_claims_payload.get("answer_status") or snippet_summary.get("answer_status")),
        "context_pack_quality_status": artifact_quality_status(context_pack or {}),
        "context_pack_answer_status": as_text((context_pack or {}).get("answer_status") or context_summary.get("answer_status")),
        "embedding_mode": as_text(snippet_summary.get("embedding_mode") or context_summary.get("embedding_mode")),
        "embedding_model_name": as_text(snippet_summary.get("embedding_model_name") or context_summary.get("embedding_model_name")),
        "embedding_dim": as_int(snippet_summary.get("embedding_dim") or context_summary.get("embedding_dim")),
        "source_snippet_claim_count": as_int(snippet_summary.get("snippet_claim_count") or len(snippet_claims_payload.get("snippet_claims") or [])),
        "clean_snippet_claim_count": len(clean_claims),
        "cited_clean_snippet_count": len(clean_claims) - uncited_count,
        "uncited_clean_snippet_count": uncited_count,
        "missing_page_id_count": missing_page_id_count,
        "missing_citation_count": uncited_count,
        "missing_clean_snippet_count": missing_clean_snippet_count,
        "clean_snippet_present_count": len(clean_claims) - missing_clean_snippet_count,
        "boilerplate_snippet_count": clean_boilerplate_count,
        "local_path_leak_count": local_path_leak_count,
        "raw_bytes_repr_count": raw_bytes_repr_count,
        "forbidden_marker_count": forbidden_marker_count,
        "retrieval_only_clean_claim_count": retrieval_only_count,
        "page_profile_clean_claim_count": page_profile_count,
        "context_helper_clean_claim_count": context_helper_count,
        "source_evidence_clean_claim_count": source_evidence_count,
        "derived_context_clean_claim_count": derived_context_count,
        "source_text_evidence_clean_claim_count": source_text_count,
        "verified_part_evidence_clean_claim_count": verified_part_count,
        "claim_without_authority_count": claim_without_authority_count,
        "direct_answer_allowed_claim_count": direct_answer_allowed_count,
        "claim_proof_direct_count": claim_proof_direct_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "final_answer_allowed_count": final_answer_allowed_count,
        "llm_freeform_answer_allowed_count": llm_freeform_answer_allowed_count,
        "missing_source_resolution_count": missing_source_resolution_count,
        "missing_authority_gate_count": missing_authority_gate_count,
        "missing_citation_requirement_count": missing_citation_requirement_count,
        "blocked_clean_snippet_count": len(blocked_records),
        "source_path_read_count": source_path_read_count,
        "page_count": len(page_ids),
        "page_ids": page_ids,
        "citation_count": len(citation_ids),
        "citation_ids": citation_ids,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
    }


def evaluate_clean_snippet_quality(
    summary: Mapping[str, Any],
    *,
    min_clean_snippets: int = 1,
    require_snippet_claims_quality_pass: bool = False,
    require_context_pack_quality_pass: bool = False,
    require_snippet_claims_answer_status: str | None = None,
    require_context_pack_answer_status: str | None = None,
    require_embedding_dim: int | None = None,
) -> QualityResult:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "value": json_safe(value), "expected": json_safe(expected)})

    clean_count = as_int(summary.get("clean_snippet_claim_count"))
    add("min_clean_snippets", clean_count >= int(min_clean_snippets), clean_count, f">={min_clean_snippets}")
    add("all_clean_snippets_cited", as_int(summary.get("uncited_clean_snippet_count")) == 0, summary.get("uncited_clean_snippet_count"), 0)
    add("all_clean_snippets_have_page_id", as_int(summary.get("missing_page_id_count")) == 0, summary.get("missing_page_id_count"), 0)
    add("all_clean_snippets_have_citation", as_int(summary.get("missing_citation_count")) == 0, summary.get("missing_citation_count"), 0)
    add("all_clean_snippets_have_clean_text", as_int(summary.get("missing_clean_snippet_count")) == 0, summary.get("missing_clean_snippet_count"), 0)
    add("no_trace_net_boilerplate", as_int(summary.get("boilerplate_snippet_count")) == 0, summary.get("boilerplate_snippet_count"), 0)
    add("no_local_path_or_url_leaks", as_int(summary.get("local_path_leak_count")) == 0, summary.get("local_path_leak_count"), 0)
    add("no_raw_bytes_repr", as_int(summary.get("raw_bytes_repr_count")) == 0, summary.get("raw_bytes_repr_count"), 0)
    add("no_forbidden_markers", as_int(summary.get("forbidden_marker_count")) == 0, summary.get("forbidden_marker_count"), 0)
    add("no_retrieval_only_clean_claims", as_int(summary.get("retrieval_only_clean_claim_count")) == 0, summary.get("retrieval_only_clean_claim_count"), 0)
    add("page_profile_clean_claim_count", as_int(summary.get("page_profile_clean_claim_count")) == 0, summary.get("page_profile_clean_claim_count"), 0)
    add("context_helper_clean_claim_count", as_int(summary.get("context_helper_clean_claim_count")) == 0, summary.get("context_helper_clean_claim_count"), 0)
    add("source_evidence_clean_claim_count", as_int(summary.get("source_evidence_clean_claim_count")) == 0, summary.get("source_evidence_clean_claim_count"), 0)
    add("derived_context_clean_claim_count", as_int(summary.get("derived_context_clean_claim_count")) == 0, summary.get("derived_context_clean_claim_count"), 0)
    add("claims_have_authority", as_int(summary.get("claim_without_authority_count")) == 0, summary.get("claim_without_authority_count"), 0)
    add("no_direct_answer_claims", as_int(summary.get("direct_answer_allowed_claim_count")) == 0, summary.get("direct_answer_allowed_claim_count"), 0)
    add("no_direct_claim_proof", as_int(summary.get("claim_proof_direct_count")) == 0, summary.get("claim_proof_direct_count"), 0)
    add("no_source_truth_mutation", as_int(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("final_answer_still_blocked", as_int(summary.get("final_answer_allowed_count")) == 0 and as_bool(summary.get("final_answer_allowed"), default=False) is False, {"count": summary.get("final_answer_allowed_count"), "flag": summary.get("final_answer_allowed")}, 0)
    add("llm_freeform_still_blocked", as_int(summary.get("llm_freeform_answer_allowed_count")) == 0 and as_bool(summary.get("llm_freeform_answer_allowed"), default=False) is False, {"count": summary.get("llm_freeform_answer_allowed_count"), "flag": summary.get("llm_freeform_answer_allowed")}, 0)
    add("source_resolution_required", as_int(summary.get("missing_source_resolution_count")) == 0, summary.get("missing_source_resolution_count"), 0)
    add("authority_gate_required", as_int(summary.get("missing_authority_gate_count")) == 0, summary.get("missing_authority_gate_count"), 0)
    add("citation_requirement_required", as_int(summary.get("missing_citation_requirement_count")) == 0, summary.get("missing_citation_requirement_count"), 0)

    if require_snippet_claims_quality_pass:
        add("snippet_claims_quality_status", as_text(summary.get("snippet_claims_quality_status")) == "PASS", summary.get("snippet_claims_quality_status"), "PASS")
    if require_context_pack_quality_pass:
        add("context_pack_quality_status", as_text(summary.get("context_pack_quality_status")) == "PASS", summary.get("context_pack_quality_status"), "PASS")
    if require_snippet_claims_answer_status:
        add("snippet_claims_answer_status", as_text(summary.get("snippet_claims_answer_status")) == require_snippet_claims_answer_status, summary.get("snippet_claims_answer_status"), require_snippet_claims_answer_status)
    if require_context_pack_answer_status:
        add("context_pack_answer_status", as_text(summary.get("context_pack_answer_status")) == require_context_pack_answer_status, summary.get("context_pack_answer_status"), require_context_pack_answer_status)
    if require_embedding_dim is not None:
        add("embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), summary.get("embedding_dim"), require_embedding_dim)

    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Evidence Snippet Cleaner v1",
        "",
        f"Status: **{html.escape(as_text(report.get('status')))}**",
        f"Quality: **{html.escape(as_text(report.get('quality_status')))}**",
        f"Query: `{html.escape(as_text(report.get('query')))}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "clean_snippet_claim_count",
        "blocked_clean_snippet_count",
        "boilerplate_snippet_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "forbidden_marker_count",
        "final_answer_allowed_count",
    ]:
        lines.append(f"- `{key}`: `{html.escape(as_text(summary.get(key)))}`")
    lines.extend(["", "## Clean snippet claims", ""])
    for claim in report.get("clean_snippet_claims") or []:
        if not isinstance(claim, Mapping):
            continue
        lines.append(f"### Rank {claim.get('clean_snippet_rank')} — {html.escape(as_text(claim.get('page_id')))}")
        lines.append("")
        lines.append(f"Bucket: `{html.escape(as_text(claim.get('rag_bucket')))}`  ")
        lines.append(f"Authority: `{html.escape(as_text(claim.get('authority')))}`  ")
        lines.append(f"Citations: `{html.escape(', '.join(citation_ids_from(claim)))}`")
        lines.append("")
        lines.append("> " + html.escape(as_text(claim.get("clean_source_snippet"))))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(report: Mapping[str, Any]) -> str:
    markdown = render_markdown(report)
    body = "<br>\n".join(html.escape(line) for line in markdown.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Evidence Snippet Cleaner v1</title></head><body><pre>{body}</pre></body></html>\n"


def build_evidence_snippet_cleaner_report(
    *,
    snippet_claims_path: Path = DEFAULT_SNIPPET_CLAIMS,
    context_pack_path: Path | None = DEFAULT_CONTEXT_PACK,
    embedding_candidates_path: Path | None = DEFAULT_EMBEDDING_CANDIDATES,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_claims: int = 12,
    max_clean_snippet_chars: int = 700,
    min_clean_snippet_chars: int = 20,
    min_clean_snippets: int = 1,
    require_snippet_claims_quality_pass: bool = False,
    require_context_pack_quality_pass: bool = False,
    require_snippet_claims_answer_status: str | None = None,
    require_context_pack_answer_status: str | None = None,
    require_embedding_dim: int | None = None,
    repo_root: Path | None = None,
    allow_local_ocr_read: bool = True,
    write_quality: bool = False,
) -> dict[str, Any]:
    snippet_claims_payload = load_mapping_artifact(Path(snippet_claims_path), name="snippet claims")
    context_pack = load_mapping_artifact(Path(context_pack_path), name="context pack") if context_pack_path and Path(context_pack_path).exists() else {}
    candidate_index = load_embedding_candidate_index(Path(embedding_candidates_path)) if embedding_candidates_path else {}
    repo_root = repo_root or Path.cwd()

    clean_claims, blocked = build_clean_snippets_from_artifacts(
        snippet_claims_payload=snippet_claims_payload,
        embedding_candidate_index=candidate_index,
        max_claims=max_claims,
        max_clean_snippet_chars=max_clean_snippet_chars,
        min_clean_snippet_chars=min_clean_snippet_chars,
        repo_root=repo_root,
        allow_local_ocr_read=allow_local_ocr_read,
    )
    summary = summarize_clean_snippets(
        snippet_claims_payload=snippet_claims_payload,
        context_pack=context_pack,
        clean_claims=clean_claims,
        blocked_records=blocked,
    )
    quality = evaluate_clean_snippet_quality(
        summary,
        min_clean_snippets=min_clean_snippets,
        require_snippet_claims_quality_pass=require_snippet_claims_quality_pass,
        require_context_pack_quality_pass=require_context_pack_quality_pass,
        require_snippet_claims_answer_status=require_snippet_claims_answer_status,
        require_context_pack_answer_status=require_context_pack_answer_status,
        require_embedding_dim=require_embedding_dim,
    )

    output_dir = Path(output_dir)
    report_path = output_dir / DEFAULT_REPORT_FILE
    claims_path = output_dir / DEFAULT_CLAIMS_FILE
    blocked_path = output_dir / DEFAULT_BLOCKED_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    md_path = output_dir / DEFAULT_MD_FILE
    html_path = output_dir / DEFAULT_HTML_FILE

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "CLEAN_SNIPPETS_BUILT",
        "quality_status": quality.status,
        "answer_status": "CLEAN_SNIPPETS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "query": summary.get("query"),
        "created_at": utc_now_iso(),
        "snippet_claims_path": str(snippet_claims_path),
        "context_pack_path": str(context_pack_path or ""),
        "embedding_candidates_path": str(embedding_candidates_path or ""),
        "summary": summary,
        "quality": {"status": quality.status, "checks": quality.checks},
        "clean_snippet_claims": clean_claims,
        "blocked_records": blocked,
        "forbidden_use": list(FORBIDDEN_USE),
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": report["created_at"],
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "report_sha256": sha256_json(report),
        "clean_snippet_claim_count": len(clean_claims),
        "blocked_clean_snippet_count": len(blocked),
        "quality_status": quality.status,
    }

    write_json(report_path, report)
    write_jsonl(claims_path, clean_claims)
    write_jsonl(blocked_path, blocked)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    html_path.write_text(render_html(report), encoding="utf-8", newline="\n")
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "summary": summary, "checks": quality.checks, "quality_path": str(quality_path)})
    report["manifest"] = manifest
    return report


def print_report_summary(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    print("TRACE-Net evidence snippet cleaner v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "query",
        "answer_status",
        "snippet_claims_quality_status",
        "context_pack_quality_status",
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
        "clean_snippet_claim_count",
        "blocked_clean_snippet_count",
        "boilerplate_snippet_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "forbidden_marker_count",
        "retrieval_only_clean_claim_count",
        "claim_without_authority_count",
        "source_truth_mutation_allowed_count",
        "final_answer_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" claims_path: {report.get('claims_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def quality_report_from_path(
    *,
    report_path: Path,
    min_clean_snippets: int = 1,
    require_snippet_claims_quality_pass: bool = False,
    require_context_pack_quality_pass: bool = False,
    require_snippet_claims_answer_status: str | None = None,
    require_context_pack_answer_status: str | None = None,
    require_embedding_dim: int | None = None,
    write_json_quality: bool = False,
) -> dict[str, Any]:
    report = load_mapping_artifact(Path(report_path), name="clean snippet report")
    summary = artifact_summary(report)
    quality = evaluate_clean_snippet_quality(
        summary,
        min_clean_snippets=min_clean_snippets,
        require_snippet_claims_quality_pass=require_snippet_claims_quality_pass,
        require_context_pack_quality_pass=require_context_pack_quality_pass,
        require_snippet_claims_answer_status=require_snippet_claims_answer_status,
        require_context_pack_answer_status=require_context_pack_answer_status,
        require_embedding_dim=require_embedding_dim,
    )
    quality_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": quality.status,
        "summary": summary,
        "checks": quality.checks,
        "report_path": str(report_path),
    }
    if write_json_quality:
        quality_path = Path(report_path).with_name(DEFAULT_QUALITY_FILE)
        quality_payload["quality_path"] = str(quality_path)
        write_json(quality_path, quality_payload)
    return quality_payload


def print_quality_summary(payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    print("TRACE-Net evidence snippet cleaner v1 quality")
    print(f" Status: {payload.get('status')}")
    for key in [
        "clean_snippet_claim_count",
        "blocked_clean_snippet_count",
        "uncited_clean_snippet_count",
        "missing_clean_snippet_count",
        "boilerplate_snippet_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "forbidden_marker_count",
        "retrieval_only_clean_claim_count",
        "page_profile_clean_claim_count",
        "context_helper_clean_claim_count",
        "source_evidence_clean_claim_count",
        "claim_without_authority_count",
        "source_truth_mutation_allowed_count",
        "final_answer_allowed_count",
        "llm_freeform_answer_allowed_count",
        "embedding_dim",
    ]:
        print(f" {key}: {summary.get(key)}")
    if payload.get("quality_path"):
        print(f" quality_path: {payload.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net evidence snippet cleaner v1 artifacts.")
    parser.add_argument("--snippet-claims", type=Path, default=DEFAULT_SNIPPET_CLAIMS)
    parser.add_argument("--context-pack", type=Path, default=DEFAULT_CONTEXT_PACK)
    parser.add_argument("--embedding-candidates", type=Path, default=DEFAULT_EMBEDDING_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-claims", type=int, default=12)
    parser.add_argument("--max-clean-snippet-chars", type=int, default=700)
    parser.add_argument("--min-clean-snippet-chars", type=int, default=20)
    parser.add_argument("--min-clean-snippets", "--min-clean-snippet-claims", dest="min_clean_snippets", type=int, default=1)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--no-local-ocr-read", action="store_true")
    parser.add_argument("--require-snippet-claims-quality-pass", action="store_true")
    parser.add_argument("--require-context-pack-quality-pass", action="store_true")
    parser.add_argument("--require-snippet-claims-answer-status", default=None)
    parser.add_argument("--require-context-pack-answer-status", default=None)
    parser.add_argument("--require-embedding-dim", type=int, default=None)
    parser.add_argument("--quality", action="store_true")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net evidence snippet cleaner v1 quality.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--min-clean-snippets", "--min-clean-snippet-claims", dest="min_clean_snippets", type=int, default=1)
    parser.add_argument("--require-snippet-claims-quality-pass", action="store_true")
    parser.add_argument("--require-context-pack-quality-pass", action="store_true")
    parser.add_argument("--require-snippet-claims-answer-status", default=None)
    parser.add_argument("--require-context-pack-answer-status", default=None)
    parser.add_argument("--require-embedding-dim", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = build_evidence_snippet_cleaner_report(
            snippet_claims_path=args.snippet_claims,
            context_pack_path=args.context_pack,
            embedding_candidates_path=args.embedding_candidates,
            output_dir=args.output_dir,
            max_claims=args.max_claims,
            max_clean_snippet_chars=args.max_clean_snippet_chars,
            min_clean_snippet_chars=args.min_clean_snippet_chars,
            min_clean_snippets=args.min_clean_snippets,
            require_snippet_claims_quality_pass=args.require_snippet_claims_quality_pass,
            require_context_pack_quality_pass=args.require_context_pack_quality_pass,
            require_snippet_claims_answer_status=args.require_snippet_claims_answer_status,
            require_context_pack_answer_status=args.require_context_pack_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            repo_root=args.repo_root,
            allow_local_ocr_read=not args.no_local_ocr_read,
            write_quality=args.quality,
        )
        print_report_summary(report)
        return 0 if report.get("quality_status") == "PASS" else 1
    except Exception as exc:
        print(f"TRACE-Net evidence snippet cleaner failed: {exc}", file=sys.stderr)
        return 2


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        payload = quality_report_from_path(
            report_path=args.report_path,
            min_clean_snippets=args.min_clean_snippets,
            require_snippet_claims_quality_pass=args.require_snippet_claims_quality_pass,
            require_context_pack_quality_pass=args.require_context_pack_quality_pass,
            require_snippet_claims_answer_status=args.require_snippet_claims_answer_status,
            require_context_pack_answer_status=args.require_context_pack_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            write_json_quality=args.write_json,
        )
        print_quality_summary(payload)
        return 0 if payload.get("status") == "PASS" else 1
    except Exception as exc:
        print(f"TRACE-Net evidence snippet cleaner quality check failed: {exc}", file=sys.stderr)
        return 2



# Backwards-compatible names used by Step 11.6 tests and docs.
def clean_source_snippet(raw_snippet: Any, *, max_chars: int = 700) -> str:
    return clean_manual_text(raw_snippet, max_chars=max_chars)


def has_local_path_leak(text: Any) -> bool:
    lowered = as_text(text).lower()
    if any(marker in lowered for marker in ("local_data\\", "local_data/", "rescarta_exports", "c:\\users\\", "/mnt/data/")):
        return True
    if re.search(r"[A-Za-z]:[\\/][^\s\"'<>]+", as_text(text)):
        return True
    if re.search(r"https?://[^\s\"'<>]+", as_text(text), flags=re.IGNORECASE):
        return True
    return False


def has_boilerplate(text: Any) -> bool:
    return any(marker in as_text(text).lower() for marker in BOILERPLATE_PHRASES)


def has_raw_bytes_repr(text: Any) -> bool:
    return looks_like_raw_bytes_repr(as_text(text))


def quality_checks_from_summary(summary: Mapping[str, Any], **kwargs: Any) -> QualityResult:
    if "min_clean_snippet_claims" in kwargs and "min_clean_snippets" not in kwargs:
        kwargs["min_clean_snippets"] = kwargs.pop("min_clean_snippet_claims")
    return evaluate_clean_snippet_quality(summary, **kwargs)


def build_trace_net_evidence_snippet_cleaner(**kwargs: Any) -> dict[str, Any]:
    if "min_clean_snippet_claims" in kwargs and "min_clean_snippets" not in kwargs:
        kwargs["min_clean_snippets"] = kwargs.pop("min_clean_snippet_claims")
    return build_evidence_snippet_cleaner_report(**kwargs)


def check_trace_net_evidence_snippet_cleaner_quality(**kwargs: Any) -> dict[str, Any]:
    if "min_clean_snippet_claims" in kwargs and "min_clean_snippets" not in kwargs:
        kwargs["min_clean_snippets"] = kwargs.pop("min_clean_snippet_claims")
    if "write_json_result" in kwargs and "write_json_quality" not in kwargs:
        kwargs["write_json_quality"] = kwargs.pop("write_json_result")
    return quality_report_from_path(**kwargs)


def build_parser() -> argparse.ArgumentParser:
    return build_arg_parser()


def build_quality_parser() -> argparse.ArgumentParser:
    return build_quality_arg_parser()

if __name__ == "__main__":
    raise SystemExit(main())
