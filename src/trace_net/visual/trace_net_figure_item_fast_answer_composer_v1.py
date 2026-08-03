from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_figure_item_fast_answer_composer_v1"
VERSION = "v1"
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FIGURE_RE = re.compile(r"\b(?:fig(?:ure)?\.?\s*)(\d+[A-Z]?)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"\bitem\s+(-?\d+[A-Z]?)\b", re.IGNORECASE)


class FigureItemFastAnswerComposerError(RuntimeError):
    pass


def _read_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))


def _write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _safe_str(value)).strip()


def _label(record: Dict[str, Any]) -> str:
    return _safe_str(record.get("citation_label") or record.get("label") or "E?").strip() or "E?"


def _cit(label: str) -> str:
    if label.startswith("[") and label.endswith("]"):
        return label
    return f"[{label}]"


def _page(record: Dict[str, Any]) -> str:
    return _safe_str(record.get("page_number") or record.get("canonical_page_number") or "?")


def _excerpt(record: Dict[str, Any]) -> str:
    return _norm_text(record.get("excerpt") or record.get("enriched_excerpt") or record.get("exact_row_text") or "")


def _unique(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        value = _safe_str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _source_quality_status(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    return _safe_str(payload.get("quality_status") or summary.get("quality_status") or "UNKNOWN")


def _parse_figure_item(question: Optional[str], figure: Optional[str], item: Optional[str]) -> Tuple[str, str]:
    q = question or ""
    fig = _safe_str(figure).strip() if figure else ""
    itm = _safe_str(item).strip() if item else ""
    if not fig:
        m = FIGURE_RE.search(q)
        fig = m.group(1) if m else ""
    if not itm:
        m = ITEM_RE.search(q)
        itm = m.group(1) if m else ""
    if not fig or not itm:
        raise FigureItemFastAnswerComposerError("figure and item are required, either as args or parseable from question")
    return fig.upper(), itm.upper()


def _leading_zero_flexible(token: str) -> str:
    token = re.escape(token.upper())
    if token.isdigit():
        return r"0*" + token
    return token


def _figure_matches(text: str, figure: str) -> bool:
    t = text.upper()
    f = _leading_zero_flexible(figure)
    patterns = [
        rf"\b(?:FIG(?:URE)?\.?|ASSY)\s*{f}\b",
        rf"\b{f}\s*[-–—]\s*\|",  # OCR table row such as "85 - |"
        rf"\b25-\d{{2}}-\d{{2}}-{f}\b",
    ]
    return any(re.search(p, t, re.IGNORECASE) for p in patterns)


def _item_matches(text: str, item: str) -> bool:
    t = text.upper()
    i = _leading_zero_flexible(item.lstrip("-"))
    item_raw = re.escape(item.upper())
    patterns = [
        rf"\bITEM\s*{item_raw}\b",
        rf"\b(?:REF\s+)?{i}\s*\|\s*\d{{3}}-\d{{5}}-\d{{3}}\b",
        rf"\b-{i}\s*\|\s*\d{{3}}-\d{{5}}-\d{{3}}\b",
    ]
    return any(re.search(p, t, re.IGNORECASE) for p in patterns)


def _extract_item_part_and_description(text: str, item: str) -> Tuple[str, str]:
    item_num = item.lstrip("-")
    # Prefer the part number immediately following the target item marker.
    part = ""
    desc = ""
    item_patterns = [
        rf"\b(?:REF\s+)?0*{re.escape(item_num)}\s*\|\s*({PART_RE.pattern[2:-2]})\s*[\.\-–—|]*\s*([^|]{{0,100}})",
        rf"\b-{re.escape(item_num)}\s*\|\s*({PART_RE.pattern[2:-2]})\s*[\.\-–—|]*\s*([^|]{{0,100}})",
    ]
    for pattern in item_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            part = m.group(1)
            desc = m.group(2)
            break
    if not part:
        parts = PART_RE.findall(text)
        part = parts[0] if parts else ""
    if not desc and part:
        m = re.search(re.escape(part) + r"\s*[\.\-–—|]*\s*([^|]{0,100})", text, re.IGNORECASE)
        if m:
            desc = m.group(1)
    desc = re.sub(r"\s+", " ", desc)
    desc = re.sub(r"\.{2,}.*$", "", desc)
    desc = re.sub(r"\s+VS\d.*$", "", desc, flags=re.IGNORECASE)
    desc = desc.strip(" .;:,|-/")
    if desc:
        desc = desc.upper()
    return part, desc


def _score_record(record: Dict[str, Any], figure: str, item: str) -> int:
    text = _excerpt(record)
    if not text:
        return 0
    score = 0
    if _figure_matches(text, figure):
        score += 50
    if _item_matches(text, item):
        score += 50
    role = record.get("anchor_aware_role") or ""
    proof = record.get("proof_strength") or ""
    if role == "direct_exact_match_anchor":
        score += 10
    if proof == "direct_exact_proof":
        score += 10
    if PART_RE.search(text):
        score += 5
    return score


def _find_matches(records: Sequence[Dict[str, Any]], figure: str, item: str, max_records: int) -> List[Dict[str, Any]]:
    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, record in enumerate(records):
        score = _score_record(record, figure, item)
        if score >= 100:  # figure and item both matched
            scored.append((score, idx, record))
    scored.sort(key=lambda x: (-x[0], x[1]))
    matches: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for score, _idx, record in scored:
        key = _label(record) + "|" + _page(record)
        if key in seen:
            continue
        seen.add(key)
        clone = dict(record)
        clone["figure_item_match_score"] = score
        clone["figure_item_part_number"], clone["figure_item_description"] = _extract_item_part_and_description(_excerpt(record), item)
        clone["composer_role"] = "figure_item_answer_evidence"
        matches.append(clone)
        if len(matches) >= max_records:
            break
    return matches


def _valid_context_labels(records: Sequence[Dict[str, Any]]) -> set[str]:
    return {_label(r) for r in records if _label(r) != "E?"}


def _answer_citations(answer: str) -> List[str]:
    return re.findall(r"\[(E\d+)\]", answer)


def _make_answer(question: str, figure: str, item: str, matches: Sequence[Dict[str, Any]]) -> str:
    if not matches:
        return (
            f"TRACE-Net recognized a figure/item request for figure {figure} item {item}, "
            "but no cited cached context record matched both the figure and item.\n\n"
            "Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true."
        )
    best = matches[0]
    part = best.get("figure_item_part_number") or "part number not extracted"
    desc = best.get("figure_item_description") or "description not extracted"
    label = _label(best)
    page = _page(best)
    answer = [
        f"TRACE-Net found figure {figure} item {item} in the cached context: it is listed as part number {part}, \u201c{desc}\u201d, on page {page} {_cit(label)}.",
        f"This answer uses the cited figure/item row only; nearby graph or Leiden evidence is not treated as proof for any additional claim {_cit(label)}.",
        f"Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true {_cit(label)}.",
    ]
    return "\n\n".join(answer)


def _write_records_csv(path: str | Path, records: Sequence[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "citation_label", "composer_role", "anchor_aware_role", "proof_strength", "anchor_relation_type",
        "page_number", "page_id", "figure_item_match_score", "figure_item_part_number", "figure_item_description",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({k: record.get(k) for k in fieldnames})


def build_figure_item_fast_answer_composer(
    *,
    context_pack: str | Path,
    output_dir: str | Path,
    question: str,
    figure: Optional[str] = None,
    item: Optional[str] = None,
    max_records: int = 5,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    context_payload = _read_json(context_pack)
    context_summary = context_payload.get("summary") or {}
    source_quality = _source_quality_status(context_payload)
    if require_source_quality_pass and source_quality != "PASS":
        raise FigureItemFastAnswerComposerError(f"source context quality is {source_quality}, expected PASS")
    fig, itm = _parse_figure_item(question, figure, item)
    source_records = context_payload.get("records") or []
    matches = _find_matches(source_records, fig, itm, max_records=max_records)
    answer_text = _make_answer(question, fig, itm, matches)
    valid_labels = _valid_context_labels(source_records)
    citations = _answer_citations(answer_text)
    invalid = [c for c in citations if c not in valid_labels]

    violations: List[Dict[str, Any]] = []
    if not matches:
        violations.append({"severity": "high", "code": "no_figure_item_match", "message": f"No cached context record matched figure {fig} item {itm}."})
    if invalid:
        violations.append({"severity": "high", "code": "invalid_citation", "message": "Answer contains citation labels not present in context.", "labels": invalid})
    if matches and not citations:
        violations.append({"severity": "critical", "code": "missing_citation", "message": "Figure/item answer did not cite evidence."})

    summary = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "figure": fig,
        "item": itm,
        "source_context_pack": str(context_pack),
        "source_context_module": context_summary.get("module") or context_payload.get("module"),
        "source_context_quality_status": source_quality,
        "source_record_count": len(source_records),
        "composer_record_count": len(matches),
        "figure_item_answer_record_count": len(matches),
        "figure_item_answer_page_numbers": _unique([_page(r) for r in matches]),
        "figure_item_answer_page_count": len(_unique([_page(r) for r in matches])),
        "figure_item_answer_citation_count": len(citations),
        "valid_answer_citation_count": len([c for c in citations if c in valid_labels]),
        "invalid_answer_citation_count": len(invalid),
        "invalid_answer_citation_labels": invalid,
        "figure_item_part_numbers": _unique([_safe_str(r.get("figure_item_part_number")) for r in matches if r.get("figure_item_part_number")]),
        "figure_item_description_count": len(_unique([_safe_str(r.get("figure_item_description")) for r in matches if r.get("figure_item_description")])),
        "answer_char_count": len(answer_text),
        "answer_citation_count": len(citations),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "dry_run_only": True,
        "figure_item_fast_answer_ready": bool(matches) and not invalid,
        "ready_for_fast_chat_runner": bool(matches) and not invalid,
        "violation_record_count": len(violations),
        "violation_severity_counts": {s: sum(1 for v in violations if v.get("severity") == s) for s in sorted({v.get("severity") for v in violations})},
    }
    quality_status = "PASS" if summary["figure_item_fast_answer_ready"] and not violations else "FAIL"
    payload = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "answer_text": answer_text,
        "records": matches,
        "violations": violations,
    }
    _write_json(out_dir / f"{MODULE}.json", payload)
    _write_json(out_dir / f"{MODULE}_summary.json", summary)
    _write_text(out_dir / f"{MODULE}_answer.md", answer_text)
    _write_records_csv(out_dir / f"{MODULE}_records.csv", matches)
    _write_text(out_dir / f"{MODULE}.md", "# TRACE-Net Figure/Item Fast Answer Composer v1\n\n" + answer_text + "\n")
    if quality:
        quality_payload = check_figure_item_fast_answer_composer_quality(report_path=out_dir / f"{MODULE}.json")
        _write_json(out_dir / f"{MODULE}_quality_check.json", quality_payload)
        print(f"Wrote: {out_dir / f'{MODULE}_quality_check.json'}")
    print("Status: TRACE_NET_FIGURE_ITEM_FAST_ANSWER_COMPOSER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_figure_item_fast_answer_composer_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_citations: int = 1,
    min_valid_citations: int = 1,
    max_invalid_citations: int = 0,
    max_violations: int = 0,
    require_source_quality_pass: bool = False,
    require_figure_item_answer_ready: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def _num(key: str) -> int:
        try:
            return int(summary.get(key, 0) or 0)
        except Exception:
            return 0

    if payload.get("quality_status") != "PASS":
        failures.append("report quality_status is not PASS")
    if _num("figure_item_answer_record_count") < min_records:
        failures.append(f"figure_item_answer_record_count below {min_records}")
    if _num("answer_citation_count") < min_citations:
        failures.append(f"answer_citation_count below {min_citations}")
    if _num("valid_answer_citation_count") < min_valid_citations:
        failures.append(f"valid_answer_citation_count below {min_valid_citations}")
    if _num("invalid_answer_citation_count") > max_invalid_citations:
        failures.append(f"invalid_answer_citation_count above {max_invalid_citations}")
    if _num("violation_record_count") > max_violations:
        failures.append(f"violation_record_count above {max_violations}")
    if require_source_quality_pass and summary.get("source_context_quality_status") != "PASS":
        failures.append("source context quality did not PASS")
    if require_figure_item_answer_ready and not summary.get("figure_item_fast_answer_ready"):
        failures.append("figure_item_fast_answer_ready is not true")
    if require_no_human_review_required and (_num("human_review_required_count") or _num("manual_review_required_count")):
        failures.append("human/manual review required count is nonzero")
    if max_unsafe is not None and _num("unsafe_record_count") > max_unsafe:
        failures.append(f"unsafe_record_count above {max_unsafe}")
    if require_no_answer_permission and _num("answer_permission_count") != 0:
        failures.append("answer_permission_count is nonzero")
    if require_no_source_truth_mutation and _num("source_truth_mutation_allowed_count") != 0:
        failures.append("source_truth_mutation_allowed_count is nonzero")
    if require_no_write_attempts and _num("write_attempt_count") != 0:
        failures.append("write_attempt_count is nonzero")

    result = {
        "module": f"{MODULE}_quality_check",
        "version": VERSION,
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "failures": failures,
    }
    if write_json:
        path = Path(report_path)
        _write_json(path.with_name(f"{MODULE}_quality_check.json"), result)
        print(f"Wrote: {path.with_name(f'{MODULE}_quality_check.json')}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures))
    return result


def main_build() -> None:
    parser = argparse.ArgumentParser(description="Build a fast cited answer for TRACE-Net figure/item questions.")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--figure")
    parser.add_argument("--item")
    parser.add_argument("--max-records", type=int, default=5)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    return build_figure_item_fast_answer_composer(**vars(args))


def main_check() -> None:
    parser = argparse.ArgumentParser(description="Check TRACE-Net figure/item fast answer quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-valid-citations", type=int, default=1)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-violations", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-figure-item-answer-ready", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()
    return check_figure_item_fast_answer_composer_quality(**vars(args))


if __name__ == "__main__":
    main_build()
