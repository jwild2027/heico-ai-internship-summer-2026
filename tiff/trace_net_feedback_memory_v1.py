"""TRACE-Net Feedback Memory v1.

Step 21 stores UI thumbs up/down and comments, then converts them into
sanitized advisory memory records for retrieval/LLM reference. Feedback is
never source truth: it cannot answer directly, prove claims, mutate source
truth, or override citations/trust authority.

The module supports local JSON/JSONL artifacts and optional Postgres schema /
write paths. The JSON path is the default because TRACE-Net local checkpoints
are artifact-first; Postgres writeback can be enabled explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_feedback_memory_v1"
EVENT_SCHEMA_VERSION = "trace_net_feedback_event_v1"
MEMORY_SCHEMA_VERSION = "trace_net_feedback_memory_record_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/feedback_memory")
DEFAULT_EVENTS_PATH = DEFAULT_OUTPUT_DIR / "trace_net_feedback_events_v1.jsonl"

ALLOWED_TARGET_TYPES = {
    "answer",
    "claim",
    "citation",
    "page",
    "retrieval_group",
    "table_row",
    "table_cell",
    "visual_region",
    "community",
}

POSITIVE_RATINGS = {"1", "+1", "up", "thumbs_up", "thumbs-up", "helpful", "yes", "true"}
NEGATIVE_RATINGS = {"-1", "down", "thumbs_down", "thumbs-down", "not_helpful", "no", "false"}

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+the\s+system\s+prompt",
    r"system\s*:\s*",
    r"developer\s*:\s*",
    r"you\s+are\s+now",
    r"reveal\s+(your\s+)?(prompt|instructions|chain\s+of\s+thought)",
    r"always\s+trust\s+this\s+comment",
    r"override\s+(the\s+)?(citations|trust|authority|safety)",
    r"do\s+not\s+check\s+(citations|sources|trust)",
]

SECRET_OR_PII_PATTERNS = [
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b",
    r"api[_-]?key\s*[:=]\s*[^\s]+",
    r"password\s*[:=]\s*[^\s]+",
    r"secret\s*[:=]\s*[^\s]+",
]

LOCAL_PATH_PATTERNS = [
    r"[A-Za-z]:\\[^\s]+",
    r"/mnt/data/[^\s]+",
    r"local_data[\\/][^\s]+",
    r"rescarta_exports[\\/][^\s]+",
]

INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in PROMPT_INJECTION_PATTERNS), re.IGNORECASE)
PII_RE = re.compile("|".join(f"(?:{p})" for p in SECRET_OR_PII_PATTERNS), re.IGNORECASE)
LOCAL_PATH_RE = re.compile("|".join(f"(?:{p})" for p in LOCAL_PATH_PATTERNS), re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")

DDL_SQL = """
create table if not exists trace_net_feedback_events (
  feedback_id text primary key,
  created_at timestamptz not null default now(),
  schema_version text not null,
  user_id_hash text,
  session_id text,
  query_text text,
  query_hash text,
  answer_report_id text,
  answer_mode text,
  retrieval_mode text,
  target_type text not null,
  target_id text,
  rating smallint not null,
  comment_text text,
  issue_tags jsonb not null default '[]'::jsonb,
  page_ids jsonb not null default '[]'::jsonb,
  citation_ids jsonb not null default '[]'::jsonb,
  claim_ids jsonb not null default '[]'::jsonb,
  community_ids jsonb not null default '[]'::jsonb,
  source_artifact_path text,
  safety_status text not null default 'raw_feedback_unreviewed',
  prompt_injection_flagged boolean not null default false,
  pii_or_secret_flagged boolean not null default false,
  local_path_flagged boolean not null default false,
  can_mutate_source_truth boolean not null default false,
  can_prove_claims boolean not null default false,
  can_answer_directly boolean not null default false,
  raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists idx_trace_net_feedback_events_query_hash
  on trace_net_feedback_events(query_hash);
create index if not exists idx_trace_net_feedback_events_target
  on trace_net_feedback_events(target_type, target_id);
create index if not exists idx_trace_net_feedback_events_created_at
  on trace_net_feedback_events(created_at);

create table if not exists trace_net_feedback_memory_records (
  memory_id text primary key,
  created_at timestamptz not null default now(),
  schema_version text not null,
  source_feedback_ids jsonb not null default '[]'::jsonb,
  query_hash text,
  query_text_redacted text,
  target_type text not null,
  target_id text,
  page_ids jsonb not null default '[]'::jsonb,
  citation_ids jsonb not null default '[]'::jsonb,
  claim_ids jsonb not null default '[]'::jsonb,
  community_ids jsonb not null default '[]'::jsonb,
  feedback_summary text not null,
  feedback_signal text not null,
  rating_score numeric not null default 0,
  authority text not null default 'feedback_advisory_only',
  record_type text not null default 'feedback_memory',
  safety_bucket text not null default 'feedback_memory_advisory',
  llm_reference_allowed boolean not null default true,
  retrieval_advisory_allowed boolean not null default true,
  can_answer_directly boolean not null default false,
  can_prove_claims boolean not null default false,
  can_mutate_source_truth boolean not null default false,
  requires_source_resolution boolean not null default true,
  requires_citation boolean not null default true,
  requires_authority_gate boolean not null default true,
  reviewed boolean not null default false,
  review_status text not null default 'unreviewed',
  sanitized_payload jsonb not null default '{}'::jsonb
);

create index if not exists idx_trace_net_feedback_memory_target
  on trace_net_feedback_memory_records(target_type, target_id);
create index if not exists idx_trace_net_feedback_memory_query_hash
  on trace_net_feedback_memory_records(query_hash);
create index if not exists idx_trace_net_feedback_memory_created_at
  on trace_net_feedback_memory_records(created_at);
""".strip() + "\n"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def stable_hash(*parts: Any, length: int = 16) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash(*parts, length=16)}"


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, tuple):
        values = list(value)
    else:
        values = [value]
    return [str(v) for v in values if v is not None and str(v) != ""]


def normalize_rating(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else -1
    if isinstance(value, (int, float)):
        return 1 if value > 0 else -1 if value < 0 else 0
    text = str(value or "").strip().lower()
    if text in POSITIVE_RATINGS:
        return 1
    if text in NEGATIVE_RATINGS:
        return -1
    try:
        number = float(text)
        return 1 if number > 0 else -1 if number < 0 else 0
    except ValueError:
        raise ValueError(f"Unsupported rating value: {value!r}")


def compact_text(text: str, max_chars: int = 1200) -> str:
    text = WHITESPACE_RE.sub(" ", str(text or "")).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def redact_text(text: str, max_chars: int = 1200) -> tuple[str, dict[str, bool]]:
    original = str(text or "")
    flags = {
        "prompt_injection_flagged": bool(INJECTION_RE.search(original)),
        "pii_or_secret_flagged": bool(PII_RE.search(original)),
        "local_path_flagged": bool(LOCAL_PATH_RE.search(original)),
    }
    redacted = INJECTION_RE.sub("[PROMPT_INJECTION_REDACTED]", original)
    redacted = PII_RE.sub("[REDACTED]", redacted)
    redacted = LOCAL_PATH_RE.sub("[LOCAL_PATH_REDACTED]", redacted)
    return compact_text(redacted, max_chars=max_chars), flags


def query_hash(query_text: str | None) -> str | None:
    if not query_text:
        return None
    return stable_hash(compact_text(query_text).lower(), length=20)


def normalize_target_type(target_type: str) -> str:
    target_type = str(target_type or "answer").strip().lower().replace("-", "_")
    if target_type not in ALLOWED_TARGET_TYPES:
        raise ValueError(f"Unsupported target_type {target_type!r}; expected one of {sorted(ALLOWED_TARGET_TYPES)}")
    return target_type


def load_final_answer_report(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return read_json(p)


def default_target_id(target_type: str, answer_report: Mapping[str, Any] | None, explicit_target_id: str | None) -> str:
    if explicit_target_id:
        return explicit_target_id
    if target_type == "answer" and answer_report:
        return str(
            answer_report.get("report_id")
            or answer_report.get("schema_version")
            or answer_report.get("answer_status")
            or "trace_net_answer"
        )
    return f"{target_type}:unspecified"


def make_feedback_event(
    *,
    query_text: str | None,
    rating: Any,
    target_type: str = "answer",
    target_id: str | None = None,
    comment_text: str | None = None,
    issue_tags: Sequence[str] | None = None,
    page_ids: Sequence[str] | None = None,
    citation_ids: Sequence[str] | None = None,
    claim_ids: Sequence[str] | None = None,
    community_ids: Sequence[str] | None = None,
    answer_report_path: str | Path | None = None,
    answer_mode: str | None = None,
    retrieval_mode: str | None = None,
    user_id_hash: str | None = None,
    session_id: str | None = None,
    source_artifact_path: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    answer_report = load_final_answer_report(answer_report_path)
    target_type_norm = normalize_target_type(target_type)
    rating_norm = normalize_rating(rating)
    qhash = query_hash(query_text)
    redacted_comment, comment_flags = redact_text(comment_text or "")
    target_id_final = default_target_id(target_type_norm, answer_report, target_id)

    if answer_report:
        answer_mode = answer_mode or str(answer_report.get("answer_mode") or answer_report.get("summary", {}).get("answer_mode") or "")
        retrieval_mode = retrieval_mode or str(answer_report.get("retrieval_mode") or answer_report.get("summary", {}).get("retrieval_mode") or "")
        if not page_ids:
            page_ids = as_list(answer_report.get("summary", {}).get("page_ids") or answer_report.get("page_ids"))
        if not citation_ids:
            citation_ids = as_list(answer_report.get("summary", {}).get("citation_ids") or answer_report.get("citation_ids"))

    feedback_id = stable_id(
        "fb",
        created_at or now_iso(),
        qhash,
        target_type_norm,
        target_id_final,
        rating_norm,
        redacted_comment,
    )
    safety_status = "raw_feedback_flagged_for_review" if any(comment_flags.values()) else "raw_feedback_unreviewed"

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "feedback_id": feedback_id,
        "created_at": created_at or now_iso(),
        "user_id_hash": user_id_hash,
        "session_id": session_id,
        "query_text": compact_text(query_text or "", 1000),
        "query_hash": qhash,
        "answer_report_id": str(answer_report_path) if answer_report_path else None,
        "answer_mode": answer_mode or "",
        "retrieval_mode": retrieval_mode or "",
        "target_type": target_type_norm,
        "target_id": target_id_final,
        "rating": rating_norm,
        "comment_text": comment_text or "",
        "comment_text_redacted": redacted_comment,
        "issue_tags": sorted({str(t).strip().lower().replace(" ", "_") for t in as_list(issue_tags)}),
        "page_ids": sorted(set(as_list(page_ids))),
        "citation_ids": sorted(set(as_list(citation_ids))),
        "claim_ids": sorted(set(as_list(claim_ids))),
        "community_ids": sorted(set(as_list(community_ids))),
        "source_artifact_path": source_artifact_path or (str(answer_report_path) if answer_report_path else None),
        "safety_status": safety_status,
        **comment_flags,
        "can_mutate_source_truth": False,
        "can_prove_claims": False,
        "can_answer_directly": False,
    }


def feedback_signal(event: Mapping[str, Any]) -> str:
    tags = set(as_list(event.get("issue_tags")))
    rating = int(event.get("rating") or 0)
    target_type = str(event.get("target_type") or "answer")
    if event.get("prompt_injection_flagged"):
        return "quarantine_feedback_for_review"
    if {"bad_citation", "missing_citation", "citation_not_supporting_claim"} & tags:
        return "review_citation_or_claim"
    if {"ocr_issue", "wrong_text", "bad_ocr"} & tags:
        return "review_ocr_or_extraction"
    if {"wrong_page", "irrelevant_page"} & tags:
        return "demote_page_for_similar_queries"
    if rating > 0:
        return f"boost_{target_type}_for_similar_queries"
    if rating < 0:
        return f"demote_or_review_{target_type}_for_similar_queries"
    return "neutral_review_signal"


def summarize_feedback(event: Mapping[str, Any]) -> str:
    rating = int(event.get("rating") or 0)
    target_type = str(event.get("target_type") or "target")
    target_id = str(event.get("target_id") or "unspecified")
    sentiment = "helpful" if rating > 0 else "not helpful" if rating < 0 else "neutral"
    comment = compact_text(str(event.get("comment_text_redacted") or ""), 500)
    tags = as_list(event.get("issue_tags"))
    pieces = [f"Prior feedback marked {target_type} {target_id} as {sentiment} for similar queries."]
    if tags:
        pieces.append(f"Tags: {', '.join(tags[:8])}.")
    if comment:
        pieces.append(f"Sanitized comment: {comment}")
    if event.get("prompt_injection_flagged"):
        pieces.append("Prompt-injection-like text was redacted; use only the advisory rating/tag signal.")
    return compact_text(" ".join(pieces), 1000)


def make_memory_record(event: Mapping[str, Any]) -> dict[str, Any]:
    memory_id = stable_id(
        "fbmem",
        event.get("feedback_id"),
        event.get("query_hash"),
        event.get("target_type"),
        event.get("target_id"),
    )
    redacted_query, query_flags = redact_text(str(event.get("query_text") or ""), max_chars=500)
    prompt_injection = bool(event.get("prompt_injection_flagged"))
    review_status = "review_required" if prompt_injection or event.get("pii_or_secret_flagged") else "unreviewed"
    llm_reference_allowed = not prompt_injection
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "memory_id": memory_id,
        "created_at": now_iso(),
        "source_feedback_ids": [str(event.get("feedback_id"))],
        "query_hash": event.get("query_hash"),
        "query_text_redacted": redacted_query,
        "target_type": event.get("target_type"),
        "target_id": event.get("target_id"),
        "page_ids": as_list(event.get("page_ids")),
        "citation_ids": as_list(event.get("citation_ids")),
        "claim_ids": as_list(event.get("claim_ids")),
        "community_ids": as_list(event.get("community_ids")),
        "feedback_summary": summarize_feedback(event),
        "feedback_signal": feedback_signal(event),
        "rating_score": float(event.get("rating") or 0),
        "authority": "feedback_advisory_only",
        "record_type": "feedback_memory",
        "safety_bucket": "feedback_memory_advisory",
        "llm_reference_allowed": llm_reference_allowed,
        "retrieval_advisory_allowed": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "reviewed": False,
        "review_status": review_status,
        "prompt_injection_flagged": prompt_injection,
        "pii_or_secret_flagged": bool(event.get("pii_or_secret_flagged") or query_flags.get("pii_or_secret_flagged")),
        "local_path_flagged": bool(event.get("local_path_flagged") or query_flags.get("local_path_flagged")),
        "sanitized_payload": {
            "issue_tags": as_list(event.get("issue_tags")),
            "comment_text_redacted": event.get("comment_text_redacted") or "",
            "safety_status": event.get("safety_status"),
        },
    }


def load_leiden_community_index(path: str | Path | None) -> dict[str, str]:
    if not path or not Path(path).exists():
        return {}
    payload = read_json(path)
    index: dict[str, str] = {}
    for community in payload.get("communities", []):
        cid = str(community.get("community_id") or "")
        for page_id in as_list(community.get("page_ids")):
            index.setdefault(page_id, cid)
        for part in as_list(community.get("part_numbers")):
            index.setdefault(f"part:{part}", cid)
    return index


def attach_community_hints(memory_records: list[dict[str, Any]], community_index: Mapping[str, str]) -> None:
    if not community_index:
        return
    for record in memory_records:
        community_ids = set(as_list(record.get("community_ids")))
        for page_id in as_list(record.get("page_ids")):
            if page_id in community_index:
                community_ids.add(community_index[page_id])
        if community_ids:
            record["community_ids"] = sorted(community_ids)
            record["sanitized_payload"]["community_hint_source"] = "leiden_graph_communities_v1"


def build_summary(events: list[dict[str, Any]], memories: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "feedback_event_count": len(events),
        "memory_record_count": len(memories),
        "rating_counts": dict(Counter(str(e.get("rating")) for e in events)),
        "target_type_counts": dict(Counter(str(e.get("target_type")) for e in events)),
        "memory_signal_counts": dict(Counter(str(m.get("feedback_signal")) for m in memories)),
        "prompt_injection_flagged_count": sum(1 for e in events if e.get("prompt_injection_flagged")),
        "pii_or_secret_flagged_count": sum(1 for e in events if e.get("pii_or_secret_flagged")),
        "local_path_flagged_count": sum(1 for e in events if e.get("local_path_flagged")),
        "raw_feedback_direct_to_llm_count": raw_feedback_direct_to_llm_count(memories),
        "feedback_can_answer_directly_count": sum(1 for m in memories if m.get("can_answer_directly")),
        "feedback_can_prove_claims_count": sum(1 for m in memories if m.get("can_prove_claims")),
        "feedback_can_mutate_source_truth_count": sum(1 for m in memories if m.get("can_mutate_source_truth")),
        "memory_without_summary_count": sum(1 for m in memories if not m.get("feedback_summary")),
        "memory_without_sanitized_payload_count": sum(1 for m in memories if not isinstance(m.get("sanitized_payload"), Mapping)),
        "missing_target_count": sum(1 for e in events if not e.get("target_type") or not e.get("target_id")),
        "missing_rating_count": sum(1 for e in events if e.get("rating") not in {-1, 0, 1}),
        "llm_reference_allowed_count": sum(1 for m in memories if m.get("llm_reference_allowed")),
        "retrieval_advisory_allowed_count": sum(1 for m in memories if m.get("retrieval_advisory_allowed")),
        "authority_counts": dict(Counter(str(m.get("authority")) for m in memories)),
    }


def raw_feedback_direct_to_llm_count(memories: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    for memory in memories:
        if "comment_text" in memory or "raw_comment_text" in memory:
            count += 1
            continue
        text = json.dumps(memory, sort_keys=True)
        # A memory record may include sanitized redacted text, but should not include explicit raw feedback field names.
        if "raw_feedback_direct_to_llm" in text:
            count += 1
    return count


def evaluate_quality(
    report: Mapping[str, Any],
    *,
    min_feedback_events: int = 1,
    min_memory_records: int = 1,
    require_prompt_injection_flagged: int | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    summary = dict(report.get("summary") or build_summary(report.get("feedback_events", []), report.get("memory_records", [])))
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected})

    add("feedback_event_count", summary.get("feedback_event_count", 0) >= min_feedback_events, summary.get("feedback_event_count", 0), f">= {min_feedback_events}")
    add("memory_record_count", summary.get("memory_record_count", 0) >= min_memory_records, summary.get("memory_record_count", 0), f">= {min_memory_records}")
    add("raw_feedback_direct_to_llm_count", summary.get("raw_feedback_direct_to_llm_count", 0) == 0, summary.get("raw_feedback_direct_to_llm_count", 0), 0)
    add("feedback_can_answer_directly_count", summary.get("feedback_can_answer_directly_count", 0) == 0, summary.get("feedback_can_answer_directly_count", 0), 0)
    add("feedback_can_prove_claims_count", summary.get("feedback_can_prove_claims_count", 0) == 0, summary.get("feedback_can_prove_claims_count", 0), 0)
    add("feedback_can_mutate_source_truth_count", summary.get("feedback_can_mutate_source_truth_count", 0) == 0, summary.get("feedback_can_mutate_source_truth_count", 0), 0)
    add("memory_without_summary_count", summary.get("memory_without_summary_count", 0) == 0, summary.get("memory_without_summary_count", 0), 0)
    add("memory_without_sanitized_payload_count", summary.get("memory_without_sanitized_payload_count", 0) == 0, summary.get("memory_without_sanitized_payload_count", 0), 0)
    add("missing_target_count", summary.get("missing_target_count", 0) == 0, summary.get("missing_target_count", 0), 0)
    add("missing_rating_count", summary.get("missing_rating_count", 0) == 0, summary.get("missing_rating_count", 0), 0)
    if require_prompt_injection_flagged is not None:
        add(
            "prompt_injection_flagged_count",
            summary.get("prompt_injection_flagged_count", 0) >= require_prompt_injection_flagged,
            summary.get("prompt_injection_flagged_count", 0),
            f">= {require_prompt_injection_flagged}",
        )

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return status, checks, summary


def create_schema_artifacts(output_dir: str | Path = DEFAULT_OUTPUT_DIR, *, write_report: bool = True) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    schema_path = output / "trace_net_feedback_memory_v1_schema.sql"
    schema_path.write_text(DDL_SQL, encoding="utf-8")
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "SCHEMA_WRITTEN",
        "created_at": now_iso(),
        "schema_path": str(schema_path),
        "tables": ["trace_net_feedback_events", "trace_net_feedback_memory_records"],
        "authority": "feedback_advisory_only",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
    }
    if write_report:
        write_json(output / "trace_net_feedback_memory_v1_schema_manifest.json", report)
    return report


def execute_postgres_schema(database_url: str, sql: str = DDL_SQL) -> None:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("psycopg is required for --write-postgres") from exc
    with psycopg.connect(database_url) as conn:  # pragma: no cover - requires external DB
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def insert_event_postgres(database_url: str, event: Mapping[str, Any]) -> None:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for --write-postgres") from exc
    sql = """
    insert into trace_net_feedback_events (
      feedback_id, created_at, schema_version, user_id_hash, session_id,
      query_text, query_hash, answer_report_id, answer_mode, retrieval_mode,
      target_type, target_id, rating, comment_text, issue_tags, page_ids,
      citation_ids, claim_ids, community_ids, source_artifact_path,
      safety_status, prompt_injection_flagged, pii_or_secret_flagged,
      local_path_flagged, can_mutate_source_truth, can_prove_claims,
      can_answer_directly, raw_payload
    ) values (
      %(feedback_id)s, %(created_at)s, %(schema_version)s, %(user_id_hash)s, %(session_id)s,
      %(query_text)s, %(query_hash)s, %(answer_report_id)s, %(answer_mode)s, %(retrieval_mode)s,
      %(target_type)s, %(target_id)s, %(rating)s, %(comment_text)s, %(issue_tags)s::jsonb, %(page_ids)s::jsonb,
      %(citation_ids)s::jsonb, %(claim_ids)s::jsonb, %(community_ids)s::jsonb, %(source_artifact_path)s,
      %(safety_status)s, %(prompt_injection_flagged)s, %(pii_or_secret_flagged)s,
      %(local_path_flagged)s, %(can_mutate_source_truth)s, %(can_prove_claims)s,
      %(can_answer_directly)s, %(raw_payload)s::jsonb
    ) on conflict (feedback_id) do nothing
    """
    params = dict(event)
    for key in ["issue_tags", "page_ids", "citation_ids", "claim_ids", "community_ids"]:
        params[key] = json.dumps(params.get(key) or [])
    params["raw_payload"] = json.dumps(event)
    with psycopg.connect(database_url) as conn:  # pragma: no cover
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def build_feedback_memory(
    *,
    feedback_events_path: str | Path = DEFAULT_EVENTS_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    final_answer_report_path: str | Path | None = None,
    leiden_communities_path: str | Path | None = None,
    min_feedback_events: int = 1,
    min_memory_records: int = 1,
    write_quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    events = read_jsonl(feedback_events_path)
    memories = [make_memory_record(e) for e in events]
    community_index = load_leiden_community_index(leiden_communities_path)
    attach_community_hints(memories, community_index)
    summary = build_summary(events, memories)
    status, checks, summary = evaluate_quality(
        {"summary": summary, "feedback_events": events, "memory_records": memories},
        min_feedback_events=min_feedback_events,
        min_memory_records=min_memory_records,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "FEEDBACK_MEMORY_BUILT",
        "quality_status": status,
        "created_at": now_iso(),
        "feedback_events_path": str(feedback_events_path),
        "final_answer_report_path": str(final_answer_report_path) if final_answer_report_path else None,
        "leiden_communities_path": str(leiden_communities_path) if leiden_communities_path else None,
        "feedback_events": events,
        "memory_records": memories,
        "summary": summary,
        "quality": {"status": status, "checks": checks},
        "authority": "feedback_advisory_only",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
    }

    report_path = output / "trace_net_feedback_memory_v1.json"
    memory_path = output / "trace_net_feedback_memory_v1_records.jsonl"
    event_snapshot_path = output / "trace_net_feedback_memory_v1_events_snapshot.jsonl"
    summary_path = output / "trace_net_feedback_memory_v1_summary.json"
    manifest_path = output / "trace_net_feedback_memory_v1_manifest.json"
    quality_path = output / "trace_net_feedback_memory_v1_quality.json"
    markdown_path = output / "trace_net_feedback_memory_v1.md"
    html_path = output / "trace_net_feedback_memory_v1.html"

    write_json(report_path, report)
    write_jsonl(memory_path, memories)
    write_jsonl(event_snapshot_path, events)
    write_json(summary_path, summary)
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "status": report["status"],
        "quality_status": status,
        "created_at": report["created_at"],
        "report_path": str(report_path),
        "memory_path": str(memory_path),
        "event_snapshot_path": str(event_snapshot_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
    })
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": status, "summary": summary, "checks": checks})
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")

    report.update({
        "report_path": str(report_path),
        "memory_path": str(memory_path),
        "event_snapshot_path": str(event_snapshot_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
    })
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Feedback Memory v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "**Authority:** feedback_advisory_only",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "feedback_event_count",
        "memory_record_count",
        "prompt_injection_flagged_count",
        "raw_feedback_direct_to_llm_count",
        "feedback_can_answer_directly_count",
        "feedback_can_prove_claims_count",
        "feedback_can_mutate_source_truth_count",
        "llm_reference_allowed_count",
        "retrieval_advisory_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Memory records", ""])
    for rec in report.get("memory_records", [])[:20]:
        lines.append(f"- **{rec.get('memory_id')}**: {rec.get('feedback_summary')} ({rec.get('feedback_signal')})")
    lines.extend(["", "Feedback is advisory only. It cannot prove claims, answer directly, mutate source truth, or override citations/trust authority.", ""])
    return "\n".join(lines)


def render_html(report: Mapping[str, Any]) -> str:
    md = render_markdown(report)
    return "<html><body><pre>" + html.escape(md) + "</pre></body></html>\n"


def quality_report(
    report_path: str | Path,
    *,
    min_feedback_events: int = 1,
    min_memory_records: int = 1,
    require_prompt_injection_flagged: int | None = None,
    write_json_flag: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    status, checks, summary = evaluate_quality(
        report,
        min_feedback_events=min_feedback_events,
        min_memory_records=min_memory_records,
        require_prompt_injection_flagged=require_prompt_injection_flagged,
    )
    quality = {"schema_version": SCHEMA_VERSION, "status": status, "summary": summary, "checks": checks, "report_path": str(report_path)}
    if write_json_flag:
        out = Path(report_path).with_name("trace_net_feedback_memory_v1_quality.json")
        write_json(out, quality)
        quality["quality_path"] = str(out)
    return quality


def init_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize TRACE-Net feedback memory schema artifacts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--database-url", default="")
    parser.add_argument("--write-postgres", action="store_true")
    args = parser.parse_args(argv)
    report = create_schema_artifacts(args.output_dir)
    if args.write_postgres:
        if not args.database_url:
            parser.error("--database-url is required with --write-postgres")
        execute_postgres_schema(args.database_url)
        report["postgres_schema_written"] = True
    print("TRACE-Net feedback memory v1 schema")
    print(" Status: SCHEMA_WRITTEN")
    print(" schema_path:", report["schema_path"])
    if args.write_postgres:
        print(" postgres_schema_written: True")
    return 0


def record_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one TRACE-Net feedback event.")
    parser.add_argument("--feedback-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--events-path", default="")
    parser.add_argument("--query", required=True)
    parser.add_argument("--rating", required=True)
    parser.add_argument("--comment", default="")
    parser.add_argument("--target-type", default="answer", choices=sorted(ALLOWED_TARGET_TYPES))
    parser.add_argument("--target-id", default="")
    parser.add_argument("--issue-tag", action="append", default=[])
    parser.add_argument("--page-id", action="append", default=[])
    parser.add_argument("--citation-id", action="append", default=[])
    parser.add_argument("--claim-id", action="append", default=[])
    parser.add_argument("--community-id", action="append", default=[])
    parser.add_argument("--answer-report", default="")
    parser.add_argument("--answer-mode", default="")
    parser.add_argument("--retrieval-mode", default="")
    parser.add_argument("--user-id-hash", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--write-postgres", action="store_true")
    args = parser.parse_args(argv)
    feedback_dir = Path(args.feedback_dir)
    events_path = Path(args.events_path) if args.events_path else feedback_dir / "trace_net_feedback_events_v1.jsonl"
    event = make_feedback_event(
        query_text=args.query,
        rating=args.rating,
        target_type=args.target_type,
        target_id=args.target_id or None,
        comment_text=args.comment,
        issue_tags=args.issue_tag,
        page_ids=args.page_id,
        citation_ids=args.citation_id,
        claim_ids=args.claim_id,
        community_ids=args.community_id,
        answer_report_path=args.answer_report or None,
        answer_mode=args.answer_mode or None,
        retrieval_mode=args.retrieval_mode or None,
        user_id_hash=args.user_id_hash or None,
        session_id=args.session_id or None,
        source_artifact_path=args.answer_report or None,
    )
    feedback_dir.mkdir(parents=True, exist_ok=True)
    create_schema_artifacts(feedback_dir)
    append_jsonl(events_path, event)
    if args.write_postgres:
        if not args.database_url:
            parser.error("--database-url is required with --write-postgres")
        execute_postgres_schema(args.database_url)
        insert_event_postgres(args.database_url, event)
    print("TRACE-Net feedback event v1")
    print(" Status: RECORDED")
    print(" feedback_id:", event["feedback_id"])
    print(" target_type:", event["target_type"])
    print(" target_id:", event["target_id"])
    print(" rating:", event["rating"])
    print(" prompt_injection_flagged:", event["prompt_injection_flagged"])
    print(" events_path:", events_path)
    return 0


def build_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net sanitized feedback memory records.")
    parser.add_argument("--feedback-events", default=str(DEFAULT_EVENTS_PATH))
    parser.add_argument("--final-answer-report", default="")
    parser.add_argument("--leiden-communities", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-feedback-events", type=int, default=1)
    parser.add_argument("--min-memory-records", type=int, default=1)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    report = build_feedback_memory(
        feedback_events_path=args.feedback_events,
        output_dir=args.output_dir,
        final_answer_report_path=args.final_answer_report or None,
        leiden_communities_path=args.leiden_communities or None,
        min_feedback_events=args.min_feedback_events,
        min_memory_records=args.min_memory_records,
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net feedback memory v1")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    for key in [
        "feedback_event_count",
        "memory_record_count",
        "prompt_injection_flagged_count",
        "raw_feedback_direct_to_llm_count",
        "feedback_can_answer_directly_count",
        "feedback_can_prove_claims_count",
        "feedback_can_mutate_source_truth_count",
        "llm_reference_allowed_count",
        "retrieval_advisory_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(" report_path:", report["report_path"])
    print(" memory_path:", report["memory_path"])
    if args.quality:
        print(" quality_path:", report["quality_path"])
    return 0 if report["quality_status"] == "PASS" else 1


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net feedback memory quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-feedback-events", type=int, default=1)
    parser.add_argument("--min-memory-records", type=int, default=1)
    parser.add_argument("--require-prompt-injection-flagged", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    report = quality_report(
        args.report_path,
        min_feedback_events=args.min_feedback_events,
        min_memory_records=args.min_memory_records,
        require_prompt_injection_flagged=args.require_prompt_injection_flagged,
        write_json_flag=args.write_json,
    )
    summary = report["summary"]
    print("TRACE-Net feedback memory v1 quality")
    print(" Status:", report["status"])
    for key in [
        "feedback_event_count",
        "memory_record_count",
        "prompt_injection_flagged_count",
        "raw_feedback_direct_to_llm_count",
        "feedback_can_answer_directly_count",
        "feedback_can_prove_claims_count",
        "feedback_can_mutate_source_truth_count",
        "missing_target_count",
        "missing_rating_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        print(" quality_path:", report.get("quality_path"))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(build_main())
