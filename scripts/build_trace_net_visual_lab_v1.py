#!/usr/bin/env python3
"""Build presentation-safe JSON for the TRACE-Net Visual Lab.

This exporter is intentionally read-only with respect to TRACE-Net source artifacts
and production databases. It discovers completed demonstration artifacts, normalizes
those artifacts into stable browser-facing schemas, computes a two-dimensional PCA
projection of page embeddings, and optionally creates PNG thumbnails from TIFF page
copies that were already produced by the OCR run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

SCHEMA_VERSION = "trace_net_visual_lab_export_v1"
PAGE_ID_RE = re.compile(r"p(\d{6})$")
PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
ROUTE_ORDER = ["blank", "plain_text", "table", "image", "unknown"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"{path}:{line_number} is not a JSON object")
            records.append(value)
    return records


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_value(mapping: Mapping[str, Any] | None, keys: Sequence[str], default: Any = None) -> Any:
    if not isinstance(mapping, Mapping):
        return default
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def deep_find_first(value: Any, keys: Sequence[str]) -> Any:
    if isinstance(value, Mapping):
        direct = first_value(value, keys)
        if direct not in (None, "", [], {}):
            return direct
        for child in value.values():
            found = deep_find_first(child, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(value, list):
        for child in value:
            found = deep_find_first(child, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def deep_find_lists(value: Any, preferred_keys: Sequence[str]) -> list[list[Any]]:
    found: list[list[Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in preferred_keys and isinstance(child, list):
                found.append(child)
            found.extend(deep_find_lists(child, preferred_keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(deep_find_lists(child, preferred_keys))
    return found


def page_number_from_id(page_id: str | None) -> int | None:
    if not page_id:
        return None
    match = PAGE_ID_RE.search(str(page_id))
    return int(match.group(1)) if match else None


def record_page_id(record: Mapping[str, Any]) -> str | None:
    value = first_value(
        record,
        [
            "page_id",
            "canonical_page_id",
            "source_page_id",
            "id",
            "record_id",
        ],
    )
    if value is None:
        page_number = first_value(record, ["page_number", "canonical_page_number", "source_page_number"])
        try:
            return f"page_{int(page_number):06d}"
        except (TypeError, ValueError):
            return None
    return str(value)


def normalize_route(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return "unknown"
    if "blank" in text:
        return "blank"
    if any(token in text for token in ["table", "parts_list", "detailed_parts", "ipl"]):
        return "table"
    if any(token in text for token in ["image", "visual", "diagram", "figure"]):
        return "image"
    if any(token in text for token in ["plain_text", "normal_text", "procedure", "description", "cover", "title"]):
        return "plain_text"
    if text in {"normal", "text"}:
        return "plain_text"
    return text


def discover_one(run_dir: Path, patterns: Sequence[str]) -> Path | None:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(run_dir.rglob(pattern))
    files = sorted({path.resolve() for path in candidates if path.is_file()}, key=lambda p: (len(p.parts), str(p)))
    return files[0] if files else None


def discover_many(run_dir: Path, patterns: Sequence[str]) -> list[Path]:
    candidates: set[Path] = set()
    for pattern in patterns:
        candidates.update(path.resolve() for path in run_dir.rglob(pattern) if path.is_file())
    return sorted(candidates)


def read_records_if_present(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    payload = read_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, Mapping):
        for key in ["records", "pages", "ink_evidence_cards", "items", "nodes", "edges"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def safe_text(path_value: Any, max_chars: int) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"true", "yes", "1", "pass", "eligible", "ready"}


def choose_vector(record: Mapping[str, Any]) -> list[float] | None:
    for key in ["embedding", "vector", "values", "embedding_vector"]:
        value = record.get(key)
        if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
            return [float(item) for item in value]
    for child in record.values():
        if isinstance(child, Mapping):
            value = choose_vector(child)
            if value:
                return value
    return None


def pca_projection(records: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    vectors: list[list[float]] = []
    metadata: list[dict[str, Any]] = []
    dimension_counter: Counter[int] = Counter()

    for record in records:
        vector = choose_vector(record)
        if vector:
            dimension_counter[len(vector)] += 1

    if not dimension_counter:
        return [], {"status": "NO_VECTORS", "point_count": 0, "dimension": 0}

    dimension, _ = dimension_counter.most_common(1)[0]
    for record in records:
        vector = choose_vector(record)
        if not vector or len(vector) != dimension:
            continue
        page_id = record_page_id(record)
        if not page_id:
            continue
        vectors.append(vector)
        metadata.append(
            {
                "page_id": page_id,
                "page_number": page_number_from_id(page_id),
                "route": normalize_route(
                    first_value(record, ["final_route", "route", "accepted_route", "operational_route"])
                ),
                "text_chars": first_value(record, ["text_chars", "text_char_count", "ocr_text_char_count"], 0),
                "model": first_value(record, ["model", "embedding_model"], "bge-m3"),
            }
        )

    if not vectors:
        return [], {"status": "NO_COMPATIBLE_VECTORS", "point_count": 0, "dimension": dimension}

    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - tested through failure contract
        raise RuntimeError("NumPy is required to compute the Visual Lab PCA projection") from exc

    matrix = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    matrix = matrix / norms
    centered = matrix - matrix.mean(axis=0, keepdims=True)

    if centered.shape[0] == 1:
        coordinates = np.zeros((1, 2), dtype=np.float64)
        explained = [1.0, 0.0]
    else:
        gram = centered @ centered.T
        eigenvalues, eigenvectors = np.linalg.eigh(gram)
        order = np.argsort(eigenvalues)[::-1]
        eigenvalues = np.maximum(eigenvalues[order], 0.0)
        eigenvectors = eigenvectors[:, order]
        components = min(2, eigenvectors.shape[1])
        coordinates = eigenvectors[:, :components] * np.sqrt(eigenvalues[:components])
        if components == 1:
            coordinates = np.column_stack([coordinates[:, 0], np.zeros(coordinates.shape[0])])
        total = float(eigenvalues.sum()) or 1.0
        explained = [float(eigenvalues[index] / total) if index < len(eigenvalues) else 0.0 for index in range(2)]

    max_abs = float(np.max(np.abs(coordinates))) if coordinates.size else 1.0
    if max_abs == 0.0:
        max_abs = 1.0
    coordinates = coordinates / max_abs

    output: list[dict[str, Any]] = []
    for index, item in enumerate(metadata):
        output.append(
            {
                **item,
                "x": round(float(coordinates[index, 0]), 7),
                "y": round(float(coordinates[index, 1]), 7),
                "vector_norm": round(float(norms[index, 0]), 7),
                "dimension": dimension,
            }
        )

    return output, {
        "status": "PASS",
        "method": "l2_normalized_centered_pca_via_gram_eigendecomposition",
        "point_count": len(output),
        "dimension": dimension,
        "explained_variance_ratio": [round(value, 7) for value in explained],
        "visualization_warning": (
            "The scatterplot is a two-dimensional PCA projection. The original embedding vectors are unchanged."
        ),
    }


def normalize_graph_nodes(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        node_id = str(first_value(record, ["id", "node_id", "page_id", "key"], f"node_{index}"))
        node_type = str(first_value(record, ["type", "node_type", "label", "kind"], "unknown"))
        label = str(first_value(record, ["display_label", "name", "title", "label", "page_id"], node_id))
        output.append(
            {
                "id": node_id,
                "type": node_type,
                "label": label,
                "page_id": first_value(record, ["page_id", "canonical_page_id"]),
                "properties": {key: value for key, value in record.items() if key not in {"id", "node_id"}},
            }
        )
    return output


def normalize_graph_edges(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        source = first_value(record, ["source", "source_id", "from", "start", "start_id"])
        target = first_value(record, ["target", "target_id", "to", "end", "end_id"])
        if isinstance(source, Mapping):
            source = first_value(source, ["id", "node_id"])
        if isinstance(target, Mapping):
            target = first_value(target, ["id", "node_id"])
        if source is None or target is None:
            continue
        output.append(
            {
                "id": str(first_value(record, ["id", "edge_id"], f"edge_{index}")),
                "source": str(source),
                "target": str(target),
                "type": str(first_value(record, ["type", "relationship", "edge_type", "label"], "RELATED_TO")),
                "properties": {
                    key: value
                    for key, value in record.items()
                    if key not in {"id", "edge_id", "source", "source_id", "target", "target_id"}
                },
            }
        )
    return output


def collect_page_sets(path: Path | None) -> set[str]:
    return {page_id for page_id in (record_page_id(record) for record in read_records_if_present(path)) if page_id}


def find_page_record_files(run_dir: Path) -> dict[str, Path | None]:
    return {
        "ocr": discover_one(run_dir, ["trace_net_ocr_route_scan_pack_v1_records.jsonl"]),
        "resolver": discover_one(run_dir, ["trace_net_route_confidence_resolver_v1_records.jsonl"]),
        "four_route": discover_one(run_dir, ["trace_net_four_route_operational_resolver_v1_records.jsonl"]),
        "validator": discover_one(run_dir, ["trace_net_route_validator_runner_v1_records.jsonl"]),
        "retry": discover_one(run_dir, ["trace_net_route_unresolved_retry_probe_v1_records.jsonl"]),
        "storage": discover_one(run_dir, ["trace_net_four_route_storage_gate_v1_records.jsonl"]),
        "graph_manifest": discover_one(run_dir, ["trace_net_four_route_storage_gate_v1_postgres_graph_manifest.jsonl"]),
        "qdrant_manifest": discover_one(run_dir, ["trace_net_four_route_storage_gate_v1_qdrant_candidates.jsonl"]),
        "opensearch_manifest": discover_one(run_dir, ["trace_net_four_route_storage_gate_v1_opensearch_candidates.jsonl"]),
    }


def map_by_page(records: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for record in records:
        page_id = record_page_id(record)
        if page_id:
            output[page_id] = record
    return output


def create_thumbnail(source: Path, destination: Path, max_side: int) -> bool:
    try:
        from PIL import Image, ImageOps
    except Exception:
        return False
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("L")
            image.thumbnail((max_side, max_side))
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, "PNG", optimize=True)
        return True
    except Exception:
        return False


def normalize_questions(paths: Sequence[Path]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, path in enumerate(paths, start=1):
        payload = read_json(path)
        question = deep_find_first(payload, ["question", "user_question", "prompt", "original_question"])
        answer = deep_find_first(payload, ["final_user_facing_answer", "final_answer", "answer", "response"])
        route = deep_find_first(payload, ["selected_route", "route", "router_decision", "query_route"])
        identifiers = deep_find_first(payload, ["exact_identifiers", "identifiers", "part_numbers"])
        evidence_lists = deep_find_lists(payload, ["evidence_records", "selected_evidence", "evidence", "candidate_evidence"])
        evidence: list[dict[str, Any]] = []
        for candidate in evidence_lists:
            dict_items = [item for item in candidate if isinstance(item, dict)]
            if dict_items:
                evidence = dict_items[:25]
                break
        validation = deep_find_first(payload, ["validation", "answer_validation", "validator_result"])
        gemma_status = deep_find_first(payload, ["gemma_status", "model_status", "llm_status"])
        release = deep_find_first(payload, ["final_release_decision", "release_decision", "answer_allowed"])
        vector_candidates = deep_find_first(payload, ["vector_candidates", "semantic_candidates"])
        deterministic_steps = deep_find_first(payload, ["deterministic_steps", "audit_trace", "steps"])

        output.append(
            {
                "question_number": index,
                "source_file": path.name,
                "question": str(question or f"Question {index}"),
                "route": route,
                "exact_identifiers": identifiers if isinstance(identifiers, list) else ([identifiers] if identifiers else []),
                "evidence": evidence,
                "vector_candidates": vector_candidates if isinstance(vector_candidates, list) else [],
                "deterministic_steps": deterministic_steps if isinstance(deterministic_steps, list) else [],
                "model": deep_find_first(payload, ["model", "llm_model", "gemma_model"]) or "gemma4:26b",
                "gemma_status": gemma_status,
                "answer": answer,
                "validation": validation if isinstance(validation, Mapping) else {},
                "final_release_decision": release,
                "raw": payload,
            }
        )
    return output


def normalize_engram(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "MISSING", "layers": []}
    payload = read_json(path)
    if isinstance(payload, Mapping):
        layers_value = payload.get("layers")
        if isinstance(layers_value, list):
            layers = layers_value
        else:
            layers = []
            aliases = [
                ("working", "WORKING MEMORY"),
                ("semantic", "SEMANTIC MEMORY"),
                ("procedural", "PROCEDURAL MEMORY"),
                ("episodic", "EPISODIC MEMORY"),
                ("trait", "TRAIT MEMORY"),
                ("critic", "CRITIC MEMORY"),
            ]
            for key, label in aliases:
                value = deep_find_first(payload, [key, f"{key}_memory", f"{key}_layer"])
                if value is not None:
                    layers.append({"id": key, "name": label, "content": value})
        if not layers:
            for key, value in payload.items():
                if any(token in key.lower() for token in ["working", "semantic", "procedural", "episodic", "trait", "critic"]):
                    layers.append({"id": key, "name": key.replace("_", " ").upper(), "content": value})
        return {"status": "PASS" if len(layers) >= 6 else "PARTIAL", "layers": layers, "raw": payload}
    return {"status": "INVALID", "layers": [], "raw": payload}


def build_export(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    visual_lab_dir = args.visual_lab_dir.resolve()
    dataset_dir = visual_lab_dir / "data" / args.dataset_slug

    if not run_dir.is_dir():
        raise RuntimeError(f"Run directory does not exist: {run_dir}")
    if dataset_dir.exists() and not args.replace_dataset:
        raise RuntimeError(f"Dataset already exists: {dataset_dir}; pass --replace-dataset to rebuild it")
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    record_files = find_page_record_files(run_dir)
    ocr_records = read_records_if_present(record_files["ocr"])
    resolver_map = map_by_page(read_records_if_present(record_files["resolver"]))
    four_route_map = map_by_page(read_records_if_present(record_files["four_route"]))
    validator_map = map_by_page(read_records_if_present(record_files["validator"]))
    retry_map = map_by_page(read_records_if_present(record_files["retry"]))
    storage_map = map_by_page(read_records_if_present(record_files["storage"]))

    graph_ready = collect_page_sets(record_files["graph_manifest"])
    qdrant_ready = collect_page_sets(record_files["qdrant_manifest"])
    opensearch_ready = collect_page_sets(record_files["opensearch_manifest"])

    page_ids = sorted(
        {
            page_id
            for page_id in (
                [record_page_id(record) for record in ocr_records]
                + list(resolver_map)
                + list(four_route_map)
                + list(validator_map)
                + list(retry_map)
                + list(storage_map)
                + list(graph_ready)
            )
            if page_id
        },
        key=lambda value: (page_number_from_id(value) or 10**9, value),
    )

    ocr_map = map_by_page(ocr_records)
    source_lineage: list[dict[str, Any]] = []
    ocr_pages: list[dict[str, Any]] = []
    classification_pages: list[dict[str, Any]] = []
    storage_pages: list[dict[str, Any]] = []
    thumbnails_made = 0

    for page_id in page_ids:
        ocr = ocr_map.get(page_id, {})
        resolver = resolver_map.get(page_id, {})
        four_route = four_route_map.get(page_id, {})
        validator = validator_map.get(page_id, {})
        retry = retry_map.get(page_id, {})
        storage = storage_map.get(page_id, {})
        page_number = page_number_from_id(page_id) or first_value(
            ocr,
            ["canonical_page_number", "page_number", "source_page_number"],
        )

        initial_route = normalize_route(
            first_value(
                resolver,
                ["primary_route", "resolved_route", "route", "accepted_route", "route_subtype"],
                first_value(ocr, ["accepted_route"]),
            )
        )
        operational_route = normalize_route(
            first_value(
                four_route,
                ["operational_route", "final_operational_route", "route", "accepted_route"],
                initial_route,
            )
        )
        validated_route = normalize_route(
            first_value(
                validator,
                ["validated_operational_route", "final_validated_operational_route", "route"],
                operational_route,
            )
        )
        retry_route_value = first_value(
            retry,
            ["final_validated_operational_route", "validated_operational_route", "final_route"],
        )
        graph_only = not bool(retry_route_value) and page_id in graph_ready and page_id not in qdrant_ready
        final_route = normalize_route(
            retry_route_value
            or first_value(retry, ["source_operational_route", "operational_route"])
            or validated_route
            or operational_route
            or initial_route
        )

        source_image_path = first_value(ocr, ["source_image_path", "image_path", "tiff_path"])
        thumbnail_rel = None
        if args.copy_thumbnails and source_image_path:
            source_path = Path(str(source_image_path))
            destination = dataset_dir / "thumbnails" / f"{page_id}.png"
            if source_path.is_file() and create_thumbnail(source_path, destination, args.thumbnail_max_side):
                thumbnail_rel = f"data/{args.dataset_slug}/thumbnails/{destination.name}"
                thumbnails_made += 1

        ocr_text = safe_text(first_value(ocr, ["ocr_text_path"]), args.max_ocr_chars)
        if not ocr_text:
            ocr_text = str(first_value(ocr, ["ocr_text", "ocr_sample_text", "text"], ""))[: args.max_ocr_chars]

        part_numbers = first_value(ocr, ["part_number_tokens"], [])
        if not isinstance(part_numbers, list):
            part_numbers = PART_NUMBER_RE.findall(ocr_text)

        source_member = first_value(ocr, ["source_member", "file_name"])
        source_hash = first_value(ocr, ["source_image_sha256", "raw_tiff_sha256"])
        lineage_ready = bool(page_id and source_member and source_hash)

        source_lineage.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "source_member": source_member,
                "source_image_sha256": source_hash,
                "source_image_byte_count": first_value(ocr, ["source_image_byte_count", "byte_count"]),
                "source_image_path": source_image_path,
                "ocr_text_sha256": first_value(ocr, ["ocr_text_sha256"]),
                "lineage_ready": lineage_ready,
                "graph_ready": page_id in graph_ready,
                "vector_eligible": page_id in qdrant_ready,
                "exact_search_eligible": page_id in opensearch_ready,
                "thumbnail": thumbnail_rel,
            }
        )

        attempts = first_value(ocr, ["tesseract_attempts"], [])
        ocr_pages.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "source_member": source_member,
                "thumbnail": thumbnail_rel,
                "image_width_px": first_value(ocr, ["image_width_px", "width"]),
                "image_height_px": first_value(ocr, ["image_height_px", "height"]),
                "ocr_status": first_value(ocr, ["tesseract_execution_status", "ocr_status", "status"], "unknown"),
                "ocr_text": ocr_text,
                "ocr_text_char_count": first_value(ocr, ["ocr_text_char_count"], len(ocr_text)),
                "ocr_text_word_count": first_value(ocr, ["ocr_text_word_count"], len(ocr_text.split())),
                "best_psm": first_value(ocr, ["tesseract_best_psm"]),
                "attempts": attempts if isinstance(attempts, list) else [],
                "part_numbers": part_numbers,
                "table_keyword_count": first_value(ocr, ["table_keyword_count"], 0),
                "visual_keyword_count": first_value(ocr, ["visual_keyword_count"], 0),
                "numeric_token_count": first_value(ocr, ["numeric_token_count"], 0),
                "ink_ratio": first_value(ocr, ["ink_ratio_estimate", "ink_density"]),
                "route_hint": normalize_route(first_value(ocr, ["accepted_route"])),
            }
        )

        classification_pages.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "initial_route": initial_route,
                "operational_route": operational_route,
                "validated_route": validated_route,
                "final_route": final_route,
                "route_subtype": first_value(
                    retry,
                    ["route_subtype"],
                    first_value(resolver, ["route_subtype", "primary_route"]),
                ),
                "resolver_confidence": first_value(resolver, ["route_confidence", "confidence", "final_confidence"]),
                "validator_status": first_value(validator, ["validation_status", "status"]),
                "retry_status": first_value(retry, ["retry_status", "status"]),
                "final_validation_score": first_value(retry, ["final_validation_score", "score"]),
                "reasons": first_value(
                    retry,
                    ["final_validation_reasons", "reasons"],
                    first_value(validator, ["validation_reasons", "reasons"], []),
                ),
                "graph_only_safety_hold": graph_only,
                "retrieval_validated": page_id in qdrant_ready or page_id in opensearch_ready,
                "unknown": final_route == "unknown",
            }
        )

        storage_pages.append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "final_route": final_route,
                "graph_ready": page_id in graph_ready,
                "vector_eligible": page_id in qdrant_ready,
                "exact_search_eligible": page_id in opensearch_ready,
                "graph_only_safety_hold": graph_only,
                "reason": (
                    "validator-gated graph-only safety hold"
                    if graph_only
                    else first_value(storage, ["eligibility_reason", "storage_reason", "reason"], "eligible by storage gate")
                ),
                "postgres_write_attempt_count": first_value(storage, ["postgres_write_attempt_count"], 0),
                "qdrant_write_attempt_count": first_value(storage, ["qdrant_write_attempt_count"], 0),
                "opensearch_write_attempt_count": first_value(storage, ["opensearch_write_attempt_count"], 0),
            }
        )

    route_counts = Counter(item["final_route"] for item in classification_pages)
    graph_nodes_path = discover_one(run_dir, ["trace_net_demo_graph_nodes_*.jsonl"])
    graph_edges_path = discover_one(run_dir, ["trace_net_demo_graph_edges_*.jsonl"])
    graph_nodes = normalize_graph_nodes(read_records_if_present(graph_nodes_path))
    graph_edges = normalize_graph_edges(read_records_if_present(graph_edges_path))

    embedding_path = discover_one(run_dir, ["trace_net_demo_page_embeddings_*.jsonl", "*page_embeddings*.jsonl"])
    embedding_records = read_records_if_present(embedding_path)
    route_by_page = {item["page_id"]: item["final_route"] for item in classification_pages}
    for record in embedding_records:
        page_id = record_page_id(record)
        if page_id:
            record.setdefault("route", route_by_page.get(page_id, "unknown"))
    vector_points, vector_summary = pca_projection(embedding_records)

    engram_path = discover_one(run_dir, ["trace_net_demo_engram_layers_*.json", "*engram_layers*.json"])
    engram = normalize_engram(engram_path)

    question_paths = discover_many(run_dir, ["trace_net_demo_question_*_v*.json", "*question_??*.json"])
    questions = normalize_questions(question_paths)

    write_attempt_count = sum(
        numeric(item.get("postgres_write_attempt_count"))
        + numeric(item.get("qdrant_write_attempt_count"))
        + numeric(item.get("opensearch_write_attempt_count"))
        for item in storage_pages
    )

    required_artifacts = {
        "ocr_records": record_files["ocr"],
        "graph_nodes": graph_nodes_path,
        "graph_edges": graph_edges_path,
        "engram": engram_path,
        "embeddings": embedding_path,
    }
    missing_artifacts = [name for name, path in required_artifacts.items() if path is None]
    failures: list[str] = []
    if args.require_page_count is not None and len(page_ids) != args.require_page_count:
        failures.append(f"page_count_expected_{args.require_page_count}_found_{len(page_ids)}")
    if missing_artifacts:
        failures.extend(f"missing_{name}" for name in missing_artifacts)
    if any(item["unknown"] for item in classification_pages):
        failures.append("unknown_page_routes_present")
    if write_attempt_count != 0:
        failures.append("production_write_attempts_nonzero")
    if vector_summary.get("status") != "PASS":
        failures.append("vector_projection_not_built")
    if len(engram.get("layers", [])) < 6:
        failures.append("engram_layer_count_below_6")

    quality_status = "PASS" if not failures else "FAIL"
    dataset_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "TRACE_NET_VISUAL_LAB_DATASET_BUILT",
        "quality_status": quality_status,
        "generated_at_utc": utc_now(),
        "dataset_slug": args.dataset_slug,
        "dataset_label": args.dataset_label,
        "run_directory_name": run_dir.name,
        "page_count": len(page_ids),
        "route_counts": dict(sorted(route_counts.items())),
        "lineage_ready_count": sum(bool(item["lineage_ready"]) for item in source_lineage),
        "graph_node_count": len(graph_nodes),
        "graph_edge_count": len(graph_edges),
        "embedding_point_count": len(vector_points),
        "embedding_dimension": vector_summary.get("dimension", 0),
        "engram_layer_count": len(engram.get("layers", [])),
        "question_count": len(questions),
        "graph_ready_count": len(graph_ready),
        "vector_eligible_count": len(qdrant_ready),
        "exact_search_eligible_count": len(opensearch_ready),
        "graph_only_safety_hold_count": sum(bool(item["graph_only_safety_hold"]) for item in storage_pages),
        "thumbnail_count": thumbnails_made,
        "production_write_attempt_count": int(write_attempt_count),
        "files": {
            "source_lineage": "source_lineage.json",
            "ocr_pages": "ocr_pages.json",
            "classification": "classification.json",
            "graph_nodes": "graph_nodes.json",
            "graph_edges": "graph_edges.json",
            "vector_projection": "vector_projection.json",
            "engram_layers": "engram_layers.json",
            "storage_plan": "storage_plan.json",
            "question_traces": "question_traces.json",
            "quality_summary": "quality_summary.json",
        },
        "failures": failures,
    }

    write_json(dataset_dir / "manifest.json", dataset_manifest)
    write_json(dataset_dir / "source_lineage.json", {"records": source_lineage})
    write_json(dataset_dir / "ocr_pages.json", {"records": ocr_pages})
    write_json(
        dataset_dir / "classification.json",
        {"summary": {"route_counts": dict(sorted(route_counts.items()))}, "records": classification_pages},
    )
    write_json(dataset_dir / "graph_nodes.json", {"records": graph_nodes})
    write_json(dataset_dir / "graph_edges.json", {"records": graph_edges})
    write_json(dataset_dir / "vector_projection.json", {"summary": vector_summary, "records": vector_points})
    write_json(dataset_dir / "engram_layers.json", engram)
    write_json(
        dataset_dir / "storage_plan.json",
        {
            "summary": {
                "graph_ready_count": len(graph_ready),
                "vector_eligible_count": len(qdrant_ready),
                "exact_search_eligible_count": len(opensearch_ready),
                "graph_only_safety_hold_count": sum(bool(item["graph_only_safety_hold"]) for item in storage_pages),
                "production_write_attempt_count": int(write_attempt_count),
            },
            "records": storage_pages,
        },
    )
    write_json(dataset_dir / "question_traces.json", {"records": questions})
    write_json(
        dataset_dir / "quality_summary.json",
        {
            "quality_status": quality_status,
            "checks": {
                "page_count": len(page_ids),
                "unknown_route_count": sum(bool(item["unknown"]) for item in classification_pages),
                "lineage_not_ready_count": sum(not bool(item["lineage_ready"]) for item in source_lineage),
                "production_write_attempt_count": int(write_attempt_count),
                "missing_artifacts": missing_artifacts,
                "vector_projection_status": vector_summary.get("status"),
                "engram_layer_count": len(engram.get("layers", [])),
            },
            "failures": failures,
            "artifact_sources": {name: str(path) if path else None for name, path in required_artifacts.items()},
        },
    )

    catalog_path = visual_lab_dir / "data" / "catalog.json"
    catalog = {"schema_version": SCHEMA_VERSION, "datasets": []}
    if catalog_path.is_file():
        existing = read_json(catalog_path)
        if isinstance(existing, Mapping) and isinstance(existing.get("datasets"), list):
            catalog = dict(existing)
    datasets = [item for item in catalog.get("datasets", []) if item.get("slug") != args.dataset_slug]
    datasets.append(
        {
            "slug": args.dataset_slug,
            "label": args.dataset_label,
            "manifest": f"data/{args.dataset_slug}/manifest.json",
            "page_count": len(page_ids),
            "quality_status": quality_status,
            "generated_at_utc": dataset_manifest["generated_at_utc"],
        }
    )
    datasets.sort(key=lambda item: item.get("label", ""))
    write_json(catalog_path, {"schema_version": SCHEMA_VERSION, "datasets": datasets})

    print("TRACE-Net Visual Lab exporter v1")
    print("status=TRACE_NET_VISUAL_LAB_DATASET_BUILT")
    print(f"quality_status={quality_status}")
    print(f"dataset_slug={args.dataset_slug}")
    print(f"page_count={len(page_ids)}")
    print(f"route_counts={json.dumps(dict(sorted(route_counts.items())))}")
    print(f"lineage_ready_count={dataset_manifest['lineage_ready_count']}")
    print(f"graph_node_count={len(graph_nodes)}")
    print(f"graph_edge_count={len(graph_edges)}")
    print(f"embedding_point_count={len(vector_points)}")
    print(f"embedding_dimension={vector_summary.get('dimension', 0)}")
    print(f"engram_layer_count={len(engram.get('layers', []))}")
    print(f"question_count={len(questions)}")
    print(f"thumbnail_count={thumbnails_made}")
    print(f"production_write_attempt_count={int(write_attempt_count)}")
    print(f"failure_count={len(failures)}")
    for failure in failures:
        print(f"failure={failure}")
    print(f"dataset_dir={dataset_dir}")
    print(f"catalog={catalog_path}")

    return dataset_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--visual-lab-dir",
        type=Path,
        default=Path("local_data/organization/trace_net/visual_lab"),
    )
    parser.add_argument("--dataset-slug", required=True)
    parser.add_argument("--dataset-label", required=True)
    parser.add_argument("--replace-dataset", action="store_true")
    parser.add_argument("--copy-thumbnails", action="store_true")
    parser.add_argument("--thumbnail-max-side", type=int, default=420)
    parser.add_argument("--max-ocr-chars", type=int, default=6000)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_export(args)
    except Exception as exc:
        print(f"quality_status=FAIL", file=sys.stderr)
        print(f"error_type={type(exc).__name__}", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 2
    if args.quality and result.get("quality_status") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
