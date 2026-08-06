"""TRACE-Net Leiden Community Quality Audit v1.

Read-only audit for Leiden/community artifacts. The module checks that Leiden
communities remain navigation/ranking aids and never become proof, while also
surfacing community-coherence risks such as missing labels, weak category
summaries, over-large communities, missing page coverage, or retrieval-only
policy leaks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_leiden_community_quality_audit_v1"
STATUS_BUILT = "LEIDEN_COMMUNITY_QUALITY_AUDIT_BUILT"
PASS = "PASS"
FAIL = "FAIL"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PAGE_RE = re.compile(r"t_p_\d+_\d+_p\d{6}")

QUALITY_KEYS = ("quality_status", "status", "source_quality_status", "quality")
COMMUNITY_LIST_KEYS = (
    "communities",
    "community_records",
    "community_cards",
    "leiden_communities",
    "records",
    "nodes",
)
COMMUNITY_SUMMARY_KEYS = (
    "community_summaries",
    "community_category_summaries",
    "category_aware_community_cards",
    "community_cards",
    "records",
)
PAGE_PROFILE_KEYS = (
    "page_category_profiles",
    "page_profiles",
    "page_cards",
    "page_records",
)

COUNT_KEY_ALIASES = {
    "community_count": (
        "community_count",
        "leiden_community_count",
        "communities_count",
        "min_community_count",
        "category_aware_community_card_count",
    ),
    "page_count": (
        "page_count",
        "effective_page_count",
        "page_node_count",
        "page_record_count",
        "page_profile_count",
        "page_category_profile_count",
        "page_nodes_with_community_count",
        "page_nodes_with_community",
        "page_card_count",
    ),
    "node_count": (
        "node_count",
        "graph_node_count",
        "overlay_node_count",
        "ui_node_count",
    ),
    "edge_count": (
        "edge_count",
        "graph_edge_count",
        "overlay_edge_count",
        "ui_edge_count",
    ),
    "orphan_edge_count": (
        "orphan_edge_count",
        "orphan_edges_count",
    ),
    "category_overlay_edge_count": (
        "category_overlay_edge_count",
        "category_overlay_edges_count",
        "category_ui_edge_count",
        "category_ui_edges_count",
    ),
    "community_as_proof_count": ("community_as_proof_count",),
    "category_as_proof_count": ("category_as_proof_count",),
    "retrieval_only_answer_allowed_count": ("retrieval_only_answer_allowed_count",),
    "source_truth_mutation_allowed_count": ("source_truth_mutation_allowed_count",),
    "can_answer_directly_count": ("can_answer_directly_count", "direct_answer_allowed_count"),
    "can_prove_claims_count": ("can_prove_claims_count", "claim_proof_allowed_count"),
}


@dataclass(frozen=True)
class QualityThresholds:
    require_page_count: int | None = None
    min_communities: int = 1
    min_audit_records: int = 1
    min_page_coverage: int | None = None
    max_community_as_proof: int = 0
    max_category_as_proof: int = 0
    max_retrieval_only_answer_allowed: int = 0
    max_source_truth_mutation_allowed: int = 0
    max_unsafe_records: int = 0
    require_leiden_quality_pass: bool = False
    require_category_overlay_quality_pass: bool = False
    require_no_orphan_edges: bool = False


def load_json(path: str | Path | None, *, required: bool = True) -> dict[str, Any]:
    if not path:
        if required:
            raise ValueError("Missing required path")
        return {}
    p = Path(path)
    if not p.exists():
        if required:
            raise FileNotFoundError(f"Missing JSON input: {p}")
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def get_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def get_quality_status(payload: dict[str, Any]) -> str | None:
    for key in QUALITY_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    summary = get_summary(payload)
    for key in QUALITY_KEYS:
        val = summary.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if s.isdigit():
            return int(s)
    return None


def summary_count(payload: dict[str, Any], logical_key: str) -> int | None:
    summary = get_summary(payload)
    for key in COUNT_KEY_ALIASES.get(logical_key, (logical_key,)):
        for src in (summary, payload):
            val = _as_int(src.get(key)) if isinstance(src, dict) else None
            if val is not None:
                return val
    return None


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def first_list(payload: dict[str, Any], keys: Iterable[str]) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            rows = [x for x in value if isinstance(x, dict)]
            if rows:
                return rows
    # Some artifacts put records under summary-like wrapper keys.
    for value in payload.values():
        if isinstance(value, dict):
            for key in keys:
                nested = value.get(key)
                if isinstance(nested, list):
                    rows = [x for x in nested if isinstance(x, dict)]
                    if rows:
                        return rows
    return []


def collect_page_ids(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.extend(PAGE_RE.findall(value))
        if value.startswith("t_p_") and value not in out:
            out.append(value)
    elif isinstance(value, list):
        for item in value:
            out.extend(collect_page_ids(item))
    elif isinstance(value, dict):
        for key, nested in value.items():
            if key in (
                "page_id",
                "page_ids",
                "source_page_id",
                "source_page_ids",
                "member_page_ids",
                "page_node_ids",
                "pages",
                "source_trace",
                "text",
                "summary",
                "description",
                "text_preview",
            ) or isinstance(nested, (dict, list)):
                out.extend(collect_page_ids(nested))
    # keep order, dedupe
    seen: set[str] = set()
    clean: list[str] = []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            clean.append(p)
    return clean


def community_id_of(record: dict[str, Any], fallback: int) -> str:
    for key in (
        "community_id",
        "leiden_community_id",
        "community",
        "id",
        "node_id",
        "card_id",
        "cluster_id",
    ):
        val = record.get(key)
        if val not in (None, "", [], {}):
            return str(val)
    return f"community_{fallback:05d}"


def label_of(record: dict[str, Any]) -> str:
    for key in (
        "label",
        "community_label",
        "title",
        "name",
        "dominant_label",
        "display_label",
        "summary_label",
    ):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("summary", "text_preview", "description"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:120]
    return ""


def page_count_of(record: dict[str, Any]) -> int:
    for key in (
        "page_count",
        "member_page_count",
        "page_node_count",
        "pages_count",
        "source_page_count",
    ):
        val = _as_int(record.get(key))
        if val is not None:
            return val
    return len(collect_page_ids(record))


def category_counts_of(record: dict[str, Any]) -> dict[str, int]:
    for key in (
        "category_counts",
        "element_category_counts",
        "family_counts",
        "category_family_counts",
        "dominant_category_counts",
    ):
        val = record.get(key)
        if isinstance(val, dict):
            return {str(k): int(v) for k, v in val.items() if _as_int(v) is not None}
    categories = record.get("categories")
    if isinstance(categories, list):
        counter: Counter[str] = Counter()
        for item in categories:
            if isinstance(item, str):
                counter[item] += 1
            elif isinstance(item, dict):
                name = item.get("category") or item.get("family") or item.get("label")
                count = _as_int(item.get("count")) or 1
                if name:
                    counter[str(name)] += count
        return dict(counter)
    return {}


def dominant_category(category_counts: dict[str, int]) -> tuple[str | None, int, float]:
    if not category_counts:
        return None, 0, 0.0
    total = sum(v for v in category_counts.values() if isinstance(v, int))
    if total <= 0:
        return None, 0, 0.0
    category, count = max(category_counts.items(), key=lambda kv: kv[1])
    return category, count, round(count / total, 6)


def extract_part_numbers(record: dict[str, Any]) -> list[str]:
    text_bits: list[str] = []
    for key in ("label", "title", "summary", "description", "text", "text_preview"):
        val = record.get(key)
        if isinstance(val, str):
            text_bits.append(val)
    for key in ("part_numbers", "parts", "part_families"):
        val = record.get(key)
        if isinstance(val, list):
            text_bits.extend(str(x) for x in val)
        elif isinstance(val, str):
            text_bits.append(val)
    matches: list[str] = []
    for text in text_bits:
        matches.extend(PART_RE.findall(text))
    return sorted(set(matches))


def extract_ata_codes(record: dict[str, Any]) -> list[str]:
    text_bits: list[str] = []
    for key in ("ata", "ata_code", "label", "title", "summary", "description", "text_preview"):
        val = record.get(key)
        if isinstance(val, str):
            text_bits.append(val)
        elif isinstance(val, list):
            text_bits.extend(str(x) for x in val)
    matches: list[str] = []
    for text in text_bits:
        matches.extend(ATA_RE.findall(text))
    return sorted(set(matches))


def build_record_from_raw(
    raw: dict[str, Any],
    index: int,
    *,
    page_universe_count: int | None,
    category_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    community_id = community_id_of(raw, index)
    overlay = category_lookup.get(community_id, {})
    merged = dict(raw)
    for key, value in overlay.items():
        merged.setdefault(key, value)

    label = label_of(merged)
    page_ids = collect_page_ids(merged)
    page_count = page_count_of(merged)
    if page_count == 0 and page_ids:
        page_count = len(page_ids)

    category_counts = category_counts_of(merged)
    dom_cat, dom_count, dom_ratio = dominant_category(category_counts)
    parts = extract_part_numbers(merged)
    ata_codes = extract_ata_codes(merged)

    risk_flags: list[str] = []
    review_reasons: list[str] = []

    if not label:
        risk_flags.append("missing_label")
        review_reasons.append("community_missing_human_readable_label")
    if page_count <= 0:
        risk_flags.append("missing_page_membership")
        review_reasons.append("community_has_no_page_membership_signal")
    if page_universe_count and page_count > max(50, math.ceil(page_universe_count * 0.2)):
        risk_flags.append("large_community_review")
        review_reasons.append("community_contains_large_share_of_pages")
    if not category_counts:
        risk_flags.append("missing_category_summary")
        review_reasons.append("community_missing_category_distribution")
    elif dom_ratio < 0.35:
        risk_flags.append("low_category_coherence")
        review_reasons.append("community_category_distribution_is_mixed")
    if len(parts) > 75:
        risk_flags.append("many_part_numbers_review")
        review_reasons.append("community_summary_contains_many_part_numbers")

    can_answer_directly = bool(merged.get("can_answer_directly"))
    can_prove_claims = bool(merged.get("can_prove_claims"))
    if can_answer_directly:
        risk_flags.append("community_can_answer_directly_policy_violation")
    if can_prove_claims:
        risk_flags.append("community_can_prove_claims_policy_violation")

    unsafe = can_answer_directly or can_prove_claims
    return {
        "audit_record_id": f"leiden_quality_audit:{community_id}",
        "community_id": community_id,
        "label": label,
        "page_count": page_count,
        "sample_page_ids": page_ids[:20],
        "part_number_count": len(parts),
        "sample_part_numbers": parts[:20],
        "ata_codes": ata_codes[:10],
        "category_counts": category_counts,
        "dominant_category": dom_cat,
        "dominant_category_count": dom_count,
        "dominant_category_ratio": dom_ratio,
        "risk_flags": sorted(set(risk_flags)),
        "review_reasons": sorted(set(review_reasons)),
        "review_recommended": bool(review_reasons),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe_record": unsafe,
        "policy_notes": [
            "Leiden communities are navigation/ranking aids only.",
            "Community membership, labels, and category summaries cannot prove claims.",
        ],
    }


def category_lookup_from_overlay(category_overlay: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = first_list(category_overlay, COMMUNITY_SUMMARY_KEYS)
    lookup: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows, 1):
        cid = community_id_of(row, i)
        lookup[cid] = row
    return lookup


def build_placeholder_records(count: int) -> list[dict[str, Any]]:
    return [
        {
            "audit_record_id": f"leiden_quality_audit:placeholder_{i:05d}",
            "community_id": f"placeholder_{i:05d}",
            "label": "count_only_record_from_summary",
            "page_count": 0,
            "sample_page_ids": [],
            "part_number_count": 0,
            "sample_part_numbers": [],
            "ata_codes": [],
            "category_counts": {},
            "dominant_category": None,
            "dominant_category_count": 0,
            "dominant_category_ratio": 0.0,
            "risk_flags": ["count_only_record"],
            "review_reasons": ["source_artifact_did_not_expose_per_community_records"],
            "review_recommended": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "unsafe_record": False,
            "policy_notes": [
                "Leiden communities are navigation/ranking aids only.",
                "Community membership, labels, and category summaries cannot prove claims.",
            ],
        }
        for i in range(1, count + 1)
    ]


def build_leiden_community_quality_audit(
    *,
    leiden_communities: dict[str, Any],
    category_aware_leiden_overlay: dict[str, Any] | None = None,
    graph_ui_community_overlay: dict[str, Any] | None = None,
    thresholds: QualityThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or QualityThresholds()
    category_aware_leiden_overlay = category_aware_leiden_overlay or {}
    graph_ui_community_overlay = graph_ui_community_overlay or {}

    leiden_summary = get_summary(leiden_communities)
    category_summary = get_summary(category_aware_leiden_overlay)
    graph_ui_summary = get_summary(graph_ui_community_overlay)

    leiden_quality = get_quality_status(leiden_communities)
    category_quality = get_quality_status(category_aware_leiden_overlay)
    graph_ui_quality = get_quality_status(graph_ui_community_overlay)

    community_rows = first_list(leiden_communities, COMMUNITY_LIST_KEYS)
    category_lookup = category_lookup_from_overlay(category_aware_leiden_overlay)
    if not community_rows:
        # Category overlay/community UI may expose richer community cards than the source Leiden artifact.
        community_rows = first_list(category_aware_leiden_overlay, COMMUNITY_SUMMARY_KEYS)
    if not community_rows:
        community_rows = first_list(graph_ui_community_overlay, COMMUNITY_SUMMARY_KEYS)

    leiden_community_count = (
        summary_count(leiden_communities, "community_count")
        or summary_count(category_aware_leiden_overlay, "community_count")
        or len(community_rows)
    )
    effective_page_count = (
        summary_count(leiden_communities, "page_count")
        or summary_count(category_aware_leiden_overlay, "page_count")
        or summary_count(graph_ui_community_overlay, "page_count")
    )
    graph_node_count = summary_count(leiden_communities, "node_count")
    graph_edge_count = summary_count(leiden_communities, "edge_count")
    orphan_edge_count = summary_count(leiden_communities, "orphan_edge_count")

    records: list[dict[str, Any]] = []
    if community_rows:
        for i, row in enumerate(community_rows, 1):
            records.append(
                build_record_from_raw(
                    row,
                    i,
                    page_universe_count=effective_page_count,
                    category_lookup=category_lookup,
                )
            )
    elif leiden_community_count:
        records = build_placeholder_records(leiden_community_count)

    all_page_ids = sorted({pid for record in records for pid in record.get("sample_page_ids", [])})
    label_missing_count = sum(1 for r in records if "missing_label" in r.get("risk_flags", []))
    missing_category_summary_count = sum(1 for r in records if "missing_category_summary" in r.get("risk_flags", []))
    low_category_coherence_count = sum(1 for r in records if "low_category_coherence" in r.get("risk_flags", []))
    large_community_review_count = sum(1 for r in records if "large_community_review" in r.get("risk_flags", []))
    count_only_record_count = sum(1 for r in records if "count_only_record" in r.get("risk_flags", []))
    review_recommended_count = sum(1 for r in records if r.get("review_recommended"))
    unsafe_record_count = sum(1 for r in records if r.get("unsafe_record"))

    community_as_proof_count = max(
        summary_count(leiden_communities, "community_as_proof_count") or 0,
        summary_count(category_aware_leiden_overlay, "community_as_proof_count") or 0,
        summary_count(graph_ui_community_overlay, "community_as_proof_count") or 0,
    )
    category_as_proof_count = max(
        summary_count(leiden_communities, "category_as_proof_count") or 0,
        summary_count(category_aware_leiden_overlay, "category_as_proof_count") or 0,
        summary_count(graph_ui_community_overlay, "category_as_proof_count") or 0,
    )
    retrieval_only_answer_allowed_count = max(
        summary_count(leiden_communities, "retrieval_only_answer_allowed_count") or 0,
        summary_count(category_aware_leiden_overlay, "retrieval_only_answer_allowed_count") or 0,
        summary_count(graph_ui_community_overlay, "retrieval_only_answer_allowed_count") or 0,
    )
    source_truth_mutation_allowed_count = max(
        summary_count(leiden_communities, "source_truth_mutation_allowed_count") or 0,
        summary_count(category_aware_leiden_overlay, "source_truth_mutation_allowed_count") or 0,
        summary_count(graph_ui_community_overlay, "source_truth_mutation_allowed_count") or 0,
    )

    can_answer_directly_count = 0
    can_prove_claims_count = 0

    quality_errors: list[str] = []
    if thresholds.require_leiden_quality_pass and str(leiden_quality).upper() != PASS:
        quality_errors.append("source_leiden_quality_not_pass")
    if thresholds.require_category_overlay_quality_pass and category_aware_leiden_overlay and str(category_quality).upper() != PASS:
        quality_errors.append("source_category_overlay_quality_not_pass")
    if thresholds.require_page_count is not None and effective_page_count != thresholds.require_page_count:
        quality_errors.append("effective_page_count_mismatch")
    if thresholds.min_page_coverage is not None:
        coverage = effective_page_count or len(all_page_ids)
        if coverage < thresholds.min_page_coverage:
            quality_errors.append("page_coverage_below_minimum")
    if (leiden_community_count or len(records)) < thresholds.min_communities:
        quality_errors.append("community_count_below_minimum")
    if len(records) < thresholds.min_audit_records:
        quality_errors.append("audit_record_count_below_minimum")
    if thresholds.require_no_orphan_edges and (orphan_edge_count or 0) != 0:
        quality_errors.append("orphan_edges_present")
    if community_as_proof_count > thresholds.max_community_as_proof:
        quality_errors.append("community_as_proof_count_above_limit")
    if category_as_proof_count > thresholds.max_category_as_proof:
        quality_errors.append("category_as_proof_count_above_limit")
    if retrieval_only_answer_allowed_count > thresholds.max_retrieval_only_answer_allowed:
        quality_errors.append("retrieval_only_answer_allowed_count_above_limit")
    if source_truth_mutation_allowed_count > thresholds.max_source_truth_mutation_allowed:
        quality_errors.append("source_truth_mutation_allowed_count_above_limit")
    if unsafe_record_count > thresholds.max_unsafe_records:
        quality_errors.append("unsafe_community_record_count_above_limit")

    quality_status = FAIL if quality_errors else PASS

    top_review_records = sorted(
        records,
        key=lambda r: (
            len(r.get("risk_flags", [])),
            r.get("page_count") or 0,
            r.get("part_number_count") or 0,
        ),
        reverse=True,
    )[:25]

    recommendations: list[str] = []
    if count_only_record_count:
        recommendations.append("Expose per-community records in Leiden/category artifacts so audit can inspect labels, members, and category mix.")
    if missing_category_summary_count:
        recommendations.append("Hydrate Leiden communities with category summaries before using them in graph UI or retrieval hints.")
    if large_community_review_count:
        recommendations.append("Review large communities for hub edges or over-broad part-family aggregation.")
    if low_category_coherence_count:
        recommendations.append("Review mixed-category communities and consider category-aware edge weighting.")
    if not recommendations:
        recommendations.append("Leiden communities look safe as advisory navigation/ranking context; keep community_as_proof at zero.")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": quality_status,
        "source_quality_statuses": {
            "leiden_graph_communities": leiden_quality,
            "category_aware_leiden_overlay": category_quality,
            "graph_ui_community_overlay": graph_ui_quality,
        },
        "leiden_community_count": leiden_community_count or len(records),
        "community_audit_record_count": len(records),
        "effective_page_count": effective_page_count,
        "graph_node_count": graph_node_count,
        "graph_edge_count": graph_edge_count,
        "orphan_edge_count": orphan_edge_count if orphan_edge_count is not None else 0,
        "sample_page_id_count_seen_in_records": len(all_page_ids),
        "review_recommended_community_count": review_recommended_count,
        "large_community_review_count": large_community_review_count,
        "missing_label_count": label_missing_count,
        "missing_category_summary_count": missing_category_summary_count,
        "low_category_coherence_count": low_category_coherence_count,
        "count_only_record_count": count_only_record_count,
        "unsafe_community_record_count": unsafe_record_count,
        "community_as_proof_count": community_as_proof_count,
        "category_as_proof_count": category_as_proof_count,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "quality_error_count": len(quality_errors),
        "quality_errors": quality_errors,
        "recommendations": recommendations,
        "algorithm": "trace_net_read_only_leiden_community_quality_audit_v1",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "community_audit_records": records,
        "review_recommended_records": top_review_records,
        "policy_contract": {
            "leiden_communities_are_proof": False,
            "category_labels_are_proof": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
        },
    }


def check_leiden_community_quality_audit(
    *,
    report_path: str | Path,
    thresholds: QualityThresholds,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = load_json(report_path)
    summary = get_summary(report)

    errors = list(summary.get("quality_errors") or [])
    community_count = _as_int(summary.get("leiden_community_count")) or 0
    record_count = _as_int(summary.get("community_audit_record_count")) or 0
    effective_page_count = _as_int(summary.get("effective_page_count"))
    orphan_edge_count = _as_int(summary.get("orphan_edge_count")) or 0

    if thresholds.require_page_count is not None and effective_page_count != thresholds.require_page_count:
        errors.append("effective_page_count_mismatch")
    if thresholds.min_page_coverage is not None:
        coverage = effective_page_count or _as_int(summary.get("sample_page_id_count_seen_in_records")) or 0
        if coverage < thresholds.min_page_coverage:
            errors.append("page_coverage_below_minimum")
    if community_count < thresholds.min_communities:
        errors.append("community_count_below_minimum")
    if record_count < thresholds.min_audit_records:
        errors.append("audit_record_count_below_minimum")
    if thresholds.require_no_orphan_edges and orphan_edge_count != 0:
        errors.append("orphan_edges_present")

    limit_checks = [
        ("community_as_proof_count", thresholds.max_community_as_proof, "community_as_proof_count_above_limit"),
        ("category_as_proof_count", thresholds.max_category_as_proof, "category_as_proof_count_above_limit"),
        (
            "retrieval_only_answer_allowed_count",
            thresholds.max_retrieval_only_answer_allowed,
            "retrieval_only_answer_allowed_count_above_limit",
        ),
        (
            "source_truth_mutation_allowed_count",
            thresholds.max_source_truth_mutation_allowed,
            "source_truth_mutation_allowed_count_above_limit",
        ),
        ("unsafe_community_record_count", thresholds.max_unsafe_records, "unsafe_community_record_count_above_limit"),
    ]
    for key, limit, reason in limit_checks:
        if (_as_int(summary.get(key)) or 0) > limit:
            errors.append(reason)

    source_statuses = summary.get("source_quality_statuses") or {}
    if thresholds.require_leiden_quality_pass and str(source_statuses.get("leiden_graph_communities")).upper() != PASS:
        errors.append("source_leiden_quality_not_pass")
    if thresholds.require_category_overlay_quality_pass and str(source_statuses.get("category_aware_leiden_overlay")).upper() != PASS:
        errors.append("source_category_overlay_quality_not_pass")

    errors = sorted(set(errors))
    quality_status = FAIL if errors else PASS
    report["quality_status"] = quality_status
    report.setdefault("summary", {})["status"] = quality_status
    report["summary"]["quality_errors"] = errors
    report["summary"]["quality_error_count"] = len(errors)

    if write_json_report:
        p = Path(report_path)
        quality_path = p.with_name(p.stem + "_quality.json")
        write_json(quality_path, report)

    return report


def write_markdown(path: str | Path, report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Leiden Community Quality Audit v1",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Key counts",
        "",
    ]
    for key in (
        "leiden_community_count",
        "community_audit_record_count",
        "effective_page_count",
        "graph_node_count",
        "graph_edge_count",
        "orphan_edge_count",
        "review_recommended_community_count",
        "large_community_review_count",
        "missing_category_summary_count",
        "low_category_coherence_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- `{key}`: {summary.get(key)}")
    lines.extend(["", "## Recommendations", ""])
    for rec in summary.get("recommendations") or []:
        lines.append(f"- {rec}")
    lines.extend(["", "## Policy contract", "", "Leiden communities and category labels are advisory only. They cannot prove claims or grant answer permission.", ""])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_audit_records=args.min_audit_records,
        min_page_coverage=args.min_page_coverage,
        max_community_as_proof=args.max_community_as_proof,
        max_category_as_proof=args.max_category_as_proof,
        max_retrieval_only_answer_allowed=args.max_retrieval_only_answer_allowed,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_unsafe_records=args.max_unsafe_records,
        require_leiden_quality_pass=args.require_leiden_quality_pass,
        require_category_overlay_quality_pass=args.require_category_overlay_quality_pass,
        require_no_orphan_edges=args.require_no_orphan_edges,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Leiden Community Quality Audit v1")
    parser.add_argument("--leiden-communities", required=True)
    parser.add_argument("--category-aware-leiden-overlay", default=None)
    parser.add_argument("--graph-ui-community-overlay", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-audit-records", type=int, default=1)
    parser.add_argument("--min-page-coverage", type=int, default=None)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--require-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-category-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-no-orphan-edges", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def check_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Leiden Community Quality Audit v1")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-audit-records", type=int, default=1)
    parser.add_argument("--min-page-coverage", type=int, default=None)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--require-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-category-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-no-orphan-edges", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    thresholds = thresholds_from_args(args)

    leiden = load_json(args.leiden_communities)
    category = load_json(args.category_aware_leiden_overlay, required=False)
    graph_ui = load_json(args.graph_ui_community_overlay, required=False)

    report = build_leiden_community_quality_audit(
        leiden_communities=leiden,
        category_aware_leiden_overlay=category,
        graph_ui_community_overlay=graph_ui,
        thresholds=thresholds,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_leiden_community_quality_audit_v1.json"
    quality_path = output_dir / "trace_net_leiden_community_quality_audit_v1_quality.json"
    markdown_path = output_dir / "trace_net_leiden_community_quality_audit_v1.md"

    write_json(report_path, report)
    if args.quality:
        checked = check_leiden_community_quality_audit(
            report_path=report_path,
            thresholds=thresholds,
            write_json_report=False,
        )
        write_json(report_path, checked)
        write_json(quality_path, checked)
        report = checked
    write_markdown(markdown_path, report)

    summary = report.get("summary", {})
    print("TRACE-Net Leiden Community Quality Audit v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "leiden_community_count",
        "community_audit_record_count",
        "effective_page_count",
        "graph_node_count",
        "graph_edge_count",
        "orphan_edge_count",
        "review_recommended_community_count",
        "large_community_review_count",
        "missing_category_summary_count",
        "low_category_coherence_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report_path}")
    if args.quality:
        print(f" quality_path: {quality_path}")
    return 0 if report.get("quality_status") == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
