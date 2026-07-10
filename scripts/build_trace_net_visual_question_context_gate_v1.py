#!/usr/bin/env python3
"""TRACE-Net visual question context gate v1.

Filters visual-question-context records using the calibrated meaningful image
route detector v1.2.

Purpose:
- Keep confirmed image_visual / mixed_visual_table pages in the image context set.
- Move visual_candidate_review pages into a separate review-only output.
- Exclude table/text/blank/uncertain pages from automatic image-context routing.

Safety contract:
- Read-only.
- Does not call OCR/LLM/Ollama.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not mutate source-truth artifacts.
- Does not grant answer permission.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


MODULE_NAME = "trace_net_visual_question_context_gate_v1"

DEFAULT_ALLOWED_ROUTES = {"image_visual", "mixed_visual_table"}
DEFAULT_REVIEW_ROUTES = {"visual_candidate_review"}
DEFAULT_EXCLUDED_ROUTES = {
    "table",
    "normal_text",
    "front_matter_or_index",
    "blank_candidate",
    "review_candidate",
}


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            yield obj


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records)
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def load_detector(detector_jsonl: Path) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    for rec in read_jsonl(detector_jsonl) or []:
        page_id = rec.get("page_id")
        if isinstance(page_id, str) and page_id:
            records[page_id] = rec
    return records


def page_id_of(record: Dict[str, Any]) -> str:
    value = record.get("page_id")
    if isinstance(value, str) and value:
        return value

    # Some context outputs may nest page metadata.
    for key in ("route_provenance", "source_page", "page", "metadata"):
        nested = record.get(key)
        if isinstance(nested, dict):
            value = nested.get("page_id")
            if isinstance(value, str) and value:
                return value

    return ""


def bool_from_nested(record: Dict[str, Any], keys: Sequence[str]) -> bool:
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            for nested in ("value", "flag", "allowed", "enabled"):
                nv = value.get(nested)
                if isinstance(nv, bool):
                    return nv
    return False


def add_gate_metadata(
    context_record: Dict[str, Any],
    detector_record: Dict[str, Any],
    gate_status: str,
) -> Dict[str, Any]:
    output = dict(context_record)
    output["meaningful_image_gate"] = {
        "module": MODULE_NAME,
        "gate_status": gate_status,
        "detector_module": detector_record.get("module"),
        "detector_route": detector_record.get("new_route"),
        "visual_subtype": detector_record.get("visual_subtype"),
        "meaningful_image_visual": bool(detector_record.get("meaningful_image_visual")),
        "route_confidence": detector_record.get("route_confidence"),
        "route_reasons": detector_record.get("route_reasons", []),
        "scores": detector_record.get("scores", {}),
        "features": detector_record.get("features", {}),
        "old_image_visual_candidate": detector_record.get("old_image_visual_candidate"),
    }

    # Preserve strict safety defaults.
    output["final_answer_allowed"] = False
    output["answer_permission"] = False
    output["can_answer_directly"] = False
    output["can_prove_claims"] = False
    output["source_truth_mutation_allowed"] = False

    return output


def build(args: argparse.Namespace) -> Dict[str, Any]:
    visual_context_jsonl = Path(args.visual_context_jsonl)
    detector_jsonl = Path(args.meaningful_image_detector_jsonl)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    allowed_routes = {x.strip() for x in args.allowed_routes.split(",") if x.strip()}
    review_routes = {x.strip() for x in args.review_routes.split(",") if x.strip()}

    detector_by_page = load_detector(detector_jsonl)
    contexts = list(read_jsonl(visual_context_jsonl) or [])

    confirmed: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    missing_detector: List[Dict[str, Any]] = []

    detector_route_counts = Counter()
    gate_status_counts = Counter()
    subtype_counts = Counter()

    for rec in contexts:
        page_id = page_id_of(rec)
        detector = detector_by_page.get(page_id)

        if not detector:
            out = dict(rec)
            out["meaningful_image_gate"] = {
                "module": MODULE_NAME,
                "gate_status": "missing_detector_record",
                "reason": "page_id_not_found_in_meaningful_image_detector",
            }
            out["final_answer_allowed"] = False
            out["answer_permission"] = False
            out["can_answer_directly"] = False
            out["can_prove_claims"] = False
            out["source_truth_mutation_allowed"] = False
            missing_detector.append(out)
            gate_status_counts["missing_detector_record"] += 1
            continue

        detector_route = str(detector.get("new_route") or "")
        detector_route_counts[detector_route] += 1
        subtype_counts[str(detector.get("visual_subtype") or "")] += 1

        if detector_route in allowed_routes and detector.get("meaningful_image_visual"):
            confirmed.append(add_gate_metadata(rec, detector, "confirmed_image_context"))
            gate_status_counts["confirmed_image_context"] += 1
        elif detector_route in review_routes:
            review.append(add_gate_metadata(rec, detector, "visual_candidate_review_only"))
            gate_status_counts["visual_candidate_review_only"] += 1
        else:
            excluded.append(add_gate_metadata(rec, detector, "excluded_from_auto_image_context"))
            gate_status_counts["excluded_from_auto_image_context"] += 1

    confirmed_path = output_dir / "trace_net_visual_question_context_gate_v1_confirmed_image_context.jsonl"
    review_path = output_dir / "trace_net_visual_question_context_gate_v1_visual_candidate_review.jsonl"
    excluded_path = output_dir / "trace_net_visual_question_context_gate_v1_excluded_context.jsonl"
    missing_path = output_dir / "trace_net_visual_question_context_gate_v1_missing_detector_context.jsonl"

    write_jsonl(confirmed_path, confirmed)
    write_jsonl(review_path, review)
    write_jsonl(excluded_path, excluded)
    write_jsonl(missing_path, missing_detector)

    # Safety count scan over emitted records.
    emitted = confirmed + review + excluded + missing_detector
    safety_counts = {
        "final_answer_allowed_true_count": sum(1 for r in emitted if bool_from_nested(r, ["final_answer_allowed"])),
        "answer_permission_count": sum(1 for r in emitted if bool_from_nested(r, ["answer_permission"])),
        "can_answer_directly_count": sum(1 for r in emitted if bool_from_nested(r, ["can_answer_directly"])),
        "can_prove_claims_count": sum(1 for r in emitted if bool_from_nested(r, ["can_prove_claims"])),
        "source_truth_mutation_allowed_count": sum(1 for r in emitted if bool_from_nested(r, ["source_truth_mutation_allowed"])),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "ollama_call_attempt_count": 0,
        "llm_call_attempt_count": 0,
    }

    failures: List[str] = []
    if len(contexts) < args.min_source_contexts:
        failures.append(f"source_context_count:{len(contexts)} < {args.min_source_contexts}")
    if len(confirmed) < args.min_confirmed_contexts:
        failures.append(f"confirmed_image_context_count:{len(confirmed)} < {args.min_confirmed_contexts}")
    if len(missing_detector) > args.max_missing_detector_records:
        failures.append(
            f"missing_detector_record_count:{len(missing_detector)} > {args.max_missing_detector_records}"
        )
    for key, value in safety_counts.items():
        if value != 0:
            failures.append(f"{key}:{value} != 0")

    summary = {
        "module": MODULE_NAME,
        "status": "TRACE_NET_VISUAL_QUESTION_CONTEXT_GATE_V1_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "quality_failures": failures,
        "inputs": {
            "visual_context_jsonl": str(visual_context_jsonl),
            "meaningful_image_detector_jsonl": str(detector_jsonl),
            "allowed_routes": sorted(allowed_routes),
            "review_routes": sorted(review_routes),
        },
        "outputs": {
            "confirmed_image_context_jsonl": str(confirmed_path),
            "visual_candidate_review_jsonl": str(review_path),
            "excluded_context_jsonl": str(excluded_path),
            "missing_detector_context_jsonl": str(missing_path),
            "summary": str(output_dir / "summary.json"),
        },
        "summary": {
            "source_context_count": len(contexts),
            "detector_page_count": len(detector_by_page),
            "confirmed_image_context_count": len(confirmed),
            "visual_candidate_review_context_count": len(review),
            "excluded_context_count": len(excluded),
            "missing_detector_record_count": len(missing_detector),
            "detector_route_counts_for_source_contexts": dict(sorted(detector_route_counts.items())),
            "visual_subtype_counts_for_source_contexts": dict(sorted(subtype_counts.items())),
            "gate_status_counts": dict(sorted(gate_status_counts.items())),
            **safety_counts,
        },
        "safety_contract": {
            "read_only_gate": True,
            "does_not_call_ollama": True,
            "does_not_call_llm": True,
            "does_not_write_postgres": True,
            "does_not_write_qdrant": True,
            "does_not_write_opensearch": True,
            "does_not_mutate_source_truth": True,
            "final_answer_allowed": False,
            "answer_permission": False,
        },
    }

    write_json(output_dir / "summary.json", summary)

    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    for key, value in summary["summary"].items():
        if isinstance(value, dict):
            print(f"{key}=" + json.dumps(value, sort_keys=True))
        else:
            print(f"{key}={value}")
    print("output_dir=" + str(output_dir))

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--visual-context-jsonl", required=True)
    ap.add_argument("--meaningful-image-detector-jsonl", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument(
        "--allowed-routes",
        default="image_visual,mixed_visual_table",
        help="Detector routes allowed into confirmed image context.",
    )
    ap.add_argument(
        "--review-routes",
        default="visual_candidate_review",
        help="Detector routes retained separately as review-only context.",
    )
    ap.add_argument("--min-source-contexts", type=int, default=1)
    ap.add_argument("--min-confirmed-contexts", type=int, default=1)
    ap.add_argument("--max-missing-detector-records", type=int, default=0)
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = build(args)
    return 0 if summary.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
