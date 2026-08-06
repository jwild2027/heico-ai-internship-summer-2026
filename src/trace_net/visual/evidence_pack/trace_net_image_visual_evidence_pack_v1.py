"""TRACE-Net image visual evidence pack v1.

Patch C module for the image/visual route. It packages LLaVA/OCR visual
observations and trusted linker records into citation-labelled visual evidence
records that can be consumed by a deterministic image/diagram fast composer.

Authority model:
- LLaVA and OCR label extraction can observe visual labels/layout.
- Trusted OCR/table/figure-item evidence proves part identity.
- Graph/Leiden/visual summaries are not proof in this module.
- No database/vector/search writes, no source-truth mutation, no answer permission.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_image_visual_evidence_pack_v1"
STATUS_BUILT = "TRACE_NET_IMAGE_VISUAL_EVIDENCE_PACK_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/image_visual_evidence_pack_v1"

PAGE_ID_KEYS = ("page_id", "trace_page_id", "source_page_id", "page_key", "id")
PAGE_NUMBER_KEYS = ("page_number", "page_num", "page", "source_page_number", "physical_page_number")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def compact_text(value: Any, max_chars: int = 1000) -> str:
    text = re.sub(r"\s+", " ", normalize_string(value)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def safe_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = normalize_string(value)
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def lower_key_map(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in record.items()}


def first_from_keys(lower: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in lower and lower[key] not in (None, ""):
            return lower[key]
    return None


def extract_page_id(record: Mapping[str, Any]) -> str:
    return normalize_string(first_from_keys(lower_key_map(record), PAGE_ID_KEYS))


def extract_page_number(record: Mapping[str, Any]) -> Optional[int]:
    lower = lower_key_map(record)
    page = safe_int(first_from_keys(lower, PAGE_NUMBER_KEYS))
    if page is not None:
        return page
    page_id = extract_page_id(record)
    match = re.search(r"p0*([0-9]{1,6})\b", page_id)
    return int(match.group(1)) if match else None


def iter_records(payload: Any) -> List[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("records", "visual_callout_link_records", "links", "evidence_records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, Mapping)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, Mapping)]
    return []


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}
    return bool(value)


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "||".join(normalize_string(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def linked_description_quality(description: str) -> str:
    text = normalize_string(description)
    if not text:
        return "missing"
    lower = text.lower()
    if lower.endswith((".tif", ".tiff", ".png", ".jpg", ".jpeg", ".json")) or "/" in lower or "\\" in lower:
        return "bad_filename_or_path"
    if re.fullmatch(r"\d{3}-\d{5}-\d{3}", text):
        return "bad_part_number_repeated"
    return "available"


def confidence_to_proof_strength(confidence: str, linked: bool, callout: str, description_quality: str) -> str:
    conf = normalize_string(confidence).upper()
    if not linked:
        return "visual_or_ocr_observation_only_not_proof"
    if conf == "HIGH":
        return "linked_visual_plus_exact_figure_item_table_proof"
    if conf == "MEDIUM" and callout:
        return "linked_visual_plus_partial_item_table_proof"
    if conf == "MEDIUM":
        return "linked_visual_plus_figure_page_table_proof"
    return "linked_but_low_confidence_review_required"


def build_visual_evidence_record(source: Mapping[str, Any], index: int) -> Dict[str, Any]:
    page_id = extract_page_id(source)
    page_number = extract_page_number(source)
    figure = normalize_string(source.get("figure"))
    callout = normalize_string(source.get("callout"))
    linked = boolish(source.get("linked"))
    confidence = normalize_string(source.get("link_confidence") or source.get("confidence") or "LOW").upper() or "LOW"
    part_number = normalize_string(source.get("linked_part_number") or source.get("part_number"))
    description = normalize_string(source.get("linked_description") or source.get("description"))
    desc_quality = normalize_string(source.get("linked_description_quality")) or linked_description_quality(description)
    source_trace_ready = boolish(source.get("source_trace_ready")) and linked
    citation_ready = boolish(source.get("citation_ready")) and linked
    proof_source = normalize_string(source.get("proof_source")) or ("trusted_ocr_table_figure_item_evidence" if linked else "none_visual_or_ocr_only")
    proof_strength = confidence_to_proof_strength(confidence, linked, callout, desc_quality)
    evidence_kind = "linked_visual_evidence" if linked else "unlinked_visual_candidate"
    visual_role = "linked_figure" if linked and not callout else ("linked_callout" if linked else "unlinked_visual_or_ocr_label")
    citation_label = f"V{index}"
    limitations: List[str] = []
    if not linked:
        limitations.append("No trusted OCR/table/figure-item proof matched this visual/OCR label; it is review-only.")
    if linked and confidence == "MEDIUM" and not callout:
        limitations.append("Figure/page proof is linked, but no exact callout/item label is present in the visual link.")
    if linked and desc_quality != "available":
        limitations.append("The visual link identifies the part number, but a clean nomenclature/description is not available in this record.")
    limitations.append("This evidence does not prove interchangeability, effectivity, fit, replacement approval, or installation safety.")

    return {
        "schema_version": "trace_net_image_visual_evidence_record_v1",
        "evidence_id": stable_id("image_visual_evidence", page_id, page_number, figure, callout, part_number, confidence, index),
        "citation_label": citation_label,
        "evidence_kind": evidence_kind,
        "visual_role": visual_role,
        "page_id": page_id,
        "page_number": page_number,
        "figure": figure,
        "callout": callout,
        "linked_part_number": part_number if linked else "",
        "linked_description": description if desc_quality == "available" else "",
        "linked_description_quality": desc_quality,
        "link_confidence": confidence,
        "link_reason": normalize_string(source.get("link_reason")),
        "linked": linked,
        "proof_source": proof_source,
        "visual_source": normalize_string(source.get("visual_source")) or "llava_plus_ocr_extractor",
        "candidate_source": normalize_string(source.get("candidate_source")),
        "proof_strength": proof_strength,
        "source_trace_ready": source_trace_ready,
        "citation_ready": citation_ready,
        "can_support_limited_visual_answer": bool(linked and source_trace_ready and citation_ready),
        "retrieval_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
        "requires_human_review": not bool(linked and source_trace_ready and citation_ready),
        "limitations": limitations,
        "source_link_record_id": normalize_string(source.get("link_record_id") or source.get("record_id") or source.get("evidence_id")),
        "source_trace": source.get("source_trace") if isinstance(source.get("source_trace"), Mapping) else {
            "page_id": page_id,
            "page_number": page_number,
            "figure": figure,
            "callout": callout,
            "source_module": "trace_net_visual_callout_table_linker_v2",
            "source_link_record_id": normalize_string(source.get("link_record_id") or source.get("record_id") or source.get("evidence_id")),
        },
    }


def summarize(records: Sequence[Mapping[str, Any]]) -> Dict[str, int | bool]:
    def count(pred) -> int:
        return sum(1 for r in records if pred(r))
    high = count(lambda r: normalize_string(r.get("link_confidence")).upper() == "HIGH")
    med = count(lambda r: normalize_string(r.get("link_confidence")).upper() == "MEDIUM")
    low = count(lambda r: normalize_string(r.get("link_confidence")).upper() == "LOW")
    linked = count(lambda r: boolish(r.get("linked")))
    source_ready = count(lambda r: boolish(r.get("source_trace_ready")))
    citation_ready = count(lambda r: boolish(r.get("citation_ready")))
    answer_eligible = count(lambda r: boolish(r.get("can_support_limited_visual_answer")))
    unsafe = count(lambda r: boolish(r.get("unsafe_record")) or boolish(r.get("unsafe")))
    return {
        "visual_evidence_record_count": len(records),
        "linked_visual_evidence_count": linked,
        "unlinked_visual_candidate_count": len(records) - linked,
        "high_confidence_visual_evidence_count": high,
        "medium_confidence_visual_evidence_count": med,
        "low_confidence_visual_candidate_count": low,
        "citation_ready_count": citation_ready,
        "source_trace_ready_count": source_ready,
        "limited_visual_answer_eligible_count": answer_eligible,
        "description_available_count": count(lambda r: normalize_string(r.get("linked_description_quality")) == "available"),
        "requires_human_review_count": count(lambda r: boolish(r.get("requires_human_review"))),
        "unsafe_record_count": unsafe,
        "answer_permission_count": count(lambda r: boolish(r.get("answer_permission"))),
        "source_truth_mutation_allowed_count": count(lambda r: boolish(r.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": count(lambda r: boolish(r.get("postgres_write_attempt"))),
        "qdrant_write_attempt_count": count(lambda r: boolish(r.get("qdrant_write_attempt"))),
        "opensearch_write_attempt_count": count(lambda r: boolish(r.get("opensearch_write_attempt"))),
        "opensearch_upload_attempt_count": count(lambda r: boolish(r.get("opensearch_upload_attempt"))),
        "write_attempt_count": count(lambda r: boolish(r.get("postgres_write_attempt")) or boolish(r.get("qdrant_write_attempt")) or boolish(r.get("opensearch_write_attempt")) or boolish(r.get("opensearch_upload_attempt"))),
        "ready_for_image_diagram_composer": bool(answer_eligible > 0 and unsafe == 0),
    }


def evaluate_quality(summary: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if int(summary.get("visual_evidence_record_count", 0)) < args.min_visual_evidence_records:
        failures.append("visual_evidence_record_count below threshold")
    if int(summary.get("linked_visual_evidence_count", 0)) < args.min_linked_visual_evidence:
        failures.append("linked_visual_evidence_count below threshold")
    if int(summary.get("source_trace_ready_count", 0)) < args.min_source_trace_ready:
        failures.append("source_trace_ready_count below threshold")
    if int(summary.get("citation_ready_count", 0)) < args.min_citation_ready:
        failures.append("citation_ready_count below threshold")
    if int(summary.get("unsafe_record_count", 0)) > args.max_unsafe:
        failures.append("unsafe_record_count above threshold")
    if int(summary.get("answer_permission_count", 0)) > args.max_answer_permission:
        failures.append("answer_permission_count above threshold")
    if int(summary.get("source_truth_mutation_allowed_count", 0)) > args.max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above threshold")
    if int(summary.get("write_attempt_count", 0)) > args.max_write_attempts:
        failures.append("write_attempt_count above threshold")
    return ("PASS" if not failures else "FAIL"), failures


def write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "citation_label", "evidence_kind", "page_number", "page_id", "figure", "callout",
        "linked_part_number", "linked_description", "link_confidence", "proof_strength",
        "source_trace_ready", "citation_ready", "can_support_limited_visual_answer",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    linker_payload = read_json(Path(args.visual_callout_linker_v2))
    source_records = iter_records(linker_payload)
    records = [build_visual_evidence_record(r, i + 1) for i, r in enumerate(source_records)]
    summary = summarize(records)
    quality_status, failures = evaluate_quality(summary, args)
    return {
        "schema_version": "trace_net_image_visual_evidence_pack_v1",
        "module": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "created_at": utc_now(),
        "paths": {
            "visual_callout_linker_v2": args.visual_callout_linker_v2,
            "llava_visual_summary_batch": args.llava_visual_summary_batch or "",
            "ocr_figure_callout_extractor": args.ocr_figure_callout_extractor or "",
        },
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
        "authority_model": {
            "llava": "visual_observation_only",
            "ocr_figure_callout_extractor": "visible_label_support",
            "trusted_ocr_table_figure_item_evidence": "proof_for_part_identity_when_linked",
            "graph_leiden": "not_used_as_proof_in_this_pack",
        },
        "summary": summary,
        "checks": {"failures": failures},
        "records": records,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-callout-linker-v2", required=True)
    parser.add_argument("--llava-visual-summary-batch", default="")
    parser.add_argument("--ocr-figure-callout-extractor", default="")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-visual-evidence-records", type=int, default=1)
    parser.add_argument("--min-linked-visual-evidence", type=int, default=1)
    parser.add_argument("--min-source-trace-ready", type=int, default=1)
    parser.add_argument("--min-citation-ready", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    payload = build_payload(args)
    main_path = output_dir / "trace_net_image_visual_evidence_pack_v1.json"
    quality_path = output_dir / "trace_net_image_visual_evidence_pack_v1_quality_check.json"
    jsonl_path = output_dir / "trace_net_image_visual_evidence_pack_v1_records.jsonl"
    csv_path = output_dir / "trace_net_image_visual_evidence_pack_v1_records.csv"
    write_json(main_path, payload)
    write_json(quality_path, {k: payload[k] for k in ("schema_version", "module", "status", "quality_status", "created_at", "summary", "checks")})
    write_jsonl(jsonl_path, payload["records"])
    write_csv(csv_path, payload["records"])
    s = payload["summary"]
    print(f"status={payload['status']}")
    print(f"quality_status={payload['quality_status']}")
    for key in ("visual_evidence_record_count", "linked_visual_evidence_count", "unlinked_visual_candidate_count", "high_confidence_visual_evidence_count", "medium_confidence_visual_evidence_count", "source_trace_ready_count", "citation_ready_count", "limited_visual_answer_eligible_count", "ready_for_image_diagram_composer", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"):
        print(f"{key}={s.get(key)}")
    print(f"pack={main_path}")
    return 0 if payload["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
