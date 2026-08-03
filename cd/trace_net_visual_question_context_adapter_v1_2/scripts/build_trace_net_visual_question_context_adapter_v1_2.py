#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

STATUS = "TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_2_DONE"
SCHEMA_VERSION = "trace_net_visual_question_context_v1_2"

CANONICAL_PAGE_ID_RE = re.compile(r"^t_p_[A-Za-z0-9]+_[A-Za-z0-9]+_p\d{6}$")
VISUAL_PAGE_ID_RE = re.compile(r"(t_p_[A-Za-z0-9]+_[A-Za-z0-9]+_p\d{6})")

DEFAULT_ALLOWED_DIRS = (
    "page_route_manifest",
    "route_dispatch_manifest",
    "calibrated_cascade_route_brain_v35_3",
    "fishnet_route_dispatch_handoff/image_visual",
    "image_visual_summary",
    "image_visual_summary_llava_12",
    "image_visual_summary_llava_12_semantic",
    "image_visual_summary_llava_12_semantic_ocr_join",
    "llava_visual_summary_batch_v1",
    "llama32_vision_image_route_summary_v1",
    "llama32_vision_image_route_summary_v2",
    "image_ocr_figure_callout_extractor_v1",
    "image_visual_evidence_pack_v1",
    "image_visual_evidence_nomenclature_merger_v1",
    "callout_visual_part_verifier",
    "figure_chart_understanding",
    "visual_callout_table_linker_v1",
    "visual_callout_table_linker_v2",
    "visual_part_nomenclature_enricher_v1",
    "corrected_visual_context_builder_v35_4",
    "route_scoped_visual_context_builder_v35",
    "page_context_v2",
)

SKIP_DIR_TOKENS = (
    "visual_question_context_adapter_v1_smoke",
    "visual_question_context_adapter_v1_1",
    "visual_question_context_adapter_v1_2",
    "nonredundancy_audit",
    "synthetic_trace_net_root",
    "test_matrix",
    "engineering_answer_",
    "fast_chat_",
    "webui_",
)

PAGE_ID_KEYS = ("page_id", "source_page_id", "canonical_page_id")
ROUTE_KEYS = ("primary_route", "route", "route_name", "selected_route", "dispatch_route")
VISUAL_ID_KEYS = ("visual_id", "visual_region_id", "region_id", "figure_id")
PART_KEYS = ("part_number", "part_numbers", "candidate_part_number", "candidate_part_numbers", "covered_part_number")
ATA_KEYS = ("ata_number", "ata_numbers", "ata_code")
FIGURE_KEYS = ("figure_number", "figure_numbers")
CALLOUT_KEYS = ("callout", "callout_number", "callout_numbers", "item_number")
NOMENCLATURE_KEYS = ("nomenclature", "nomenclature_text", "part_name", "component_name")
OBJECT_FIELDS = ("primary_object", "object_category", "physical_description", "functional_description")

CONTAINER_KEYS = (
    "records", "cards", "items", "pages", "results", "summaries",
    "visual_regions", "regions", "nodes", "graph_nodes", "candidates"
)


def scalar_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(scalar_values(item))
        return out
    return []


def direct_page_id(record: dict[str, Any]) -> str | None:
    for key in PAGE_ID_KEYS:
        for value in scalar_values(record.get(key)):
            if CANONICAL_PAGE_ID_RE.fullmatch(value):
                return value
    return None


def has_direct_payload(record: dict[str, Any]) -> bool:
    interesting = set(
        PAGE_ID_KEYS + ROUTE_KEYS + VISUAL_ID_KEYS + PART_KEYS + ATA_KEYS +
        FIGURE_KEYS + CALLOUT_KEYS + NOMENCLATURE_KEYS + OBJECT_FIELDS +
        ("ocr_text", "vision_text", "ocr_agreement", "agreement_status",
         "page_context_v2", "citation_ready", "source_trace_ready", "proof_status")
    )
    return any(key in record for key in interesting)


def iter_scoped_records(value: Any) -> Iterable[dict[str, Any]]:
    """Yield page/visual leaf records, never aggregate containers as page records."""
    if isinstance(value, list):
        for item in value:
            yield from iter_scoped_records(item)
        return
    if not isinstance(value, dict):
        return

    # Yield the current dict only if it directly carries record fields.
    if has_direct_payload(value):
        yield value

    # Recurse into known collections and any nested dict/list that may hold records.
    for key, nested in value.items():
        if key in CONTAINER_KEYS or isinstance(nested, (dict, list)):
            yield from iter_scoped_records(nested)


def iter_json_records(path: Path) -> Iterable[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                yield from iter_scoped_records(value)
            return
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        yield from iter_scoped_records(value)
    except (OSError, json.JSONDecodeError):
        return


def route_is_image_visual(record: dict[str, Any]) -> bool:
    for key in ROUTE_KEYS:
        for value in scalar_values(record.get(key)):
            if value.lower() == "image_visual":
                return True
    return False


def collect_values(record: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for key in keys:
        for value in scalar_values(record.get(key)):
            if value not in out:
                out.append(value)
    return out


def collect_visual_ids_for_page(record: dict[str, Any], page_id: str) -> tuple[list[str], int]:
    accepted: list[str] = []
    rejected = 0
    for value in collect_values(record, VISUAL_ID_KEYS):
        match = VISUAL_PAGE_ID_RE.search(value)
        if match and match.group(1) != page_id:
            rejected += 1
            continue
        if value not in accepted:
            accepted.append(value)
    return accepted, rejected


def collect_object(record: dict[str, Any]) -> dict[str, str | None]:
    return {
        field: record[field].strip()
        if isinstance(record.get(field), str) and record[field].strip()
        else None
        for field in OBJECT_FIELDS
    }


def collect_reconciliation(record: dict[str, Any]) -> dict[str, Any]:
    status = None
    for key in ("ocr_agreement", "agreement_status"):
        if isinstance(record.get(key), str) and record[key].strip():
            status = record[key].strip()
            break
    conflicts = []
    for key in ("character_conflict", "character_conflicts"):
        value = record.get(key)
        if value not in (None, "", [], {}):
            conflicts.append(value)
    return {
        "agreement_status": status,
        "ocr_text": scalar_values(record.get("ocr_text")),
        "vision_text": scalar_values(record.get("vision_text")),
        "character_conflicts": conflicts,
    }


def approved_files(artifact_root: Path, output_dir: Path) -> Iterable[Path]:
    out = output_dir.resolve()
    for rel in DEFAULT_ALLOWED_DIRS:
        base = artifact_root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
                continue
            try:
                resolved = path.resolve()
                if resolved == out or out in resolved.parents:
                    continue
            except OSError:
                pass
            low = path.as_posix().lower()
            if any(token.lower() in low for token in SKIP_DIR_TOKENS):
                continue
            yield path


def discover_image_pages(route_manifest: Path) -> tuple[set[str], dict[str, int]]:
    pages: set[str] = set()
    metrics = {"route_records_read": 0, "rejected_noncanonical_route_record_count": 0}
    for record in iter_json_records(route_manifest):
        metrics["route_records_read"] += 1
        if not route_is_image_visual(record):
            continue
        page_id = direct_page_id(record)
        if page_id:
            pages.add(page_id)
        else:
            metrics["rejected_noncanonical_route_record_count"] += 1
    return pages, metrics


def merge_unique(target: list[Any], values: Iterable[Any]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def build_contexts(artifact_root: Path, output_dir: Path, image_pages: set[str], max_pages: int | None):
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    metrics = {
        "scanned_file_count": 0,
        "scanned_record_count": 0,
        "rejected_noncanonical_page_id_count": 0,
        "rejected_non_image_route_page_count": 0,
        "rejected_cross_page_visual_id_count": 0,
        "aggregate_container_record_count": 0,
    }

    for path in approved_files(artifact_root, output_dir):
        metrics["scanned_file_count"] += 1
        for record in iter_json_records(path):
            metrics["scanned_record_count"] += 1
            page_id = direct_page_id(record)
            if not page_id:
                metrics["rejected_noncanonical_page_id_count"] += 1
                continue
            if page_id not in image_pages:
                metrics["rejected_non_image_route_page_count"] += 1
                continue
            grouped[page_id].append((path, record))

    contexts = []
    for page_id in sorted(grouped):
        visual_ids: list[str] = []
        part_numbers: list[str] = []
        ata_numbers: list[str] = []
        figure_numbers: list[str] = []
        callout_numbers: list[str] = []
        nomenclature: list[str] = []
        object_description = {field: None for field in OBJECT_FIELDS}
        recon = {"agreement_status": None, "ocr_text": [], "vision_text": [], "character_conflicts": []}
        page_context_v2 = None
        source_refs = []
        citation_ready = False
        source_trace_ready = False
        proof_status = "candidate_only"

        for path, record in grouped[page_id]:
            ids, rejected = collect_visual_ids_for_page(record, page_id)
            metrics["rejected_cross_page_visual_id_count"] += rejected
            merge_unique(visual_ids, ids)
            merge_unique(part_numbers, collect_values(record, PART_KEYS))
            merge_unique(ata_numbers, collect_values(record, ATA_KEYS))
            merge_unique(figure_numbers, collect_values(record, FIGURE_KEYS))
            merge_unique(callout_numbers, collect_values(record, CALLOUT_KEYS))
            merge_unique(nomenclature, collect_values(record, NOMENCLATURE_KEYS))

            obj = collect_object(record)
            for field, value in obj.items():
                if object_description[field] is None and value:
                    object_description[field] = value

            rr = collect_reconciliation(record)
            if recon["agreement_status"] is None and rr["agreement_status"]:
                recon["agreement_status"] = rr["agreement_status"]
            merge_unique(recon["ocr_text"], rr["ocr_text"])
            merge_unique(recon["vision_text"], rr["vision_text"])
            merge_unique(recon["character_conflicts"], rr["character_conflicts"])

            if page_context_v2 is None and record.get("page_context_v2") not in (None, "", [], {}):
                page_context_v2 = record.get("page_context_v2")
            if isinstance(record.get("proof_status"), str) and record["proof_status"].strip():
                proof_status = record["proof_status"].strip()
            citation_ready = citation_ready or record.get("citation_ready") is True
            source_trace_ready = source_trace_ready or record.get("source_trace_ready") is True

            source_refs.append({
                "artifact_path": path.as_posix(),
                "page_id": page_id,
                "role": path.parent.name,
            })

        has_visual_signal = bool(
            visual_ids or any(object_description.values()) or part_numbers or
            figure_numbers or callout_numbers or recon["vision_text"]
        )
        if not has_visual_signal:
            continue

        contexts.append({
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "route": "image_visual",
            "visual_ids": visual_ids,
            "page_context_v2": page_context_v2,
            "object_description": object_description,
            "identifiers": {
                "part_numbers": part_numbers,
                "ata_numbers": ata_numbers,
                "figure_numbers": figure_numbers,
                "callout_numbers": callout_numbers,
                "nomenclature": nomenclature,
            },
            "ocr_vision_reconciliation": recon,
            "evidence_status": {
                "proof_status": proof_status,
                "citation_ready": citation_ready,
                "source_trace_ready": source_trace_ready,
                "candidate_only": not (citation_ready and source_trace_ready),
                "final_answer_allowed": False,
            },
            "source_artifact_refs": source_refs,
            "safety_contract": {
                "read_only": True,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
                "answer_permission_count": 0,
            },
        })
        if max_pages and len(contexts) >= max_pages:
            break
    return contexts, metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--route-manifest", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-pages", type=int)
    ap.add_argument("--min-context-count", type=int, default=1)
    ap.add_argument("--min-pages-with-visual-ids", type=int, default=0)
    args = ap.parse_args()

    artifact_root = Path(args.artifact_root)
    route_manifest = Path(args.route_manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pages, route_metrics = discover_image_pages(route_manifest)
    contexts, metrics = build_contexts(artifact_root, output_dir, pages, args.max_pages)

    pages_with_visual_ids = sum(bool(r["visual_ids"]) for r in contexts)
    pages_with_objects = sum(any(r["object_description"].values()) for r in contexts)
    pages_with_parts = sum(bool(r["identifiers"]["part_numbers"]) for r in contexts)
    pages_with_pc = sum(r["page_context_v2"] is not None for r in contexts)
    pages_with_recon = sum(bool(r["ocr_vision_reconciliation"]["ocr_text"] or r["ocr_vision_reconciliation"]["vision_text"] or r["ocr_vision_reconciliation"]["agreement_status"]) for r in contexts)

    failures = []
    if not pages:
        failures.append("no_authoritative_image_pages")
    if len(contexts) < args.min_context_count:
        failures.append("context_count_below_minimum")
    if pages_with_visual_ids < args.min_pages_with_visual_ids:
        failures.append("pages_with_visual_ids_below_minimum")
    quality = "PASS" if not failures else "FAIL"

    records_path = output_dir / "trace_net_visual_question_context_v1_2.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "trace_net_visual_question_context_v1_2_report.txt"

    records_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in contexts), encoding="utf-8")
    summary = {
        "status": STATUS,
        "quality_status": quality,
        "schema_version": SCHEMA_VERSION,
        "authoritative_image_route_page_count": len(pages),
        "context_count": len(contexts),
        "pages_with_visual_ids": pages_with_visual_ids,
        "pages_with_object_description": pages_with_objects,
        "pages_with_part_numbers": pages_with_parts,
        "pages_with_page_context_v2": pages_with_pc,
        "pages_with_ocr_vision_reconciliation": pages_with_recon,
        **route_metrics,
        **metrics,
        "final_answer_allowed_true_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "failure_reasons": failures,
        "outputs": {"records": str(records_path), "summary": str(summary_path), "report": str(report_path)},
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        f"status={STATUS}",
        f"quality_status={quality}",
        f"authoritative_image_route_page_count={len(pages)}",
        f"context_count={len(contexts)}",
        f"pages_with_visual_ids={pages_with_visual_ids}",
        f"pages_with_object_description={pages_with_objects}",
        f"pages_with_part_numbers={pages_with_parts}",
        f"pages_with_page_context_v2={pages_with_pc}",
        f"pages_with_ocr_vision_reconciliation={pages_with_recon}",
        f"rejected_cross_page_visual_id_count={metrics['rejected_cross_page_visual_id_count']}",
        "final_answer_allowed_true_count=0",
        "source_truth_mutation_allowed_count=0",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        print(line)
    print(f"records={records_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")
    return 0 if quality == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
