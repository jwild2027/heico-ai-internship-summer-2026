"""TRACE-Net engineering semantic answer quality eval v1.

This module checks whether intent-specific engineering answers actually match
what the user asked, beyond citation/safety counters. It is intentionally
non-mutating: it reads composer manifests and writes an eval manifest only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_semantic_answer_quality_eval_v1"
VERSION = "v1"
MANIFEST_NAME = "trace_net_engineering_semantic_answer_quality_eval_v1.json"
QC_NAME = "trace_net_engineering_semantic_answer_quality_eval_v1_quality_check.json"
CSV_NAME = "trace_net_engineering_semantic_answer_quality_eval_v1_records.csv"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
CIT_RE = re.compile(r"\[[A-Z]+\d+\]")


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {p}")
    return data


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Any, records: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "record_id",
        "question",
        "task_type",
        "intent_answer_type",
        "composer_quality_status",
        "semantic_quality_status",
        "semantic_passed",
        "missing_requirement_count",
        "prohibited_phrase_count",
        "answer_citation_count",
        "source_trace_ready_citation_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = dict(r)
            row["missing_requirement_count"] = len(row.get("missing_requirements", []) or [])
            row["prohibited_phrase_count"] = len(row.get("prohibited_phrase_hits", []) or [])
            writer.writerow(row)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(n.lower() in text for n in needles)


def _parts_from(question: str, answer: str) -> List[str]:
    seen: List[str] = []
    for value in PART_RE.findall(f"{question} {answer}"):
        if value not in seen:
            seen.append(value)
    return seen


def _citation_count(answer: str, fallback: Any = 0) -> int:
    found = len(CIT_RE.findall(answer or ""))
    try:
        fb = int(fallback or 0)
    except Exception:
        fb = 0
    return max(found, fb)


def _require(record: Dict[str, Any], condition: bool, requirement: str) -> None:
    if not condition:
        record.setdefault("missing_requirements", []).append(requirement)
    else:
        record.setdefault("satisfied_requirements", []).append(requirement)


def _semantic_rules(question: str, answer: str, intent: str, task_type: str) -> Dict[str, Any]:
    qn = _norm(question)
    an = _norm(answer)
    parts = _parts_from(question, answer)
    rec: Dict[str, Any] = {
        "semantic_rule": intent or task_type or "generic",
        "satisfied_requirements": [],
        "missing_requirements": [],
        "prohibited_phrase_hits": [],
        "detected_part_numbers": parts,
    }

    _require(rec, bool(answer.strip()), "answer_text_present")

    if intent == "unsupported_interchangeability" or "interchangeab" in qn:
        _require(rec, _has_any(an, ["cannot prove", "can not prove", "does not prove", "not prove", "not proven"]), "states_interchangeability_not_proven")
        _require(rec, "interchangeab" in an, "mentions_interchangeability")
        for part in parts[:2]:
            _require(rec, part.lower() in an, f"mentions_part_{part}")
        _require(rec, _has_any(an, ["same nomenclature", "similar nomenclature", "not approval", "not an approval", "not prove"]), "explains_same_nomenclature_is_not_approval")
        _require(rec, _has_any(an, ["effectivity", "supersedure", "replacement", "interchangeability documentation", "approved source"]), "names_required_approval_evidence")
        if " are interchangeable" in an and not _has_any(an, ["cannot prove", "does not prove", "not prove", "not proven"]):
            rec["prohibited_phrase_hits"].append("asserts_are_interchangeable")

    elif intent == "unsupported_installation_safety" or "installation safety" in qn:
        _require(rec, _has_any(an, ["no.", "cannot prove", "does not prove", "not prove", "not proven"]), "states_installation_safety_not_proven")
        _require(rec, "installation safety" in an, "mentions_installation_safety")
        _require(rec, _has_any(an, ["identify", "identification", "figure", "figure-linked"]), "separates_identification_from_safety")
        _require(rec, _has_any(an, ["approved", "procedure", "effectivity", "safety evidence", "installation"]), "names_required_safety_evidence")
        if "proves installation safety" in an and not _has_any(an, ["does not prove", "cannot prove", "not prove"]):
            rec["prohibited_phrase_hits"].append("asserts_installation_safety_proven")

    elif intent == "limitations" or "not prove" in qn or "can't prove" in qn or "cannot prove" in qn:
        _require(rec, _has_any(an, ["can support", "can prove", "source-traced identification", "source-trace"]), "states_supported_claim_boundary")
        _require(rec, _has_any(an, ["cannot prove", "can not prove", "does not prove", "not prove"]), "states_cannot_prove_boundary")
        limit_terms = ["interchangeability", "effectivity", "fit", "replacement approval", "installation safety"]
        hit_count = sum(1 for term in limit_terms if term in an)
        _require(rec, hit_count >= 3, "lists_multiple_unsupported_engineering_claims")

    elif intent == "troubleshooting_nomenclature" or ("nomenclature" in qn and _has_any(qn, ["missing", "why"])):
        _require(rec, "nomenclature" in an, "mentions_nomenclature")
        _require(rec, "visual" in an and "link" in an, "mentions_visual_link_stage")
        _require(rec, _has_any(an, ["did not carry", "missing", "field coverage", "clean description", "clean nomenclature"]), "explains_missing_field_or_field_coverage")
        _require(rec, "ocr" in an and _has_any(an, ["recovered", "recover", "provides", "raw ocr"]), "explains_ocr_recovery")
        _require(rec, _has_any(an, ["merged", "now carries", "merged visual evidence", "visual evidence pack"]), "mentions_merged_recovery_state")

    elif intent == "comparison" or "compare" in qn:
        _require(rec, "figure 69" in an, "mentions_figure_69")
        _require(rec, "figure 75" in an, "mentions_figure_75")
        _require(rec, "120-50645-005" in an, "mentions_figure_69_part")
        _require(rec, "120-50645-011" in an, "mentions_figure_75_part")
        _require(rec, _has_any(an, ["comparison", "compare", "both"]), "uses_comparison_framing")
        _require(rec, _has_any(an, ["does not prove interchangeability", "not prove interchangeability", "not interchangeability proof"]), "states_comparison_not_interchangeability_proof")

    elif "evidence" in qn or intent == "evidence_support":
        _require(rec, "evidence" in an, "mentions_evidence")
        _require(rec, _citation_count(answer) >= 2, "uses_multiple_citations")
        _require(rec, _has_any(an, ["source-trace", "source trace", "ocr", "visual", "table"]), "names_evidence_types")

    else:
        _require(rec, _citation_count(answer) >= 1, "has_at_least_one_citation")
        _require(rec, _has_any(an, ["limits", "evidence", "engineering confidence"]), "has_engineering_answer_structure")

    rec["semantic_passed"] = not rec.get("missing_requirements") and not rec.get("prohibited_phrase_hits")
    rec["semantic_quality_status"] = "PASS" if rec["semantic_passed"] else "FAIL"
    return rec


def _extract_composer_record(path: Path, idx: int) -> Dict[str, Any]:
    data = _load_json(path)
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    qgate = data.get("quality_gate", {}) if isinstance(data.get("quality_gate"), dict) else {}

    question = str(summary.get("question") or data.get("question") or "")
    answer = str(data.get("answer_text") or data.get("answer") or "")
    intent = str(summary.get("intent_answer_type") or data.get("intent_answer_type") or "")
    task_type = str(summary.get("task_type") or data.get("task_type") or "")

    sem = _semantic_rules(question, answer, intent, task_type)

    record: Dict[str, Any] = {
        "record_id": f"sem_{idx:03d}",
        "source_composer": str(path),
        "question": question,
        "task_type": task_type,
        "intent_answer_type": intent,
        "composer_quality_status": data.get("quality_status"),
        "answer_text": answer,
        "answer_preview": answer[:700],
        "answer_citation_count": _citation_count(answer, summary.get("answer_citation_count")),
        "valid_answer_citation_count": int(summary.get("valid_answer_citation_count") or qgate.get("valid_answer_citation_count") or 0),
        "source_trace_ready_citation_count": int(summary.get("source_trace_ready_citation_count") or qgate.get("source_trace_ready_citation_count") or 0),
        "invalid_answer_citation_count": int(summary.get("invalid_answer_citation_count") or qgate.get("invalid_answer_citation_count") or 0),
        "unsupported_claim_count": int(summary.get("unsupported_claim_count") or qgate.get("unsupported_claim_count") or 0),
        "summary_used_as_proof_count": int(summary.get("summary_used_as_proof_count") or qgate.get("summary_used_as_proof_count") or 0),
        "llava_only_part_identity_claim_count": int(summary.get("llava_only_part_identity_claim_count") or qgate.get("llava_only_part_identity_claim_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or qgate.get("answer_permission_count") or 0),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count") or qgate.get("source_truth_mutation_allowed_count") or 0),
        "postgres_write_attempt_count": int(summary.get("postgres_write_attempt_count") or 0),
        "qdrant_write_attempt_count": int(summary.get("qdrant_write_attempt_count") or 0),
        "opensearch_write_attempt_count": int(summary.get("opensearch_write_attempt_count") or 0),
        "opensearch_upload_attempt_count": int(summary.get("opensearch_upload_attempt_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or qgate.get("write_attempt_count") or 0),
        "unsafe_record_count": int(summary.get("unsafe_record_count") or qgate.get("unsafe_record_count") or 0),
    }
    record.update(sem)
    return record


def _discover_composers(composer_paths: Optional[Sequence[Any]], composer_root: Optional[Any]) -> List[Path]:
    found: List[Path] = []
    for p in composer_paths or []:
        path = Path(p)
        if path.is_dir():
            path = path / "trace_net_engineering_intent_answer_composer_v1.json"
        found.append(path)
    if composer_root:
        root = Path(composer_root)
        found.extend(sorted(root.glob("**/trace_net_engineering_intent_answer_composer_v1.json")))
    unique: List[Path] = []
    seen = set()
    for p in found:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _quality_check(
    manifest: Mapping[str, Any],
    *,
    min_semantic_records: int = 1,
    min_semantic_passes: int = 1,
    max_semantic_failures: Optional[int] = None,
    max_missing_intent_requirements: int = 0,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    s = dict(manifest.get("summary", {}) or {})
    failures: List[str] = []

    def check_max(key: str, max_value: int) -> None:
        value = int(s.get(key, 0) or 0)
        if value > max_value:
            failures.append(f"{key} above maximum: {value} > {max_value}")

    if int(s.get("semantic_eval_record_count", 0) or 0) < min_semantic_records:
        failures.append(f"semantic_eval_record_count below minimum: {s.get('semantic_eval_record_count', 0)} < {min_semantic_records}")
    if int(s.get("semantic_pass_count", 0) or 0) < min_semantic_passes:
        failures.append(f"semantic_pass_count below minimum: {s.get('semantic_pass_count', 0)} < {min_semantic_passes}")
    if max_semantic_failures is not None and int(s.get("semantic_fail_count", 0) or 0) > max_semantic_failures:
        failures.append(f"semantic_fail_count above maximum: {s.get('semantic_fail_count', 0)} > {max_semantic_failures}")
    if int(s.get("missing_intent_requirement_count", 0) or 0) > max_missing_intent_requirements:
        failures.append(f"missing_intent_requirement_count above maximum: {s.get('missing_intent_requirement_count', 0)} > {max_missing_intent_requirements}")

    check_max("unsupported_claim_count", max_unsupported_claims)
    check_max("summary_used_as_proof_count", max_summary_used_as_proof)
    check_max("invalid_answer_citation_count", max_invalid_citations)
    check_max("llava_only_part_identity_claim_count", max_llava_only_part_identity_claims)
    check_max("unsafe_record_count", max_unsafe)
    check_max("answer_permission_count", max_answer_permission)
    check_max("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed)
    check_max("write_attempt_count", max_write_attempts)

    return {
        "status": "TRACE_NET_ENGINEERING_SEMANTIC_ANSWER_QUALITY_EVAL_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "summary": s,
    }


def build_semantic_answer_quality_eval(
    *,
    composer: Optional[Sequence[Any]] = None,
    composer_root: Optional[Any] = None,
    output_dir: Any,
    min_semantic_records: int = 1,
    min_semantic_passes: int = 1,
    max_semantic_failures: Optional[int] = None,
    max_missing_intent_requirements: int = 0,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    require_quality_pass: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    composers = _discover_composers(composer, composer_root)
    records: List[Dict[str, Any]] = []
    missing: List[str] = []
    for p in composers:
        if not p.exists():
            missing.append(str(p))
            continue
        records.append(_extract_composer_record(p, len(records) + 1))

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "semantic_eval_record_count": len(records),
        "source_composer_count": len(composers),
        "missing_composer_count": len(missing),
        "semantic_pass_count": sum(1 for r in records if r.get("semantic_passed")),
        "semantic_fail_count": sum(1 for r in records if not r.get("semantic_passed")),
        "missing_intent_requirement_count": sum(len(r.get("missing_requirements", []) or []) for r in records),
        "prohibited_phrase_count": sum(len(r.get("prohibited_phrase_hits", []) or []) for r in records),
        "answer_citation_count": sum(int(r.get("answer_citation_count", 0) or 0) for r in records),
        "source_trace_ready_citation_count": sum(int(r.get("source_trace_ready_citation_count", 0) or 0) for r in records),
        "invalid_answer_citation_count": sum(int(r.get("invalid_answer_citation_count", 0) or 0) for r in records),
        "unsupported_claim_count": sum(int(r.get("unsupported_claim_count", 0) or 0) for r in records),
        "summary_used_as_proof_count": sum(int(r.get("summary_used_as_proof_count", 0) or 0) for r in records),
        "llava_only_part_identity_claim_count": sum(int(r.get("llava_only_part_identity_claim_count", 0) or 0) for r in records),
        "answer_permission_count": sum(int(r.get("answer_permission_count", 0) or 0) for r in records),
        "source_truth_mutation_allowed_count": sum(int(r.get("source_truth_mutation_allowed_count", 0) or 0) for r in records),
        "postgres_write_attempt_count": sum(int(r.get("postgres_write_attempt_count", 0) or 0) for r in records),
        "qdrant_write_attempt_count": sum(int(r.get("qdrant_write_attempt_count", 0) or 0) for r in records),
        "opensearch_write_attempt_count": sum(int(r.get("opensearch_write_attempt_count", 0) or 0) for r in records),
        "opensearch_upload_attempt_count": sum(int(r.get("opensearch_upload_attempt_count", 0) or 0) for r in records),
        "write_attempt_count": sum(int(r.get("write_attempt_count", 0) or 0) for r in records),
        "unsafe_record_count": sum(int(r.get("unsafe_record_count", 0) or 0) for r in records),
        "intent_answer_types": sorted({str(r.get("intent_answer_type") or "") for r in records if r.get("intent_answer_type")}),
    }
    summary["ready_for_real_answer_smoke_test"] = (
        summary["semantic_eval_record_count"] > 0
        and summary["semantic_fail_count"] == 0
        and summary["unsupported_claim_count"] == 0
        and summary["summary_used_as_proof_count"] == 0
    )

    manifest: Dict[str, Any] = {
        "status": "TRACE_NET_ENGINEERING_SEMANTIC_ANSWER_QUALITY_EVAL_BUILT",
        "quality_status": "UNKNOWN",
        "summary": summary,
        "missing_composers": missing,
        "records": records,
        "paths": {
            "manifest": str(out_dir / MANIFEST_NAME),
            "quality_check": str(out_dir / QC_NAME),
            "records_csv": str(out_dir / CSV_NAME),
        },
    }
    qc = _quality_check(
        manifest,
        min_semantic_records=min_semantic_records,
        min_semantic_passes=min_semantic_passes,
        max_semantic_failures=max_semantic_failures,
        max_missing_intent_requirements=max_missing_intent_requirements,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    manifest["quality_status"] = qc["quality_status"]
    manifest["failures"] = qc["failures"]

    _write_json(out_dir / MANIFEST_NAME, manifest)
    _write_json(out_dir / QC_NAME, qc)
    _write_csv(out_dir / CSV_NAME, records)

    if require_quality_pass and manifest["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")
    return manifest


def check_semantic_answer_quality_eval(
    *,
    eval_set: Any,
    output: Any,
    require_quality_pass: bool = False,
    min_semantic_records: int = 1,
    min_semantic_passes: int = 1,
    max_semantic_failures: Optional[int] = None,
    max_missing_intent_requirements: int = 0,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    manifest = _load_json(eval_set)
    qc = _quality_check(
        manifest,
        min_semantic_records=min_semantic_records,
        min_semantic_passes=min_semantic_passes,
        max_semantic_failures=max_semantic_failures,
        max_missing_intent_requirements=max_missing_intent_requirements,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    _write_json(output, qc)
    if require_quality_pass and qc["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")
    return qc


def _add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-semantic-records", type=int, default=1)
    parser.add_argument("--min-semantic-passes", type=int, default=1)
    parser.add_argument("--max-semantic-failures", type=int, default=None)
    parser.add_argument("--max-missing-intent-requirements", type=int, default=0)
    parser.add_argument("--max-unsupported-claims", type=int, default=0)
    parser.add_argument("--max-summary-used-as-proof", type=int, default=0)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--require-quality-pass", action="store_true")


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering semantic answer quality eval v1")
    parser.add_argument("--composer", action="append", default=[])
    parser.add_argument("--composer-root")
    parser.add_argument("--output-dir", required=True)
    _add_threshold_args(parser)
    args = parser.parse_args(argv)
    manifest = build_semantic_answer_quality_eval(**vars(args))
    s = manifest.get("summary", {})
    print("status=" + str(manifest.get("status")))
    print("quality_status=" + str(manifest.get("quality_status")))
    for key in [
        "semantic_eval_record_count",
        "semantic_pass_count",
        "semantic_fail_count",
        "missing_intent_requirement_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
        "ready_for_real_answer_smoke_test",
    ]:
        print(f"{key}={s.get(key)}")
    print("eval=" + str(Path(args.output_dir) / MANIFEST_NAME))
    return 0


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering semantic answer quality eval v1")
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--output", required=True)
    _add_threshold_args(parser)
    args = parser.parse_args(argv)
    qc = check_semantic_answer_quality_eval(**vars(args))
    s = qc.get("summary", {})
    print("status=" + str(qc.get("status")))
    print("quality_status=" + str(qc.get("quality_status")))
    for key in [
        "semantic_eval_record_count",
        "semantic_pass_count",
        "semantic_fail_count",
        "missing_intent_requirement_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
    ]:
        print(f"{key}={s.get(key)}")
    for f in qc.get("failures", []) or []:
        print("failure=" + str(f))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_build())
