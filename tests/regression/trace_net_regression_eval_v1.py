"""TRACE-Net Regression Evaluation v1.

Step 8 compares the Step 7 hybrid retrieval simulation against a small,
source-safe regression set before hybrid retrieval is allowed anywhere near ask.

This module is deliberately read-only. It does not call an LLM, does not mutate
Postgres, does not mutate Qdrant, and does not treat retrieval results as
answers. It evaluates two things:

1. Regression quality: each expected query still returns candidate/page-profile
   hits and grouped page results.
2. TRACE-Net safety: no result is allowed to answer directly, prove claims
   without authority, or mutate source truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_regression_eval_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/regression_eval")
DEFAULT_HYBRID_REPORT = Path(
    "local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json"
)
DEFAULT_REPORT_FILE = "trace_net_regression_eval_v1.json"
DEFAULT_CASES_FILE = "trace_net_regression_eval_v1_cases.jsonl"
DEFAULT_REGRESSION_SET_FILE = "trace_net_regression_set_v1.json"
DEFAULT_SUMMARY_FILE = "trace_net_regression_eval_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_regression_eval_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_regression_eval_v1_quality.json"

DEFAULT_REGRESSION_CASES: list[dict[str, Any]] = [
    {
        "case_id": "manual_revision_history",
        "query_id": "manual_revision_history",
        "description": "Manual revision/title-block routing should still return source-backed retrieval groups.",
        "expected_intent": "route_to_revision_source_page",
        "min_ranked_groups": 3,
        "min_candidate_hits": 3,
        "min_page_profile_hits": 3,
        "min_resolved_candidate_hits": 3,
        "min_resolved_page_profile_hits": 3,
        "require_retrieval_safe_groups": True,
    },
    {
        "case_id": "ata_25_21_placards",
        "query_id": "ata_25_21_placards",
        "description": "ATA placard/label routing should still produce hybrid page and candidate hits.",
        "expected_intent": "route_to_ata_or_page_evidence",
        "min_ranked_groups": 3,
        "min_candidate_hits": 3,
        "min_page_profile_hits": 3,
        "min_resolved_candidate_hits": 3,
        "min_resolved_page_profile_hits": 3,
        "require_retrieval_safe_groups": True,
    },
    {
        "case_id": "part_nomenclature_lookup",
        "query_id": "part_nomenclature_lookup",
        "description": "Part/nomenclature lookup should keep returning resolved candidate and page-profile hits.",
        "expected_intent": "route_to_part_and_nomenclature_evidence",
        "min_ranked_groups": 3,
        "min_candidate_hits": 3,
        "min_page_profile_hits": 3,
        "min_resolved_candidate_hits": 3,
        "min_resolved_page_profile_hits": 3,
        "require_retrieval_safe_groups": True,
    },
    {
        "case_id": "source_trace_page_000001",
        "query_id": "source_trace_page_000001",
        "description": "Source trace query should still resolve page/candidate hits without allowing direct answers.",
        "expected_intent": "route_to_page_source_trace",
        "min_ranked_groups": 3,
        "min_candidate_hits": 3,
        "min_page_profile_hits": 3,
        "min_resolved_candidate_hits": 3,
        "min_resolved_page_profile_hits": 3,
        "require_retrieval_safe_groups": True,
    },
    {
        "case_id": "technical_publication_evidence",
        "query_id": "technical_publication_evidence",
        "description": "Technical publication/source-citation query should keep safe hybrid routing behavior.",
        "expected_intent": "route_to_source_backed_candidates",
        "min_ranked_groups": 3,
        "min_candidate_hits": 3,
        "min_page_profile_hits": 3,
        "min_resolved_candidate_hits": 3,
        "min_resolved_page_profile_hits": 3,
        "require_retrieval_safe_groups": True,
    },
]


class RegressionEvalError(RuntimeError):
    """Raised when regression evaluation cannot be completed safely."""


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


def sha256_json(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_regression_set(path: Path | None = None) -> dict[str, Any]:
    if path:
        payload = read_json(Path(path))
        if isinstance(payload, Mapping):
            cases = payload.get("cases") or payload.get("regression_cases") or []
            return {
                "schema_version": as_text(payload.get("schema_version") or "trace_net_regression_set_v1"),
                "name": as_text(payload.get("name") or "custom_regression_set"),
                "description": as_text(payload.get("description") or "Custom TRACE-Net regression set."),
                "cases": [dict(case) for case in cases if isinstance(case, Mapping)],
            }
        raise RegressionEvalError(f"Regression set at {path} must be a JSON object")
    return {
        "schema_version": "trace_net_regression_set_v1",
        "name": "trace_net_default_hybrid_retrieval_regression_set_v1",
        "description": "Default Step 8 regression cases aligned with Step 7 hybrid simulation queries.",
        "cases": [dict(case) for case in DEFAULT_REGRESSION_CASES],
    }


def hybrid_quality_status(payload: Mapping[str, Any]) -> str:
    quality = payload.get("quality")
    if isinstance(quality, Mapping) and as_text(quality.get("status")):
        return as_text(quality.get("status"))
    if as_text(payload.get("quality_status")):
        return as_text(payload.get("quality_status"))
    return as_text(payload.get("status"))


def report_results(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results") or payload.get("query_results") or []
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def index_results_by_query_id(results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for result in results:
        query_id = as_text(result.get("query_id"))
        if query_id:
            index[query_id] = dict(result)
    return index


def list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def any_direct_answer_allowed(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if as_bool(row.get("answer_allowed"), default=False)
        or as_bool(row.get("can_answer_directly"), default=False)
        or as_bool(row.get("embedding_answer_authority_allowed"), default=False)
    )


def any_claim_proof_allowed(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if as_bool(row.get("can_prove_claims"), default=False))


def source_truth_mutation_allowed(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if as_bool(row.get("can_mutate_source_truth"), default=False))


def unsafe_rows(rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for row in rows:
        reasons = row.get("unsafe_reasons")
        if isinstance(reasons, list) and reasons:
            count += 1
        elif as_text(row.get("safety_status")) and as_text(row.get("safety_status")) not in {"retrieval_safe", "safe"}:
            count += 1
    return count


def count_resolved(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if as_bool(row.get("resolved_to_artifact"), default=False))


def evaluate_regression_case(case: Mapping[str, Any], result_index: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    case_id = as_text(case.get("case_id") or case.get("query_id"))
    query_id = as_text(case.get("query_id") or case_id)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any, expected: Any, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected, "severity": severity})

    result = result_index.get(query_id)
    if result is None:
        add("query_result_exists", False, "missing", query_id)
        return {
            "case_id": case_id,
            "query_id": query_id,
            "status": "FAIL",
            "missing_result": True,
            "checks": checks,
            "ranked_group_count": 0,
            "candidate_hit_count": 0,
            "page_profile_hit_count": 0,
            "resolved_candidate_hit_count": 0,
            "resolved_page_profile_hit_count": 0,
            "unsafe_result_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }

    groups = list_items(result.get("ranked_groups"))
    candidate_hits = list_items(result.get("candidate_hits"))
    page_profile_hits = list_items(result.get("page_profile_hits"))
    all_rows = groups + candidate_hits + page_profile_hits
    ranked_group_count = as_int(result.get("ranked_group_count"), default=len(groups))
    candidate_hit_count = as_int(result.get("candidate_hit_count"), default=len(candidate_hits))
    page_profile_hit_count = as_int(result.get("page_profile_hit_count"), default=len(page_profile_hits))
    resolved_candidate_hit_count = count_resolved(candidate_hits)
    resolved_page_profile_hit_count = count_resolved(page_profile_hits)
    unsafe_count = unsafe_rows(all_rows)
    direct_answer_count = any_direct_answer_allowed(all_rows)
    claim_proof_count = any_claim_proof_allowed(all_rows)
    source_truth_mutation_count = source_truth_mutation_allowed(all_rows)
    top_group = groups[0] if groups else {}
    top_page_id = as_text(top_group.get("page_id"))
    group_page_ids = [as_text(group.get("page_id")) for group in groups if as_text(group.get("page_id"))]
    hit_buckets = {as_text(hit.get("rag_bucket")) for hit in candidate_hits + page_profile_hits if as_text(hit.get("rag_bucket"))}
    hit_authorities = {as_text(hit.get("authority")) for hit in candidate_hits + page_profile_hits if as_text(hit.get("authority"))}

    add("query_result_exists", True, query_id, query_id)
    expected_intent = as_text(case.get("expected_intent"))
    if expected_intent:
        add("intent_matches", as_text(result.get("intent")) == expected_intent, result.get("intent"), expected_intent)
    add(
        "ranked_group_count_min",
        ranked_group_count >= as_int(case.get("min_ranked_groups"), default=1),
        ranked_group_count,
        f">={as_int(case.get('min_ranked_groups'), default=1)}",
    )
    add(
        "candidate_hit_count_min",
        candidate_hit_count >= as_int(case.get("min_candidate_hits"), default=1),
        candidate_hit_count,
        f">={as_int(case.get('min_candidate_hits'), default=1)}",
    )
    add(
        "page_profile_hit_count_min",
        page_profile_hit_count >= as_int(case.get("min_page_profile_hits"), default=1),
        page_profile_hit_count,
        f">={as_int(case.get('min_page_profile_hits'), default=1)}",
    )
    add(
        "resolved_candidate_hit_count_min",
        resolved_candidate_hit_count >= as_int(case.get("min_resolved_candidate_hits"), default=1),
        resolved_candidate_hit_count,
        f">={as_int(case.get('min_resolved_candidate_hits'), default=1)}",
    )
    add(
        "resolved_page_profile_hit_count_min",
        resolved_page_profile_hit_count >= as_int(case.get("min_resolved_page_profile_hits"), default=1),
        resolved_page_profile_hit_count,
        f">={as_int(case.get('min_resolved_page_profile_hits'), default=1)}",
    )
    if as_bool(case.get("require_retrieval_safe_groups"), default=True):
        unsafe_groups = [group for group in groups if as_text(group.get("safety_status")) not in {"retrieval_safe", "safe"}]
        add("ranked_groups_retrieval_safe", len(unsafe_groups) == 0, len(unsafe_groups), 0)
    required_page_ids = {as_text(value) for value in case.get("required_page_ids") or [] if as_text(value)}
    if required_page_ids:
        add("required_page_id_present", bool(required_page_ids.intersection(group_page_ids)), group_page_ids, sorted(required_page_ids))
    forbidden_page_ids = {as_text(value) for value in case.get("forbidden_page_ids") or [] if as_text(value)}
    if forbidden_page_ids:
        add("forbidden_page_id_absent", not bool(forbidden_page_ids.intersection(group_page_ids)), group_page_ids, sorted(forbidden_page_ids))
    required_buckets = {as_text(value) for value in case.get("required_buckets_any") or [] if as_text(value)}
    if required_buckets:
        add("required_bucket_any_present", bool(required_buckets.intersection(hit_buckets)), sorted(hit_buckets), sorted(required_buckets))
    required_authorities = {as_text(value) for value in case.get("required_authorities_any") or [] if as_text(value)}
    if required_authorities:
        add("required_authority_any_present", bool(required_authorities.intersection(hit_authorities)), sorted(hit_authorities), sorted(required_authorities))
    add("unsafe_count_zero", unsafe_count == 0, unsafe_count, 0)
    add("direct_answer_allowed_count_zero", direct_answer_count == 0, direct_answer_count, 0)
    add("claim_proof_allowed_count_zero", claim_proof_count == 0, claim_proof_count, 0)
    add("source_truth_mutation_allowed_count_zero", source_truth_mutation_count == 0, source_truth_mutation_count, 0)

    status = "PASS" if all(check["passed"] or check.get("severity") == "warning" for check in checks) else "FAIL"
    return {
        "case_id": case_id,
        "query_id": query_id,
        "description": as_text(case.get("description")),
        "status": status,
        "missing_result": False,
        "query": as_text(result.get("query")),
        "intent": as_text(result.get("intent")),
        "top_page_id": top_page_id,
        "top_hybrid_score": as_float(top_group.get("hybrid_score"), default=0.0),
        "ranked_group_count": ranked_group_count,
        "candidate_hit_count": candidate_hit_count,
        "page_profile_hit_count": page_profile_hit_count,
        "resolved_candidate_hit_count": resolved_candidate_hit_count,
        "resolved_page_profile_hit_count": resolved_page_profile_hit_count,
        "unsafe_result_count": unsafe_count,
        "direct_answer_allowed_count": direct_answer_count,
        "claim_proof_allowed_count": claim_proof_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_count,
        "group_page_ids": group_page_ids,
        "hit_buckets": sorted(hit_buckets),
        "hit_authorities": sorted(hit_authorities),
        "checks": checks,
    }


def summarize_regression(
    *,
    case_results: Sequence[Mapping[str, Any]],
    hybrid_report: Mapping[str, Any],
    regression_set: Mapping[str, Any],
) -> dict[str, Any]:
    hybrid_summary = dict(hybrid_report.get("summary") or {})
    case_count = len(case_results)
    pass_count = sum(1 for case in case_results if as_text(case.get("status")) == "PASS")
    fail_count = case_count - pass_count
    return {
        "schema_version": SCHEMA_VERSION,
        "regression_set_name": as_text(regression_set.get("name")),
        "hybrid_report_status": as_text(hybrid_report.get("status")),
        "hybrid_quality_status": hybrid_quality_status(hybrid_report),
        "embedding_mode": as_text(hybrid_report.get("embedding_mode") or hybrid_summary.get("embedding_mode")),
        "embedding_model_name": as_text(hybrid_report.get("embedding_model_name") or hybrid_summary.get("embedding_model_name")),
        "embedding_dim": as_int(hybrid_report.get("embedding_dim") or hybrid_summary.get("embedding_dim")),
        "regression_case_count": case_count,
        "case_pass_count": pass_count,
        "case_fail_count": fail_count,
        "case_pass_rate": round((pass_count / case_count) if case_count else 0.0, 6),
        "required_case_missing_count": sum(1 for case in case_results if as_bool(case.get("missing_result"), default=False)),
        "cases_with_results_count": sum(1 for case in case_results if as_bool(case.get("missing_result"), default=False) is False),
        "cases_with_candidate_hits_count": sum(1 for case in case_results if as_int(case.get("candidate_hit_count")) > 0),
        "cases_with_page_profile_hits_count": sum(1 for case in case_results if as_int(case.get("page_profile_hit_count")) > 0),
        "cases_with_grouped_results_count": sum(1 for case in case_results if as_int(case.get("ranked_group_count")) > 0),
        "total_ranked_group_count": sum(as_int(case.get("ranked_group_count")) for case in case_results),
        "total_candidate_hit_count": sum(as_int(case.get("candidate_hit_count")) for case in case_results),
        "total_page_profile_hit_count": sum(as_int(case.get("page_profile_hit_count")) for case in case_results),
        "total_resolved_candidate_hit_count": sum(as_int(case.get("resolved_candidate_hit_count")) for case in case_results),
        "total_resolved_page_profile_hit_count": sum(as_int(case.get("resolved_page_profile_hit_count")) for case in case_results),
        "case_unsafe_result_count": sum(as_int(case.get("unsafe_result_count")) for case in case_results),
        "case_direct_answer_allowed_count": sum(as_int(case.get("direct_answer_allowed_count")) for case in case_results),
        "case_claim_proof_allowed_count": sum(as_int(case.get("claim_proof_allowed_count")) for case in case_results),
        "case_source_truth_mutation_allowed_count": sum(as_int(case.get("source_truth_mutation_allowed_count")) for case in case_results),
        "hybrid_unsafe_result_count": as_int(hybrid_summary.get("unsafe_result_count")),
        "hybrid_unsafe_hit_payload_count": as_int(hybrid_summary.get("unsafe_hit_payload_count")),
        "hybrid_direct_answer_allowed_result_count": as_int(hybrid_summary.get("direct_answer_allowed_result_count")),
        "hybrid_claim_proof_allowed_without_authority_count": as_int(hybrid_summary.get("claim_proof_allowed_without_authority_count")),
        "hybrid_source_truth_mutation_allowed_count": as_int(hybrid_summary.get("source_truth_mutation_allowed_count")),
        "candidate_collection_count": as_int(hybrid_summary.get("candidate_collection_count")),
        "page_profile_collection_count": as_int(hybrid_summary.get("page_profile_collection_count")),
        "hybrid_grouped_result_count": as_int(hybrid_summary.get("grouped_result_count")),
        "hybrid_candidate_hit_count": as_int(hybrid_summary.get("candidate_hit_count")),
        "hybrid_page_profile_hit_count": as_int(hybrid_summary.get("page_profile_hit_count")),
        "hybrid_resolved_candidate_hit_count": as_int(hybrid_summary.get("resolved_candidate_hit_count")),
        "hybrid_resolved_page_profile_hit_count": as_int(hybrid_summary.get("resolved_page_profile_hit_count")),
    }


def build_quality_report(
    summary: Mapping[str, Any],
    *,
    min_regression_cases: int = 1,
    min_case_pass_rate: float = 1.0,
    min_cases_with_results: int = 1,
    min_cases_with_candidate_hits: int = 1,
    min_cases_with_page_profile_hits: int = 1,
    min_total_ranked_groups: int = 1,
    min_total_candidate_hits: int = 1,
    min_total_page_profile_hits: int = 1,
    require_all_cases_pass: bool = False,
    require_hybrid_quality_pass: bool = False,
    require_candidate_count: int = 0,
    require_page_profile_count: int = 0,
    require_embedding_dim: int = 0,
) -> QualityResult:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any, expected: Any, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected, "severity": severity})

    add("regression_case_count_min", as_int(summary.get("regression_case_count")) >= min_regression_cases, summary.get("regression_case_count"), f">={min_regression_cases}")
    add("case_pass_rate_min", as_float(summary.get("case_pass_rate")) >= min_case_pass_rate, summary.get("case_pass_rate"), f">={min_case_pass_rate}")
    add("cases_with_results_min", as_int(summary.get("cases_with_results_count")) >= min_cases_with_results, summary.get("cases_with_results_count"), f">={min_cases_with_results}")
    add("cases_with_candidate_hits_min", as_int(summary.get("cases_with_candidate_hits_count")) >= min_cases_with_candidate_hits, summary.get("cases_with_candidate_hits_count"), f">={min_cases_with_candidate_hits}")
    add("cases_with_page_profile_hits_min", as_int(summary.get("cases_with_page_profile_hits_count")) >= min_cases_with_page_profile_hits, summary.get("cases_with_page_profile_hits_count"), f">={min_cases_with_page_profile_hits}")
    add("total_ranked_group_count_min", as_int(summary.get("total_ranked_group_count")) >= min_total_ranked_groups, summary.get("total_ranked_group_count"), f">={min_total_ranked_groups}")
    add("total_candidate_hit_count_min", as_int(summary.get("total_candidate_hit_count")) >= min_total_candidate_hits, summary.get("total_candidate_hit_count"), f">={min_total_candidate_hits}")
    add("total_page_profile_hit_count_min", as_int(summary.get("total_page_profile_hit_count")) >= min_total_page_profile_hits, summary.get("total_page_profile_hit_count"), f">={min_total_page_profile_hits}")
    add("required_case_missing_count_zero", as_int(summary.get("required_case_missing_count")) == 0, summary.get("required_case_missing_count"), 0)
    if require_all_cases_pass:
        add("case_fail_count_zero", as_int(summary.get("case_fail_count")) == 0, summary.get("case_fail_count"), 0)
    if require_hybrid_quality_pass:
        add("hybrid_quality_status_pass", as_text(summary.get("hybrid_quality_status")) == "PASS", summary.get("hybrid_quality_status"), "PASS")
    add("case_unsafe_result_count_zero", as_int(summary.get("case_unsafe_result_count")) == 0, summary.get("case_unsafe_result_count"), 0)
    add("case_direct_answer_allowed_count_zero", as_int(summary.get("case_direct_answer_allowed_count")) == 0, summary.get("case_direct_answer_allowed_count"), 0)
    add("case_claim_proof_allowed_count_zero", as_int(summary.get("case_claim_proof_allowed_count")) == 0, summary.get("case_claim_proof_allowed_count"), 0)
    add("case_source_truth_mutation_allowed_count_zero", as_int(summary.get("case_source_truth_mutation_allowed_count")) == 0, summary.get("case_source_truth_mutation_allowed_count"), 0)
    add("hybrid_unsafe_result_count_zero", as_int(summary.get("hybrid_unsafe_result_count")) == 0, summary.get("hybrid_unsafe_result_count"), 0)
    add("hybrid_unsafe_hit_payload_count_zero", as_int(summary.get("hybrid_unsafe_hit_payload_count")) == 0, summary.get("hybrid_unsafe_hit_payload_count"), 0)
    add("hybrid_direct_answer_allowed_result_count_zero", as_int(summary.get("hybrid_direct_answer_allowed_result_count")) == 0, summary.get("hybrid_direct_answer_allowed_result_count"), 0)
    add("hybrid_claim_proof_allowed_without_authority_count_zero", as_int(summary.get("hybrid_claim_proof_allowed_without_authority_count")) == 0, summary.get("hybrid_claim_proof_allowed_without_authority_count"), 0)
    add("hybrid_source_truth_mutation_allowed_count_zero", as_int(summary.get("hybrid_source_truth_mutation_allowed_count")) == 0, summary.get("hybrid_source_truth_mutation_allowed_count"), 0)
    if require_candidate_count:
        add("candidate_collection_count_exact", as_int(summary.get("candidate_collection_count")) == require_candidate_count, summary.get("candidate_collection_count"), require_candidate_count)
    if require_page_profile_count:
        add("page_profile_collection_count_exact", as_int(summary.get("page_profile_collection_count")) == require_page_profile_count, summary.get("page_profile_collection_count"), require_page_profile_count)
    if require_embedding_dim:
        add("embedding_dim_exact", as_int(summary.get("embedding_dim")) == require_embedding_dim, summary.get("embedding_dim"), require_embedding_dim)
    status = "PASS" if all(check["passed"] or check.get("severity") == "warning" for check in checks) else "FAIL"
    return QualityResult(status=status, checks=checks, summary=dict(summary))


def run_regression_eval(
    *,
    hybrid_report_path: Path = DEFAULT_HYBRID_REPORT,
    regression_set_path: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_regression_cases: int = 1,
    min_case_pass_rate: float = 1.0,
    min_cases_with_results: int = 1,
    min_cases_with_candidate_hits: int = 1,
    min_cases_with_page_profile_hits: int = 1,
    min_total_ranked_groups: int = 1,
    min_total_candidate_hits: int = 1,
    min_total_page_profile_hits: int = 1,
    require_all_cases_pass: bool = False,
    require_hybrid_quality_pass: bool = False,
    require_candidate_count: int = 0,
    require_page_profile_count: int = 0,
    require_embedding_dim: int = 0,
    write_quality: bool = False,
) -> dict[str, Any]:
    hybrid_report_path = Path(hybrid_report_path)
    output_dir = Path(output_dir)
    hybrid_report = read_json(hybrid_report_path)
    if not isinstance(hybrid_report, Mapping):
        raise RegressionEvalError(f"Hybrid report must be a JSON object: {hybrid_report_path}")
    regression_set = load_regression_set(regression_set_path)
    cases = regression_set.get("cases") or []
    if not cases:
        raise RegressionEvalError("Regression set has no cases")
    result_index = index_results_by_query_id(report_results(hybrid_report))
    case_results = [evaluate_regression_case(case, result_index) for case in cases if isinstance(case, Mapping)]
    summary = summarize_regression(case_results=case_results, hybrid_report=hybrid_report, regression_set=regression_set)
    quality = build_quality_report(
        summary,
        min_regression_cases=min_regression_cases,
        min_case_pass_rate=min_case_pass_rate,
        min_cases_with_results=min_cases_with_results,
        min_cases_with_candidate_hits=min_cases_with_candidate_hits,
        min_cases_with_page_profile_hits=min_cases_with_page_profile_hits,
        min_total_ranked_groups=min_total_ranked_groups,
        min_total_candidate_hits=min_total_candidate_hits,
        min_total_page_profile_hits=min_total_page_profile_hits,
        require_all_cases_pass=require_all_cases_pass,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_candidate_count=require_candidate_count,
        require_page_profile_count=require_page_profile_count,
        require_embedding_dim=require_embedding_dim,
    )
    report_path = output_dir / DEFAULT_REPORT_FILE
    cases_path = output_dir / DEFAULT_CASES_FILE
    regression_set_out_path = output_dir / DEFAULT_REGRESSION_SET_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    quality_path = output_dir / DEFAULT_QUALITY_FILE
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if quality.passed else "FAIL",
        "generated_at_utc": utc_now_iso(),
        "read_only": True,
        "simulation_only": True,
        "ask_integration": False,
        "hybrid_report_path": str(hybrid_report_path),
        "hybrid_report_sha256": sha256_file(hybrid_report_path),
        "regression_set_name": regression_set.get("name"),
        "regression_set_sha256": sha256_json(regression_set),
        "summary": summary,
        "cases": case_results,
        "quality": {"status": quality.status, "checks": quality.checks},
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": report["status"],
        "generated_at_utc": report["generated_at_utc"],
        "read_only": True,
        "simulation_only": True,
        "ask_integration": False,
        "hybrid_report_path": str(hybrid_report_path),
        "hybrid_report_sha256": report["hybrid_report_sha256"],
        "regression_set_name": regression_set.get("name"),
        "regression_set_sha256": report["regression_set_sha256"],
        "report_file": DEFAULT_REPORT_FILE,
        "cases_file": DEFAULT_CASES_FILE,
        "regression_set_file": DEFAULT_REGRESSION_SET_FILE,
        "summary_file": DEFAULT_SUMMARY_FILE,
        "quality_file": DEFAULT_QUALITY_FILE if write_quality else "",
    }
    write_json(report_path, report)
    write_jsonl(cases_path, case_results)
    write_json(regression_set_out_path, regression_set)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": quality.status, "summary": summary, "checks": quality.checks})
    return {
        "status": report["status"],
        "report_path": str(report_path),
        "cases_path": str(cases_path),
        "regression_set_path": str(regression_set_out_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path) if write_quality else "",
        "summary": summary,
        "quality": quality,
    }


def check_regression_eval_quality(
    *,
    report_path: Path,
    min_regression_cases: int = 1,
    min_case_pass_rate: float = 1.0,
    min_cases_with_results: int = 1,
    min_cases_with_candidate_hits: int = 1,
    min_cases_with_page_profile_hits: int = 1,
    min_total_ranked_groups: int = 1,
    min_total_candidate_hits: int = 1,
    min_total_page_profile_hits: int = 1,
    require_all_cases_pass: bool = False,
    require_hybrid_quality_pass: bool = False,
    require_candidate_count: int = 0,
    require_page_profile_count: int = 0,
    require_embedding_dim: int = 0,
    write_json_path: Path | None = None,
) -> dict[str, Any]:
    payload = read_json(Path(report_path))
    if not isinstance(payload, Mapping):
        raise RegressionEvalError(f"Regression report must be a JSON object: {report_path}")
    summary = dict(payload.get("summary") or {})
    quality = build_quality_report(
        summary,
        min_regression_cases=min_regression_cases,
        min_case_pass_rate=min_case_pass_rate,
        min_cases_with_results=min_cases_with_results,
        min_cases_with_candidate_hits=min_cases_with_candidate_hits,
        min_cases_with_page_profile_hits=min_cases_with_page_profile_hits,
        min_total_ranked_groups=min_total_ranked_groups,
        min_total_candidate_hits=min_total_candidate_hits,
        min_total_page_profile_hits=min_total_page_profile_hits,
        require_all_cases_pass=require_all_cases_pass,
        require_hybrid_quality_pass=require_hybrid_quality_pass,
        require_candidate_count=require_candidate_count,
        require_page_profile_count=require_page_profile_count,
        require_embedding_dim=require_embedding_dim,
    )
    output = {"schema_version": SCHEMA_VERSION, "status": quality.status, "summary": summary, "checks": quality.checks}
    if write_json_path:
        write_json(Path(write_json_path), output)
    return output


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Expected integer, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("Expected a non-negative integer")
    return parsed


def nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Expected float, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("Expected a non-negative float")
    return parsed


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-regression-cases", type=positive_int, default=1)
    parser.add_argument("--min-case-pass-rate", type=nonnegative_float, default=1.0)
    parser.add_argument("--min-cases-with-results", type=positive_int, default=1)
    parser.add_argument("--min-cases-with-candidate-hits", type=positive_int, default=1)
    parser.add_argument("--min-cases-with-page-profile-hits", type=positive_int, default=1)
    parser.add_argument("--min-total-ranked-groups", type=positive_int, default=1)
    parser.add_argument("--min-total-candidate-hits", type=positive_int, default=1)
    parser.add_argument("--min-total-page-profile-hits", type=positive_int, default=1)
    parser.add_argument("--require-all-cases-pass", action="store_true")
    parser.add_argument("--require-hybrid-quality-pass", action="store_true")
    parser.add_argument("--require-candidate-count", type=positive_int, default=0)
    parser.add_argument("--require-page-profile-count", type=positive_int, default=0)
    parser.add_argument("--require-embedding-dim", type=positive_int, default=0)


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net regression evaluation v1 against hybrid retrieval simulation output.")
    parser.add_argument("--hybrid-report", type=Path, default=DEFAULT_HYBRID_REPORT)
    parser.add_argument("--regression-set", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quality", action="store_true", help="Write quality JSON next to the regression report.")
    add_quality_args(parser)
    return parser


def build_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net regression evaluation v1 quality output.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_REPORT_FILE)
    parser.add_argument("--write-json", action="store_true", help="Write refreshed quality JSON next to the report.")
    add_quality_args(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_run_parser().parse_args(argv)
    result = run_regression_eval(
        hybrid_report_path=args.hybrid_report,
        regression_set_path=args.regression_set,
        output_dir=args.output_dir,
        min_regression_cases=args.min_regression_cases,
        min_case_pass_rate=args.min_case_pass_rate,
        min_cases_with_results=args.min_cases_with_results,
        min_cases_with_candidate_hits=args.min_cases_with_candidate_hits,
        min_cases_with_page_profile_hits=args.min_cases_with_page_profile_hits,
        min_total_ranked_groups=args.min_total_ranked_groups,
        min_total_candidate_hits=args.min_total_candidate_hits,
        min_total_page_profile_hits=args.min_total_page_profile_hits,
        require_all_cases_pass=args.require_all_cases_pass,
        require_hybrid_quality_pass=args.require_hybrid_quality_pass,
        require_candidate_count=args.require_candidate_count,
        require_page_profile_count=args.require_page_profile_count,
        require_embedding_dim=args.require_embedding_dim,
        write_quality=args.quality,
    )
    summary = result["summary"]
    print("TRACE-Net regression evaluation v1")
    print(f" Status: {result['status']}")
    print(f" Quality status: {result['quality'].status}")
    for key in [
        "regression_case_count",
        "case_pass_count",
        "case_fail_count",
        "case_pass_rate",
        "required_case_missing_count",
        "cases_with_results_count",
        "total_ranked_group_count",
        "total_candidate_hit_count",
        "total_page_profile_hit_count",
        "case_unsafe_result_count",
        "case_direct_answer_allowed_count",
        "case_claim_proof_allowed_count",
        "case_source_truth_mutation_allowed_count",
        "hybrid_quality_status",
        "candidate_collection_count",
        "page_profile_collection_count",
        "embedding_dim",
    ]:
        if key in summary:
            print(f" {key}: {summary[key]}")
    print(f" report_path: {result['report_path']}")
    print(f" cases_path: {result['cases_path']}")
    print(f" manifest_path: {result['manifest_path']}")
    if result.get("quality_path"):
        print(f" quality_path: {result['quality_path']}")
    return 0 if result["quality"].passed else 1


def quality_main(argv: Sequence[str] | None = None) -> int:
    args = build_check_parser().parse_args(argv)
    write_path = None
    if args.write_json:
        write_path = Path(args.report_path).with_name(DEFAULT_QUALITY_FILE)
    result = check_regression_eval_quality(
        report_path=args.report_path,
        min_regression_cases=args.min_regression_cases,
        min_case_pass_rate=args.min_case_pass_rate,
        min_cases_with_results=args.min_cases_with_results,
        min_cases_with_candidate_hits=args.min_cases_with_candidate_hits,
        min_cases_with_page_profile_hits=args.min_cases_with_page_profile_hits,
        min_total_ranked_groups=args.min_total_ranked_groups,
        min_total_candidate_hits=args.min_total_candidate_hits,
        min_total_page_profile_hits=args.min_total_page_profile_hits,
        require_all_cases_pass=args.require_all_cases_pass,
        require_hybrid_quality_pass=args.require_hybrid_quality_pass,
        require_candidate_count=args.require_candidate_count,
        require_page_profile_count=args.require_page_profile_count,
        require_embedding_dim=args.require_embedding_dim,
        write_json_path=write_path,
    )
    summary = result["summary"]
    print("TRACE-Net regression evaluation v1 quality")
    print(f" Status: {result['status']}")
    for key in [
        "regression_case_count",
        "case_pass_count",
        "case_fail_count",
        "case_pass_rate",
        "required_case_missing_count",
        "cases_with_results_count",
        "total_ranked_group_count",
        "total_candidate_hit_count",
        "total_page_profile_hit_count",
        "case_unsafe_result_count",
        "case_direct_answer_allowed_count",
        "case_claim_proof_allowed_count",
        "case_source_truth_mutation_allowed_count",
        "hybrid_quality_status",
        "candidate_collection_count",
        "page_profile_collection_count",
        "embedding_dim",
    ]:
        if key in summary:
            print(f" {key}: {summary[key]}")
    if write_path:
        print(f" quality_path: {write_path}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
