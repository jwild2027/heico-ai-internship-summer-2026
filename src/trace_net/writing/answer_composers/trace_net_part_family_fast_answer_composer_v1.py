from __future__ import annotations

import argparse
import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_part_family_fast_answer_composer_v1"
VERSION = "v1"
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FAMILY_RE = re.compile(r"\b\d{3}-\d{5}\b")


class PartFamilyFastAnswerComposerError(RuntimeError):
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


def _parse_family(question: Optional[str], family: Optional[str]) -> str:
    fam = _safe_str(family).strip() if family else ""
    if not fam:
        m = FAMILY_RE.search(question or "")
        fam = m.group(0) if m else ""
    if not fam:
        raise PartFamilyFastAnswerComposerError("part family is required, either as --part-family or parseable from question")
    return fam


def _family_parts_from_record(record: Dict[str, Any], family: str) -> List[str]:
    text = _excerpt(record)
    # Include JSON record text as a fallback because some exact/reference records carry short values.
    if len(text) < 10:
        text += " " + json.dumps(record, ensure_ascii=False)
    return [p for p in _unique(PART_RE.findall(text)) if p.startswith(family + "-")]


def _score_record(record: Dict[str, Any], family: str) -> int:
    parts = _family_parts_from_record(record, family)
    if not parts:
        return 0
    score = 25 + len(parts)
    role = _safe_str(record.get("anchor_aware_role"))
    relation = _safe_str(record.get("anchor_relation_type"))
    proof = _safe_str(record.get("proof_strength"))
    same_anchor = record.get("same_anchor_leiden_community_ids") or record.get("same_anchor_leiden_community") or []
    if role == "direct_exact_match_anchor" or proof == "direct_exact_proof":
        score += 50
    if role in {"same_anchor_community_variant", "family_variant_anchor"} or relation in {"part_family_variant", "same_anchor_leiden_community_variant"}:
        score += 35
    if same_anchor:
        score += 10
    if proof == "related_variant":
        score += 10
    return score


def _find_family_records(records: Sequence[Dict[str, Any]], family: str, max_records: int) -> List[Dict[str, Any]]:
    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, record in enumerate(records):
        score = _score_record(record, family)
        if score <= 0:
            continue
        scored.append((score, idx, record))
    scored.sort(key=lambda x: (-x[0], x[1]))

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for score, _idx, record in scored:
        key = _label(record) + "|" + _page(record) + "|" + ",".join(_family_parts_from_record(record, family))
        if key in seen:
            continue
        seen.add(key)
        clone = dict(record)
        clone["part_family_match_score"] = score
        clone["matched_family_parts"] = _family_parts_from_record(record, family)
        clone["composer_role"] = _family_composer_role(clone)
        out.append(clone)
        if len(out) >= max_records:
            break
    return out


def _family_composer_role(record: Dict[str, Any]) -> str:
    role = _safe_str(record.get("anchor_aware_role"))
    proof = _safe_str(record.get("proof_strength"))
    relation = _safe_str(record.get("anchor_relation_type"))
    if role == "direct_exact_match_anchor" or proof == "direct_exact_proof":
        return "part_family_direct_anchor"
    if role in {"same_anchor_community_variant", "family_variant_anchor"} or relation in {"part_family_variant", "same_anchor_leiden_community_variant"}:
        return "part_family_variant_evidence"
    return "part_family_related_context"


def _valid_context_labels(records: Sequence[Dict[str, Any]]) -> set[str]:
    return {_label(r) for r in records if _label(r) != "E?"}


def _answer_citations(answer: str) -> List[str]:
    return re.findall(r"\[(E\d+)\]", answer)


def _part_label_map(records: Sequence[Dict[str, Any]], family: str) -> "OrderedDict[str, List[str]]":
    part_map: "OrderedDict[str, List[str]]" = OrderedDict()
    for record in records:
        for part in _family_parts_from_record(record, family):
            labels = part_map.setdefault(part, [])
            lab = _label(record)
            if lab not in labels:
                labels.append(lab)
    return part_map


def _page_refs(records: Sequence[Dict[str, Any]], limit: int = 8) -> List[str]:
    refs: List[str] = []
    seen: set[str] = set()
    for record in records:
        key = f"{_page(record)}|{_label(record)}"
        if key in seen:
            continue
        seen.add(key)
        refs.append(f"page {_page(record)} {_cit(_label(record))}")
        if len(refs) >= limit:
            break
    return refs


def _make_answer(family: str, records: Sequence[Dict[str, Any]], max_labels_per_part: int) -> str:
    if not records:
        return (
            f"TRACE-Net recognized a part-family request for {family}, but no cited cached context record contained that family.\n\n"
            "Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true."
        )

    direct = [r for r in records if r.get("composer_role") == "part_family_direct_anchor"]
    variants = [r for r in records if r.get("composer_role") == "part_family_variant_evidence"]
    related = [r for r in records if r.get("composer_role") == "part_family_related_context"]
    part_map = _part_label_map(records, family)
    parts = list(part_map.keys())

    direct_parts = _part_label_map(direct, family)
    variant_parts = OrderedDict((p, labels) for p, labels in part_map.items() if p not in direct_parts)

    answer: List[str] = []
    if direct_parts:
        bits = []
        for part, labels in direct_parts.items():
            bits.append(f"{part} ({', '.join(_cit(x) for x in labels[:max_labels_per_part])})")
        answer.append(
            f"TRACE-Net found the {family} part family in cached context. Direct anchor evidence includes "
            + "; ".join(bits)
            + "."
        )
    else:
        answer.append(
            f"TRACE-Net found the {family} part family in cached context; no direct exact anchor record was present, so the listed records are treated as related family evidence."
        )

    if variant_parts:
        bits = []
        for part, labels in variant_parts.items():
            bits.append(f"{part} ({', '.join(_cit(x) for x in labels[:max_labels_per_part])})")
        answer.append("Related family variants in the provided context include " + "; ".join(bits) + ".")

    direct_pages = _page_refs(direct, limit=8)
    if direct_pages:
        answer.append("Direct family anchor pages include " + ", ".join(direct_pages) + ".")

    if variants:
        answer.append(
            "Leiden/community-linked and part-prefix evidence are used only to group nearby family records; cited source rows remain the proof for each listed part."
        )
    elif related:
        answer.append("Related context is retained as support only and is not used as direct proof for unlisted parts.")

    proof_labels = _unique([_label(r) for r in (direct or records)[:8]])
    if proof_labels:
        answer.append(
            f"Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true "
            + ", ".join(_cit(x) for x in proof_labels)
            + "."
        )
    else:
        answer.append("Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n\n".join(answer)


def _write_records_csv(path: str | Path, records: Sequence[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "citation_label", "composer_role", "anchor_aware_role", "proof_strength", "anchor_relation_type",
        "page_number", "page_id", "part_family_match_score", "matched_family_parts",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {k: record.get(k) for k in fieldnames}
            if isinstance(row.get("matched_family_parts"), list):
                row["matched_family_parts"] = ";".join(row["matched_family_parts"])
            writer.writerow(row)


def build_part_family_fast_answer_composer(
    *,
    context_pack: str | Path,
    output_dir: str | Path,
    question: str,
    part_family: Optional[str] = None,
    max_records: int = 24,
    max_labels_per_part: int = 3,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    context_payload = _read_json(context_pack)
    context_summary = context_payload.get("summary") or {}
    source_quality = _source_quality_status(context_payload)
    if require_source_quality_pass and source_quality != "PASS":
        raise PartFamilyFastAnswerComposerError(f"source context quality is {source_quality}, expected PASS")
    family = _parse_family(question, part_family)
    source_records = context_payload.get("records") or []
    matches = _find_family_records(source_records, family, max_records=max_records)
    answer_text = _make_answer(family, matches, max_labels_per_part=max_labels_per_part)
    valid_labels = _valid_context_labels(source_records)
    citations = _answer_citations(answer_text)
    invalid = [c for c in citations if c not in valid_labels]
    family_part_map = _part_label_map(matches, family)
    direct_records = [r for r in matches if r.get("composer_role") == "part_family_direct_anchor"]
    variant_records = [r for r in matches if r.get("composer_role") == "part_family_variant_evidence"]
    leiden_records = [r for r in matches if r.get("same_anchor_leiden_community_ids") or r.get("leiden_community_ids")]

    violations: List[Dict[str, Any]] = []
    if not matches:
        violations.append({"severity": "high", "code": "no_part_family_match", "message": f"No cached context record matched part family {family}."})
    if invalid:
        violations.append({"severity": "high", "code": "invalid_citation", "message": "Answer contains citation labels not present in context.", "labels": invalid})
    if matches and not citations:
        violations.append({"severity": "critical", "code": "missing_citation", "message": "Part family answer did not cite evidence."})

    summary = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "part_family": family,
        "source_context_pack": str(context_pack),
        "source_context_module": context_summary.get("module") or context_payload.get("module"),
        "source_context_quality_status": source_quality,
        "source_record_count": len(source_records),
        "composer_record_count": len(matches),
        "part_family_answer_record_count": len(matches),
        "part_family_direct_record_count": len(direct_records),
        "part_family_variant_record_count": len(variant_records),
        "part_family_leiden_context_record_count": len(leiden_records),
        "part_family_page_numbers": _unique([_page(r) for r in matches]),
        "part_family_page_count": len(_unique([_page(r) for r in matches])),
        "part_family_part_numbers": list(family_part_map.keys()),
        "part_family_part_number_count": len(family_part_map),
        "answer_char_count": len(answer_text),
        "answer_citation_count": len(citations),
        "valid_answer_citation_count": len([c for c in citations if c in valid_labels]),
        "invalid_answer_citation_count": len(invalid),
        "invalid_answer_citation_labels": invalid,
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
        "part_family_fast_answer_ready": bool(matches) and not invalid,
        "ready_for_fast_chat_runner": bool(matches) and not invalid,
        "violation_record_count": len(violations),
        "violation_severity_counts": {s: sum(1 for v in violations if v.get("severity") == s) for s in sorted({v.get("severity") for v in violations})},
    }
    quality_status = "PASS" if summary["part_family_fast_answer_ready"] and not violations else "FAIL"
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
    _write_text(out_dir / f"{MODULE}.md", "# TRACE-Net Part Family Fast Answer Composer v1\n\n" + answer_text + "\n")
    if quality:
        quality_payload = check_part_family_fast_answer_composer_quality(report_path=out_dir / f"{MODULE}.json")
        _write_json(out_dir / f"{MODULE}_quality_check.json", quality_payload)
        print(f"Wrote: {out_dir / f'{MODULE}_quality_check.json'}")
    print("Status: TRACE_NET_PART_FAMILY_FAST_ANSWER_COMPOSER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_part_family_fast_answer_composer_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_citations: int = 1,
    min_valid_citations: int = 1,
    min_family_part_numbers: int = 1,
    max_invalid_citations: int = 0,
    max_violations: int = 0,
    require_source_quality_pass: bool = False,
    require_part_family_answer_ready: bool = False,
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
    if _num("part_family_answer_record_count") < min_records:
        failures.append(f"part_family_answer_record_count below {min_records}")
    if _num("answer_citation_count") < min_citations:
        failures.append(f"answer_citation_count below {min_citations}")
    if _num("valid_answer_citation_count") < min_valid_citations:
        failures.append(f"valid_answer_citation_count below {min_valid_citations}")
    if _num("part_family_part_number_count") < min_family_part_numbers:
        failures.append(f"part_family_part_number_count below {min_family_part_numbers}")
    if _num("invalid_answer_citation_count") > max_invalid_citations:
        failures.append(f"invalid_answer_citation_count above {max_invalid_citations}")
    if _num("violation_record_count") > max_violations:
        failures.append(f"violation_record_count above {max_violations}")
    if require_source_quality_pass and summary.get("source_context_quality_status") != "PASS":
        failures.append("source context quality did not PASS")
    if require_part_family_answer_ready and not summary.get("part_family_fast_answer_ready"):
        failures.append("part_family_fast_answer_ready is not true")
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
    parser = argparse.ArgumentParser(description="Build a fast cited answer for TRACE-Net part-family questions.")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--part-family")
    parser.add_argument("--max-records", type=int, default=24)
    parser.add_argument("--max-labels-per-part", type=int, default=3)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    return build_part_family_fast_answer_composer(
        context_pack=args.context_pack,
        output_dir=args.output_dir,
        question=args.question,
        part_family=args.part_family,
        max_records=args.max_records,
        max_labels_per_part=args.max_labels_per_part,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check() -> None:
    parser = argparse.ArgumentParser(description="Check TRACE-Net part-family fast answer composer quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-valid-citations", type=int, default=1)
    parser.add_argument("--min-family-part-numbers", type=int, default=1)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-violations", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-part-family-answer-ready", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()
    return check_part_family_fast_answer_composer_quality(**vars(args))


if __name__ == "__main__":
    main_build()
