
"""TRACE-Net Engineering Context Draft Packet v1.

Packages Self-RAG-approved engineering context packs into Gemma-ready draft packets.

This module is NOT the final answer API.
It prepares the exact context/instructions Gemma may use to draft, while preserving:
- no final answer permission
- no direct answer permission
- no claim-proving permission
- no LLM call
- no retrieval execution
- no source-truth mutation

It only includes context packs that Self-RAG marked ready_for_gemma_draft=True.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MODULE_VERSION = "trace_net_engineering_context_draft_packet_v1"
REPORT_NAME = "trace_net_engineering_context_draft_packet_v1.json"

SOURCE_TRUTH_TIERS = {
    "exact_source_evidence_candidate",
    "source_context_guidance",
    "structured_table_candidate",
}

CANDIDATE_TIERS = {
    "relationship_candidate",
    "visual_candidate_only",
    "semantic_lead_only",
    "routing_metadata_not_source_truth",
    "candidate_or_supporting",
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _all_capsules(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    capsules: List[Dict[str, Any]] = []
    route_caps = pack.get("route_evidence_capsules") or {}
    if isinstance(route_caps, dict):
        for route, items in route_caps.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        clone = dict(item)
                        clone.setdefault("route", route)
                        capsules.append(clone)
    return capsules


def _capsule_excerpt(capsule: Mapping[str, Any], limit: int = 700) -> str:
    text = str(capsule.get("source_text_excerpt") or "").strip()
    return text[:limit]


def _capsule_ref(capsule: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "route": capsule.get("route"),
        "source_artifact": capsule.get("source_artifact"),
        "source_artifact_path": capsule.get("source_artifact_path"),
        "source_artifact_index": capsule.get("source_artifact_index"),
        "page_id": capsule.get("page_id"),
        "trust_tier": capsule.get("trust_tier"),
        "match_score": capsule.get("match_score"),
        "source_trace_ready": capsule.get("source_trace_ready"),
        "fallback_available_context": capsule.get("fallback_available_context", False),
        "excerpt": _capsule_excerpt(capsule),
    }


def _context_sections_by_id(pack: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for section in pack.get("sections") or []:
        if isinstance(section, dict):
            sid = section.get("section_id")
            if sid:
                out[str(sid)] = section
    return out


def _source_truth_capsules(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for capsule in _all_capsules(pack):
        if capsule.get("trust_tier") in SOURCE_TRUTH_TIERS and not capsule.get("fallback_available_context"):
            out.append(_capsule_ref(capsule))
    return out


def _candidate_capsules(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for capsule in _all_capsules(pack):
        if capsule.get("trust_tier") in CANDIDATE_TIERS or capsule.get("fallback_available_context"):
            out.append(_capsule_ref(capsule))
    return out


def _find_self_rag_for_pack(self_rag_records: Sequence[Mapping[str, Any]], pack_id: str) -> Optional[Mapping[str, Any]]:
    for record in self_rag_records:
        if record.get("context_pack_id") == pack_id:
            return record
    return None


def _draft_instruction_block(pack: Mapping[str, Any], self_rag: Mapping[str, Any]) -> Dict[str, Any]:
    intent = pack.get("intent_family")
    if intent == "exact_part_lookup":
        answer_mode = "exact_evidence_first_then_related_context"
        instructions = [
            "Start with exact source-backed evidence.",
            "Keep nearby/similar parts separate from exact matches.",
            "Do not call a related part an alternate, substitute, approved replacement, or interchangeable item unless source evidence explicitly says so.",
            "Use citations/source trace references from the provided context pack only.",
            "State missing evidence instead of guessing.",
        ]
    elif intent == "repair_or_fault_context":
        answer_mode = "source_backed_procedure_context"
        instructions = [
            "Preserve warnings/cautions/notes before procedural details.",
            "Do not invent maintenance steps.",
            "If warning/caution evidence is missing, say so.",
            "Do not approve maintenance activity or imply safety.",
        ]
    elif intent in {"engineering_change_candidate", "similarity_or_substitution_candidate", "visual_or_callout_similarity"}:
        answer_mode = "candidate_for_engineering_review"
        instructions = [
            "Use candidate-for-review language.",
            "Separate proven source facts from candidate evidence.",
            "Do not claim fit, approval, safety, interchangeability, or modification permission.",
            "Clearly list missing dimension/effectivity/interface evidence.",
        ]
    else:
        answer_mode = "engineering_triage"
        instructions = [
            "Answer as engineering triage only.",
            "Separate source-backed facts, candidates, and missing evidence.",
            "Do not overclaim beyond source evidence.",
        ]

    return {
        "answer_mode": answer_mode,
        "draft_instructions": instructions,
        "self_rag_status": self_rag.get("self_rag_status"),
        "evidence_strength_score": self_rag.get("evidence_strength_score"),
        "source_truth_evidence_strength": self_rag.get("source_truth_evidence_strength"),
        "route_coverage_status": (self_rag.get("route_coverage") or {}).get("route_coverage_status"),
        "draft_permission_scope": "gemma_draft_context_only_not_final_answer",
    }


def _prompt_contract(pack: Mapping[str, Any], self_rag: Mapping[str, Any]) -> Dict[str, Any]:
    sections = _context_sections_by_id(pack)
    missing = pack.get("missing_evidence") or []
    forbidden = pack.get("forbidden_answer_claims") or []
    return {
        "system_role": (
            "You are an engineering evidence drafting assistant for TRACE-Net. "
            "You may draft a response from the provided context only. "
            "You must separate source-backed facts, candidates, and missing evidence."
        ),
        "non_negotiable_rules": [
            "Do not use knowledge outside this packet.",
            "Do not invent part relationships, dimensions, procedures, warnings, or approvals.",
            "Do not state approved replacement, guaranteed fit, safe to install, or engineering approval unless explicitly present in source evidence.",
            "Do not treat visual, graph, or semantic evidence as exact proof.",
            "If evidence is missing, say it is missing.",
            "This is a draft only; final answer permission is not granted.",
        ],
        "user_question": pack.get("user_question"),
        "structured_user_intent": (
            sections.get("structured_user_intent", {}).get("content")
            if isinstance(sections.get("structured_user_intent"), dict)
            else {
                "seed_entities": pack.get("seed_entities") or [],
                "requested_change": pack.get("requested_change"),
            }
        ),
        "selected_playbook": {
            "selected_playbook_id": pack.get("selected_playbook_id"),
            "intent_family": pack.get("intent_family"),
        },
        "draft_instruction_block": _draft_instruction_block(pack, self_rag),
        "source_truth_evidence": _source_truth_capsules(pack),
        "candidate_evidence": _candidate_capsules(pack),
        "missing_evidence": missing,
        "forbidden_claims": forbidden,
        "answer_format_contract": pack.get("answer_format_contract"),
        "self_rag_summary": {
            "self_rag_record_id": self_rag.get("self_rag_record_id"),
            "evidence_strength_score": self_rag.get("evidence_strength_score"),
            "source_truth_evidence_strength": self_rag.get("source_truth_evidence_strength"),
            "capsule_counts": self_rag.get("capsule_counts"),
            "route_coverage": self_rag.get("route_coverage"),
        },
    }


def build_draft_packet_record(
    *,
    pack: Mapping[str, Any],
    self_rag: Mapping[str, Any],
    index: int,
) -> Dict[str, Any]:
    source_truth = _source_truth_capsules(pack)
    candidate = _candidate_capsules(pack)
    prompt_contract = _prompt_contract(pack, self_rag)
    evidence_score = int(self_rag.get("evidence_strength_score") or 0)

    return {
        "draft_packet_version": MODULE_VERSION,
        "draft_packet_id": f"engineering_draft_packet_{index+1:04d}",
        "source_context_pack_id": pack.get("context_pack_id"),
        "source_self_rag_record_id": self_rag.get("self_rag_record_id"),
        "question_id": pack.get("question_id"),
        "user_question": pack.get("user_question"),
        "intent_family": pack.get("intent_family"),
        "selected_playbook_id": pack.get("selected_playbook_id"),
        "draft_packet_status": "ready_for_gemma_draft_context_only",
        "gemma_model_role": "draft_from_packet_only",
        "prompt_contract": prompt_contract,
        "source_truth_capsule_count": len(source_truth),
        "candidate_capsule_count": len(candidate),
        "missing_evidence_count": len(pack.get("missing_evidence") or []),
        "forbidden_claim_count": len(pack.get("forbidden_answer_claims") or []),
        "evidence_strength_score": evidence_score,
        "source_truth_evidence_strength": self_rag.get("source_truth_evidence_strength"),
        "ready_for_gemma_draft": True,
        "ready_for_final_answer": False,
        "requires_final_gate_after_draft": True,
        "answers_user_question": False,
        "llm_call_allowed": False,
        "retrieval_execution_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": False,
    }


def build_engineering_context_draft_packet(
    *,
    context_pack_path: Path,
    self_rag_report_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    context_payload = _read_json(context_pack_path)
    self_rag_payload = _read_json(self_rag_report_path)
    packs = context_payload.get("records") or []
    self_rag_records = self_rag_payload.get("records") or []

    records: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        pack_id = str(pack.get("context_pack_id") or "")
        self_rag = _find_self_rag_for_pack(self_rag_records, pack_id)
        if not self_rag:
            skipped.append({
                "context_pack_id": pack_id,
                "reason": "missing_self_rag_record",
            })
            continue
        if not self_rag.get("ready_for_gemma_draft"):
            skipped.append({
                "context_pack_id": pack_id,
                "reason": "self_rag_not_ready_for_gemma_draft",
                "self_rag_status": self_rag.get("self_rag_status"),
                "crag_retry_required": self_rag.get("crag_retry_required"),
            })
            continue
        records.append(build_draft_packet_record(pack=pack, self_rag=self_rag, index=len(records)))

    intent_counts = Counter(record.get("intent_family") for record in records)
    status_counts = Counter(record.get("draft_packet_status") for record in records)

    summary = {
        "source_context_pack_builder_quality_status": context_payload.get("quality_status"),
        "source_self_rag_quality_status": self_rag_payload.get("quality_status"),
        "source_context_pack_count": len(packs),
        "source_self_rag_record_count": len(self_rag_records),
        "draft_packet_count": len(records),
        "skipped_context_pack_count": len(skipped),
        "draft_packet_status_counts": dict(sorted(status_counts.items())),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "ready_for_gemma_draft_count": sum(1 for r in records if r.get("ready_for_gemma_draft")),
        "ready_for_final_answer_count": sum(1 for r in records if r.get("ready_for_final_answer")),
        "requires_final_gate_after_draft_count": sum(1 for r in records if r.get("requires_final_gate_after_draft")),
        "total_source_truth_capsule_count": sum(r.get("source_truth_capsule_count", 0) for r in records),
        "total_candidate_capsule_count": sum(r.get("candidate_capsule_count", 0) for r in records),
        "total_missing_evidence_count": sum(r.get("missing_evidence_count", 0) for r in records),
        "skipped_context_packs": skipped,
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "llm_call_allowed_count": sum(1 for r in records if r.get("llm_call_allowed")),
        "retrieval_execution_allowed_count": sum(1 for r in records if r.get("retrieval_execution_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
    }

    quality_status = "PASS"
    if context_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if self_rag_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_CONTEXT_DRAFT_PACKET_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_context_pack_builder_path": str(context_pack_path),
        "source_self_rag_report_path": str(self_rag_report_path),
        "records": records,
        "safety_contract": {
            "artifact_authority": "gemma_draft_packet_context_only",
            "answers_user_question": False,
            "llm_call_allowed": False,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "ready_for_final_answer": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_context_draft_packet_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_context_draft_packet_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_context_draft_packet_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_context_draft_packet_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Context Draft Packet v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Draft packets: {summary.get('draft_packet_count')}",
        f"- Skipped context packs: {summary.get('skipped_context_pack_count')}",
        f"- Ready for Gemma draft: {summary.get('ready_for_gemma_draft_count')}",
        f"- Ready for final answer: {summary.get('ready_for_final_answer_count')}",
        f"- Requires final gate after draft: {summary.get('requires_final_gate_after_draft_count')}",
        f"- Source-truth capsules: {summary.get('total_source_truth_capsule_count')}",
        f"- Candidate capsules: {summary.get('total_candidate_capsule_count')}",
        "",
        "## Draft packets",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('draft_packet_id')} — {record.get('intent_family')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Playbook: `{record.get('selected_playbook_id')}`",
            f"- Evidence score: `{record.get('evidence_strength_score')}`",
            f"- Source-truth strength: `{record.get('source_truth_evidence_strength')}`",
            f"- Source-truth capsules: `{record.get('source_truth_capsule_count')}`",
            f"- Candidate capsules: `{record.get('candidate_capsule_count')}`",
            f"- Ready for Gemma draft: `{record.get('ready_for_gemma_draft')}`",
            f"- Ready for final answer: `{record.get('ready_for_final_answer')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_context_draft_packet_quality(
    *,
    report_path: Path,
    require_source_context_pack_quality_pass: bool = False,
    require_source_self_rag_quality_pass: bool = False,
    min_draft_packets: int = 1,
    min_ready_for_gemma_draft: int = 1,
    max_ready_for_final_answer: int = 0,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_llm_calls: bool = False,
    require_no_retrieval_execution: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_context_pack_quality_pass:
        fail_if(summary.get("source_context_pack_builder_quality_status") != "PASS", "source context pack quality is not PASS")
    if require_source_self_rag_quality_pass:
        fail_if(summary.get("source_self_rag_quality_status") != "PASS", "source Self-RAG quality is not PASS")
    fail_if(summary.get("draft_packet_count", 0) < min_draft_packets, "not enough draft packets")
    fail_if(summary.get("ready_for_gemma_draft_count", 0) < min_ready_for_gemma_draft, "not enough packets ready for Gemma draft")
    fail_if(summary.get("ready_for_final_answer_count", 0) > max_ready_for_final_answer, "too many packets ready for final answer")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "LLM call allowed count not zero")
    if require_no_retrieval_execution:
        fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context draft packet v1.")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--self-rag-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_context_draft_packet(
        context_pack_path=Path(args.context_pack),
        self_rag_report_path=Path(args.self_rag_report),
        output_dir=Path(args.output_dir),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context draft packet v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-context-pack-quality-pass", action="store_true")
    parser.add_argument("--require-source-self-rag-quality-pass", action="store_true")
    parser.add_argument("--min-draft-packets", type=int, default=1)
    parser.add_argument("--min-ready-for-gemma-draft", type=int, default=1)
    parser.add_argument("--max-ready-for-final-answer", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_context_draft_packet_quality(
        report_path=Path(args.report_path),
        require_source_context_pack_quality_pass=args.require_source_context_pack_quality_pass,
        require_source_self_rag_quality_pass=args.require_source_self_rag_quality_pass,
        min_draft_packets=args.min_draft_packets,
        min_ready_for_gemma_draft=args.min_ready_for_gemma_draft,
        max_ready_for_final_answer=args.max_ready_for_final_answer,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_llm_calls=args.require_no_llm_calls,
        require_no_retrieval_execution=args.require_no_retrieval_execution,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_context_draft_packet_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
