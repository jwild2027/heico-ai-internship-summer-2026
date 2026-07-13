#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

STATUS = "TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_3_DONE"
SCHEMA_VERSION = "trace_net_visual_question_context_v1_3"
PAGE_RE = re.compile(r"^t_p_[A-Za-z0-9]+_[A-Za-z0-9]+_p\d{6}$")

ROUTE_KEYS = ("primary_route", "route", "selected_route", "dispatch_route")
PAGE_KEYS = ("page_id", "source_page_id", "canonical_page_id")

CONTENT_DIRS = (
    "llava_visual_summary_batch_v1",
    "image_visual_evidence_pack_v1",
    "image_visual_evidence_nomenclature_merger_v1",
    "figure_chart_understanding",
    "visual_callout_table_linker_v1",
    "visual_callout_table_linker_v2",
    "page_context_v2",
)

SKIP_NAMES = (
    "summary.json",
    "quality.json",
    "quality_check.json",
    "report.json",
    "manifest.json",
)

def read_json_records(path: Path) -> Iterable[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value
            return
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return
    if isinstance(value, dict):
        if isinstance(value.get("records"), list):
            for item in value["records"]:
                if isinstance(item, dict):
                    yield item
        elif any(k in value for k in PAGE_KEYS):
            yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item

def direct_page_id(record: dict[str, Any]) -> str | None:
    for key in PAGE_KEYS:
        value = record.get(key)
        if isinstance(value, str) and PAGE_RE.fullmatch(value):
            return value
    return None

def route_is_image_visual(record: dict[str, Any]) -> bool:
    for key in ROUTE_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value == "image_visual":
            return True
    return False

def discover_image_pages(route_manifest: Path) -> set[str]:
    pages = set()
    for record in read_json_records(route_manifest):
        if route_is_image_visual(record):
            page_id = direct_page_id(record)
            if page_id:
                pages.add(page_id)
    return pages

def add_unique(target: list[Any], values: Iterable[Any]) -> None:
    for value in values:
        if value in (None, "", [], {}):
            continue
        if value not in target:
            target.append(value)

def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def adapt_llava(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "visual_summary": record.get("visual_summary"),
        "diagram_type": record.get("diagram_type"),
        "visual_confidence": record.get("visual_confidence"),
        "visible_text_candidates": listify(record.get("visible_text_candidates")),
        "callout_candidates": listify(record.get("callout_candidates")),
        "figure_candidates": listify(record.get("figure_candidates")),
        "uncertainties": listify(record.get("uncertainties")),
        "source_trace_ready": record.get("source_trace_ready") is True,
        "source_trace": record.get("source_trace_fields"),
        "model": record.get("llava_model"),
        "record_id": record.get("record_id"),
    }

def adapt_visual_evidence(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "figure": record.get("figure"),
        "callout": record.get("callout"),
        "linked_part_number": record.get("linked_part_number"),
        "linked_description": record.get("linked_description"),
        "linked_description_quality": record.get("linked_description_quality"),
        "proof_strength": record.get("proof_strength"),
        "proof_source": record.get("proof_source"),
        "citation_ready": record.get("citation_ready") is True,
        "source_trace_ready": record.get("source_trace_ready") is True,
        "requires_human_review": record.get("requires_human_review") is True,
        "limitations": listify(record.get("limitations")),
        "evidence_id": record.get("evidence_id"),
        "visual_role": record.get("visual_role"),
    }

def adapt_nomenclature(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "linked_nomenclature": record.get("linked_nomenclature"),
        "nomenclature_merge_status": record.get("nomenclature_merge_status"),
        "linked_part_number": record.get("linked_part_number"),
        "figure": record.get("figure"),
        "callout": record.get("callout"),
    }

def adapt_figure_understanding(record: dict[str, Any]) -> dict[str, Any]:
    visual_regions = []
    for region in listify(record.get("visual_regions")):
        if not isinstance(region, dict):
            continue
        visual_regions.append({
            "region_id": region.get("region_id"),
            "region_type": region.get("region_type"),
            "source_snippet": region.get("source_snippet"),
            "detected_callout_labels": listify(region.get("detected_callout_labels")),
            "detected_figure_refs": listify(region.get("detected_figure_refs")),
            "linked_part_candidates": listify(region.get("linked_part_candidates")),
        })
    return {
        "ata_code": record.get("ata_code"),
        "visual_type": record.get("visual_type"),
        "image_classification": record.get("image_classification"),
        "image_role": record.get("image_role"),
        "figure_refs": listify(record.get("figure_refs")),
        "callout_labels": listify(record.get("callout_labels")),
        "item_refs": listify(record.get("item_refs")),
        "linked_part_candidates": listify(record.get("linked_part_candidates")),
        "visual_record_id": record.get("visual_record_id"),
        "visual_regions": visual_regions,
        "needs_human_review": record.get("needs_human_review") is True,
        "review_reasons": listify(record.get("review_reasons")),
        "citation_ids": listify(record.get("citation_ids")),
        "trust_tier": record.get("trust_tier"),
    }

def adapt_callout_link(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "figure": record.get("figure"),
        "callout": record.get("callout"),
        "linked_part_number": record.get("linked_part_number"),
        "linked_part_numbers": listify(record.get("linked_part_numbers")),
        "linked_description": record.get("linked_description"),
        "link_confidence": record.get("link_confidence"),
        "link_reason": record.get("link_reason"),
        "citation_ready": record.get("citation_ready") is True,
        "source_trace_ready": record.get("source_trace_ready") is True,
        "requires_human_review": record.get("requires_human_review") is True,
        "link_record_id": record.get("link_record_id"),
    }

def adapt_page_context(record: dict[str, Any]) -> dict[str, Any] | None:
    # Preserve the existing page_context_v2 contract and do not rename it.
    candidate = record.get("page_context_v2")
    if candidate not in (None, "", [], {}):
        return {"page_context_v2": candidate}
    for key in ("summary", "context", "context_text", "page_summary", "summary_text"):
        if record.get(key) not in (None, "", [], {}):
            return {"page_context_v2": record.get(key)}
    return None

def classify_path(path: Path) -> str | None:
    text = path.as_posix().lower()
    if "llava_visual_summary_batch_v1" in text:
        return "llava"
    if "image_visual_evidence_nomenclature_merger_v1" in text:
        return "nomenclature"
    if "image_visual_evidence_pack_v1" in text:
        return "visual_evidence"
    if "figure_chart_understanding" in text and "callouts" not in text and "regions" not in text and "graph_attachment_plan" not in text:
        return "figure_understanding"
    if "visual_callout_table_linker_v2" in text or "visual_callout_table_linker_v1" in text:
        return "callout_link"
    if "page_context_v2" in text:
        return "page_context_v2"
    return None

def iter_content_files(artifact_root: Path) -> Iterable[Path]:
    for dirname in CONTENT_DIRS:
        base = artifact_root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
                continue
            low_name = path.name.lower()
            if any(low_name.endswith(name) for name in SKIP_NAMES):
                continue
            yield path

def build_contexts(artifact_root: Path, route_manifest: Path, max_pages: int | None):
    image_pages = discover_image_pages(route_manifest)
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    metrics = {
        "scanned_file_count": 0,
        "scanned_record_count": 0,
        "accepted_record_count": 0,
        "rejected_non_image_route_page_count": 0,
        "rejected_noncanonical_page_id_count": 0,
    }

    for path in iter_content_files(artifact_root):
        role = classify_path(path)
        if role is None:
            continue
        metrics["scanned_file_count"] += 1
        for record in read_json_records(path):
            metrics["scanned_record_count"] += 1
            page_id = direct_page_id(record)
            if not page_id:
                metrics["rejected_noncanonical_page_id_count"] += 1
                continue
            if page_id not in image_pages:
                metrics["rejected_non_image_route_page_count"] += 1
                continue
            grouped[page_id][role].append({
                "path": path.as_posix(),
                "record": record,
            })
            metrics["accepted_record_count"] += 1

    contexts = []
    for page_id in sorted(grouped):
        buckets = grouped[page_id]
        llava = [adapt_llava(x["record"]) for x in buckets.get("llava", [])]
        evidence = [adapt_visual_evidence(x["record"]) for x in buckets.get("visual_evidence", [])]
        nomenclature = [adapt_nomenclature(x["record"]) for x in buckets.get("nomenclature", [])]
        figures = [adapt_figure_understanding(x["record"]) for x in buckets.get("figure_understanding", [])]
        links = [adapt_callout_link(x["record"]) for x in buckets.get("callout_link", [])]

        page_context_v2 = None
        for x in buckets.get("page_context_v2", []):
            adapted = adapt_page_context(x["record"])
            if adapted:
                page_context_v2 = adapted["page_context_v2"]
                break

        visual_ids: list[str] = []
        part_numbers: list[str] = []
        figure_refs: list[str] = []
        callouts: list[str] = []
        nomenclature_values: list[str] = []
        ata_numbers: list[str] = []
        object_descriptions: list[str] = []
        source_snippets: list[str] = []
        citation_ids: list[str] = []
        uncertainties: list[Any] = []
        human_review_reasons: list[str] = []

        for item in llava:
            add_unique(object_descriptions, [item.get("visual_summary")])
            add_unique(figure_refs, item.get("figure_candidates", []))
            add_unique(callouts, item.get("callout_candidates", []))
            add_unique(uncertainties, item.get("uncertainties", []))

        for item in evidence:
            add_unique(figure_refs, [item.get("figure")])
            add_unique(callouts, [item.get("callout")])
            add_unique(part_numbers, [item.get("linked_part_number")])
            add_unique(object_descriptions, [item.get("linked_description")])
            if item.get("requires_human_review"):
                add_unique(human_review_reasons, item.get("limitations", []))

        for item in nomenclature:
            add_unique(nomenclature_values, [item.get("linked_nomenclature")])
            add_unique(part_numbers, [item.get("linked_part_number")])
            add_unique(figure_refs, [item.get("figure")])
            add_unique(callouts, [item.get("callout")])

        for item in figures:
            add_unique(ata_numbers, [item.get("ata_code")])
            add_unique(figure_refs, item.get("figure_refs", []))
            add_unique(callouts, item.get("callout_labels", []))
            add_unique(part_numbers, item.get("linked_part_candidates", []))
            add_unique(citation_ids, item.get("citation_ids", []))
            add_unique(human_review_reasons, item.get("review_reasons", []))
            for region in item.get("visual_regions", []):
                add_unique(visual_ids, [region.get("region_id")])
                add_unique(source_snippets, [region.get("source_snippet")])
                add_unique(callouts, region.get("detected_callout_labels", []))
                add_unique(figure_refs, region.get("detected_figure_refs", []))
                add_unique(part_numbers, region.get("linked_part_candidates", []))

        for item in links:
            add_unique(figure_refs, [item.get("figure")])
            add_unique(callouts, [item.get("callout")])
            add_unique(part_numbers, [item.get("linked_part_number")])
            add_unique(part_numbers, item.get("linked_part_numbers", []))
            add_unique(object_descriptions, [item.get("linked_description")])
            if item.get("requires_human_review"):
                add_unique(human_review_reasons, [item.get("link_reason")])

        citation_ready = any(x.get("citation_ready") for x in evidence + links)
        source_trace_ready = any(x.get("source_trace_ready") for x in llava + evidence + links)

        content_refs = []
        for role, items in buckets.items():
            for item in items:
                content_refs.append({
                    "artifact_path": item["path"],
                    "artifact_role": role,
                    "page_id": page_id,
                })

        contexts.append({
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "route_provenance": {
                "route": "image_visual",
                "route_manifest": route_manifest.as_posix(),
            },
            "page_context_v2": page_context_v2,
            "visual_summary": {
                "descriptions": object_descriptions,
                "source_snippets": source_snippets,
                "diagram_types": [x["diagram_type"] for x in llava if x.get("diagram_type")],
                "visual_confidences": [x["visual_confidence"] for x in llava if x.get("visual_confidence")],
            },
            "visual_ids": visual_ids,
            "identifiers": {
                "part_numbers": part_numbers,
                "ata_numbers": ata_numbers,
                "figure_refs": figure_refs,
                "callouts": callouts,
                "nomenclature": nomenclature_values,
            },
            "ocr_vision_reconciliation": {
                "status": "not_explicitly_available",
                "vision_text_candidates": [
                    value
                    for item in llava
                    for value in item.get("visible_text_candidates", [])
                    if value not in (None, "")
                ],
                "ocr_text_candidates": [],
                "uncertainties": uncertainties,
                "character_conflicts": [],
            },
            "evidence_status": {
                "citation_ready": citation_ready,
                "source_trace_ready": source_trace_ready,
                "candidate_only": not (citation_ready and source_trace_ready),
                "human_review_required": bool(human_review_reasons),
                "human_review_reasons": human_review_reasons,
                "final_answer_allowed": False,
                "can_prove_claims": False,
            },
            "source_records": {
                "llava": llava,
                "visual_evidence": evidence,
                "nomenclature": nomenclature,
                "figure_understanding": figures,
                "callout_links": links,
            },
            "content_source_artifact_refs": content_refs,
            "safety_contract": {
                "read_only": True,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            },
        })
        if max_pages and len(contexts) >= max_pages:
            break

    return image_pages, contexts, metrics

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--route-manifest", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-pages", type=int)
    ap.add_argument("--min-context-count", type=int, default=1)
    ap.add_argument("--min-pages-with-description", type=int, default=1)
    ap.add_argument("--min-pages-with-visual-ids", type=int, default=1)
    args = ap.parse_args()

    artifact_root = Path(args.artifact_root)
    route_manifest = Path(args.route_manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_pages, contexts, metrics = build_contexts(artifact_root, route_manifest, args.max_pages)
    pages_with_description = sum(bool(x["visual_summary"]["descriptions"] or x["visual_summary"]["source_snippets"]) for x in contexts)
    pages_with_visual_ids = sum(bool(x["visual_ids"]) for x in contexts)
    pages_with_page_context = sum(x["page_context_v2"] is not None for x in contexts)
    pages_with_parts = sum(bool(x["identifiers"]["part_numbers"]) for x in contexts)
    pages_with_figure_refs = sum(bool(x["identifiers"]["figure_refs"]) for x in contexts)

    failures = []
    if len(contexts) < args.min_context_count:
        failures.append("context_count_below_minimum")
    if pages_with_description < args.min_pages_with_description:
        failures.append("pages_with_description_below_minimum")
    if pages_with_visual_ids < args.min_pages_with_visual_ids:
        failures.append("pages_with_visual_ids_below_minimum")
    quality = "PASS" if not failures else "FAIL"

    records_path = output_dir / "trace_net_visual_question_context_v1_3.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "trace_net_visual_question_context_v1_3_report.txt"

    records_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in contexts), encoding="utf-8")
    summary = {
        "status": STATUS,
        "quality_status": quality,
        "schema_version": SCHEMA_VERSION,
        "authoritative_image_route_page_count": len(image_pages),
        "context_count": len(contexts),
        "pages_with_description": pages_with_description,
        "pages_with_visual_ids": pages_with_visual_ids,
        "pages_with_page_context_v2": pages_with_page_context,
        "pages_with_part_numbers": pages_with_parts,
        "pages_with_figure_refs": pages_with_figure_refs,
        **metrics,
        "failure_reasons": failures,
        "final_answer_allowed_true_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "outputs": {
            "records": str(records_path),
            "summary": str(summary_path),
            "report": str(report_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = "\n".join(f"{k}={v}" for k, v in summary.items() if k != "outputs") + "\n"
    report_path.write_text(report, encoding="utf-8")

    print(f"status={STATUS}")
    print(f"quality_status={quality}")
    print(f"authoritative_image_route_page_count={len(image_pages)}")
    print(f"context_count={len(contexts)}")
    print(f"pages_with_description={pages_with_description}")
    print(f"pages_with_visual_ids={pages_with_visual_ids}")
    print(f"pages_with_page_context_v2={pages_with_page_context}")
    print(f"pages_with_part_numbers={pages_with_parts}")
    print(f"pages_with_figure_refs={pages_with_figure_refs}")
    print("final_answer_allowed_true_count=0")
    print("source_truth_mutation_allowed_count=0")
    print(f"records={records_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")
    return 0 if quality == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
