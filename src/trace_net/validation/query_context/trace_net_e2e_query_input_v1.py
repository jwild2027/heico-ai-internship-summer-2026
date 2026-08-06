"""TRACE-Net E2E query input harness v1.

This module is intentionally small and safe. It turns one or more user
questions into a stable query-input artifact for the later end-to-end runtime.
It does not retrieve, generate answers, mutate source truth, or write to any
runtime database/search/vector service.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATUS = "E2E_QUERY_INPUT_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"
READINESS_STATUS = "E2E_QUERY_INPUT_READY_FOR_RETRIEVAL_RUNTIME"

PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
MANUAL_PAGE_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(r"\b\d+\b")

REQUIRED_QUERY_KEYS = {
    "query_id",
    "user_query",
    "normalized_query",
    "query_intent",
    "requested_routes",
    "retrieval_channels",
    "query_terms",
    "answer_policy_hint",
    "safety_contract",
}

STANDARD_DEMO_QUERIES = [
    "Find part number 120-36833-001",
    "Where is manual reference 25-21-00 used?",
    "Find IPL item 130",
    "Search table text MAINTENANCE MANUAL WITH",
    "What maintenance manual pages mention covered part numbers?",
]


@dataclass(frozen=True)
class QueryBuildConfig:
    min_query_records: int = 1
    min_routeable_queries: int = 1
    min_unique_intents: int = 1
    min_planned_retrieval_queries: int = 1
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_no_answer_permission: bool = True


def normalize_query(query: str) -> str:
    return " ".join((query or "").strip().split())


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _extract_terms(query: str) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for match in PART_NUMBER_RE.findall(query):
        terms.append({"term": match, "term_type": "part_number"})
    for match in MANUAL_PAGE_RE.findall(query):
        terms.append({"term": match, "term_type": "manual_page_reference"})

    upper = query.upper()
    if "MAINTENANCE MANUAL WITH" in upper:
        terms.append({"term": "MAINTENANCE MANUAL WITH", "term_type": "table_text_phrase"})

    # Keep short numeric item queries, but avoid duplicating digits already inside
    # part-number/manual-page references.
    protected_numbers: set[str] = set()
    for match in PART_NUMBER_RE.findall(query):
        protected_numbers.update(match.split("-"))
    for match in MANUAL_PAGE_RE.findall(query):
        protected_numbers.update(match.split("-"))
    for number in NUMBER_RE.findall(query):
        if number not in protected_numbers and len(number) <= 4:
            terms.append({"term": number, "term_type": "numeric_token"})

    if not terms:
        # Store a compact keyword-ish fallback term for downstream runtime.
        fallback = normalize_query(query)
        if fallback:
            terms.append({"term": fallback[:160], "term_type": "free_text"})
    return terms


def classify_query(query: str) -> dict[str, Any]:
    q = normalize_query(query)
    lower = q.lower()
    terms = _extract_terms(q)
    term_types = {t["term_type"] for t in terms}

    requested_routes: list[str] = []
    retrieval_channels: list[str] = []
    intent = "normal_text_query"
    answer_policy_hint = "needs_retrieval_and_final_gate"

    if "part number" in lower or "covered part" in lower or "part_number" in lower or "part_number" in term_types:
        intent = "covered_part_number"
        requested_routes.extend(["table", "normal_text"])
        retrieval_channels.extend([
            "table_exact_search",
            "table_hybrid_retrieval_bridge",
            "qdrant_page_profiles",
            "graph_source_trace",
        ])
    elif "manual reference" in lower or "manual page" in lower or "manual_page_reference" in term_types:
        intent = "manual_page_reference"
        requested_routes.extend(["table", "normal_text"])
        retrieval_channels.extend([
            "table_exact_search",
            "table_hybrid_retrieval_bridge",
            "qdrant_page_profiles",
            "graph_source_trace",
        ])
    elif "ipl" in lower or "item" in lower or "figure" in lower or "quantity" in lower:
        intent = "ipl_figure_item_or_quantity"
        requested_routes.extend(["table", "image_visual"])
        retrieval_channels.extend([
            "table_exact_search",
            "table_hybrid_retrieval_bridge",
            "graph_source_trace",
        ])
    elif "table" in lower or "maintenance manual with" in lower or "table_text_phrase" in term_types:
        intent = "table_text"
        requested_routes.extend(["table", "normal_text"])
        retrieval_channels.extend([
            "table_exact_search",
            "table_hybrid_retrieval_bridge",
            "qdrant_page_profiles",
        ])
    elif any(token in lower for token in ["diagram", "callout", "visual", "image", "exploded view"]):
        intent = "visual_or_callout_query"
        requested_routes.extend(["image_visual", "normal_text"])
        retrieval_channels.extend(["visual_retrieval", "graph_source_trace", "qdrant_page_profiles"])
    elif any(token in lower for token in ["lottery", "predict the future", "guess", "make up"]):
        intent = "audit_only_or_unknown"
        requested_routes.extend(["normal_text"])
        retrieval_channels.extend(["qdrant_page_profiles", "graph_source_trace"])
        answer_policy_hint = "likely_audit_only_without_source_evidence"
    else:
        requested_routes.extend(["normal_text"])
        retrieval_channels.extend(["qdrant_page_profiles", "graph_source_trace"])

    return {
        "query_intent": intent,
        "requested_routes": _dedupe_keep_order(requested_routes),
        "retrieval_channels": _dedupe_keep_order(retrieval_channels),
        "query_terms": terms,
        "answer_policy_hint": answer_policy_hint,
    }


def build_query_records(queries: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for raw_query in queries:
        normalized = normalize_query(raw_query)
        if not normalized or normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        plan = classify_query(normalized)
        idx = len(records) + 1
        query_id = f"e2e_query_v1_{idx:04d}"
        record = {
            "query_id": query_id,
            "user_query": normalized,
            "normalized_query": normalized.lower(),
            "query_intent": plan["query_intent"],
            "requested_routes": plan["requested_routes"],
            "retrieval_channels": plan["retrieval_channels"],
            "query_terms": plan["query_terms"],
            "answer_policy_hint": plan["answer_policy_hint"],
            "route_contract": {
                "table_route_values_are_allowed_as_ranking_signals": True,
                "table_route_values_are_allowed_as_final_answer_authority": False,
                "normal_text_requires_source_trace": True,
                "visual_route_output_is_advisory_until_verified": True,
            },
            "safety_contract": {
                "retrieval_only_input": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
                "opensearch_upload_attempt": False,
            },
        }
        records.append(record)
    return records


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    intent_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    for record in records:
        intent_counts[record["query_intent"]] = intent_counts.get(record["query_intent"], 0) + 1
        for route in record.get("requested_routes", []):
            route_counts[route] = route_counts.get(route, 0) + 1
        for channel in record.get("retrieval_channels", []):
            channel_counts[channel] = channel_counts.get(channel, 0) + 1

    unsafe_count = sum(1 for r in records if r.get("unsafe", False))
    answer_permission_count = sum(1 for r in records if r["safety_contract"].get("answer_permission"))
    can_answer_directly_count = sum(1 for r in records if r["safety_contract"].get("can_answer_directly"))
    can_prove_claims_count = sum(1 for r in records if r["safety_contract"].get("can_prove_claims"))
    source_truth_mutation_allowed_count = sum(
        1 for r in records if r["safety_contract"].get("source_truth_mutation_allowed")
    )
    postgres_write_attempt_count = sum(1 for r in records if r["safety_contract"].get("postgres_write_attempt"))
    qdrant_write_attempt_count = sum(1 for r in records if r["safety_contract"].get("qdrant_write_attempt"))
    opensearch_write_attempt_count = sum(1 for r in records if r["safety_contract"].get("opensearch_write_attempt"))
    opensearch_upload_attempt_count = sum(1 for r in records if r["safety_contract"].get("opensearch_upload_attempt"))

    return {
        "e2e_query_input_record_count": len(records),
        "routeable_query_count": sum(1 for r in records if r.get("requested_routes")),
        "planned_retrieval_query_count": sum(1 for r in records if r.get("retrieval_channels")),
        "unique_intent_count": len(intent_counts),
        "intent_counts": dict(sorted(intent_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "retrieval_channel_counts": dict(sorted(channel_counts.items())),
        "unsafe_query_input_record_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
    }


def _check(name: str, observed: Any, expected: str, passed: bool) -> dict[str, Any]:
    return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}


def evaluate_quality(report: dict[str, Any], config: QueryBuildConfig) -> tuple[str, list[dict[str, Any]]]:
    summary = report.get("summary", {})
    records = report.get("query_records", [])
    checks = [
        _check(
            "e2e_query_input_record_count",
            summary.get("e2e_query_input_record_count", 0),
            f">= {config.min_query_records}",
            summary.get("e2e_query_input_record_count", 0) >= config.min_query_records,
        ),
        _check(
            "routeable_query_count",
            summary.get("routeable_query_count", 0),
            f">= {config.min_routeable_queries}",
            summary.get("routeable_query_count", 0) >= config.min_routeable_queries,
        ),
        _check(
            "planned_retrieval_query_count",
            summary.get("planned_retrieval_query_count", 0),
            f">= {config.min_planned_retrieval_queries}",
            summary.get("planned_retrieval_query_count", 0) >= config.min_planned_retrieval_queries,
        ),
        _check(
            "unique_intent_count",
            summary.get("unique_intent_count", 0),
            f">= {config.min_unique_intents}",
            summary.get("unique_intent_count", 0) >= config.min_unique_intents,
        ),
        _check(
            "schema_missing_required_key_record_count",
            report.get("schema_missing_required_key_record_count", 0),
            "== 0",
            report.get("schema_missing_required_key_record_count", 0) == 0,
        ),
        _check(
            "unsafe_query_input_record_count",
            summary.get("unsafe_query_input_record_count", 0),
            f"<= {config.max_unsafe_records}",
            summary.get("unsafe_query_input_record_count", 0) <= config.max_unsafe_records,
        ),
        _check(
            "answer_permission_count",
            summary.get("answer_permission_count", 0),
            f"<= {config.max_answer_permission_count}",
            summary.get("answer_permission_count", 0) <= config.max_answer_permission_count,
        ),
        _check(
            "source_truth_mutation_allowed_count",
            summary.get("source_truth_mutation_allowed_count", 0),
            f"<= {config.max_source_truth_mutation_allowed}",
            summary.get("source_truth_mutation_allowed_count", 0) <= config.max_source_truth_mutation_allowed,
        ),
        _check("can_answer_directly_count", summary.get("can_answer_directly_count", 0), "== 0", summary.get("can_answer_directly_count", 0) == 0),
        _check("can_prove_claims_count", summary.get("can_prove_claims_count", 0), "== 0", summary.get("can_prove_claims_count", 0) == 0),
        _check("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", summary.get("postgres_write_attempt_count", 0) == 0),
        _check("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", summary.get("qdrant_write_attempt_count", 0) == 0),
        _check("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", summary.get("opensearch_write_attempt_count", 0) == 0),
        _check("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count", 0), "== 0", summary.get("opensearch_upload_attempt_count", 0) == 0),
    ]
    if config.require_no_answer_permission:
        checks.append(
            _check(
                "all_records_retrieval_only",
                all(not r.get("safety_contract", {}).get("answer_permission", True) for r in records),
                "is True",
                all(not r.get("safety_contract", {}).get("answer_permission", True) for r in records),
            )
        )
    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def build_report(queries: Iterable[str], config: QueryBuildConfig | None = None) -> dict[str, Any]:
    config = config or QueryBuildConfig()
    records = build_query_records(queries)
    summary = summarize_records(records)
    missing_schema = sum(1 for record in records if not REQUIRED_QUERY_KEYS.issubset(record.keys()))
    report: dict[str, Any] = {
        "status": STATUS,
        "quality_status": QUALITY_FAIL,
        "e2e_query_input_status": READINESS_STATUS,
        "query_input_contract": {
            "purpose": "Convert user questions into safe query-plan artifacts for the later E2E retrieval runtime.",
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "summary": summary,
        "schema_missing_required_key_record_count": missing_schema,
        "query_records": records,
    }
    quality_status, checks = evaluate_quality(report, config)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    return report


def read_queries_from_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            out: list[str] = []
            for item in data:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    value = item.get("query") or item.get("user_query") or item.get("text")
                    if value:
                        out.append(str(value))
            return out
        if isinstance(data, dict):
            items = data.get("queries") or data.get("demo_queries") or []
            return [str(x.get("query") or x.get("user_query") if isinstance(x, dict) else x) for x in items]
    if suffix == ".jsonl":
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if isinstance(data, str):
                out.append(data)
            elif isinstance(data, dict):
                value = data.get("query") or data.get("user_query") or data.get("text")
                if value:
                    out.append(str(value))
        return out
    return [line.strip() for line in text.splitlines() if line.strip()]


def write_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_query_input_v1.json"
    records_jsonl_path = output_dir / "trace_net_e2e_query_input_records_v1.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_query_input_v1_inspect.md"
    quality_path = output_dir / "trace_net_e2e_query_input_v1_quality.json"

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    with records_jsonl_path.open("w", encoding="utf-8") as fh:
        for record in report.get("query_records", []):
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    quality_doc = {
        "quality_status": report.get("quality_status"),
        "quality_checks": report.get("quality_checks", []),
        "summary": report.get("summary", {}),
    }
    quality_path.write_text(json.dumps(quality_doc, indent=2, sort_keys=True), encoding="utf-8")
    inspect_md_path.write_text(render_inspect_markdown(report), encoding="utf-8")

    return {
        "report_path": str(report_path),
        "records_jsonl_path": str(records_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
        "quality_path": str(quality_path),
    }


def render_inspect_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net E2E Query Input v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Purpose",
        "This artifact turns user questions into safe query-plan records for the later E2E retrieval runtime.",
        "It does not retrieve, answer, mutate source truth, or write to runtime services.",
        "",
        "## Query input contract",
    ]
    for key, value in report.get("query_input_contract", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Main counters"])
    for key in [
        "e2e_query_input_record_count",
        "routeable_query_count",
        "planned_retrieval_query_count",
        "unique_intent_count",
        "schema_missing_required_key_record_count",
    ]:
        value = summary.get(key, report.get(key))
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Intent counts"])
    for key, value in summary.get("intent_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Route counts"])
    for key, value in summary.get("route_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Retrieval channel counts"])
    for key, value in summary.get("retrieval_channel_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Safety/write counters"])
    for key in [
        "unsafe_query_input_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Query records"])
    for record in report.get("query_records", []):
        terms = ", ".join(f"{t['term']} ({t['term_type']})" for t in record.get("query_terms", []))
        routes = ", ".join(record.get("requested_routes", []))
        channels = ", ".join(record.get("retrieval_channels", []))
        lines.append(f"- {record['query_id']} | {record['query_intent']} | {record['user_query']}")
        lines.append(f"  - routes: {routes}")
        lines.append(f"  - channels: {channels}")
        lines.append(f"  - terms: {terms}")
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        label = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {label} {check['name']}: observed={check['observed']} expected={check['expected']}")
    lines.append("")
    return "\n".join(lines)
