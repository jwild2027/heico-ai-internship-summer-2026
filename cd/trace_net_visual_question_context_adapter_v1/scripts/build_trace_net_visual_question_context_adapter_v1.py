#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATUS = "TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_DONE"
SCHEMA = "trace_net_visual_question_context_v1"

PAGE_KEYS = ("page_id", "source_page_id", "page_key", "page")
VISUAL_KEYS = ("visual_id", "visual_region_id", "region_id", "image_id", "figure_id")

FIELD_ALIASES = {
    "primary_object": ("primary_object", "object_name", "main_object", "visual_subject"),
    "object_category": ("object_category", "visual_type", "image_type", "figure_type"),
    "physical_description": ("physical_description", "visual_description", "description", "summary"),
    "functional_description": ("functional_description", "function", "purpose"),
    "part_numbers": ("part_numbers", "part_number", "candidate_part_numbers", "visible_part_numbers"),
    "ata_numbers": ("ata_numbers", "ata_number", "ata", "ata_code"),
    "figure_numbers": ("figure_numbers", "figure_number", "figure", "figures"),
    "callout_numbers": ("callout_numbers", "callouts", "item_numbers", "item_number"),
    "nomenclature": ("nomenclature", "nomenclatures", "part_name", "component_name"),
    "ocr_text": ("ocr_text", "ocr_tokens", "recognized_text"),
    "vision_text": ("vision_text", "llava_text", "visual_text", "model_text"),
    "ocr_agreement": ("ocr_agreement", "agreement_status", "ocr_vision_agreement"),
    "character_conflicts": ("character_conflicts", "character_conflict", "ocr_conflicts"),
    "proof_status": ("proof_status", "evidence_status"),
    "citation_ready": ("citation_ready",),
    "source_trace_ready": ("source_trace_ready",),
    "candidate_only": ("candidate_only", "candidate_discovery_only"),
    "page_context_v2": ("page_context_v2", "context_v2", "page_summary_v2"),
}

@dataclass(frozen=True)
class SourceRecord:
    path: str
    record_index: int
    payload: dict[str, Any]


def _iter_json_records(path: Path) -> Iterable[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        yield obj
            return
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if isinstance(obj, dict):
        yield obj
        for key in ("records", "items", "pages", "visuals", "results", "documents"):
            value = obj.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item


def _walk_dict(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_dict(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dict(child)


def _first_scalar(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key, value in _walk_dict(record):
        if key in keys and isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return None


def _flatten_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            out.extend(_flatten_values(item))
        return out
    if isinstance(value, dict):
        for candidate_key in ("text", "value", "normalized", "part_number", "number", "name"):
            if candidate_key in value:
                return _flatten_values(value[candidate_key])
        return []
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    return []


def _collect_alias_values(records: list[SourceRecord], aliases: tuple[str, ...]) -> tuple[list[Any], list[dict[str, Any]]]:
    values: list[Any] = []
    provenance: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in records:
        for key, value in _walk_dict(source.payload):
            if key not in aliases:
                continue
            extracted = _flatten_values(value)
            for item in extracted:
                marker = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if marker in seen:
                    continue
                seen.add(marker)
                values.append(item)
                provenance.append({"source_path": source.path, "record_index": source.record_index, "source_field": key})
    return values, provenance


def _single(values: list[Any]) -> Any:
    return values[0] if values else None


def _bool_value(values: list[Any], default: bool) -> bool:
    if not values:
        return default
    value = str(values[0]).lower()
    return value in {"true", "1", "yes"}


def discover_records(artifact_root: Path) -> tuple[dict[str, list[SourceRecord]], int, int]:
    grouped: dict[str, list[SourceRecord]] = defaultdict(list)
    file_count = 0
    record_count = 0
    for path in sorted(artifact_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        file_count += 1
        for idx, record in enumerate(_iter_json_records(path)):
            record_count += 1
            page_id = _first_scalar(record, PAGE_KEYS)
            if page_id:
                grouped[page_id].append(SourceRecord(str(path), idx, record))
    return grouped, file_count, record_count


def build_context(page_id: str, records: list[SourceRecord]) -> dict[str, Any]:
    collected: dict[str, list[Any]] = {}
    provenance: dict[str, list[dict[str, Any]]] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        values, refs = _collect_alias_values(records, aliases)
        collected[canonical] = values
        provenance[canonical] = refs

    visual_ids = sorted({v for r in records if (v := _first_scalar(r.payload, VISUAL_KEYS))})
    source_paths = sorted({r.path for r in records})

    return {
        "schema_version": SCHEMA,
        "page_id": page_id,
        "visual_ids": visual_ids,
        "page_context_v2": _single(collected["page_context_v2"]),
        "object_description": {
            "primary_object": _single(collected["primary_object"]),
            "object_category": _single(collected["object_category"]),
            "physical_description": _single(collected["physical_description"]),
            "functional_description": _single(collected["functional_description"]),
        },
        "identifiers": {
            "part_numbers": collected["part_numbers"],
            "ata_numbers": collected["ata_numbers"],
            "figure_numbers": collected["figure_numbers"],
            "callout_numbers": collected["callout_numbers"],
            "nomenclature": collected["nomenclature"],
        },
        "ocr_vision_reconciliation": {
            "agreement_status": _single(collected["ocr_agreement"]),
            "ocr_text": collected["ocr_text"],
            "vision_text": collected["vision_text"],
            "character_conflicts": collected["character_conflicts"],
        },
        "evidence_status": {
            "proof_status": _single(collected["proof_status"]) or "candidate_only",
            "citation_ready": _bool_value(collected["citation_ready"], False),
            "source_trace_ready": _bool_value(collected["source_trace_ready"], False),
            "candidate_only": _bool_value(collected["candidate_only"], True),
            "final_answer_allowed": False,
        },
        "source_artifact_refs": source_paths,
        "field_provenance": provenance,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission_count": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only visual question contexts from existing TRACE-Net artifacts.")
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--page-id", action="append", default=[])
    parser.add_argument("--min-context-count", type=int, default=1)
    args = parser.parse_args()

    grouped, scanned_file_count, scanned_record_count = discover_records(args.artifact_root)
    selected_ids = sorted(grouped)
    if args.page_id:
        wanted = set(args.page_id)
        selected_ids = [p for p in selected_ids if p in wanted]
    if args.max_pages > 0:
        selected_ids = selected_ids[: args.max_pages]

    contexts = [build_context(page_id, grouped[page_id]) for page_id in selected_ids]
    quality = "PASS" if len(contexts) >= args.min_context_count else "FAIL"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    records_path = args.output_dir / "trace_net_visual_question_context_v1.jsonl"
    summary_path = args.output_dir / "summary.json"
    report_path = args.output_dir / "trace_net_visual_question_context_v1_report.txt"

    records_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in contexts), encoding="utf-8")
    summary = {
        "status": STATUS,
        "quality_status": quality,
        "schema_version": SCHEMA,
        "scanned_file_count": scanned_file_count,
        "scanned_record_count": scanned_record_count,
        "available_page_count": len(grouped),
        "context_count": len(contexts),
        "pages_with_part_numbers": sum(bool(c["identifiers"]["part_numbers"]) for c in contexts),
        "pages_with_page_context_v2": sum(c["page_context_v2"] is not None for c in contexts),
        "pages_with_ocr_vision_reconciliation": sum(bool(c["ocr_vision_reconciliation"]["agreement_status"] or c["ocr_vision_reconciliation"]["ocr_text"] or c["ocr_vision_reconciliation"]["vision_text"]) for c in contexts),
        "final_answer_allowed_true_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "outputs": {"records": str(records_path), "summary": str(summary_path), "report": str(report_path)},
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text("\n".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in summary.items()) + "\n", encoding="utf-8")

    print(f"quality_status={quality}")
    print(f"context_count={len(contexts)}")
    print(f"records={records_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
