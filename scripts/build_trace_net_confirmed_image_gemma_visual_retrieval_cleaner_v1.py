#!/usr/bin/env python3
"""TRACE-Net confirmed image Gemma visual retrieval cleaner v1.

Deterministic post-cleaner for completed Gemma visual cards before endpoint use.
No model calls. No DB/vector/search writes. No answer permission.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

MODULE_NAME = "trace_net_confirmed_image_gemma_visual_retrieval_cleaner_v1"
STATUS_BUILT = "TRACE_NET_CONFIRMED_IMAGE_GEMMA_VISUAL_RETRIEVAL_CLEANER_V1_BUILT"

PROMPT_LEAK_PATTERNS = [
    "trace-net's visual observation specialist",
    "trace-net visual observation specialist",
    "scanned aircraft technical-manual pages",
    "existing non-authoritative hints",
    "required json fields",
    "strict rules",
    "do not copy non-authoritative hints",
    "do not prove fit",
    "do not replace ocr",
    "mark uncertain text",
]
UNRELATED_OR_UNSAFE_KEYWORD_PATTERNS = [
    "tecnam aircraft",
    "type certificate data sheet",
    "safety note",
    "sensitive information",
]
GENERIC_CALLOUT_VALUES = {
    "arrows", "arrow", "lines", "line", "relationships", "relationship",
    "part number", "part numbers", "measurements", "measurement",
    "component description", "components", "parts", "labels", "annotations",
}
PROOF_WORD_RE = re.compile(r"\b(confirm|confirmation|confirmed|verify|verified|prove|establish|certify|validate|validation)\b", re.I)


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
    out, seen = [], set()
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
                obj = json.loads(line)
            except Exception as exc:
                raise SystemExit(f"invalid JSONL at {path}:{lineno}: {exc}") from exc
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def has_bad_pattern(value: Any, patterns: Sequence[str]) -> bool:
    low = compact_ws(value, limit=12000).lower()
    return any(pattern in low for pattern in patterns)


def scrub_bad_patterns(value: Any) -> str:
    text = compact_ws(value, limit=12000)
    for pattern in PROMPT_LEAK_PATTERNS + UNRELATED_OR_UNSAFE_KEYWORD_PATTERNS:
        text = re.sub(re.escape(pattern), "", text, flags=re.I)
    text = re.sub(r"\s*,\s*,+", ", ", text)
    text = re.sub(r"\s*\|\s*\|\s*", " | ", text)
    return compact_ws(text, limit=12000).strip(" ,|")


def clean_list(values: Any, *, limit: int = 80) -> List[str]:
    if values is None:
        return []
    raw = values if isinstance(values, list) else [values]
    cleaned = []
    for value in raw:
        text = scrub_bad_patterns(value)
        if not text:
            continue
        if has_bad_pattern(text, PROMPT_LEAK_PATTERNS + UNRELATED_OR_UNSAFE_KEYWORD_PATTERNS):
            continue
        cleaned.append(text)
    return stable_unique(cleaned, limit=limit)


def normalize_figure_refs(values: Any, *, limit: int = 40) -> List[str]:
    out: List[str] = []
    for value in clean_list(values, limit=limit * 2):
        text = compact_ws(value, limit=200).lower()
        for match in re.finditer(r"\bfig(?:ure)?\.?\s*([0-9]{1,4}[a-z]?)(?:\s*sheet\s*([0-9]{1,3}))?\b", text, flags=re.I):
            fig = f"figure {match.group(1)}"
            if match.group(2):
                fig += f" sheet {match.group(2)}"
            out.append(fig)
        if re.fullmatch(r"[0-9]{2,4}[a-z]?", text):
            out.append(f"figure {text}")
    return stable_unique(out, limit=limit)


def normalize_callouts(values: Any, *, limit: int = 60) -> List[str]:
    out = []
    for value in clean_list(values, limit=limit * 2):
        low = value.lower()
        if low in GENERIC_CALLOUT_VALUES:
            continue
        if len(value.split()) > 6 and not re.search(r"\b(item|callout|fig(?:ure)?|part|no\.?|number)\b", low):
            continue
        out.append(value)
    return stable_unique(out, limit=limit)


def sanitize_evidence_use(value: Any) -> str:
    text = scrub_bad_patterns(value)
    text = re.sub(r"\bvisual\s+confirmation\b", "visual retrieval context", text, flags=re.I)
    text = re.sub(r"\bconfirmation\b", "retrieval context", text, flags=re.I)
    text = re.sub(r"\bconfirmed\b", "candidate", text, flags=re.I)
    text = re.sub(r"\bconfirm\b", "locate", text, flags=re.I)
    text = re.sub(r"\bverified\b", "retrieval-linked", text, flags=re.I)
    text = re.sub(r"\bverify\b", "retrieve", text, flags=re.I)
    text = re.sub(r"\bprove\b", "support retrieval for", text, flags=re.I)
    text = re.sub(r"\bestablish\b", "suggest", text, flags=re.I)
    text = re.sub(r"\bcertify\b", "describe", text, flags=re.I)
    text = re.sub(r"\bvalidate\b", "organize", text, flags=re.I)
    text = re.sub(r"\bvalidation\b", "organization", text, flags=re.I)
    if not text:
        text = "Use this card to retrieve likely relevant visual/diagram pages."
    if "not final proof" not in text.lower():
        text += " This is not final proof."
    if "fit" not in text.lower() or "installation" not in text.lower():
        text += " Do not use for fit, interchangeability, effectivity, approval, eligibility, or installation claims."
    return compact_ws(text, limit=1200)


def clean_uncertainty(value: Any) -> str:
    text = scrub_bad_patterns(value)
    text = re.sub(r"Safety note:\s*", "", text, flags=re.I)
    text = re.sub(r"Do not [^.]+(?:\.|$)", "", text, flags=re.I)
    text = compact_ws(text, limit=1000)
    return text or "Visual interpretation is guidance only; exact text requires OCR/source evidence."


def clean_structured_card(card: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(card)
    out["normalized_visual_page_type"] = scrub_bad_patterns(out.get("normalized_visual_page_type") or "technical_diagram_or_figure")
    out["normalized_subject"] = scrub_bad_patterns(out.get("normalized_subject") or "unknown") or "unknown"
    out["figure_refs"] = normalize_figure_refs(out.get("figure_refs"), limit=40)
    out["part_numbers"] = clean_list(out.get("part_numbers"), limit=40)
    out["visible_callouts"] = normalize_callouts(out.get("visible_callouts"), limit=60)
    out["visual_layout_summary"] = scrub_bad_patterns(out.get("visual_layout_summary"))
    out["uncertainty_notes"] = clean_uncertainty(out.get("uncertainty_notes"))
    out["retrieval_keywords"] = stable_unique(
        [
            out.get("normalized_visual_page_type"),
            out.get("normalized_subject"),
            *out.get("figure_refs", []),
            *out.get("part_numbers", []),
            *out.get("visible_callouts", []),
            *clean_list(card.get("retrieval_keywords"), limit=80),
        ],
        limit=80,
    )
    out["evidence_use"] = sanitize_evidence_use(out.get("evidence_use"))
    prohibited = set(clean_list(out.get("prohibited_claims"), limit=20))
    prohibited.update(["fit", "interchangeability", "effectivity", "approval", "eligibility", "installation"])
    out["prohibited_claims"] = stable_unique(sorted(prohibited), limit=20)
    confidence = compact_ws(out.get("confidence"), limit=50).lower()
    out["confidence"] = confidence if confidence in {"low", "medium", "high"} else "low"
    return out


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
        "document_id": f"confirmed_image_gemma_visual_card_clean::{record['page_id']}",
        "page_id": record["page_id"],
        "route_name": "confirmed_image_gemma_visual_card_clean",
        "retrieval_text": compact_ws(" | ".join([p for p in parts if p]), limit=12000),
        "structured_visual_card": card,
        "source_record_module": record.get("module"),
        "safety_contract": record.get("safety_contract") or {
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        },
    }


def clean_record(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["module"] = MODULE_NAME
    out["source_module"] = row.get("module")
    out["structured_visual_card"] = clean_structured_card(row.get("structured_visual_card") or {})
    out.setdefault("safety_contract", {})
    out["safety_contract"].update(
        {
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        }
    )
    return out


def quality_summary(records: List[Dict[str, Any]], docs: List[Dict[str, Any]], *, min_record_count: int) -> Dict[str, Any]:
    counts = {
        "prompt_leak_record_count": 0,
        "unsafe_keyword_record_count": 0,
        "proof_word_evidence_use_count": 0,
        "generic_callout_count": 0,
        "non_figure_ref_count": 0,
        "answer_permission_count": 0,
        "final_answer_allowed_true_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    for row in records:
        card = row.get("structured_visual_card") or {}
        blob = json.dumps(card, ensure_ascii=False, sort_keys=True)
        counts["prompt_leak_record_count"] += int(has_bad_pattern(blob, PROMPT_LEAK_PATTERNS))
        counts["unsafe_keyword_record_count"] += int(has_bad_pattern(card.get("retrieval_keywords"), UNRELATED_OR_UNSAFE_KEYWORD_PATTERNS))
        counts["proof_word_evidence_use_count"] += int(bool(PROOF_WORD_RE.search(compact_ws(card.get("evidence_use"), limit=2000))))
        for c in card.get("visible_callouts") or []:
            counts["generic_callout_count"] += int(compact_ws(c, limit=200).lower() in GENERIC_CALLOUT_VALUES)
        for fig in card.get("figure_refs") or []:
            counts["non_figure_ref_count"] += int(not re.fullmatch(r"figure [0-9]{1,4}[a-z]?(?: sheet [0-9]{1,3})?", compact_ws(fig, limit=200).lower()))
        safety = row.get("safety_contract") or {}
        counts["answer_permission_count"] += int(bool(safety.get("answer_permission")))
        counts["final_answer_allowed_true_count"] += int(bool(safety.get("final_answer_allowed")))
        counts["source_truth_mutation_allowed_count"] += int(bool(safety.get("source_truth_mutation_allowed")))

    quality_status, issues = "PASS", []
    if len(records) < min_record_count:
        quality_status = "FAIL"
        issues.append(f"record_count_below_min:{len(records)}<{min_record_count}")
    for key, value in counts.items():
        if value:
            quality_status = "FAIL"
            issues.append(f"{key}:{value}")

    return {
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "quality_issues": issues,
        "source_record_count": len(records),
        "cleaned_record_count": len(records),
        "retrieval_document_count": len(docs),
        **counts,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--structured-visual-cards-jsonl", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--min-record-count", type=int, default=1)
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    rows = read_jsonl(Path(args.structured_visual_cards_jsonl))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cleaned = [clean_record(r) for r in rows]
    docs = [retrieval_doc_for_record(r) for r in cleaned]
    summary = quality_summary(cleaned, docs, min_record_count=args.min_record_count)
    summary["output_dir"] = str(out_dir)

    write_jsonl(out_dir / "trace_net_confirmed_image_gemma_visual_clean_cards_v1.jsonl", cleaned)
    write_jsonl(out_dir / "trace_net_confirmed_image_gemma_visual_clean_retrieval_documents_v1.jsonl", docs)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (out_dir / "trace_net_confirmed_image_gemma_visual_retrieval_cleaner_v1_report.txt").write_text(
        "\n".join(f"{k}={v}" for k, v in summary.items()) + "\n",
        encoding="utf-8",
    )

    for key in [
        "status", "quality_status", "source_record_count", "cleaned_record_count",
        "retrieval_document_count", "prompt_leak_record_count", "unsafe_keyword_record_count",
        "proof_word_evidence_use_count", "generic_callout_count", "non_figure_ref_count",
        "answer_permission_count", "final_answer_allowed_true_count",
        "source_truth_mutation_allowed_count", "output_dir",
    ]:
        print(f"{key}={summary[key]}")
    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
