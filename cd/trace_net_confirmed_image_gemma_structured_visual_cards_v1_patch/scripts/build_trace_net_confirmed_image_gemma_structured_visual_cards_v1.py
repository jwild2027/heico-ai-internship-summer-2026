#!/usr/bin/env python3
"""TRACE-Net confirmed image Gemma structured visual cards v1.

Reads confirmed image page summary cards that already contain cleaned LLaVA
observations, then optionally asks Gemma4 to normalize them into retrieval-ready
structured visual cards.

Safety contract:
- Does not mutate source truth.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not grant answer permission.
- LLaVA is visual guidance only; OCR/source fields remain authority for exact
  text/part-number facts.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


MODULE_NAME = "trace_net_confirmed_image_gemma_structured_visual_cards_v1"
STATUS_BUILT = "TRACE_NET_CONFIRMED_IMAGE_GEMMA_STRUCTURED_VISUAL_CARDS_V1_BUILT"


def compact_ws(value: Any, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            value = str(value)
    value = re.sub(r"\s+", " ", value).strip()
    if limit and len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def stable_unique(values: Iterable[Any], *, limit: int = 80) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = compact_ws(value, limit=600)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception as exc:
                raise SystemExit(f"invalid JSONL at {path}:{lineno}: {exc}") from exc
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def strip_json_fence(text: str) -> str:
    value = compact_ws(text, limit=100000)
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def parse_jsonish(text: Any) -> Optional[Dict[str, Any]]:
    value = strip_json_fence(compact_ws(text, limit=100000))
    if not value:
        return None
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    try:
        parsed = ast.literal_eval(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def pick_page_id(row: Dict[str, Any]) -> str:
    return compact_ws(row.get("page_id") or row.get("page") or row.get("id"), limit=200)


def row_matches_page_filter(row: Dict[str, Any], page_ids: Sequence[str]) -> bool:
    if not page_ids:
        return True
    return pick_page_id(row) in set(page_ids)


def clean_list(values: Any, *, limit: int = 80) -> List[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return stable_unique(values, limit=limit)
    return stable_unique([values], limit=limit)


def is_generic_subject(subject: str) -> bool:
    low = compact_ws(subject, limit=300).lower()
    return (
        not low
        or low == "unknown"
        or low.startswith("confirmed image/diagram page")
        or low.startswith("visual page associated with part number")
        or "subject not explicitly identified" in low
    )


def prompt_for_gemma(row: Dict[str, Any]) -> str:
    card = row.get("visual_page_summary") if isinstance(row.get("visual_page_summary"), dict) else {}
    llava_clean = row.get("llava_clean_observation") if isinstance(row.get("llava_clean_observation"), dict) else {}

    source_payload = {
        "page_id": pick_page_id(row),
        "visual_page_type": card.get("visual_page_type"),
        "current_subject": card.get("likely_diagram_subject"),
        "figure_refs_from_source_or_cleaned_visual": card.get("figure_refs_clean") or [],
        "part_numbers_from_source_authority": card.get("part_numbers") or [],
        "current_visual_observations": card.get("visual_observations") or [],
        "cleaned_llava_observation": {
            "diagram_subject_guess": llava_clean.get("diagram_subject_guess"),
            "visual_layout_description": llava_clean.get("visual_layout_description"),
            "figure_title_or_sheet_text_if_clearly_visible": llava_clean.get("figure_title_or_sheet_text_if_clearly_visible"),
            "visible_callouts_or_labels_cleaned": llava_clean.get("visible_callouts_or_labels_cleaned") or [],
            "visual_uncertainty": llava_clean.get("visual_uncertainty"),
            "retrieval_keywords": llava_clean.get("retrieval_keywords") or [],
        },
        "safety": {
            "llava_is_visual_guidance_only": True,
            "ocr_table_source_evidence_is_authority_for_exact_text": True,
            "do_not_make_fit_interchangeability_effectivity_approval_installation_claims": True,
        },
    }

    return f"""You are TRACE-Net's Gemma4 visual-card structurer.

Task: convert the provided confirmed image-page card plus cleaned LLaVA observation into one strict JSON object for retrieval. You are organizing evidence, not answering the user.

Return ONLY valid JSON with exactly these keys:
- page_id
- normalized_visual_page_type
- normalized_subject
- figure_refs
- part_numbers
- visible_callouts
- visual_layout_summary
- uncertainty_notes
- retrieval_keywords
- evidence_use
- prohibited_claims
- confidence

Rules:
- Use only the provided input.
- Do not invent part numbers, figure numbers, callouts, titles, effectivity, eligibility, approval, fit, interchangeability, or installation facts.
- part_numbers must come only from part_numbers_from_source_authority.
- If a subject is uncertain, use "unknown" or keep a cautious association like "visual page associated with part number(s): ...".
- LLaVA visual observations are guidance only, not source-truth proof for exact text.
- Keep visible_callouts short and concrete; do not include generic sentences.
- evidence_use should explain how the card can help retrieval, not final answering.
- prohibited_claims must include fit, interchangeability, effectivity, approval, eligibility, and installation.
- confidence must be one of: low, medium, high.

Input:
{json.dumps(source_payload, ensure_ascii=False, sort_keys=True)[:12000]}
"""


def ollama_generate(
    *,
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: float,
) -> str:
    endpoint = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": 8192,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
    return compact_ws(parsed.get("response") or "", limit=100000)


def deterministic_structured_card(row: Dict[str, Any]) -> Dict[str, Any]:
    page_id = pick_page_id(row)
    card = row.get("visual_page_summary") if isinstance(row.get("visual_page_summary"), dict) else {}
    llava_clean = row.get("llava_clean_observation") if isinstance(row.get("llava_clean_observation"), dict) else {}

    subject = compact_ws(card.get("likely_diagram_subject"), limit=500)
    if is_generic_subject(subject):
        llava_subject = compact_ws(llava_clean.get("diagram_subject_guess"), limit=500)
        subject = "" if llava_subject.lower() == "unknown" else llava_subject
    if not subject:
        parts = clean_list(card.get("part_numbers"), limit=12)
        subject = (
            f"visual page associated with part number(s): {', '.join(parts[:5])}"
            if parts
            else "unknown"
        )

    layout_parts = [
        compact_ws(llava_clean.get("visual_layout_description"), limit=1200),
        *clean_list(card.get("visual_observations"), limit=5),
    ]
    visual_layout = compact_ws(" | ".join([x for x in layout_parts if x]), limit=2000)

    callouts = clean_list(llava_clean.get("visible_callouts_or_labels_cleaned"), limit=40)
    # Keep callouts concrete and short; remove generic long sentences.
    callouts = [
        c for c in callouts
        if len(c) <= 120 and not c.lower().startswith(("callouts include", "the diagram includes"))
    ]

    parts = clean_list(card.get("part_numbers"), limit=40)
    figures = clean_list(card.get("figure_refs_clean"), limit=40)

    keywords = stable_unique(
        [
            card.get("visual_page_type"),
            subject,
            *figures,
            *parts,
            *callouts,
            *clean_list(llava_clean.get("retrieval_keywords"), limit=40),
        ],
        limit=80,
    )

    return {
        "page_id": page_id,
        "normalized_visual_page_type": compact_ws(card.get("visual_page_type") or "technical_diagram_or_figure", limit=200),
        "normalized_subject": subject,
        "figure_refs": figures,
        "part_numbers": parts,
        "visible_callouts": callouts,
        "visual_layout_summary": visual_layout,
        "uncertainty_notes": compact_ws(llava_clean.get("visual_uncertainty") or "Visual interpretation is guidance only; exact text requires OCR/source evidence.", limit=1000),
        "retrieval_keywords": keywords,
        "evidence_use": "Use this card to retrieve likely relevant visual/diagram pages. Do not use it as final proof for exact text, fit, interchangeability, effectivity, approval, eligibility, or installation.",
        "prohibited_claims": ["fit", "interchangeability", "effectivity", "approval", "eligibility", "installation"],
        "confidence": "medium" if parts or figures or callouts else "low",
    }


def validate_structured_card(card: Dict[str, Any], page_id: str, source_part_numbers: List[str]) -> Dict[str, Any]:
    out = dict(card)
    out["page_id"] = compact_ws(out.get("page_id") or page_id, limit=200)
    out["normalized_visual_page_type"] = compact_ws(out.get("normalized_visual_page_type") or "technical_diagram_or_figure", limit=200)
    out["normalized_subject"] = compact_ws(out.get("normalized_subject") or "unknown", limit=600)
    out["figure_refs"] = clean_list(out.get("figure_refs"), limit=40)

    # Enforce source authority for part numbers. Gemma may only select from the
    # source-approved part-number set.
    allowed_parts = set(clean_list(source_part_numbers, limit=80))
    proposed_parts = clean_list(out.get("part_numbers"), limit=40)
    out["part_numbers"] = [p for p in proposed_parts if p in allowed_parts]

    out["visible_callouts"] = clean_list(out.get("visible_callouts"), limit=60)
    out["visual_layout_summary"] = compact_ws(out.get("visual_layout_summary"), limit=2200)
    out["uncertainty_notes"] = compact_ws(out.get("uncertainty_notes"), limit=1200)
    out["retrieval_keywords"] = clean_list(out.get("retrieval_keywords"), limit=80)
    out["evidence_use"] = compact_ws(out.get("evidence_use"), limit=1200)
    prohibited = set(clean_list(out.get("prohibited_claims"), limit=20))
    prohibited.update(["fit", "interchangeability", "effectivity", "approval", "eligibility", "installation"])
    out["prohibited_claims"] = stable_unique(prohibited, limit=20)
    confidence = compact_ws(out.get("confidence"), limit=50).lower()
    out["confidence"] = confidence if confidence in {"low", "medium", "high"} else "low"
    return out


def build_record(
    row: Dict[str, Any],
    *,
    call_ollama_gemma: bool,
    ollama_base_url: str,
    gemma_model: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    page_id = pick_page_id(row)
    source_card = row.get("visual_page_summary") if isinstance(row.get("visual_page_summary"), dict) else {}
    source_part_numbers = clean_list(source_card.get("part_numbers"), limit=80)

    safety_contract = {
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "llava_visual_guidance_only": True,
        "ocr_table_source_evidence_authority_for_exact_text": True,
    }

    runtime_counts = {
        "ollama_gemma_call_attempt": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }

    gemma_status = "not_requested"
    gemma_raw_response = ""
    parsed_gemma: Optional[Dict[str, Any]] = None

    if call_ollama_gemma:
        runtime_counts["ollama_gemma_call_attempt"] = True
        prompt = prompt_for_gemma(row)
        try:
            started = time.time()
            gemma_raw_response = ollama_generate(
                base_url=ollama_base_url,
                model=gemma_model,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
            parsed_gemma = parse_jsonish(gemma_raw_response)
            if parsed_gemma:
                gemma_status = f"ollama_gemma_structured_card_created ({time.time() - started:.3f}s)"
            else:
                gemma_status = "ollama_gemma_unparseable_response_fallback_used"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            gemma_status = f"ollama_gemma_error_fallback_used: {type(exc).__name__}: {exc}"

    fallback_card = deterministic_structured_card(row)
    structured_card = validate_structured_card(parsed_gemma or fallback_card, page_id, source_part_numbers)
    if not parsed_gemma:
        structured_card = validate_structured_card(fallback_card, page_id, source_part_numbers)

    return {
        "module": MODULE_NAME,
        "page_id": page_id,
        "source_page_summary_module": row.get("module"),
        "source_visual_route": row.get("source_visual_route") or row.get("visual_route"),
        "source_visual_subtype": row.get("source_visual_subtype") or row.get("visual_subtype"),
        "gemma_status": gemma_status,
        "gemma_raw_response": gemma_raw_response,
        "structured_visual_card": structured_card,
        "source_card_snapshot": {
            "visual_page_type": source_card.get("visual_page_type"),
            "likely_diagram_subject": source_card.get("likely_diagram_subject"),
            "figure_refs_clean": source_card.get("figure_refs_clean") or [],
            "part_numbers": source_card.get("part_numbers") or [],
            "llava_clean_payload_loaded": bool((row.get("model_layers") or {}).get("llava_clean_payload_loaded")),
        },
        "runtime_counts": runtime_counts,
        "safety_contract": safety_contract,
    }


def retrieval_doc_for_record(record: Dict[str, Any]) -> Dict[str, Any]:
    card = record["structured_visual_card"]
    parts = [
        card.get("normalized_visual_page_type"),
        card.get("normalized_subject"),
        "figures: " + ", ".join(card.get("figure_refs") or []),
        "parts: " + ", ".join(card.get("part_numbers") or []),
        "callouts: " + ", ".join(card.get("visible_callouts") or []),
        card.get("visual_layout_summary"),
        card.get("uncertainty_notes"),
        "keywords: " + ", ".join(card.get("retrieval_keywords") or []),
    ]
    return {
        "document_id": f"confirmed_image_gemma_visual_card::{record['page_id']}",
        "page_id": record["page_id"],
        "route_name": "confirmed_image_gemma_visual_card",
        "retrieval_text": compact_ws(" | ".join([p for p in parts if p]), limit=12000),
        "structured_visual_card": card,
        "safety_contract": record["safety_contract"],
    }


def build_summary(
    records: List[Dict[str, Any]],
    retrieval_docs: List[Dict[str, Any]],
    *,
    selected_page_count: int,
    min_record_count: int,
    require_gemma_success: bool,
) -> Dict[str, Any]:
    gemma_attempts = sum(bool((r.get("runtime_counts") or {}).get("ollama_gemma_call_attempt")) for r in records)
    gemma_created = sum(str(r.get("gemma_status") or "").startswith("ollama_gemma_structured_card_created") for r in records)
    fallback_count = sum("fallback" in str(r.get("gemma_status") or "") or r.get("gemma_status") == "not_requested" for r in records)
    answer_permission = sum(bool((r.get("safety_contract") or {}).get("answer_permission")) for r in records)
    final_allowed = sum(bool((r.get("safety_contract") or {}).get("final_answer_allowed")) for r in records)
    source_mut = sum(bool((r.get("safety_contract") or {}).get("source_truth_mutation_allowed")) for r in records)

    quality_status = "PASS"
    quality_issues: List[str] = []
    if len(records) < min_record_count:
        quality_status = "FAIL"
        quality_issues.append(f"record_count_below_min:{len(records)}<{min_record_count}")
    if require_gemma_success and gemma_created != len(records):
        quality_status = "FAIL"
        quality_issues.append(f"gemma_success_count_mismatch:{gemma_created}!={len(records)}")
    if answer_permission or final_allowed or source_mut:
        quality_status = "FAIL"
        quality_issues.append("safety_contract_violation")

    return {
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "quality_issues": quality_issues,
        "selected_page_count": selected_page_count,
        "structured_visual_card_count": len(records),
        "retrieval_document_count": len(retrieval_docs),
        "ollama_gemma_call_attempt_count": gemma_attempts,
        "successful_gemma_structured_card_count": gemma_created,
        "fallback_structured_card_count": fallback_count,
        "answer_permission_count": answer_permission,
        "final_answer_allowed_true_count": final_allowed,
        "source_truth_mutation_allowed_count": source_mut,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirmed-image-page-summary-jsonl", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--page-ids", nargs="*", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-record-count", type=int, default=1)
    ap.add_argument("--call-ollama-gemma", action="store_true")
    ap.add_argument("--require-gemma-success", action="store_true")
    ap.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--gemma-model", default="gemma4:26b")
    ap.add_argument("--timeout-seconds", type=float, default=300.0)
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    in_path = Path(args.confirmed_image_page_summary_jsonl)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [r for r in read_jsonl(in_path) if row_matches_page_filter(r, args.page_ids)]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    records: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, 1):
        page_id = pick_page_id(row)
        print(f"[{idx}/{len(rows)}] Gemma visual card page {page_id}...")
        record = build_record(
            row,
            call_ollama_gemma=args.call_ollama_gemma,
            ollama_base_url=args.ollama_base_url,
            gemma_model=args.gemma_model,
            timeout_seconds=args.timeout_seconds,
        )
        print(f"  {record['gemma_status']}")
        records.append(record)

    retrieval_docs = [retrieval_doc_for_record(r) for r in records]
    summary = build_summary(
        records,
        retrieval_docs,
        selected_page_count=len(rows),
        min_record_count=args.min_record_count,
        require_gemma_success=args.require_gemma_success,
    )
    summary["output_dir"] = str(out_dir)

    write_jsonl(out_dir / "trace_net_confirmed_image_gemma_structured_visual_cards_v1.jsonl", records)
    write_jsonl(out_dir / "trace_net_confirmed_image_gemma_structured_visual_retrieval_documents_v1.jsonl", retrieval_docs)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    report_lines = [f"{k}={v}" for k, v in summary.items() if k != "quality_issues"]
    if summary["quality_issues"]:
        report_lines.append("quality_issues=" + json.dumps(summary["quality_issues"], ensure_ascii=False))
    (out_dir / "trace_net_confirmed_image_gemma_structured_visual_cards_v1_report.txt").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    for key in [
        "status",
        "quality_status",
        "selected_page_count",
        "structured_visual_card_count",
        "retrieval_document_count",
        "ollama_gemma_call_attempt_count",
        "successful_gemma_structured_card_count",
        "fallback_structured_card_count",
        "answer_permission_count",
        "final_answer_allowed_true_count",
        "source_truth_mutation_allowed_count",
        "output_dir",
    ]:
        print(f"{key}={summary[key]}")

    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
