"""TRACE-Net Final Answer Gate v1.

Step 12 consumes Step 11.6 cleaned evidence snippets and produces a guarded,
user-visible answer artifact only when every final claim is sourced, cited,
authority-bearing, and leak-free.

Gemma/Ollama support is intentionally constrained: a local LLM may produce an
advisory composition draft, but the final answer text is built from approved
TRACE-Net claims unless the LLM draft passes strict citation/leak validation.
The gate remains the source of authority.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_final_answer_gate_v1"
DEFAULT_CLEAN_SNIPPETS = Path(
    "local_data/organization/trace_net/evidence_snippet_cleaner/trace_net_evidence_snippet_cleaner_v1.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/final_answer_gate")
DEFAULT_REPORT_FILE = "trace_net_final_answer_gate_v1.json"
DEFAULT_CLAIMS_FILE = "trace_net_final_answer_gate_v1_claims.jsonl"
DEFAULT_BLOCKED_FILE = "trace_net_final_answer_gate_v1_blocked_claims.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_final_answer_gate_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_final_answer_gate_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_final_answer_gate_v1_quality.json"
DEFAULT_MD_FILE = "trace_net_final_answer_gate_v1_answer.md"
DEFAULT_HTML_FILE = "trace_net_final_answer_gate_v1_answer.html"

ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "derived_context",
}
BANNED_FINAL_BUCKETS = RETRIEVAL_ONLY_BUCKETS | {
    "raw_ocr",
    "raw_ocr_unfiltered",
    "raw_visual_text",
    "raw_visual_extraction",
    "raw_table_extraction",
    "table_candidate",
    "table_candidates",
    "feedback_only",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}

FORBIDDEN_MARKERS = [
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "c:\\users\\",
    "source url:",
    "tiff path:",
    "ocr path:",
    "source path:",
    "source text evidence for page",
    "this chunk is source-backed",
    "ocr text: [b",
    "[b'",
    '[b"',
    "prompt:",
    "debug:",
]

PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>]+|(?:^|\s)(?:local_data|rescarta_exports)[\\/][^\s\"'<>]+|[^\s\"'<>]*(?:\\|/)(?:local_data|rescarta_exports)(?:\\|/)[^\s\"'<>]*)",
    flags=re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", flags=re.IGNORECASE)
RAW_BYTES_RE = re.compile(r"\bb(['\"])")

OCR_UNCERTAINTY_NOTE = (
    "This answer is based on cleaned, citation-backed OCR evidence. OCR may contain noise, "
    "so review the cited source pages for exact wording."
)

FINAL_FORBIDDEN_USE = [
    "uncited_final_claim",
    "final_claim_without_authority",
    "final_claim_from_retrieval_only_record",
    "final_claim_from_page_retrieval_profile",
    "final_claim_from_context_retrieval_helper",
    "final_claim_from_source_evidence_locator",
    "final_claim_from_raw_ocr_or_visual_extraction",
    "final_answer_contains_local_path",
    "final_answer_contains_raw_bytes_repr",
    "source_truth_mutation",
    "trust_tier_override",
    "citation_replacement",
    "llm_freeform_claim_without_gate",
]


class FinalAnswerGateError(RuntimeError):
    """Raised when final-answer gate artifacts cannot be built safely."""


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


def sha256_text(text: Any) -> str:
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


def page_number_from(page_id: str, page_number: Any = None) -> str:
    if page_number not in (None, ""):
        return as_text(page_number)
    tail = as_text(page_id).rsplit("p", 1)[-1]
    if tail.isdigit():
        return str(int(tail))
    return ""


def page_label(page_id: str, page_number: Any = None) -> str:
    number = page_number_from(page_id, page_number)
    if number:
        return f"page {number} ({page_id})"
    return as_text(page_id) or "an unresolved page"


def contains_forbidden_text(value: Any) -> bool:
    text = as_text(value)
    lower = text.lower()
    if PATH_RE.search(text) or URL_RE.search(text) or RAW_BYTES_RE.search(text):
        return True
    return any(marker in lower for marker in FORBIDDEN_MARKERS)


def forbidden_markers(value: Any) -> list[str]:
    text = as_text(value)
    lower = text.lower()
    markers = [marker for marker in FORBIDDEN_MARKERS if marker in lower]
    if PATH_RE.search(text):
        markers.append("local_or_rescarta_path")
    if URL_RE.search(text):
        markers.append("url")
    if RAW_BYTES_RE.search(text):
        markers.append("raw_bytes_repr")
    return sorted(set(markers))


def load_clean_snippets(path: Path) -> dict[str, Any]:
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        raise FinalAnswerGateError(f"clean snippet report is not a JSON object: {path}")
    return dict(payload)


def clean_claims_from(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("clean_snippet_claims") or payload.get("claims") or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def final_claim_block_reasons(claim: Mapping[str, Any]) -> list[str]:
    bucket = record_bucket(claim)
    reasons: list[str] = []
    if bucket not in ANSWER_SUPPORT_BUCKETS:
        reasons.append("bucket_not_allowed_for_final_answer")
    if bucket in BANNED_FINAL_BUCKETS:
        reasons.append(f"banned_final_bucket:{bucket}")
    if not as_text(claim.get("page_id")):
        reasons.append("missing_page_id")
    if not citation_ids_from(claim):
        reasons.append("missing_citation")
    if not as_text(claim.get("authority")):
        reasons.append("missing_authority")
    if not as_bool(claim.get("requires_source_resolution"), default=True):
        reasons.append("source_resolution_not_required")
    if not as_bool(claim.get("requires_citation"), default=True):
        reasons.append("citation_not_required")
    if not as_bool(claim.get("requires_authority_gate"), default=True):
        reasons.append("authority_gate_not_required")
    if as_bool(claim.get("can_mutate_source_truth"), default=False) or as_bool(claim.get("source_truth_mutation_allowed"), default=False):
        reasons.append("source_truth_mutation_allowed")
    if as_bool(claim.get("llm_freeform_answer_allowed"), default=False):
        reasons.append("llm_freeform_answer_allowed")
    if as_bool(claim.get("retrieval_only_source_used_as_claim"), default=False):
        reasons.append("retrieval_only_source_used_as_claim")
    snippet = as_text(claim.get("clean_source_snippet"))
    if not snippet:
        reasons.append("missing_clean_source_snippet")
    if contains_forbidden_text(snippet):
        reasons.append("clean_source_snippet_contains_forbidden_text")
    if contains_forbidden_text(claim.get("clean_materialized_claim_text")):
        reasons.append("claim_text_contains_forbidden_text")
    return sorted(set(reasons))


def build_final_claim(claim: Mapping[str, Any], *, rank: int, max_snippet_chars: int = 420) -> dict[str, Any]:
    page_id = as_text(claim.get("page_id"))
    page_number = claim.get("page_number")
    bucket = record_bucket(claim)
    snippet = compact_text(claim.get("clean_source_snippet"), max_chars=max_snippet_chars)
    citation_ids = citation_ids_from(claim)
    if bucket == "verified_part_evidence":
        claim_type = "verified_part_evidence_summary"
        text = f"{page_label(page_id, page_number)} contains verified part/page evidence relevant to the query: \"{snippet}\""
    else:
        claim_type = "source_text_evidence_summary"
        text = f"{page_label(page_id, page_number)} contains cleaned source-text evidence relevant to the query: \"{snippet}\""
    return {
        "final_claim_id": stable_id("final_claim", claim.get("clean_snippet_claim_id"), page_id, citation_ids[0] if citation_ids else "", snippet),
        "schema_version": SCHEMA_VERSION,
        "final_claim_status": "FINAL_CLAIM_APPROVED_BY_GATE",
        "claim_rank": rank,
        "claim_type": claim_type,
        "query": as_text(claim.get("query")),
        "final_claim_text": text,
        "page_id": page_id,
        "page_number": page_number,
        "document_id": as_text(claim.get("document_id")),
        "ata_code": as_text(claim.get("ata_code")),
        "rag_bucket": bucket,
        "authority": as_text(claim.get("authority")),
        "trust_tier": as_text(claim.get("trust_tier")),
        "citation_ids": citation_ids,
        "citation_id": citation_ids[0] if citation_ids else "",
        "clean_source_snippet": snippet,
        "clean_source_snippet_sha256": sha256_text(claim.get("clean_source_snippet")),
        "source_clean_snippet_claim_id": as_text(claim.get("clean_snippet_claim_id")),
        "source_snippet_claim_id": as_text(claim.get("source_snippet_claim_id")),
        "draft_claim_id": as_text(claim.get("draft_claim_id")),
        "context_record_id": as_text(claim.get("context_record_id")),
        "embedding_candidate_id": as_text(claim.get("embedding_candidate_id")),
        "source_candidate_id": as_text(claim.get("source_candidate_id")),
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "source_truth_mutation_allowed": False,
        "can_mutate_source_truth": False,
        "retrieval_only_source_used_as_claim": False,
        "llm_freeform_answer_allowed": False,
        "final_answer_gate_approved": True,
        "final_answer_claim_allowed": True,
        "final_answer_allowed": True,
        "forbidden_use": list(FINAL_FORBIDDEN_USE),
        "unsafe_reasons": [],
    }


def build_blocked_final_claim(claim: Mapping[str, Any], *, reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "blocked_final_claim_id": stable_id("blocked_final_claim", claim.get("clean_snippet_claim_id"), claim.get("page_id"), reasons),
        "schema_version": SCHEMA_VERSION,
        "blocked_from_final_answer": True,
        "block_reasons": sorted(set(as_text(reason) for reason in reasons if as_text(reason))),
        "clean_snippet_claim_id": as_text(claim.get("clean_snippet_claim_id")),
        "page_id": as_text(claim.get("page_id")),
        "rag_bucket": record_bucket(claim),
        "authority": as_text(claim.get("authority")),
        "citation_ids": citation_ids_from(claim),
        "clean_source_snippet_preview": compact_text(claim.get("clean_source_snippet"), max_chars=240),
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
    }


def approve_final_claims(clean_claims: Sequence[Mapping[str, Any]], *, max_final_claims: int = 8, max_claims_per_page: int = 2, max_snippet_chars: int = 420) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    per_page: Counter[str] = Counter()
    seen: set[str] = set()
    for claim in clean_claims:
        reasons = final_claim_block_reasons(claim)
        page_id = as_text(claim.get("page_id"))
        citation_ids = citation_ids_from(claim)
        key = "|".join([page_id, record_bucket(claim), citation_ids[0] if citation_ids else "", sha256_text(claim.get("clean_source_snippet"))[:16]])
        if key in seen:
            continue
        if reasons:
            blocked.append(build_blocked_final_claim(claim, reasons=reasons))
            continue
        if page_id and per_page[page_id] >= int(max_claims_per_page):
            blocked.append(build_blocked_final_claim(claim, reasons=["max_claims_per_page_exceeded"]))
            continue
        approved.append(build_final_claim(claim, rank=len(approved) + 1, max_snippet_chars=max_snippet_chars))
        per_page[page_id] += 1
        seen.add(key)
        if len(approved) >= int(max_final_claims):
            break
    return approved, blocked


def page_sort_key(value: str) -> tuple[int, str]:
    tail = as_text(value).rsplit("p", 1)[-1]
    return (int(tail) if tail.isdigit() else 10**9, as_text(value))


def build_template_final_answer(
    *,
    query: str,
    final_claims: Sequence[Mapping[str, Any]],
    max_answer_claims: int = 6,
    include_ocr_note: bool = True,
) -> str:
    if not final_claims:
        return "TRACE-Net did not authorize a final answer because no cleaned, cited evidence claims passed the final gate."
    page_ids = sorted({as_text(claim.get("page_id")) for claim in final_claims if as_text(claim.get("page_id"))}, key=page_sort_key)
    page_labels = ", ".join(page_label(pid) for pid in page_ids[:8])
    lines = [
        f"TRACE-Net final gated answer for: {query}",
        "",
        f"The final gate authorized citation-backed evidence from {len(page_ids)} page(s): {page_labels}.",
        "",
        "Cited evidence:",
    ]
    for claim in list(final_claims)[: int(max_answer_claims)]:
        citations = ", ".join(citation_ids_from(claim))
        snippet = compact_text(claim.get("clean_source_snippet"), max_chars=260)
        bucket = as_text(claim.get("rag_bucket"))
        authority = as_text(claim.get("authority"))
        lines.append(f"- {page_label(as_text(claim.get('page_id')), claim.get('page_number'))}: {snippet} [{citations}] ({bucket}; {authority})")
    if include_ocr_note:
        lines.extend(["", f"OCR/source note: {OCR_UNCERTAINTY_NOTE}"])
    lines.extend(["", "TRACE-Net gate: no retrieval-only records, uncited claims, local paths, raw byte wrappers, or source-truth mutations were allowed into this answer."])
    return "\n".join(lines).strip() + "\n"


def build_ollama_prompt(query: str, final_claims: Sequence[Mapping[str, Any]], *, max_answer_claims: int = 6) -> str:
    rows = []
    for claim in list(final_claims)[: int(max_answer_claims)]:
        rows.append(
            {
                "page_id": claim.get("page_id"),
                "page_number": claim.get("page_number"),
                "citation_ids": citation_ids_from(claim),
                "authority": claim.get("authority"),
                "bucket": claim.get("rag_bucket"),
                "snippet": compact_text(claim.get("clean_source_snippet"), max_chars=320),
            }
        )
    return (
        "You are assisting TRACE-Net with a constrained final-answer draft.\n"
        "Use only the evidence JSON below. Do not invent facts. Every factual sentence must include one of the citation IDs exactly as written.\n"
        "Do not include local paths, OCR paths, source URLs, or internal TRACE-Net metadata except citation IDs.\n"
        "Mention that OCR may contain noise and that cited pages should be reviewed for exact wording.\n\n"
        f"Query: {query}\n"
        f"Evidence JSON:\n{json.dumps(rows, ensure_ascii=False, indent=2)}\n\n"
        "Write a concise answer."
    )


def call_ollama_generate(*, ollama_url: str, endpoint: str, model: str, prompt: str, timeout: float = 180.0) -> tuple[str, dict[str, Any]]:
    url = as_text(ollama_url).rstrip("/") + endpoint
    payload = {"model": model, "prompt": prompt, "stream": False}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=float(timeout)) as response:  # nosec B310 - local user-provided Ollama URL only.
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return as_text(parsed.get("response") or parsed.get("message", {}).get("content")), parsed


def validate_llm_candidate_answer(text: str, final_claims: Sequence[Mapping[str, Any]], *, require_all_citations: bool = False) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not as_text(text):
        reasons.append("empty_llm_candidate_answer")
    if contains_forbidden_text(text):
        reasons.append("llm_candidate_contains_forbidden_text")
    if "ocr" not in as_text(text).lower():
        reasons.append("llm_candidate_missing_ocr_uncertainty_note")
    required_citations = sorted({cid for claim in final_claims for cid in citation_ids_from(claim)})
    present = [cid for cid in required_citations if cid in text]
    if require_all_citations and len(present) != len(required_citations):
        reasons.append("llm_candidate_missing_required_citations")
    if not require_all_citations and required_citations and not present:
        reasons.append("llm_candidate_missing_any_trace_net_citation")
    return not reasons, sorted(set(reasons))


def maybe_build_llm_draft(
    *,
    composer_mode: str,
    query: str,
    final_claims: Sequence[Mapping[str, Any]],
    llm_model: str,
    ollama_url: str,
    ollama_endpoint: str,
    ollama_timeout: float,
    max_answer_claims: int,
    allow_llm_final_text: bool,
) -> dict[str, Any]:
    mode = as_text(composer_mode) or "template"
    if mode == "template":
        return {
            "composer_mode": mode,
            "llm_assisted_composition_used": False,
            "llm_model_name": "",
            "llm_candidate_answer": "",
            "llm_candidate_answer_allowed_for_final": False,
            "llm_candidate_rejected_reasons": [],
            "llm_prompt_sha256": "",
            "llm_error": "",
        }
    prompt = build_ollama_prompt(query, final_claims, max_answer_claims=max_answer_claims)
    try:
        draft, raw = call_ollama_generate(
            ollama_url=ollama_url,
            endpoint=ollama_endpoint,
            model=llm_model,
            prompt=prompt,
            timeout=ollama_timeout,
        )
        ok, reasons = validate_llm_candidate_answer(draft, final_claims, require_all_citations=False)
        return {
            "composer_mode": mode,
            "llm_assisted_composition_used": True,
            "llm_model_name": llm_model,
            "llm_candidate_answer": draft,
            "llm_candidate_answer_sha256": sha256_text(draft),
            "llm_candidate_answer_allowed_for_final": bool(ok and allow_llm_final_text),
            "llm_candidate_rejected_reasons": [] if ok else reasons,
            "llm_prompt_sha256": sha256_text(prompt),
            "llm_raw_response_keys": sorted(str(k) for k in raw.keys()) if isinstance(raw, Mapping) else [],
            "llm_error": "",
        }
    except Exception as exc:
        return {
            "composer_mode": mode,
            "llm_assisted_composition_used": False,
            "llm_model_name": llm_model,
            "llm_candidate_answer": "",
            "llm_candidate_answer_allowed_for_final": False,
            "llm_candidate_rejected_reasons": ["llm_call_failed"],
            "llm_prompt_sha256": sha256_text(prompt),
            "llm_error": f"{type(exc).__name__}: {exc}",
        }


def summarize_final_answer_gate(
    *,
    clean_snippet_payload: Mapping[str, Any],
    final_claims: Sequence[Mapping[str, Any]],
    blocked_claims: Sequence[Mapping[str, Any]],
    final_answer_text: str,
    composer_info: Mapping[str, Any],
) -> dict[str, Any]:
    clean_summary = artifact_summary(clean_snippet_payload)
    bucket_counts = Counter(record_bucket(claim) for claim in final_claims)
    authority_counts = Counter(as_text(claim.get("authority")) for claim in final_claims)
    page_ids = sorted({as_text(claim.get("page_id")) for claim in final_claims if as_text(claim.get("page_id"))}, key=page_sort_key)
    citation_ids = sorted({cid for claim in final_claims for cid in citation_ids_from(claim)})

    final_claim_count = len(final_claims)
    cited_final_claim_count = sum(1 for claim in final_claims if citation_ids_from(claim))
    uncited_final_claim_count = final_claim_count - cited_final_claim_count
    missing_page_id_count = sum(1 for claim in final_claims if not as_text(claim.get("page_id")))
    missing_citation_count = sum(1 for claim in final_claims if not citation_ids_from(claim))
    missing_authority_count = sum(1 for claim in final_claims if not as_text(claim.get("authority")))
    retrieval_only_final_claim_count = sum(1 for claim in final_claims if record_bucket(claim) in RETRIEVAL_ONLY_BUCKETS)
    page_profile_final_claim_count = sum(1 for claim in final_claims if record_bucket(claim) == "page_retrieval_profile")
    context_helper_final_claim_count = sum(1 for claim in final_claims if record_bucket(claim) == "context_retrieval_helper")
    source_evidence_final_claim_count = sum(1 for claim in final_claims if record_bucket(claim) == "source_evidence")
    raw_or_visual_final_claim_count = sum(1 for claim in final_claims if record_bucket(claim) in BANNED_FINAL_BUCKETS - RETRIEVAL_ONLY_BUCKETS)
    source_truth_mutation_allowed_count = sum(
        1
        for claim in final_claims
        if as_bool(claim.get("can_mutate_source_truth"), default=False) or as_bool(claim.get("source_truth_mutation_allowed"), default=False)
    )
    llm_freeform_answer_allowed_count = sum(1 for claim in final_claims if as_bool(claim.get("llm_freeform_answer_allowed"), default=False))
    local_path_leak_count = int(contains_forbidden_text(final_answer_text) or any(contains_forbidden_text(claim.get("final_claim_text")) for claim in final_claims))
    raw_bytes_repr_count = int(RAW_BYTES_RE.search(final_answer_text) is not None)
    boilerplate_leak_count = int(any(marker in final_answer_text.lower() for marker in ["source text evidence for page", "this chunk is source-backed", "tiff path:", "ocr path:"]))
    ocr_uncertainty_note_present = "ocr" in final_answer_text.lower() and "review" in final_answer_text.lower()

    final_answer_allowed = (
        final_claim_count > 0
        and uncited_final_claim_count == 0
        and missing_page_id_count == 0
        and missing_citation_count == 0
        and missing_authority_count == 0
        and retrieval_only_final_claim_count == 0
        and source_truth_mutation_allowed_count == 0
        and local_path_leak_count == 0
        and raw_bytes_repr_count == 0
        and boilerplate_leak_count == 0
        and ocr_uncertainty_note_present
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "answer_status": "FINAL_ANSWER_GATE_APPROVED" if final_answer_allowed else "FINAL_ANSWER_GATE_BLOCKED",
        "final_answer_allowed": bool(final_answer_allowed),
        "query": as_text(clean_summary.get("query") or clean_snippet_payload.get("query")),
        "clean_snippet_quality_status": artifact_quality_status(clean_snippet_payload),
        "clean_snippet_answer_status": as_text(clean_snippet_payload.get("answer_status") or clean_summary.get("answer_status")),
        "embedding_mode": as_text(clean_summary.get("embedding_mode") or clean_snippet_payload.get("embedding_mode")),
        "embedding_model_name": as_text(clean_summary.get("embedding_model_name") or clean_snippet_payload.get("embedding_model_name")),
        "embedding_dim": as_int(clean_summary.get("embedding_dim") or clean_snippet_payload.get("embedding_dim")),
        "composer_mode": as_text(composer_info.get("composer_mode")),
        "llm_assisted_composition_used": as_bool(composer_info.get("llm_assisted_composition_used"), default=False),
        "llm_model_name": as_text(composer_info.get("llm_model_name")),
        "llm_candidate_answer_allowed_for_final": as_bool(composer_info.get("llm_candidate_answer_allowed_for_final"), default=False),
        "llm_candidate_rejected_reason_count": len(composer_info.get("llm_candidate_rejected_reasons") or []),
        "llm_error_present": bool(as_text(composer_info.get("llm_error"))),
        "final_claim_count": final_claim_count,
        "cited_final_claim_count": cited_final_claim_count,
        "uncited_final_claim_count": uncited_final_claim_count,
        "blocked_final_claim_count": len(blocked_claims),
        "missing_page_id_count": missing_page_id_count,
        "missing_citation_count": missing_citation_count,
        "missing_authority_count": missing_authority_count,
        "retrieval_only_final_claim_count": retrieval_only_final_claim_count,
        "page_profile_final_claim_count": page_profile_final_claim_count,
        "context_helper_final_claim_count": context_helper_final_claim_count,
        "source_evidence_final_claim_count": source_evidence_final_claim_count,
        "raw_or_visual_final_claim_count": raw_or_visual_final_claim_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "llm_freeform_answer_allowed_count": llm_freeform_answer_allowed_count,
        "local_path_leak_count": local_path_leak_count,
        "raw_bytes_repr_count": raw_bytes_repr_count,
        "boilerplate_leak_count": boilerplate_leak_count,
        "ocr_uncertainty_note_present": bool(ocr_uncertainty_note_present),
        "final_answer_char_count": len(final_answer_text),
        "page_count": len(page_ids),
        "page_ids": page_ids,
        "top_page_id": page_ids[0] if page_ids else "",
        "citation_count": len(citation_ids),
        "citation_ids": citation_ids,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "clean_snippet_claim_count": as_int(clean_summary.get("clean_snippet_claim_count")),
        "clean_snippet_blocked_count": as_int(clean_summary.get("blocked_clean_snippet_count") or clean_summary.get("blocked_record_count")),
        "clean_snippet_local_path_leak_count": as_int(clean_summary.get("local_path_leak_count")),
        "clean_snippet_raw_bytes_repr_count": as_int(clean_summary.get("raw_bytes_repr_count")),
    }


def quality_checks_for_summary(
    summary: Mapping[str, Any],
    *,
    min_final_claims: int = 1,
    require_clean_snippet_quality_pass: bool = False,
    require_clean_snippet_answer_status: str = "",
    require_embedding_dim: int | None = None,
    require_final_answer_allowed: bool = False,
    allow_llm_error: bool = True,
) -> QualityResult:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected})

    final_claim_count = as_int(summary.get("final_claim_count"))
    final_answer_allowed = as_bool(summary.get("final_answer_allowed"), default=False)
    add("min_final_claims", final_claim_count >= int(min_final_claims), final_claim_count, f">= {min_final_claims}")
    add("all_final_claims_cited", as_int(summary.get("uncited_final_claim_count")) == 0, summary.get("uncited_final_claim_count"), 0)
    add("no_missing_page_ids", as_int(summary.get("missing_page_id_count")) == 0, summary.get("missing_page_id_count"), 0)
    add("no_missing_citations", as_int(summary.get("missing_citation_count")) == 0, summary.get("missing_citation_count"), 0)
    add("no_missing_authority", as_int(summary.get("missing_authority_count")) == 0, summary.get("missing_authority_count"), 0)
    add("no_retrieval_only_final_claims", as_int(summary.get("retrieval_only_final_claim_count")) == 0, summary.get("retrieval_only_final_claim_count"), 0)
    add("no_page_profile_final_claims", as_int(summary.get("page_profile_final_claim_count")) == 0, summary.get("page_profile_final_claim_count"), 0)
    add("no_context_helper_final_claims", as_int(summary.get("context_helper_final_claim_count")) == 0, summary.get("context_helper_final_claim_count"), 0)
    add("no_source_evidence_locator_final_claims", as_int(summary.get("source_evidence_final_claim_count")) == 0, summary.get("source_evidence_final_claim_count"), 0)
    add("no_raw_or_visual_final_claims", as_int(summary.get("raw_or_visual_final_claim_count")) == 0, summary.get("raw_or_visual_final_claim_count"), 0)
    add("no_source_truth_mutation", as_int(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("no_llm_freeform_claims", as_int(summary.get("llm_freeform_answer_allowed_count")) == 0, summary.get("llm_freeform_answer_allowed_count"), 0)
    add("no_local_path_leaks", as_int(summary.get("local_path_leak_count")) == 0, summary.get("local_path_leak_count"), 0)
    add("no_raw_bytes_repr", as_int(summary.get("raw_bytes_repr_count")) == 0, summary.get("raw_bytes_repr_count"), 0)
    add("no_boilerplate_leak", as_int(summary.get("boilerplate_leak_count")) == 0, summary.get("boilerplate_leak_count"), 0)
    add("ocr_uncertainty_note_present", as_bool(summary.get("ocr_uncertainty_note_present"), default=False), summary.get("ocr_uncertainty_note_present"), True)
    if require_clean_snippet_quality_pass:
        add("clean_snippet_quality_pass", summary.get("clean_snippet_quality_status") == "PASS", summary.get("clean_snippet_quality_status"), "PASS")
    if require_clean_snippet_answer_status:
        add(
            "clean_snippet_answer_status",
            summary.get("clean_snippet_answer_status") == require_clean_snippet_answer_status,
            summary.get("clean_snippet_answer_status"),
            require_clean_snippet_answer_status,
        )
    if require_embedding_dim is not None:
        add("embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), summary.get("embedding_dim"), int(require_embedding_dim))
    if require_final_answer_allowed:
        add("final_answer_allowed", final_answer_allowed, final_answer_allowed, True)
    if not allow_llm_error:
        add("no_llm_error", not as_bool(summary.get("llm_error_present"), default=False), summary.get("llm_error_present"), False)

    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def build_markdown_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Final Answer Gate v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Answer status:** {report.get('answer_status')}",
        f"**Final answer allowed:** {report.get('final_answer_allowed')}",
        "",
        "## Summary",
        "",
        f"- Query: {summary.get('query', '')}",
        f"- Final claims: {summary.get('final_claim_count', 0)}",
        f"- Citations: {summary.get('citation_count', 0)}",
        f"- Pages: {', '.join(summary.get('page_ids') or [])}",
        f"- Composer mode: {summary.get('composer_mode', '')}",
        f"- LLM model: {summary.get('llm_model_name', '')}",
        "",
        "## Final gated answer",
        "",
        as_text(report.get("final_answer_text")),
    ]
    if as_text(report.get("llm_candidate_answer")):
        lines.extend([
            "",
            "## LLM candidate draft, advisory only",
            "",
            as_text(report.get("llm_candidate_answer")),
        ])
    return "\n".join(lines).strip() + "\n"


def build_html_report(report: Mapping[str, Any]) -> str:
    markdown = build_markdown_report(report)
    body = "<br/>\n".join(html.escape(line) for line in markdown.splitlines())
    return "<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>TRACE-Net Final Answer Gate v1</title></head><body>\n" + body + "\n</body></html>\n"


def build_final_answer_gate_report(
    *,
    clean_snippet_payload: Mapping[str, Any],
    max_final_claims: int = 8,
    max_claims_per_page: int = 2,
    max_answer_claims: int = 6,
    max_snippet_chars: int = 420,
    composer_mode: str = "template",
    llm_model: str = "gemma4:26b",
    ollama_url: str = "http://localhost:11434",
    ollama_endpoint: str = "/api/generate",
    ollama_timeout: float = 180.0,
    allow_llm_final_text: bool = False,
    min_final_claims: int = 1,
    require_clean_snippet_quality_pass: bool = False,
    require_clean_snippet_answer_status: str = "",
    require_embedding_dim: int | None = None,
    require_final_answer_allowed: bool = False,
    allow_llm_error: bool = True,
) -> dict[str, Any]:
    clean_claims = clean_claims_from(clean_snippet_payload)
    final_claims, blocked_claims = approve_final_claims(
        clean_claims,
        max_final_claims=max_final_claims,
        max_claims_per_page=max_claims_per_page,
        max_snippet_chars=max_snippet_chars,
    )
    query = as_text(artifact_summary(clean_snippet_payload).get("query") or clean_snippet_payload.get("query"))
    template_answer = build_template_final_answer(
        query=query,
        final_claims=final_claims,
        max_answer_claims=max_answer_claims,
        include_ocr_note=True,
    )
    composer_info = maybe_build_llm_draft(
        composer_mode=composer_mode,
        query=query,
        final_claims=final_claims,
        llm_model=llm_model,
        ollama_url=ollama_url,
        ollama_endpoint=ollama_endpoint,
        ollama_timeout=ollama_timeout,
        max_answer_claims=max_answer_claims,
        allow_llm_final_text=allow_llm_final_text,
    )
    llm_answer = as_text(composer_info.get("llm_candidate_answer"))
    use_llm_final = as_bool(composer_info.get("llm_candidate_answer_allowed_for_final"), default=False)
    final_answer_text = llm_answer if use_llm_final else template_answer
    summary = summarize_final_answer_gate(
        clean_snippet_payload=clean_snippet_payload,
        final_claims=final_claims,
        blocked_claims=blocked_claims,
        final_answer_text=final_answer_text,
        composer_info=composer_info,
    )
    quality = quality_checks_for_summary(
        summary,
        min_final_claims=min_final_claims,
        require_clean_snippet_quality_pass=require_clean_snippet_quality_pass,
        require_clean_snippet_answer_status=require_clean_snippet_answer_status,
        require_embedding_dim=require_embedding_dim,
        require_final_answer_allowed=require_final_answer_allowed,
        allow_llm_error=allow_llm_error,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "FINAL_ANSWER_GATE_RAN",
        "quality_status": quality.status,
        "answer_status": summary["answer_status"],
        "final_answer_allowed": summary["final_answer_allowed"],
        "final_answer_text": final_answer_text,
        "template_final_answer_text": template_answer,
        "llm_candidate_answer": llm_answer,
        "llm_candidate_answer_allowed_for_final": composer_info.get("llm_candidate_answer_allowed_for_final", False),
        "llm_candidate_rejected_reasons": composer_info.get("llm_candidate_rejected_reasons", []),
        "llm_error": composer_info.get("llm_error", ""),
        "summary": summary,
        "quality": {"status": quality.status, "checks": quality.checks},
        "final_claims": list(final_claims),
        "blocked_final_claims": list(blocked_claims),
        "created_at": utc_now_iso(),
    }
    return report


def write_final_answer_gate_outputs(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    report_path = output_dir / DEFAULT_REPORT_FILE
    claims_path = output_dir / DEFAULT_CLAIMS_FILE
    blocked_path = output_dir / DEFAULT_BLOCKED_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    md_path = output_dir / DEFAULT_MD_FILE
    html_path = output_dir / DEFAULT_HTML_FILE
    write_json(report_path, report)
    write_jsonl(claims_path, report.get("final_claims") or [])
    write_jsonl(blocked_path, report.get("blocked_final_claims") or [])
    write_json(summary_path, report.get("summary") or {})
    write_json(quality_path, report.get("quality") or {})
    md_path.write_text(build_markdown_report(report), encoding="utf-8", newline="\n")
    html_path.write_text(build_html_report(report), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "report_sha256": sha256_json(report),
        "final_answer_text_sha256": sha256_text(report.get("final_answer_text")),
        "quality_status": report.get("quality_status"),
        "final_answer_allowed": report.get("final_answer_allowed"),
    }
    write_json(manifest_path, manifest)
    return {
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }


def run_final_answer_gate(**kwargs: Any) -> dict[str, Any]:
    clean_snippets_path = Path(kwargs.get("clean_snippets_path") or DEFAULT_CLEAN_SNIPPETS)
    output_dir = Path(kwargs.get("output_dir") or DEFAULT_OUTPUT_DIR)
    payload = load_clean_snippets(clean_snippets_path)
    report = build_final_answer_gate_report(
        clean_snippet_payload=payload,
        max_final_claims=as_int(kwargs.get("max_final_claims"), default=8),
        max_claims_per_page=as_int(kwargs.get("max_claims_per_page"), default=2),
        max_answer_claims=as_int(kwargs.get("max_answer_claims"), default=6),
        max_snippet_chars=as_int(kwargs.get("max_snippet_chars"), default=420),
        composer_mode=as_text(kwargs.get("composer_mode") or "template"),
        llm_model=as_text(kwargs.get("llm_model") or "gemma4:26b"),
        ollama_url=as_text(kwargs.get("ollama_url") or "http://localhost:11434"),
        ollama_endpoint=as_text(kwargs.get("ollama_endpoint") or "/api/generate"),
        ollama_timeout=float(kwargs.get("ollama_timeout") or 180.0),
        allow_llm_final_text=as_bool(kwargs.get("allow_llm_final_text"), default=False),
        min_final_claims=as_int(kwargs.get("min_final_claims"), default=1),
        require_clean_snippet_quality_pass=as_bool(kwargs.get("require_clean_snippet_quality_pass"), default=False),
        require_clean_snippet_answer_status=as_text(kwargs.get("require_clean_snippet_answer_status")),
        require_embedding_dim=as_int(kwargs.get("require_embedding_dim"), default=0) or None,
        require_final_answer_allowed=as_bool(kwargs.get("require_final_answer_allowed"), default=False),
        allow_llm_error=as_bool(kwargs.get("allow_llm_error"), default=True),
    )
    paths = write_final_answer_gate_outputs(report, output_dir)
    report.update(paths)
    # Rewrite with embedded paths.
    write_json(Path(paths["report_path"]), report)
    write_json(Path(paths["summary_path"]), report.get("summary") or {})
    write_json(Path(paths["quality_path"]), report.get("quality") or {})
    return report


def check_final_answer_gate_quality(
    *,
    report_path: Path,
    min_final_claims: int = 1,
    require_clean_snippet_quality_pass: bool = False,
    require_clean_snippet_answer_status: str = "",
    require_embedding_dim: int | None = None,
    require_final_answer_allowed: bool = False,
    allow_llm_error: bool = True,
    write_json_quality: bool = False,
) -> dict[str, Any]:
    report = read_json(Path(report_path))
    if not isinstance(report, Mapping):
        raise FinalAnswerGateError(f"final answer gate report is not a JSON object: {report_path}")
    summary = dict(report.get("summary") or {}) if isinstance(report.get("summary"), Mapping) else {}
    if not summary:
        summary = summarize_final_answer_gate(
            clean_snippet_payload={},
            final_claims=report.get("final_claims") or [],
            blocked_claims=report.get("blocked_final_claims") or [],
            final_answer_text=as_text(report.get("final_answer_text")),
            composer_info={"composer_mode": report.get("composer_mode", "template")},
        )
    quality = quality_checks_for_summary(
        summary,
        min_final_claims=min_final_claims,
        require_clean_snippet_quality_pass=require_clean_snippet_quality_pass,
        require_clean_snippet_answer_status=require_clean_snippet_answer_status,
        require_embedding_dim=require_embedding_dim,
        require_final_answer_allowed=require_final_answer_allowed,
        allow_llm_error=allow_llm_error,
    )
    quality_payload = {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary, "created_at": utc_now_iso()}
    if write_json_quality:
        quality_path = Path(report_path).with_name(DEFAULT_QUALITY_FILE)
        write_json(quality_path, quality_payload)
        quality_payload["quality_path"] = str(quality_path)
    return quality_payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net final answer gate v1 artifact.")
    parser.add_argument("--clean-snippets", dest="clean_snippets_path", type=Path, default=DEFAULT_CLEAN_SNIPPETS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-final-claims", type=int, default=8)
    parser.add_argument("--max-claims-per-page", type=int, default=2)
    parser.add_argument("--max-answer-claims", type=int, default=6)
    parser.add_argument("--max-snippet-chars", type=int, default=420)
    parser.add_argument("--composer-mode", choices=["template", "ollama"], default="template")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-endpoint", default="/api/generate")
    parser.add_argument("--ollama-timeout", type=float, default=180.0)
    parser.add_argument("--allow-llm-final-text", action="store_true")
    parser.add_argument("--min-final-claims", type=int, default=1)
    parser.add_argument("--require-clean-snippet-quality-pass", action="store_true")
    parser.add_argument("--require-clean-snippet-answer-status", default="")
    parser.add_argument("--require-embedding-dim", type=int, default=0)
    parser.add_argument("--require-final-answer-allowed", action="store_true")
    parser.add_argument("--fail-on-llm-error", action="store_true")
    parser.add_argument("--quality", action="store_true", help="Kept for stage compatibility; quality is always written.")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net final answer gate v1 quality.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--min-final-claims", type=int, default=1)
    parser.add_argument("--require-clean-snippet-quality-pass", action="store_true")
    parser.add_argument("--require-clean-snippet-answer-status", default="")
    parser.add_argument("--require-embedding-dim", type=int, default=0)
    parser.add_argument("--require-final-answer-allowed", action="store_true")
    parser.add_argument("--fail-on-llm-error", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def print_run_summary(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    print("TRACE-Net final answer gate v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    print(f" answer_status: {report.get('answer_status')}")
    print(f" final_answer_allowed: {report.get('final_answer_allowed')}")
    for key in [
        "query",
        "clean_snippet_quality_status",
        "clean_snippet_answer_status",
        "composer_mode",
        "llm_model_name",
        "llm_assisted_composition_used",
        "llm_candidate_answer_allowed_for_final",
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
        "final_claim_count",
        "cited_final_claim_count",
        "uncited_final_claim_count",
        "blocked_final_claim_count",
        "retrieval_only_final_claim_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "boilerplate_leak_count",
        "ocr_uncertainty_note_present",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, '')}")
    for key in ["report_path", "markdown_path", "html_path", "quality_path"]:
        if report.get(key):
            print(f" {key}: {report.get(key)}")


def print_quality_summary(quality: Mapping[str, Any]) -> None:
    summary = quality.get("summary") if isinstance(quality.get("summary"), Mapping) else {}
    print("TRACE-Net final answer gate v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in [
        "answer_status",
        "final_answer_allowed",
        "final_claim_count",
        "cited_final_claim_count",
        "uncited_final_claim_count",
        "retrieval_only_final_claim_count",
        "missing_page_id_count",
        "missing_citation_count",
        "missing_authority_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "boilerplate_leak_count",
        "ocr_uncertainty_note_present",
        "source_truth_mutation_allowed_count",
        "llm_freeform_answer_allowed_count",
        "embedding_dim",
    ]:
        print(f" {key}: {summary.get(key, '')}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality.get('quality_path')}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = run_final_answer_gate(
            clean_snippets_path=args.clean_snippets_path,
            output_dir=args.output_dir,
            max_final_claims=args.max_final_claims,
            max_claims_per_page=args.max_claims_per_page,
            max_answer_claims=args.max_answer_claims,
            max_snippet_chars=args.max_snippet_chars,
            composer_mode=args.composer_mode,
            llm_model=args.llm_model,
            ollama_url=args.ollama_url,
            ollama_endpoint=args.ollama_endpoint,
            ollama_timeout=args.ollama_timeout,
            allow_llm_final_text=args.allow_llm_final_text,
            min_final_claims=args.min_final_claims,
            require_clean_snippet_quality_pass=args.require_clean_snippet_quality_pass,
            require_clean_snippet_answer_status=args.require_clean_snippet_answer_status,
            require_embedding_dim=args.require_embedding_dim,
            require_final_answer_allowed=args.require_final_answer_allowed,
            allow_llm_error=not args.fail_on_llm_error,
        )
        print_run_summary(report)
        return 0 if report.get("quality_status") == "PASS" else 1
    except Exception as exc:
        print(f"TRACE-Net final answer gate failed: {exc}", file=sys.stderr)
        return 2


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        quality = check_final_answer_gate_quality(
            report_path=args.report_path,
            min_final_claims=args.min_final_claims,
            require_clean_snippet_quality_pass=args.require_clean_snippet_quality_pass,
            require_clean_snippet_answer_status=args.require_clean_snippet_answer_status,
            require_embedding_dim=args.require_embedding_dim or None,
            require_final_answer_allowed=args.require_final_answer_allowed,
            allow_llm_error=not args.fail_on_llm_error,
            write_json_quality=args.write_json,
        )
        print_quality_summary(quality)
        return 0 if quality.get("status") == "PASS" else 1
    except Exception as exc:
        print(f"TRACE-Net final answer gate quality check failed: {exc}", file=sys.stderr)
        return 2


# Backward-compatible aliases used by wrapper tests in prior stages.
build_trace_net_final_answer_gate = run_final_answer_gate
check_trace_net_final_answer_gate_quality = check_final_answer_gate_quality


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
