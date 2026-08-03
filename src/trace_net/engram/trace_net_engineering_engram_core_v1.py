from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

MODULE = "trace_net_engineering_engram_core_v1"
VERSION = "v1"

SAFETY_ZERO_FIELDS = [
    "answer_permission_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "opensearch_upload_attempt_count",
    "write_attempt_count",
    "unsafe_record_count",
]


def _read_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "engram_id",
        "memory_type",
        "priority",
        "trait",
        "trigger_text",
        "rule",
        "source",
        "status",
    ]
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _csv_value(r.get(k)) for k in fieldnames})


def _csv_value(v: Any) -> str:
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return ""
    return str(v)


def _as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _default_memory_atoms() -> List[Dict[str, Any]]:
    """Seed TRACE-Net's first engineering engram from H11-H14C lessons."""
    return [
        {
            "engram_id": "policy_no_interchangeability_without_authority_v1",
            "memory_type": "policy_trait",
            "priority": "hard_boundary",
            "trait": "source_trace_caution",
            "triggers": ["interchangeability", "approved replacement", "replacement approval", "shared nomenclature"],
            "trigger_text": "interchangeability | replacement approval | shared nomenclature",
            "rule": "Shared nomenclature, nearby figures, or part-family similarity are not proof of interchangeability or replacement approval.",
            "good_behavior": "Say what TRACE-Net can prove about each part, then state interchangeability/replacement approval is not proven.",
            "bad_behavior": "Treating the same description or part-family proximity as approval or interchangeability.",
            "source": "H14C llm smoke repair",
            "status": "active",
        },
        {
            "engram_id": "policy_no_installation_safety_from_figure_v1",
            "memory_type": "policy_trait",
            "priority": "hard_boundary",
            "trait": "approval_boundary",
            "triggers": ["installation safety", "safe install", "fit approval", "aircraft effectivity"],
            "trigger_text": "installation safety | fit approval | aircraft effectivity",
            "rule": "Figure/part identification evidence does not prove installation safety, fit approval, aircraft effectivity, or replacement approval.",
            "good_behavior": "Lead with not proven, then list the source-trace-ready identity/nomenclature evidence that is proven.",
            "bad_behavior": "Implying a figure, OCR line, or part listing authorizes installation or fit.",
            "source": "H14C llm smoke repair",
            "status": "active",
        },
        {
            "engram_id": "policy_v2_summaries_guidance_not_proof_v1",
            "memory_type": "policy_trait",
            "priority": "hard_boundary",
            "trait": "summary_boundary",
            "triggers": ["v2 summary", "summaries", "summary proof", "summary-only"],
            "trigger_text": "v2 summary | summary-only proof",
            "rule": "V2 summaries may guide planning and framing, but cannot prove source claims; factual claims require proof_context citations.",
            "good_behavior": "Use summaries only to guide route selection and answer framing; cite proof_context for claims.",
            "bad_behavior": "Using a v2 summary as direct evidence for part identity or approval.",
            "source": "H10/H14C semantic eval",
            "status": "active",
        },
        {
            "engram_id": "route_visual_link_vs_ocr_nomenclature_v1",
            "memory_type": "route_behavior",
            "priority": "high",
            "trait": "route_awareness",
            "triggers": ["visual route", "OCR nomenclature", "nomenclature missing", "figure identity"],
            "trigger_text": "visual route | OCR nomenclature | nomenclature missing",
            "rule": "visual_figure_link establishes figure-to-part identity; ocr_nomenclature provides OCR-backed line-text name proof.",
            "good_behavior": "Explain both routes separately when asked evidence-support or pipeline questions.",
            "bad_behavior": "Saying only 'not proven' for pipeline questions when route behavior evidence is available.",
            "source": "H14C safe reasoning traces",
            "status": "active",
        },
        {
            "engram_id": "route_table_ocr_supports_exact_part_v1",
            "memory_type": "route_behavior",
            "priority": "medium",
            "trait": "route_awareness",
            "triggers": ["table OCR", "exact part", "part lookup", "evidence supports"],
            "trigger_text": "table OCR | exact part lookup | evidence support",
            "rule": "Exact-part/table-OCR evidence supports presence of a part number but does not by itself prove approvals or compatibility.",
            "good_behavior": "Use table/OCR evidence to support part presence and citation readiness, while keeping approval claims out of scope.",
            "bad_behavior": "Converting a table hit into effectivity, fit, or replacement authority.",
            "source": "H11-H14C smoke evals",
            "status": "active",
        },
        {
            "engram_id": "style_engineering_answer_shape_v1",
            "memory_type": "style_trait",
            "priority": "high",
            "trait": "engineering_answer_shape",
            "triggers": ["engineering answer", "limitations", "evidence", "confidence"],
            "trigger_text": "engineering answer | limitations | evidence",
            "rule": "Prefer answer sections: Answer, Evidence, Engineering confidence, Limits; for limitations questions, split Can prove vs Cannot prove.",
            "good_behavior": "Give a concise direct answer, then cite proof and state limits.",
            "bad_behavior": "Generic disclaimer-only answers, or citation dumps without answering the actual intent.",
            "source": "H14C llm answer style",
            "status": "active",
        },
        {
            "engram_id": "style_useful_not_proven_v1",
            "memory_type": "style_trait",
            "priority": "high",
            "trait": "useful_caution",
            "triggers": ["not proven", "cannot prove", "not source-trace-ready"],
            "trigger_text": "not proven | cannot prove | not source-trace-ready",
            "rule": "When a claim is not proven, still explain what TRACE-Net can prove and why the requested claim is outside the evidence.",
            "good_behavior": "Not proven + can prove identity/nomenclature/pages + cannot prove approval/safety/effectivity.",
            "bad_behavior": "Only saying 'not proven' without useful evidence context.",
            "source": "H13 over-refusal repair through H14C",
            "status": "active",
        },
        {
            "engram_id": "style_unknown_part_or_figure_v1",
            "memory_type": "style_trait",
            "priority": "medium",
            "trait": "unknown_handling",
            "triggers": ["unknown part", "unknown figure", "not found", "999"],
            "trigger_text": "unknown part | unknown figure | not found",
            "rule": "For unknown part/figure questions with no proof_context, lead with not found / not source-trace-ready and do not cite unrelated evidence.",
            "good_behavior": "State no proof_context was available and avoid unrelated citations.",
            "bad_behavior": "Citing nearby known figures or parts for an unknown requested identifier.",
            "source": "H14C partial unknown handling",
            "status": "active",
        },
        {
            "engram_id": "episode_h13_generic_not_proven_v1",
            "memory_type": "episodic_failure_memory",
            "priority": "high",
            "trait": "failure_memory",
            "triggers": ["pipeline question", "debug question", "nomenclature missing"],
            "trigger_text": "pipeline/debug questions over-refused",
            "rule": "H13/H14 initially answered pipeline/debug questions with generic 'not proven'; H14C repaired this using scaffold + route-specific intent rules.",
            "good_behavior": "Explain route behavior when the scaffold describes pipeline behavior; distinguish pipeline explanation from source-truth proof.",
            "bad_behavior": "Blank/blocked or generic not-proven answers for route behavior questions.",
            "source": "H13-H14C eval history",
            "status": "active",
        },
        {
            "engram_id": "episode_h14b_path_length_stage_output_v1",
            "memory_type": "episodic_failure_memory",
            "priority": "medium",
            "trait": "failure_memory",
            "triggers": ["Windows path", "quality_check missing", "stage output", "FileNotFoundError"],
            "trigger_text": "Windows path length | missing quality_check",
            "rule": "H14B exposed nested stage-output path failures; H14C used shorter output dirs and safe trace records to prevent blocked answers.",
            "good_behavior": "Use short run directories and record safe failure traces instead of letting path plumbing block question evaluation.",
            "bad_behavior": "Long nested run directories that prevent quality-check artifacts from being written/read on Windows.",
            "source": "H14B/H14C path hardening",
            "status": "active",
        },
        {
            "engram_id": "critic_answer_behavior_self_rag_v1",
            "memory_type": "critic_trait",
            "priority": "high",
            "trait": "self_rag_behavior_check",
            "triggers": ["answer critique", "Self-RAG", "unsupported claim", "intent mismatch"],
            "trigger_text": "Self-RAG answer behavior critique",
            "rule": "Self-RAG should check whether the draft obeys source-trace boundaries, answers the actual intent, cites claims, and avoids over/under-refusal.",
            "good_behavior": "Critique answers for evidence support and behavior correctness before delivery.",
            "bad_behavior": "Only checking citation existence while missing semantic intent failure.",
            "source": "H10 semantic answer quality eval",
            "status": "active",
        },
        {
            "engram_id": "repair_crag_engram_repair_v1",
            "memory_type": "repair_trait",
            "priority": "high",
            "trait": "crag_repair_reflex",
            "triggers": ["CRAG", "repair", "weak answer", "retry"],
            "trigger_text": "CRAG repair | weak answer retry",
            "rule": "CRAG should retrieve relevant failure/repair engrams and regenerate or rewrite the answer when Self-RAG flags weak behavior or weak evidence.",
            "good_behavior": "Use retrieved repair patterns such as 'shared nomenclature is not interchangeability' to fix weak drafts.",
            "bad_behavior": "Retrying the same prompt without adding behavior memory or evidence diagnostics.",
            "source": "TRACE-Net engram architecture plan",
            "status": "active",
        },
    ]


def _summarize_smoke(path: Any) -> Dict[str, Any]:
    data = _read_json(path)
    summary = dict(data.get("summary") or {})
    records = list(data.get("records") or [])
    grade_counts = Counter(str(r.get("grade") or "") for r in records)
    category_counts = Counter(str(r.get("category") or "") for r in records)
    partial_categories = sorted({str(r.get("category")) for r in records if r.get("grade") == "PARTIAL"})
    blocked_categories = sorted({str(r.get("category")) for r in records if r.get("grade") == "BLOCKED"})
    bad_categories = sorted({str(r.get("category")) for r in records if r.get("grade") == "BAD"})
    return {
        "path": str(path),
        "quality_status": data.get("quality_status"),
        "summary": summary,
        "record_count": len(records),
        "grade_counts": dict(grade_counts),
        "category_counts": dict(category_counts),
        "partial_categories": partial_categories,
        "blocked_categories": blocked_categories,
        "bad_categories": bad_categories,
    }


def _eval_memory_atoms(eval_summaries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    atoms: List[Dict[str, Any]] = []
    for idx, ev in enumerate(eval_summaries, 1):
        summary = dict(ev.get("summary") or {})
        q = summary.get("smoke_question_count") or ev.get("record_count")
        good = summary.get("good_answer_count", 0)
        partial = summary.get("partial_answer_count", 0)
        bad = summary.get("bad_answer_count", 0)
        blocked = summary.get("blocked_answer_count", 0)
        unsupported = summary.get("unsupported_claim_count", 0)
        atoms.append({
            "engram_id": f"episode_llm_smoke_result_{idx:02d}_v1",
            "memory_type": "episodic_eval_memory",
            "priority": "medium",
            "trait": "eval_history",
            "triggers": ["LLM smoke", "answer quality", "eval history"],
            "trigger_text": "LLM smoke eval history",
            "rule": f"Observed eval result: {good} GOOD, {partial} PARTIAL, {bad} BAD, {blocked} BLOCKED out of {q}; unsupported_claim_count={unsupported}.",
            "good_behavior": "Reuse high-performing answer patterns and keep safety counters at zero.",
            "bad_behavior": "Ignore prior eval failures or regress on unsupported claims.",
            "source": str(ev.get("path") or "smoke_eval"),
            "status": "active",
        })
        for cat in _as_list(ev.get("partial_categories")):
            if cat:
                atoms.append({
                    "engram_id": f"episode_partial_category_{idx:02d}_{_slug(cat)}_v1",
                    "memory_type": "episodic_failure_memory",
                    "priority": "medium",
                    "trait": "partial_answer_memory",
                    "triggers": [cat, "partial answer", "quality improvement"],
                    "trigger_text": f"partial category: {cat}",
                    "rule": f"Category '{cat}' was graded PARTIAL in a smoke eval; retrieve a more specific answer pattern before drafting.",
                    "good_behavior": "Explain the boundary and the available proof rather than generic refusal.",
                    "bad_behavior": "Generic not-proven or incomplete answer for a known weak category.",
                    "source": str(ev.get("path") or "smoke_eval"),
                    "status": "active",
                })
    return atoms


def _slug(text: Any, max_len: int = 48) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "").lower()).strip("_")
    return (s or "item")[:max_len]


def _quality_gate(
    atoms: Sequence[Mapping[str, Any]],
    eval_summaries: Sequence[Mapping[str, Any]],
    *,
    min_engram_atoms: int,
    min_policy_traits: int,
    min_memory_types: int,
    max_unsafe: int,
    max_write_attempts: int,
    require_eval_source_pass: bool,
) -> Dict[str, Any]:
    memory_types = Counter(str(a.get("memory_type") or "") for a in atoms)
    policy_trait_count = memory_types.get("policy_trait", 0)
    failures: List[str] = []
    if len(atoms) < min_engram_atoms:
        failures.append(f"engram_atom_count below minimum: {len(atoms)} < {min_engram_atoms}")
    if policy_trait_count < min_policy_traits:
        failures.append(f"policy_trait_count below minimum: {policy_trait_count} < {min_policy_traits}")
    if len([m for m in memory_types if m]) < min_memory_types:
        failures.append(f"memory_type_count below minimum: {len(memory_types)} < {min_memory_types}")
    if max_unsafe < 0:
        failures.append("max_unsafe cannot be negative")
    if max_write_attempts < 0:
        failures.append("max_write_attempts cannot be negative")
    if require_eval_source_pass:
        for ev in eval_summaries:
            if ev.get("quality_status") != "PASS":
                failures.append(f"eval source is not PASS: {ev.get('path')}")
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "engram_atom_count": len(atoms),
        "policy_trait_count": policy_trait_count,
        "memory_type_count": len([m for m in memory_types if m]),
    }


def build_engram_core(
    output_dir: Any,
    smoke_test: Optional[Sequence[Any]] = None,
    min_engram_atoms: int = 10,
    min_policy_traits: int = 3,
    min_memory_types: int = 5,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    require_quality_pass: bool = False,
    require_eval_source_pass: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_summaries: List[Dict[str, Any]] = []
    for p in _as_list(smoke_test):
        if p:
            eval_summaries.append(_summarize_smoke(p))

    atoms = _default_memory_atoms() + _eval_memory_atoms(eval_summaries)
    memory_types = Counter(str(a.get("memory_type") or "") for a in atoms)
    priorities = Counter(str(a.get("priority") or "") for a in atoms)
    traits = sorted({str(a.get("trait") or "") for a in atoms if a.get("trait")})

    safety = {
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }

    qg = _quality_gate(
        atoms,
        eval_summaries,
        min_engram_atoms=min_engram_atoms,
        min_policy_traits=min_policy_traits,
        min_memory_types=min_memory_types,
        max_unsafe=max_unsafe,
        max_write_attempts=max_write_attempts,
        require_eval_source_pass=require_eval_source_pass,
    )

    for field, value in [
        ("answer_permission_count", safety["answer_permission_count"]),
        ("source_truth_mutation_allowed_count", safety["source_truth_mutation_allowed_count"]),
        ("unsafe_record_count", safety["unsafe_record_count"]),
        ("write_attempt_count", safety["write_attempt_count"]),
    ]:
        limit = {
            "answer_permission_count": max_answer_permission,
            "source_truth_mutation_allowed_count": max_source_truth_mutation_allowed,
            "unsafe_record_count": max_unsafe,
            "write_attempt_count": max_write_attempts,
        }[field]
        if value > limit:
            qg["failures"].append(f"{field} above maximum: {value} > {limit}")
    qg["quality_status"] = "PASS" if not qg.get("failures") else "FAIL"

    summary = {
        "module": MODULE,
        "version": VERSION,
        "engram_atom_count": len(atoms),
        "policy_trait_count": memory_types.get("policy_trait", 0),
        "style_trait_count": memory_types.get("style_trait", 0),
        "route_behavior_count": memory_types.get("route_behavior", 0),
        "episodic_failure_memory_count": memory_types.get("episodic_failure_memory", 0),
        "episodic_eval_memory_count": memory_types.get("episodic_eval_memory", 0),
        "critic_trait_count": memory_types.get("critic_trait", 0),
        "repair_trait_count": memory_types.get("repair_trait", 0),
        "memory_type_count": len([m for m in memory_types if m]),
        "hard_boundary_count": priorities.get("hard_boundary", 0),
        "eval_source_count": len(eval_summaries),
        "traits": traits,
        "ready_for_engram_prompt_injector": qg["quality_status"] == "PASS",
        **safety,
    }

    traits_pack = {
        "module": "trace_net_engineering_engram_traits_v1",
        "version": VERSION,
        "quality_status": qg["quality_status"],
        "records": [a for a in atoms if str(a.get("memory_type", "")).endswith("trait") or a.get("memory_type") in {"policy_trait", "style_trait", "critic_trait", "repair_trait"}],
        "summary": {
            "trait_record_count": sum(1 for a in atoms if str(a.get("memory_type", "")).endswith("trait") or a.get("memory_type") in {"policy_trait", "style_trait", "critic_trait", "repair_trait"}),
            "policy_trait_count": memory_types.get("policy_trait", 0),
            "style_trait_count": memory_types.get("style_trait", 0),
            "critic_trait_count": memory_types.get("critic_trait", 0),
            "repair_trait_count": memory_types.get("repair_trait", 0),
        },
    }

    memory_pack = {
        "module": "trace_net_engineering_engram_memory_atoms_v1",
        "version": VERSION,
        "quality_status": qg["quality_status"],
        "records": atoms,
        "summary": {
            "engram_atom_count": len(atoms),
            "memory_types": dict(memory_types),
            "priorities": dict(priorities),
        },
    }

    result = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_ENGINEERING_ENGRAM_CORE_BUILT",
        "quality_status": qg["quality_status"],
        "summary": summary,
        "quality_gate": qg,
        "records": atoms,
        "eval_summaries": eval_summaries,
        "safety_contract": {
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "note": "H15 builds a local JSON engram profile only; Qdrant/Postgres loading is reserved for later adapter stages.",
        },
    }

    core_path = out_dir / "trace_net_engineering_engram_core_v1.json"
    memory_path = out_dir / "trace_net_engineering_engram_memory_atoms_v1.json"
    traits_path = out_dir / "trace_net_engineering_engram_traits_v1.json"
    qc_path = out_dir / "trace_net_engineering_engram_core_v1_quality_check.json"
    csv_path = out_dir / "trace_net_engineering_engram_memory_atoms_v1.csv"

    _write_json(core_path, result)
    _write_json(memory_path, memory_pack)
    _write_json(traits_path, traits_pack)
    _write_json(qc_path, {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_ENGINEERING_ENGRAM_CORE_QUALITY_CHECKED",
        "quality_status": qg["quality_status"],
        "summary": summary,
        "quality_gate": qg,
    })
    _write_csv(csv_path, atoms)

    result["paths"] = {
        "core": str(core_path),
        "memory_atoms": str(memory_path),
        "traits": str(traits_path),
        "quality_check": str(qc_path),
        "csv": str(csv_path),
    }
    _write_json(core_path, result)

    if require_quality_pass and qg["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")
    return result


def check_engram_core(
    engram_core: Any,
    output: Any,
    min_engram_atoms: int = 10,
    min_policy_traits: int = 3,
    min_memory_types: int = 5,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    require_quality_pass: bool = False,
) -> Dict[str, Any]:
    data = _read_json(engram_core)
    records = list(data.get("records") or [])
    eval_summaries = list(data.get("eval_summaries") or [])
    qg = _quality_gate(
        records,
        eval_summaries,
        min_engram_atoms=min_engram_atoms,
        min_policy_traits=min_policy_traits,
        min_memory_types=min_memory_types,
        max_unsafe=max_unsafe,
        max_write_attempts=max_write_attempts,
        require_eval_source_pass=False,
    )
    summary = dict(data.get("summary") or {})
    failures = list(qg.get("failures") or [])
    for field, limit in [
        ("unsafe_record_count", max_unsafe),
        ("answer_permission_count", max_answer_permission),
        ("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed),
        ("write_attempt_count", max_write_attempts),
    ]:
        value = int(summary.get(field) or 0)
        if value > limit:
            failures.append(f"{field} above maximum: {value} > {limit}")
    if data.get("quality_status") != "PASS":
        failures.append("source engram_core quality_status is not PASS")
    result = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_ENGINEERING_ENGRAM_CORE_QUALITY_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "summary": summary,
        "quality_gate": {**qg, "failures": failures, "quality_status": "PASS" if not failures else "FAIL"},
    }
    _write_json(output, result)
    if require_quality_pass and result["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")
    return result


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Core v1")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--smoke-test", action="append", default=[])
    p.add_argument("--min-engram-atoms", type=int, default=10)
    p.add_argument("--min-policy-traits", type=int, default=3)
    p.add_argument("--min-memory-types", type=int, default=5)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-eval-source-pass", action="store_true")
    return p


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    result = build_engram_core(
        output_dir=args.output_dir,
        smoke_test=args.smoke_test,
        min_engram_atoms=args.min_engram_atoms,
        min_policy_traits=args.min_policy_traits,
        min_memory_types=args.min_memory_types,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
        require_quality_pass=args.require_quality_pass,
        require_eval_source_pass=args.require_eval_source_pass,
    )
    s = result.get("summary", {})
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("engram_atom_count=" + str(s.get("engram_atom_count")))
    print("policy_trait_count=" + str(s.get("policy_trait_count")))
    print("memory_type_count=" + str(s.get("memory_type_count")))
    print("ready_for_engram_prompt_injector=" + str(s.get("ready_for_engram_prompt_injector")))
    print("engram_core=" + str(result.get("paths", {}).get("core")))
    return 0


def _check_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Core v1")
    p.add_argument("--engram-core", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--min-engram-atoms", type=int, default=10)
    p.add_argument("--min-policy-traits", type=int, default=3)
    p.add_argument("--min-memory-types", type=int, default=5)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    p.add_argument("--require-quality-pass", action="store_true")
    return p


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    args = _check_parser().parse_args(argv)
    result = check_engram_core(
        engram_core=args.engram_core,
        output=args.output,
        min_engram_atoms=args.min_engram_atoms,
        min_policy_traits=args.min_policy_traits,
        min_memory_types=args.min_memory_types,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
        require_quality_pass=args.require_quality_pass,
    )
    s = result.get("summary", {})
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("engram_atom_count=" + str(s.get("engram_atom_count")))
    print("policy_trait_count=" + str(s.get("policy_trait_count")))
    print("memory_type_count=" + str(s.get("memory_type_count")))
    return 0


if __name__ == "__main__":
    main_build()
