#!/usr/bin/env python3
"""Build a full-corpus TRACE-Net v27 serving pack from existing JSON/JSONL artifacts.

Read-only inputs:
- existing OCR, table, part/nomenclature, V2/V3 summary and Leiden artifacts

Outputs:
- normalized exact-search adapter
- normalized page-context guidance
- normalized Leiden memberships
- v27 serving manifest

This does not OCR files, scan TIFFs, or write to Postgres/Qdrant/OpenSearch.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PAGE_RE = re.compile(r"(?:^|[^a-z0-9])(p\d{6}|t_p_[A-Za-z0-9_]+)(?:$|[^a-z0-9])", re.I)
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

FIELD_ALIASES = {
    "covered_part_number": "covered_part_number",
    "ipl_part_number": "ipl_part_number",
    "part_number": "part_number",
    "part_numbers": "part_number",
    "candidate_part_number": "part_number",
    "candidate_value": "part_number",
    "part_no": "part_number",
    "partno": "part_number",
    "pn": "part_number",
    "p_n": "part_number",
    "nomenclature": "nomenclature",
    "candidate_nomenclature": "nomenclature",
    "description": "nomenclature",
    "part_description": "nomenclature",
    "item_description": "nomenclature",
    "manual_page_reference": "manual_page_reference",
    "manual_reference": "manual_page_reference",
    "manual_references": "manual_page_reference",
    "table_text": "table_text",
    "ipl_text": "ipl_text",
    "cell_text": "table_text",
    "cell_value": "table_text",
    "row_text": "table_text",
    "citation_text": "table_text",
    "source_text": "table_text",
    "retrieval_text": "table_text",
    "text_preview": "table_text",
    "embedding_text_preview": "table_text",
    "extracted_text": "table_text",
    "tile_text": "table_text",
    "sample_text": "table_text",
    "ocr_text": "ocr_text",
    "page_text": "ocr_text",
    "procedure_text": "procedure_text",
    "warning": "warning_text",
    "caution": "caution_text",
    "note": "note_text",
}
SUMMARY_KEYS = (
    "v3_page_intelligence", "v3_summary", "v2_summary", "page_summary",
    "context_summary", "summary", "retrieval_text",
)
COMMUNITY_KEYS = ("community_id", "leiden_community_id", "community", "cluster_id")
PAGE_KEYS = ("page_id", "source_page_id", "page", "page_key")
DOC_KEYS = ("document_id", "source_document_id", "manual_id", "source_id", "document")


def compact(value: Any, limit: int = 12000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def first(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    lookup = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lookup.get(str(key).lower())
        text = compact(value, 1000)
        if text:
            return text
    return ""


def page_id_for(row: Mapping[str, Any], inherited: str = "") -> str:
    value = first(row, PAGE_KEYS)
    if value:
        match = PAGE_RE.search(value)
        return match.group(1) if match else value
    blob = compact(row, 4000)
    match = PAGE_RE.search(blob)
    return match.group(1) if match else inherited


def iter_records(value: Any, inherited_page: str = "") -> Iterable[Tuple[Mapping[str, Any], str]]:
    if isinstance(value, Mapping):
        page = page_id_for(value, inherited_page)
        yield value, page
        for child in value.values():
            if isinstance(child, (Mapping, list)):
                yield from iter_records(child, page)
    elif isinstance(value, list):
        for child in value:
            yield from iter_records(child, inherited_page)


def read_records(path: Path) -> Iterable[Any]:
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
    else:
        try:
            yield json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return


def file_priority(path: Path) -> int:
    low = str(path).replace("\\", "/").lower()
    weights = {
        "guided_candidate_discovery": 100,
        "source_citations": 95,
        "graph_explorer_edges": 90,
        "graph_explorer_nodes": 88,
        "page_context_overlay": 86,
        "page_context_v2": 80,
        "page_intelligence": 78,
        "leiden": 76,
        "community": 72,
        "nomenclature": 70,
        "part": 65,
        "table": 62,
        "ocr_route_scan_pack_tesseract_full": 60,
        "ocr": 45,
        "embedding_candidates": 35,
        "draft": -10,
        "retry_prompt": -10,
    }
    return sum(weight for token, weight in weights.items() if token in low)


def candidate_files(root: Path, explicit: Sequence[str], max_files: int) -> List[Path]:
    if explicit:
        files: List[Path] = []
        for raw in explicit:
            path = Path(raw)
            if path.exists() and path.is_file():
                files.append(path)
        return list(dict.fromkeys(files))

    preferred = (
        "ocr", "table", "part", "nomenclature", "page_context", "page_intelligence",
        "v2", "v3", "leiden", "community", "source_citation", "source_citations",
        "rag_candidate", "guided_candidate_discovery", "graph_explorer",
        "page_context_overlay", "embedding_candidates",
    )
    found: List[Path] = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        low = str(path).replace("\\", "/").lower()
        if any(token in low for token in preferred):
            found.append(path)
    found.sort(key=lambda p: (-file_priority(p), len(str(p)), str(p).lower()))
    return list(dict.fromkeys(found[:max_files]))


def values_for(key: str, value: Any) -> List[str]:
    if isinstance(value, list):
        return [compact(v, 6000) for v in value if compact(v, 6000)]
    if isinstance(value, Mapping):
        return []
    text = compact(value, 6000)
    return [text] if text else []


def is_noise_text(value: str) -> bool:
    text = compact(value, 400)
    token_count = len(TOKEN_RE.findall(text))
    if token_count == 0:
        return True
    if len(text) <= 2:
        return True
    return False


def graph_nomenclatures(blob: str) -> List[str]:
    """Extract labels from graph strings like nomenclature:nomenclature:ring_locking."""
    out: List[str] = []
    for raw in re.findall(r"nomenclature[:_]+(?:nomenclature[:_]+)?([A-Za-z0-9_,\- ]{3,80})", blob, flags=re.I):
        token = raw.strip(" :;,.\"'[]{}()")
        token = re.split(r"[\"'{}\[\]/\\]", token)[0].strip(" :;,.")
        if not token:
            continue
        if "_" in token:
            pieces = [p for p in token.split("_") if p]
            if len(pieces) == 2:
                value = f"{pieces[0].upper()}, {pieces[1].upper()}"
            else:
                value = " ".join(pieces).upper()
        else:
            value = token.upper()
        if len(TOKEN_RE.findall(value)) >= 1:
            out.append(value)
    return list(dict.fromkeys(out))


def add_exact(
    exact: Dict[Tuple[str, str, str], Dict[str, Any]],
    *,
    page: str,
    field: str,
    value: str,
    row: Mapping[str, Any],
    document_id: str,
    path: Path,
) -> None:
    normalized = compact(value, 6000)
    if not page or not normalized or is_noise_text(normalized):
        return
    key = (page, field, normalized)
    exact.setdefault(key, {
        "document_id": document_id,
        "page_id": page,
        "field_name": field,
        "normalized_value": normalized,
        "search_text": compact(row, 12000),
        "source_artifact_path": str(path),
        "source_trace_ready": True,
        "direct_proof_authority": field not in {
            "ocr_text", "procedure_text", "warning_text", "caution_text",
            "note_text", "retrieval_text",
        },
    })


def build(args: argparse.Namespace) -> Dict[str, Any]:
    artifact_root = Path(args.artifact_root)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = candidate_files(artifact_root, args.input, args.max_files)

    exact: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    summaries: Dict[str, str] = {}
    page_to_community: Dict[str, str] = {}
    community_to_pages: Dict[str, List[str]] = defaultdict(list)
    file_stats = []
    parse_record_count = 0

    for path in files:
        before = len(exact)
        page_seen = set()
        for payload in read_records(path):
            for row, inherited_page in iter_records(payload):
                parse_record_count += 1
                page = page_id_for(row, inherited_page)
                if not page:
                    continue
                page_seen.add(page)
                document_id = first(row, DOC_KEYS)
                row_lookup = {str(k).lower(): v for k, v in row.items()}
                row_blob = compact(row, 12000)

                for part in PART_RE.findall(row_blob):
                    add_exact(exact, page=page, field="part_number", value=part, row=row, document_id=document_id, path=path)
                for manual in MANUAL_RE.findall(row_blob):
                    add_exact(exact, page=page, field="manual_page_reference", value=manual, row=row, document_id=document_id, path=path)
                for nomenclature in graph_nomenclatures(row_blob):
                    add_exact(exact, page=page, field="nomenclature", value=nomenclature, row=row, document_id=document_id, path=path)
                    add_exact(exact, page=page, field="table_text", value=nomenclature, row=row, document_id=document_id, path=path)

                for key, canonical in FIELD_ALIASES.items():
                    if key not in row_lookup:
                        continue
                    for value in values_for(key, row_lookup.get(key)):
                        if canonical == "part_number":
                            found = PART_RE.findall(value)
                            candidates = found or ([value] if key in {"candidate_part_number", "part_number", "part_no", "partno", "pn", "p_n"} else [])
                        elif canonical == "manual_page_reference":
                            found = MANUAL_RE.findall(value)
                            candidates = found or [value]
                        else:
                            candidates = [value]
                        for normalized in candidates:
                            add_exact(exact, page=page, field=canonical, value=normalized, row=row, document_id=document_id, path=path)
                            if canonical == "nomenclature":
                                add_exact(exact, page=page, field="table_text", value=normalized, row=row, document_id=document_id, path=path)

                for key in SUMMARY_KEYS:
                    if key in row_lookup:
                        summary = compact(row_lookup.get(key), 12000)
                        if summary and len(summary) >= args.min_summary_chars:
                            current = summaries.get(page, "")
                            if len(summary) > len(current):
                                summaries[page] = summary

                community = first(row, COMMUNITY_KEYS)
                if community:
                    page_to_community[page] = community
                    community_to_pages[community].append(page)

        file_stats.append({
            "path": str(path),
            "priority": file_priority(path),
            "page_count": len(page_seen),
            "new_exact_document_count": len(exact) - before,
        })

    all_pages = sorted({k[0] for k in exact} | set(summaries) | set(page_to_community))
    fallback_count = 0
    for page in all_pages:
        if page not in page_to_community:
            community = f"unassigned_page::{page}"
            page_to_community[page] = community
            community_to_pages[community].append(page)
            fallback_count += 1

    exact_rows = sorted(exact.values(), key=lambda r: (r["page_id"], r["field_name"], r["normalized_value"]))
    summary_rows = [{"page_id": p, "v2_summary": summaries[p]} for p in sorted(summaries)]
    community_rows = [
        {"community_id": cid, "page_ids": sorted(set(pages))}
        for cid, pages in sorted(community_to_pages.items())
    ]

    adapter_path = output / "trace_net_full_corpus_exact_search_adapter_v1.json"
    summary_path = output / "trace_net_full_corpus_page_context_v2_v1.json"
    leiden_path = output / "trace_net_full_corpus_leiden_guidance_v1.json"
    manifest_path = output / "trace_net_full_corpus_v27_serving_manifest_v1.json"

    adapter_path.write_text(json.dumps({"exact_search_documents": exact_rows}, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps({"page_context_v2_records": summary_rows}, indent=2), encoding="utf-8")
    leiden_path.write_text(json.dumps({"communities": community_rows}, indent=2), encoding="utf-8")

    v27 = importlib.import_module("tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27")
    state = v27.build_state(
        table_exact_search_adapter_path=adapter_path,
        output_dir=None,
        page_context_v2_path=summary_path,
        leiden_communities_path=leiden_path,
        llm_mode="ollama",
        llm_model=args.llm_model,
        fast_path_mode=args.fast_path_mode,
        include_standard_demo_queries=False,
    )
    manifest_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    field_counts = Counter(row["field_name"] for row in exact_rows)
    quality_failures = []
    if len(exact_rows) < args.min_exact_documents:
        quality_failures.append(f"exact_documents_below_min:{len(exact_rows)}<{args.min_exact_documents}")
    if len(summaries) < args.min_page_summaries:
        quality_failures.append(f"page_summaries_below_min:{len(summaries)}<{args.min_page_summaries}")
    if len(page_to_community) < args.min_page_memberships:
        quality_failures.append(f"page_memberships_below_min:{len(page_to_community)}<{args.min_page_memberships}")

    result = {
        "status": "TRACE_NET_FULL_CORPUS_SERVING_PACK_V1_DONE",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "quality_failures": quality_failures,
        "input_file_count": len(files),
        "parsed_record_count": parse_record_count,
        "exact_search_document_count": len(exact_rows),
        "page_summary_count": len(summaries),
        "leiden_page_membership_count": len(page_to_community),
        "true_or_discovered_community_count": len(community_rows) - fallback_count,
        "singleton_fallback_community_count": fallback_count,
        "field_counts": dict(field_counts),
        "paths": {
            "adapter": str(adapter_path),
            "page_context_v2": str(summary_path),
            "leiden": str(leiden_path),
            "v27_manifest": str(manifest_path),
        },
        "file_stats": file_stats,
        "safety_contract": {
            "read_only_inputs": True,
            "raw_tiff_scan": False,
            "ocr_run": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "final_answer_allowed": False,
        },
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-root", default="local_data/organization/trace_net")
    p.add_argument("--input", action="append", default=[], help="Explicit JSON/JSONL input. Repeatable. When omitted, preferred artifacts are discovered.")
    p.add_argument("--output-dir", default="local_data/organization/trace_net/full_corpus_serving_pack_v1")
    p.add_argument("--max-files", type=int, default=5000)
    p.add_argument("--min-summary-chars", type=int, default=20)
    p.add_argument("--min-exact-documents", type=int, default=100)
    p.add_argument("--min-page-summaries", type=int, default=400)
    p.add_argument("--min-page-memberships", type=int, default=400)
    p.add_argument("--llm-model", default="gemma4:26b")
    p.add_argument("--fast-path-mode", choices=["exact", "all_direct", "off"], default="exact")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    result = build(args)
    for key in ("status", "quality_status", "input_file_count", "exact_search_document_count", "page_summary_count", "leiden_page_membership_count"):
        print(f"{key}={result[key]}")
    if result["quality_failures"]:
        print("quality_failures=" + json.dumps(result["quality_failures"]))
    print("v27_manifest=" + result["paths"]["v27_manifest"])
    return 0 if result["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
