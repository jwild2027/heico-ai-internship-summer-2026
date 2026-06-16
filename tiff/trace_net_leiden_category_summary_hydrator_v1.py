"""
TRACE-Net Leiden Category Summary Hydrator v1.

Read-only helper that hydrates Leiden community records with category summaries
using page-category signals from the category-aware Leiden overlay, element
category taxonomy, Dublin Core refined records, and graph UI community overlay.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- communities/categories remain navigation hints, never proof
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_leiden_category_summary_hydrator_v1"
DEFAULT_OUTPUT_NAME = "trace_net_leiden_category_summary_hydrator_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_leiden_category_summary_hydrator_v1_quality.json"
DEFAULT_MARKDOWN_NAME = "trace_net_leiden_category_summary_hydrator_v1.md"
DEFAULT_RECORDS_JSONL_NAME = "trace_net_leiden_category_summary_hydrator_v1_records.jsonl"

PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}")
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")

CATEGORY_ALIASES = {
    "text_page": "text_source_page",
    "technical_manual_page": "text_source_page",
    "source_text": "text_source_page",
    "source": "source_identity",
    "source_page": "source_identity",
    "table": "table_evidence",
    "table_cell": "table_evidence",
    "table_row": "table_evidence",
    "diagram": "visual_evidence",
    "figure": "visual_evidence",
    "chart": "visual_evidence",
    "visual": "visual_evidence",
    "part": "part_evidence",
    "part_candidate": "part_evidence",
    "verified_part": "part_evidence",
    "citation": "citation_evidence",
    "review": "review_signal",
    "feedback": "feedback_signal",
    "community": "community_navigation",
    "blank_page": "blank_page",
}

DOC_LIST_KEYS = (
    "communities",
    "community_records",
    "community_summaries",
    "community_cards",
    "category_aware_community_cards",
    "graph_ui_community_cards",
    "community_audit_records",
    "review_recommended_records",
    "records",
)

PAGE_PROFILE_KEYS = (
    "page_category_profiles",
    "page_category_profile_cards",
    "page_profiles",
    "page_records",
    "records",
)


def load_json(path: str | Path | None, *, required: bool = True) -> dict[str, Any]:
    if path is None:
        if required:
            raise ValueError("Missing required JSON path")
        return {}
    p = Path(path)
    if not p.exists():
        if required:
            raise FileNotFoundError(f"Missing JSON input: {p}")
        return {}
    with p.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise TypeError(f"Expected top-level JSON object in {p}")
    return value


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            for key in ("page_id", "id", "node_id", "part_number", "label", "value"):
                if key in value:
                    value = value.get(key)
                    break
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def find_first(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, "", [], {}):
            return record.get(key)
    return None


def extract_page_ids_from_any(value: Any) -> list[str]:
    ids: list[str] = []
    if value is None:
        return ids
    if isinstance(value, str):
        ids.extend(PAGE_ID_RE.findall(value))
        if PAGE_ID_RE.fullmatch(value.strip()):
            ids.append(value.strip())
        return unique_strings(ids)
    if isinstance(value, Mapping):
        for key, sub in value.items():
            if key in {"page_id", "source_page_id", "canonical_page_id"}:
                if isinstance(sub, str):
                    ids.extend(PAGE_ID_RE.findall(sub) or [sub])
            elif key in {"page_ids", "source_page_ids", "member_page_ids", "sample_page_ids", "pages"}:
                ids.extend(extract_page_ids_from_any(sub))
            elif isinstance(sub, (str, list, dict, tuple)):
                ids.extend(extract_page_ids_from_any(sub))
        return unique_strings(ids)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            ids.extend(extract_page_ids_from_any(item))
        return unique_strings(ids)
    return ids


def extract_part_numbers_from_any(value: Any) -> list[str]:
    parts: list[str] = []
    if value is None:
        return parts
    if isinstance(value, str):
        return unique_strings(PART_RE.findall(value))
    if isinstance(value, Mapping):
        for key, sub in value.items():
            if key in {"part_number", "part_numbers", "sample_part_numbers", "parts", "part_families"}:
                parts.extend(extract_part_numbers_from_any(sub))
            elif isinstance(sub, (str, list, dict, tuple)):
                parts.extend(extract_part_numbers_from_any(sub))
        return unique_strings(parts)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            parts.extend(extract_part_numbers_from_any(item))
        return unique_strings(parts)
    return parts


def normalize_category(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower().replace(" ", "_").replace("-", "_")
    lowered = re.sub(r"_+", "_", lowered)
    if lowered in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[lowered]
    for needle, category in CATEGORY_ALIASES.items():
        if needle in lowered:
            return category
    return lowered


def add_category(counter: Counter[str], value: Any, weight: int = 1) -> None:
    category = normalize_category(value)
    if category:
        counter[category] += int(weight or 1)


def find_records(payload: Mapping[str, Any], keys: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list) and value and all(isinstance(x, dict) for x in value[:20]):
            records.extend([x for x in value if isinstance(x, dict)])
    return records


def find_community_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = find_records(payload, DOC_LIST_KEYS)
    if records:
        # Keep rows that look community-ish, but do not discard when the shape is generic.
        communityish = []
        for record in records:
            if any(k in record for k in ("community_id", "community", "community_key")):
                communityish.append(record)
            elif str(record.get("id") or record.get("node_id") or "").startswith("tracenet_community"):
                communityish.append(record)
            elif record.get("node_type") == "community":
                communityish.append(record)
        return communityish or records
    return []


def community_id(record: Mapping[str, Any], fallback_index: int = 0) -> str:
    raw = find_first(record, ("community_id", "id", "node_id", "community", "community_key"))
    if raw:
        text = str(raw).strip()
        if text.startswith("community::"):
            text = text.split("::", 1)[1]
        return text
    return f"tracenet_community_{fallback_index:05d}"


def extract_label(record: Mapping[str, Any], cid: str) -> str:
    label = find_first(record, ("label", "title", "name", "community_label", "display_label"))
    if label:
        return str(label).strip()
    part_numbers = extract_part_numbers_from_any(record)
    if part_numbers:
        return f"Part family community {part_numbers[0][:9]}"
    return "TRACE-Net graph community"


def extract_category_counter(record: Mapping[str, Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for key in ("category_counts", "category_distribution", "dominant_category_counts", "element_category_counts", "family_counts"):
        value = record.get(key)
        if isinstance(value, Mapping):
            for category, count in value.items():
                try:
                    weight = int(count)
                except Exception:
                    weight = 1
                add_category(counter, category, max(weight, 1))
    for key in ("dominant_category", "page_category_label", "category", "category_family", "dc_type", "dc:type"):
        if key in record:
            add_category(counter, record.get(key), 3 if key == "dominant_category" else 1)
    for key in ("categories", "category_labels", "element_categories", "families", "dc_types"):
        for item in as_list(record.get(key)):
            if isinstance(item, Mapping):
                add_category(counter, find_first(item, ("category", "label", "family", "type", "name")))
            else:
                add_category(counter, item)
    dc = record.get("dc")
    if isinstance(dc, Mapping):
        for item in as_list(dc.get("dc:type") or dc.get("type")):
            add_category(counter, item)
    return counter


def build_page_category_index(*payloads: Mapping[str, Any]) -> dict[str, Counter[str]]:
    index: dict[str, Counter[str]] = defaultdict(Counter)
    for payload in payloads:
        for record in find_records(payload, PAGE_PROFILE_KEYS):
            page_ids = extract_page_ids_from_any({
                "page_id": record.get("page_id"),
                "source_page_id": record.get("source_page_id"),
                "canonical_page_id": record.get("canonical_page_id"),
                "page_ids": record.get("page_ids"),
            })
            if not page_ids:
                page_ids = extract_page_ids_from_any(record)
                # Avoid indexing all nested sample pages from community cards as page-profile rows.
                if len(page_ids) > 1 and not any(k in record for k in ("page_id", "source_page_id", "canonical_page_id")):
                    page_ids = []
            if not page_ids:
                continue
            cats = extract_category_counter(record)
            if not cats:
                continue
            for page_id in page_ids:
                index[page_id].update(cats)
    return dict(index)


def build_community_overlay_index(*payloads: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for i, record in enumerate(find_community_records(payload), 1):
            cid = community_id(record, i)
            existing = index.setdefault(
                cid,
                {
                    "community_id": cid,
                    "page_ids": [],
                    "part_numbers": [],
                    "category_counts": Counter(),
                    "labels": [],
                    "raw_record_count": 0,
                },
            )
            existing["raw_record_count"] += 1
            existing["page_ids"] = unique_strings(existing["page_ids"] + extract_page_ids_from_any(record))
            existing["part_numbers"] = unique_strings(existing["part_numbers"] + extract_part_numbers_from_any(record))
            label = find_first(record, ("label", "title", "name", "community_label", "display_label"))
            if label:
                existing["labels"] = unique_strings(existing["labels"] + [label])
            existing["category_counts"].update(extract_category_counter(record))
    return index


def dominant_category(counter: Counter[str]) -> tuple[str | None, int, float]:
    total = sum(counter.values())
    if total <= 0:
        return None, 0, 0.0
    cat, count = counter.most_common(1)[0]
    return cat, count, round(float(count) / float(total), 6)


def compact_counter(counter: Counter[str]) -> dict[str, int]:
    return {k: int(v) for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))}


def navigation_intent_for(label: str, category: str | None, part_count: int) -> str:
    lowered = (label or "").lower()
    if part_count > 0 or "part" in lowered:
        return "part_family_navigation"
    if category == "table_evidence":
        return "table_evidence_navigation"
    if category == "visual_evidence":
        return "visual_evidence_navigation"
    if category == "review_signal":
        return "review_navigation"
    if category == "source_identity":
        return "source_identity_navigation"
    return "mixed_evidence_navigation"


def make_record(
    cid: str,
    base: Mapping[str, Any],
    overlay: Mapping[str, Any] | None,
    page_category_index: Mapping[str, Counter[str]],
) -> dict[str, Any]:
    overlay = overlay or {}
    label = extract_label(base, cid)
    if overlay.get("labels"):
        label = str(overlay["labels"][0])

    page_ids = unique_strings(
        extract_page_ids_from_any(base)
        + list(overlay.get("page_ids") or [])
        + unique_strings(as_list(base.get("member_page_ids")))
        + unique_strings(as_list(base.get("sample_page_ids")))
    )
    part_numbers = unique_strings(extract_part_numbers_from_any(base) + list(overlay.get("part_numbers") or []))

    category_counts: Counter[str] = Counter()
    category_counts.update(extract_category_counter(base))
    overlay_counts = overlay.get("category_counts")
    if isinstance(overlay_counts, Counter):
        category_counts.update(overlay_counts)
    elif isinstance(overlay_counts, Mapping):
        for k, v in overlay_counts.items():
            try:
                category_counts[normalize_category(k) or str(k)] += int(v)
            except Exception:
                category_counts[normalize_category(k) or str(k)] += 1

    page_derived_count = 0
    for page_id in page_ids:
        cats = page_category_index.get(page_id)
        if cats:
            category_counts.update(cats)
            page_derived_count += 1

    dom, dom_count, dom_ratio = dominant_category(category_counts)
    risk_flags: list[str] = []
    review_reasons: list[str] = []
    if not page_ids:
        risk_flags.append("missing_page_membership")
        review_reasons.append("community_has_no_page_membership_signal")
    if not category_counts:
        risk_flags.append("missing_category_summary")
        review_reasons.append("community_missing_category_distribution")
    if category_counts and dom_ratio < 0.34:
        risk_flags.append("low_category_coherence")
        review_reasons.append("community_category_distribution_is_mixed")
    if len(page_ids) >= 50:
        risk_flags.append("large_community")
        review_reasons.append("community_has_large_page_membership")

    hydrated = bool(category_counts)
    source_methods: list[str] = []
    if extract_category_counter(base):
        source_methods.append("source_leiden_record")
    if overlay_counts:
        source_methods.append("category_overlay_or_graph_ui_record")
    if page_derived_count:
        source_methods.append("page_category_profile_rollup")

    record = {
        "schema_version": SCHEMA_VERSION,
        "community_id": cid,
        "label": label,
        "page_count": len(page_ids),
        "sample_page_ids": page_ids[:12],
        "page_ids": page_ids,
        "part_number_count": len(part_numbers),
        "sample_part_numbers": part_numbers[:20],
        "category_summary_hydrated": hydrated,
        "category_summary_source_methods": source_methods,
        "page_profiles_used_for_rollup_count": page_derived_count,
        "category_counts": compact_counter(category_counts),
        "dominant_category": dom,
        "dominant_category_count": dom_count,
        "dominant_category_ratio": dom_ratio,
        "navigation_intent": navigation_intent_for(label, dom, len(part_numbers)),
        "risk_flags": risk_flags,
        "review_recommended": bool(risk_flags),
        "review_reasons": review_reasons,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "community_as_proof": False,
        "category_as_proof": False,
        "source_truth_mutation_allowed": False,
    }
    return record


def build_hydrator_report(
    *,
    leiden_communities: Mapping[str, Any],
    category_aware_leiden_overlay: Mapping[str, Any],
    element_category_taxonomy: Mapping[str, Any],
    dublin_core_refined: Mapping[str, Any],
    graph_ui_community_overlay: Mapping[str, Any] | None = None,
    leiden_quality_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    graph_ui_community_overlay = graph_ui_community_overlay or {}
    leiden_quality_audit = leiden_quality_audit or {}

    leiden_records = find_community_records(leiden_communities)
    category_overlay_index = build_community_overlay_index(category_aware_leiden_overlay, graph_ui_community_overlay, leiden_quality_audit)
    page_category_index = build_page_category_index(
        category_aware_leiden_overlay,
        element_category_taxonomy,
        dublin_core_refined,
        graph_ui_community_overlay,
    )

    community_ids: list[str] = []
    base_by_id: dict[str, Mapping[str, Any]] = {}
    for i, record in enumerate(leiden_records, 1):
        cid = community_id(record, i)
        community_ids.append(cid)
        base_by_id[cid] = record
    for cid in sorted(category_overlay_index):
        if cid not in base_by_id:
            community_ids.append(cid)
            base_by_id[cid] = {"community_id": cid, "label": "TRACE-Net graph community"}

    records = [make_record(cid, base_by_id.get(cid, {}), category_overlay_index.get(cid), page_category_index) for cid in unique_strings(community_ids)]
    records.sort(key=lambda r: (not r["review_recommended"], r["community_id"]))

    review_records = [r for r in records if r.get("review_recommended")]
    category_counter: Counter[str] = Counter()
    risk_counter: Counter[str] = Counter()
    intent_counter: Counter[str] = Counter()
    for record in records:
        if record.get("dominant_category"):
            category_counter[record["dominant_category"]] += 1
        risk_counter.update(record.get("risk_flags") or [])
        intent_counter[record.get("navigation_intent") or "unknown"] += 1

    source_quality_statuses = {
        "leiden_graph_communities": leiden_communities.get("quality_status") or leiden_communities.get("status"),
        "category_aware_leiden_overlay": category_aware_leiden_overlay.get("quality_status") or category_aware_leiden_overlay.get("status"),
        "element_category_taxonomy": element_category_taxonomy.get("quality_status") or element_category_taxonomy.get("status"),
        "dublin_core_refined": dublin_core_refined.get("quality_status") or dublin_core_refined.get("status"),
        "graph_ui_community_overlay": graph_ui_community_overlay.get("quality_status") or graph_ui_community_overlay.get("status"),
        "leiden_community_quality_audit": leiden_quality_audit.get("quality_status") or leiden_quality_audit.get("status"),
    }

    hydrated_count = sum(1 for r in records if r.get("category_summary_hydrated"))
    missing_page_count = sum(1 for r in records if "missing_page_membership" in (r.get("risk_flags") or []))
    missing_summary_count = sum(1 for r in records if "missing_category_summary" in (r.get("risk_flags") or []))
    low_coherence_count = sum(1 for r in records if "low_category_coherence" in (r.get("risk_flags") or []))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "trace_net_leiden_category_summary_rollup_v1",
        "source_quality_statuses": source_quality_statuses,
        "source_leiden_community_count": len(leiden_records),
        "community_hydration_record_count": len(records),
        "category_summary_hydrated_count": hydrated_count,
        "missing_category_summary_count": missing_summary_count,
        "missing_page_membership_count": missing_page_count,
        "low_category_coherence_count": low_coherence_count,
        "review_recommended_community_count": len(review_records),
        "effective_page_count": len({p for r in records for p in r.get("page_ids", [])}),
        "page_category_profile_count": len(page_category_index),
        "dominant_category_counts": dict(category_counter),
        "navigation_intent_counts": dict(intent_counter),
        "risk_flag_counts": dict(risk_counter),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "LEIDEN_CATEGORY_SUMMARY_HYDRATED",
        "quality_status": "UNVERIFIED",
        "summary": summary,
        "community_hydration_records": records,
        "review_recommended_records": review_records[:100],
    }
    return report


@dataclass
class QualityThresholds:
    require_page_count: int | None = None
    min_communities: int = 1
    min_hydrated_communities: int = 1
    max_missing_page_membership: int | None = None
    max_missing_category_summary: int | None = None
    max_community_as_proof: int = 0
    max_category_as_proof: int = 0
    max_retrieval_only_answer_allowed: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_leiden_quality_pass: bool = False
    require_category_overlay_quality_pass: bool = False
    require_dublin_core_quality_pass: bool = False


def status_is_pass(value: Any) -> bool:
    return str(value or "").upper() in {"PASS", "OK", "BUILT", "LOADED", "LEIDEN_COMMUNITY_QUALITY_AUDIT_BUILT"}


def check_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    issues: list[str] = []

    def require(name: str, ok: bool, detail: str) -> None:
        if not ok:
            issues.append(f"{name}: {detail}")

    require("community_count", int(summary.get("community_hydration_record_count") or 0) >= thresholds.min_communities, f"expected >= {thresholds.min_communities}")
    require("hydrated_count", int(summary.get("category_summary_hydrated_count") or 0) >= thresholds.min_hydrated_communities, f"expected >= {thresholds.min_hydrated_communities}")

    if thresholds.require_page_count is not None:
        require("effective_page_count", int(summary.get("effective_page_count") or 0) >= thresholds.require_page_count, f"expected >= {thresholds.require_page_count}")
    if thresholds.max_missing_page_membership is not None:
        require("missing_page_membership_count", int(summary.get("missing_page_membership_count") or 0) <= thresholds.max_missing_page_membership, f"expected <= {thresholds.max_missing_page_membership}")
    if thresholds.max_missing_category_summary is not None:
        require("missing_category_summary_count", int(summary.get("missing_category_summary_count") or 0) <= thresholds.max_missing_category_summary, f"expected <= {thresholds.max_missing_category_summary}")

    require("community_as_proof_count", int(summary.get("community_as_proof_count") or 0) <= thresholds.max_community_as_proof, f"expected <= {thresholds.max_community_as_proof}")
    require("category_as_proof_count", int(summary.get("category_as_proof_count") or 0) <= thresholds.max_category_as_proof, f"expected <= {thresholds.max_category_as_proof}")
    require("retrieval_only_answer_allowed_count", int(summary.get("retrieval_only_answer_allowed_count") or 0) <= thresholds.max_retrieval_only_answer_allowed, f"expected <= {thresholds.max_retrieval_only_answer_allowed}")
    require("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count") or 0) <= thresholds.max_source_truth_mutation_allowed, f"expected <= {thresholds.max_source_truth_mutation_allowed}")
    require("postgres_write_attempt_count", int(summary.get("postgres_write_attempt_count") or 0) == 0, "must be 0")
    require("qdrant_write_attempt_count", int(summary.get("qdrant_write_attempt_count") or 0) == 0, "must be 0")
    require("opensearch_write_attempt_count", int(summary.get("opensearch_write_attempt_count") or 0) == 0, "must be 0")

    source_statuses = summary.get("source_quality_statuses") or {}
    if thresholds.require_leiden_quality_pass:
        require("leiden_quality", status_is_pass(source_statuses.get("leiden_graph_communities")), f"got {source_statuses.get('leiden_graph_communities')}")
    if thresholds.require_category_overlay_quality_pass:
        require("category_overlay_quality", status_is_pass(source_statuses.get("category_aware_leiden_overlay")), f"got {source_statuses.get('category_aware_leiden_overlay')}")
    if thresholds.require_dublin_core_quality_pass:
        require("dublin_core_quality", status_is_pass(source_statuses.get("dublin_core_refined")), f"got {source_statuses.get('dublin_core_refined')}")

    quality_status = "PASS" if not issues else "FAIL"
    quality = {
        "schema_version": SCHEMA_VERSION,
        "status": report.get("status"),
        "quality_status": quality_status,
        "issues": issues,
        "summary": summary,
    }
    return quality


def write_markdown(path: str | Path, report: Mapping[str, Any], quality: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    lines = [
        "# TRACE-Net Leiden Category Summary Hydrator v1",
        "",
        f"Quality status: **{quality.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Key counts",
        "",
    ]
    for key in (
        "community_hydration_record_count",
        "category_summary_hydrated_count",
        "missing_category_summary_count",
        "missing_page_membership_count",
        "low_category_coherence_count",
        "review_recommended_community_count",
        "effective_page_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- `{key}`: {summary.get(key)}")
    lines.extend([
        "",
        "## Safety contract",
        "",
        "Communities and categories are navigation/ranking hints only. This artifact does not grant answer permission or claim-proof authority.",
    ])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_thresholds(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_hydrated_communities=args.min_hydrated_communities,
        max_missing_page_membership=args.max_missing_page_membership,
        max_missing_category_summary=args.max_missing_category_summary,
        max_community_as_proof=args.max_community_as_proof,
        max_category_as_proof=args.max_category_as_proof,
        max_retrieval_only_answer_allowed=args.max_retrieval_only_answer_allowed,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_leiden_quality_pass=args.require_leiden_quality_pass,
        require_category_overlay_quality_pass=args.require_category_overlay_quality_pass,
        require_dublin_core_quality_pass=args.require_dublin_core_quality_pass,
    )


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-hydrated-communities", type=int, default=1)
    parser.add_argument("--max-missing-page-membership", type=int, default=None)
    parser.add_argument("--max-missing-category-summary", type=int, default=None)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-category-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-quality-pass", action="store_true")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Leiden Category Summary Hydrator v1")
    parser.add_argument("--leiden-communities", required=True)
    parser.add_argument("--category-aware-leiden-overlay", required=True)
    parser.add_argument("--element-category-taxonomy", required=True)
    parser.add_argument("--dublin-core-refined", required=True)
    parser.add_argument("--graph-ui-community-overlay", required=False)
    parser.add_argument("--leiden-community-quality-audit", required=False)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_hydrator_report(
        leiden_communities=load_json(args.leiden_communities),
        category_aware_leiden_overlay=load_json(args.category_aware_leiden_overlay),
        element_category_taxonomy=load_json(args.element_category_taxonomy),
        dublin_core_refined=load_json(args.dublin_core_refined),
        graph_ui_community_overlay=load_json(args.graph_ui_community_overlay, required=False),
        leiden_quality_audit=load_json(args.leiden_community_quality_audit, required=False),
    )

    thresholds = parse_thresholds(args)
    quality = check_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["quality_issues"] = quality["issues"]

    report_path = out_dir / DEFAULT_OUTPUT_NAME
    quality_path = out_dir / DEFAULT_QUALITY_NAME
    markdown_path = out_dir / DEFAULT_MARKDOWN_NAME
    records_path = out_dir / DEFAULT_RECORDS_JSONL_NAME

    write_json(report_path, report)
    write_json(quality_path, quality)
    write_jsonl(records_path, report.get("community_hydration_records") or [])
    write_markdown(markdown_path, report, quality)

    summary = report.get("summary") or {}
    print("TRACE-Net Leiden Category Summary Hydrator v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "community_hydration_record_count",
        "category_summary_hydrated_count",
        "missing_category_summary_count",
        "missing_page_membership_count",
        "low_category_coherence_count",
        "review_recommended_community_count",
        "effective_page_count",
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
    print(f" quality_path: {quality_path}")
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
