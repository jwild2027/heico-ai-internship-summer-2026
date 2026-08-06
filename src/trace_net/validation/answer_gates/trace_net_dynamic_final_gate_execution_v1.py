"""TRACE-Net Dynamic Final-Gate Execution v1.

Read-only dynamic gate runner that takes Hybrid Retrieval v2 groups and tries to
materialize final-answer candidates for arbitrary queries.  It may approve a
minimal final answer only when the selected dynamic retrieval groups have page
lineage, citations, and answer-support authority.  Otherwise it returns a
retrieval-only, final-gate-required result.

Safety contract:
- Hybrid retrieval groups are possible evidence, not proof.
- Dynamic final claims require page/source lineage, citations, and answer-support
  buckets/authorities.
- Feedback, communities, and categories are never proof.
- No Postgres, Qdrant, OpenSearch, graph, citation, trust, or source writes occur.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

SCHEMA_VERSION = "trace_net_dynamic_final_gate_execution_v1"
ALGORITHM = "trace_net_dynamic_retrieval_to_citation_authority_gate_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/dynamic_final_gate_execution")
DEFAULT_HYBRID_V2_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json")
DEFAULT_FINAL_ANSWER_REPORT = Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json")
DEFAULT_FINAL_ANSWER_MD = Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md")
DEFAULT_OUTPUT_FILE = "trace_net_dynamic_final_gate_execution_v1.json"
DEFAULT_RESULTS_FILE = "trace_net_dynamic_final_gate_execution_v1_results.jsonl"
DEFAULT_CLAIMS_FILE = "trace_net_dynamic_final_gate_execution_v1_claims.jsonl"
DEFAULT_BLOCKED_FILE = "trace_net_dynamic_final_gate_execution_v1_blocked_claims.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_dynamic_final_gate_execution_v1_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_dynamic_final_gate_execution_v1_quality.json"
DEFAULT_MANIFEST_FILE = "trace_net_dynamic_final_gate_execution_v1_manifest.json"
DEFAULT_MD_FILE = "trace_net_dynamic_final_gate_execution_v1.md"
DEFAULT_HTML_FILE = "trace_net_dynamic_final_gate_execution_v1.html"

ANSWER_SUPPORT_BUCKETS = {
    "source_text_evidence",
    "verified_part_evidence",
    "table_part_catalog_evidence",
    "table_structured_evidence",
    "clean_evidence_snippet",
    "promoted_table_part_evidence_candidate",
    "promoted_visual_part_evidence_candidate",
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
    "feedback_memory_advisory",
}
ANSWER_SUPPORT_AUTHORITIES = {
    "ocr_text_claim_with_citation",
    "part_page_relationship",
    "table_part_catalog_evidence_with_citation",
    "promoted_table_part_evidence_with_citation",
    "promoted_visual_part_evidence_with_citation",
}
BANNED_BUCKET_TOKENS = {
    "raw_ocr",
    "raw_visual",
    "raw_table",
    "raw_feedback",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}

PART_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
LOCAL_PATH_RE = re.compile(r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)", re.IGNORECASE)
RAW_BYTES_RE = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")

OCR_UNCERTAINTY_NOTE = (
    "This dynamic answer is based on TRACE-Net retrieval groups that passed page, citation, "
    "and authority checks. OCR and extracted table text may contain noise, so review the cited "
    "source pages for exact wording."
)


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "pass", "allowed"}:
            return True
        if text in {"0", "false", "no", "n", "fail", "blocked"}:
            return False
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def unique_texts(values: Iterable[Any]) -> list[str]:
    return sorted({as_text(v) for v in values if as_text(v)})


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: Optional[str | Path]) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def read_text_if_exists(path: Optional[str | Path]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def quality_status(payload: Mapping[str, Any]) -> str:
    for key in ("quality_status", "status"):
        value = as_text(payload.get(key)).upper()
        if value in {"PASS", "FAIL"}:
            return value
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    for key in ("quality_status", "status"):
        value = as_text(summary.get(key)).upper()
        if value in {"PASS", "FAIL"}:
            return value
    return ""


def normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", as_text(value).lower())


def page_number_from_page_id(page_id: str) -> str:
    m = re.search(r"p(\d{6})$", as_text(page_id))
    if not m:
        return as_text(page_id)
    return str(int(m.group(1)))


def sanitize_text(text: str, max_chars: int = 14000) -> tuple[str, dict[str, int]]:
    counts = {
        "local_path_leak_count": len(LOCAL_PATH_RE.findall(text or "")),
        "raw_bytes_repr_count": len(RAW_BYTES_RE.findall(text or "")),
    }
    safe = LOCAL_PATH_RE.sub("[redacted-local-path]", text or "")
    safe = RAW_BYTES_RE.sub("[redacted-bytes]", safe)
    if len(safe) > max_chars:
        safe = safe[:max_chars].rstrip() + "\n\n[truncated by TRACE-Net dynamic final gate]"
    return safe, counts


def query_results(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("query_results") or report.get("results") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def ranked_groups(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = row.get("ranked_groups") or row.get("groups") or []
    return [dict(g) for g in groups if isinstance(g, Mapping)] if isinstance(groups, list) else []


def load_queries(query_file: Optional[str | Path], hybrid_v2: Mapping[str, Any], query: str = "") -> list[dict[str, str]]:
    if as_text(query):
        return [{"query_id": f"custom__{stable_hash(query)}", "query": as_text(query), "intent": "custom_query"}]
    if query_file:
        payload = read_json(query_file)
        rows = payload.get("queries") if isinstance(payload.get("queries"), list) else []
        out = []
        for idx, row in enumerate(rows):
            if isinstance(row, Mapping) and as_text(row.get("query")):
                out.append({
                    "query_id": as_text(row.get("query_id") or f"query_{idx + 1:03d}"),
                    "query": as_text(row.get("query")),
                    "intent": as_text(row.get("intent") or "custom_query"),
                })
        if out:
            return out
    out = []
    for row in query_results(hybrid_v2):
        if as_text(row.get("query")):
            out.append({
                "query_id": as_text(row.get("query_id") or f"hybrid_query__{stable_hash(row.get('query'))}"),
                "query": as_text(row.get("query")),
                "intent": as_text(row.get("intent") or "hybrid_v2_query"),
            })
    return out


def find_hybrid_query_result(hybrid_v2: Mapping[str, Any], query: Mapping[str, str]) -> dict[str, Any]:
    qid = as_text(query.get("query_id"))
    qtext = normalize_query(as_text(query.get("query")))
    best: dict[str, Any] = {}
    for row in query_results(hybrid_v2):
        if qid and as_text(row.get("query_id")) == qid:
            return dict(row)
        row_q = normalize_query(as_text(row.get("query")))
        if qtext and row_q == qtext:
            return dict(row)
        if qtext and row_q and (qtext in row_q or row_q in qtext):
            best = dict(row)
    return best


def final_artifact_query(final_report: Mapping[str, Any]) -> str:
    summary = final_report.get("summary") if isinstance(final_report.get("summary"), Mapping) else {}
    return as_text(final_report.get("query") or summary.get("query"))


def final_artifact_allowed(final_report: Mapping[str, Any]) -> bool:
    if "final_answer_allowed" in final_report:
        return as_bool(final_report.get("final_answer_allowed"))
    summary = final_report.get("summary") if isinstance(final_report.get("summary"), Mapping) else {}
    return as_bool(summary.get("final_answer_allowed"))


def extract_markdown_final_answer(markdown_text: str) -> str:
    marker = "## Final gated answer"
    if marker in markdown_text:
        answer = markdown_text.split(marker, 1)[1].strip()
        nxt = answer.find("\n## ")
        if nxt > 0:
            answer = answer[:nxt].strip()
        return answer
    return markdown_text.strip()


def final_artifact_answer_text(final_report: Mapping[str, Any], final_markdown: Optional[str | Path]) -> str:
    for key in ("final_answer_text", "answer_text", "answer", "final_answer"):
        value = final_report.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            for inner in ("text", "markdown", "answer_text", "final_answer_text"):
                if isinstance(value.get(inner), str) and value.get(inner).strip():
                    return value.get(inner).strip()
    return extract_markdown_final_answer(read_text_if_exists(final_markdown))


def group_citations(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("citation_ids")))
    for hit in as_list(group.get("exact_hits")):
        if isinstance(hit, Mapping):
            values.extend(as_list(hit.get("citation_ids")))
            if hit.get("citation_id"):
                values.append(hit.get("citation_id"))
    for sg in as_list(group.get("semantic_groups")):
        if isinstance(sg, Mapping):
            values.extend(as_list(sg.get("citation_ids")))
            for key in ("candidate_hits", "hits", "exact_hits"):
                for hit in as_list(sg.get(key)):
                    if isinstance(hit, Mapping):
                        values.extend(as_list(hit.get("citation_ids")))
                        if hit.get("citation_id"):
                            values.append(hit.get("citation_id"))
    return unique_texts(values)


def group_buckets(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("rag_buckets") or group.get("buckets")))
    for hit in as_list(group.get("exact_hits")):
        if isinstance(hit, Mapping):
            values.append(hit.get("rag_bucket"))
    return unique_texts(v.lower() for v in values if as_text(v))


def group_authorities(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("authorities")))
    for hit in as_list(group.get("exact_hits")):
        if isinstance(hit, Mapping):
            values.append(hit.get("authority"))
    return unique_texts(v.lower() for v in values if as_text(v))


def group_page_id(group: Mapping[str, Any]) -> str:
    if as_text(group.get("page_id")):
        return as_text(group.get("page_id"))
    pages = unique_texts(group.get("source_page_ids") or [])
    return pages[0] if pages else ""


def group_part_numbers(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("part_numbers")))
    for hit in as_list(group.get("exact_hits")):
        if isinstance(hit, Mapping):
            values.extend(as_list(hit.get("part_numbers")))
            values.extend(PART_RE.findall(as_text(hit.get("text_preview"))))
    return unique_texts(values)


def has_answer_support(group: Mapping[str, Any]) -> bool:
    if as_int(group.get("answer_support_candidate_count")) > 0:
        return True
    buckets = set(group_buckets(group))
    authorities = set(group_authorities(group))
    if buckets & ANSWER_SUPPORT_BUCKETS:
        return True
    if authorities & ANSWER_SUPPORT_AUTHORITIES:
        return True
    for hit in as_list(group.get("exact_hits")):
        if isinstance(hit, Mapping) and as_bool(hit.get("answer_support_candidate")):
            return True
    return False


def is_banned_bucket(bucket: str) -> bool:
    b = as_text(bucket).lower()
    return any(token in b for token in BANNED_BUCKET_TOKENS)


def evaluate_group_for_dynamic_claim(query: Mapping[str, str], group: Mapping[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    page_id = group_page_id(group)
    citations = group_citations(group)
    buckets = group_buckets(group)
    authorities = group_authorities(group)
    reasons: list[str] = []
    if not page_id:
        reasons.append("missing_page_id")
    if not citations:
        reasons.append("missing_citation")
    if any(is_banned_bucket(bucket) for bucket in buckets):
        reasons.append("banned_bucket_present")
    if as_bool(group.get("source_truth_mutation_allowed")) or as_bool(group.get("can_mutate_source_truth")):
        reasons.append("source_truth_mutation_risk")
    if as_bool(group.get("feedback_as_proof")):
        reasons.append("feedback_as_proof")
    if as_bool(group.get("community_as_proof")):
        reasons.append("community_as_proof")
    if as_bool(group.get("category_as_proof")):
        reasons.append("category_as_proof")
    if not has_answer_support(group):
        reasons.append("no_answer_support_authority")
    if as_bool(group.get("retrieval_only"), True) and "no_answer_support_authority" in reasons:
        reasons.append("retrieval_only_group")

    base = {
        "query_id": as_text(query.get("query_id")),
        "query": as_text(query.get("query")),
        "hybrid_v2_group_id": as_text(group.get("hybrid_v2_group_id")),
        "hybrid_v2_rank": as_int(group.get("hybrid_v2_rank")),
        "page_id": page_id,
        "page_number": page_number_from_page_id(page_id) if page_id else "",
        "citation_ids": citations,
        "part_numbers": group_part_numbers(group),
        "rag_buckets": buckets,
        "authorities": authorities,
        "exact_hit_count": as_int(group.get("exact_hit_count")),
        "semantic_group_count": as_int(group.get("semantic_group_count")),
        "hybrid_v2_score": as_float(group.get("hybrid_v2_score")),
        "category_labels": unique_texts(group.get("category_labels") or []),
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }

    if reasons:
        blocked = dict(base)
        blocked.update({
            "blocked_claim_id": f"dynblock__{stable_hash([query, group.get('hybrid_v2_group_id'), page_id])}",
            "blocked_reason_codes": unique_texts(reasons),
            "claim_status": "blocked_from_final_answer",
            "can_answer_directly": False,
            "can_prove_claims": False,
        })
        return None, blocked

    q = as_text(query.get("query"))
    parts = PART_RE.findall(q)
    atas = ATA_RE.findall(q)
    if parts:
        subject = f"part number {parts[0]}"
        claim_text = f"Page {page_number_from_page_id(page_id)} is a citation-backed TRACE-Net evidence page matching {subject}."
    elif atas:
        subject = f"ATA code {atas[0]}"
        claim_text = f"Page {page_number_from_page_id(page_id)} is a citation-backed TRACE-Net evidence page matching {subject}."
    elif q:
        claim_text = f"Page {page_number_from_page_id(page_id)} is a citation-backed TRACE-Net evidence page for the query '{q}'."
    else:
        claim_text = f"Page {page_number_from_page_id(page_id)} is a citation-backed TRACE-Net evidence page for this query."

    claim = dict(base)
    claim.update({
        "dynamic_final_claim_id": f"dynclaim__{stable_hash([query, group.get('hybrid_v2_group_id'), page_id, citations[:3]])}",
        "claim_text": claim_text,
        "claim_status": "approved_dynamic_final_claim_candidate",
        "evidence_authority_status": "citation_and_authority_checked",
        "retrieval_only": False,
        "can_answer_directly": True,
        "can_prove_claims": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "feedback_as_proof": False,
        "community_as_proof": False,
        "category_as_proof": False,
    })
    return claim, None


def build_dynamic_answer_text(query: Mapping[str, str], claims: list[dict[str, Any]], max_claims: int) -> str:
    lines = [f"TRACE-Net dynamic final-gate answer for: {as_text(query.get('query'))}", ""]
    if not claims:
        lines.append("TRACE-Net found dynamic retrieval groups, but no group passed citation, page, and authority checks for a final answer.")
        lines.append("Review the retrieval groups or run the full TRACE-Net final-gate pipeline for this query.")
        return "\n".join(lines).strip()
    lines.append(f"The dynamic gate authorized {min(len(claims), max_claims)} citation-backed claim(s):")
    for claim in claims[:max_claims]:
        cids = ", ".join(claim.get("citation_ids", [])[:3])
        if len(claim.get("citation_ids", [])) > 3:
            cids += ", ..."
        lines.append(f"- {claim['claim_text']} [cite:{cids}]")
    lines.append("")
    lines.append(f"OCR/source note: {OCR_UNCERTAINTY_NOTE}")
    lines.append("TRACE-Net gate: feedback, community, category, and retrieval-only records were not used as proof.")
    return "\n".join(lines).strip()


def build_dynamic_result(
    query: Mapping[str, str],
    hybrid_result: Mapping[str, Any],
    *,
    max_claims: int,
    min_claims_for_answer: int,
) -> dict[str, Any]:
    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for group in ranked_groups(hybrid_result):
        claim, block = evaluate_group_for_dynamic_claim(query, group)
        if claim:
            approved.append(claim)
        if block:
            blocked.append(block)
    approved = sorted(approved, key=lambda c: (as_int(c.get("hybrid_v2_rank")), -as_float(c.get("hybrid_v2_score"))))[:max_claims]
    final_allowed = len(approved) >= min_claims_for_answer
    answer_text = build_dynamic_answer_text(query, approved, max_claims) if final_allowed else ""
    safe_answer, leaks = sanitize_text(answer_text)
    status = "DYNAMIC_FINAL_GATE_APPROVED" if final_allowed else "DYNAMIC_FINAL_GATE_RETRIEVAL_ONLY"
    return {
        "dynamic_gate_result_id": f"dyngate__{stable_hash([query, approved, blocked[:3]])}",
        "query_id": as_text(query.get("query_id")),
        "query": as_text(query.get("query")),
        "answer_status": status,
        "final_answer_allowed": final_allowed,
        "final_answer_text": safe_answer,
        "final_claims": approved,
        "blocked_claims": blocked,
        "final_claim_count": len(approved),
        "blocked_claim_count": len(blocked),
        "retrieval_group_count": as_int(hybrid_result.get("ranked_group_count") or len(ranked_groups(hybrid_result))),
        "exact_hit_group_count": sum(1 for g in ranked_groups(hybrid_result) if as_int(g.get("exact_hit_count")) > 0),
        "semantic_group_count": sum(1 for g in ranked_groups(hybrid_result) if as_int(g.get("semantic_group_count")) > 0),
        "uncited_final_claim_count": sum(1 for c in approved if not c.get("citation_ids")),
        "retrieval_only_final_claim_count": sum(1 for c in approved if as_bool(c.get("retrieval_only"))),
        "feedback_as_proof_count": sum(1 for c in approved if as_bool(c.get("feedback_as_proof"))),
        "community_as_proof_count": sum(1 for c in approved if as_bool(c.get("community_as_proof"))),
        "category_as_proof_count": sum(1 for c in approved if as_bool(c.get("category_as_proof"))),
        "source_truth_mutation_allowed_count": sum(1 for c in approved if as_bool(c.get("source_truth_mutation_allowed"))),
        "local_path_leak_count": leaks["local_path_leak_count"],
        "raw_bytes_repr_count": leaks["raw_bytes_repr_count"],
        "can_answer_directly": final_allowed,
        "can_prove_claims": final_allowed,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
    }


def build_final_artifact_result(query: Mapping[str, str], final_report: Mapping[str, Any], final_markdown: Optional[str | Path]) -> dict[str, Any]:
    answer = final_artifact_answer_text(final_report, final_markdown)
    answer, leaks = sanitize_text(answer)
    return {
        "dynamic_gate_result_id": f"dyngate_final_artifact__{stable_hash(query)}",
        "query_id": as_text(query.get("query_id")),
        "query": as_text(query.get("query")),
        "answer_status": "FINAL_GATE_ARTIFACT_ANSWER",
        "final_answer_allowed": True,
        "final_answer_text": answer,
        "final_claims": [],
        "blocked_claims": [],
        "final_claim_count": as_int(final_report.get("final_claim_count") or (final_report.get("summary") or {}).get("final_claim_count")),
        "blocked_claim_count": 0,
        "retrieval_group_count": 0,
        "exact_hit_group_count": 0,
        "semantic_group_count": 0,
        "uncited_final_claim_count": as_int(final_report.get("uncited_final_claim_count") or (final_report.get("summary") or {}).get("uncited_final_claim_count")),
        "retrieval_only_final_claim_count": as_int(final_report.get("retrieval_only_final_claim_count") or (final_report.get("summary") or {}).get("retrieval_only_final_claim_count")),
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "source_truth_mutation_allowed_count": as_int(final_report.get("source_truth_mutation_allowed_count") or (final_report.get("summary") or {}).get("source_truth_mutation_allowed_count")),
        "local_path_leak_count": leaks["local_path_leak_count"],
        "raw_bytes_repr_count": leaks["raw_bytes_repr_count"],
        "can_answer_directly": True,
        "can_prove_claims": True,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "final_artifact_quality_status": quality_status(final_report),
    }


def summarize(report: Mapping[str, Any]) -> dict[str, Any]:
    results = [r for r in as_list(report.get("query_results")) if isinstance(r, Mapping)]
    claims = [c for r in results for c in as_list(r.get("final_claims")) if isinstance(c, Mapping)]
    blocked = [b for r in results for b in as_list(r.get("blocked_claims")) if isinstance(b, Mapping)]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "dynamic_gate_query_count": len(results),
        "final_answer_allowed_count": sum(1 for r in results if as_bool(r.get("final_answer_allowed"))),
        "dynamic_final_gate_approved_count": sum(1 for r in results if as_text(r.get("answer_status")) == "DYNAMIC_FINAL_GATE_APPROVED"),
        "final_artifact_answer_count": sum(1 for r in results if as_text(r.get("answer_status")) == "FINAL_GATE_ARTIFACT_ANSWER"),
        "retrieval_only_result_count": sum(1 for r in results if as_text(r.get("answer_status")) == "DYNAMIC_FINAL_GATE_RETRIEVAL_ONLY"),
        "final_claim_count": len(claims),
        "cited_final_claim_count": sum(1 for c in claims if c.get("citation_ids")),
        "uncited_final_claim_count": sum(1 for r in results for _ in range(as_int(r.get("uncited_final_claim_count")))),
        "retrieval_only_final_claim_count": sum(1 for r in results for _ in range(as_int(r.get("retrieval_only_final_claim_count")))),
        "blocked_claim_count": len(blocked),
        "missing_page_id_blocked_claim_count": sum(1 for b in blocked if "missing_page_id" in as_list(b.get("blocked_reason_codes"))),
        "missing_citation_blocked_claim_count": sum(1 for b in blocked if "missing_citation" in as_list(b.get("blocked_reason_codes"))),
        "no_answer_support_blocked_claim_count": sum(1 for b in blocked if "no_answer_support_authority" in as_list(b.get("blocked_reason_codes"))),
        "feedback_as_proof_count": sum(as_int(r.get("feedback_as_proof_count")) for r in results),
        "community_as_proof_count": sum(as_int(r.get("community_as_proof_count")) for r in results),
        "category_as_proof_count": sum(as_int(r.get("category_as_proof_count")) for r in results),
        "local_path_leak_count": sum(as_int(r.get("local_path_leak_count")) for r in results),
        "raw_bytes_repr_count": sum(as_int(r.get("raw_bytes_repr_count")) for r in results),
        "source_truth_mutation_allowed_count": sum(as_int(r.get("source_truth_mutation_allowed_count")) for r in results),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "hybrid_v2_quality_status": report.get("source_quality_statuses", {}).get("hybrid_v2", ""),
        "final_answer_gate_quality_status": report.get("source_quality_statuses", {}).get("final_answer_gate", ""),
    }
    summary["answer_status_counts"] = dict(Counter(as_text(r.get("answer_status")) for r in results))
    summary["blocked_reason_counts"] = dict(Counter(reason for b in blocked for reason in as_list(b.get("blocked_reason_codes"))))
    return summary


def quality_report(
    report: Mapping[str, Any],
    *,
    min_queries: int = 1,
    min_results: int = 1,
    require_hybrid_v2_quality_pass: bool = False,
    require_final_answer_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    add("dynamic_gate_query_count_min", as_int(summary.get("dynamic_gate_query_count")) >= min_queries, summary.get("dynamic_gate_query_count"), f">= {min_queries}")
    add("result_count_min", len(as_list(report.get("query_results"))) >= min_results, len(as_list(report.get("query_results"))), f">= {min_results}")
    add("uncited_final_claim_count_zero", as_int(summary.get("uncited_final_claim_count")) == 0, summary.get("uncited_final_claim_count"), 0)
    add("retrieval_only_final_claim_count_zero", as_int(summary.get("retrieval_only_final_claim_count")) == 0, summary.get("retrieval_only_final_claim_count"), 0)
    add("feedback_as_proof_count_zero", as_int(summary.get("feedback_as_proof_count")) == 0, summary.get("feedback_as_proof_count"), 0)
    add("community_as_proof_count_zero", as_int(summary.get("community_as_proof_count")) == 0, summary.get("community_as_proof_count"), 0)
    add("category_as_proof_count_zero", as_int(summary.get("category_as_proof_count")) == 0, summary.get("category_as_proof_count"), 0)
    add("local_path_leak_count_zero", as_int(summary.get("local_path_leak_count")) == 0, summary.get("local_path_leak_count"), 0)
    add("raw_bytes_repr_count_zero", as_int(summary.get("raw_bytes_repr_count")) == 0, summary.get("raw_bytes_repr_count"), 0)
    add("source_truth_mutation_allowed_count_zero", as_int(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("postgres_write_attempt_count_zero", as_int(summary.get("postgres_write_attempt_count")) == 0, summary.get("postgres_write_attempt_count"), 0)
    add("qdrant_write_attempt_count_zero", as_int(summary.get("qdrant_write_attempt_count")) == 0, summary.get("qdrant_write_attempt_count"), 0)
    add("opensearch_write_attempt_count_zero", as_int(summary.get("opensearch_write_attempt_count")) == 0, summary.get("opensearch_write_attempt_count"), 0)
    if require_hybrid_v2_quality_pass:
        add("hybrid_v2_quality_pass", as_text(summary.get("hybrid_v2_quality_status")).upper() == "PASS", summary.get("hybrid_v2_quality_status"), "PASS")
    if require_final_answer_quality_pass:
        add("final_answer_quality_pass", as_text(summary.get("final_answer_gate_quality_status")).upper() == "PASS", summary.get("final_answer_gate_quality_status"), "PASS")
    status = "PASS" if all(c["passed"] or c["severity"] != "critical" for c in checks) else "FAIL"
    return {"schema_version": f"{SCHEMA_VERSION}_quality", "status": status, "summary": dict(summary), "checks": checks}


def build_dynamic_final_gate_execution(
    *,
    hybrid_v2_report_path: str | Path,
    final_answer_report_path: str | Path | None = None,
    final_answer_markdown_path: str | Path | None = None,
    query_file: str | Path | None = None,
    query: str = "",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_claims: int = 8,
    min_claims_for_answer: int = 1,
    min_queries: int = 1,
    min_results: int = 1,
    require_hybrid_v2_quality_pass: bool = False,
    require_final_answer_quality_pass: bool = False,
) -> dict[str, Any]:
    hybrid_v2 = read_json(hybrid_v2_report_path)
    final_report = read_json(final_answer_report_path) if final_answer_report_path else {}
    queries = load_queries(query_file, hybrid_v2, query=query)
    final_q = normalize_query(final_artifact_query(final_report))
    final_quality = quality_status(final_report)
    final_allowed = final_artifact_allowed(final_report) and final_quality == "PASS"

    results: list[dict[str, Any]] = []
    all_claims: list[dict[str, Any]] = []
    all_blocked: list[dict[str, Any]] = []
    for q in queries:
        q_norm = normalize_query(as_text(q.get("query")))
        if final_allowed and final_q and q_norm == final_q:
            result = build_final_artifact_result(q, final_report, final_answer_markdown_path)
        else:
            hv2_result = find_hybrid_query_result(hybrid_v2, q)
            result = build_dynamic_result(q, hv2_result, max_claims=max_claims, min_claims_for_answer=min_claims_for_answer)
        results.append(result)
        all_claims.extend([dict(c) for c in as_list(result.get("final_claims")) if isinstance(c, Mapping)])
        all_blocked.extend([dict(b) for b in as_list(result.get("blocked_claims")) if isinstance(b, Mapping)])

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "DYNAMIC_FINAL_GATE_EXECUTION_BUILT",
        "generated_at": now_iso(),
        "query_results": results,
        "final_claims": all_claims,
        "blocked_claims": all_blocked,
        "source_artifacts": {
            "hybrid_v2_report": str(hybrid_v2_report_path),
            "final_answer_report": str(final_answer_report_path or ""),
            "final_answer_markdown": str(final_answer_markdown_path or ""),
        },
        "source_quality_statuses": {
            "hybrid_v2": quality_status(hybrid_v2),
            "final_answer_gate": final_quality,
        },
        "read_only": True,
        "writeback_mode": "dynamic_final_gate_dry_run_only",
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed": False,
    }
    report["summary"] = summarize(report)
    qreport = quality_report(
        report,
        min_queries=min_queries,
        min_results=min_results,
        require_hybrid_v2_quality_pass=require_hybrid_v2_quality_pass,
        require_final_answer_quality_pass=require_final_answer_quality_pass,
    )
    report["quality_status"] = qreport["status"]
    report["quality_checks"] = qreport["checks"]
    report["summary"]["status"] = qreport["status"]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / DEFAULT_OUTPUT_FILE
    results_path = out_dir / DEFAULT_RESULTS_FILE
    claims_path = out_dir / DEFAULT_CLAIMS_FILE
    blocked_path = out_dir / DEFAULT_BLOCKED_FILE
    summary_path = out_dir / DEFAULT_SUMMARY_FILE
    quality_path = out_dir / DEFAULT_QUALITY_FILE
    manifest_path = out_dir / DEFAULT_MANIFEST_FILE
    md_path = out_dir / DEFAULT_MD_FILE
    html_path = out_dir / DEFAULT_HTML_FILE
    write_json(report_path, report)
    write_jsonl(results_path, results)
    write_jsonl(claims_path, all_claims)
    write_jsonl(blocked_path, all_blocked)
    write_json(summary_path, report["summary"])
    write_json(quality_path, qreport)
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "report_path": str(report_path),
        "results_path": str(results_path),
        "claims_path": str(claims_path),
        "blocked_path": str(blocked_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_artifacts": report["source_artifacts"],
    })
    md = render_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["quality_path"] = str(quality_path)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Dynamic Final-Gate Execution v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "dynamic_gate_query_count",
        "final_answer_allowed_count",
        "dynamic_final_gate_approved_count",
        "final_artifact_answer_count",
        "retrieval_only_result_count",
        "final_claim_count",
        "blocked_claim_count",
        "uncited_final_claim_count",
        "retrieval_only_final_claim_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Query Results", ""])
    for result in as_list(report.get("query_results")):
        if not isinstance(result, Mapping):
            continue
        lines.append(f"### {result.get('query')}")
        lines.append(f"- answer_status: {result.get('answer_status')}")
        lines.append(f"- final_answer_allowed: {result.get('final_answer_allowed')}")
        if result.get("final_answer_text"):
            lines.append("")
            lines.append(as_text(result.get("final_answer_text"))[:2000])
        else:
            lines.append(f"- retrieval_group_count: {result.get('retrieval_group_count')}")
            lines.append(f"- blocked_claim_count: {result.get('blocked_claim_count')}")
        lines.append("")
    lines.append("Safety: dynamic retrieval groups become final claims only after citation, page, and authority checks.")
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    body = "\n".join(
        f"<p>{html.escape(line)}</p>" if line.strip() else ""
        for line in markdown_text.splitlines()
    )
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Dynamic Final-Gate Execution v1</title></head><body>" + body + "</body></html>\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Dynamic Final-Gate Execution v1 artifacts.")
    parser.add_argument("--hybrid-v2-report", default=str(DEFAULT_HYBRID_V2_REPORT))
    parser.add_argument("--final-answer-report", default=str(DEFAULT_FINAL_ANSWER_REPORT))
    parser.add_argument("--final-answer-markdown", default=str(DEFAULT_FINAL_ANSWER_MD))
    parser.add_argument("--query-file", default=None)
    parser.add_argument("--query", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-claims", type=int, default=8)
    parser.add_argument("--min-claims-for-answer", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-results", type=int, default=1)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-final-answer-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    report = build_dynamic_final_gate_execution(
        hybrid_v2_report_path=args.hybrid_v2_report,
        final_answer_report_path=args.final_answer_report,
        final_answer_markdown_path=args.final_answer_markdown,
        query_file=args.query_file,
        query=args.query,
        output_dir=args.output_dir,
        max_claims=args.max_claims,
        min_claims_for_answer=args.min_claims_for_answer,
        min_queries=args.min_queries,
        min_results=args.min_results,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_final_answer_quality_pass=args.require_final_answer_quality_pass,
    )
    summary = report["summary"]
    print("TRACE-Net Dynamic Final-Gate Execution v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" dynamic_gate_query_count: {summary.get('dynamic_gate_query_count')}")
    print(f" final_answer_allowed_count: {summary.get('final_answer_allowed_count')}")
    print(f" dynamic_final_gate_approved_count: {summary.get('dynamic_final_gate_approved_count')}")
    print(f" final_artifact_answer_count: {summary.get('final_artifact_answer_count')}")
    print(f" retrieval_only_result_count: {summary.get('retrieval_only_result_count')}")
    print(f" final_claim_count: {summary.get('final_claim_count')}")
    print(f" blocked_claim_count: {summary.get('blocked_claim_count')}")
    print(f" uncited_final_claim_count: {summary.get('uncited_final_claim_count')}")
    print(f" retrieval_only_final_claim_count: {summary.get('retrieval_only_final_claim_count')}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
