"""TRACE-Net Ask Hybrid Flag v1.

Step 9 wires the Ollama/Qdrant hybrid retriever into an ask-facing command,
but only behind an explicit ``--retrieval-mode hybrid-simulate`` flag.

This module is deliberately conservative:

* It requires the Step 8 regression evaluation to pass before hybrid ask mode is
  allowed.
* It runs the Step 7 hybrid retriever for the user's query and writes ask-style
  artifacts.
* It does not generate a final answer, call an LLM answer composer, mutate
  source truth, or treat vector payloads as proof.
* It marks every result as retrieval-only and requiring source/citation/authority
  resolution before a future answer composer may use it.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import inspect
import json
import os
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tiff.trace_net_hybrid_retrieval_sim_v1 import (  # type: ignore
    DEFAULT_CANDIDATE_COLLECTION,
    DEFAULT_EMBEDDING_CANDIDATES,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODE,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_PAGE_PROFILE_COLLECTION,
    DEFAULT_PAGE_PROFILES,
    DEFAULT_QDRANT_URL,
    run_hybrid_retrieval_sim,
)

SCHEMA_VERSION = "trace_net_ask_hybrid_flag_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask_hybrid_flag")
DEFAULT_HYBRID_RUNTIME_DIR = DEFAULT_OUTPUT_DIR / "hybrid_runtime"
DEFAULT_REGRESSION_REPORT = Path("local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1.json")
DEFAULT_VECTOR_SMOKE_REPORT = Path("local_data/organization/trace_net/vector_search_smoke/trace_net_vector_search_smoke_v1.json")
DEFAULT_ASK_REPORT_FILE = "trace_net_ask_hybrid_flag_v1.json"
DEFAULT_ASK_GROUPS_FILE = "trace_net_ask_hybrid_flag_v1_groups.jsonl"
DEFAULT_ASK_SUMMARY_FILE = "trace_net_ask_hybrid_flag_v1_summary.json"
DEFAULT_ASK_MANIFEST_FILE = "trace_net_ask_hybrid_flag_v1_manifest.json"
DEFAULT_ASK_QUALITY_FILE = "trace_net_ask_hybrid_flag_v1_quality.json"
DEFAULT_ASK_MD_FILE = "trace_net_ask_hybrid_flag_v1.md"
DEFAULT_ASK_HTML_FILE = "trace_net_ask_hybrid_flag_v1.html"
RETRIEVAL_MODES = {"off", "hybrid-simulate"}
SAFE_BUCKETS_FOR_RETRIEVAL = {
    "page_retrieval_profile",
    "context_retrieval_helper",
    "source_evidence",
    "source_text_evidence",
    "verified_part_evidence",
    "derived_context",
}
FORBIDDEN_USE = [
    "direct_answer_from_vector_hit",
    "claim_proof_from_vector_payload",
    "source_truth_mutation",
    "trust_tier_override",
    "citation_replacement",
    "answer_without_source_resolution",
]


class AskHybridFlagError(RuntimeError):
    """Raised when guarded hybrid ask mode cannot run safely."""


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


def as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not Path(path).exists():
        return rows
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, Mapping):
                rows.append(dict(row))
    return rows


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_text(value: Any, *, max_chars: int = 4000) -> str:
    text = " ".join(as_text(value).replace("\x00", " ").split())
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def effective_query(*, query: str = "", part_number: str = "", page_id: str = "") -> str:
    if as_text(part_number):
        return as_text(part_number)
    if as_text(page_id):
        return as_text(page_id)
    return as_text(query)


def compatible_hybrid_sim_kwargs(**kwargs: Any) -> dict[str, Any]:
    """Return kwargs supported by the installed Step 7 hybrid simulator.

    The ask flag should be a thin guard around Step 7. Earlier local patches used
    a few prototype Step 7 names such as ``database_url``,
    ``max_groups_per_query``, and ``min_ranked_groups``. The released Step 7
    function does not accept those names. Filtering here keeps the flag wrapper
    compatible with the actual simulator while still allowing tests to monkeypatch
    the simulator with ``**kwargs``.
    """

    signature = inspect.signature(run_hybrid_retrieval_sim)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return dict(kwargs)
    allowed = set(signature.parameters)
    return {key: value for key, value in kwargs.items() if key in allowed}


def load_regression_status(path: Path) -> dict[str, Any]:
    if not Path(path).exists():
        return {
            "present": False,
            "status": "MISSING",
            "quality_status": "MISSING",
            "summary": {},
            "safe": False,
            "path": str(path),
        }
    payload = read_json(Path(path))
    if not isinstance(payload, Mapping):
        return {
            "present": True,
            "status": "INVALID",
            "quality_status": "INVALID",
            "summary": {},
            "safe": False,
            "path": str(path),
        }
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else payload
    status = as_text(quality.get("status") or payload.get("quality_status") or payload.get("status"))
    safe = (
        status == "PASS"
        and as_int(summary.get("case_fail_count")) == 0
        and as_int(summary.get("required_case_missing_count")) == 0
        and as_int(summary.get("case_unsafe_result_count")) == 0
        and as_int(summary.get("case_direct_answer_allowed_count")) == 0
        and as_int(summary.get("case_claim_proof_allowed_count")) == 0
        and as_int(summary.get("case_source_truth_mutation_allowed_count")) == 0
    )
    return {
        "present": True,
        "status": as_text(payload.get("status")),
        "quality_status": status,
        "safe": bool(safe),
        "path": str(path),
        "summary": dict(summary),
    }


def hybrid_quality_status(hybrid_report: Mapping[str, Any]) -> str:
    """Extract PASS/FAIL from either the Step 7 return object or report JSON."""

    quality = hybrid_report.get("quality")
    if isinstance(quality, Mapping) and as_text(quality.get("status")):
        return as_text(quality.get("status"))
    if as_text(hybrid_report.get("quality_status")):
        return as_text(hybrid_report.get("quality_status"))
    status = as_text(hybrid_report.get("status"))
    if status in {"PASS", "FAIL"}:
        return status
    return ""


def hydrate_hybrid_report(hybrid_result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the full Step 7 hybrid report.

    ``run_hybrid_retrieval_sim`` returns a compact runtime object containing
    paths, summary, and quality. The ranked groups live in the full JSON report
    written at ``report_path`` and are also mirrored in ``groups_path``. The ask
    flag must hydrate those files before summarizing; otherwise it can see zero
    groups even though Step 7 passed. This function supports:

    * full in-memory reports with ``results`` or ``query_results``;
    * compact Step 7 runtime returns with ``report_path``;
    * compact Step 7 runtime returns with only ``groups_path``.
    """

    runtime = dict(hybrid_result)
    hydrated = dict(runtime)

    # Prefer current in-memory Step 7 results when they are present. Some local
    # runs leave a previous ``report_path`` on disk; loading that stale file can
    # replace the fresh groups for the user's current query. Only hydrate from
    # disk when the runtime object is compact and does not already contain
    # ``results`` or ``query_results``.
    has_in_memory_results = bool(runtime.get("query_results") or runtime.get("results"))

    report_path = Path(as_text(runtime.get("report_path"))) if as_text(runtime.get("report_path")) else None
    if not has_in_memory_results and report_path and report_path.exists():
        loaded = read_json(report_path)
        if isinstance(loaded, Mapping):
            # Prefer the full Step 7 JSON for semantic report fields, but keep
            # runtime paths returned by the simulator.
            hydrated = dict(loaded)
            for key, value in runtime.items():
                if key.endswith("_path") or key in {"report_path", "results_path", "groups_path", "summary_path", "manifest_path", "quality_path"}:
                    hydrated[key] = value
            if "summary" not in hydrated and isinstance(runtime.get("summary"), Mapping):
                hydrated["summary"] = dict(runtime.get("summary") or {})

    # Fallback: if the full report was not available or did not contain result
    # blocks, hydrate groups directly from the JSONL file Step 7 writes.
    if not (hydrated.get("query_results") or hydrated.get("results")):
        groups_path = Path(as_text(runtime.get("groups_path"))) if as_text(runtime.get("groups_path")) else None
        groups = read_jsonl(groups_path) if groups_path else []
        if groups:
            hydrated["results"] = [
                {
                    "query_id": "ask_inline_001",
                    "query": "",
                    "ranked_groups": groups,
                    "ranked_group_count": len(groups),
                }
            ]

    # Fallback: hydrate quality from the standalone quality JSON if needed.
    if not isinstance(hydrated.get("quality"), Mapping):
        quality_path = Path(as_text(runtime.get("quality_path"))) if as_text(runtime.get("quality_path")) else None
        if quality_path and quality_path.exists():
            quality_payload = read_json(quality_path)
            if isinstance(quality_payload, Mapping):
                hydrated["quality"] = {"status": as_text(quality_payload.get("status")), "checks": quality_payload.get("checks") or []}

    return hydrated


def flatten_hybrid_groups(hybrid_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    results = hybrid_report.get("query_results") or hybrid_report.get("results") or []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        for raw in result.get("ranked_groups") or []:
            if isinstance(raw, Mapping):
                groups.append(dict(raw))
    return groups


def group_is_safe(group: Mapping[str, Any]) -> bool:
    return (
        not (group.get("unsafe_reasons") or [])
        and as_bool(group.get("answer_allowed"), default=False) is False
        and as_bool(group.get("can_answer_directly"), default=False) is False
        and as_bool(group.get("can_prove_claims"), default=False) is False
        and as_bool(group.get("can_mutate_source_truth"), default=False) is False
        and as_bool(group.get("requires_source_resolution"), default=False) is True
        and as_bool(group.get("requires_citation"), default=False) is True
        and as_bool(group.get("requires_authority_gate"), default=False) is True
    )


def compact_group(group: Mapping[str, Any]) -> dict[str, Any]:
    bucket_counts = group.get("bucket_counts") if isinstance(group.get("bucket_counts"), Mapping) else group.get("candidate_buckets")
    authority_counts = group.get("authority_counts") if isinstance(group.get("authority_counts"), Mapping) else {}
    trust_tier_counts = group.get("trust_tier_counts") if isinstance(group.get("trust_tier_counts"), Mapping) else {}
    safe_status = as_text(group.get("safety_status")) == "retrieval_safe" or as_bool(group.get("retrieval_safe"), default=False)
    page_hits = group.get("page_profile_hits") if isinstance(group.get("page_profile_hits"), Sequence) else []
    candidate_hits = group.get("candidate_hits") if isinstance(group.get("candidate_hits"), Sequence) else []
    return {
        "rank": as_int(group.get("rank")),
        "page_id": as_text(group.get("page_id")),
        "page_number": group.get("page_number"),
        "document_id": as_text(group.get("document_id")),
        "ata_code": as_text(group.get("ata_code")),
        "hybrid_score": as_float(group.get("hybrid_score")),
        "safety_status": as_text(group.get("safety_status") or ("retrieval_safe" if safe_status else "unsafe")),
        "retrieval_safe": bool(safe_status),
        "answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "page_profile_hit_count": as_int(group.get("page_profile_hit_count")),
        "candidate_hit_count": as_int(group.get("candidate_hit_count")),
        "answer_support_candidate_count": as_int(group.get("answer_support_candidate_count")),
        "retrieval_only_hit_count": as_int(group.get("retrieval_only_hit_count")),
        "trace_resolved_hit_count": as_int(group.get("trace_resolved_hit_count"), default=as_int(group.get("resolved_hit_count"))),
        "citation_present_hit_count": as_int(group.get("citation_present_hit_count"), default=len(group.get("citation_ids") or [])),
        "context_v2_present": as_bool(group.get("context_v2_present"), default=False),
        "source_trace_present": as_bool(group.get("source_trace_present"), default=False),
        "candidate_buckets": dict(bucket_counts or {}),
        "bucket_counts": dict(bucket_counts or {}),
        "authority_counts": dict(authority_counts),
        "trust_tier_counts": dict(trust_tier_counts),
        "authorities": list(authority_counts.keys()) if authority_counts else list(group.get("authorities") or []),
        "trust_tiers": list(trust_tier_counts.keys()) if trust_tier_counts else list(group.get("trust_tiers") or []),
        "citation_ids": list(group.get("citation_ids") or []),
        "source_urls": list(group.get("source_urls") or []),
        "unsafe_reasons": list(group.get("unsafe_reasons") or []),
        "page_profile_hit_preview": [dict(hit) for hit in page_hits[:2] if isinstance(hit, Mapping)],
        "candidate_hit_preview": [dict(hit) for hit in candidate_hits[:2] if isinstance(hit, Mapping)],
        "forbidden_use": list(FORBIDDEN_USE),
    }


def summarize_groups(groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    unsafe = [g for g in groups if not group_is_safe(g)]
    return {
        "ranked_group_count": len(groups),
        "safe_group_count": len(groups) - len(unsafe),
        "unsafe_group_count": len(unsafe),
        "direct_answer_allowed_group_count": sum(1 for g in groups if as_bool(g.get("answer_allowed"), default=False) or as_bool(g.get("can_answer_directly"), default=False)),
        "claim_proof_allowed_group_count": sum(1 for g in groups if as_bool(g.get("can_prove_claims"), default=False)),
        "source_truth_mutation_allowed_group_count": sum(1 for g in groups if as_bool(g.get("can_mutate_source_truth"), default=False)),
        "source_resolution_required_false_count": sum(1 for g in groups if as_bool(g.get("requires_source_resolution"), default=False) is not True),
        "citation_required_false_count": sum(1 for g in groups if as_bool(g.get("requires_citation"), default=False) is not True),
        "authority_gate_required_false_count": sum(1 for g in groups if as_bool(g.get("requires_authority_gate"), default=False) is not True),
        "top_page_id": as_text(groups[0].get("page_id")) if groups else "",
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Ask Hybrid Flag v1",
        "",
        f"Status: **{report.get('status')}**",
        f"Quality status: **{report.get('quality_status')}**",
        f"Retrieval mode: `{summary.get('retrieval_mode')}`",
        f"Query: `{report.get('query')}`",
        "",
        "> Hybrid retrieval is running in simulation mode only. This report is a retrieval preview, not a final answer.",
        "",
        "## Safety contract",
        "",
        "- Vector and page-profile hits cannot answer directly.",
        "- Vector and page-profile hits cannot prove claims by themselves.",
        "- Every future answer must resolve through source evidence, citation, and trust authority.",
        "- This step does not mutate source truth, trust tiers, citations, Postgres, or Qdrant.",
        "",
        "## Summary",
    ]
    for key in [
        "regression_quality_status",
        "hybrid_quality_status",
        "ranked_group_count",
        "safe_group_count",
        "unsafe_group_count",
        "direct_answer_allowed_group_count",
        "claim_proof_allowed_group_count",
        "source_truth_mutation_allowed_group_count",
        "candidate_collection_count",
        "page_profile_collection_count",
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
    ]:
        if key in summary:
            lines.append(f"- **{key}**: {summary.get(key)}")
    lines.extend(["", "## Top retrieval groups"])
    for group in report.get("top_groups") or []:
        if not isinstance(group, Mapping):
            continue
        lines.append(
            f"- Rank {group.get('rank')}: page `{group.get('page_id')}`, "
            f"score `{group.get('hybrid_score')}`, "
            f"candidate hits `{group.get('candidate_hit_count')}`, "
            f"page hits `{group.get('page_profile_hit_count')}`, "
            f"answer allowed `{group.get('answer_allowed')}`"
        )
    lines.append("")
    return "\n".join(lines)


def render_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return "<!doctype html>\n<meta charset='utf-8'>\n<title>TRACE-Net Ask Hybrid Flag v1</title>\n<pre>" + escaped + "</pre>\n"


def evaluate_ask_hybrid_flag_quality(
    report: Mapping[str, Any],
    *,
    min_ranked_groups: int = 1,
    min_safe_groups: int = 1,
    require_retrieval_mode: str | None = "hybrid-simulate",
    require_regression_quality_pass: bool = True,
    require_hybrid_quality_pass: bool = True,
    require_embedding_dim: int | None = 1024,
) -> QualityResult:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "OK" if ok else "FAIL", "detail": detail})

    check("schema_version", as_text(report.get("schema_version")) == SCHEMA_VERSION, f"schema={report.get('schema_version')}")
    check("status", as_text(report.get("status")) in {"ASK_RAN", "FLAG_OFF"}, f"status={report.get('status')}")
    if require_retrieval_mode:
        check("retrieval_mode", as_text(summary.get("retrieval_mode")) == require_retrieval_mode, f"mode={summary.get('retrieval_mode')}")
    if require_regression_quality_pass:
        check("regression_quality", as_text(summary.get("regression_quality_status")) == "PASS", f"regression={summary.get('regression_quality_status')}")
    if require_hybrid_quality_pass:
        check("hybrid_quality", as_text(summary.get("hybrid_quality_status")) == "PASS", f"hybrid={summary.get('hybrid_quality_status')}")
    check("ranked_groups", as_int(summary.get("ranked_group_count")) >= min_ranked_groups, f"groups={summary.get('ranked_group_count')}; min={min_ranked_groups}")
    check("safe_groups", as_int(summary.get("safe_group_count")) >= min_safe_groups, f"safe={summary.get('safe_group_count')}; min={min_safe_groups}")
    check("unsafe_groups", as_int(summary.get("unsafe_group_count")) == 0, f"unsafe={summary.get('unsafe_group_count')}")
    check("direct_answer_blocked", as_int(summary.get("direct_answer_allowed_group_count")) == 0, f"direct={summary.get('direct_answer_allowed_group_count')}")
    check("claim_proof_blocked", as_int(summary.get("claim_proof_allowed_group_count")) == 0, f"claim={summary.get('claim_proof_allowed_group_count')}")
    check("source_truth_mutation_blocked", as_int(summary.get("source_truth_mutation_allowed_group_count")) == 0, f"mutations={summary.get('source_truth_mutation_allowed_group_count')}")
    check("source_resolution_required", as_int(summary.get("source_resolution_required_false_count")) == 0, f"false={summary.get('source_resolution_required_false_count')}")
    check("citation_required", as_int(summary.get("citation_required_false_count")) == 0, f"false={summary.get('citation_required_false_count')}")
    check("authority_gate_required", as_int(summary.get("authority_gate_required_false_count")) == 0, f"false={summary.get('authority_gate_required_false_count')}")
    if require_embedding_dim is not None:
        check("embedding_dim", as_int(summary.get("embedding_dim")) == int(require_embedding_dim), f"dim={summary.get('embedding_dim')}; expected={require_embedding_dim}")
    check("answer_artifact_policy", as_text(summary.get("answer_status")) == "NOT_COMPOSED_SIMULATION_ONLY", f"answer_status={summary.get('answer_status')}")
    status = "PASS" if all(item["status"] == "OK" for item in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def run_trace_net_ask_hybrid_flag(
    *,
    query: str = "",
    part_number: str = "",
    page_id: str = "",
    retrieval_mode: str = "off",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    hybrid_runtime_dir: Path | None = None,
    regression_report_path: Path = DEFAULT_REGRESSION_REPORT,
    vector_smoke_report_path: Path = DEFAULT_VECTOR_SMOKE_REPORT,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    api_key: str = "",
    candidate_collection: str = DEFAULT_CANDIDATE_COLLECTION,
    page_profile_collection: str = DEFAULT_PAGE_PROFILE_COLLECTION,
    embedding_candidates_path: Path = DEFAULT_EMBEDDING_CANDIDATES,
    page_profiles_path: Path = DEFAULT_PAGE_PROFILES,
    database_url: str | None = None,
    embedding_mode: str = DEFAULT_EMBEDDING_MODE,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    embedding_device: str | None = None,
    ollama_url: str = "",
    top_k: int = 8,
    max_groups: int = 8,
    require_regression_quality_pass: bool = True,
    require_vector_smoke_quality_pass: bool = True,
    require_candidate_count: int | None = 1476,
    require_page_profile_count: int | None = 509,
    require_embedding_dim: int | None = 1024,
    open_result: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    mode = as_text(retrieval_mode) or "off"
    if mode not in RETRIEVAL_MODES:
        raise AskHybridFlagError(f"unsupported retrieval mode: {retrieval_mode}")
    user_query = effective_query(query=query, part_number=part_number, page_id=page_id)
    if not user_query:
        raise AskHybridFlagError("Provide --query, --part-number, or --page-id.")

    output_dir = Path(output_dir)
    hybrid_runtime_dir = Path(hybrid_runtime_dir or (output_dir / "hybrid_runtime"))
    regression = load_regression_status(regression_report_path)
    if mode == "off":
        summary = {
            "retrieval_mode": "off",
            "answer_status": "NOT_COMPOSED_FLAG_OFF",
            "regression_quality_status": regression.get("quality_status"),
            "hybrid_quality_status": "NOT_RUN",
            "ranked_group_count": 0,
            "safe_group_count": 0,
            "unsafe_group_count": 0,
            "direct_answer_allowed_group_count": 0,
            "claim_proof_allowed_group_count": 0,
            "source_truth_mutation_allowed_group_count": 0,
            "source_resolution_required_false_count": 0,
            "citation_required_false_count": 0,
            "authority_gate_required_false_count": 0,
            "embedding_dim": int(embedding_dim),
        }
        report = {
            "schema_version": SCHEMA_VERSION,
            "status": "FLAG_OFF",
            "quality_status": "PASS",
            "created_at_utc": utc_now_iso(),
            "query": user_query,
            "summary": summary,
            "top_groups": [],
            "warnings": ["Hybrid retrieval was not run because --retrieval-mode hybrid-simulate was not provided."],
        }
    else:
        if require_regression_quality_pass and not regression.get("safe"):
            raise AskHybridFlagError(
                f"Step 8 regression quality must PASS before hybrid ask mode. "
                f"path={regression_report_path}; quality={regression.get('quality_status')}"
            )
        hybrid_kwargs = compatible_hybrid_sim_kwargs(
            output_dir=hybrid_runtime_dir,
            qdrant_url=qdrant_url,
            api_key=api_key,
            candidate_collection=candidate_collection,
            page_profile_collection=page_profile_collection,
            embedding_mode=embedding_mode,
            embedding_model=embedding_model,
            embedding_dim=int(embedding_dim),
            embedding_device=embedding_device,
            ollama_url=ollama_url,
            top_k=int(top_k),
            inline_queries=[user_query],
            embedding_candidates_path=embedding_candidates_path,
            page_profiles_path=page_profiles_path,
            vector_smoke_report_path=vector_smoke_report_path,
            max_groups=int(max_groups),
            min_hybrid_queries=1,
            min_queries_with_results=1,
            min_grouped_results=1,
            min_candidate_hits=1,
            min_page_profile_hits=1,
            min_resolved_candidate_hits=1,
            min_resolved_page_profile_hits=1,
            min_candidate_collection_count=1,
            min_page_profile_collection_count=1,
            require_candidate_count=require_candidate_count or 0,
            require_page_profile_count=require_page_profile_count or 0,
            require_embedding_dim=require_embedding_dim or 0,
            require_vector_smoke_quality_pass=require_vector_smoke_quality_pass,
            write_quality=True,
        )
        hybrid_result = run_hybrid_retrieval_sim(**hybrid_kwargs)
        hybrid_report = hydrate_hybrid_report(hybrid_result if isinstance(hybrid_result, Mapping) else {})
        hybrid_summary = hybrid_report.get("summary") if isinstance(hybrid_report.get("summary"), Mapping) else {}
        groups = flatten_hybrid_groups(hybrid_report)[: int(max_groups)]
        compact_groups = [compact_group(group) for group in groups]
        group_summary = summarize_groups(compact_groups)
        summary = {
            "retrieval_mode": "hybrid-simulate",
            "answer_status": "NOT_COMPOSED_SIMULATION_ONLY",
            "regression_quality_status": regression.get("quality_status"),
            "regression_case_fail_count": as_int((regression.get("summary") or {}).get("case_fail_count")) if isinstance(regression.get("summary"), Mapping) else 0,
            "hybrid_quality_status": hybrid_quality_status(hybrid_report),
            "hybrid_status": as_text(hybrid_report.get("status")),
            "candidate_collection_count": as_int(hybrid_summary.get("candidate_collection_count")),
            "page_profile_collection_count": as_int(hybrid_summary.get("page_profile_collection_count")),
            "embedding_mode": as_text(hybrid_summary.get("embedding_mode") or embedding_mode),
            "embedding_model_name": as_text(hybrid_summary.get("embedding_model_name") or embedding_model),
            "embedding_dim": as_int(hybrid_summary.get("embedding_dim"), default=int(embedding_dim)),
            "source_truth_mutations_performed": 0,
            "ask_answer_generated": False,
            "ask_answer_generation_allowed": False,
            "must_resolve_before_answer": True,
            **group_summary,
        }
        report = {
            "schema_version": SCHEMA_VERSION,
            "status": "ASK_RAN",
            "quality_status": "PENDING",
            "created_at_utc": utc_now_iso(),
            "query": user_query,
            "query_inputs": {"query": query, "part_number": part_number, "page_id": page_id},
            "summary": summary,
            "top_groups": compact_groups,
            "hybrid_report_path": hybrid_report.get("report_path"),
            "regression_report_path": str(regression_report_path),
            "forbidden_use": list(FORBIDDEN_USE),
            "warnings": [
                "Hybrid ask flag mode is simulation-only.",
                "This artifact is retrieval preview output, not an answer.",
                "Future answer use must pass source/citation/trust authority gates.",
            ],
        }

    quality = evaluate_ask_hybrid_flag_quality(
        report,
        min_ranked_groups=1 if mode == "hybrid-simulate" else 0,
        min_safe_groups=1 if mode == "hybrid-simulate" else 0,
        require_retrieval_mode="hybrid-simulate" if mode == "hybrid-simulate" else None,
        require_regression_quality_pass=require_regression_quality_pass and mode == "hybrid-simulate",
        require_hybrid_quality_pass=mode == "hybrid-simulate",
        require_embedding_dim=require_embedding_dim,
    )
    report["quality_status"] = quality.status

    report_path = output_dir / DEFAULT_ASK_REPORT_FILE
    groups_path = output_dir / DEFAULT_ASK_GROUPS_FILE
    summary_path = output_dir / DEFAULT_ASK_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_ASK_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_ASK_QUALITY_FILE
    md_path = output_dir / DEFAULT_ASK_MD_FILE
    html_path = output_dir / DEFAULT_ASK_HTML_FILE
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": report.get("status"),
        "quality_status": quality.status,
        "created_at_utc": utc_now_iso(),
        "retrieval_mode": mode,
        "query": user_query,
        "report_path": str(report_path),
        "groups_jsonl_path": str(groups_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "report_sha256": sha256_json(report),
        "summary_sha256": sha256_json(report.get("summary") or {}),
    }
    write_json(report_path, report)
    write_jsonl(groups_path, report.get("top_groups") or [])
    write_json(summary_path, report.get("summary") or {})
    write_json(manifest_path, manifest)
    markdown = render_markdown(report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8", newline="\n")
    html_path.write_text(render_html(markdown), encoding="utf-8", newline="\n")
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary})

    report.update(
        {
            "report_path": str(report_path),
            "groups_jsonl_path": str(groups_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "quality_path": str(quality_path),
            "markdown_path": str(md_path),
            "html_path": str(html_path),
        }
    )
    if open_result:
        try:
            webbrowser.open(html_path.resolve().as_uri())
        except Exception as exc:  # pragma: no cover
            report.setdefault("warnings", []).append(f"Could not open HTML report: {exc}")
            write_json(report_path, report)
    return report


def check_trace_net_ask_hybrid_flag_quality(
    *,
    report_path: Path,
    min_ranked_groups: int = 1,
    min_safe_groups: int = 1,
    require_retrieval_mode: str | None = "hybrid-simulate",
    require_regression_quality_pass: bool = True,
    require_hybrid_quality_pass: bool = True,
    require_embedding_dim: int | None = 1024,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path)
    if not isinstance(payload, Mapping):
        raise AskHybridFlagError(f"ask hybrid flag report is not a JSON object: {report_path}")
    quality = evaluate_ask_hybrid_flag_quality(
        payload,
        min_ranked_groups=min_ranked_groups,
        min_safe_groups=min_safe_groups,
        require_retrieval_mode=require_retrieval_mode,
        require_regression_quality_pass=require_regression_quality_pass,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_embedding_dim=require_embedding_dim,
    )
    output = {"schema_version": SCHEMA_VERSION, "status": quality.status, "checks": quality.checks, "summary": quality.summary}
    if write_json_report:
        quality_path = Path(report_path).parent / DEFAULT_ASK_QUALITY_FILE
        write_json(quality_path, output)
        output["quality_path"] = str(quality_path)
    return output


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def optional_int(value: str) -> int | None:
    if value is None or str(value).strip().lower() in {"", "none", "null"}:
        return None
    return int(value)


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net ask with guarded hybrid retrieval behind a flag.")
    parser.add_argument("--query", default="")
    parser.add_argument("--part-number", default="")
    parser.add_argument("--page-id", default="")
    parser.add_argument("--retrieval-mode", choices=sorted(RETRIEVAL_MODES), default="off")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--hybrid-runtime-dir", type=Path, default=None)
    parser.add_argument("--regression-report", type=Path, default=DEFAULT_REGRESSION_REPORT)
    parser.add_argument("--vector-smoke-report", type=Path, default=DEFAULT_VECTOR_SMOKE_REPORT)
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL") or DEFAULT_QDRANT_URL)
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY") or "")
    parser.add_argument("--candidate-collection", default=DEFAULT_CANDIDATE_COLLECTION)
    parser.add_argument("--page-profile-collection", default=DEFAULT_PAGE_PROFILE_COLLECTION)
    parser.add_argument("--embedding-candidates", type=Path, default=DEFAULT_EMBEDDING_CANDIDATES)
    parser.add_argument("--page-profiles", type=Path, default=DEFAULT_PAGE_PROFILES)
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL") or "")
    parser.add_argument("--embedding-mode", default=DEFAULT_EMBEDDING_MODE)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dim", type=positive_int, default=DEFAULT_EMBEDDING_DIM)
    parser.add_argument("--embedding-device", default=None)
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL") or os.environ.get("TRACE_NET_OLLAMA_URL") or "")
    parser.add_argument("--top-k", "--limit", dest="top_k", type=positive_int, default=8)
    parser.add_argument("--max-groups", type=positive_int, default=8)
    parser.add_argument("--no-require-regression-quality-pass", action="store_true")
    parser.add_argument("--no-require-vector-smoke-quality-pass", action="store_true")
    parser.add_argument("--require-candidate-count", type=optional_int, default=1476)
    parser.add_argument("--require-page-profile-count", type=optional_int, default=509)
    parser.add_argument("--require-embedding-dim", type=optional_int, default=1024)
    parser.add_argument("--open", action="store_true", dest="open_result")
    parser.add_argument("--quality", action="store_true")
    return parser


def run_main(argv: Sequence[str] | None = None) -> int:
    parser = build_run_parser()
    args = parser.parse_args(argv)
    try:
        result = run_trace_net_ask_hybrid_flag(
            query=args.query,
            part_number=args.part_number,
            page_id=args.page_id,
            retrieval_mode=args.retrieval_mode,
            output_dir=args.output_dir,
            hybrid_runtime_dir=args.hybrid_runtime_dir,
            regression_report_path=args.regression_report,
            vector_smoke_report_path=args.vector_smoke_report,
            qdrant_url=args.qdrant_url,
            api_key=args.api_key,
            candidate_collection=args.candidate_collection,
            page_profile_collection=args.page_profile_collection,
            embedding_candidates_path=args.embedding_candidates,
            page_profiles_path=args.page_profiles,
            database_url=args.database_url or None,
            embedding_mode=args.embedding_mode,
            embedding_model=args.embedding_model,
            embedding_dim=args.embedding_dim,
            embedding_device=args.embedding_device,
            ollama_url=args.ollama_url,
            top_k=args.top_k,
            max_groups=args.max_groups,
            require_regression_quality_pass=not args.no_require_regression_quality_pass,
            require_vector_smoke_quality_pass=not args.no_require_vector_smoke_quality_pass,
            require_candidate_count=args.require_candidate_count,
            require_page_profile_count=args.require_page_profile_count,
            require_embedding_dim=args.require_embedding_dim,
            open_result=args.open_result,
            write_quality=args.quality,
        )
    except Exception as exc:
        print(f"TRACE-Net ask hybrid flag failed: {exc}", file=sys.stderr)
        return 1
    summary = result.get("summary", {})
    print("TRACE-Net ask hybrid flag v1")
    print(f" Status: {result.get('status')}")
    print(f" Quality status: {result.get('quality_status')}")
    for key in (
        "retrieval_mode",
        "answer_status",
        "regression_quality_status",
        "hybrid_quality_status",
        "ranked_group_count",
        "safe_group_count",
        "unsafe_group_count",
        "direct_answer_allowed_group_count",
        "claim_proof_allowed_group_count",
        "source_truth_mutation_allowed_group_count",
        "candidate_collection_count",
        "page_profile_collection_count",
        "embedding_mode",
        "embedding_model_name",
        "embedding_dim",
    ):
        if key in summary:
            print(f" {key}: {summary.get(key)}")
    print(f" report_path: {result.get('report_path')}")
    print(f" markdown_path: {result.get('markdown_path')}")
    print(f" html_path: {result.get('html_path')}")
    return 0 if result.get("quality_status") == "PASS" or not args.quality else 1


def build_quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net ask hybrid flag v1 quality.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_ASK_REPORT_FILE)
    parser.add_argument("--min-ranked-groups", type=int, default=1)
    parser.add_argument("--min-safe-groups", type=int, default=1)
    parser.add_argument("--require-retrieval-mode", default="hybrid-simulate")
    parser.add_argument("--no-require-regression-quality-pass", action="store_true")
    parser.add_argument("--no-require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--require-embedding-dim", type=optional_int, default=1024)
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: Sequence[str] | None = None) -> int:
    parser = build_quality_parser()
    args = parser.parse_args(argv)
    try:
        result = check_trace_net_ask_hybrid_flag_quality(
            report_path=args.report_path,
            min_ranked_groups=args.min_ranked_groups,
            min_safe_groups=args.min_safe_groups,
            require_retrieval_mode=args.require_retrieval_mode or None,
            require_regression_quality_pass=not args.no_require_regression_quality_pass,
            require_hybrid_quality_pass=not args.no_require_hybrid_quality_pass,
            require_embedding_dim=args.require_embedding_dim,
            write_json_report=args.write_json,
        )
    except Exception as exc:
        print(f"TRACE-Net ask hybrid flag quality check failed: {exc}", file=sys.stderr)
        return 1
    summary = result.get("summary", {})
    print("TRACE-Net ask hybrid flag v1 quality")
    print(f" Status: {result.get('status')}")
    for key in (
        "retrieval_mode",
        "answer_status",
        "regression_quality_status",
        "hybrid_quality_status",
        "ranked_group_count",
        "safe_group_count",
        "unsafe_group_count",
        "direct_answer_allowed_group_count",
        "claim_proof_allowed_group_count",
        "source_truth_mutation_allowed_group_count",
        "embedding_dim",
    ):
        if key in summary:
            print(f" {key}: {summary.get(key)}")
    if result.get("quality_path"):
        print(f" quality_path: {result.get('quality_path')}")
    return 0 if result.get("status") == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_main())
