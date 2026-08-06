"""TRACE-Net Page Element Registry v1.

This module builds one read-only page intake/element registry record per page.
It reconciles existing TRACE-Net artifacts such as page retrieval profiles,
embedding candidates, context helpers, and the frozen graph baseline into a
single front-start TRACE-Net control artifact.

The registry can classify and route. It cannot answer directly, prove claims by
itself, or mutate source truth.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_page_element_registry_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/page_element_registry")

ROUTE_ONLY_AUTHORITY = "page_element_registry_route_only"
TRUST_POLICY = "evidence_consensus_then_trust_authority_gate"

ANSWER_SUPPORT_BUCKETS = {"source_text_evidence", "verified_part_evidence"}
RETRIEVAL_ONLY_BUCKETS = {
    "source_evidence",
    "derived_context",
    "context_retrieval_helper",
    "page_retrieval_profile",
    "table_retrieval_helper",
    "figure_retrieval_helper",
}

FORBIDDEN_DIRECT_FLAGS = {
    "can_answer_directly": False,
    "can_prove_claims": False,
    "can_mutate_source_truth": False,
    "canonical_source_truth": False,
    "embedding_answer_authority_allowed": False,
}

TABLE_TERMS = {
    "table",
    "list of effective pages",
    "effective pages",
    "parts list",
    "vendor list",
    "ipl",
    "grid",
    "row",
    "column",
}
FIGURE_TERMS = {
    "figure",
    "diagram",
    "illustration",
    "visual",
    "callout",
    "drawing",
    "image",
    "chart",
}
REVISION_TERMS = {
    "revision",
    "revised pages",
    "record of revisions",
    "supersedes",
    "effective pages",
    "insert revised pages",
    "date inserted",
}
FRONT_MATTER_TERMS = {
    "title",
    "manual",
    "technical publication",
    "emb84",
    "embraer",
    "t.p.",
    "t p",
}
PART_TERMS = {"part", "nomenclature", "catalog", "ipl", "item", "assy", "assembly"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any, length: int = 16) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def read_json(path: str | Path | None, *, required: bool = False, default: Any = None) -> Any:
    if path is None:
        if required:
            raise FileNotFoundError("Missing required path")
        return default
    p = Path(path)
    if not p.exists():
        if required:
            raise FileNotFoundError(str(p))
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def first_existing_list(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def parse_page_number(page_id: str | None, fallback: int | None = None) -> int | None:
    if not page_id:
        return fallback
    match = re.search(r"p0*([0-9]+)$", str(page_id))
    if match:
        return int(match.group(1))
    return fallback


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, (list, tuple, set)):
        return " ".join(norm_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(norm_text(v) for v in value.values())
    return str(value).lower()


def has_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def dedupe_preserve(values: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, ensure_ascii=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def extract_summary_status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    quality = payload.get("quality")
    if isinstance(quality, dict):
        status = quality.get("status") or quality.get("quality_status")
        if status:
            return str(status)
    for key in ("quality_status", "status"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("quality_status", "status"):
            value = summary.get(key)
            if isinstance(value, str):
                return value
    return ""


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class RegistryInputs:
    page_profiles_path: Path
    embedding_candidates_path: Path
    context_helpers_path: Path | None = None
    baseline_checkpoint_path: Path | None = None
    evidence_consensus_summary_path: Path | None = None
    image_recognition_quality_path: Path | None = None


def load_registry_inputs(inputs: RegistryInputs) -> dict[str, Any]:
    page_profiles_payload = read_json(inputs.page_profiles_path, required=True)
    embedding_candidates_payload = read_json(inputs.embedding_candidates_path, required=True)
    context_helpers_payload = read_json(inputs.context_helpers_path, default={})
    baseline_payload = read_json(inputs.baseline_checkpoint_path, default={})
    evidence_consensus_payload = read_json(inputs.evidence_consensus_summary_path, default={})
    image_recognition_payload = read_json(inputs.image_recognition_quality_path, default={})
    return {
        "page_profiles_payload": page_profiles_payload,
        "embedding_candidates_payload": embedding_candidates_payload,
        "context_helpers_payload": context_helpers_payload,
        "baseline_payload": baseline_payload,
        "evidence_consensus_payload": evidence_consensus_payload,
        "image_recognition_payload": image_recognition_payload,
    }


def index_artifacts(payloads: dict[str, Any]) -> dict[str, Any]:
    page_profiles = first_existing_list(payloads["page_profiles_payload"], ("records", "page_profiles", "profiles"))
    candidates = first_existing_list(payloads["embedding_candidates_payload"], ("records", "embedding_candidates", "candidates"))
    helpers = first_existing_list(payloads["context_helpers_payload"], ("records", "helpers", "context_helpers"))

    pages: dict[str, dict[str, Any]] = {}
    candidates_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    helpers_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for profile in page_profiles:
        page_id = str(profile.get("page_id") or profile.get("id") or "").strip()
        if not page_id:
            continue
        pages.setdefault(page_id, {"page_profile": profile})
        pages[page_id]["page_profile"] = profile

    for candidate in candidates:
        page_id = str(candidate.get("page_id") or "").strip()
        if not page_id:
            continue
        candidates_by_page[page_id].append(candidate)
        pages.setdefault(page_id, {})

    for helper in helpers:
        page_id = str(helper.get("page_id") or "").strip()
        if not page_id:
            continue
        helpers_by_page[page_id].append(helper)
        pages.setdefault(page_id, {})

    return {
        "page_profiles": page_profiles,
        "candidates": candidates,
        "helpers": helpers,
        "pages": pages,
        "candidates_by_page": dict(candidates_by_page),
        "helpers_by_page": dict(helpers_by_page),
    }


def candidate_bucket_counts(candidates: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for candidate in candidates:
        bucket = candidate.get("rag_bucket") or candidate.get("safety_bucket") or candidate.get("bucket") or "unknown"
        counter[str(bucket)] += 1
    return counter


def candidate_citation_ids(candidates: list[dict[str, Any]]) -> list[str]:
    citation_ids: list[str] = []
    for candidate in candidates:
        for key in ("citation_id", "source_citation_id"):
            value = candidate.get(key)
            if value:
                citation_ids.append(str(value))
        for value in listify(candidate.get("citation_ids")):
            if value:
                citation_ids.append(str(value))
    return dedupe_preserve(citation_ids)


def candidate_source_ids(candidates: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for candidate in candidates:
        for key in ("source_candidate_id", "source_record_id", "source_id", "candidate_id", "embedding_candidate_id"):
            value = candidate.get(key)
            if value:
                ids.append(str(value))
    return dedupe_preserve(ids)


def build_detected_elements(
    page_id: str,
    profile: dict[str, Any],
    candidates: list[dict[str, Any]],
    helpers: list[dict[str, Any]],
    text_blob: str,
) -> list[dict[str, Any]]:
    buckets = candidate_bucket_counts(candidates)
    elements: list[dict[str, Any]] = []

    def add_element(element_type: str, status: str, answer_role: str, source: str, *, count: int = 1, route: str | None = None) -> None:
        elements.append(
            {
                "element_id": f"elem__{page_id}__{element_type}__{stable_hash([page_id, element_type, source], 8)}",
                "element_type": element_type,
                "status": status,
                "answer_role": answer_role,
                "source_signal": source,
                "record_count": count,
                "recommended_route": route or f"{element_type}_route",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "requires_source_resolution": True,
                "requires_citation": answer_role.startswith("answer_support"),
                "requires_authority_gate": True,
            }
        )

    if buckets.get("source_evidence", 0) > 0 or profile:
        add_element("source_trace", "available", "source_exists_only", "embedding_candidates/page_profile", count=max(1, buckets.get("source_evidence", 0)), route="source_trace_route")
    if buckets.get("source_text_evidence", 0) > 0:
        add_element("source_text", "available", "answer_support_with_citation", "embedding_candidates", count=buckets["source_text_evidence"], route="source_text_route")
    if buckets.get("verified_part_evidence", 0) > 0:
        add_element("part_catalog", "available", "answer_support_with_citation", "embedding_candidates", count=buckets["verified_part_evidence"], route="part_catalog_route")
    if buckets.get("derived_context", 0) > 0:
        add_element("derived_context", "available", "retrieval_only", "embedding_candidates", count=buckets["derived_context"], route="context_route")
    if helpers or profile.get("context_v2_present"):
        add_element("context_v2", "available", "retrieval_only", "context_helpers/page_profile", count=max(1, len(helpers)), route="context_v2_route")
    if has_any(text_blob, REVISION_TERMS):
        add_element("revision_or_effectivity_text", "candidate", "answer_support_after_source_text_gate", "term_detection", route="revision_metadata_route")
    if has_any(text_blob, TABLE_TERMS):
        add_element("table_or_list", "candidate", "retrieval_only_until_table_validated", "term_detection", route="table_candidate_route")
    if has_any(text_blob, FIGURE_TERMS):
        add_element("figure_chart_or_diagram", "candidate", "retrieval_only_until_visual_verified", "term_detection", route="figure_chart_route")
    if has_any(text_blob, FRONT_MATTER_TERMS):
        add_element("front_matter_or_title_block", "candidate", "answer_support_after_source_text_gate", "term_detection", route="title_block_route")

    if not elements:
        add_element("unknown_or_blank", "needs_review", "blocked_until_review", "fallback", route="human_review_route")

    return elements


def build_page_traits(
    profile: dict[str, Any],
    candidates: list[dict[str, Any]],
    helpers: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    text_blob: str,
) -> list[str]:
    buckets = candidate_bucket_counts(candidates)
    traits: list[str] = []

    if profile:
        traits.append("page_profile_present")
    if buckets.get("source_evidence", 0) > 0 or profile:
        traits.append("source_trace_present")
    if buckets.get("source_text_evidence", 0) > 0:
        traits.append("ocr_text_present")
    else:
        traits.append("ocr_text_missing_or_not_rag_eligible")
    if buckets.get("verified_part_evidence", 0) > 0 or has_any(text_blob, PART_TERMS):
        traits.append("part_or_catalog_signal")
    if buckets.get("derived_context", 0) > 0:
        traits.append("derived_context_present")
    if helpers or profile.get("context_v2_present"):
        traits.append("context_v2_present")
    if has_any(text_blob, TABLE_TERMS):
        traits.append("table_or_list_signal")
    if has_any(text_blob, FIGURE_TERMS):
        traits.append("figure_chart_or_diagram_signal")
    if has_any(text_blob, REVISION_TERMS):
        traits.append("revision_or_effectivity_signal")
    if has_any(text_blob, FRONT_MATTER_TERMS):
        traits.append("front_matter_or_title_signal")

    for element in elements:
        element_type = element.get("element_type")
        if element_type and element_type != "unknown_or_blank":
            traits.append(f"has_{element_type}")

    return sorted(set(traits))


def build_routes(traits: list[str], elements: list[dict[str, Any]], buckets: Counter[str]) -> list[str]:
    routes: list[str] = []
    for element in elements:
        route = element.get("recommended_route")
        if route:
            routes.append(str(route))

    if "ocr_text_missing_or_not_rag_eligible" in traits:
        routes.append("ocr_cleanup_or_review_route")
    if buckets.get("source_text_evidence", 0) == 0:
        routes.append("source_text_recovery_route")
    if any("table" in t for t in traits):
        routes.extend(["table_tile_route", "table_structure_validation_route"])
    if any("figure" in t or "diagram" in t or "chart" in t for t in traits):
        routes.extend(["visual_region_route", "visual_catalog_compare_route"])
    routes.append("evidence_consensus_route")
    routes.append("trust_authority_route")
    routes.append("graph_attachment_plan_route")
    return sorted(set(routes))


def build_fishnet_plan(traits: list[str], routes: list[str], buckets: Counter[str]) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []

    def add(layer: int, name: str, retry_route: str, trigger: str) -> None:
        layers.append(
            {
                "fishnet_layer": layer,
                "layer_name": name,
                "retry_route": retry_route,
                "trigger_condition": trigger,
                "can_answer_directly": False,
                "can_mutate_source_truth": False,
            }
        )

    add(0, "normal_extraction", "existing_extractor_outputs", "always_record_existing_outputs")
    add(1, "cleanup_normalization_retry", "ocr_cleanup_or_text_normalization", "if_ocr_noisy_missing_or_boilerplate_detected")

    if any("table" in route for route in routes):
        add(2, "table_region_retry", "table_crop_tile_and_tile_ocr", "if_table_or_list_signal_present")
    else:
        add(2, "region_retry_if_needed", "layout_region_retry", "if_low_confidence_or_missing_answer_support")

    if any("visual" in route or "figure" in route for route in routes):
        add(3, "visual_specialist_retry", "visual_text_callout_and_catalog_compare", "if_figure_chart_or_diagram_signal_present")
    else:
        add(3, "specialist_retry_if_needed", "route_specific_specialist_retry", "if_consensus_flags_extractor_gap")

    add(4, "ocr_catalog_graph_compare", "evidence_consensus_compare", "before_trust_assignment")
    add(5, "trust_downgrade_or_review", "human_review_or_block_if_still_weak", "if_unresolved_or_untrusted_after_compare")
    return layers


def build_comparison_targets(traits: list[str], buckets: Counter[str], citation_count: int) -> list[str]:
    targets = ["source_trace", "graph", "trust_authority", "rag_eligibility"]
    if buckets.get("source_text_evidence", 0) > 0 or "ocr_text_missing_or_not_rag_eligible" in traits:
        targets.append("ocr")
    if buckets.get("verified_part_evidence", 0) > 0 or "part_or_catalog_signal" in traits:
        targets.append("catalog_or_part_graph")
    if "table_or_list_signal" in traits:
        targets.append("table_extraction")
    if "figure_chart_or_diagram_signal" in traits:
        targets.append("visual_extraction")
    if citation_count > 0:
        targets.append("source_citation")
    return sorted(set(targets))


def build_graph_attachment_plan(
    page_id: str,
    elements: list[dict[str, Any]],
    buckets: Counter[str],
    citation_ids: list[str],
) -> dict[str, Any]:
    nodes = ["Page"]
    edges = []
    clean_buckets = []

    for element in elements:
        element_type = str(element.get("element_type") or "unknown")
        nodes.append(f"PageElement:{element_type}")
        edges.append({"from": page_id, "edge_type": "HAS_PAGE_ELEMENT", "to": element_type})

    for bucket, count in sorted(buckets.items()):
        if bucket in ANSWER_SUPPORT_BUCKETS or bucket in RETRIEVAL_ONLY_BUCKETS:
            clean_buckets.append({"bucket": bucket, "record_count": count})
            edges.append({"from": page_id, "edge_type": "HAS_SAFE_EVIDENCE_BUCKET", "to": bucket})

    for citation_id in citation_ids:
        nodes.append("SourceCitation")
        edges.append({"from": page_id, "edge_type": "HAS_CITATION", "to": citation_id})

    answer_support_count = sum(buckets.get(bucket, 0) for bucket in ANSWER_SUPPORT_BUCKETS)

    return {
        "plan_id": f"graph_attach_plan__{page_id}__{stable_hash([page_id, buckets, citation_ids], 8)}",
        "mode": "plan_only_no_postgres_mutation",
        "target_page_id": page_id,
        "node_types": sorted(set(nodes)),
        "planned_edges": edges,
        "clean_evidence_buckets": clean_buckets,
        "answer_support_candidate_count": answer_support_count,
        "citation_count": len(citation_ids),
        "clean_evidence_attached_or_available": bool(clean_buckets or citation_ids),
        "can_mutate_source_truth": False,
        "requires_authority_gate_before_answer": True,
    }


def build_registry_record(
    page_id: str,
    page_data: dict[str, Any],
    candidates: list[dict[str, Any]],
    helpers: list[dict[str, Any]],
) -> dict[str, Any]:
    profile = page_data.get("page_profile") or {}
    text_blob = norm_text(
        [
            profile.get("embedding_text"),
            profile.get("query_tunnel_terms"),
            profile.get("retrieval_cues"),
            profile.get("known_parts"),
            profile.get("known_nomenclature"),
            candidates,
            helpers,
        ]
    )
    buckets = candidate_bucket_counts(candidates)
    citation_ids = candidate_citation_ids(candidates)
    source_candidate_ids = candidate_source_ids(candidates)
    elements = build_detected_elements(page_id, profile, candidates, helpers, text_blob)
    traits = build_page_traits(profile, candidates, helpers, elements, text_blob)
    routes = build_routes(traits, elements, buckets)
    fishnet_plan = build_fishnet_plan(traits, routes, buckets)
    comparison_targets = build_comparison_targets(traits, buckets, len(citation_ids))
    graph_attachment_plan = build_graph_attachment_plan(page_id, elements, buckets, citation_ids)
    page_number = safe_int(profile.get("page_number"), default=parse_page_number(page_id) or 0) or parse_page_number(page_id)
    answer_support_candidate_count = sum(buckets.get(bucket, 0) for bucket in ANSWER_SUPPORT_BUCKETS)

    record = {
        "schema_version": SCHEMA_VERSION,
        "registry_record_id": f"page_registry__{page_id}__{stable_hash([page_id, buckets, traits], 10)}",
        "record_type": "page_element_registry",
        "authority": ROUTE_ONLY_AUTHORITY,
        "answer_use_policy": "registry_classifies_and_routes_only_not_answer_proof",
        "page_id": page_id,
        "page_number": page_number,
        "document_id": profile.get("document_id") or profile.get("manual_id") or "",
        "ata_code": profile.get("ata_code") or profile.get("ata") or "",
        "page_traits": traits,
        "detected_elements": elements,
        "recommended_extraction_routes": routes,
        "fishnet_retry_plan": fishnet_plan,
        "comparison_targets": comparison_targets,
        "trust_assignment_policy": TRUST_POLICY,
        "graph_attachment_plan": graph_attachment_plan,
        "candidate_bucket_counts": dict(sorted(buckets.items())),
        "candidate_count": len(candidates),
        "rag_candidate_count": len([c for c in candidates if str(c.get("record_type") or "").startswith("embedding") or c.get("source_candidate_id")]),
        "answer_support_candidate_count": answer_support_candidate_count,
        "retrieval_only_candidate_count": sum(buckets.get(bucket, 0) for bucket in RETRIEVAL_ONLY_BUCKETS),
        "citation_ids": citation_ids,
        "citation_count": len(citation_ids),
        "source_candidate_ids": source_candidate_ids[:50],
        "source_candidate_count": len(source_candidate_ids),
        "context_v2_present": bool(helpers or profile.get("context_v2_present")),
        "context_helper_count": len(helpers),
        "page_profile_present": bool(profile),
        "clean_evidence_attached": bool(graph_attachment_plan["clean_evidence_attached_or_available"]),
        "needs_human_review": any("review" in route for route in routes) or "unknown_or_blank" in {e.get("element_type") for e in elements},
        "review_reasons": [],
        "can_embed": True,
        "can_retrieve": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "source_truth_mutations_performed": 0,
    }

    if buckets.get("source_text_evidence", 0) == 0:
        record["review_reasons"].append("no_source_text_evidence_candidate")
    if not citation_ids and answer_support_candidate_count > 0:
        record["review_reasons"].append("answer_support_without_citation")
    if "ocr_text_missing_or_not_rag_eligible" in traits:
        record["review_reasons"].append("ocr_text_missing_or_not_rag_eligible")

    return record


def build_registry_report(
    *,
    page_profiles_path: str | Path,
    embedding_candidates_path: str | Path,
    context_helpers_path: str | Path | None = None,
    baseline_checkpoint_path: str | Path | None = None,
    evidence_consensus_summary_path: str | Path | None = None,
    image_recognition_quality_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    quality_config: dict[str, Any] | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    inputs = RegistryInputs(
        page_profiles_path=Path(page_profiles_path),
        embedding_candidates_path=Path(embedding_candidates_path),
        context_helpers_path=Path(context_helpers_path) if context_helpers_path else None,
        baseline_checkpoint_path=Path(baseline_checkpoint_path) if baseline_checkpoint_path else None,
        evidence_consensus_summary_path=Path(evidence_consensus_summary_path) if evidence_consensus_summary_path else None,
        image_recognition_quality_path=Path(image_recognition_quality_path) if image_recognition_quality_path else None,
    )
    payloads = load_registry_inputs(inputs)
    index = index_artifacts(payloads)

    records: list[dict[str, Any]] = []
    for page_id in sorted(index["pages"], key=lambda p: (parse_page_number(p) or 999999, p)):
        records.append(
            build_registry_record(
                page_id,
                index["pages"][page_id],
                index["candidates_by_page"].get(page_id, []),
                index["helpers_by_page"].get(page_id, []),
            )
        )

    summary = summarize_registry(records, payloads=payloads)
    quality = evaluate_registry_quality(summary, records, quality_config or {})

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_page_element_registry_v1.json"
    records_path = output_dir / "trace_net_page_element_registry_v1_records.jsonl"
    routes_path = output_dir / "trace_net_page_element_registry_v1_routes.jsonl"
    graph_plan_path = output_dir / "trace_net_page_element_registry_v1_graph_attachment_plan.jsonl"
    summary_path = output_dir / "trace_net_page_element_registry_v1_summary.json"
    manifest_path = output_dir / "trace_net_page_element_registry_v1_manifest.json"
    quality_path = output_dir / "trace_net_page_element_registry_v1_quality.json"
    matrix_json_path = output_dir / "trace_net_core_algorithm_matrix_v1.json"
    matrix_md_path = output_dir / "trace_net_core_algorithm_matrix_v1.md"
    markdown_path = output_dir / "trace_net_page_element_registry_v1.md"
    html_path = output_dir / "trace_net_page_element_registry_v1.html"

    matrix = build_algorithm_matrix(summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "status": "PAGE_ELEMENT_REGISTRY_BUILT",
        "quality_status": quality["status"],
        "input_paths": {
            "page_profiles": str(inputs.page_profiles_path),
            "embedding_candidates": str(inputs.embedding_candidates_path),
            "context_helpers": str(inputs.context_helpers_path) if inputs.context_helpers_path else "",
            "baseline_checkpoint": str(inputs.baseline_checkpoint_path) if inputs.baseline_checkpoint_path else "",
            "evidence_consensus_summary": str(inputs.evidence_consensus_summary_path) if inputs.evidence_consensus_summary_path else "",
            "image_recognition_quality": str(inputs.image_recognition_quality_path) if inputs.image_recognition_quality_path else "",
        },
        "output_paths": {
            "report": str(report_path),
            "records": str(records_path),
            "routes": str(routes_path),
            "graph_attachment_plan": str(graph_plan_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
            "matrix_json": str(matrix_json_path),
            "matrix_md": str(matrix_md_path),
            "markdown": str(markdown_path),
            "html": str(html_path),
        },
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "PAGE_ELEMENT_REGISTRY_BUILT",
        "quality_status": quality["status"],
        "created_at": manifest["created_at"],
        "record_count": len(records),
        "summary": summary,
        "quality": quality,
        "algorithm_matrix": matrix,
        "records": records,
        "manifest": manifest,
    }
    report["registry_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    manifest["registry_sha256"] = report["registry_sha256"]

    route_rows = []
    graph_rows = []
    for record in records:
        for route in record["recommended_extraction_routes"]:
            route_rows.append({"page_id": record["page_id"], "page_number": record["page_number"], "route": route})
        graph_rows.append({"page_id": record["page_id"], **record["graph_attachment_plan"]})

    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(routes_path, route_rows)
    write_jsonl(graph_plan_path, graph_rows)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    write_json(matrix_json_path, matrix)
    matrix_md_path.write_text(render_algorithm_matrix_markdown(matrix), encoding="utf-8")
    markdown_path.write_text(render_report_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(render_report_markdown(report)), encoding="utf-8")

    if write_quality:
        write_json(quality_path, quality)

    report["report_path"] = str(report_path)
    report["records_path"] = str(records_path)
    report["routes_path"] = str(routes_path)
    report["graph_attachment_plan_path"] = str(graph_plan_path)
    report["summary_path"] = str(summary_path)
    report["manifest_path"] = str(manifest_path)
    report["quality_path"] = str(quality_path)
    report["matrix_path"] = str(matrix_json_path)
    report["matrix_markdown_path"] = str(matrix_md_path)
    report["markdown_path"] = str(markdown_path)
    report["html_path"] = str(html_path)
    return report


def summarize_registry(records: list[dict[str, Any]], *, payloads: dict[str, Any]) -> dict[str, Any]:
    trait_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    element_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    authority_counts: Counter[str] = Counter()

    pages_with_elements = 0
    pages_with_routes = 0
    pages_with_fishnet = 0
    pages_with_comparison_targets = 0
    pages_with_graph_plan = 0
    pages_with_trust_policy = 0
    pages_with_source_trace = 0
    pages_with_ocr = 0
    empty_ocr_pages = 0
    pages_with_context_v2 = 0
    pages_with_answer_support = 0
    pages_with_citations = 0
    pages_needing_review = 0

    direct_answer_allowed = 0
    claim_proof_allowed = 0
    source_truth_mutation_allowed = 0
    unsafe_registry_records = 0
    missing_page_id = 0
    retrieval_only_answer_allowed = 0

    for record in records:
        page_id = record.get("page_id")
        if not page_id:
            missing_page_id += 1
        for trait in record.get("page_traits", []):
            trait_counts[str(trait)] += 1
        for route in record.get("recommended_extraction_routes", []):
            route_counts[str(route)] += 1
        for element in record.get("detected_elements", []):
            element_counts[str(element.get("element_type") or "unknown")] += 1
            if element.get("answer_role") == "retrieval_only" and element.get("can_answer_directly") is not False:
                retrieval_only_answer_allowed += 1
        for bucket, count in record.get("candidate_bucket_counts", {}).items():
            bucket_counts[str(bucket)] += safe_int(count)
        authority_counts[str(record.get("authority"))] += 1

        pages_with_elements += int(bool(record.get("detected_elements")))
        pages_with_routes += int(bool(record.get("recommended_extraction_routes")))
        pages_with_fishnet += int(bool(record.get("fishnet_retry_plan")))
        pages_with_comparison_targets += int(bool(record.get("comparison_targets")))
        pages_with_graph_plan += int(bool(record.get("graph_attachment_plan")))
        pages_with_trust_policy += int(bool(record.get("trust_assignment_policy")))
        pages_with_source_trace += int("source_trace_present" in record.get("page_traits", []))
        pages_with_ocr += int("ocr_text_present" in record.get("page_traits", []))
        empty_ocr_pages += int("ocr_text_missing_or_not_rag_eligible" in record.get("page_traits", []))
        pages_with_context_v2 += int(bool(record.get("context_v2_present")))
        pages_with_answer_support += int(safe_int(record.get("answer_support_candidate_count")) > 0)
        pages_with_citations += int(safe_int(record.get("citation_count")) > 0)
        pages_needing_review += int(bool(record.get("needs_human_review")))

        direct_answer_allowed += int(record.get("can_answer_directly") is not False)
        claim_proof_allowed += int(record.get("can_prove_claims") is not False)
        source_truth_mutation_allowed += int(record.get("can_mutate_source_truth") is not False)
        source_truth_mutation_allowed += safe_int(record.get("source_truth_mutations_performed"))
        if record.get("can_answer_directly") is not False or record.get("can_mutate_source_truth") is not False:
            unsafe_registry_records += 1

    baseline_status = extract_summary_status(payloads.get("baseline_payload"))
    page_profiles_status = extract_summary_status(payloads.get("page_profiles_payload"))
    embedding_candidates_status = extract_summary_status(payloads.get("embedding_candidates_payload"))
    context_helpers_status = extract_summary_status(payloads.get("context_helpers_payload"))
    evidence_consensus_status = extract_summary_status(payloads.get("evidence_consensus_payload"))
    image_recognition_status = extract_summary_status(payloads.get("image_recognition_payload"))

    return {
        "schema_version": SCHEMA_VERSION,
        "page_registry_record_count": len(records),
        "pages_with_detected_elements_count": pages_with_elements,
        "pages_with_recommended_routes_count": pages_with_routes,
        "pages_with_fishnet_plan_count": pages_with_fishnet,
        "pages_with_comparison_targets_count": pages_with_comparison_targets,
        "pages_with_graph_attachment_plan_count": pages_with_graph_plan,
        "pages_with_trust_policy_count": pages_with_trust_policy,
        "pages_with_source_trace_count": pages_with_source_trace,
        "pages_with_ocr_count": pages_with_ocr,
        "empty_or_missing_ocr_page_count": empty_ocr_pages,
        "pages_with_context_v2_count": pages_with_context_v2,
        "pages_with_answer_support_count": pages_with_answer_support,
        "pages_with_citations_count": pages_with_citations,
        "pages_needing_review_count": pages_needing_review,
        "direct_answer_allowed_count": direct_answer_allowed,
        "claim_proof_allowed_count": claim_proof_allowed,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "unsafe_registry_record_count": unsafe_registry_records,
        "missing_page_id_count": missing_page_id,
        "trait_counts": dict(sorted(trait_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "element_counts": dict(sorted(element_counts.items())),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "baseline_quality_status": baseline_status,
        "page_profiles_quality_status": page_profiles_status,
        "embedding_candidates_quality_status": embedding_candidates_status,
        "context_helpers_quality_status": context_helpers_status,
        "evidence_consensus_quality_status": evidence_consensus_status,
        "image_recognition_quality_status": image_recognition_status,
        "answer_status": "REGISTRY_ONLY",
        "final_answer_allowed": False,
        "can_mutate_source_truth": False,
    }


def evaluate_registry_quality(summary: dict[str, Any], records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, observed: Any, expected: Any, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected, "severity": severity})

    thresholds = {
        "min_page_records": config.get("min_page_records", 1),
        "min_pages_with_detected_elements": config.get("min_pages_with_detected_elements", 1),
        "min_pages_with_recommended_routes": config.get("min_pages_with_recommended_routes", 1),
        "min_pages_with_fishnet": config.get("min_pages_with_fishnet", 1),
        "min_pages_with_comparison_targets": config.get("min_pages_with_comparison_targets", 1),
        "min_pages_with_graph_attachment_plan": config.get("min_pages_with_graph_attachment_plan", 1),
        "min_pages_with_trust_policy": config.get("min_pages_with_trust_policy", 1),
        "min_pages_with_source_trace": config.get("min_pages_with_source_trace", 1),
        "min_pages_with_ocr": config.get("min_pages_with_ocr", 1),
        "max_missing_page_id": config.get("max_missing_page_id", 0),
        "max_unsafe_registry_records": config.get("max_unsafe_registry_records", 0),
        "max_retrieval_only_answer_allowed": config.get("max_retrieval_only_answer_allowed", 0),
        "max_source_truth_mutation_allowed": config.get("max_source_truth_mutation_allowed", 0),
        "max_direct_answer_allowed": config.get("max_direct_answer_allowed", 0),
    }

    add_check("min_page_records", summary["page_registry_record_count"] >= thresholds["min_page_records"], summary["page_registry_record_count"], f">= {thresholds['min_page_records']}")
    add_check("min_pages_with_detected_elements", summary["pages_with_detected_elements_count"] >= thresholds["min_pages_with_detected_elements"], summary["pages_with_detected_elements_count"], f">= {thresholds['min_pages_with_detected_elements']}")
    add_check("min_pages_with_recommended_routes", summary["pages_with_recommended_routes_count"] >= thresholds["min_pages_with_recommended_routes"], summary["pages_with_recommended_routes_count"], f">= {thresholds['min_pages_with_recommended_routes']}")
    add_check("min_pages_with_fishnet", summary["pages_with_fishnet_plan_count"] >= thresholds["min_pages_with_fishnet"], summary["pages_with_fishnet_plan_count"], f">= {thresholds['min_pages_with_fishnet']}")
    add_check("min_pages_with_comparison_targets", summary["pages_with_comparison_targets_count"] >= thresholds["min_pages_with_comparison_targets"], summary["pages_with_comparison_targets_count"], f">= {thresholds['min_pages_with_comparison_targets']}")
    add_check("min_pages_with_graph_attachment_plan", summary["pages_with_graph_attachment_plan_count"] >= thresholds["min_pages_with_graph_attachment_plan"], summary["pages_with_graph_attachment_plan_count"], f">= {thresholds['min_pages_with_graph_attachment_plan']}")
    add_check("min_pages_with_trust_policy", summary["pages_with_trust_policy_count"] >= thresholds["min_pages_with_trust_policy"], summary["pages_with_trust_policy_count"], f">= {thresholds['min_pages_with_trust_policy']}")
    add_check("min_pages_with_source_trace", summary["pages_with_source_trace_count"] >= thresholds["min_pages_with_source_trace"], summary["pages_with_source_trace_count"], f">= {thresholds['min_pages_with_source_trace']}")
    add_check("min_pages_with_ocr", summary["pages_with_ocr_count"] >= thresholds["min_pages_with_ocr"], summary["pages_with_ocr_count"], f">= {thresholds['min_pages_with_ocr']}")
    add_check("missing_page_id_count", summary["missing_page_id_count"] <= thresholds["max_missing_page_id"], summary["missing_page_id_count"], f"<= {thresholds['max_missing_page_id']}")
    add_check("unsafe_registry_record_count", summary["unsafe_registry_record_count"] <= thresholds["max_unsafe_registry_records"], summary["unsafe_registry_record_count"], f"<= {thresholds['max_unsafe_registry_records']}")
    add_check("retrieval_only_answer_allowed_count", summary["retrieval_only_answer_allowed_count"] <= thresholds["max_retrieval_only_answer_allowed"], summary["retrieval_only_answer_allowed_count"], f"<= {thresholds['max_retrieval_only_answer_allowed']}")
    add_check("source_truth_mutation_allowed_count", summary["source_truth_mutation_allowed_count"] <= thresholds["max_source_truth_mutation_allowed"], summary["source_truth_mutation_allowed_count"], f"<= {thresholds['max_source_truth_mutation_allowed']}")
    add_check("direct_answer_allowed_count", summary["direct_answer_allowed_count"] <= thresholds["max_direct_answer_allowed"], summary["direct_answer_allowed_count"], f"<= {thresholds['max_direct_answer_allowed']}")

    if config.get("require_page_count") is not None:
        expected = safe_int(config["require_page_count"])
        add_check("require_page_count", summary["page_registry_record_count"] == expected, summary["page_registry_record_count"], expected)

    failed = [c for c in checks if not c["passed"] and c.get("severity") == "error"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not failed else "FAIL",
        "created_at": utc_now_iso(),
        "checks": checks,
        "summary": summary,
    }


def build_algorithm_matrix(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "trace_net_step": "Page enters system",
            "does_current_code_do_it": "Yes",
            "status": f"Registry represents {summary.get('page_registry_record_count', 0)} page(s); source trace pages: {summary.get('pages_with_source_trace_count', 0)}.",
        },
        {
            "trace_net_step": "Classify page traits",
            "does_current_code_do_it": "Yes",
            "status": f"Registry emits deterministic traits for {summary.get('pages_with_detected_elements_count', 0)} page(s). Trait families include OCR, source, table/list, figure/chart, part/catalog, context, and revision/front-matter signals.",
        },
        {
            "trace_net_step": "Choose extraction route",
            "does_current_code_do_it": "Yes",
            "status": f"Registry emits recommended extraction routes for {summary.get('pages_with_recommended_routes_count', 0)} page(s), including source, OCR, part, table, visual, context, consensus, trust, and graph-attachment routes.",
        },
        {
            "trace_net_step": "Run specialized extractors",
            "does_current_code_do_it": "Yes for current extractor outputs; registry plans next routes",
            "status": "Existing artifacts provide OCR/source/part/table/visual/context outputs. Registry does not rerun extractors; it records which existing outputs are present and which route should run next.",
        },
        {
            "trace_net_step": "Retry failures through fishnet layers",
            "does_current_code_do_it": "Planner implemented; universal executor future",
            "status": f"Registry emits fishnet retry plans for {summary.get('pages_with_fishnet_plan_count', 0)} page(s). It is plan-only and does not mutate source truth.",
        },
        {
            "trace_net_step": "Compare outputs against OCR/catalog/graph",
            "does_current_code_do_it": "Yes",
            "status": f"Registry emits comparison targets for {summary.get('pages_with_comparison_targets_count', 0)} page(s), including OCR, catalog/part graph, source trace, citations, table/visual signals, RAG eligibility, and trust authority where relevant.",
        },
        {
            "trace_net_step": "Assign trust tier",
            "does_current_code_do_it": "Yes",
            "status": f"Registry attaches trust assignment policy to {summary.get('pages_with_trust_policy_count', 0)} page(s): {TRUST_POLICY}.",
        },
        {
            "trace_net_step": "Attach clean evidence to graph",
            "does_current_code_do_it": "Plan generated; Postgres writeback remains explicit",
            "status": f"Registry emits graph attachment plans for {summary.get('pages_with_graph_attachment_plan_count', 0)} page(s). Plans are read-only and prepare Page -> Element/Evidence/Citation relationships.",
        },
    ]


def render_algorithm_matrix_markdown(matrix: list[dict[str, Any]]) -> str:
    lines = ["# TRACE-Net Core Algorithm Matrix v1", "", "| TRACE-Net step | Does current code do it? | Status |", "|---|---:|---|"]
    for row in matrix:
        lines.append(
            "| "
            + str(row["trace_net_step"]).replace("|", "\\|")
            + " | "
            + str(row["does_current_code_do_it"]).replace("|", "\\|")
            + " | "
            + str(row["status"]).replace("|", "\\|")
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def render_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Page Element Registry v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
        f"- Page registry records: {summary.get('page_registry_record_count')}",
        f"- Pages with detected elements: {summary.get('pages_with_detected_elements_count')}",
        f"- Pages with recommended routes: {summary.get('pages_with_recommended_routes_count')}",
        f"- Pages with fishnet plans: {summary.get('pages_with_fishnet_plan_count')}",
        f"- Pages with comparison targets: {summary.get('pages_with_comparison_targets_count')}",
        f"- Pages with graph attachment plans: {summary.get('pages_with_graph_attachment_plan_count')}",
        f"- Pages with source trace: {summary.get('pages_with_source_trace_count')}",
        f"- Pages with OCR/source text evidence: {summary.get('pages_with_ocr_count')}",
        f"- Pages with ContextV2: {summary.get('pages_with_context_v2_count')}",
        f"- Unsafe registry records: {summary.get('unsafe_registry_record_count')}",
        f"- Source truth mutation allowed: {summary.get('source_truth_mutation_allowed_count')}",
        "",
        "## Element counts",
        "",
    ]
    for key, value in sorted(summary.get("element_counts", {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Route counts", ""])
    for key, value in sorted(summary.get("route_counts", {}).items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", render_algorithm_matrix_markdown(report.get("algorithm_matrix", []))])
    return "\n".join(lines)


def render_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Page Element Registry v1</title></head><body><pre>{escaped}</pre></body></html>\n"


def make_quality_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = [
        "min_page_records",
        "min_pages_with_detected_elements",
        "min_pages_with_recommended_routes",
        "min_pages_with_fishnet",
        "min_pages_with_comparison_targets",
        "min_pages_with_graph_attachment_plan",
        "min_pages_with_trust_policy",
        "min_pages_with_source_trace",
        "min_pages_with_ocr",
        "require_page_count",
    ]
    config: dict[str, Any] = {}
    for key in keys:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    return config


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Page Element Registry v1")
    parser.add_argument("--page-profiles", default="local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json")
    parser.add_argument("--embedding-candidates", default="local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json")
    parser.add_argument("--context-helpers", default="local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json")
    parser.add_argument("--baseline-checkpoint", default="local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json")
    parser.add_argument("--evidence-consensus-summary", default="local_data/organization/trace_net/evidence_consensus/evidence_consensus_summary.json")
    parser.add_argument("--image-recognition-quality", default="local_data/organization/image_recognition/page_image_recognition_quality.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-pages-with-detected-elements", type=int, default=1)
    parser.add_argument("--min-pages-with-recommended-routes", type=int, default=1)
    parser.add_argument("--min-pages-with-fishnet", type=int, default=1)
    parser.add_argument("--min-pages-with-comparison-targets", type=int, default=1)
    parser.add_argument("--min-pages-with-graph-attachment-plan", type=int, default=1)
    parser.add_argument("--min-pages-with-trust-policy", type=int, default=1)
    parser.add_argument("--min-pages-with-source-trace", type=int, default=1)
    parser.add_argument("--min-pages-with-ocr", type=int, default=1)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--quality", action="store_true", help="Write quality JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = build_registry_report(
            page_profiles_path=args.page_profiles,
            embedding_candidates_path=args.embedding_candidates,
            context_helpers_path=args.context_helpers,
            baseline_checkpoint_path=args.baseline_checkpoint,
            evidence_consensus_summary_path=args.evidence_consensus_summary,
            image_recognition_quality_path=args.image_recognition_quality,
            output_dir=args.output_dir,
            quality_config=make_quality_config_from_args(args),
            write_quality=args.quality,
        )
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net page element registry failed: {exc}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print("TRACE-Net page element registry v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" page_registry_record_count: {summary['page_registry_record_count']}")
    print(f" pages_with_detected_elements_count: {summary['pages_with_detected_elements_count']}")
    print(f" pages_with_recommended_routes_count: {summary['pages_with_recommended_routes_count']}")
    print(f" pages_with_fishnet_plan_count: {summary['pages_with_fishnet_plan_count']}")
    print(f" pages_with_comparison_targets_count: {summary['pages_with_comparison_targets_count']}")
    print(f" pages_with_graph_attachment_plan_count: {summary['pages_with_graph_attachment_plan_count']}")
    print(f" pages_with_source_trace_count: {summary['pages_with_source_trace_count']}")
    print(f" pages_with_ocr_count: {summary['pages_with_ocr_count']}")
    print(f" pages_with_context_v2_count: {summary['pages_with_context_v2_count']}")
    print(f" unsafe_registry_record_count: {summary['unsafe_registry_record_count']}")
    print(f" source_truth_mutation_allowed_count: {summary['source_truth_mutation_allowed_count']}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


def check_quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Page Element Registry v1 quality")
    parser.add_argument("--report-path", default=str(DEFAULT_OUTPUT_DIR / "trace_net_page_element_registry_v1.json"))
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-pages-with-detected-elements", type=int, default=1)
    parser.add_argument("--min-pages-with-recommended-routes", type=int, default=1)
    parser.add_argument("--min-pages-with-fishnet", type=int, default=1)
    parser.add_argument("--min-pages-with-comparison-targets", type=int, default=1)
    parser.add_argument("--min-pages-with-graph-attachment-plan", type=int, default=1)
    parser.add_argument("--min-pages-with-trust-policy", type=int, default=1)
    parser.add_argument("--min-pages-with-source-trace", type=int, default=1)
    parser.add_argument("--min-pages-with-ocr", type=int, default=1)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    args = check_quality_arg_parser().parse_args(argv)
    try:
        report = read_json(args.report_path, required=True)
        records = first_existing_list(report, ("records",))
        summary = summarize_registry(records, payloads={
            "baseline_payload": {},
            "page_profiles_payload": {},
            "embedding_candidates_payload": {},
            "context_helpers_payload": {},
            "evidence_consensus_payload": {},
            "image_recognition_payload": {},
        })
        # Preserve upstream statuses/counts that do not derive from records when present.
        original_summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        for key in (
            "baseline_quality_status",
            "page_profiles_quality_status",
            "embedding_candidates_quality_status",
            "context_helpers_quality_status",
            "evidence_consensus_quality_status",
            "image_recognition_quality_status",
        ):
            if original_summary.get(key):
                summary[key] = original_summary[key]
        quality = evaluate_registry_quality(summary, records, make_quality_config_from_args(args))
        out_path = Path(args.report_path).with_name("trace_net_page_element_registry_v1_quality.json")
        if args.write_json:
            write_json(out_path, quality)
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net page element registry quality check failed: {exc}", file=sys.stderr)
        return 2

    s = quality["summary"]
    print("TRACE-Net page element registry v1 quality")
    print(f" Status: {quality['status']}")
    print(f" page_registry_record_count: {s['page_registry_record_count']}")
    print(f" pages_with_detected_elements_count: {s['pages_with_detected_elements_count']}")
    print(f" pages_with_recommended_routes_count: {s['pages_with_recommended_routes_count']}")
    print(f" pages_with_fishnet_plan_count: {s['pages_with_fishnet_plan_count']}")
    print(f" pages_with_comparison_targets_count: {s['pages_with_comparison_targets_count']}")
    print(f" pages_with_graph_attachment_plan_count: {s['pages_with_graph_attachment_plan_count']}")
    print(f" pages_with_source_trace_count: {s['pages_with_source_trace_count']}")
    print(f" pages_with_ocr_count: {s['pages_with_ocr_count']}")
    print(f" pages_with_context_v2_count: {s['pages_with_context_v2_count']}")
    print(f" unsafe_registry_record_count: {s['unsafe_registry_record_count']}")
    print(f" source_truth_mutation_allowed_count: {s['source_truth_mutation_allowed_count']}")
    if args.write_json:
        print(f" quality_path: {out_path}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
