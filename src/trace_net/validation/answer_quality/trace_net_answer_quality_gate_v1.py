from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

MODULE = "trace_net_answer_quality_gate_v1"
VERSION = "v1"

CITATION_RE = re.compile(r"\[(E\d+)\]")
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

INTERCHANGEABILITY_TERMS = [
    "interchangeable",
    "interchangeability",
    "replacement",
    "replace",
    "replaces",
    "substitute",
    "substitution",
    "equivalent",
    "equivalency",
    "compatible replacement",
    "supersedes",
    "superseded by",
]

GRAPH_PROOF_OVERSTATEMENTS = [
    "graph proves",
    "graph confirms",
    "graph verified",
    "leiden proves",
    "leiden confirms",
    "community proves",
    "community confirms",
    "same community proves",
    "community makes it",
]

UNSUPPORTED_ABSOLUTE_TERMS = [
    "all aircraft",
    "all units",
    "always applicable",
    "approved substitute",
    "approved replacement",
    "must be used",
    "mandatory replacement",
]

FACTUAL_KEYWORDS = [
    "found",
    "appears",
    "located",
    "listed",
    "page",
    "figure",
    "fig.",
    "item",
    "variant",
    "nearby",
    "similar",
    "structure",
    "lateral leg",
    "part number",
    "assembly",
    "effectivity",
    "units",
]


@dataclass
class Violation:
    violation_type: str
    severity: str
    message: str
    evidence: str = ""


@dataclass
class CitationAuditRecord:
    citation_label: str
    valid: bool
    anchor_aware_role: str = ""
    proof_strength: str = ""
    anchor_relation_type: str = ""
    page_number: Any = None
    page_id: str = ""


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _extract_answer_from_report(report_path: str | Path) -> str:
    report_path = Path(report_path)
    payload = _read_json(report_path)

    for key_path in [
        ("answer_text",),
        ("answer",),
        ("answer_draft", "answer_text"),
        ("answer_draft", "content"),
        ("llm_answer",),
        ("llm_response", "content"),
    ]:
        obj: Any = payload
        for key in key_path:
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                obj = None
                break
        if isinstance(obj, str) and obj.strip():
            return obj.strip()

    # Common TRACE-Net convention: answer markdown next to report.
    for candidate in [
        report_path.with_name("trace_net_raw_to_answer_context_engineered_native_v1_answer.md"),
        report_path.with_name("trace_net_raw_to_answer_e2e_smoke_native_v1_answer.md"),
        report_path.with_name("trace_net_raw_to_answer_e2e_smoke_v1_answer.md"),
    ]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace").strip()

    return ""


def _load_answer(answer_file: str | None, raw_to_answer_report: str | None) -> str:
    if answer_file:
        return Path(answer_file).read_text(encoding="utf-8", errors="replace").strip()
    if raw_to_answer_report:
        return _extract_answer_from_report(raw_to_answer_report)
    return ""


def _norm_label(label: Any) -> str:
    if label is None:
        return ""
    return str(label).strip()


def _context_records(context_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = context_payload.get("records")
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    return []


def _context_quality_status(context_payload: dict[str, Any]) -> str | None:
    return context_payload.get("quality_status") or (context_payload.get("summary") or {}).get("quality_status")


def _citation_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for idx, record in enumerate(records, start=1):
        label = _norm_label(record.get("citation_label")) or f"E{idx}"
        index[label] = record
    return index


def _labels_by_role(records: list[dict[str, Any]], roles: Iterable[str]) -> set[str]:
    roles = set(roles)
    labels: set[str] = set()
    for idx, record in enumerate(records, start=1):
        if record.get("anchor_aware_role") in roles or record.get("anchor_role") in roles or record.get("exact_row_context_role") in roles:
            labels.add(_norm_label(record.get("citation_label")) or f"E{idx}")
    return labels


def _labels_by_proof(records: list[dict[str, Any]], proofs: Iterable[str]) -> set[str]:
    proofs = set(proofs)
    labels: set[str] = set()
    for idx, record in enumerate(records, start=1):
        if record.get("proof_strength") in proofs or record.get("proof_role") in proofs:
            labels.add(_norm_label(record.get("citation_label")) or f"E{idx}")
    return labels


def _query_part_numbers(context_payload: dict[str, Any], question: str | None = None) -> list[str]:
    summary = context_payload.get("summary") or {}
    values = summary.get("query_part_numbers") or context_payload.get("query_part_numbers") or []
    parts: list[str] = []
    if isinstance(values, list):
        parts.extend(str(v) for v in values if v)
    elif isinstance(values, str):
        parts.extend(PART_RE.findall(values))
    if question:
        parts.extend(PART_RE.findall(question))
    # Preserve order.
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _sentences(answer: str) -> list[str]:
    chunks: list[str] = []
    for line in answer.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("```") or line.startswith("TRACE-Net"):
            continue
        for part in SENTENCE_RE.split(line):
            clean = part.strip(" -*\t")
            if clean:
                chunks.append(clean)
    return chunks


def _looks_factual(sentence: str, query_parts: list[str]) -> bool:
    low = sentence.lower()
    if any(p in sentence for p in query_parts):
        return True
    if PART_RE.search(sentence):
        return True
    return any(k in low for k in FACTUAL_KEYWORDS)


def _has_any_term(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term in low]


def _unsupported_interchangeability_terms(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for term in INTERCHANGEABILITY_TERMS:
        start = 0
        while True:
            pos = low.find(term, start)
            if pos < 0:
                break
            window = low[max(0, pos - 60): pos + len(term) + 20]
            negated = any(phrase in window for phrase in [
                "not proof of",
                "not evidence of",
                "not interchangeable",
                "not an interchangeable",
                "not a replacement",
                "not a substitute",
                "not equivalent",
                "does not prove",
                "do not prove",
                "without proof of",
                "no proof of",
            ])
            if not negated:
                found.append(term)
                break
            start = pos + len(term)
    return found


def audit_answer_quality(
    *,
    answer_text: str,
    context_payload: dict[str, Any],
    question: str | None = None,
) -> dict[str, Any]:
    records = _context_records(context_payload)
    summary = context_payload.get("summary") or {}
    citation_index = _citation_index(records)
    valid_labels = set(citation_index)
    cited_labels = CITATION_RE.findall(answer_text or "")
    cited_label_counts = Counter(cited_labels)
    invalid_labels = sorted({label for label in cited_labels if label not in valid_labels})

    direct_labels = _labels_by_role(records, ["direct_exact_match_anchor", "direct_exact_match_proven"])
    direct_labels |= _labels_by_proof(records, ["direct_exact_proof", "direct_exact_match_proven"])
    variant_labels = _labels_by_role(records, ["family_variant_anchor", "same_anchor_community_variant"])
    variant_labels |= _labels_by_proof(records, ["related_variant"])

    query_parts = _query_part_numbers(context_payload, question=question)
    answer_lower = (answer_text or "").lower()
    cited_direct_labels = sorted(set(cited_labels) & direct_labels)
    cited_variant_labels = sorted(set(cited_labels) & variant_labels)

    violations: list[Violation] = []
    if not answer_text.strip():
        violations.append(Violation("empty_answer", "critical", "Answer text is empty."))
    if not records:
        violations.append(Violation("empty_context_records", "critical", "Context pack has no records."))
    if not cited_labels:
        violations.append(Violation("no_citations", "critical", "Answer contains no citation labels like [E1]."))
    if invalid_labels:
        violations.append(Violation("invalid_citation_label", "high", "Answer cites labels not present in context.", ",".join(invalid_labels)))

    missing_parts = [p for p in query_parts if p not in answer_text]
    if query_parts and missing_parts:
        violations.append(Violation("query_part_not_mentioned", "high", "Answer does not mention all queried part numbers.", ",".join(missing_parts)))

    if direct_labels and not cited_direct_labels:
        violations.append(Violation("no_direct_proof_citation", "high", "Answer does not cite any direct exact proof anchor.", ",".join(sorted(direct_labels))))

    interchange_terms = _unsupported_interchangeability_terms(answer_text)
    if interchange_terms:
        # Current TRACE-Net context does not yet carry interchangeability proof. Treat all as unsupported unless explicit proof appears.
        has_interchangeability_proof = any(
            str(r.get("proof_strength", "")).lower() in {"interchangeability_proof", "substitution_proof"}
            or str(r.get("anchor_relation_type", "")).lower() in {"interchangeability", "approved_substitution"}
            for r in records
        )
        if not has_interchangeability_proof:
            violations.append(Violation(
                "unsupported_interchangeability_claim",
                "high",
                "Answer uses replacement/substitution/equivalence wording without explicit proof in context.",
                ",".join(interchange_terms),
            ))

    graph_terms = _has_any_term(answer_text, GRAPH_PROOF_OVERSTATEMENTS)
    if graph_terms:
        violations.append(Violation(
            "graph_or_leiden_overstated_as_proof",
            "high",
            "Answer overstates graph/Leiden/community as proof instead of guidance.",
            ",".join(graph_terms),
        ))

    absolute_terms = _has_any_term(answer_text, UNSUPPORTED_ABSOLUTE_TERMS)
    if absolute_terms:
        violations.append(Violation(
            "unsupported_absolute_claim",
            "medium",
            "Answer contains broad absolute/applicability wording that should require explicit proof.",
            ",".join(absolute_terms),
        ))

    unsupported_sentences: list[str] = []
    for sentence in _sentences(answer_text):
        if _looks_factual(sentence, query_parts) and not CITATION_RE.search(sentence):
            # Avoid penalizing title-only fragments too aggressively.
            if len(sentence.split()) >= 5:
                unsupported_sentences.append(sentence)
    if unsupported_sentences:
        violations.append(Violation(
            "unsupported_factual_sentence_without_citation",
            "medium",
            "One or more factual-looking sentences do not include citation labels.",
            " | ".join(unsupported_sentences[:5]),
        ))

    violation_records = [asdict(v) for v in violations]
    audit_records: list[dict[str, Any]] = []
    for label in sorted(valid_labels, key=lambda x: int(x[1:]) if x.startswith("E") and x[1:].isdigit() else 10**9):
        record = citation_index[label]
        audit_records.append(asdict(CitationAuditRecord(
            citation_label=label,
            valid=label in cited_label_counts,
            anchor_aware_role=str(record.get("anchor_aware_role") or record.get("anchor_role") or record.get("exact_row_context_role") or ""),
            proof_strength=str(record.get("proof_strength") or record.get("proof_role") or ""),
            anchor_relation_type=str(record.get("anchor_relation_type") or record.get("graph_relation_type") or ""),
            page_number=record.get("page_number"),
            page_id=str(record.get("page_id") or ""),
        )))

    safety = {
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "dry_run_only": True,
    }

    severity_counts = Counter(v["severity"] for v in violation_records)
    quality_status = "PASS" if not violation_records else "FAIL"

    out_summary = {
        "module": MODULE,
        "version": VERSION,
        "source_context_module": summary.get("module") or context_payload.get("module"),
        "source_context_quality_status": context_payload.get("quality_status"),
        "question": question or summary.get("question") or context_payload.get("question"),
        "query_part_numbers": query_parts,
        "answer_char_count": len(answer_text),
        "answer_sentence_count": len(_sentences(answer_text)),
        "context_record_count": len(records),
        "context_citation_label_count": len(valid_labels),
        "answer_citation_count": len(cited_labels),
        "answer_unique_citation_count": len(set(cited_labels)),
        "valid_answer_citation_count": len([c for c in cited_labels if c in valid_labels]),
        "invalid_answer_citation_count": len(invalid_labels),
        "invalid_answer_citation_labels": invalid_labels,
        "direct_proof_label_count": len(direct_labels),
        "direct_proof_citation_count": len(cited_direct_labels),
        "cited_direct_proof_labels": cited_direct_labels,
        "variant_label_count": len(variant_labels),
        "variant_citation_count": len(cited_variant_labels),
        "cited_variant_labels": cited_variant_labels,
        "unsupported_factual_sentence_count": len(unsupported_sentences),
        "unsupported_interchangeability_claim_count": 1 if interchange_terms else 0,
        "graph_or_leiden_overstatement_count": 1 if graph_terms else 0,
        "unsupported_absolute_claim_count": 1 if absolute_terms else 0,
        "violation_record_count": len(violation_records),
        "violation_severity_counts": dict(severity_counts),
        "answer_quality_gate_ready": True,
        "answer_quality_gate_passed": quality_status == "PASS",
        **safety,
    }

    return {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": out_summary,
        "answer_text": answer_text,
        "records": audit_records,
        "violations": violation_records,
    }


def build_answer_quality_gate(
    *,
    context_pack: str,
    output_dir: str,
    answer_file: str | None = None,
    raw_to_answer_report: str | None = None,
    question: str | None = None,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    context_payload = _read_json(context_pack)
    answer_text = _load_answer(answer_file, raw_to_answer_report)
    if question is None:
        question = (context_payload.get("summary") or {}).get("question") or context_payload.get("question")

    payload = audit_answer_quality(answer_text=answer_text, context_payload=context_payload, question=question)
    payload["source_context_pack"] = str(context_pack)
    payload["source_answer_file"] = str(answer_file) if answer_file else None
    payload["source_raw_to_answer_report"] = str(raw_to_answer_report) if raw_to_answer_report else None

    if require_source_quality_pass and _context_quality_status(context_payload) != "PASS":
        payload["quality_status"] = "FAIL"
        payload["violations"].append(asdict(Violation(
            "source_context_quality_not_pass",
            "critical",
            "Source context pack did not have quality_status PASS.",
            str(_context_quality_status(context_payload)),
        )))
        payload["summary"]["violation_record_count"] = len(payload["violations"])
        payload["summary"]["answer_quality_gate_passed"] = False

    report_path = output / f"{MODULE}.json"
    _write_json(report_path, payload)

    _write_csv(
        output / f"{MODULE}_records.csv",
        payload.get("records") or [],
        ["citation_label", "valid", "anchor_aware_role", "proof_strength", "anchor_relation_type", "page_number", "page_id"],
    )
    _write_csv(
        output / f"{MODULE}_violations.csv",
        payload.get("violations") or [],
        ["violation_type", "severity", "message", "evidence"],
    )

    md = [
        f"# TRACE-Net Answer Quality Gate v1",
        "",
        f"Quality status: **{payload['quality_status']}**",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(payload["summary"], indent=2, sort_keys=True),
        "```",
    ]
    (output / f"{MODULE}.md").write_text("\n".join(md), encoding="utf-8")

    if quality:
        quality_payload = check_answer_quality_gate_report(report_path=report_path)
        _write_json(output / f"{MODULE}_quality_check.json", quality_payload)
        print(f"Wrote: {output / f'{MODULE}_quality_check.json'}")

    print("Status: TRACE_NET_ANSWER_QUALITY_GATE_BUILT")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return payload


def check_answer_quality_gate_report(
    *,
    report_path: str | Path,
    min_records: int = 1,
    min_citations: int = 1,
    min_valid_citations: int = 1,
    max_invalid_citations: int = 0,
    max_unsupported_claim_sentences: int | None = None,
    max_violation_records: int | None = None,
    require_source_quality_pass: bool = False,
    require_answer_quality_pass: bool = False,
    require_direct_proof_citation: bool = False,
    require_query_part_mentioned: bool = False,
    require_no_unsupported_interchangeability: bool = False,
    require_no_graph_proof_overstatement: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require((summary.get("context_record_count") or 0) >= min_records, f"context_record_count below {min_records}")
    require((summary.get("answer_citation_count") or 0) >= min_citations, f"answer_citation_count below {min_citations}")
    require((summary.get("valid_answer_citation_count") or 0) >= min_valid_citations, f"valid_answer_citation_count below {min_valid_citations}")
    require((summary.get("invalid_answer_citation_count") or 0) <= max_invalid_citations, f"invalid_answer_citation_count above {max_invalid_citations}")

    if max_unsupported_claim_sentences is not None:
        require((summary.get("unsupported_factual_sentence_count") or 0) <= max_unsupported_claim_sentences, f"unsupported_factual_sentence_count above {max_unsupported_claim_sentences}")
    if max_violation_records is not None:
        require((summary.get("violation_record_count") or 0) <= max_violation_records, f"violation_record_count above {max_violation_records}")
    if require_source_quality_pass:
        require(summary.get("source_context_quality_status") == "PASS", "source_context_quality_status is not PASS")
    if require_answer_quality_pass:
        require(payload.get("quality_status") == "PASS", "answer quality gate did not PASS")
        require(summary.get("answer_quality_gate_passed") is True, "answer_quality_gate_passed is not true")
    if require_direct_proof_citation:
        require((summary.get("direct_proof_citation_count") or 0) >= 1, "answer did not cite direct proof")
    if require_query_part_mentioned:
        for part in summary.get("query_part_numbers") or []:
            require(part in (payload.get("answer_text") or ""), f"answer did not mention queried part {part}")
    if require_no_unsupported_interchangeability:
        require((summary.get("unsupported_interchangeability_claim_count") or 0) == 0, "unsupported interchangeability/replacement claim found")
    if require_no_graph_proof_overstatement:
        require((summary.get("graph_or_leiden_overstatement_count") or 0) == 0, "graph/Leiden overstatement found")
    if require_no_human_review_required:
        require((summary.get("human_review_required_count") or 0) == 0, "human_review_required_count is not zero")
        require((summary.get("manual_review_required_count") or 0) == 0, "manual_review_required_count is not zero")
    if max_unsafe is not None:
        require((summary.get("unsafe_record_count") or 0) <= max_unsafe, f"unsafe_record_count above {max_unsafe}")
    if require_no_answer_permission:
        require((summary.get("answer_permission_count") or 0) == 0, "answer_permission_count is not zero")
        require((summary.get("can_answer_directly_count") or 0) == 0, "can_answer_directly_count is not zero")
        require((summary.get("can_prove_claims_count") or 0) == 0, "can_prove_claims_count is not zero")
    if require_no_source_truth_mutation:
        require((summary.get("source_truth_mutation_allowed_count") or 0) == 0, "source_truth_mutation_allowed_count is not zero")
    if require_no_write_attempts:
        for key in ["write_attempt_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            require((summary.get(key) or 0) == 0, f"{key} is not zero")

    quality_status = "PASS" if not failures else "FAIL"
    return {
        "module": f"{MODULE}_quality_check",
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "source_report_path": str(report_path),
    }


def main_build() -> None:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer quality gate report v1.")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--answer-file")
    parser.add_argument("--raw-to-answer-report")
    parser.add_argument("--question")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    build_answer_quality_gate(
        context_pack=args.context_pack,
        output_dir=args.output_dir,
        answer_file=args.answer_file,
        raw_to_answer_report=args.raw_to_answer_report,
        question=args.question,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check() -> None:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer quality gate v1 report.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-valid-citations", type=int, default=1)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-unsupported-claim-sentences", type=int)
    parser.add_argument("--max-violation-records", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-answer-quality-pass", action="store_true")
    parser.add_argument("--require-direct-proof-citation", action="store_true")
    parser.add_argument("--require-query-part-mentioned", action="store_true")
    parser.add_argument("--require-no-unsupported-interchangeability", action="store_true")
    parser.add_argument("--require-no-graph-proof-overstatement", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()

    payload = check_answer_quality_gate_report(
        report_path=args.report_path,
        min_records=args.min_records,
        min_citations=args.min_citations,
        min_valid_citations=args.min_valid_citations,
        max_invalid_citations=args.max_invalid_citations,
        max_unsupported_claim_sentences=args.max_unsupported_claim_sentences,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_answer_quality_pass=args.require_answer_quality_pass,
        require_direct_proof_citation=args.require_direct_proof_citation,
        require_query_part_mentioned=args.require_query_part_mentioned,
        require_no_unsupported_interchangeability=args.require_no_unsupported_interchangeability,
        require_no_graph_proof_overstatement=args.require_no_graph_proof_overstatement,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )
    if args.write_json:
        out = Path(args.report_path).with_name(f"{MODULE}_quality_check.json")
        _write_json(out, payload)
        print(f"Wrote: {out}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    if payload["failures"]:
        print("Failures:", json.dumps(payload["failures"], sort_keys=True))


if __name__ == "__main__":
    main_build()
