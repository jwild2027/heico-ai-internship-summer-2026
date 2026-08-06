"""TRACE-Net Ask Final Gate Flag v1.

Step 13 exposes a passed Step 12 final-answer gate artifact through an ask-facing
command, but only behind an explicit ``--answer-mode final-gate`` flag.

This module does not perform retrieval, vector search, source mutation, trust
mutation, or LLM free-form answering. It reads the Step 12 final-answer gate
report, verifies the gate passed, verifies every final claim remains cited and
safe, and writes ask-style artifacts for a user-visible gated answer.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_ask_final_gate_v1"
DEFAULT_FINAL_ANSWER_REPORT = Path(
    "local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask_final_gate")
DEFAULT_REPORT_FILE = "trace_net_ask_final_gate_v1.json"
DEFAULT_CLAIMS_FILE = "trace_net_ask_final_gate_v1_claims.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_ask_final_gate_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_ask_final_gate_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_ask_final_gate_v1_quality.json"
DEFAULT_MD_FILE = "trace_net_ask_final_gate_v1_answer.md"
DEFAULT_HTML_FILE = "trace_net_ask_final_gate_v1_answer.html"

ANSWER_MODES = {"off", "final-gate"}
RETRIEVAL_MODES = {"off", "hybrid-simulate", "hybrid"}
RETRIEVAL_ONLY_BUCKETS = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "derived_context",
}
ALLOWED_FINAL_BUCKETS = {"source_text_evidence", "verified_part_evidence"}

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


class AskFinalGateError(RuntimeError):
    """Raised when ask final-gate mode cannot safely expose an answer."""


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


def sha256_text(value: Any) -> str:
    return hashlib.sha256(as_text(value).encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_text(value: Any, *, max_chars: int = 600) -> str:
    text = " ".join(as_text(value).replace("\x00", " ").split())
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def contains_forbidden_text(value: Any) -> bool:
    text = as_text(value)
    lower = text.lower()
    if PATH_RE.search(text) or URL_RE.search(text) or RAW_BYTES_RE.search(text):
        return True
    return any(marker in lower for marker in FORBIDDEN_MARKERS)


def artifact_quality_status(payload: Mapping[str, Any]) -> str:
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return as_text(quality.get("status") or payload.get("quality_status") or summary.get("quality_status"))


def artifact_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload.get("summary") or {}) if isinstance(payload.get("summary"), Mapping) else {}


def citation_ids_from(claim: Mapping[str, Any]) -> list[str]:
    raw = claim.get("citation_ids")
    ids: list[str] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        ids.extend(as_text(item) for item in raw if as_text(item))
    if as_text(claim.get("citation_id")):
        ids.append(as_text(claim.get("citation_id")))
    return sorted(set(ids))


def record_bucket(record: Mapping[str, Any]) -> str:
    return normalize_bucket(record.get("rag_bucket") or record.get("bucket") or record.get("safety_bucket"))


def load_final_answer_report(path: Path) -> dict[str, Any]:
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        raise AskFinalGateError(f"final-answer gate report is not a JSON object: {path}")
    return dict(payload)


def final_claims_from(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("final_claims") or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def final_gate_safe_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = artifact_summary(payload)
    claims = final_claims_from(payload)
    final_answer_text = as_text(payload.get("final_answer_text"))
    if not summary:
        cited = sum(1 for claim in claims if citation_ids_from(claim))
        retrieval_only = sum(1 for claim in claims if record_bucket(claim) in RETRIEVAL_ONLY_BUCKETS)
        summary = {
            "answer_status": as_text(payload.get("answer_status")),
            "final_answer_allowed": as_bool(payload.get("final_answer_allowed"), default=False),
            "final_claim_count": len(claims),
            "cited_final_claim_count": cited,
            "uncited_final_claim_count": len(claims) - cited,
            "retrieval_only_final_claim_count": retrieval_only,
            "missing_page_id_count": sum(1 for claim in claims if not as_text(claim.get("page_id"))),
            "missing_citation_count": sum(1 for claim in claims if not citation_ids_from(claim)),
            "missing_authority_count": sum(1 for claim in claims if not as_text(claim.get("authority"))),
            "local_path_leak_count": int(contains_forbidden_text(final_answer_text)),
            "raw_bytes_repr_count": int(RAW_BYTES_RE.search(final_answer_text) is not None),
            "boilerplate_leak_count": int(any(marker in final_answer_text.lower() for marker in ["source text evidence for page", "this chunk is source-backed", "tiff path:", "ocr path:"])),
            "ocr_uncertainty_note_present": "ocr" in final_answer_text.lower() and "review" in final_answer_text.lower(),
            "source_truth_mutation_allowed_count": sum(1 for claim in claims if as_bool(claim.get("source_truth_mutation_allowed"), default=False) or as_bool(claim.get("can_mutate_source_truth"), default=False)),
            "llm_freeform_answer_allowed_count": sum(1 for claim in claims if as_bool(claim.get("llm_freeform_answer_allowed"), default=False)),
        }
    return dict(summary)


def build_ask_final_gate_summary(
    *,
    query: str,
    answer_mode: str,
    retrieval_mode: str,
    final_answer_payload: Mapping[str, Any],
    final_answer_report_path: Path,
) -> dict[str, Any]:
    final_summary = final_gate_safe_summary(final_answer_payload)
    claims = final_claims_from(final_answer_payload)
    final_answer_text = as_text(final_answer_payload.get("final_answer_text"))
    final_gate_query = as_text(final_summary.get("query") or final_answer_payload.get("query"))
    requested_query = as_text(query)
    effective_query = requested_query or final_gate_query
    query_match_status = "PASS" if not requested_query or not final_gate_query or requested_query == final_gate_query else "FAIL"
    citation_ids = sorted({cid for claim in claims for cid in citation_ids_from(claim)})
    page_ids = sorted({as_text(claim.get("page_id")) for claim in claims if as_text(claim.get("page_id"))})
    bucket_counts: dict[str, int] = {}
    for claim in claims:
        bucket = record_bucket(claim)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    authority_counts: dict[str, int] = {}
    for claim in claims:
        authority = as_text(claim.get("authority"))
        authority_counts[authority] = authority_counts.get(authority, 0) + 1

    final_gate_quality_status = artifact_quality_status(final_answer_payload)
    final_answer_allowed = as_bool(final_answer_payload.get("final_answer_allowed") or final_summary.get("final_answer_allowed"), default=False)
    delivered = (
        answer_mode == "final-gate"
        and final_gate_quality_status == "PASS"
        and as_text(final_answer_payload.get("answer_status") or final_summary.get("answer_status")) == "FINAL_ANSWER_GATE_APPROVED"
        and final_answer_allowed
        and as_int(final_summary.get("uncited_final_claim_count")) == 0
        and as_int(final_summary.get("retrieval_only_final_claim_count")) == 0
        and as_int(final_summary.get("missing_page_id_count")) == 0
        and as_int(final_summary.get("missing_citation_count")) == 0
        and as_int(final_summary.get("missing_authority_count")) == 0
        and as_int(final_summary.get("local_path_leak_count")) == 0
        and as_int(final_summary.get("raw_bytes_repr_count")) == 0
        and as_int(final_summary.get("boilerplate_leak_count")) == 0
        and as_int(final_summary.get("source_truth_mutation_allowed_count")) == 0
        and as_int(final_summary.get("llm_freeform_answer_allowed_count")) == 0
        and bool(final_answer_text)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "query": effective_query,
        "final_answer_gate_query": final_gate_query,
        "query_match_status": query_match_status,
        "answer_mode": answer_mode,
        "retrieval_mode": retrieval_mode,
        "answer_status": "FINAL_ANSWER_DELIVERED_BY_GATE" if delivered else "FINAL_ANSWER_BLOCKED_BY_ASK_FLAG",
        "ask_final_answer_allowed": bool(delivered),
        "final_answer_gate_quality_status": final_gate_quality_status,
        "final_answer_gate_status": as_text(final_answer_payload.get("status")),
        "final_answer_gate_answer_status": as_text(final_answer_payload.get("answer_status") or final_summary.get("answer_status")),
        "final_answer_gate_allowed": final_answer_allowed,
        "final_answer_report_path": str(final_answer_report_path),
        "final_answer_sha256": sha256_text(final_answer_text),
        "final_answer_char_count": len(final_answer_text),
        "final_claim_count": len(claims),
        "cited_final_claim_count": as_int(final_summary.get("cited_final_claim_count"), default=sum(1 for c in claims if citation_ids_from(c))),
        "uncited_final_claim_count": as_int(final_summary.get("uncited_final_claim_count")),
        "retrieval_only_final_claim_count": as_int(final_summary.get("retrieval_only_final_claim_count")),
        "missing_page_id_count": as_int(final_summary.get("missing_page_id_count")),
        "missing_citation_count": as_int(final_summary.get("missing_citation_count")),
        "missing_authority_count": as_int(final_summary.get("missing_authority_count")),
        "local_path_leak_count": as_int(final_summary.get("local_path_leak_count")),
        "raw_bytes_repr_count": as_int(final_summary.get("raw_bytes_repr_count")),
        "boilerplate_leak_count": as_int(final_summary.get("boilerplate_leak_count")),
        "ocr_uncertainty_note_present": as_bool(final_summary.get("ocr_uncertainty_note_present"), default=False),
        "source_truth_mutation_allowed_count": as_int(final_summary.get("source_truth_mutation_allowed_count")),
        "llm_freeform_answer_allowed_count": as_int(final_summary.get("llm_freeform_answer_allowed_count")),
        "embedding_mode": as_text(final_summary.get("embedding_mode")),
        "embedding_model_name": as_text(final_summary.get("embedding_model_name")),
        "embedding_dim": as_int(final_summary.get("embedding_dim")),
        "composer_mode": as_text(final_summary.get("composer_mode")),
        "llm_model_name": as_text(final_summary.get("llm_model_name")),
        "llm_assisted_composition_used": as_bool(final_summary.get("llm_assisted_composition_used"), default=False),
        "llm_candidate_answer_allowed_for_final": as_bool(final_summary.get("llm_candidate_answer_allowed_for_final"), default=False),
        "page_count": len(page_ids),
        "page_ids": page_ids,
        "citation_count": len(citation_ids),
        "citation_ids": citation_ids,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "default_ask_unchanged": True,
        "source_truth_mutations_performed": 0,
    }


def quality_checks_for_summary(
    summary: Mapping[str, Any],
    *,
    min_final_claims: int = 1,
    require_answer_mode: str = "final-gate",
    require_retrieval_mode: str = "",
    require_final_answer_gate_pass: bool = False,
    require_final_answer_allowed: bool = False,
    require_embedding_dim: int | None = None,
    require_ocr_uncertainty_note: bool = True,
) -> QualityResult:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected})

    add("answer_mode", as_text(summary.get("answer_mode")) == require_answer_mode, summary.get("answer_mode"), require_answer_mode)
    if require_retrieval_mode:
        add("retrieval_mode", as_text(summary.get("retrieval_mode")) == require_retrieval_mode, summary.get("retrieval_mode"), require_retrieval_mode)
    add("query_matches_final_answer_gate", as_text(summary.get("query_match_status") or "PASS") == "PASS", summary.get("query_match_status") or "PASS", "PASS")
    add("min_final_claims", as_int(summary.get("final_claim_count")) >= int(min_final_claims), summary.get("final_claim_count"), f">= {min_final_claims}")
    add("all_final_claims_cited", as_int(summary.get("uncited_final_claim_count")) == 0, summary.get("uncited_final_claim_count"), 0)
    add("no_retrieval_only_final_claims", as_int(summary.get("retrieval_only_final_claim_count")) == 0, summary.get("retrieval_only_final_claim_count"), 0)
    add("no_missing_page_ids", as_int(summary.get("missing_page_id_count")) == 0, summary.get("missing_page_id_count"), 0)
    add("no_missing_citations", as_int(summary.get("missing_citation_count")) == 0, summary.get("missing_citation_count"), 0)
    add("no_missing_authority", as_int(summary.get("missing_authority_count")) == 0, summary.get("missing_authority_count"), 0)
    add("no_local_path_leaks", as_int(summary.get("local_path_leak_count")) == 0, summary.get("local_path_leak_count"), 0)
    add("no_raw_bytes_repr", as_int(summary.get("raw_bytes_repr_count")) == 0, summary.get("raw_bytes_repr_count"), 0)
    add("no_boilerplate_leak", as_int(summary.get("boilerplate_leak_count")) == 0, summary.get("boilerplate_leak_count"), 0)
    add("no_source_truth_mutation", as_int(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("no_llm_freeform_answer", as_int(summary.get("llm_freeform_answer_allowed_count")) == 0, summary.get("llm_freeform_answer_allowed_count"), 0)
    add("default_ask_unchanged", as_bool(summary.get("default_ask_unchanged"), default=False), summary.get("default_ask_unchanged"), True)
    if require_ocr_uncertainty_note:
        add("ocr_uncertainty_note_present", as_bool(summary.get("ocr_uncertainty_note_present"), default=False), summary.get("ocr_uncertainty_note_present"), True)
    if require_final_answer_gate_pass:
        add("final_answer_gate_quality_pass", as_text(summary.get("final_answer_gate_quality_status")) == "PASS", summary.get("final_answer_gate_quality_status"), "PASS")
        add(
            "final_answer_gate_approved",
            as_text(summary.get("final_answer_gate_answer_status")) == "FINAL_ANSWER_GATE_APPROVED",
            summary.get("final_answer_gate_answer_status"),
            "FINAL_ANSWER_GATE_APPROVED",
        )
    if require_final_answer_allowed:
        add("ask_final_answer_allowed", as_bool(summary.get("ask_final_answer_allowed"), default=False), summary.get("ask_final_answer_allowed"), True)
        add("final_answer_gate_allowed", as_bool(summary.get("final_answer_gate_allowed"), default=False), summary.get("final_answer_gate_allowed"), True)
    if require_embedding_dim is not None:
        add("embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), summary.get("embedding_dim"), int(require_embedding_dim))

    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def build_markdown_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Ask Final Gate v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Answer mode:** {summary.get('answer_mode', '')}",
        f"**Retrieval mode:** {summary.get('retrieval_mode', '')}",
        f"**Answer status:** {report.get('answer_status')}",
        f"**Ask final answer allowed:** {report.get('ask_final_answer_allowed')}",
        "",
        "## Summary",
        "",
        f"- Query: {summary.get('query', '')}",
        f"- Final claims: {summary.get('final_claim_count', 0)}",
        f"- Citations: {summary.get('citation_count', 0)}",
        f"- Pages: {', '.join(summary.get('page_ids') or [])}",
        f"- Final gate quality: {summary.get('final_answer_gate_quality_status', '')}",
        f"- Final gate answer status: {summary.get('final_answer_gate_answer_status', '')}",
        "",
        "## Gated ask answer",
        "",
        as_text(report.get("final_answer_text")),
        "",
        "## TRACE-Net ask-gate note",
        "",
        "This answer was exposed only because the Step 12 final-answer gate passed. The default ask path remains unchanged.",
    ]
    return "\n".join(lines).strip() + "\n"


def build_html_report(report: Mapping[str, Any]) -> str:
    markdown = build_markdown_report(report)
    body = "<br/>\n".join(html.escape(line) for line in markdown.splitlines())
    return "<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>TRACE-Net Ask Final Gate v1</title></head><body>\n" + body + "\n</body></html>\n"


def build_ask_final_gate_report(
    *,
    query: str,
    retrieval_mode: str = "hybrid-simulate",
    answer_mode: str = "final-gate",
    final_answer_payload: Mapping[str, Any] | None = None,
    final_answer_report_path: Path | None = None,
    final_gate_report: Mapping[str, Any] | None = None,
    min_final_claims: int = 1,
    require_answer_mode: str = "final-gate",
    require_retrieval_mode: str = "",
    require_final_answer_gate_pass: bool = False,
    require_final_answer_allowed: bool = False,
    require_embedding_dim: int | None = None,
    require_ocr_uncertainty_note: bool = True,
) -> dict[str, Any]:
    if final_answer_payload is None:
        final_answer_payload = final_gate_report
    if final_answer_payload is None:
        raise AskFinalGateError("final answer gate payload is required")
    if final_answer_report_path is None:
        final_answer_report_path = DEFAULT_FINAL_ANSWER_REPORT
    if answer_mode not in ANSWER_MODES:
        raise AskFinalGateError(f"unsupported answer mode: {answer_mode}")
    if retrieval_mode not in RETRIEVAL_MODES:
        raise AskFinalGateError(f"unsupported retrieval mode: {retrieval_mode}")
    summary = build_ask_final_gate_summary(
        query=query,
        answer_mode=answer_mode,
        retrieval_mode=retrieval_mode,
        final_answer_payload=final_answer_payload,
        final_answer_report_path=final_answer_report_path,
    )
    quality = quality_checks_for_summary(
        summary,
        min_final_claims=min_final_claims,
        require_answer_mode=require_answer_mode,
        require_retrieval_mode=require_retrieval_mode,
        require_final_answer_gate_pass=require_final_answer_gate_pass,
        require_final_answer_allowed=require_final_answer_allowed,
        require_embedding_dim=require_embedding_dim,
        require_ocr_uncertainty_note=require_ocr_uncertainty_note,
    )
    final_answer_text = as_text(final_answer_payload.get("final_answer_text")) if quality.status == "PASS" else ""
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_FINAL_GATE_RAN",
        "quality_status": quality.status,
        "answer_status": summary["answer_status"],
        "ask_final_answer_allowed": bool(quality.status == "PASS" and as_bool(summary.get("ask_final_answer_allowed"), default=False)),
        "query": summary["query"],
        "retrieval_mode": retrieval_mode,
        "answer_mode": answer_mode,
        "final_answer_text": final_answer_text,
        "summary": summary,
        "quality": {"status": quality.status, "checks": quality.checks},
        "final_claims": final_claims_from(final_answer_payload) if quality.status == "PASS" else [],
        "source_final_answer_report_path": str(final_answer_report_path),
        "created_at": utc_now_iso(),
    }
    return report


def write_ask_final_gate_outputs(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    report_path = output_dir / DEFAULT_REPORT_FILE
    claims_path = output_dir / DEFAULT_CLAIMS_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    md_path = output_dir / DEFAULT_MD_FILE
    html_path = output_dir / DEFAULT_HTML_FILE
    write_json(report_path, report)
    write_jsonl(claims_path, report.get("final_claims") or [])
    write_json(summary_path, report.get("summary") or {})
    write_json(quality_path, report.get("quality") or {})
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(build_markdown_report(report), encoding="utf-8", newline="\n")
    html_path.write_text(build_html_report(report), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "report_sha256": sha256_json(report),
        "final_answer_text_sha256": sha256_text(report.get("final_answer_text")),
        "quality_status": report.get("quality_status"),
        "ask_final_answer_allowed": report.get("ask_final_answer_allowed"),
    }
    write_json(manifest_path, manifest)
    return {
        "report_path": str(report_path),
        "claims_path": str(claims_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }


def run_ask_final_gate(
    *,
    query: str = "",
    retrieval_mode: str = "hybrid-simulate",
    answer_mode: str = "off",
    final_answer_report_path: Path = DEFAULT_FINAL_ANSWER_REPORT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_final_claims: int = 1,
    require_answer_mode: str = "final-gate",
    require_retrieval_mode: str = "",
    require_final_answer_gate_pass: bool = False,
    require_final_answer_allowed: bool = False,
    require_embedding_dim: int | None = None,
    require_ocr_uncertainty_note: bool = True,
    write_quality: bool = True,
) -> dict[str, Any]:
    payload = load_final_answer_report(final_answer_report_path)
    report = build_ask_final_gate_report(
        query=query,
        retrieval_mode=retrieval_mode,
        answer_mode=answer_mode,
        final_answer_payload=payload,
        final_answer_report_path=Path(final_answer_report_path),
        min_final_claims=min_final_claims,
        require_answer_mode=require_answer_mode,
        require_retrieval_mode=require_retrieval_mode,
        require_final_answer_gate_pass=require_final_answer_gate_pass,
        require_final_answer_allowed=require_final_answer_allowed,
        require_embedding_dim=require_embedding_dim,
        require_ocr_uncertainty_note=require_ocr_uncertainty_note,
    )
    paths = write_ask_final_gate_outputs(report, output_dir)
    report.update(paths)
    write_json(Path(paths["report_path"]), report)
    write_json(Path(paths["summary_path"]), report.get("summary") or {})
    if write_quality:
        write_json(Path(paths["quality_path"]), report.get("quality") or {})
    return report


def check_ask_final_gate_quality(
    *,
    report_path: Path,
    min_final_claims: int = 1,
    require_answer_mode: str = "final-gate",
    require_retrieval_mode: str = "",
    require_final_answer_gate_pass: bool = False,
    require_final_answer_allowed: bool = False,
    require_embedding_dim: int | None = None,
    require_ocr_uncertainty_note: bool = True,
    write_json_quality: bool = False,
) -> dict[str, Any]:
    report = read_json(Path(report_path))
    if not isinstance(report, Mapping):
        raise AskFinalGateError(f"ask final-gate report is not a JSON object: {report_path}")
    summary = dict(report.get("summary") or {}) if isinstance(report.get("summary"), Mapping) else {}
    if not summary:
        summary = {
            "answer_mode": report.get("answer_mode"),
            "retrieval_mode": report.get("retrieval_mode"),
            "ask_final_answer_allowed": report.get("ask_final_answer_allowed"),
            "final_claim_count": len(report.get("final_claims") or []),
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
        }
    quality = quality_checks_for_summary(
        summary,
        min_final_claims=min_final_claims,
        require_answer_mode=require_answer_mode,
        require_retrieval_mode=require_retrieval_mode,
        require_final_answer_gate_pass=require_final_answer_gate_pass,
        require_final_answer_allowed=require_final_answer_allowed,
        require_embedding_dim=require_embedding_dim,
        require_ocr_uncertainty_note=require_ocr_uncertainty_note,
    )
    quality_payload = {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary, "created_at": utc_now_iso()}
    if write_json_quality:
        quality_path = Path(report_path).with_name(DEFAULT_QUALITY_FILE)
        write_json(quality_path, quality_payload)
        quality_payload["quality_path"] = str(quality_path)
    return quality_payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expose TRACE-Net final-answer gate through ask behind an explicit flag.")
    parser.add_argument("--query", default="")
    parser.add_argument("--retrieval-mode", default="hybrid-simulate", choices=sorted(RETRIEVAL_MODES))
    parser.add_argument("--answer-mode", default="off", choices=sorted(ANSWER_MODES))
    parser.add_argument("--final-answer-report", dest="final_answer_report_path", type=Path, default=DEFAULT_FINAL_ANSWER_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-final-claims", type=int, default=1)
    parser.add_argument("--require-answer-mode", default="final-gate")
    parser.add_argument("--require-retrieval-mode", default="")
    parser.add_argument("--require-final-answer-gate-pass", action="store_true")
    parser.add_argument("--require-final-answer-allowed", action="store_true")
    parser.add_argument("--require-embedding-dim", type=int, default=0)
    parser.add_argument("--allow-missing-ocr-note", action="store_true")
    parser.add_argument("--quality", action="store_true", help="Kept for stage compatibility; quality is always written.")
    return parser


def build_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net ask final gate v1 quality.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--min-final-claims", type=int, default=1)
    parser.add_argument("--require-answer-mode", default="final-gate")
    parser.add_argument("--require-retrieval-mode", default="")
    parser.add_argument("--require-final-answer-gate-pass", action="store_true")
    parser.add_argument("--require-final-answer-allowed", action="store_true")
    parser.add_argument("--require-embedding-dim", type=int, default=0)
    parser.add_argument("--allow-missing-ocr-note", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def print_run_summary(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    print("TRACE-Net ask final gate v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    print(f" retrieval_mode: {report.get('retrieval_mode')}")
    print(f" answer_mode: {report.get('answer_mode')}")
    print(f" answer_status: {report.get('answer_status')}")
    print(f" ask_final_answer_allowed: {report.get('ask_final_answer_allowed')}")
    for key in [
        "query",
        "final_answer_gate_quality_status",
        "final_answer_gate_answer_status",
        "final_answer_gate_allowed",
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
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
    ]:
        print(f" {key}: {summary.get(key, '')}")
    for key in ["report_path", "markdown_path", "html_path", "quality_path"]:
        if report.get(key):
            print(f" {key}: {report.get(key)}")


def print_quality_summary(quality: Mapping[str, Any]) -> None:
    summary = quality.get("summary") if isinstance(quality.get("summary"), Mapping) else {}
    print("TRACE-Net ask final gate v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in [
        "answer_mode",
        "retrieval_mode",
        "answer_status",
        "ask_final_answer_allowed",
        "final_answer_gate_quality_status",
        "final_answer_gate_answer_status",
        "final_claim_count",
        "cited_final_claim_count",
        "uncited_final_claim_count",
        "retrieval_only_final_claim_count",
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
        report = run_ask_final_gate(
            query=args.query,
            retrieval_mode=args.retrieval_mode,
            answer_mode=args.answer_mode,
            final_answer_report_path=args.final_answer_report_path,
            output_dir=args.output_dir,
            min_final_claims=args.min_final_claims,
            require_answer_mode=args.require_answer_mode,
            require_retrieval_mode=args.require_retrieval_mode,
            require_final_answer_gate_pass=args.require_final_answer_gate_pass,
            require_final_answer_allowed=args.require_final_answer_allowed,
            require_embedding_dim=args.require_embedding_dim or None,
            require_ocr_uncertainty_note=not args.allow_missing_ocr_note,
        )
        print_run_summary(report)
        return 0 if report.get("quality_status") == "PASS" else 1
    except Exception as exc:
        print(f"TRACE-Net ask final gate failed: {exc}", file=sys.stderr)
        return 2


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        quality = check_ask_final_gate_quality(
            report_path=args.report_path,
            min_final_claims=args.min_final_claims,
            require_answer_mode=args.require_answer_mode,
            require_retrieval_mode=args.require_retrieval_mode,
            require_final_answer_gate_pass=args.require_final_answer_gate_pass,
            require_final_answer_allowed=args.require_final_answer_allowed,
            require_embedding_dim=args.require_embedding_dim or None,
            require_ocr_uncertainty_note=not args.allow_missing_ocr_note,
            write_json_quality=args.write_json,
        )
        print_quality_summary(quality)
        return 0 if quality.get("status") == "PASS" else 1
    except Exception as exc:
        print(f"TRACE-Net ask final gate quality check failed: {exc}", file=sys.stderr)
        return 2


# Backward-compatible names for tests or wrappers.
build_trace_net_ask_final_gate = run_ask_final_gate
run_trace_net_ask_final_gate = run_ask_final_gate
check_trace_net_ask_final_gate_quality = check_ask_final_gate_quality
run_quality_check = check_ask_final_gate_quality


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
