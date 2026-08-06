#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

STATUS = "TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_1_DONE"
SCHEMA_VERSION = "trace_net_visual_question_context_v1_1"

CANONICAL_PAGE_ID_RE = re.compile(r"^t_p_[A-Za-z0-9]+_[A-Za-z0-9]+_p\d{6}$")

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
FIGURE_KEYS = ("figure_number", "figure_numbers", "figure_id")
CALLOUT_KEYS = ("callout", "callout_number", "callout_numbers", "item_number")
NOMENCLATURE_KEYS = ("nomenclature", "nomenclature_text", "part_name", "component_name")
OBJECT_FIELDS = ("primary_object", "object_category", "physical_description", "functional_description")
RECON_FIELDS = ("ocr_agreement", "agreement_status", "ocr_text", "vision_text", "character_conflict", "character_conflicts")
PROOF_FIELDS = ("proof_status", "citation_ready", "source_trace_ready", "candidate_only", "final_answer_allowed")


def iter_json_records(path: Path) -> Iterable[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value
            return
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return

    if isinstance(value, dict):
        yield value
        for key in ("records", "cards", "items", "pages", "results", "summaries"):
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        yield item
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk_dicts(nested)


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


def first_canonical_page_id(record: dict[str, Any]) -> str | None:
    for node in walk_dicts(record):
        for key in PAGE_ID_KEYS:
            for value in scalar_values(node.get(key)):
                if CANONICAL_PAGE_ID_RE.fullmatch(value):
                    return value
    return None


def route_is_image_visual(record: dict[str, Any]) -> bool:
    for node in walk_dicts(record):
        for key in ROUTE_KEYS:
            for value in scalar_values(node.get(key)):
                if value.strip().lower() == "image_visual":
                    return True
    return False


def collect_values(record: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for node in walk_dicts(record):
        for key in keys:
            for value in scalar_values(node.get(key)):
                if value not in seen:
                    seen.add(value)
                    values.append(value)
    return values


def collect_object_description(record: dict[str, Any]) -> dict[str, str | None]:
    out = {field: None for field in OBJECT_FIELDS}
    for node in walk_dicts(record):
        for field in OBJECT_FIELDS:
            if out[field] is None and isinstance(node.get(field), str) and node[field].strip():
                out[field] = node[field].strip()
    return out


def collect_reconciliation(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "agreement_status": None,
        "ocr_text": [],
        "vision_text": [],
        "character_conflicts": [],
    }
    for node in walk_dicts(record):
        if out["agreement_status"] is None:
            for key in ("ocr_agreement", "agreement_status"):
                if isinstance(node.get(key), str) and node[key].strip():
                    out["agreement_status"] = node[key].strip()
                    break
        out["ocr_text"].extend(v for v in scalar_values(node.get("ocr_text")) if v not in out["ocr_text"])
        out["vision_text"].extend(v for v in scalar_values(node.get("vision_text")) if v not in out["vision_text"])
        for key in ("character_conflict", "character_conflicts"):
            value = node.get(key)
            if value not in (None, [], {}, "") and value not in out["character_conflicts"]:
                out["character_conflicts"].append(value)
    return out


def discover_image_pages(artifact_root: Path, route_manifest: Path | None) -> tuple[set[str], dict[str, int]]:
    candidates: list[Path] = []
    if route_manifest:
        candidates.append(route_manifest)
    else:
        candidates.extend([
            artifact_root / "page_route_manifest" / "trace_net_page_route_manifest_v1_cards.jsonl",
            artifact_root / "page_route_manifest" / "trace_net_page_route_manifest_v1_manifest.json",
            artifact_root / "route_dispatch_manifest" / "trace_net_route_dispatch_manifest_v1.json",
            artifact_root / "calibrated_cascade_route_brain_v35_3" / "trace_net_cascade_route_decisions_v35_3.jsonl",
        ])

    pages: set[str] = set()
    counts = {"route_files_read": 0, "route_records_read": 0, "rejected_noncanonical_route_record_count": 0}
    for path in candidates:
        if not path.exists():
            continue
        counts["route_files_read"] += 1
        for record in iter_json_records(path):
            counts["route_records_read"] += 1
            if not route_is_image_visual(record):
                continue
            page_id = first_canonical_page_id(record)
            if page_id:
                pages.add(page_id)
            else:
                counts["rejected_noncanonical_route_record_count"] += 1
    return pages, counts


def approved_files(artifact_root: Path, allowed_dirs: tuple[str, ...], output_dir: Path) -> Iterable[Path]:
    output_resolved = output_dir.resolve()
    for rel in allowed_dirs:
        base = artifact_root / rel
        if not base.exists() or not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
                continue
            try:
                resolved = path.resolve()
                if output_resolved == resolved or output_resolved in resolved.parents:
                    continue
            except OSError:
                pass
            rel_text = path.as_posix().lower()
            if any(token.lower() in rel_text for token in SKIP_DIR_TOKENS):
                continue
            yield path


def merge_unique(target: list[str], values: Iterable[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def build_contexts(artifact_root: Path, output_dir: Path, image_pages: set[str], max_pages: int | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    metrics = {
        "scanned_file_count": 0,
        "scanned_record_count": 0,
        "rejected_noncanonical_page_id_count": 0,
        "rejected_non_image_route_page_count": 0,
        "rejected_nonvisual_artifact_count": 0,
    }

    for path in approved_files(artifact_root, DEFAULT_ALLOWED_DIRS, output_dir):
        metrics["scanned_file_count"] += 1
        file_had_accepted = False
        for record in iter_json_records(path):
            metrics["scanned_record_count"] += 1
            page_id = first_canonical_page_id(record)
            if not page_id:
                metrics["rejected_noncanonical_page_id_count"] += 1
                continue
            if page_id not in image_pages:
                metrics["rejected_non_image_route_page_count"] += 1
                continue
            grouped[page_id].append((path, record))
            file_had_accepted = True
        if not file_had_accepted:
            metrics["rejected_nonvisual_artifact_count"] += 1

    contexts: list[dict[str, Any]] = []
    for page_id in sorted(grouped):
        sources = grouped[page_id]
        visual_ids: list[str] = []
        part_numbers: list[str] = []
        ata_numbers: list[str] = []
        figure_numbers: list[str] = []
        callout_numbers: list[str] = []
        nomenclature: list[str] = []
        object_description = {field: None for field in OBJECT_FIELDS}
        reconciliation = {
            "agreement_status": None,
            "ocr_text": [],
            "vision_text": [],
            "character_conflicts": [],
        }
        page_context_v2 = None
        source_refs: list[dict[str, Any]] = []

        proof_status = "candidate_only"
        citation_ready = False
        source_trace_ready = False

        for path, record in sources:
            merge_unique(visual_ids, collect_values(record, VISUAL_ID_KEYS))
            merge_unique(part_numbers, collect_values(record, PART_KEYS))
            merge_unique(ata_numbers, collect_values(record, ATA_KEYS))
            merge_unique(figure_numbers, collect_values(record, FIGURE_KEYS))
            merge_unique(callout_numbers, collect_values(record, CALLOUT_KEYS))
            merge_unique(nomenclature, collect_values(record, NOMENCLATURE_KEYS))

            current_object = collect_object_description(record)
            for field in OBJECT_FIELDS:
                if object_description[field] is None and current_object[field]:
                    object_description[field] = current_object[field]

            current_recon = collect_reconciliation(record)
            if reconciliation["agreement_status"] is None and current_recon["agreement_status"]:
                reconciliation["agreement_status"] = current_recon["agreement_status"]
            merge_unique(reconciliation["ocr_text"], current_recon["ocr_text"])
            merge_unique(reconciliation["vision_text"], current_recon["vision_text"])
            for conflict in current_recon["character_conflicts"]:
                if conflict not in reconciliation["character_conflicts"]:
                    reconciliation["character_conflicts"].append(conflict)

            for node in walk_dicts(record):
                if page_context_v2 is None:
                    value = node.get("page_context_v2")
                    if isinstance(value, (str, dict, list)) and value not in ("", {}, []):
                        page_context_v2 = value
                if isinstance(node.get("proof_status"), str) and node["proof_status"].strip():
                    proof_status = node["proof_status"].strip()
                citation_ready = citation_ready or node.get("citation_ready") is True
                source_trace_ready = source_trace_ready or node.get("source_trace_ready") is True

            source_refs.append({
                "artifact_path": path.as_posix(),
                "page_id": page_id,
                "role": path.parent.name,
            })

        # Require an actual visual signal. A page-context-only record is not enough.
        has_visual_signal = bool(
            visual_ids
            or any(object_description.values())
            or part_numbers
            or figure_numbers
            or callout_numbers
            or reconciliation["vision_text"]
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
            "ocr_vision_reconciliation": reconciliation,
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
        if max_pages is not None and len(contexts) >= max_pages:
            break

    return contexts, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--route-manifest")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--min-context-count", type=int, default=1)
    parser.add_argument("--min-pages-with-visual-ids", type=int, default=0)
    parser.add_argument("--min-pages-with-page-context-v2", type=int, default=0)
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    route_manifest = Path(args.route_manifest) if args.route_manifest else None
    image_pages, route_metrics = discover_image_pages(artifact_root, route_manifest)
    contexts, metrics = build_contexts(artifact_root, output_dir, image_pages, args.max_pages)

    pages_with_visual_ids = sum(bool(r["visual_ids"]) for r in contexts)
    pages_with_object_description = sum(any(r["object_description"].values()) for r in contexts)
    pages_with_part_numbers = sum(bool(r["identifiers"]["part_numbers"]) for r in contexts)
    pages_with_page_context_v2 = sum(r["page_context_v2"] is not None for r in contexts)
    pages_with_reconciliation = sum(
        bool(
            r["ocr_vision_reconciliation"]["agreement_status"]
            or r["ocr_vision_reconciliation"]["ocr_text"]
            or r["ocr_vision_reconciliation"]["vision_text"]
            or r["ocr_vision_reconciliation"]["character_conflicts"]
        )
        for r in contexts
    )

    fail_reasons = []
    if not image_pages:
        fail_reasons.append("no_authoritative_image_visual_pages_discovered")
    if len(contexts) < args.min_context_count:
        fail_reasons.append("context_count_below_minimum")
    if pages_with_visual_ids < args.min_pages_with_visual_ids:
        fail_reasons.append("pages_with_visual_ids_below_minimum")
    if pages_with_page_context_v2 < args.min_pages_with_page_context_v2:
        fail_reasons.append("pages_with_page_context_v2_below_minimum")

    quality_status = "PASS" if not fail_reasons else "FAIL"

    records_path = output_dir / "trace_net_visual_question_context_v1_1.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "trace_net_visual_question_context_v1_1_report.txt"

    records_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in contexts),
        encoding="utf-8",
    )

    summary = {
        "status": STATUS,
        "quality_status": quality_status,
        "schema_version": SCHEMA_VERSION,
        "authoritative_image_route_page_count": len(image_pages),
        "context_count": len(contexts),
        "pages_with_visual_ids": pages_with_visual_ids,
        "pages_with_object_description": pages_with_object_description,
        "pages_with_part_numbers": pages_with_part_numbers,
        "pages_with_page_context_v2": pages_with_page_context_v2,
        "pages_with_ocr_vision_reconciliation": pages_with_reconciliation,
        **route_metrics,
        **metrics,
        "final_answer_allowed_true_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "failure_reasons": fail_reasons,
        "outputs": {
            "records": str(records_path),
            "summary": str(summary_path),
            "report": str(report_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_lines = [
        f"status={STATUS}",
        f"quality_status={quality_status}",
        f"authoritative_image_route_page_count={len(image_pages)}",
        f"context_count={len(contexts)}",
        f"pages_with_visual_ids={pages_with_visual_ids}",
        f"pages_with_object_description={pages_with_object_description}",
        f"pages_with_part_numbers={pages_with_part_numbers}",
        f"pages_with_page_context_v2={pages_with_page_context_v2}",
        f"pages_with_ocr_vision_reconciliation={pages_with_reconciliation}",
        f"rejected_noncanonical_page_id_count={metrics['rejected_noncanonical_page_id_count']}",
        f"rejected_non_image_route_page_count={metrics['rejected_non_image_route_page_count']}",
        f"final_answer_allowed_true_count=0",
        f"source_truth_mutation_allowed_count=0",
    ]
    if fail_reasons:
        report_lines.append("failure_reasons=" + json.dumps(fail_reasons))
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    for line in report_lines[:12]:
        print(line)
    print(f"records={records_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
