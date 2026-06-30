
"""TRACE-Net raw OCR nomenclature window extractor v1.

This module enriches linked image/visual evidence with part nomenclature extracted from
raw OCR scan-pack text windows. It is deliberately read-only and retrieval-only:
LLaVA sees, OCR text supplies the candidate nomenclature, TRACE-Net keeps final answer
permission disabled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS = "TRACE_NET_RAW_OCR_NOMENCLATURE_WINDOW_EXTRACTOR_BUILT"
CHECK_STATUS = "TRACE_NET_RAW_OCR_NOMENCLATURE_WINDOW_EXTRACTOR_QUALITY_CHECKED"
MODULE = "trace_net_raw_ocr_nomenclature_window_extractor_v1"
SCHEMA_VERSION = "trace_net_raw_ocr_nomenclature_window_extractor_v1"
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
NOISE_WORDS = {
    "VS4956", "REF", "ASSY", "PER", "FROM", "TO", "AIRLINE", "EFF", "UNITS", "STOCK",
    "NUMBER", "FIG", "ITEM", "PARTNUMBER", "PART", "EFFECTIVITY", "PAGE",
}
BAD_VALUE_RE = re.compile(r"^(?:true|false|none|null|yes|no|ref|vs\d+|\d+|[-+]?\d+(?:\.\d+)?)$", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_path(p: Any) -> Path:
    return p if isinstance(p, Path) else Path(str(p))


def _load_json(path: Any) -> Any:
    p = _as_path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = _as_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    p = _as_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def _norm_space(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("\u00a0", " ")).strip()


def _normalize_nomenclature(value: str) -> str:
    s = _norm_space(value)
    # Remove OCR dotted leaders and repeated filler punctuation while preserving commas/slashes.
    s = re.sub(r"[.·]{2,}.*$", "", s)
    s = re.sub(r"\s+\.\s*", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    # Remove common right-side stock/effectivity/qty tails.
    s = re.split(r"\bVS\d+\b|\bE\d{4,}\b|\bREF\b|\b[A-Z]\s+REF\b", s, maxsplit=1, flags=re.I)[0]
    # Remove obvious OCR junk following a valid name.
    s = re.sub(r"\b(?:cc+|ee+|oo+|nn+|ss+|tt+)[A-Za-z]*\b.*$", "", s, flags=re.I)
    s = s.strip(" -|_/.,;:()[]{}")
    s = _norm_space(s)
    # Canonicalize common all-caps OCR words.
    s = re.sub(r"\bASSY\b", "ASSY", s, flags=re.I)
    return s.upper() if s.isupper() or not any(c.islower() for c in s) else s


def _is_bad_nomenclature(value: str, part_number: str = "") -> bool:
    s = _norm_space(value)
    if not s:
        return True
    if part_number and part_number in s and len(s) <= len(part_number) + 3:
        return True
    if PART_RE.fullmatch(s):
        return True
    if BAD_VALUE_RE.fullmatch(s):
        return True
    if re.search(r"\.(?:tif|tiff|png|jpg|json|txt)$", s, flags=re.I):
        return True
    bad_phrases = [
        "TRACE-NET PAGE", "PART FAMILY COMMUNITY", "VISUAL PART / DIAGRAM REVIEW COMMUNITY",
        "TABLE + PARTS + DIAGRAM REVIEW COMMUNITY", "DUBLIN CORE", "COMMUNITY",
    ]
    if any(p in s.upper() for p in bad_phrases):
        return True
    # Reject strings with no letters.
    if not re.search(r"[A-Za-z]", s):
        return True
    # Reject nearly all stop/noise tokens.
    tokens = re.findall(r"[A-Za-z0-9/-]+", s.upper())
    if tokens and sum(t in NOISE_WORDS or PART_RE.fullmatch(t or "") is not None for t in tokens) >= max(1, len(tokens) - 1):
        return True
    return False


def _get_records(obj: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for k in ("records", "evidence_documents", "exact_search_documents", "page_records"):
        v = obj.get(k)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, Mapping)]
    return []


def _linked_visual_parts(image_visual_evidence_pack: Any) -> List[Dict[str, Any]]:
    data = _load_json(image_visual_evidence_pack)
    out: List[Dict[str, Any]] = []
    for r in _get_records(data):
        part = _norm_space(r.get("linked_part_number"))
        if not part or not PART_RE.fullmatch(part):
            continue
        if not bool(r.get("linked")):
            continue
        out.append({
            "source_visual_citation_label": r.get("citation_label") or r.get("source_visual_citation_label") or "",
            "source_visual_evidence_id": r.get("evidence_id") or "",
            "page_id": r.get("page_id") or "",
            "page_number": _safe_int(r.get("page_number")),
            "figure": _norm_space(r.get("figure")),
            "callout": _norm_space(r.get("callout")),
            "linked_part_number": part,
            "visual_link_confidence": r.get("link_confidence") or "",
            "visual_source_trace_ready": bool(r.get("source_trace_ready")),
        })
    # Deduplicate by part + visual citation.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in out:
        key = (r["linked_part_number"], r["source_visual_citation_label"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def _record_text(record: Mapping[str, Any], scan_pack_path: Path) -> str:
    path_value = record.get("ocr_text_path") or record.get("text_path") or ""
    if path_value:
        p = Path(path_value)
        if not p.is_absolute():
            # First try repo/current relative path, then relative to scan-pack parent.
            candidates = [p, scan_pack_path.parent / p]
        else:
            candidates = [p]
        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
    for key in ("ocr_sample_text", "ocr_text", "text", "page_text", "raw_text"):
        v = record.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _iter_ocr_records(paths: Sequence[Any]) -> Iterable[Tuple[Path, Mapping[str, Any], str]]:
    for path in paths:
        p = _as_path(path)
        if not p.exists():
            continue
        try:
            data = _load_json(p)
        except Exception:
            continue
        for r in _get_records(data):
            text = _record_text(r, p)
            if text:
                yield p, r, text


def _line_windows(text: str, part_number: str, context_lines: int = 2) -> List[Dict[str, Any]]:
    raw_lines = text.splitlines()
    lines = [ln.rstrip() for ln in raw_lines]
    windows = []
    for i, line in enumerate(lines):
        if part_number not in line:
            continue
        lo = max(0, i - context_lines)
        hi = min(len(lines), i + context_lines + 1)
        windows.append({
            "line_index": i,
            "line_text": _norm_space(line),
            "window_text": "\n".join(lines[lo:hi]).strip(),
        })
    return windows


def _extract_after_part(line: str, part_number: str) -> str:
    if part_number not in line:
        return ""
    after = line.split(part_number, 1)[1]
    # Trim left separators; preserve words immediately following the PN.
    after = re.sub(r"^[\s|:;,_/.-]+", "", after)
    # Sometimes figure/item columns precede part number and nomenclature follows until effectivity/qty.
    # Keep alphabetic words before dotted leaders or stock/effectivity values.
    after = re.split(r"\s{2,}|\.{2,}|\s+VS\d+\b|\s+E\d{4,}\b|\s+[A-Z]\s+REF\b|\s+REF\b", after, maxsplit=1, flags=re.I)[0]
    return _normalize_nomenclature(after)


def _extract_title_parenthetical(line: str, part_number: str) -> str:
    # e.g. Double Passenger Seat Structure (120-29068-003)
    m = re.search(r"(.{3,120}?)\s*\(\s*" + re.escape(part_number) + r"\s*\)", line, flags=re.I)
    if not m:
        return ""
    return _normalize_nomenclature(m.group(1))


def _candidate_from_window(window: Mapping[str, Any], part_number: str) -> List[Dict[str, Any]]:
    line = str(window.get("line_text") or "")
    window_text = str(window.get("window_text") or "")
    candidates: List[Dict[str, Any]] = []
    for extractor_name, extractor in (("same_line_after_part", _extract_after_part), ("parenthetical_title", _extract_title_parenthetical)):
        value = extractor(line, part_number)
        if not _is_bad_nomenclature(value, part_number):
            candidates.append({
                "nomenclature": value,
                "extraction_rule": extractor_name,
                "line_text": line,
                "window_text": window_text,
            })
    # If part spans/dirty line, inspect every window line for parenthetical title.
    for ln in window_text.splitlines():
        value = _extract_title_parenthetical(ln, part_number)
        if not _is_bad_nomenclature(value, part_number):
            candidates.append({
                "nomenclature": value,
                "extraction_rule": "window_parenthetical_title",
                "line_text": _norm_space(ln),
                "window_text": window_text,
            })
    # Deduplicate same text/rule.
    seen = set()
    deduped = []
    for c in candidates:
        key = (c["nomenclature"].upper(), c["extraction_rule"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


def _score_candidate(c: Mapping[str, Any], visual: Mapping[str, Any], ocr_page_number: Optional[int]) -> Tuple[int, str]:
    score = 0
    reasons = []
    rule = c.get("extraction_rule")
    if rule == "same_line_after_part":
        score += 50; reasons.append("same_line_after_part")
    elif "parenthetical" in str(rule):
        score += 45; reasons.append("parenthetical_title")
    line = str(c.get("line_text") or "")
    figure = str(visual.get("figure") or "")
    if figure and re.search(r"\b" + re.escape(figure) + r"\b", line):
        score += 20; reasons.append("figure_on_line")
    part = str(visual.get("linked_part_number") or "")
    if part and part in line:
        score += 15; reasons.append("part_on_line")
    vp = visual.get("page_number")
    if isinstance(vp, int) and isinstance(ocr_page_number, int):
        delta = abs(ocr_page_number - vp)
        if delta == 0:
            score += 15; reasons.append("same_page_number")
        elif delta <= 2:
            score += 10; reasons.append("near_visual_page")
    nom = str(c.get("nomenclature") or "")
    # Prefer names with known part-noun content; not mandatory.
    if re.search(r"\b(ASSY|STRUCTURE|SEAT|LEG|ARMREST|COVER|FITTING|BUSHING|WASHER|SCREW|NUT|BOLT)\b", nom, flags=re.I):
        score += 10; reasons.append("part_noun")
    return score, ";".join(reasons)


def build_extractor(
    *,
    image_visual_evidence_pack: Any,
    ocr_route_scan_pack: Sequence[Any],
    output_dir: Any,
    page_window: int = 3,
    context_lines: int = 2,
    min_linked_visual_parts: int = 1,
    min_nomenclature_selected: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    out = _as_path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    visuals = _linked_visual_parts(image_visual_evidence_pack)
    ocr_paths = [_as_path(p) for p in ocr_route_scan_pack]
    ocr_records = list(_iter_ocr_records(ocr_paths))
    records: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for visual in visuals:
        part = visual["linked_part_number"]
        vpage = visual.get("page_number")
        all_candidates: List[Dict[str, Any]] = []
        matched_ocr_count = 0
        for scan_path, ocr_rec, text in ocr_records:
            if part not in text:
                continue
            ocr_page = _safe_int(ocr_rec.get("canonical_page_number") or ocr_rec.get("page_number"))
            if isinstance(vpage, int) and isinstance(ocr_page, int) and abs(ocr_page - vpage) > page_window:
                # Still allow figure pages with parenthetical title? Not for v1; keep bounded.
                continue
            matched_ocr_count += 1
            windows = _line_windows(text, part, context_lines=context_lines)
            for w in windows:
                candidates = _candidate_from_window(w, part)
                for c in candidates:
                    score, reason = _score_candidate(c, visual, ocr_page)
                    c.update({
                        "score": score,
                        "score_reason": reason,
                        "ocr_scan_pack": str(scan_path),
                        "ocr_page_id": ocr_rec.get("page_id") or "",
                        "ocr_source_page_id": ocr_rec.get("source_page_id") or "",
                        "ocr_page_number": ocr_page,
                        "ocr_file_name": ocr_rec.get("file_name") or "",
                        "ocr_text_path": ocr_rec.get("ocr_text_path") or "",
                        "ocr_text_sha256": ocr_rec.get("ocr_text_sha256") or "",
                        "line_index": w.get("line_index"),
                    })
                    all_candidates.append(c)
                if not candidates:
                    rejected.append({
                        "linked_part_number": part,
                        "line_text": w.get("line_text"),
                        "reason": "no_valid_nomenclature_candidate_from_window",
                        "ocr_scan_pack": str(scan_path),
                        "ocr_page_number": ocr_page,
                    })

        all_candidates.sort(key=lambda c: (-int(c.get("score") or 0), len(str(c.get("nomenclature") or ""))))
        # Deduplicate candidates by nomenclature and page.
        unique_candidates: List[Dict[str, Any]] = []
        seen_nom = set()
        for c in all_candidates:
            key = (str(c.get("nomenclature") or "").upper(), c.get("ocr_page_id"), c.get("extraction_rule"))
            if key in seen_nom:
                continue
            seen_nom.add(key)
            unique_candidates.append(c)
        selected = unique_candidates[0] if unique_candidates else {}
        selected_name = str(selected.get("nomenclature") or "")
        confidence = "NONE"
        if selected_name:
            sc = int(selected.get("score") or 0)
            if sc >= 85:
                confidence = "HIGH"
            elif sc >= 65:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"
        source_trace_ready = bool(visual.get("visual_source_trace_ready")) and bool(selected_name) and bool(selected.get("ocr_page_id"))
        record_id = "raw_ocr_nomenclature_window_" + hashlib.sha256((part + str(visual.get("source_visual_citation_label"))).encode()).hexdigest()[:16]
        rec = {
            "record_id": record_id,
            "schema_version": SCHEMA_VERSION,
            "source_visual_citation_label": visual.get("source_visual_citation_label"),
            "source_visual_evidence_id": visual.get("source_visual_evidence_id"),
            "linked_part_number": part,
            "figure": visual.get("figure"),
            "callout": visual.get("callout"),
            "visual_page_id": visual.get("page_id"),
            "visual_page_number": visual.get("page_number"),
            "matched_ocr_record_count": matched_ocr_count,
            "nomenclature_candidate_count": len(unique_candidates),
            "selected_nomenclature": selected_name,
            "selected_nomenclature_confidence": confidence,
            "selected_extraction_rule": selected.get("extraction_rule") or "",
            "selected_score": selected.get("score") or 0,
            "selected_score_reason": selected.get("score_reason") or "",
            "selected_ocr_page_id": selected.get("ocr_page_id") or "",
            "selected_ocr_source_page_id": selected.get("ocr_source_page_id") or "",
            "selected_ocr_page_number": selected.get("ocr_page_number"),
            "selected_ocr_file_name": selected.get("ocr_file_name") or "",
            "selected_ocr_text_path": selected.get("ocr_text_path") or "",
            "selected_ocr_text_sha256": selected.get("ocr_text_sha256") or "",
            "selected_line_index": selected.get("line_index"),
            "selected_line_text": selected.get("line_text") or "",
            "selected_window_text": selected.get("window_text") or "",
            "nomenclature_candidates": unique_candidates[:10],
            "source_trace_ready": source_trace_ready,
            "citation_ready": source_trace_ready,
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt_count": 0,
            "unsafe": False,
            "limitations": [
                "Raw OCR nomenclature is a source-traced text extraction candidate, not standalone answer permission.",
                "This evidence does not prove interchangeability, effectivity, fit, replacement approval, or installation safety.",
            ],
        }
        records.append(rec)

    summary = {
        "linked_visual_part_count": len(visuals),
        "ocr_scan_pack_count": len(ocr_paths),
        "ocr_record_count": len(ocr_records),
        "nomenclature_window_record_count": len(records),
        "matched_ocr_record_count": sum(int(r.get("matched_ocr_record_count") or 0) for r in records),
        "nomenclature_candidate_count": sum(int(r.get("nomenclature_candidate_count") or 0) for r in records),
        "nomenclature_selected_count": sum(1 for r in records if r.get("selected_nomenclature")),
        "nomenclature_missing_count": sum(1 for r in records if not r.get("selected_nomenclature")),
        "high_confidence_count": sum(1 for r in records if r.get("selected_nomenclature_confidence") == "HIGH"),
        "medium_confidence_count": sum(1 for r in records if r.get("selected_nomenclature_confidence") == "MEDIUM"),
        "low_confidence_count": sum(1 for r in records if r.get("selected_nomenclature_confidence") == "LOW"),
        "source_trace_ready_count": sum(1 for r in records if r.get("source_trace_ready")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
        "opensearch_upload_attempt_count": sum(1 for r in records if r.get("opensearch_upload_attempt")),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
        "ready_for_visual_nomenclature_enrichment": True,
    }
    thresholds = {
        "min_linked_visual_parts": min_linked_visual_parts,
        "min_nomenclature_selected": min_nomenclature_selected,
        "min_source_trace_ready": min_source_trace_ready,
        "max_unsafe": max_unsafe,
        "max_answer_permission": max_answer_permission,
        "max_source_truth_mutation_allowed": max_source_truth_mutation_allowed,
        "max_write_attempts": max_write_attempts,
    }
    checks = [
        {"name": "min_linked_visual_parts", "observed": summary["linked_visual_part_count"], "expected": f">= {min_linked_visual_parts}", "passed": summary["linked_visual_part_count"] >= min_linked_visual_parts},
        {"name": "min_nomenclature_selected", "observed": summary["nomenclature_selected_count"], "expected": f">= {min_nomenclature_selected}", "passed": summary["nomenclature_selected_count"] >= min_nomenclature_selected},
        {"name": "min_source_trace_ready", "observed": summary["source_trace_ready_count"], "expected": f">= {min_source_trace_ready}", "passed": summary["source_trace_ready_count"] >= min_source_trace_ready},
        {"name": "max_unsafe", "observed": summary["unsafe_record_count"], "expected": f"<= {max_unsafe}", "passed": summary["unsafe_record_count"] <= max_unsafe},
        {"name": "max_answer_permission", "observed": summary["answer_permission_count"], "expected": f"<= {max_answer_permission}", "passed": summary["answer_permission_count"] <= max_answer_permission},
        {"name": "max_source_truth_mutation_allowed", "observed": summary["source_truth_mutation_allowed_count"], "expected": f"<= {max_source_truth_mutation_allowed}", "passed": summary["source_truth_mutation_allowed_count"] <= max_source_truth_mutation_allowed},
        {"name": "max_write_attempts", "observed": summary["write_attempt_count"], "expected": f"<= {max_write_attempts}", "passed": summary["write_attempt_count"] <= max_write_attempts},
    ]
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    paths = {
        "extractor": str(out / "trace_net_raw_ocr_nomenclature_window_extractor_v1.json"),
        "quality_check": str(out / "trace_net_raw_ocr_nomenclature_window_extractor_v1_quality_check.json"),
        "records_jsonl": str(out / "trace_net_raw_ocr_nomenclature_window_extractor_v1_records.jsonl"),
        "records_csv": str(out / "trace_net_raw_ocr_nomenclature_window_extractor_v1_records.csv"),
        "rejected_windows_jsonl": str(out / "trace_net_raw_ocr_nomenclature_window_extractor_v1_rejected_windows.jsonl"),
    }
    result = {
        "status": STATUS,
        "quality_status": quality_status,
        "module": MODULE,
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": _now(),
        "inputs": {
            "image_visual_evidence_pack": str(_as_path(image_visual_evidence_pack)),
            "ocr_route_scan_pack": [str(p) for p in ocr_paths],
        },
        "authority_model": {
            "ocr_role": "Raw OCR line/window supplies candidate nomenclature text.",
            "visual_role": "Image/visual evidence supplies linked part and figure anchor.",
            "safety_rule": "No answer permission and no source-truth mutation; extracted nomenclature is evidence for downstream gating only.",
        },
        "thresholds": thresholds,
        "checks": checks,
        "summary": summary,
        "records": records,
        "rejected_windows": rejected[:500],
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
        "paths": paths,
    }
    _write_json(paths["extractor"], result)
    _write_json(paths["quality_check"], {"status": CHECK_STATUS, "quality_status": quality_status, "checks": checks, "summary": summary})
    _write_jsonl(paths["records_jsonl"], records)
    _write_jsonl(paths["rejected_windows_jsonl"], rejected[:500])
    _write_csv(paths["records_csv"], records)
    return result


def _write_csv(path: Any, records: Sequence[Mapping[str, Any]]) -> None:
    p = _as_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_visual_citation_label", "linked_part_number", "figure", "visual_page_number",
        "selected_nomenclature", "selected_nomenclature_confidence", "selected_ocr_page_number",
        "selected_ocr_page_id", "selected_line_text", "source_trace_ready",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in fields})


def check_extractor(
    *,
    extractor: Any,
    output: Any = None,
    require_quality_pass: bool = False,
    min_linked_visual_parts: int = 1,
    min_nomenclature_selected: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(extractor)
    s = data.get("summary", {}) if isinstance(data, Mapping) else {}
    checks = [
        {"name": "quality_status", "observed": data.get("quality_status"), "expected": "PASS" if require_quality_pass else "any", "passed": (not require_quality_pass) or data.get("quality_status") == "PASS"},
        {"name": "min_linked_visual_parts", "observed": int(s.get("linked_visual_part_count") or 0), "expected": f">= {min_linked_visual_parts}", "passed": int(s.get("linked_visual_part_count") or 0) >= min_linked_visual_parts},
        {"name": "min_nomenclature_selected", "observed": int(s.get("nomenclature_selected_count") or 0), "expected": f">= {min_nomenclature_selected}", "passed": int(s.get("nomenclature_selected_count") or 0) >= min_nomenclature_selected},
        {"name": "min_source_trace_ready", "observed": int(s.get("source_trace_ready_count") or 0), "expected": f">= {min_source_trace_ready}", "passed": int(s.get("source_trace_ready_count") or 0) >= min_source_trace_ready},
        {"name": "max_unsafe", "observed": int(s.get("unsafe_record_count") or 0), "expected": f"<= {max_unsafe}", "passed": int(s.get("unsafe_record_count") or 0) <= max_unsafe},
        {"name": "max_answer_permission", "observed": int(s.get("answer_permission_count") or 0), "expected": f"<= {max_answer_permission}", "passed": int(s.get("answer_permission_count") or 0) <= max_answer_permission},
        {"name": "max_source_truth_mutation_allowed", "observed": int(s.get("source_truth_mutation_allowed_count") or 0), "expected": f"<= {max_source_truth_mutation_allowed}", "passed": int(s.get("source_truth_mutation_allowed_count") or 0) <= max_source_truth_mutation_allowed},
        {"name": "max_write_attempts", "observed": int(s.get("write_attempt_count") or 0), "expected": f"<= {max_write_attempts}", "passed": int(s.get("write_attempt_count") or 0) <= max_write_attempts},
    ]
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    result = {"status": CHECK_STATUS, "quality_status": quality_status, "checks": checks, "summary": s}
    if output:
        _write_json(output, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=MODULE)
    p.add_argument("--image-visual-evidence-pack", required=True)
    p.add_argument("--ocr-route-scan-pack", action="append", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--page-window", type=int, default=3)
    p.add_argument("--context-lines", type=int, default=2)
    p.add_argument("--min-linked-visual-parts", type=int, default=1)
    p.add_argument("--min-nomenclature-selected", type=int, default=1)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_extractor(
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        ocr_route_scan_pack=args.ocr_route_scan_pack,
        output_dir=args.output_dir,
        page_window=args.page_window,
        context_lines=args.context_lines,
        min_linked_visual_parts=args.min_linked_visual_parts,
        min_nomenclature_selected=args.min_nomenclature_selected,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    for k in ["linked_visual_part_count", "ocr_record_count", "matched_ocr_record_count", "nomenclature_candidate_count", "nomenclature_selected_count", "nomenclature_missing_count", "high_confidence_count", "medium_confidence_count", "source_trace_ready_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"]:
        print(f"{k}={s.get(k)}")
    print(f"extractor={result['paths']['extractor']}")
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
