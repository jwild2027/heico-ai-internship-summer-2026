"""TRACE-Net Engineering Engram Vector Loader v1.

Artifact-only adapter that converts H17 Engram memory-layer atoms into a
Qdrant-ready local vector manifest.  This module does not connect to Qdrant,
Postgres, OpenSearch, or any live service.  It produces deterministic local
records so CI and Git review can validate the vector payload shape before a
future live loader is enabled.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

MODULE = "trace_net_engineering_engram_vector_loader_v1"
VERSION = "v1"

REQUIRED_MEMORY_LAYERS = (
    "working_memory",
    "semantic_memory",
    "procedural_memory",
    "episodic_memory",
    "trait_memory",
    "critic_memory",
)

GUIDANCE_ONLY_PROOF_ROLES = {"guidance_only", "current_proof_context_only"}

VECTOR_RECORD_STATUS = "ENGRAM_VECTOR_RECORD_READY"


@dataclass(frozen=True)
class VectorLoaderConfig:
    vector_dim: int = 64
    collection_name: str = "trace_net_engineering_engram_memory_v1"
    encoder_name: str = "trace_net_hashing_encoder_v1"
    distance: str = "Cosine"
    allow_live_qdrant_write: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def atom_identifier(atom: Mapping[str, Any], index: int) -> str:
    raw = str(atom.get("atom_id") or atom.get("id") or atom.get("name") or "").strip()
    if raw:
        return raw
    digest = hashlib.sha256(stable_json_dumps(atom).encode("utf-8")).hexdigest()[:16]
    return f"generated_atom_{index:04d}_{digest}"


def infer_memory_layer(atom: Mapping[str, Any]) -> str:
    layer = str(atom.get("memory_layer") or "").strip()
    if layer:
        return layer
    memory_type = str(atom.get("memory_type") or atom.get("type") or "").lower()
    title = str(atom.get("title") or atom.get("atom_id") or "").lower()
    text = " ".join(str(atom.get(k) or "") for k in ("rule", "description", "lesson", "failure_pattern", "repair_pattern")).lower()
    blob = f"{memory_type} {title} {text}"
    if any(t in blob for t in ("critic", "self-rag", "crag", "repair")):
        return "critic_memory"
    if any(t in blob for t in ("episode", "h13", "h14", "h15", "h16", "failure", "eval")):
        return "episodic_memory"
    if any(t in blob for t in ("style", "trait", "tone", "answer shape", "personality")):
        return "trait_memory"
    if any(t in blob for t in ("policy", "if user", "forbidden", "require", "must", "do not")):
        return "procedural_memory"
    if any(t in blob for t in ("route", "visual", "ocr", "table", "figure", "nomenclature")):
        return "semantic_memory"
    return "working_memory"


def infer_proof_role(atom: Mapping[str, Any], memory_layer: str) -> str:
    proof_role = str(atom.get("proof_role") or "").strip()
    if proof_role:
        return proof_role
    if memory_layer == "working_memory":
        return "current_proof_context_only"
    return "guidance_only"


def atom_to_text(atom: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in (
        "atom_id",
        "title",
        "memory_layer",
        "memory_type",
        "rule",
        "description",
        "trigger",
        "allowed_behavior",
        "forbidden_behavior",
        "failure_pattern",
        "repair_pattern",
        "lesson",
        "runtime_role",
        "proof_role",
    ):
        value = atom.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value = stable_json_dumps(value)
        else:
            value = str(value)
        value = normalize_text(value)
        if value:
            parts.append(f"{key}: {value}")
    return normalize_text(" | ".join(parts))


def deterministic_hash_vector(text: str, dim: int = 64) -> List[float]:
    """Return a deterministic unit-normalized vector for local artifact tests.

    This is not intended to replace a production embedding model.  It gives H18
    stable Qdrant-ready vector records without requiring network calls, GPU, or
    a live vector database.
    """

    if dim <= 0:
        raise ValueError("vector_dim must be positive")
    text = normalize_text(text).lower()
    tokens = re.findall(r"[a-z0-9_\-]+", text)
    vec = [0.0] * dim
    if not tokens:
        tokens = ["empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] % 11) / 10.0
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 8) for v in vec]


def qdrant_point_id(atom_id: str) -> str:
    return hashlib.sha256(atom_id.encode("utf-8")).hexdigest()


def load_memory_atoms(memory_layers_manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    atoms = memory_layers_manifest.get("memory_atoms")
    if not isinstance(atoms, list):
        raise ValueError("H17 memory layer manifest must contain a memory_atoms list")
    normalized: List[Dict[str, Any]] = []
    for idx, atom in enumerate(atoms, start=1):
        if not isinstance(atom, dict):
            continue
        item = dict(atom)
        atom_id = atom_identifier(item, idx)
        layer = infer_memory_layer(item)
        proof_role = infer_proof_role(item, layer)
        item["atom_id"] = atom_id
        item["memory_layer"] = layer
        item["proof_role"] = proof_role
        normalized.append(item)
    return normalized


def make_vector_record(atom: Mapping[str, Any], *, config: VectorLoaderConfig) -> Dict[str, Any]:
    atom_id = str(atom.get("atom_id") or "").strip()
    if not atom_id:
        raise ValueError("atom_id is required")
    memory_layer = str(atom.get("memory_layer") or "").strip()
    proof_role = str(atom.get("proof_role") or "").strip()
    text = atom_to_text(atom)
    vector = deterministic_hash_vector(text, dim=config.vector_dim)
    payload = {
        "atom_id": atom_id,
        "memory_layer": memory_layer,
        "proof_role": proof_role,
        "title": atom.get("title") or atom_id,
        "rule": atom.get("rule") or atom.get("description") or "",
        "source_module": MODULE,
        "source_version": VERSION,
        "active": bool(atom.get("active", True)),
        "engram_memory_is_proof": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
    }
    return {
        "status": VECTOR_RECORD_STATUS,
        "point_id": qdrant_point_id(atom_id),
        "atom_id": atom_id,
        "memory_layer": memory_layer,
        "proof_role": proof_role,
        "text_for_embedding": text,
        "vector": vector,
        "vector_dim": config.vector_dim,
        "encoder": config.encoder_name,
        "qdrant_payload": payload,
    }


def safety_findings(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for rec in records:
        atom_id = rec.get("atom_id")
        layer = rec.get("memory_layer")
        proof_role = rec.get("proof_role")
        payload = rec.get("qdrant_payload") if isinstance(rec.get("qdrant_payload"), dict) else {}
        if layer not in REQUIRED_MEMORY_LAYERS:
            findings.append({"atom_id": atom_id, "code": "UNKNOWN_MEMORY_LAYER", "memory_layer": layer})
        if proof_role not in GUIDANCE_ONLY_PROOF_ROLES:
            findings.append({"atom_id": atom_id, "code": "UNSAFE_PROOF_ROLE", "proof_role": proof_role})
        if payload.get("engram_memory_is_proof"):
            findings.append({"atom_id": atom_id, "code": "ENGRAM_MARKED_AS_PROOF"})
        if payload.get("answer_permission"):
            findings.append({"atom_id": atom_id, "code": "ANSWER_PERMISSION_GRANTED"})
        if payload.get("source_truth_mutation_allowed"):
            findings.append({"atom_id": atom_id, "code": "SOURCE_TRUTH_MUTATION_ALLOWED"})
        for key in ("postgres_write_attempt", "qdrant_write_attempt", "opensearch_write_attempt", "opensearch_upload_attempt"):
            if payload.get(key):
                findings.append({"atom_id": atom_id, "code": "WRITE_ATTEMPT", "field": key})
        vector = rec.get("vector")
        if not isinstance(vector, list) or not vector:
            findings.append({"atom_id": atom_id, "code": "MISSING_VECTOR"})
        if rec.get("text_for_embedding") in (None, ""):
            findings.append({"atom_id": atom_id, "code": "MISSING_TEXT_FOR_EMBEDDING"})
    return findings


def layer_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {layer: 0 for layer in REQUIRED_MEMORY_LAYERS}
    for rec in records:
        layer = rec.get("memory_layer")
        if layer in counts:
            counts[str(layer)] += 1
        else:
            counts[str(layer or "unknown")] = counts.get(str(layer or "unknown"), 0) + 1
    return counts


def build_vector_loader_manifest(
    *,
    memory_layers: str | Path,
    output_dir: str | Path | None = None,
    vector_dim: int = 64,
    collection_name: str = "trace_net_engineering_engram_memory_v1",
    min_records: int = 1,
    require_all_layers: bool = False,
    max_unsafe: int = 0,
) -> Dict[str, Any]:
    config = VectorLoaderConfig(vector_dim=vector_dim, collection_name=collection_name)
    source = read_json(memory_layers)
    atoms = load_memory_atoms(source)
    records = [make_vector_record(atom, config=config) for atom in atoms]
    findings = safety_findings(records)
    counts = layer_counts(records)

    missing_layers = [layer for layer in REQUIRED_MEMORY_LAYERS if counts.get(layer, 0) <= 0]
    write_attempt_count = sum(
        1
        for rec in records
        for k in ("postgres_write_attempt", "qdrant_write_attempt", "opensearch_write_attempt", "opensearch_upload_attempt")
        if isinstance(rec.get("qdrant_payload"), dict) and rec["qdrant_payload"].get(k)
    )
    answer_permission_count = sum(1 for rec in records if isinstance(rec.get("qdrant_payload"), dict) and rec["qdrant_payload"].get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for rec in records if isinstance(rec.get("qdrant_payload"), dict) and rec["qdrant_payload"].get("source_truth_mutation_allowed"))
    qdrant_ready_record_count = len(records)

    quality_status = "PASS"
    quality_failures: List[str] = []
    if qdrant_ready_record_count < min_records:
        quality_status = "FAIL"
        quality_failures.append("min_records_not_met")
    if require_all_layers and missing_layers:
        quality_status = "FAIL"
        quality_failures.append("missing_required_memory_layers")
    if len(findings) > max_unsafe:
        quality_status = "FAIL"
        quality_failures.append("unsafe_finding_count_exceeds_max")
    if answer_permission_count:
        quality_status = "FAIL"
        quality_failures.append("answer_permission_count_nonzero")
    if source_truth_mutation_allowed_count:
        quality_status = "FAIL"
        quality_failures.append("source_truth_mutation_allowed_count_nonzero")
    if write_attempt_count:
        quality_status = "FAIL"
        quality_failures.append("write_attempt_count_nonzero")

    manifest: Dict[str, Any] = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_LOADER_BUILT",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "created_at_utc": utc_now_iso(),
        "source_memory_layers_path": str(memory_layers),
        "collection_plan": {
            "collection_name": collection_name,
            "distance": config.distance,
            "vector_dim": vector_dim,
            "encoder": config.encoder_name,
            "live_qdrant_write_enabled": False,
            "live_qdrant_write_attempted": False,
            "note": "Artifact-only Qdrant-ready payload. Future H19/H20 may enable live writes behind explicit gates.",
        },
        "summary": {
            "module": MODULE,
            "version": VERSION,
            "memory_atom_count": len(atoms),
            "qdrant_ready_record_count": qdrant_ready_record_count,
            "vector_dim": vector_dim,
            "memory_layer_counts": counts,
            "missing_layers": missing_layers,
            "unsafe_finding_count": len(findings),
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": write_attempt_count,
            "quality_failures": quality_failures,
        },
        "safety_contract": {
            "artifact_only": True,
            "engram_memory_is_guidance_only": True,
            "no_answer_permission": True,
            "no_source_truth_mutation": True,
            "no_postgres_write": True,
            "no_qdrant_write": True,
            "no_opensearch_write": True,
            "proof_boundary": "Engram vector records guide behavior retrieval only; source-truth manual claims still require current proof_context citations.",
        },
        "unsafe_findings": findings,
        "qdrant_ready_records": records,
    }

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / f"{MODULE}.json", manifest)
        # JSONL is useful for future import/load tools and human diffing.
        jsonl = out / f"{MODULE}.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
        write_json(out / f"{MODULE}_quality_check.json", {
            "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_LOADER_CHECKED",
            "quality_status": quality_status,
            "summary": manifest["summary"],
            "unsafe_findings": findings,
        })

    return manifest


def check_vector_loader_manifest(
    *,
    vector_loader: str | Path,
    min_records: int = 1,
    require_all_layers: bool = False,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    manifest = read_json(vector_loader)
    records = manifest.get("qdrant_ready_records")
    if not isinstance(records, list):
        raise ValueError("Vector loader manifest must contain qdrant_ready_records list")
    findings = safety_findings(records)
    counts = layer_counts(records)
    missing_layers = [layer for layer in REQUIRED_MEMORY_LAYERS if counts.get(layer, 0) <= 0]
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    write_attempt_count = int(summary.get("write_attempt_count") or 0)
    answer_permission_count = int(summary.get("answer_permission_count") or 0)
    quality_failures: List[str] = []
    quality_status = "PASS"
    if len(records) < min_records:
        quality_status = "FAIL"
        quality_failures.append("min_records_not_met")
    if require_all_layers and missing_layers:
        quality_status = "FAIL"
        quality_failures.append("missing_required_memory_layers")
    if require_quality_pass and manifest.get("quality_status") != "PASS":
        quality_status = "FAIL"
        quality_failures.append("source_quality_status_not_pass")
    if require_no_answer_permission and answer_permission_count:
        quality_status = "FAIL"
        quality_failures.append("answer_permission_count_nonzero")
    if len(findings) > max_unsafe:
        quality_status = "FAIL"
        quality_failures.append("unsafe_finding_count_exceeds_max")
    if write_attempt_count > max_write_attempts:
        quality_status = "FAIL"
        quality_failures.append("write_attempt_count_exceeds_max")

    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_LOADER_CHECKED",
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "summary": {
            "qdrant_ready_record_count": len(records),
            "memory_layer_counts": counts,
            "missing_layers": missing_layers,
            "unsafe_finding_count": len(findings),
            "answer_permission_count": answer_permission_count,
            "write_attempt_count": write_attempt_count,
            "quality_failures": quality_failures,
        },
        "unsafe_findings": findings,
    }
