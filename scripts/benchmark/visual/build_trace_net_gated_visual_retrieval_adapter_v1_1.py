#!/usr/bin/env python3
"""TRACE-Net gated visual retrieval adapter v1.1.

Builds a retrieval-ready visual evidence pack from the gated visual question
context output.

Inputs:
- confirmed image context JSONL from trace_net_visual_question_context_gate_v1
- optional visual_candidate_review JSONL from the same gate

Outputs:
- search-ready visual retrieval documents
- review-only visual candidate documents
- summary/quality manifest

Safety contract:
- Read-only.
- Does not call OCR/LLM/Ollama.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not mutate source-truth artifacts.
- Does not grant answer permission.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


MODULE_NAME = "trace_net_gated_visual_retrieval_adapter_v1_1"


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            yield obj


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records)
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def page_id_of(record: Dict[str, Any]) -> str:
    value = record.get("page_id")
    if isinstance(value, str) and value:
        return value
    for key in ("route_provenance", "source_page", "page", "metadata"):
        nested = record.get(key)
        if isinstance(nested, dict):
            value = nested.get("page_id")
            if isinstance(value, str) and value:
                return value
    return ""


def compact_string(value: Any, limit: int = 600) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()[:limit]
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False, sort_keys=True)).strip()[:limit]
    except Exception:
        return str(value)[:limit]


def walk_strings(value: Any, *, limit: int = 80, max_depth: int = 6) -> List[str]:
    found: List[str] = []

    def walk(x: Any, depth: int) -> None:
        if len(found) >= limit or depth > max_depth:
            return
        if isinstance(x, str):
            s = compact_string(x, limit=500)
            if s and s not in found:
                found.append(s)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x[:120]:
                walk(v, depth + 1)

    walk(value, 0)
    return found


def first_nonempty(record: Dict[str, Any], paths: Sequence[Sequence[str]]) -> Any:
    for path in paths:
        cur: Any = record
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and cur not in (None, "", [], {}):
            return cur
    return None


def listify(value: Any, *, max_items: int = 60) -> List[str]:
    out: List[str] = []
    if value is None:
        return out
    if isinstance(value, list):
        vals = value
    else:
        vals = [value]
    for v in vals[:max_items]:
        if isinstance(v, dict):
            # Preserve useful dicts compactly, but prefer visible IDs/labels.
            picked = first_nonempty(
                v,
                [
                    ["part_number"],
                    ["linked_part_number"],
                    ["figure"],
                    ["callout"],
                    ["label"],
                    ["id"],
                    ["visual_id"],
                    ["region_id"],
                    ["description"],
                ],
            )
            s = compact_string(picked if picked is not None else v, limit=300)
        else:
            s = compact_string(v, limit=300)
        if s and s not in out:
            out.append(s)
    return out


def extract_visual_summary(record: Dict[str, Any]) -> List[str]:
    """Extract human/useful visual description text from many adapter schemas.

    v1 only recognized a few keys and therefore counted only a handful of pages
    as having summaries, even though the upstream v1.3 adapter reported page
    descriptions. v1.1 searches broader top-level keys, source records, and
    prompt/context fields.
    """
    candidates: List[str] = []

    # Common top-level schema variants.
    for key in (
        "visual_summary",
        "description",
        "object_description",
        "visual_description",
        "page_description",
        "summary",
        "summary_text",
        "prompt_context",
        "visual_context",
        "retrieval_text",
        "search_text",
    ):
        value = record.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            for subkey in (
                "summary",
                "visual_summary",
                "description",
                "text",
                "object_description",
                "page_description",
                "prompt_context",
                "context",
            ):
                if value.get(subkey):
                    candidates.append(compact_string(value.get(subkey), limit=1200))
            for subkey in ("llava_summaries", "summaries", "descriptions", "text_candidates"):
                candidates.extend(listify(value.get(subkey), max_items=20))
        elif isinstance(value, list):
            candidates.extend(listify(value, max_items=20))
        else:
            candidates.append(compact_string(value, limit=1200))

    # Existing v1.3 visual-question context usually places the useful detail in
    # source_records with varying names. Mine it broadly but keep only visual-ish
    # strings to avoid turning safety metadata into prose.
    source_records = record.get("source_records")
    if isinstance(source_records, dict):
        for group_name, group in source_records.items():
            if not isinstance(group, list):
                continue
            for item in group[:80]:
                if not isinstance(item, dict):
                    continue

                for path in (
                    ["visual_summary"],
                    ["summary"],
                    ["description"],
                    ["object_description"],
                    ["page_description"],
                    ["source_snippet"],
                    ["prompt_context"],
                    ["visual_context"],
                    ["linked_description"],
                    ["linked_nomenclature"],
                    ["diagram_type"],
                    ["visual_type"],
                    ["image_classification"],
                    ["image_role"],
                ):
                    value = first_nonempty(item, [path])
                    if value:
                        candidates.extend(listify(value, max_items=8))

                for s in walk_strings(item, limit=40):
                    lower = s.lower()
                    if any(
                        k in lower
                        for k in (
                            "diagram",
                            "figure",
                            "illustrat",
                            "technical drawing",
                            "callout",
                            "assembly",
                            "seat",
                            "view",
                            "detail",
                            "parts list",
                            "nomenclature",
                        )
                    ):
                        candidates.append(s)

    # Preserve order and dedupe.
    out: List[str] = []
    for c in candidates:
        c = compact_string(c, limit=1200)
        if c and c not in out:
            out.append(c)
    return out[:16]


def evidence_fallback_summary(
    page_id: str,
    identifiers: Dict[str, List[str]],
    gate: Dict[str, Any],
) -> str:
    """Create a deterministic, non-LLM summary from structured evidence.

    This is not proof and not a final answer. It gives retrieval something
    searchable when the upstream visual context has figure/part evidence but no
    simple prose summary field.
    """
    visual_subtype = compact_string(gate.get("visual_subtype"), limit=80)
    visual_route = compact_string(gate.get("detector_route"), limit=80)

    parts: List[str] = [
        f"Visual retrieval page {page_id}",
    ]
    if visual_route:
        parts.append(f"route {visual_route}")
    if visual_subtype:
        parts.append(f"subtype {visual_subtype}")

    figures = identifiers.get("figure_refs", [])
    part_numbers = identifiers.get("part_numbers", [])
    callouts = identifiers.get("callouts", [])
    nomenclature = identifiers.get("nomenclature", [])

    if figures:
        parts.append("figures " + ", ".join(figures[:8]))
    if part_numbers:
        parts.append("part candidates " + ", ".join(part_numbers[:10]))
    if callouts:
        parts.append("callouts/items " + ", ".join(callouts[:18]))
    if nomenclature:
        parts.append("nomenclature/description " + "; ".join(nomenclature[:5]))

    return "; ".join(parts) + "."

def extract_identifiers(record: Dict[str, Any]) -> Dict[str, List[str]]:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), dict) else {}

    part_numbers: List[str] = []
    figure_refs: List[str] = []
    callouts: List[str] = []
    visual_ids: List[str] = []
    nomenclature: List[str] = []

    for key in ("part_numbers", "linked_part_numbers", "linked_part_number", "covered_part_numbers"):
        part_numbers.extend(listify(identifiers.get(key) if isinstance(identifiers, dict) else None))
    for key in ("figure_refs", "figures", "figure_candidates"):
        figure_refs.extend(listify(identifiers.get(key) if isinstance(identifiers, dict) else None))
    for key in ("callouts", "callout_labels", "item_refs"):
        callouts.extend(listify(identifiers.get(key) if isinstance(identifiers, dict) else None))
    for key in ("nomenclature", "linked_nomenclature", "descriptions"):
        nomenclature.extend(listify(identifiers.get(key) if isinstance(identifiers, dict) else None))

    visual_ids.extend(listify(record.get("visual_ids")))

    # Also mine source records because older adapters have varying schema.
    source_records = record.get("source_records")
    if isinstance(source_records, dict):
        for group in source_records.values():
            if not isinstance(group, list):
                continue
            for item in group[:60]:
                if not isinstance(item, dict):
                    continue
                part_numbers.extend(listify(first_nonempty(item, [["part_number"], ["linked_part_number"], ["linked_part_numbers"]])))
                figure_refs.extend(listify(first_nonempty(item, [["figure"], ["figure_refs"], ["detected_figure_refs"]])))
                callouts.extend(listify(first_nonempty(item, [["callout"], ["callout_labels"], ["item_refs"]])))
                visual_ids.extend(listify(first_nonempty(item, [["visual_id"], ["visual_record_id"], ["region_id"], ["id"]])))
                nomenclature.extend(listify(first_nonempty(item, [["linked_description"], ["linked_nomenclature"], ["description"], ["source_snippet"]])))

    def dedupe(xs: List[str], max_items: int = 80) -> List[str]:
        out: List[str] = []
        for x in xs:
            x = compact_string(x, limit=180)
            if x and x not in out:
                out.append(x)
        return out[:max_items]

    return {
        "part_numbers": dedupe(part_numbers),
        "figure_refs": dedupe(figure_refs),
        "callouts": dedupe(callouts),
        "visual_ids": dedupe(visual_ids),
        "nomenclature": dedupe(nomenclature),
    }


def extract_gate(record: Dict[str, Any]) -> Dict[str, Any]:
    gate = record.get("meaningful_image_gate")
    return gate if isinstance(gate, dict) else {}


def build_search_text(
    page_id: str,
    summaries: Sequence[str],
    identifiers: Dict[str, List[str]],
    gate: Dict[str, Any],
) -> str:
    parts: List[str] = []
    parts.append(f"page_id: {page_id}")
    route = gate.get("detector_route")
    subtype = gate.get("visual_subtype")
    if route:
        parts.append(f"visual_route: {route}")
    if subtype:
        parts.append(f"visual_subtype: {subtype}")

    for label, values in [
        ("summary", list(summaries)),
        ("part_numbers", identifiers.get("part_numbers", [])),
        ("figures", identifiers.get("figure_refs", [])),
        ("callouts", identifiers.get("callouts", [])),
        ("nomenclature", identifiers.get("nomenclature", [])),
        ("visual_ids", identifiers.get("visual_ids", [])),
    ]:
        if values:
            parts.append(f"{label}: " + "; ".join(values[:50]))

    reasons = listify(gate.get("route_reasons"), max_items=20)
    if reasons:
        parts.append("gate_reasons: " + "; ".join(reasons))
    return "\n".join(parts)


def make_document(
    record: Dict[str, Any],
    *,
    document_kind: str,
    sequence: int,
    source_file: str,
) -> Dict[str, Any]:
    page_id = page_id_of(record)
    summaries = extract_visual_summary(record)
    identifiers = extract_identifiers(record)
    gate = extract_gate(record)
    summary_source = "upstream_visual_context"
    if not summaries:
        fallback = evidence_fallback_summary(page_id, identifiers, gate)
        summaries = [fallback] if fallback.strip() else []
        summary_source = "deterministic_evidence_fallback"
    search_text = build_search_text(page_id, summaries, identifiers, gate)

    detector_route = gate.get("detector_route")
    visual_subtype = gate.get("visual_subtype")

    citation_ready = bool(
        first_nonempty(record, [["evidence_status", "citation_ready"], ["citation_ready"]])
        or first_nonempty(record, [["evidence_status", "source_trace_ready"], ["source_trace_ready"]])
    )

    source_trace_ready = bool(
        first_nonempty(record, [["evidence_status", "source_trace_ready"], ["source_trace_ready"]])
    )

    return {
        "module": MODULE_NAME,
        "document_id": f"{MODULE_NAME}::{document_kind}::{sequence:06d}::{page_id}",
        "document_kind": document_kind,
        "page_id": page_id,
        "source_visual_context_file": source_file,
        "search_ready": document_kind == "confirmed_image_context",
        "review_only": document_kind != "confirmed_image_context",
        "visual_route": detector_route,
        "visual_subtype": visual_subtype,
        "route_confidence": gate.get("route_confidence"),
        "visual_summaries": list(summaries),
        "visual_summary_source": summary_source,
        "identifiers": identifiers,
        "search_text": search_text,
        "citation_ready": citation_ready,
        "source_trace_ready": source_trace_ready,
        "retrieval_guidance": {
            "use_for_image_route_retrieval": document_kind == "confirmed_image_context",
            "use_for_candidate_review": document_kind != "confirmed_image_context",
            "do_not_treat_as_proof_by_itself": True,
            "requires_source_trace_for_final_claims": True,
            "visual_observation_is_candidate_only": True,
        },
        "meaningful_image_gate": gate,
        "safety_contract": {
            "final_answer_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "ollama_call_attempt": False,
            "llm_call_attempt": False,
        },
    }


def bool_nested(record: Dict[str, Any], key: str) -> bool:
    value = record.get(key)
    if isinstance(value, bool):
        return value
    safety = record.get("safety_contract")
    if isinstance(safety, dict) and isinstance(safety.get(key), bool):
        return bool(safety.get(key))
    return False


def build(args: argparse.Namespace) -> Dict[str, Any]:
    confirmed_path = Path(args.confirmed_image_context_jsonl)
    review_path = Path(args.visual_candidate_review_jsonl) if args.visual_candidate_review_jsonl else None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    confirmed_records = list(read_jsonl(confirmed_path) or [])
    review_records = list(read_jsonl(review_path) or []) if review_path else []

    confirmed_docs = [
        make_document(
            rec,
            document_kind="confirmed_image_context",
            sequence=i,
            source_file=str(confirmed_path),
        )
        for i, rec in enumerate(confirmed_records, start=1)
    ]
    review_docs = [
        make_document(
            rec,
            document_kind="visual_candidate_review",
            sequence=i,
            source_file=str(review_path),
        )
        for i, rec in enumerate(review_records, start=1)
    ]

    confirmed_out = output_dir / "trace_net_gated_visual_retrieval_documents_v1_1.jsonl"
    review_out = output_dir / "trace_net_gated_visual_candidate_review_documents_v1_1.jsonl"
    combined_out = output_dir / "trace_net_gated_visual_retrieval_all_documents_v1_1.jsonl"

    write_jsonl(confirmed_out, confirmed_docs)
    write_jsonl(review_out, review_docs)
    write_jsonl(combined_out, confirmed_docs + review_docs)

    route_counts = Counter(str(d.get("visual_route")) for d in confirmed_docs)
    subtype_counts = Counter(str(d.get("visual_subtype")) for d in confirmed_docs)
    review_route_counts = Counter(str(d.get("visual_route")) for d in review_docs)
    summary_source_counts = Counter(str(d.get("visual_summary_source")) for d in confirmed_docs)

    all_docs = confirmed_docs + review_docs
    safety_counts = {
        "final_answer_allowed_true_count": sum(1 for d in all_docs if bool_nested(d, "final_answer_allowed")),
        "answer_permission_count": sum(1 for d in all_docs if bool_nested(d, "answer_permission")),
        "can_answer_directly_count": sum(1 for d in all_docs if bool_nested(d, "can_answer_directly")),
        "can_prove_claims_count": sum(1 for d in all_docs if bool_nested(d, "can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for d in all_docs if bool_nested(d, "source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "ollama_call_attempt_count": 0,
        "llm_call_attempt_count": 0,
    }

    pages_with_summary = sum(1 for d in confirmed_docs if d.get("visual_summaries"))
    pages_with_part_numbers = sum(1 for d in confirmed_docs if d["identifiers"].get("part_numbers"))
    pages_with_figures = sum(1 for d in confirmed_docs if d["identifiers"].get("figure_refs"))
    empty_search_text_count = sum(1 for d in confirmed_docs if not d.get("search_text", "").strip())

    failures: List[str] = []
    if len(confirmed_records) < args.min_confirmed_contexts:
        failures.append(f"confirmed_context_count:{len(confirmed_records)} < {args.min_confirmed_contexts}")
    if len(confirmed_docs) < args.min_search_ready_documents:
        failures.append(f"search_ready_document_count:{len(confirmed_docs)} < {args.min_search_ready_documents}")
    if pages_with_summary < args.min_pages_with_summary:
        failures.append(f"pages_with_summary:{pages_with_summary} < {args.min_pages_with_summary}")
    if empty_search_text_count > args.max_empty_search_text:
        failures.append(f"empty_search_text_count:{empty_search_text_count} > {args.max_empty_search_text}")
    for key, value in safety_counts.items():
        if value != 0:
            failures.append(f"{key}:{value} != 0")

    summary = {
        "module": MODULE_NAME,
        "status": "TRACE_NET_GATED_VISUAL_RETRIEVAL_ADAPTER_V1_1_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "quality_failures": failures,
        "inputs": {
            "confirmed_image_context_jsonl": str(confirmed_path),
            "visual_candidate_review_jsonl": str(review_path) if review_path else "",
        },
        "outputs": {
            "search_ready_documents_jsonl": str(confirmed_out),
            "review_only_documents_jsonl": str(review_out),
            "combined_documents_jsonl": str(combined_out),
            "summary": str(output_dir / "summary.json"),
        },
        "summary": {
            "confirmed_context_count": len(confirmed_records),
            "visual_candidate_review_context_count": len(review_records),
            "search_ready_document_count": len(confirmed_docs),
            "review_only_document_count": len(review_docs),
            "combined_document_count": len(all_docs),
            "confirmed_route_counts": dict(sorted(route_counts.items())),
            "confirmed_visual_subtype_counts": dict(sorted(subtype_counts.items())),
            "review_route_counts": dict(sorted(review_route_counts.items())),
            "summary_source_counts": dict(sorted(summary_source_counts.items())),
            "pages_with_summary": pages_with_summary,
            "pages_with_part_numbers": pages_with_part_numbers,
            "pages_with_figure_refs": pages_with_figures,
            "empty_search_text_count": empty_search_text_count,
            **safety_counts,
        },
        "safety_contract": {
            "read_only_adapter": True,
            "does_not_call_ollama": True,
            "does_not_call_llm": True,
            "does_not_write_postgres": True,
            "does_not_write_qdrant": True,
            "does_not_write_opensearch": True,
            "does_not_mutate_source_truth": True,
            "final_answer_allowed": False,
            "answer_permission": False,
        },
    }

    write_json(output_dir / "summary.json", summary)

    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    for key, value in summary["summary"].items():
        if isinstance(value, dict):
            print(f"{key}=" + json.dumps(value, sort_keys=True))
        else:
            print(f"{key}={value}")
    print("output_dir=" + str(output_dir))

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirmed-image-context-jsonl", required=True)
    p.add_argument("--visual-candidate-review-jsonl", default="")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--min-confirmed-contexts", type=int, default=1)
    p.add_argument("--min-search-ready-documents", type=int, default=1)
    p.add_argument("--min-pages-with-summary", type=int, default=1)
    p.add_argument("--max-empty-search-text", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = build(args)
    return 0 if summary.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
