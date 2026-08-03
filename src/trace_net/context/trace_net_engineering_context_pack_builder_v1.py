
"""TRACE-Net Engineering Context Pack Builder v1.

Fills engineering context-pack blueprints with available TRACE-Net artifacts.

v1.2:
- optional artifact paths no longer crash when missing
- missing optional artifacts are recorded in artifact_missing_inputs
- quality checker can require no required-missing inputs while allowing optional missing inputs

Safety:
- no LLM calls
- no live retrieval execution
- no DB writes
- no source-truth mutation
- no answer permission
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


MODULE_VERSION = "trace_net_engineering_context_pack_builder_v1"
REPORT_NAME = "trace_net_engineering_context_pack_builder_v1.json"

TEXT_KEYS = (
    "text", "sample", "sample_text", "content", "body", "snippet", "ocr_text",
    "fishnet_ocr_sample_text", "page_text", "page_summary", "page_summary_v2",
    "summary", "description", "title", "nomenclature", "covered_part_number",
    "part_number", "manual_page_reference", "field_value", "value", "source_text",
    "normalized_value", "raw_value", "query", "answer", "evidence_text",
    "source_excerpt", "record_text", "callout_text", "warning", "caution", "note",
)

PAGE_KEYS = (
    "page_id", "source_page_id", "current_route_manifest_page_id",
    "source_trace_page_id", "page", "document_page_id", "manual_page_id",
    "page_ref", "source_page_ref",
)

TECHNICAL_STRING_KEYS = {
    "source_artifact_path", "_artifact_path", "path", "file_path", "output_path",
    "report_path", "json_path", "image_path", "overlay_path", "schema", "module",
    "status", "quality_status", "version",
}

PRIORITY_LIST_KEYS = (
    "records", "cards", "items", "pages", "documents", "evidence_documents",
    "search_documents", "exact_search_documents", "table_exact_search_documents",
    "adapter_documents", "search_ready_documents", "page_context_records",
    "route_records", "route_handoff_records", "accepted_delta_records",
    "table_records", "community_records", "nodes", "edges", "matches",
    "results", "candidate_records", "workbench_cards", "policy_records",
)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotErrorForOptional(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


class FileNotErrorForOptional(FileNotFoundError):
    pass


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _looks_like_record(record: Mapping[str, Any]) -> bool:
    keys = set(record.keys())
    if keys.intersection(PAGE_KEYS):
        return True
    if keys.intersection(TEXT_KEYS):
        return True
    if {"route", "accepted_route", "selected_route"}.intersection(keys):
        return True
    if {"source_trace", "source_trace_ready", "citation_ready"}.intersection(keys):
        return True
    if {"part_number", "covered_part_number", "manual_page_reference", "field_name", "field_value"}.intersection(keys):
        return True
    scalars = 0
    for value in record.values():
        if isinstance(value, (str, int, float)) and str(value).strip():
            scalars += 1
    return scalars >= 3


def _flatten_records(payload: Any, *, max_records: int = 20000) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: Set[int] = set()

    def add(record: Mapping[str, Any]) -> None:
        if len(records) >= max_records:
            return
        ident = id(record)
        if ident in seen:
            return
        seen.add(ident)
        if _looks_like_record(record):
            records.append(dict(record))

    def walk(obj: Any, depth: int = 0) -> None:
        if len(records) >= max_records or depth > 8:
            return
        if isinstance(obj, list):
            if obj and all(isinstance(item, dict) for item in obj):
                for item in obj:
                    add(item)
                    walk(item, depth + 1)
            else:
                for item in obj[:200]:
                    walk(item, depth + 1)
        elif isinstance(obj, dict):
            for key in PRIORITY_LIST_KEYS:
                value = obj.get(key)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            add(item)
                            walk(item, depth + 1)
                elif isinstance(value, dict):
                    walk(value, depth + 1)
            for value in obj.values():
                if len(records) >= max_records:
                    break
                if isinstance(value, (dict, list)):
                    walk(value, depth + 1)

    if isinstance(payload, dict):
        add(payload)
    walk(payload)
    return records


def _recursive_text_values(obj: Any, limit: int = 100) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()

    def maybe_add(key: str, value: Any) -> None:
        if len(out) >= limit:
            return
        if value in (None, "") or isinstance(value, bool):
            return
        text = str(value).strip()
        if not text:
            return
        if key in TECHNICAL_STRING_KEYS and len(text) > 40:
            return
        if ("/" in text or "\\" in text) and len(text) > 80:
            return
        if text not in seen:
            seen.add(text)
            out.append(text)

    def walk(value: Any, key_hint: str = "") -> None:
        if len(out) >= limit:
            return
        if isinstance(value, dict):
            for key in TEXT_KEYS:
                if key in value:
                    inner = value.get(key)
                    if isinstance(inner, (str, int, float)):
                        maybe_add(key, inner)
                    elif isinstance(inner, (dict, list)):
                        walk(inner, key)
            for key, inner in value.items():
                if isinstance(inner, (str, int, float)):
                    maybe_add(key, inner)
                elif isinstance(inner, (dict, list)):
                    walk(inner, key)
        elif isinstance(value, list):
            for item in value[:50]:
                walk(item, key_hint)
        elif isinstance(value, (str, int, float)):
            maybe_add(key_hint, value)

    walk(obj)
    return out


def _recursive_first(obj: Any, keys: Sequence[str]) -> Optional[Any]:
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if value not in (None, ""):
                return value
        for value in obj.values():
            found = _recursive_first(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _recursive_first(value, keys)
            if found not in (None, ""):
                return found
    return None


def _compact_text(text: str, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:limit]


def _tokenize_question(question: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", question.lower())
    stop = {
        "the", "and", "with", "this", "that", "part", "parts", "what", "where",
        "show", "find", "need", "needs", "like", "same", "from", "into", "can",
        "any", "for", "you", "how", "does", "are", "have", "nearby", "similar",
    }
    out: List[str] = []
    seen = set()
    for token in tokens:
        if token in stop:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out[:30]


def _record_text_blob(record: Mapping[str, Any]) -> str:
    values = _recursive_text_values(record)
    return _compact_text(" ".join(values), limit=2400)


def _match_score(record: Mapping[str, Any], *, question: str, seed_entities: Sequence[str]) -> int:
    blob = _record_text_blob(record).lower()
    score = 0
    for seed in seed_entities:
        seed_norm = str(seed).lower()
        if seed_norm and seed_norm in blob:
            score += 100
        alt = seed_norm.replace("-", "_")
        if alt != seed_norm and alt in blob:
            score += 90
    for token in _tokenize_question(question):
        if token in blob:
            score += 3
    if record.get("route_changed") or record.get("route_change_authorized"):
        score += 5
    if _recursive_first(record, PAGE_KEYS):
        score += 1
    return score


def _artifact_records(path: Optional[Path], route: str, artifact_name: str, *, optional: bool = True) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if path is None:
        return [], None
    if not path.exists():
        missing = {
            "artifact_name": artifact_name,
            "route": route,
            "path": str(path),
            "optional": optional,
            "missing": True,
        }
        if optional:
            return [], missing
        raise FileNotFoundError(f"required artifact missing: {path}")
    payload = _read_json(path)
    raw = _flatten_records(payload)
    records: List[Dict[str, Any]] = []
    for idx, record in enumerate(raw):
        clone = dict(record)
        clone["_artifact_route"] = route
        clone["_artifact_name"] = artifact_name
        clone["_artifact_path"] = str(path)
        clone["_artifact_index"] = idx
        records.append(clone)
    return records, None


def _build_artifact_corpus(
    *,
    route_dispatch_handoff: Optional[Path],
    table_exact_search_adapter: Optional[Path],
    page_context_v2: Optional[Path],
    leiden_communities: Optional[Path],
    image_visual_observer: Optional[Path],
) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[Dict[str, Any]]]:
    specs = [
        ("fishnet_route_dispatch_handoff", route_dispatch_handoff, "route_dispatch", True),
        ("table_exact_search_adapter", table_exact_search_adapter, "table", True),
        ("page_context_v2", page_context_v2, "normal_text", True),
        ("leiden_communities", leiden_communities, "graph", True),
        ("image_visual_observer", image_visual_observer, "image_visual", True),
    ]
    corpus: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    missing_inputs: List[Dict[str, Any]] = []
    for name, path, route, optional in specs:
        records, missing = _artifact_records(path, route, name, optional=optional)
        corpus.extend(records)
        counts[name] = len(records)
        if missing:
            missing_inputs.append(missing)
    return corpus, counts, missing_inputs


def _trust_tier_for_route(route: str, score: int, seed_entities: Sequence[str]) -> str:
    if route == "table" and score >= 100 and seed_entities:
        return "exact_source_evidence_candidate"
    if route == "table":
        return "structured_table_candidate"
    if route == "normal_text":
        return "source_context_guidance"
    if route == "graph":
        return "relationship_candidate"
    if route == "image_visual":
        return "visual_candidate_only"
    if route == "route_dispatch":
        return "routing_metadata_not_source_truth"
    return "candidate_or_supporting"


def _evidence_capsule(record: Mapping[str, Any], *, route: str, seed_entities: Sequence[str], score: int, fallback: bool = False) -> Dict[str, Any]:
    page_id = _recursive_first(record, PAGE_KEYS)
    excerpt = _record_text_blob(record)[:900]
    return {
        "capsule_version": MODULE_VERSION,
        "route": route,
        "source_artifact": record.get("_artifact_name"),
        "source_artifact_path": record.get("_artifact_path"),
        "source_artifact_index": record.get("_artifact_index"),
        "page_id": str(page_id) if page_id not in (None, "") else None,
        "match_score": score,
        "fallback_available_context": bool(fallback),
        "trust_tier": _trust_tier_for_route(route, score, seed_entities),
        "source_text_excerpt": excerpt,
        "source_trace_ready": bool(page_id),
        "claim_authority": "candidate_or_context_until_final_gate",
        "answer_permission": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def _select_capsules_for_slot(*, slot: Mapping[str, Any], blueprint: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]], max_records_per_slot: int) -> List[Dict[str, Any]]:
    route = slot.get("route")
    question = str(blueprint.get("user_question") or "")
    seed_entities = blueprint.get("seed_entities") or []
    max_records = min(int(slot.get("max_records") or max_records_per_slot), max_records_per_slot)
    route_records = [record for record in corpus if record.get("_artifact_route") == route]
    scored = [(_match_score(record, question=question, seed_entities=seed_entities), record) for record in route_records]
    positives = [(score, record) for score, record in scored if score > 0]
    positives.sort(key=lambda item: item[0], reverse=True)
    selected = [
        _evidence_capsule(record, route=str(route), seed_entities=seed_entities, score=score)
        for score, record in positives[:max_records]
    ]
    if not selected and route_records and route in {"route_dispatch", "graph", "image_visual", "table"}:
        selected = [
            _evidence_capsule(record, route=str(route), seed_entities=seed_entities, score=0, fallback=True)
            for record in route_records[: min(max_records, 3)]
        ]
    return selected


def _missing_evidence_notes(blueprint: Mapping[str, Any], slot_capsules: Mapping[str, List[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    for slot in blueprint.get("route_evidence_slots") or []:
        route = slot.get("route")
        capsules = slot_capsules.get(route) or []
        if not capsules:
            notes.append({
                "missing_type": "route_slot_unfilled",
                "route": route,
                "reason": f"no available artifact evidence selected for route {route}",
                "crag_retry_recommended": True,
            })
        elif all(c.get("fallback_available_context") for c in capsules):
            notes.append({
                "missing_type": "route_slot_has_only_fallback_context",
                "route": route,
                "reason": f"route {route} has artifact records but no high-signal match for this question",
                "crag_retry_recommended": True,
            })
    if blueprint.get("requested_change"):
        table_capsules = slot_capsules.get("table") or []
        dimension_words = ("dimension", "length", "height", "width", "diameter", "inch", "inches", "mm", "cm")
        has_dimension_evidence = any(
            any(word in (capsule.get("source_text_excerpt") or "").lower() for word in dimension_words)
            and not capsule.get("fallback_available_context")
            for capsule in table_capsules
        )
        if not has_dimension_evidence:
            notes.append({
                "missing_type": "source_dimension_not_confirmed",
                "route": "table",
                "reason": "question requests a dimensional change but selected table evidence does not clearly prove a source dimension",
                "crag_retry_recommended": True,
            })
    if blueprint.get("intent_family") == "repair_or_fault_context":
        text = " ".join(c.get("source_text_excerpt", "") for caps in slot_capsules.values() for c in caps).lower()
        if "warning" not in text and "caution" not in text:
            notes.append({
                "missing_type": "warning_caution_not_confirmed",
                "route": "normal_text",
                "reason": "procedure question should check warnings/cautions; selected evidence did not clearly include them",
                "crag_retry_recommended": True,
            })
    return notes


def _pack_sections(blueprint: Mapping[str, Any], slot_capsules: Mapping[str, List[Mapping[str, Any]]], missing_notes: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    for contract in blueprint.get("section_contracts") or []:
        section_id = contract.get("section_id")
        if section_id == "system_engineering_role":
            content: Any = "Gemma should act as an engineering evidence assistant: separate proven facts, candidates, and missing proof."
        elif section_id == "selected_engineering_playbook":
            content = {
                "selected_playbook_id": blueprint.get("selected_playbook_id"),
                "intent_family": blueprint.get("intent_family"),
                "engineer_brain_role": blueprint.get("engineer_brain_role"),
            }
        elif section_id == "structured_user_intent":
            content = {
                "question": blueprint.get("user_question"),
                "seed_entities": blueprint.get("seed_entities"),
                "requested_change": blueprint.get("requested_change"),
            }
        elif section_id == "source_truth_evidence":
            content = {
                route: [
                    c for c in caps
                    if c.get("trust_tier") in ("exact_source_evidence_candidate", "source_context_guidance", "structured_table_candidate")
                    and not c.get("fallback_available_context")
                ]
                for route, caps in slot_capsules.items()
            }
        elif section_id == "candidate_evidence":
            content = slot_capsules
        elif section_id == "missing_evidence":
            content = list(missing_notes)
        elif section_id == "trust_tier_policy":
            content = blueprint.get("trust_tier_policy")
        elif section_id == "forbidden_claims":
            content = blueprint.get("forbidden_answer_claims")
        elif section_id == "answer_format_contract":
            content = blueprint.get("answer_format_contract")
        elif section_id == "route_handoff_availability":
            content = {
                "route_evidence_slots": [
                    {"route": slot.get("route"), "required": slot.get("required"), "trust_tier": slot.get("trust_tier")}
                    for slot in blueprint.get("route_evidence_slots") or []
                ]
            }
        else:
            content = {"section_id": section_id, "status": "reserved_for_later_context_builder"}
        sections.append({
            "section_id": section_id,
            "required": contract.get("required", True),
            "source_truth_required": contract.get("source_truth_required", False),
            "content": content,
        })
    return sections


def build_context_pack_record(*, blueprint: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]], index: int, max_records_per_slot: int) -> Dict[str, Any]:
    slot_capsules: Dict[str, List[Dict[str, Any]]] = {}
    for slot in blueprint.get("route_evidence_slots") or []:
        route = str(slot.get("route"))
        slot_capsules[route] = _select_capsules_for_slot(
            slot=slot,
            blueprint=blueprint,
            corpus=corpus,
            max_records_per_slot=max_records_per_slot,
        )
    missing_notes = _missing_evidence_notes(blueprint, slot_capsules)
    sections = _pack_sections(blueprint, slot_capsules, missing_notes)
    evidence_capsule_count = sum(len(v) for v in slot_capsules.values())
    high_signal_capsule_count = sum(1 for v in slot_capsules.values() for c in v if not c.get("fallback_available_context"))
    fallback_capsule_count = sum(1 for v in slot_capsules.values() for c in v if c.get("fallback_available_context"))
    filled_slot_count = sum(1 for v in slot_capsules.values() if v)
    high_signal_filled_slot_count = sum(1 for v in slot_capsules.values() if any(not c.get("fallback_available_context") for c in v))

    return {
        "context_pack_version": MODULE_VERSION,
        "context_pack_id": f"engineering_context_pack_{index+1:04d}",
        "source_blueprint_id": blueprint.get("blueprint_id"),
        "question_id": blueprint.get("question_id"),
        "user_question": blueprint.get("user_question"),
        "intent_family": blueprint.get("intent_family"),
        "selected_playbook_id": blueprint.get("selected_playbook_id"),
        "seed_entities": blueprint.get("seed_entities") or [],
        "requested_change": blueprint.get("requested_change"),
        "context_pack_status": "built_from_available_artifacts_no_llm",
        "sections": sections,
        "route_evidence_capsules": slot_capsules,
        "missing_evidence": missing_notes,
        "evidence_capsule_count": evidence_capsule_count,
        "high_signal_evidence_capsule_count": high_signal_capsule_count,
        "fallback_evidence_capsule_count": fallback_capsule_count,
        "filled_route_slot_count": filled_slot_count,
        "high_signal_filled_route_slot_count": high_signal_filled_slot_count,
        "required_route_slot_count": len(blueprint.get("route_evidence_slots") or []),
        "answer_format_contract": blueprint.get("answer_format_contract"),
        "self_rag_crag_contract": blueprint.get("self_rag_crag_contract"),
        "forbidden_answer_claims": blueprint.get("forbidden_answer_claims") or [],
        "ready_for_self_rag_check": True,
        "ready_for_gemma_context": high_signal_capsule_count > 0,
        "answers_user_question": False,
        "llm_call_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_execution_allowed": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": False,
    }


def build_engineering_context_pack_builder(
    *,
    blueprint_path: Path,
    output_dir: Path,
    route_dispatch_handoff: Optional[Path] = None,
    table_exact_search_adapter: Optional[Path] = None,
    page_context_v2: Optional[Path] = None,
    leiden_communities: Optional[Path] = None,
    image_visual_observer: Optional[Path] = None,
    max_records_per_slot: int = 8,
) -> Dict[str, Any]:
    blueprint_payload = _read_json(blueprint_path)
    blueprints = blueprint_payload.get("records") or []
    corpus, artifact_counts, missing_inputs = _build_artifact_corpus(
        route_dispatch_handoff=route_dispatch_handoff,
        table_exact_search_adapter=table_exact_search_adapter,
        page_context_v2=page_context_v2,
        leiden_communities=leiden_communities,
        image_visual_observer=image_visual_observer,
    )

    records = [
        build_context_pack_record(
            blueprint=blueprint,
            corpus=corpus,
            index=index,
            max_records_per_slot=max_records_per_slot,
        )
        for index, blueprint in enumerate(blueprints)
    ]

    route_capsule_counts = Counter(
        route
        for record in records
        for route, capsules in record.get("route_evidence_capsules", {}).items()
        for _ in capsules
    )
    high_signal_route_capsule_counts = Counter(
        route
        for record in records
        for route, capsules in record.get("route_evidence_capsules", {}).items()
        for capsule in capsules
        if not capsule.get("fallback_available_context")
    )
    intent_counts = Counter(record.get("intent_family") for record in records)

    summary = {
        "source_blueprint_quality_status": blueprint_payload.get("quality_status"),
        "source_blueprint_count": len(blueprints),
        "context_pack_count": len(records),
        "artifact_corpus_record_count": len(corpus),
        "artifact_record_counts": artifact_counts,
        "artifact_missing_input_count": len(missing_inputs),
        "artifact_missing_inputs": missing_inputs,
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "total_evidence_capsule_count": sum(record.get("evidence_capsule_count", 0) for record in records),
        "total_high_signal_evidence_capsule_count": sum(record.get("high_signal_evidence_capsule_count", 0) for record in records),
        "total_fallback_evidence_capsule_count": sum(record.get("fallback_evidence_capsule_count", 0) for record in records),
        "route_evidence_capsule_counts": dict(sorted(route_capsule_counts.items())),
        "high_signal_route_evidence_capsule_counts": dict(sorted(high_signal_route_capsule_counts.items())),
        "packs_ready_for_gemma_context_count": sum(1 for r in records if r.get("ready_for_gemma_context")),
        "packs_ready_for_self_rag_check_count": sum(1 for r in records if r.get("ready_for_self_rag_check")),
        "total_missing_evidence_note_count": sum(len(r.get("missing_evidence") or []) for r in records),
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
    if blueprint_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_CONTEXT_PACK_BUILDER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_blueprint_path": str(blueprint_path),
        "artifact_inputs": {
            "route_dispatch_handoff": str(route_dispatch_handoff) if route_dispatch_handoff else None,
            "table_exact_search_adapter": str(table_exact_search_adapter) if table_exact_search_adapter else None,
            "page_context_v2": str(page_context_v2) if page_context_v2 else None,
            "leiden_communities": str(leiden_communities) if leiden_communities else None,
            "image_visual_observer": str(image_visual_observer) if image_visual_observer else None,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "context_pack_builder_artifact_only",
            "answers_user_question": False,
            "llm_call_allowed": False,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_context_pack_builder_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_context_pack_builder_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_context_pack_builder_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_context_pack_builder_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Context Pack Builder v1.2",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Context packs: {summary.get('context_pack_count')}",
        f"- Artifact corpus records: {summary.get('artifact_corpus_record_count')}",
        f"- Artifact record counts: `{summary.get('artifact_record_counts')}`",
        f"- Missing optional artifact inputs: `{summary.get('artifact_missing_inputs')}`",
        f"- Evidence capsules: {summary.get('total_evidence_capsule_count')}",
        f"- High-signal capsules: {summary.get('total_high_signal_evidence_capsule_count')}",
        f"- Fallback capsules: {summary.get('total_fallback_evidence_capsule_count')}",
        f"- Route capsule counts: `{summary.get('route_evidence_capsule_counts')}`",
        f"- Missing evidence notes: {summary.get('total_missing_evidence_note_count')}",
        "",
        "## Packs",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('context_pack_id')} — {record.get('intent_family')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Playbook: `{record.get('selected_playbook_id')}`",
            f"- Evidence capsules: `{record.get('evidence_capsule_count')}`",
            f"- High-signal capsules: `{record.get('high_signal_evidence_capsule_count')}`",
            f"- Filled route slots: `{record.get('filled_route_slot_count')}/{record.get('required_route_slot_count')}`",
            f"- High-signal filled slots: `{record.get('high_signal_filled_route_slot_count')}/{record.get('required_route_slot_count')}`",
            f"- Missing evidence: `{record.get('missing_evidence')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_context_pack_builder_quality(
    *,
    report_path: Path,
    require_source_blueprint_quality_pass: bool = False,
    min_context_packs: int = 1,
    min_artifact_corpus_records: int = 1,
    min_evidence_capsules: int = 1,
    min_high_signal_evidence_capsules: int = 0,
    min_packs_ready_for_gemma_context: int = 1,
    max_missing_optional_artifact_inputs: Optional[int] = None,
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

    if require_source_blueprint_quality_pass:
        fail_if(summary.get("source_blueprint_quality_status") != "PASS", "source blueprint quality is not PASS")
    fail_if(summary.get("context_pack_count", 0) < min_context_packs, "not enough context packs")
    fail_if(summary.get("artifact_corpus_record_count", 0) < min_artifact_corpus_records, "not enough artifact corpus records")
    fail_if(summary.get("total_evidence_capsule_count", 0) < min_evidence_capsules, "not enough evidence capsules")
    fail_if(summary.get("total_high_signal_evidence_capsule_count", 0) < min_high_signal_evidence_capsules, "not enough high-signal evidence capsules")
    fail_if(summary.get("packs_ready_for_gemma_context_count", 0) < min_packs_ready_for_gemma_context, "not enough packs ready for Gemma context")
    if max_missing_optional_artifact_inputs is not None:
        fail_if(summary.get("artifact_missing_input_count", 0) > max_missing_optional_artifact_inputs, "too many missing optional artifact inputs")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "llm call allowed count not zero")
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context pack builder v1.")
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--route-dispatch-handoff")
    parser.add_argument("--table-exact-search-adapter")
    parser.add_argument("--page-context-v2")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--image-visual-observer")
    parser.add_argument("--max-records-per-slot", type=int, default=8)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_context_pack_builder(
        blueprint_path=Path(args.blueprint),
        output_dir=Path(args.output_dir),
        route_dispatch_handoff=Path(args.route_dispatch_handoff) if args.route_dispatch_handoff else None,
        table_exact_search_adapter=Path(args.table_exact_search_adapter) if args.table_exact_search_adapter else None,
        page_context_v2=Path(args.page_context_v2) if args.page_context_v2 else None,
        leiden_communities=Path(args.leiden_communities) if args.leiden_communities else None,
        image_visual_observer=Path(args.image_visual_observer) if args.image_visual_observer else None,
        max_records_per_slot=args.max_records_per_slot,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context pack builder v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-blueprint-quality-pass", action="store_true")
    parser.add_argument("--min-context-packs", type=int, default=1)
    parser.add_argument("--min-artifact-corpus-records", type=int, default=1)
    parser.add_argument("--min-evidence-capsules", type=int, default=1)
    parser.add_argument("--min-high-signal-evidence-capsules", type=int, default=0)
    parser.add_argument("--min-packs-ready-for-gemma-context", type=int, default=1)
    parser.add_argument("--max-missing-optional-artifact-inputs", type=int)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_context_pack_builder_quality(
        report_path=Path(args.report_path),
        require_source_blueprint_quality_pass=args.require_source_blueprint_quality_pass,
        min_context_packs=args.min_context_packs,
        min_artifact_corpus_records=args.min_artifact_corpus_records,
        min_evidence_capsules=args.min_evidence_capsules,
        min_high_signal_evidence_capsules=args.min_high_signal_evidence_capsules,
        min_packs_ready_for_gemma_context=args.min_packs_ready_for_gemma_context,
        max_missing_optional_artifact_inputs=args.max_missing_optional_artifact_inputs,
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
        out = Path(args.report_path).with_name("trace_net_engineering_context_pack_builder_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
