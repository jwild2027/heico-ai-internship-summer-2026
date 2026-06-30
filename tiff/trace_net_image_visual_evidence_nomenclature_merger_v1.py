
"""TRACE-Net image visual evidence nomenclature merger v1.

Merges OCR-backed nomenclature windows into linked image visual evidence records.
This module is read-only with respect to source-truth stores: it writes only local
JSON/JSONL/CSV/report artifacts under the requested output directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

STATUS_BUILT = "TRACE_NET_IMAGE_VISUAL_EVIDENCE_NOMENCLATURE_MERGER_BUILT"
STATUS_CHECKED = "TRACE_NET_IMAGE_VISUAL_EVIDENCE_NOMENCLATURE_MERGER_QUALITY_CHECKED"
MODULE = "trace_net_image_visual_evidence_nomenclature_merger_v1"
SCHEMA_VERSION = "trace_net_image_visual_evidence_nomenclature_merger_v1"

BAD_NOMENCLATURE_VALUES = {
    "", "true", "false", "none", "null", "n/a", "na", "unknown",
}


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {p}")
    return data


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Any, records: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _stable_id(prefix: str, *parts: Any) -> str:
    blob = "|".join(str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:16]}"


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _canon(s: Any) -> str:
    return " ".join(str(s or "").strip().upper().replace(".", " ").split())


def _clean_nomenclature(value: Any) -> str:
    text = _norm(value)
    # Normalize common OCR filler following dotted leaders without removing meaningful words.
    text = text.replace("\u00a0", " ")
    text = " ".join(text.split())
    # Remove obvious OCR dotted-leader remnants at the end.
    for marker in ["..........", "........", "......", ".....", "....", "..."]:
        text = text.replace(marker, " ")
    text = " ".join(text.split())
    # Remove trailing OCR garbage token that came from dotted leaders in the observed corpus.
    # Example: "STRUCTURE ASSY 00" from "STRUCTURE ASSY 00...".
    if text.upper().endswith(" ASSY 00"):
        text = text[:-3].strip()
    # Remove trailing standalone numeric noise when the phrase already has strong noun content.
    parts = text.split()
    if len(parts) >= 3 and parts[-1].isdigit() and any(w.upper() in {"ASSY", "ASSEMBLY", "STRUCTURE", "SEAT"} for w in parts[:-1]):
        text = " ".join(parts[:-1]).strip()
    return text


def _valid_nomenclature(value: Any) -> bool:
    text = _clean_nomenclature(value)
    low = text.lower()
    if low in BAD_NOMENCLATURE_VALUES:
        return False
    if len(text) < 4:
        return False
    if any(ch.isdigit() for ch in text) and not any(ch.isalpha() for ch in text):
        return False
    if text.lower().startswith("trace-net page"):
        return False
    if "community" in low:
        return False
    if text.lower().endswith(('.tif', '.tiff', '.png', '.jpg', '.jpeg')):
        return False
    # Reject pure part-number-ish text.
    if text.count("-") >= 2 and sum(ch.isdigit() for ch in text) >= 6 and len([ch for ch in text if ch.isalpha()]) == 0:
        return False
    strong_words = {"ASSY", "ASSEMBLY", "STRUCTURE", "SEAT", "COVER", "LOCK", "ARMREST", "BUSHING", "WASHER", "NUT", "BOLT", "REINFORCEMENT", "PROTECTOR"}
    words = {w.strip(" ,.;:-()[]{}").upper() for w in text.split()}
    return bool(words & strong_words) or (len(text.split()) >= 2 and any(ch.isalpha() for ch in text))


def _truthy_false_count(records: Iterable[Mapping[str, Any]], field: str) -> int:
    return sum(1 for r in records if bool(r.get(field)))


def _key_from_record(record: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (_norm(record.get("source_visual_citation_label") or record.get("citation_label")), _norm(record.get("linked_part_number")), _norm(record.get("figure")))


def _index_ocr_records(extractor: Mapping[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in extractor.get("records", []) or []:
        if not isinstance(r, dict):
            continue
        nom = _clean_nomenclature(r.get("selected_nomenclature"))
        if not _valid_nomenclature(nom):
            continue
        if not bool(r.get("source_trace_ready")):
            continue
        if bool(r.get("answer_permission")) or bool(r.get("source_truth_mutation_allowed")) or bool(r.get("unsafe")):
            continue
        key = _key_from_record(r)
        if key[1] and key[2]:
            existing = out.get(key)
            if existing is None:
                out[key] = dict(r, selected_nomenclature=nom)
            else:
                # Prefer HIGH confidence, then shorter cleaned nomenclature when otherwise tied.
                rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
                cur = rank.get(_norm(existing.get("selected_nomenclature_confidence")).upper(), 0)
                new = rank.get(_norm(r.get("selected_nomenclature_confidence")).upper(), 0)
                if new > cur or (new == cur and len(nom) < len(_norm(existing.get("selected_nomenclature")))):
                    out[key] = dict(r, selected_nomenclature=nom)
    return out


def _find_match(record: Mapping[str, Any], index: Mapping[Tuple[str, str, str], Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    exact = (_norm(record.get("citation_label")), _norm(record.get("linked_part_number")), _norm(record.get("figure")))
    if exact in index:
        return index[exact]
    # Citation labels can change after re-packaging; fall back to part + figure unique match.
    part = _norm(record.get("linked_part_number"))
    fig = _norm(record.get("figure"))
    matches = [r for (citation, p, f), r in index.items() if p == part and f == fig]
    if len(matches) == 1:
        return matches[0]
    return None


def _merge_record(record: Mapping[str, Any], match: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    merged = dict(record)
    limitations = list(merged.get("limitations") or [])
    if match:
        nom = _clean_nomenclature(match.get("selected_nomenclature"))
        merged["linked_description"] = nom
        merged["linked_description_quality"] = "ocr_backed_high_confidence" if _norm(match.get("selected_nomenclature_confidence")).upper() == "HIGH" else "ocr_backed"
        merged["linked_nomenclature"] = nom
        merged["linked_nomenclature_source"] = "raw_ocr_nomenclature_window_extractor_v1"
        merged["linked_nomenclature_confidence"] = _norm(match.get("selected_nomenclature_confidence")) or "UNKNOWN"
        merged["linked_nomenclature_ocr_page_id"] = _norm(match.get("selected_ocr_page_id"))
        merged["linked_nomenclature_ocr_page_number"] = match.get("selected_ocr_page_number")
        merged["linked_nomenclature_line_text"] = _norm(match.get("selected_line_text"))
        merged["linked_nomenclature_rule"] = _norm(match.get("selected_extraction_rule"))
        merged["linked_nomenclature_source_trace"] = {
            "source_module": "trace_net_raw_ocr_nomenclature_window_extractor_v1",
            "source_record_id": match.get("nomenclature_window_record_id") or match.get("record_id") or "",
            "source_visual_citation_label": match.get("source_visual_citation_label") or merged.get("citation_label"),
            "linked_part_number": match.get("linked_part_number"),
            "figure": match.get("figure"),
            "ocr_page_id": match.get("selected_ocr_page_id"),
            "ocr_page_number": match.get("selected_ocr_page_number"),
            "ocr_text_path": match.get("selected_ocr_text_path") or match.get("ocr_text_path") or "",
            "selected_line_text": match.get("selected_line_text"),
        }
        # Replace the stale limitation if present.
        limitations = [l for l in limitations if "clean nomenclature/description is not available" not in str(l)]
        upgrade_note = "OCR-backed nomenclature was found in raw OCR text near the linked figure/part evidence."
        if upgrade_note not in limitations:
            limitations.insert(0, upgrade_note)
        merged["limitations"] = limitations
        merged["nomenclature_merge_status"] = "merged"
    else:
        merged["nomenclature_merge_status"] = "missing_ocr_nomenclature"
        merged.setdefault("linked_nomenclature", "")
    merged["answer_permission"] = False
    merged["can_answer_directly"] = False
    merged["can_prove_claims"] = False
    merged["source_truth_mutation_allowed"] = False
    merged["postgres_write_attempt"] = False
    merged["qdrant_write_attempt"] = False
    merged["opensearch_write_attempt"] = False
    merged["opensearch_upload_attempt"] = False
    merged["unsafe"] = False
    return merged


def build_merger(
    image_visual_evidence_pack: Any,
    raw_ocr_nomenclature_extractor: Any,
    output_dir: Any,
    min_visual_records: int = 1,
    min_nomenclature_merged: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    pack_path = Path(image_visual_evidence_pack)
    extractor_path = Path(raw_ocr_nomenclature_extractor)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pack = _load_json(pack_path)
    extractor = _load_json(extractor_path)
    records = [r for r in (pack.get("records") or []) if isinstance(r, dict)]
    index = _index_ocr_records(extractor)

    merged_records: List[Dict[str, Any]] = []
    merge_records: List[Dict[str, Any]] = []
    missing_records: List[Dict[str, Any]] = []

    for rec in records:
        match = None
        if bool(rec.get("linked")) and _norm(rec.get("linked_part_number")):
            match = _find_match(rec, index)
        merged = _merge_record(rec, match)
        merged_records.append(merged)
        if match:
            merge_records.append({
                "merge_record_id": _stable_id("image_visual_nomenclature_merge", rec.get("citation_label"), rec.get("linked_part_number"), rec.get("figure")),
                "citation_label": rec.get("citation_label"),
                "page_id": rec.get("page_id"),
                "page_number": rec.get("page_number"),
                "figure": rec.get("figure"),
                "linked_part_number": rec.get("linked_part_number"),
                "selected_nomenclature": merged.get("linked_nomenclature"),
                "nomenclature_confidence": merged.get("linked_nomenclature_confidence"),
                "ocr_page_id": merged.get("linked_nomenclature_ocr_page_id"),
                "ocr_page_number": merged.get("linked_nomenclature_ocr_page_number"),
                "selected_line_text": merged.get("linked_nomenclature_line_text"),
                "source_trace_ready": bool(merged.get("source_trace_ready")),
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "unsafe": False,
            })
        elif bool(rec.get("linked")) and _norm(rec.get("linked_part_number")):
            missing_records.append({
                "citation_label": rec.get("citation_label"),
                "page_id": rec.get("page_id"),
                "page_number": rec.get("page_number"),
                "figure": rec.get("figure"),
                "linked_part_number": rec.get("linked_part_number"),
                "reason": "no_matching_raw_ocr_nomenclature_record",
            })

    linked_visual_record_count = sum(1 for r in merged_records if bool(r.get("linked")) and _norm(r.get("linked_part_number")))
    nomenclature_merged_count = len(merge_records)
    high_confidence_count = sum(1 for r in merge_records if _norm(r.get("nomenclature_confidence")).upper() == "HIGH")
    source_trace_ready_count = sum(1 for r in merge_records if bool(r.get("source_trace_ready")))
    unsafe_count = _truthy_false_count(merged_records, "unsafe")
    answer_permission_count = _truthy_false_count(merged_records, "answer_permission")
    source_truth_mutation_allowed_count = _truthy_false_count(merged_records, "source_truth_mutation_allowed")
    write_attempt_count = sum(1 for r in merged_records if any(bool(r.get(k)) for k in ["postgres_write_attempt", "qdrant_write_attempt", "opensearch_write_attempt", "opensearch_upload_attempt"]))

    summary = {
        "visual_record_count": len(merged_records),
        "linked_visual_record_count": linked_visual_record_count,
        "raw_ocr_nomenclature_record_count": len(extractor.get("records") or []),
        "nomenclature_merged_count": nomenclature_merged_count,
        "nomenclature_missing_count": len(missing_records),
        "high_confidence_nomenclature_count": high_confidence_count,
        "source_trace_ready_count": source_trace_ready_count,
        "ready_for_visual_answer_upgrade": nomenclature_merged_count >= min_nomenclature_merged,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": sum(1 for r in merged_records if bool(r.get("postgres_write_attempt"))),
        "qdrant_write_attempt_count": sum(1 for r in merged_records if bool(r.get("qdrant_write_attempt"))),
        "opensearch_write_attempt_count": sum(1 for r in merged_records if bool(r.get("opensearch_write_attempt"))),
        "opensearch_upload_attempt_count": sum(1 for r in merged_records if bool(r.get("opensearch_upload_attempt"))),
        "write_attempt_count": write_attempt_count,
        "unsafe_record_count": unsafe_count,
    }

    checks = []
    def add_check(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add_check("min_visual_records", len(merged_records), f">= {min_visual_records}", len(merged_records) >= min_visual_records)
    add_check("min_nomenclature_merged", nomenclature_merged_count, f">= {min_nomenclature_merged}", nomenclature_merged_count >= min_nomenclature_merged)
    add_check("min_source_trace_ready", source_trace_ready_count, f">= {min_source_trace_ready}", source_trace_ready_count >= min_source_trace_ready)
    add_check("max_unsafe", unsafe_count, f"<= {max_unsafe}", unsafe_count <= max_unsafe)
    add_check("max_answer_permission", answer_permission_count, f"<= {max_answer_permission}", answer_permission_count <= max_answer_permission)
    add_check("max_source_truth_mutation_allowed", source_truth_mutation_allowed_count, f"<= {max_source_truth_mutation_allowed}", source_truth_mutation_allowed_count <= max_source_truth_mutation_allowed)
    add_check("max_write_attempts", write_attempt_count, f"<= {max_write_attempts}", write_attempt_count <= max_write_attempts)
    add_check("source_pack_quality_pass", pack.get("quality_status"), "PASS", pack.get("quality_status") == "PASS")
    add_check("source_extractor_quality_pass", extractor.get("quality_status"), "PASS", extractor.get("quality_status") == "PASS")

    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"

    merged_pack = dict(pack)
    merged_pack["records"] = merged_records
    merged_pack["quality_status"] = quality_status
    merged_pack["status"] = STATUS_BUILT
    merged_pack["module"] = MODULE
    merged_pack["schema_version"] = SCHEMA_VERSION
    merged_pack["source_image_visual_evidence_pack"] = str(pack_path)
    merged_pack["source_raw_ocr_nomenclature_extractor"] = str(extractor_path)
    merged_pack["summary"] = summary
    merged_pack["checks"] = checks
    merged_pack["safety_contract"] = {
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
        "writes_only_local_artifacts": True,
    }
    merged_pack["paths"] = dict(merged_pack.get("paths") or {})

    main_path = out_dir / "trace_net_image_visual_evidence_nomenclature_merger_v1.json"
    pack_path_out = out_dir / "trace_net_image_visual_evidence_pack_with_nomenclature_v1.json"
    records_jsonl = out_dir / "trace_net_image_visual_evidence_nomenclature_merger_v1_records.jsonl"
    missing_jsonl = out_dir / "trace_net_image_visual_evidence_nomenclature_merger_v1_missing.jsonl"
    csv_path = out_dir / "trace_net_image_visual_evidence_nomenclature_merger_v1_records.csv"
    quality_path = out_dir / "trace_net_image_visual_evidence_nomenclature_merger_v1_quality_check.json"

    artifact = {
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "module": MODULE,
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "image_visual_evidence_pack": str(pack_path),
            "raw_ocr_nomenclature_extractor": str(extractor_path),
        },
        "paths": {
            "merger": str(main_path),
            "merged_image_visual_evidence_pack": str(pack_path_out),
            "records_jsonl": str(records_jsonl),
            "missing_jsonl": str(missing_jsonl),
            "records_csv": str(csv_path),
            "quality_check": str(quality_path),
        },
        "summary": summary,
        "checks": checks,
        "records": merge_records,
        "missing_records": missing_records,
        "safety_contract": merged_pack["safety_contract"],
    }

    _write_json(main_path, artifact)
    _write_json(pack_path_out, merged_pack)
    _write_jsonl(records_jsonl, merge_records)
    _write_jsonl(missing_jsonl, missing_records)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["citation_label", "figure", "linked_part_number", "selected_nomenclature", "nomenclature_confidence", "ocr_page_number", "ocr_page_id", "source_trace_ready"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in merge_records:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    _write_json(quality_path, {"status": STATUS_CHECKED, "quality_status": quality_status, "summary": summary, "checks": checks})

    print(f"status={STATUS_BUILT}")
    print(f"quality_status={quality_status}")
    print(f"visual_record_count={summary['visual_record_count']}")
    print(f"linked_visual_record_count={linked_visual_record_count}")
    print(f"nomenclature_merged_count={nomenclature_merged_count}")
    print(f"high_confidence_nomenclature_count={high_confidence_count}")
    print(f"source_trace_ready_count={source_trace_ready_count}")
    print(f"unsafe_record_count={unsafe_count}")
    print(f"answer_permission_count={answer_permission_count}")
    print(f"source_truth_mutation_allowed_count={source_truth_mutation_allowed_count}")
    print(f"write_attempt_count={write_attempt_count}")
    print(f"merger={main_path}")
    print(f"merged_pack={pack_path_out}")
    return artifact


def check_merger(
    merger: Any,
    output: Any,
    require_quality_pass: bool = False,
    min_nomenclature_merged: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(merger)
    s = data.get("summary") or {}
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    if int(s.get("nomenclature_merged_count") or 0) < min_nomenclature_merged:
        failures.append(f"nomenclature_merged_count below minimum: {s.get('nomenclature_merged_count')} < {min_nomenclature_merged}")
    if int(s.get("source_trace_ready_count") or 0) < min_source_trace_ready:
        failures.append(f"source_trace_ready_count below minimum: {s.get('source_trace_ready_count')} < {min_source_trace_ready}")
    if int(s.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count above maximum")
    if int(s.get("answer_permission_count") or 0) > max_answer_permission:
        failures.append("answer_permission_count above maximum")
    if int(s.get("source_truth_mutation_allowed_count") or 0) > max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above maximum")
    if int(s.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count above maximum")
    result = {
        "status": STATUS_CHECKED,
        "quality_status": "PASS" if not failures else "FAIL",
        "source_merger": str(merger),
        "summary": s,
        "failures": failures,
    }
    _write_json(output, result)
    print(f"status={STATUS_CHECKED}")
    print(f"quality_status={result['quality_status']}")
    print(f"nomenclature_merged_count={s.get('nomenclature_merged_count')}")
    print(f"high_confidence_nomenclature_count={s.get('high_confidence_nomenclature_count')}")
    print(f"source_trace_ready_count={s.get('source_trace_ready_count')}")
    print(f"unsafe_record_count={s.get('unsafe_record_count')}")
    print(f"answer_permission_count={s.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={s.get('write_attempt_count')}")
    for f in failures:
        print(f"failure={f}")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=MODULE)
    sub = p.add_subparsers(dest="cmd")
    b = sub.add_parser("build")
    b.add_argument("--image-visual-evidence-pack", required=True)
    b.add_argument("--raw-ocr-nomenclature-extractor", required=True)
    b.add_argument("--output-dir", required=True)
    b.add_argument("--min-visual-records", type=int, default=1)
    b.add_argument("--min-nomenclature-merged", type=int, default=1)
    b.add_argument("--min-source-trace-ready", type=int, default=1)
    b.add_argument("--max-unsafe", type=int, default=0)
    b.add_argument("--max-answer-permission", type=int, default=0)
    b.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    b.add_argument("--max-write-attempts", type=int, default=0)
    c = sub.add_parser("check")
    c.add_argument("--merger", required=True)
    c.add_argument("--output", required=True)
    c.add_argument("--require-quality-pass", action="store_true")
    c.add_argument("--min-nomenclature-merged", type=int, default=1)
    c.add_argument("--min-source-trace-ready", type=int, default=1)
    c.add_argument("--max-unsafe", type=int, default=0)
    c.add_argument("--max-answer-permission", type=int, default=0)
    c.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    c.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.cmd == "check":
        result = check_merger(
            merger=args.merger,
            output=args.output,
            require_quality_pass=args.require_quality_pass,
            min_nomenclature_merged=args.min_nomenclature_merged,
            min_source_trace_ready=args.min_source_trace_ready,
            max_unsafe=args.max_unsafe,
            max_answer_permission=args.max_answer_permission,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            max_write_attempts=args.max_write_attempts,
        )
        return 0 if result.get("quality_status") == "PASS" else 1
    # Allow scripts to omit explicit 'build'.
    if args.cmd not in (None, "build"):
        parser.error("unknown command")
    result = build_merger(
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        raw_ocr_nomenclature_extractor=args.raw_ocr_nomenclature_extractor,
        output_dir=args.output_dir,
        min_visual_records=args.min_visual_records,
        min_nomenclature_merged=args.min_nomenclature_merged,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
