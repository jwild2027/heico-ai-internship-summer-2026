"""TRACE-Net Incremental Corpus Manifest v1.

This module builds a read-only, dependency-aware manifest for TRACE-Net corpus
incremental processing.  It is intentionally conservative: the manifest can
mark files/pages/stages as dirty, but it cannot mutate source truth, Postgres,
Qdrant, OpenSearch, or graph state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_incremental_corpus_manifest_v1"
ALGORITHM = "trace_net_dependency_aware_incremental_manifest_v1"

DEFAULT_SOURCE_SUFFIXES = {
    ".tif",
    ".tiff",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".txt",
    ".ocr",
    ".json",
    ".jsonl",
}

DEFAULT_DIR_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "qdrant_storage",
    "node_modules",
}

DEFAULT_DIRTY_STAGES = [
    "ocr",
    "page_element_registry",
    "table_understanding",
    "table_cell_normalizer",
    "figure_chart_understanding",
    "visual_ink_layout_calibrator",
    "fishnet_retry",
    "evidence_consensus",
    "trust_authority",
    "safe_candidates",
    "embeddings",
    "qdrant_upsert",
    "opensearch_upsert",
    "graph_attachment",
    "graph_writeback",
    "leiden_communities",
    "retrieval_regression_smoke",
]

STAGE_DEPENDENCY_GRAPH = {
    "ocr": [],
    "page_element_registry": ["ocr"],
    "table_understanding": ["page_element_registry"],
    "table_cell_normalizer": ["table_understanding"],
    "figure_chart_understanding": ["page_element_registry"],
    "visual_ink_layout_calibrator": ["figure_chart_understanding"],
    "fishnet_retry": ["table_cell_normalizer", "visual_ink_layout_calibrator", "evidence_consensus"],
    "evidence_consensus": ["ocr", "table_cell_normalizer", "figure_chart_understanding"],
    "trust_authority": ["evidence_consensus"],
    "safe_candidates": ["trust_authority"],
    "embeddings": ["safe_candidates"],
    "qdrant_upsert": ["embeddings"],
    "opensearch_upsert": ["safe_candidates"],
    "graph_attachment": ["safe_candidates", "fishnet_retry"],
    "graph_writeback": ["graph_attachment"],
    "leiden_communities": ["graph_writeback"],
    "retrieval_regression_smoke": ["qdrant_upsert", "opensearch_upsert", "leiden_communities"],
}

PAGE_ID_RE = re.compile(r"(t_p_\d+_\d+_p\d{6})", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"(?:^|[_\-./\\])p?(\d{6})(?:\D|$)", re.IGNORECASE)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_json(path: str | Path | None, *, default: Any = None) -> Any:
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(read_text(p))


def load_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def extract_records(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        for key in ("records", "page_records", "node_plans", "nodes", "memory_records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def normalize_path_string(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("\\", "/")


def document_id_from_page_id(page_id: str) -> str:
    if "_p" in page_id:
        return page_id.rsplit("_p", 1)[0]
    return "unknown_document"


def page_number_from_page_id(page_id: str) -> int | None:
    m = re.search(r"p(\d{6})$", page_id)
    if not m:
        return None
    return int(m.group(1))


def page_id_from_path(path: Path | str, default_document_id: str = "t_p_120_1176") -> str | None:
    text = normalize_path_string(str(path))
    m = PAGE_ID_RE.search(text)
    if m:
        return m.group(1).lower()
    matches = list(PAGE_NUMBER_RE.finditer(text))
    if matches:
        # Prefer the last six-digit token because paths often include document ids too.
        number = matches[-1].group(1)
        return f"{default_document_id}_p{number}"
    return None


def compute_fingerprint(path: Path, mode: str = "stat") -> str:
    stat = path.stat()
    if mode == "sha256":
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    return f"stat:{stat.st_size}:{stat.st_mtime_ns}"


def file_record_for_path(path: Path, root: Path, *, fingerprint_mode: str, default_document_id: str) -> dict[str, Any]:
    stat = path.stat()
    rel_path = normalize_path_string(str(path.relative_to(root))) if path.is_relative_to(root) else normalize_path_string(str(path))
    abs_path = normalize_path_string(str(path.resolve()))
    source_path = normalize_path_string(str(path))
    page_id = page_id_from_path(path, default_document_id=default_document_id)
    document_id = document_id_from_page_id(page_id) if page_id else default_document_id
    fingerprint = compute_fingerprint(path, mode=fingerprint_mode)
    file_id = "srcfile__" + stable_hash({"path": source_path, "fingerprint": fingerprint}, 20)
    return {
        "file_id": file_id,
        "document_id": document_id,
        "page_ids": [page_id] if page_id else [],
        "source_path": source_path,
        "relative_path": rel_path,
        "absolute_path": abs_path,
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "fingerprint_mode": fingerprint_mode,
        "fingerprint": fingerprint,
        "exists": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
    }


def should_skip_dir(path: Path, excludes: set[str]) -> bool:
    return any(part in excludes for part in path.parts)


def scan_source_roots(
    roots: list[str | Path],
    *,
    fingerprint_mode: str = "stat",
    suffixes: set[str] | None = None,
    dir_excludes: set[str] | None = None,
    default_document_id: str = "t_p_120_1176",
) -> list[dict[str, Any]]:
    suffixes = suffixes or DEFAULT_SOURCE_SUFFIXES
    dir_excludes = dir_excludes or DEFAULT_DIR_EXCLUDES
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root_value in roots:
        root = Path(root_value)
        if not root.exists():
            continue
        if root.is_file():
            files = [root]
            scan_root = root.parent
        else:
            scan_root = root
            files = []
            for path in sorted(root.rglob("*")):
                if should_skip_dir(path, dir_excludes):
                    continue
                if path.is_file() and (not suffixes or path.suffix.lower() in suffixes):
                    files.append(path)
        for path in files:
            key = normalize_path_string(str(path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            try:
                records.append(file_record_for_path(path, scan_root, fingerprint_mode=fingerprint_mode, default_document_id=default_document_id))
            except OSError:
                continue
    return records


def previous_source_index(previous_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not previous_manifest:
        return {}
    source_records = previous_manifest.get("source_file_records") or previous_manifest.get("source_files") or []
    index: dict[str, dict[str, Any]] = {}
    for record in source_records:
        if not isinstance(record, dict):
            continue
        path = normalize_path_string(record.get("source_path") or record.get("absolute_path") or record.get("relative_path") or "")
        if path:
            index[path] = record
    return index


def compare_source_records(current: list[dict[str, Any]], previous_manifest: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prev = previous_source_index(previous_manifest)
    current_paths = {normalize_path_string(r.get("source_path")) for r in current}
    compared: list[dict[str, Any]] = []
    for record in current:
        source_path = normalize_path_string(record.get("source_path"))
        old = prev.get(source_path)
        if old is None:
            state = "new"
        elif old.get("fingerprint") != record.get("fingerprint"):
            state = "changed"
        else:
            state = "unchanged"
        dirty_stages = list(DEFAULT_DIRTY_STAGES) if state in {"new", "changed"} else []
        compared.append({**record, "change_state": state, "dirty_stages": dirty_stages})
    missing: list[dict[str, Any]] = []
    for path, old in prev.items():
        if path not in current_paths:
            missing.append({**old, "exists": False, "change_state": "missing", "dirty_stages": ["source_removed", "graph_writeback", "qdrant_delete", "opensearch_delete", "leiden_communities"]})
    return compared, missing


def records_by_page(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        page_id = record.get("page_id") or record.get("page")
        if isinstance(page_id, str) and page_id:
            by_page[page_id].append(record)
        for page_id in record.get("page_ids") or []:
            if isinstance(page_id, str) and page_id:
                by_page[page_id].append(record)
    return dict(by_page)


def load_page_registry_records(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_json(path, default={})
    records = extract_records(payload, "records")
    return payload if isinstance(payload, dict) else {}, records


def collect_page_ids(page_registry_records: list[dict[str, Any]], embedding_records: list[dict[str, Any]], source_records: list[dict[str, Any]]) -> list[str]:
    page_ids: set[str] = set()
    for record in page_registry_records:
        page_id = record.get("page_id")
        if isinstance(page_id, str) and page_id:
            page_ids.add(page_id)
    for record in embedding_records:
        page_id = record.get("page_id")
        if isinstance(page_id, str) and page_id:
            page_ids.add(page_id)
    for record in source_records:
        for page_id in record.get("page_ids") or []:
            if isinstance(page_id, str) and page_id:
                page_ids.add(page_id)
    return sorted(page_ids, key=lambda p: (document_id_from_page_id(p), page_number_from_page_id(p) or 0, p))


def artifact_quality_status(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    return (
        payload.get("quality_status")
        or payload.get("status")
        or payload.get("quality", {}).get("status") if isinstance(payload.get("quality"), dict) else None
    )


def make_page_manifest_records(
    *,
    page_ids: list[str],
    page_registry_records: list[dict[str, Any]],
    embedding_records: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    missing_source_records: list[dict[str, Any]],
    graph_attachment_payload: dict[str, Any] | None,
    leiden_payload: dict[str, Any] | None,
    feedback_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    registry_by_page = {r.get("page_id"): r for r in page_registry_records if r.get("page_id")}
    embeddings_by_page = records_by_page(embedding_records)
    sources_by_page = records_by_page(source_records)
    missing_sources_by_page = records_by_page(missing_source_records)

    graph_nodes_by_page: dict[str, int] = Counter()
    graph_edges_by_page: dict[str, int] = Counter()
    if isinstance(graph_attachment_payload, dict):
        for node in graph_attachment_payload.get("node_plans", []) or []:
            page_id = node.get("page_id")
            if page_id:
                graph_nodes_by_page[page_id] += 1
        for edge in graph_attachment_payload.get("edge_plans", []) or []:
            page_id = edge.get("page_id")
            if page_id:
                graph_edges_by_page[page_id] += 1

    communities_by_page: dict[str, list[str]] = defaultdict(list)
    if isinstance(leiden_payload, dict):
        for member in leiden_payload.get("node_membership", []) or []:
            page_id = member.get("page_id")
            community_id = member.get("community_id")
            if page_id and community_id and community_id not in communities_by_page[page_id]:
                communities_by_page[page_id].append(community_id)
        for community in leiden_payload.get("communities", []) or []:
            community_id = community.get("community_id")
            for page_id in community.get("page_ids") or []:
                if page_id and community_id and community_id not in communities_by_page[page_id]:
                    communities_by_page[page_id].append(community_id)

    feedback_by_page: dict[str, int] = Counter()
    if isinstance(feedback_payload, dict):
        for record in feedback_payload.get("memory_records", []) or []:
            for page_id in record.get("page_ids") or []:
                feedback_by_page[page_id] += 1

    output: list[dict[str, Any]] = []
    for page_id in page_ids:
        registry = registry_by_page.get(page_id, {})
        source_records_for_page = sources_by_page.get(page_id, [])
        changed_sources = [r for r in source_records_for_page if r.get("change_state") in {"new", "changed"}]
        missing_sources = missing_sources_by_page.get(page_id, [])
        candidate_records = embeddings_by_page.get(page_id, [])
        candidate_bucket_counts = Counter(r.get("rag_bucket") or r.get("bucket") or "unknown" for r in candidate_records)
        has_changed_input = bool(changed_sources or missing_sources)
        dirty_stages: list[str] = []
        if has_changed_input:
            dirty_stages = list(DEFAULT_DIRTY_STAGES)
        elif not candidate_records:
            dirty_stages = ["safe_candidates", "embeddings", "qdrant_upsert", "opensearch_upsert"]
        page_number = registry.get("page_number") or page_number_from_page_id(page_id)
        detected_elements = registry.get("detected_elements") or []
        recommended_routes = registry.get("recommended_extraction_routes") or registry.get("routes") or []
        source_file_ids = [r.get("file_id") for r in source_records_for_page if r.get("file_id")]
        page_record = {
            "page_id": page_id,
            "document_id": document_id_from_page_id(page_id),
            "page_number": page_number,
            "source_file_ids": source_file_ids,
            "source_file_count": len(source_file_ids),
            "source_change_states": sorted({r.get("change_state") for r in source_records_for_page if r.get("change_state")}),
            "missing_source_record_count": len(missing_sources),
            "detected_element_count": len(detected_elements),
            "recommended_route_count": len(recommended_routes),
            "embedding_candidate_count": len(candidate_records),
            "candidate_bucket_counts": dict(candidate_bucket_counts),
            "graph_node_plan_count": graph_nodes_by_page.get(page_id, 0),
            "graph_edge_plan_count": graph_edges_by_page.get(page_id, 0),
            "community_ids": sorted(communities_by_page.get(page_id, [])),
            "community_count": len(communities_by_page.get(page_id, [])),
            "feedback_memory_record_count": feedback_by_page.get(page_id, 0),
            "dirty_stages": dirty_stages,
            "dirty_stage_count": len(dirty_stages),
            "needs_ocr": "ocr" in dirty_stages,
            "needs_table": "table_understanding" in dirty_stages or "table_cell_normalizer" in dirty_stages,
            "needs_visual": "figure_chart_understanding" in dirty_stages or "visual_ink_layout_calibrator" in dirty_stages,
            "needs_embedding": "embeddings" in dirty_stages,
            "needs_qdrant": "qdrant_upsert" in dirty_stages,
            "needs_opensearch": "opensearch_upsert" in dirty_stages,
            "needs_graph_update": "graph_writeback" in dirty_stages or "graph_attachment" in dirty_stages,
            "needs_leiden_refresh": "leiden_communities" in dirty_stages,
            "last_successful_stage": None if dirty_stages else "unchanged_or_artifact_current",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "manifest_role": "incremental_page_dependency_record",
        }
        output.append(page_record)
    return output


def build_incremental_corpus_manifest(
    *,
    page_registry_path: str | Path,
    embedding_candidates_path: str | Path | None = None,
    element_graph_attachment_path: str | Path | None = None,
    leiden_communities_path: str | Path | None = None,
    feedback_memory_path: str | Path | None = None,
    previous_manifest_path: str | Path | None = None,
    source_roots: list[str | Path] | None = None,
    output_dir: str | Path = "local_data/organization/trace_net/incremental_corpus_manifest",
    fingerprint_mode: str = "stat",
    default_document_id: str = "t_p_120_1176",
    require_page_count: int | None = None,
    min_source_records: int = 0,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    page_registry_payload, page_registry_records = load_page_registry_records(page_registry_path)
    embedding_payload = load_json(embedding_candidates_path, default={}) if embedding_candidates_path else {}
    embedding_records = extract_records(embedding_payload, "records")
    graph_payload = load_json(element_graph_attachment_path, default={}) if element_graph_attachment_path else {}
    leiden_payload = load_json(leiden_communities_path, default={}) if leiden_communities_path else {}
    feedback_payload = load_json(feedback_memory_path, default={}) if feedback_memory_path else {}
    previous_payload = load_json(previous_manifest_path, default=None) if previous_manifest_path else None

    source_roots = source_roots or []
    source_records_raw = scan_source_roots(
        source_roots,
        fingerprint_mode=fingerprint_mode,
        default_document_id=default_document_id,
    )
    source_records, missing_source_records = compare_source_records(source_records_raw, previous_payload)

    page_ids = collect_page_ids(page_registry_records, embedding_records, source_records)
    page_records = make_page_manifest_records(
        page_ids=page_ids,
        page_registry_records=page_registry_records,
        embedding_records=embedding_records,
        source_records=source_records,
        missing_source_records=missing_source_records,
        graph_attachment_payload=graph_payload,
        leiden_payload=leiden_payload,
        feedback_payload=feedback_payload,
    )

    summary = summarize_manifest(
        page_records=page_records,
        source_records=source_records,
        missing_source_records=missing_source_records,
        page_registry_payload=page_registry_payload,
        embedding_payload=embedding_payload,
        graph_payload=graph_payload,
        leiden_payload=leiden_payload,
        feedback_payload=feedback_payload,
        require_page_count=require_page_count,
        min_source_records=min_source_records,
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "INCREMENTAL_CORPUS_MANIFEST_BUILT",
        "quality_status": "PASS" if quality_passes(summary) else "FAIL",
        "created_at": now_iso(),
        "fingerprint_mode": fingerprint_mode,
        "default_document_id": default_document_id,
        "writeback_mode": "read_only_manifest",
        "stage_dependency_graph": STAGE_DEPENDENCY_GRAPH,
        "source_file_records": source_records,
        "missing_source_file_records": missing_source_records,
        "page_manifest_records": page_records,
        "summary": summary,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
    }

    manifest_path = output_path / "trace_net_incremental_corpus_manifest_v1.json"
    source_path = output_path / "trace_net_incremental_corpus_manifest_v1_sources.jsonl"
    pages_path = output_path / "trace_net_incremental_corpus_manifest_v1_pages.jsonl"
    dirty_pages_path = output_path / "trace_net_incremental_corpus_manifest_v1_dirty_pages.jsonl"
    summary_path = output_path / "trace_net_incremental_corpus_manifest_v1_summary.json"
    quality_path = output_path / "trace_net_incremental_corpus_manifest_v1_quality.json"
    readme_path = output_path / "trace_net_incremental_corpus_manifest_v1.md"

    dirty_pages = [p for p in page_records if p.get("dirty_stage_count", 0) > 0]

    write_json(manifest_path, manifest)
    write_jsonl(source_path, source_records + missing_source_records)
    write_jsonl(pages_path, page_records)
    write_jsonl(dirty_pages_path, dirty_pages)
    write_json(summary_path, summary)
    write_manifest_markdown(readme_path, manifest)

    if write_quality:
        write_json(quality_path, quality_report(manifest))
        manifest["quality_path"] = str(quality_path)
        write_json(manifest_path, manifest)

    manifest["report_path"] = str(manifest_path)
    manifest["sources_path"] = str(source_path)
    manifest["pages_path"] = str(pages_path)
    manifest["dirty_pages_path"] = str(dirty_pages_path)
    manifest["summary_path"] = str(summary_path)
    return manifest


def summarize_manifest(
    *,
    page_records: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    missing_source_records: list[dict[str, Any]],
    page_registry_payload: dict[str, Any] | None,
    embedding_payload: dict[str, Any] | None,
    graph_payload: dict[str, Any] | None,
    leiden_payload: dict[str, Any] | None,
    feedback_payload: dict[str, Any] | None,
    require_page_count: int | None,
    min_source_records: int,
) -> dict[str, Any]:
    source_state_counts = Counter(r.get("change_state") for r in source_records + missing_source_records)
    suffix_counts = Counter(r.get("suffix") for r in source_records if r.get("suffix"))
    page_dirty_stage_counts = Counter()
    for record in page_records:
        page_dirty_stage_counts.update(record.get("dirty_stages") or [])

    dirty_page_count = sum(1 for r in page_records if r.get("dirty_stage_count", 0) > 0)
    page_with_source_count = sum(1 for r in page_records if r.get("source_file_count", 0) > 0)
    pages_needing = {
        "needs_ocr_page_count": sum(1 for r in page_records if r.get("needs_ocr")),
        "needs_table_page_count": sum(1 for r in page_records if r.get("needs_table")),
        "needs_visual_page_count": sum(1 for r in page_records if r.get("needs_visual")),
        "needs_embedding_page_count": sum(1 for r in page_records if r.get("needs_embedding")),
        "needs_qdrant_page_count": sum(1 for r in page_records if r.get("needs_qdrant")),
        "needs_opensearch_page_count": sum(1 for r in page_records if r.get("needs_opensearch")),
        "needs_graph_update_page_count": sum(1 for r in page_records if r.get("needs_graph_update")),
        "needs_leiden_refresh_page_count": sum(1 for r in page_records if r.get("needs_leiden_refresh")),
    }
    fingerprints = [r.get("fingerprint") for r in source_records if r.get("fingerprint")]
    duplicate_fingerprint_count = sum(count - 1 for count in Counter(fingerprints).values() if count > 1)

    page_count = len(page_records)
    source_record_count = len(source_records)
    missing_page_id_count = sum(1 for r in page_records if not r.get("page_id"))
    unsafe_manifest_record_count = sum(
        1
        for r in page_records + source_records + missing_source_records
        if r.get("can_answer_directly") or r.get("can_prove_claims") or r.get("can_mutate_source_truth")
    )
    source_truth_mutation_allowed_count = sum(1 for r in page_records + source_records + missing_source_records if r.get("can_mutate_source_truth"))

    checks = {
        "page_count_matches_required": require_page_count is None or page_count == require_page_count,
        "source_record_count_min_met": source_record_count >= min_source_records,
        "missing_page_id_count_zero": missing_page_id_count == 0,
        "unsafe_manifest_record_count_zero": unsafe_manifest_record_count == 0,
        "source_truth_mutation_allowed_count_zero": source_truth_mutation_allowed_count == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": status,
        "page_count": page_count,
        "source_record_count": source_record_count,
        "missing_source_record_count": len(missing_source_records),
        "page_with_source_count": page_with_source_count,
        "dirty_page_count": dirty_page_count,
        "changed_source_count": source_state_counts.get("changed", 0),
        "new_source_count": source_state_counts.get("new", 0),
        "unchanged_source_count": source_state_counts.get("unchanged", 0),
        "removed_source_count": source_state_counts.get("missing", 0),
        "source_state_counts": dict(source_state_counts),
        "source_suffix_counts": dict(suffix_counts),
        "duplicate_source_fingerprint_count": duplicate_fingerprint_count,
        "dirty_stage_counts": dict(page_dirty_stage_counts),
        **pages_needing,
        "missing_page_id_count": missing_page_id_count,
        "unsafe_manifest_record_count": unsafe_manifest_record_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "can_answer_directly_count": sum(1 for r in page_records if r.get("can_answer_directly")),
        "claim_proof_allowed_count": sum(1 for r in page_records if r.get("can_prove_claims")),
        "page_registry_quality_status": artifact_quality_status(page_registry_payload),
        "embedding_candidates_quality_status": artifact_quality_status(embedding_payload),
        "element_graph_attachment_quality_status": artifact_quality_status(graph_payload),
        "leiden_communities_quality_status": artifact_quality_status(leiden_payload),
        "feedback_memory_quality_status": artifact_quality_status(feedback_payload),
        "require_page_count": require_page_count,
        "min_source_records": min_source_records,
        "quality_checks": checks,
        "source_truth_mutations_performed": 0,
    }


def quality_passes(summary: dict[str, Any]) -> bool:
    return summary.get("status") == "PASS" and all((summary.get("quality_checks") or {}).values())


def quality_report(
    manifest_or_path: dict[str, Any] | str | Path,
    *,
    require_page_count: int | None = None,
    min_source_records: int | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    if isinstance(manifest_or_path, (str, Path)):
        manifest = load_json(manifest_or_path, default={})
        report_path = Path(manifest_or_path)
    else:
        manifest = manifest_or_path
        report_path = None

    summary = dict(manifest.get("summary") or {})
    if require_page_count is not None:
        summary["quality_checks"] = dict(summary.get("quality_checks") or {})
        summary["quality_checks"]["page_count_matches_required"] = summary.get("page_count") == require_page_count
        summary["require_page_count"] = require_page_count
    if min_source_records is not None:
        summary["quality_checks"] = dict(summary.get("quality_checks") or {})
        summary["quality_checks"]["source_record_count_min_met"] = summary.get("source_record_count", 0) >= min_source_records
        summary["min_source_records"] = min_source_records

    status = "PASS" if all((summary.get("quality_checks") or {}).values()) else "FAIL"
    report = {
        "schema_version": SCHEMA_VERSION + "_quality",
        "status": status,
        "quality_status": status,
        "summary": summary,
        "page_count": summary.get("page_count", 0),
        "source_record_count": summary.get("source_record_count", 0),
        "dirty_page_count": summary.get("dirty_page_count", 0),
        "new_source_count": summary.get("new_source_count", 0),
        "changed_source_count": summary.get("changed_source_count", 0),
        "removed_source_count": summary.get("removed_source_count", 0),
        "missing_page_id_count": summary.get("missing_page_id_count", 0),
        "unsafe_manifest_record_count": summary.get("unsafe_manifest_record_count", 0),
        "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count", 0),
        "source_truth_mutations_performed": summary.get("source_truth_mutations_performed", 0),
    }
    if write_json_report and report_path is not None:
        quality_path = report_path.with_name("trace_net_incremental_corpus_manifest_v1_quality.json")
        write_json(quality_path, report)
        report["quality_path"] = str(quality_path)
    return report


def write_manifest_markdown(path: Path, manifest: dict[str, Any]) -> None:
    summary = manifest.get("summary") or {}
    lines = [
        "# TRACE-Net Incremental Corpus Manifest v1",
        "",
        f"**Status:** {manifest.get('status')}",
        f"**Quality:** {manifest.get('quality_status')}",
        f"**Fingerprint mode:** {manifest.get('fingerprint_mode')}",
        f"**Writeback mode:** {manifest.get('writeback_mode')}",
        "",
        "## Summary",
        "",
        f"- Pages: {summary.get('page_count', 0)}",
        f"- Source records: {summary.get('source_record_count', 0)}",
        f"- New sources: {summary.get('new_source_count', 0)}",
        f"- Changed sources: {summary.get('changed_source_count', 0)}",
        f"- Unchanged sources: {summary.get('unchanged_source_count', 0)}",
        f"- Removed sources: {summary.get('removed_source_count', 0)}",
        f"- Dirty pages: {summary.get('dirty_page_count', 0)}",
        f"- Unsafe manifest records: {summary.get('unsafe_manifest_record_count', 0)}",
        f"- Source-truth mutation allowed: {summary.get('source_truth_mutation_allowed_count', 0)}",
        "",
        "## Dirty stage counts",
        "",
    ]
    for stage, count in sorted((summary.get("dirty_stage_counts") or {}).items()):
        lines.append(f"- {stage}: {count}")
    lines.extend([
        "",
        "## Safety rule",
        "",
        "This manifest is a planner. It cannot answer directly, prove claims, or mutate source truth.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_manifest_summary(manifest: dict[str, Any]) -> None:
    summary = manifest.get("summary") or {}
    print("TRACE-Net incremental corpus manifest v1")
    print(f" Status: {manifest.get('status')}")
    print(f" Quality status: {manifest.get('quality_status')}")
    print(f" page_count: {summary.get('page_count', 0)}")
    print(f" source_record_count: {summary.get('source_record_count', 0)}")
    print(f" new_source_count: {summary.get('new_source_count', 0)}")
    print(f" changed_source_count: {summary.get('changed_source_count', 0)}")
    print(f" unchanged_source_count: {summary.get('unchanged_source_count', 0)}")
    print(f" removed_source_count: {summary.get('removed_source_count', 0)}")
    print(f" dirty_page_count: {summary.get('dirty_page_count', 0)}")
    print(f" needs_ocr_page_count: {summary.get('needs_ocr_page_count', 0)}")
    print(f" needs_embedding_page_count: {summary.get('needs_embedding_page_count', 0)}")
    print(f" needs_qdrant_page_count: {summary.get('needs_qdrant_page_count', 0)}")
    print(f" needs_opensearch_page_count: {summary.get('needs_opensearch_page_count', 0)}")
    print(f" needs_graph_update_page_count: {summary.get('needs_graph_update_page_count', 0)}")
    print(f" needs_leiden_refresh_page_count: {summary.get('needs_leiden_refresh_page_count', 0)}")
    print(f" unsafe_manifest_record_count: {summary.get('unsafe_manifest_record_count', 0)}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}")
    print(f" report_path: {manifest.get('report_path')}")
    if manifest.get("quality_path"):
        print(f" quality_path: {manifest.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net incremental corpus manifest v1")
    parser.add_argument("--page-registry", required=True)
    parser.add_argument("--embedding-candidates")
    parser.add_argument("--element-graph-attachment")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--feedback-memory")
    parser.add_argument("--previous-manifest")
    parser.add_argument("--source-root", action="append", default=[])
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/incremental_corpus_manifest")
    parser.add_argument("--fingerprint-mode", choices=["stat", "sha256"], default="stat")
    parser.add_argument("--default-document-id", default="t_p_120_1176")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-source-records", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_incremental_corpus_manifest(
        page_registry_path=args.page_registry,
        embedding_candidates_path=args.embedding_candidates,
        element_graph_attachment_path=args.element_graph_attachment,
        leiden_communities_path=args.leiden_communities,
        feedback_memory_path=args.feedback_memory,
        previous_manifest_path=args.previous_manifest,
        source_roots=args.source_root,
        output_dir=args.output_dir,
        fingerprint_mode=args.fingerprint_mode,
        default_document_id=args.default_document_id,
        require_page_count=args.require_page_count,
        min_source_records=args.min_source_records,
        write_quality=args.quality,
    )
    print_manifest_summary(manifest)
    return 0 if manifest.get("quality_status") == "PASS" else 1


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net incremental corpus manifest v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-source-records", type=int)
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    report = quality_report(
        args.report_path,
        require_page_count=args.require_page_count,
        min_source_records=args.min_source_records,
        write_json_report=args.write_json,
    )
    summary = report.get("summary") or {}
    print("TRACE-Net incremental corpus manifest v1 quality")
    print(f" Status: {report.get('status')}")
    print(f" page_count: {summary.get('page_count', 0)}")
    print(f" source_record_count: {summary.get('source_record_count', 0)}")
    print(f" dirty_page_count: {summary.get('dirty_page_count', 0)}")
    print(f" new_source_count: {summary.get('new_source_count', 0)}")
    print(f" changed_source_count: {summary.get('changed_source_count', 0)}")
    print(f" unsafe_manifest_record_count: {summary.get('unsafe_manifest_record_count', 0)}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
