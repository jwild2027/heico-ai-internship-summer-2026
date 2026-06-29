"""TRACE-Net WebUI visual context bridge v1.

Builds a conservative WebUI/Self-RAG visual-context artifact from the
semantically validated image visual summary. Only records explicitly allowed by
TRACE-Net semantic validation are surfaced as context cards. Review-only LLaVA
observations are counted and excluded.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_webui_visual_context_bridge_v1"
VERSION = "v1"
STATUS = "TRACE_NET_WEBUI_VISUAL_CONTEXT_BRIDGE_BUILT"

_ALLOWED_SEMANTIC_STATUS = "WEBUI_VISUAL_CONTEXT_ALLOWED"
_ALLOWED_VISUAL_QUALITY = "CLEAN_VISION_OBSERVATION_READY"


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ("records", "visual_summary_cards", "cards", "context_cards"):
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string_list(value: Any, *, max_items: int = 20, max_len: int = 200) -> List[str]:
    result: List[str] = []
    for item in _safe_list(value):
        if isinstance(item, Mapping):
            # Common LLaVA JSON shapes in earlier smoke runs.
            for key in ("label", "feature", "text", "value", "name"):
                if isinstance(item.get(key), str):
                    item = item[key]
                    break
        if not isinstance(item, str):
            item = str(item)
        cleaned = " ".join(item.split()).strip()
        if not cleaned:
            continue
        if len(cleaned) > max_len:
            cleaned = cleaned[: max_len - 1].rstrip() + "…"
        if cleaned not in result:
            result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def _page_id(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("page_id", "canonical_page_id", "source_page_id", "trace_page_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _visual_observation(record: Mapping[str, Any]) -> Mapping[str, Any]:
    observation = record.get("visual_observation")
    return observation if isinstance(observation, Mapping) else {}


def _semantic_validation(record: Mapping[str, Any]) -> Mapping[str, Any]:
    validation = record.get("semantic_validation")
    return validation if isinstance(validation, Mapping) else {}


def _allowed(record: Mapping[str, Any]) -> bool:
    if not _as_bool(record.get("webui_visual_context_allowed")):
        return False
    if record.get("semantic_validation_status") != _ALLOWED_SEMANTIC_STATUS:
        return False
    if record.get("visual_observation_quality_status") != _ALLOWED_VISUAL_QUALITY:
        return False
    if record.get("visual_model_execution_status") != "vision_model_observation_ready":
        return False
    if _as_bool(record.get("prompt_leak_suspected")):
        return False
    if _as_bool(record.get("invented_item_sequence_suspected")):
        return False
    if _as_bool(record.get("excessive_visual_label_count")):
        return False
    return True


def _context_card(record: Mapping[str, Any], index: int) -> Dict[str, Any]:
    observation = _visual_observation(record)
    semantic = _semantic_validation(record)
    supported_terms = _string_list(semantic.get("ocr_supported_visual_terms"), max_items=20)
    unsupported_labels = _string_list(semantic.get("unsupported_visual_labels"), max_items=20)
    visible_text_or_labels = _string_list(observation.get("visible_text_or_labels"), max_items=20)
    visible_callouts = _string_list(observation.get("visible_callouts"), max_items=20)
    observed_features = _string_list(observation.get("observed_visual_features"), max_items=20)
    uncertainty_flags = _string_list(observation.get("uncertainty_flags"), max_items=20)
    page_id = _page_id(record) or f"visual_context_{index:04d}"

    return {
        "record_type": "webui_visual_context_card",
        "module": MODULE,
        "version": VERSION,
        "context_card_id": f"webui_visual_context_{index + 1:04d}",
        "page_id": page_id,
        "canonical_page_number": record.get("canonical_page_number"),
        "accepted_route": record.get("accepted_route") or "image_visual",
        "source_image_path": record.get("image_path"),
        "source_visual_summary_artifact_id": record.get("visual_summary_card_id") or record.get("card_id"),
        "vision_model": record.get("vision_model"),
        "vision_mode": record.get("vision_mode"),
        "visual_page_type": observation.get("visual_page_type") or record.get("visual_page_type"),
        "visual_summary_text": record.get("visual_summary_text") or observation.get("summary"),
        "ocr_supported_visual_terms": supported_terms,
        "unsupported_visual_labels_excluded": unsupported_labels,
        "visible_text_or_labels": visible_text_or_labels,
        "visible_callouts": visible_callouts,
        "observed_visual_features": observed_features,
        "uncertainty_flags": sorted(set(uncertainty_flags + ["vision_derived_guidance_not_source_truth"])),
        "semantic_validation_status": record.get("semantic_validation_status"),
        "hallucination_risk_status": record.get("hallucination_risk_status"),
        "visual_observation_quality_status": record.get("visual_observation_quality_status"),
        "ocr_text_available_for_visual_validation": _as_bool(record.get("ocr_text_available_for_visual_validation")),
        "ocr_text_char_count_for_visual_validation": record.get("ocr_text_char_count_for_visual_validation") or 0,
        "ocr_label_support_count": record.get("ocr_label_support_count") or 0,
        "unsupported_visual_label_count": record.get("unsupported_visual_label_count") or 0,
        "generic_visual_label_count": record.get("generic_visual_label_count") or 0,
        "webui_visual_context_allowed": True,
        "context_authority": "vision_derived_retrieval_guidance_not_source_truth",
        "requires_source_truth_confirmation": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "safety_contract": {
            "artifact_authority": "vision_derived_retrieval_guidance_not_source_truth",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "requires_downstream_source_truth_confirmation": True,
            "review_only_cards_excluded": True,
        },
    }


def _excluded_record(record: Mapping[str, Any], index: int) -> Dict[str, Any]:
    semantic = _semantic_validation(record)
    reasons = _string_list(semantic.get("semantic_review_reasons"), max_items=30)
    if not reasons and record.get("visual_review_reasons"):
        reasons = _string_list(record.get("visual_review_reasons"), max_items=30)
    if not reasons:
        reasons = ["not_webui_visual_context_allowed"]
    return {
        "record_type": "excluded_visual_context_record",
        "exclusion_id": f"excluded_visual_context_{index + 1:04d}",
        "page_id": _page_id(record),
        "canonical_page_number": record.get("canonical_page_number"),
        "accepted_route": record.get("accepted_route") or "image_visual",
        "semantic_validation_status": record.get("semantic_validation_status"),
        "hallucination_risk_status": record.get("hallucination_risk_status"),
        "visual_observation_quality_status": record.get("visual_observation_quality_status"),
        "visual_model_execution_status": record.get("visual_model_execution_status"),
        "webui_visual_context_allowed": _as_bool(record.get("webui_visual_context_allowed")),
        "excluded_from_webui_context": True,
        "exclusion_reasons": reasons,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def build_webui_visual_context_bridge(
    *,
    image_visual_summary_path: Path,
    output_dir: Path,
    max_context_cards: Optional[int] = None,
) -> Dict[str, Any]:
    source_payload = _read_json(image_visual_summary_path)
    source_records = _records(source_payload)
    allowed_records = [record for record in source_records if _allowed(record)]
    if max_context_cards is not None:
        allowed_records = allowed_records[: max(0, max_context_cards)]

    context_cards = [_context_card(record, index) for index, record in enumerate(allowed_records)]
    excluded_records = [_excluded_record(record, index) for index, record in enumerate(source_records) if not _allowed(record)]

    safety_counter_fields = (
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "unsafe_record_count",
    )

    source_summary = source_payload.get("summary") if isinstance(source_payload.get("summary"), Mapping) else {}
    status_counts = Counter(str(record.get("semantic_validation_status")) for record in source_records)
    hallucination_counts = Counter(str(record.get("hallucination_risk_status")) for record in source_records)

    summary: Dict[str, Any] = {
        "source_image_visual_summary_quality_status": source_payload.get("quality_status"),
        "source_image_visual_summary_record_count": len(source_records),
        "source_image_visual_handoff_count": source_summary.get("image_visual_handoff_count"),
        "source_webui_visual_context_allowed_count": source_summary.get("webui_visual_context_allowed_count"),
        "semantic_validation_status_counts": dict(status_counts),
        "hallucination_risk_status_counts": dict(hallucination_counts),
        "visual_context_card_count": len(context_cards),
        "review_only_visual_context_excluded_count": len(excluded_records),
        "included_page_count": len({card.get("page_id") for card in context_cards if card.get("page_id")}),
        "included_pages": [card.get("page_id") for card in context_cards],
        "included_canonical_page_numbers": [card.get("canonical_page_number") for card in context_cards],
        "vision_model_counts": dict(Counter(str(card.get("vision_model")) for card in context_cards)),
        "context_authority": "vision_derived_retrieval_guidance_not_source_truth",
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    # Preserve obvious upstream safety failures if present; this bridge itself never writes.
    for field in safety_counter_fields:
        upstream = source_summary.get(field)
        if isinstance(upstream, int) and upstream > 0:
            summary[field] = upstream

    quality_failures: List[str] = []
    if source_payload.get("quality_status") != "PASS":
        quality_failures.append("source image visual summary quality_status is not PASS")
    if any(summary.get(field, 0) for field in safety_counter_fields):
        quality_failures.append("one or more safety counters are non-zero")
    for card in context_cards:
        if not card.get("webui_visual_context_allowed"):
            quality_failures.append(f"context card not webui allowed: {card.get('page_id')}")
        if card.get("answer_permission"):
            quality_failures.append(f"context card has answer permission: {card.get('page_id')}")

    quality_status = "PASS" if not quality_failures else "FAIL"
    payload: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS,
        "quality_status": quality_status,
        "quality_failures": quality_failures,
        "summary": summary,
        "source_paths": {
            "image_visual_summary": str(image_visual_summary_path),
        },
        "records": context_cards,
        "context_cards": context_cards,
        "excluded_records": excluded_records,
        "safety_contract": {
            "artifact_authority": "vision_derived_retrieval_guidance_not_source_truth",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "requires_downstream_source_truth_confirmation": True,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "trace_net_webui_visual_context_bridge_v1.json", payload)
    _write_json(output_dir / "trace_net_webui_visual_context_bridge_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_webui_visual_context_bridge_v1_quality.json", {"quality_status": quality_status, "summary": summary, "quality_failures": quality_failures})
    _write_jsonl(output_dir / "trace_net_webui_visual_context_bridge_v1_context_cards.jsonl", context_cards)
    _write_jsonl(output_dir / "trace_net_webui_visual_context_bridge_v1_excluded_records.jsonl", excluded_records)
    _write_text(output_dir / "trace_net_webui_visual_context_bridge_v1.md", _markdown_report(payload))
    return payload


def _markdown_report(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net WebUI Visual Context Bridge v1",
        "",
        f"Quality status: {payload.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in sorted(summary.keys()):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Included context cards")
    lines.append("")
    for card in payload.get("records") or []:
        lines.append(f"- {card.get('page_id')} page={card.get('canonical_page_number')} risk={card.get('hallucination_risk_status')} supported_terms={card.get('ocr_supported_visual_terms')}")
    lines.append("")
    lines.append("Safety: visual context is retrieval guidance only, not source truth and not answer permission.")
    lines.append("")
    return "\n".join(lines)


def check_webui_visual_context_bridge_quality(
    *,
    report_path: Path,
    min_source_records: int = 1,
    min_context_cards: int = 1,
    min_excluded_records: int = 0,
    require_source_quality_pass: bool = False,
    require_only_webui_allowed: bool = False,
    require_review_only_excluded: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: Optional[int] = None,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    excluded = payload.get("excluded_records") if isinstance(payload.get("excluded_records"), list) else []
    failures: List[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if int(summary.get("source_image_visual_summary_record_count") or 0) < min_source_records:
        failures.append("source record count below minimum")
    if len(records) < min_context_cards:
        failures.append("context card count below minimum")
    if len(excluded) < min_excluded_records:
        failures.append("excluded record count below minimum")
    if require_source_quality_pass and summary.get("source_image_visual_summary_quality_status") != "PASS":
        failures.append("source image visual summary quality_status is not PASS")
    if require_only_webui_allowed:
        for record in records:
            if not _as_bool(record.get("webui_visual_context_allowed")):
                failures.append(f"non-webui-allowed record included: {record.get('page_id')}")
            if record.get("context_authority") != "vision_derived_retrieval_guidance_not_source_truth":
                failures.append(f"unexpected context authority: {record.get('page_id')}")
    if require_review_only_excluded and int(summary.get("review_only_visual_context_excluded_count") or 0) < 1:
        failures.append("review-only visual contexts were not counted as excluded")
    if require_no_answer_permission:
        if int(summary.get("answer_permission_count") or 0) != 0:
            failures.append("answer_permission_count is non-zero")
        for record in records:
            if _as_bool(record.get("answer_permission")) or _as_bool(record.get("can_answer_directly")) or _as_bool(record.get("can_prove_claims")):
                failures.append(f"record has answer/direct/proof permission: {record.get('page_id')}")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count is non-zero")
    if require_no_write_attempts:
        for field in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            if int(summary.get(field) or 0) != 0:
                failures.append(f"{field} is non-zero")
    if max_unsafe is not None and int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count exceeds maximum")

    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "module": MODULE,
        "check_type": "quality_check",
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
    }
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net WebUI visual context bridge v1")
    parser.add_argument("--image-visual-summary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-context-cards", type=int, default=None)
    parser.add_argument("--quality", action="store_true")
    return parser


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    args = _build_parser().parse_args(argv)
    payload = build_webui_visual_context_bridge(
        image_visual_summary_path=args.image_visual_summary,
        output_dir=args.output_dir,
        max_context_cards=args.max_context_cards,
    )
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload.get("summary", {}), sort_keys=True))
    if args.quality and payload.get("quality_status") != "PASS":
        raise SystemExit(1)
    return payload


def _check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net WebUI visual context bridge v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-source-records", type=int, default=1)
    parser.add_argument("--min-context-cards", type=int, default=1)
    parser.add_argument("--min-excluded-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-only-webui-allowed", action="store_true")
    parser.add_argument("--require-review-only-excluded", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=None)
    return parser


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    args = _check_parser().parse_args(argv)
    result = check_webui_visual_context_bridge_quality(
        report_path=args.report_path,
        min_source_records=args.min_source_records,
        min_context_cards=args.min_context_cards,
        min_excluded_records=args.min_excluded_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_only_webui_allowed=args.require_only_webui_allowed,
        require_review_only_excluded=args.require_review_only_excluded,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        max_unsafe=args.max_unsafe,
    )
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(result.get("summary", {}), sort_keys=True))
    if result.get("failures"):
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = args.report_path.with_name("trace_net_webui_visual_context_bridge_v1_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    if result["quality_status"] != "PASS":
        raise SystemExit(1)
    return result


if __name__ == "__main__":  # pragma: no cover
    main_build()
