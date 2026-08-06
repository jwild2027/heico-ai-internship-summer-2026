#!/usr/bin/env python3
"""TRACE-Net Page Context V2 Gemma adapter v1.

This adapter reads the new Gemma4 V2 summary runner output and writes the older
TRACE-Net page_context_v2 graph/artifact shape:

    page:<page_id> -[:HAS_CONTEXT_V2]-> page_context_v2:<page_id>

The adapter is intentionally non-mutating. It writes local JSON/JSONL artifacts
only and gives the summaries guidance status, not source-truth/proof status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ADAPTER_VERSION = "trace_net_page_context_v2_gemma_adapter_v1"
LEGACY_NODE_TYPE = "page_context_v2"
LEGACY_EDGE_TYPE = "HAS_CONTEXT_V2"
SOURCE_RUNNER = "trace_net_v2_gemma_summary_sample_runner_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/page_context_v2")

RECORDS_JSON = "trace_net_page_context_v2_records.json"
RECORDS_JSONL = "trace_net_page_context_v2_records.jsonl"
GRAPH_NODES_JSON = "trace_net_page_context_v2_graph_nodes.json"
GRAPH_EDGES_JSON = "trace_net_page_context_v2_graph_edges.json"
MANIFEST_JSON = "trace_net_page_context_v2_gemma_adapter_v1.json"
QUALITY_JSON = "trace_net_page_context_v2_gemma_adapter_v1_quality_check.json"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def load_gemma_records(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load Gemma V2 output.

    Accepted shapes:
    - manifest dict with key ``records``
    - raw list of records
    - JSONL file containing one record per line
    """
    if not path.exists():
        raise FileNotFoundError(f"Gemma V2 input not found: {path}")

    if path.suffix.lower() == ".jsonl":
        records: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError(f"JSONL line {line_no} is not an object in {path}")
                records.append(item)
        return records, {"input_shape": "jsonl_records", "summary": {}}

    data = read_json(path)
    if isinstance(data, list):
        records = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"Record {i} is not an object in {path}")
            records.append(item)
        return records, {"input_shape": "json_record_list", "summary": {}}

    if isinstance(data, dict):
        raw_records = data.get("records")
        if raw_records is None and isinstance(data.get("record"), dict):
            raw_records = [data["record"]]
        if not isinstance(raw_records, list):
            raise ValueError(f"Input JSON dict must contain a records list: {path}")
        records = []
        for i, item in enumerate(raw_records):
            if not isinstance(item, dict):
                raise ValueError(f"Record {i} is not an object in {path}")
            records.append(item)
        meta = {
            "input_shape": "manifest_with_records",
            "quality_status": data.get("quality_status"),
            "failure_reasons": data.get("failure_reasons", []),
            "summary": data.get("summary", {}),
        }
        return records, meta

    raise ValueError(f"Unsupported Gemma V2 input shape in {path}")


def stable_edge_id(source_id: str, edge_type: str, target_id: str) -> str:
    digest = hashlib.sha1(f"{source_id}|{edge_type}|{target_id}".encode("utf-8")).hexdigest()[:20]
    return f"edge:{digest}"


def page_context_id(page_id: str) -> str:
    return f"page_context_v2:{page_id}"


def page_node_id(page_id: str) -> str:
    return f"page:{page_id}"


def build_legacy_context_record(gemma_record: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = norm_text(gemma_record.get("page_id"))
    if not page_id:
        raise ValueError("Gemma record is missing page_id")

    context_id = page_context_id(page_id)
    retrieval_cues = as_list(gemma_record.get("retrieval_cues"))
    important_entities = as_list(gemma_record.get("important_entities"))

    # Preserve old page_context_v2 naming while adding the newer Gemma fields.
    return {
        "id": context_id,
        "context_id": context_id,
        "page_id": page_id,
        "record_type": LEGACY_NODE_TYPE,
        "context_version": "v2",
        "adapter_version": ADAPTER_VERSION,
        "source_runner": SOURCE_RUNNER,
        "summary_source": "gemma4_v2_summary_runner",
        "generation_model": gemma_record.get("generation_model"),
        "llm_status": gemma_record.get("llm_status"),
        "role": gemma_record.get("role"),
        "subrole": gemma_record.get("subrole"),
        "confidence": gemma_record.get("confidence"),
        "short_summary": gemma_record.get("short_summary"),
        "retrieval_summary": gemma_record.get("retrieval_summary"),
        "retrieval_cues": retrieval_cues,
        "important_entities": important_entities,
        "source_grounding": gemma_record.get("source_grounding", {}),
        "authority": gemma_record.get("authority", {}),
        "v3_preview": gemma_record.get("v3_preview"),
        "prompt_version": gemma_record.get("prompt_version"),
        "source_page_node_id": page_node_id(page_id),
        "graph_node_id": context_id,
        "graph_edge_type": LEGACY_EDGE_TYPE,
        # Safety/proof boundary: V2 helps route/retrieve but does not prove claims.
        "guidance_only": True,
        "canonical_source_truth": False,
        "requires_source_check": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed": False,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_record_count": 0,
        "proof_boundary": "page_context_v2_is_guidance_only_not_source_truth",
        "original_gemma_record": dict(gemma_record),
    }


def build_graph_node(record: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = norm_text(record.get("page_id"))
    node_id = page_context_id(page_id)
    return {
        "id": node_id,
        "node_id": node_id,
        "type": LEGACY_NODE_TYPE,
        "node_type": LEGACY_NODE_TYPE,
        "label": f"Context v2 {page_id}",
        "page_id": page_id,
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "source_truth_mutation_allowed": False,
        "payload": dict(record),
    }


def build_graph_edge(record: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = norm_text(record.get("page_id"))
    source_id = page_node_id(page_id)
    target_id = page_context_id(page_id)
    edge_id = stable_edge_id(source_id, LEGACY_EDGE_TYPE, target_id)
    return {
        "id": edge_id,
        "edge_id": edge_id,
        "type": LEGACY_EDGE_TYPE,
        "edge_type": LEGACY_EDGE_TYPE,
        "source": source_id,
        "source_id": source_id,
        "target": target_id,
        "target_id": target_id,
        "page_id": page_id,
        "guidance_only": True,
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "source_truth_mutation_allowed": False,
        "payload": {
            "adapter_version": ADAPTER_VERSION,
            "source_runner": SOURCE_RUNNER,
            "relationship": "page_has_page_context_v2",
            "proof_boundary": "HAS_CONTEXT_V2 edge exposes retrieval guidance only",
        },
    }


def summarize(records: Sequence[Mapping[str, Any]], nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]], *, input_meta: Mapping[str, Any]) -> Dict[str, Any]:
    page_ids = [norm_text(r.get("page_id")) for r in records]
    duplicate_page_count = len(page_ids) - len(set(page_ids))
    missing_page_id_count = sum(1 for pid in page_ids if not pid)
    role_counts: Dict[str, int] = {}
    llm_status_counts: Dict[str, int] = {}
    for r in records:
        role = norm_text(r.get("role")) or "unknown"
        role_counts[role] = role_counts.get(role, 0) + 1
        status = norm_text(r.get("llm_status")) or "unknown"
        llm_status_counts[status] = llm_status_counts.get(status, 0) + 1

    return {
        "adapter_version": ADAPTER_VERSION,
        "source_runner": SOURCE_RUNNER,
        "input_shape": input_meta.get("input_shape"),
        "input_quality_status": input_meta.get("quality_status"),
        "record_count": len(records),
        "graph_node_count": len(nodes),
        "graph_edge_count": len(edges),
        "unique_page_count": len(set(pid for pid in page_ids if pid)),
        "duplicate_page_count": duplicate_page_count,
        "missing_page_id_count": missing_page_id_count,
        "page_context_v2_node_count": sum(1 for n in nodes if n.get("node_type") == LEGACY_NODE_TYPE or n.get("type") == LEGACY_NODE_TYPE),
        "has_context_v2_edge_count": sum(1 for e in edges if e.get("edge_type") == LEGACY_EDGE_TYPE or e.get("type") == LEGACY_EDGE_TYPE),
        "guidance_only_count": sum(1 for r in records if r.get("guidance_only") is True),
        "canonical_source_truth_count": sum(1 for r in records if r.get("canonical_source_truth") is True),
        "answer_permission_count": sum(1 for r in records if bool(r.get("answer_permission")) or int(r.get("answer_permission_count") or 0) > 0),
        "can_answer_directly_count": sum(1 for r in records if bool(r.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for r in records if bool(r.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(1 for r in records if bool(r.get("source_truth_mutation_allowed")) or int(r.get("source_truth_mutation_allowed_count") or 0) > 0),
        "postgres_write_attempt_count": sum(int(r.get("postgres_write_attempt_count") or 0) for r in records),
        "qdrant_write_attempt_count": sum(int(r.get("qdrant_write_attempt_count") or 0) for r in records),
        "opensearch_write_attempt_count": sum(int(r.get("opensearch_write_attempt_count") or 0) for r in records),
        "unsafe_record_count": sum(int(r.get("unsafe_record_count") or 0) for r in records),
        "role_counts": role_counts,
        "llm_status_counts": llm_status_counts,
    }


def validate_artifacts(records: Sequence[Mapping[str, Any]], nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]], *, min_records: int = 1, expected_records: Optional[int] = None) -> List[str]:
    failures: List[str] = []
    if len(records) < min_records:
        failures.append(f"record_count_below_min:{len(records)}<{min_records}")
    if expected_records is not None and len(records) != expected_records:
        failures.append(f"record_count_mismatch:{len(records)}!={expected_records}")
    if len(nodes) != len(records):
        failures.append(f"graph_node_count_mismatch:{len(nodes)}!={len(records)}")
    if len(edges) != len(records):
        failures.append(f"graph_edge_count_mismatch:{len(edges)}!={len(records)}")

    seen_pages = set()
    for idx, record in enumerate(records):
        page_id = norm_text(record.get("page_id"))
        if not page_id:
            failures.append(f"record_{idx}_missing_page_id")
            continue
        if page_id in seen_pages:
            failures.append(f"duplicate_page_id:{page_id}")
        seen_pages.add(page_id)
        if record.get("record_type") != LEGACY_NODE_TYPE:
            failures.append(f"record_{page_id}_wrong_record_type:{record.get('record_type')}")
        if record.get("id") != page_context_id(page_id):
            failures.append(f"record_{page_id}_wrong_id:{record.get('id')}")
        if record.get("guidance_only") is not True:
            failures.append(f"record_{page_id}_not_guidance_only")
        if record.get("canonical_source_truth") is not False:
            failures.append(f"record_{page_id}_canonical_source_truth_true")
        if bool(record.get("answer_permission")) or int(record.get("answer_permission_count") or 0) > 0:
            failures.append(f"record_{page_id}_answer_permission")
        if bool(record.get("source_truth_mutation_allowed")) or int(record.get("source_truth_mutation_allowed_count") or 0) > 0:
            failures.append(f"record_{page_id}_source_truth_mutation_allowed")

    node_by_id = {norm_text(n.get("id") or n.get("node_id")): n for n in nodes}
    edge_targets = {norm_text(e.get("target") or e.get("target_id")): e for e in edges}
    for record in records:
        page_id = norm_text(record.get("page_id"))
        if not page_id:
            continue
        node_id = page_context_id(page_id)
        source_id = page_node_id(page_id)
        node = node_by_id.get(node_id)
        if not node:
            failures.append(f"missing_node_for_page:{page_id}")
        else:
            if (node.get("node_type") or node.get("type")) != LEGACY_NODE_TYPE:
                failures.append(f"node_{page_id}_wrong_type:{node.get('node_type') or node.get('type')}")
        edge = edge_targets.get(node_id)
        if not edge:
            failures.append(f"missing_edge_for_page:{page_id}")
        else:
            if (edge.get("edge_type") or edge.get("type")) != LEGACY_EDGE_TYPE:
                failures.append(f"edge_{page_id}_wrong_type:{edge.get('edge_type') or edge.get('type')}")
            if (edge.get("source") or edge.get("source_id")) != source_id:
                failures.append(f"edge_{page_id}_wrong_source:{edge.get('source') or edge.get('source_id')}")
            if (edge.get("target") or edge.get("target_id")) != node_id:
                failures.append(f"edge_{page_id}_wrong_target:{edge.get('target') or edge.get('target_id')}")

    return failures


def build_adapter(input_path: Path, output_dir: Path, *, min_records: int = 1, expected_records: Optional[int] = None) -> Dict[str, Any]:
    raw_records, input_meta = load_gemma_records(input_path)
    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for idx, gemma_record in enumerate(raw_records):
        try:
            records.append(build_legacy_context_record(gemma_record))
        except Exception as exc:  # keep adapter inspectable instead of failing silently
            errors.append({"index": idx, "error_type": type(exc).__name__, "error": str(exc)})

    nodes = [build_graph_node(record) for record in records]
    edges = [build_graph_edge(record) for record in records]

    failures = []
    failures.extend(validate_artifacts(records, nodes, edges, min_records=min_records, expected_records=expected_records))
    if errors:
        failures.append(f"record_conversion_error_count:{len(errors)}")

    summary = summarize(records, nodes, edges, input_meta=input_meta)
    summary["conversion_error_count"] = len(errors)
    summary["input_record_count"] = len(raw_records)

    output_dir.mkdir(parents=True, exist_ok=True)
    records_json_path = output_dir / RECORDS_JSON
    records_jsonl_path = output_dir / RECORDS_JSONL
    graph_nodes_path = output_dir / GRAPH_NODES_JSON
    graph_edges_path = output_dir / GRAPH_EDGES_JSON
    manifest_path = output_dir / MANIFEST_JSON

    write_json(records_json_path, records)
    write_jsonl(records_jsonl_path, records)
    write_json(graph_nodes_path, nodes)
    write_json(graph_edges_path, edges)

    manifest = {
        "adapter_version": ADAPTER_VERSION,
        "status": "PAGE_CONTEXT_V2_GEMMA_ADAPTER_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "artifacts": {
            "records_json": str(records_json_path),
            "records_jsonl": str(records_jsonl_path),
            "graph_nodes_json": str(graph_nodes_path),
            "graph_edges_json": str(graph_edges_path),
        },
        "summary": summary,
        "errors": errors,
        "safety_contract": {
            "guidance_only": True,
            "canonical_source_truth": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    write_json(manifest_path, manifest)
    return manifest


def load_manifest_artifacts(manifest_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    manifest = read_json(manifest_path)
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest, dict) else {}
    base = manifest_path.parent

    def artifact_path(key: str, default_name: str) -> Path:
        raw = artifacts.get(key) or str(base / default_name)
        p = Path(raw)
        if not p.is_absolute() and not p.exists():
            # Manifest paths are usually repo-relative. Fall back to manifest dir.
            candidate = base / p.name
            if candidate.exists():
                return candidate
        return p

    records = read_json(artifact_path("records_json", RECORDS_JSON))
    nodes = read_json(artifact_path("graph_nodes_json", GRAPH_NODES_JSON))
    edges = read_json(artifact_path("graph_edges_json", GRAPH_EDGES_JSON))
    if not isinstance(records, list) or not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Adapter artifacts must be JSON lists")
    return manifest, records, nodes, edges


def check_quality(manifest_path: Path, *, output_path: Optional[Path] = None, min_records: int = 1, expected_records: Optional[int] = None, require_quality_pass: bool = False, require_old_v2_graph_contract: bool = False, require_no_answer_permission: bool = False, require_no_source_truth_mutation: bool = False, max_unsafe: Optional[int] = None) -> Dict[str, Any]:
    manifest, records, nodes, edges = load_manifest_artifacts(manifest_path)
    summary = summarize(records, nodes, edges, input_meta={"input_shape": manifest.get("summary", {}).get("input_shape")})
    failures = validate_artifacts(records, nodes, edges, min_records=min_records, expected_records=expected_records)

    manifest_failures = manifest.get("failure_reasons", []) if isinstance(manifest.get("failure_reasons", []), list) else []
    if require_quality_pass and manifest.get("quality_status") != "PASS":
        failures.append(f"manifest_quality_not_pass:{manifest.get('quality_status')}")
    if require_quality_pass and manifest_failures:
        failures.append(f"manifest_has_failure_reasons:{len(manifest_failures)}")

    if require_old_v2_graph_contract:
        if summary["page_context_v2_node_count"] != len(records):
            failures.append("old_contract_missing_page_context_v2_nodes")
        if summary["has_context_v2_edge_count"] != len(records):
            failures.append("old_contract_missing_has_context_v2_edges")

    if require_no_answer_permission and summary["answer_permission_count"] != 0:
        failures.append(f"answer_permission_count_nonzero:{summary['answer_permission_count']}")
    if require_no_source_truth_mutation and summary["source_truth_mutation_allowed_count"] != 0:
        failures.append(f"source_truth_mutation_allowed_count_nonzero:{summary['source_truth_mutation_allowed_count']}")
    if max_unsafe is not None and summary["unsafe_record_count"] > max_unsafe:
        failures.append(f"unsafe_record_count_above_max:{summary['unsafe_record_count']}>{max_unsafe}")

    result = {
        "adapter_version": ADAPTER_VERSION,
        "status": "PAGE_CONTEXT_V2_GEMMA_ADAPTER_QUALITY_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "manifest_path": str(manifest_path),
        "summary": summary,
    }
    if output_path:
        write_json(output_path, result)
    return result


def build_cli_main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Adapt Gemma4 V2 summaries to old TRACE-Net page_context_v2 graph artifacts.")
    p.add_argument("--input", "--gemma-v2-summary", dest="input_path", required=True, help="Gemma V2 summary JSON/JSONL path.")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for old-style page_context_v2 artifacts.")
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--expected-records", type=int, default=None)
    p.add_argument("--require-quality-pass", action="store_true", help="Exit nonzero if adapter quality_status is not PASS.")
    args = p.parse_args(argv)

    manifest = build_adapter(Path(args.input_path), Path(args.output_dir), min_records=args.min_records, expected_records=args.expected_records)
    print(f"Status: {manifest['status']}")
    print(f"Quality status: {manifest['quality_status']}")
    print("Summary: " + json.dumps(manifest["summary"], sort_keys=True))
    manifest_path = Path(args.output_dir) / MANIFEST_JSON
    print(f"Wrote: {manifest_path}")
    for key, path in manifest["artifacts"].items():
        print(f"Wrote: {path}")
    if args.require_quality_pass and manifest["quality_status"] != "PASS":
        return 1
    return 0


def quality_cli_main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net page_context_v2 Gemma adapter artifacts.")
    p.add_argument("--manifest", "--report", dest="manifest_path", required=True)
    p.add_argument("--output", default=None)
    p.add_argument("--write-json", action="store_true")
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--expected-records", type=int, default=None)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-old-v2-graph-contract", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--require-no-source-truth-mutation", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=None)
    args = p.parse_args(argv)

    output_path: Optional[Path] = Path(args.output) if args.output else None
    if args.write_json and output_path is None:
        output_path = Path(args.manifest_path).parent / QUALITY_JSON

    result = check_quality(
        Path(args.manifest_path),
        output_path=output_path,
        min_records=args.min_records,
        expected_records=args.expected_records,
        require_quality_pass=args.require_quality_pass,
        require_old_v2_graph_contract=args.require_old_v2_graph_contract,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        max_unsafe=args.max_unsafe,
    )
    print(f"Quality status: {result['quality_status']}")
    print("Summary: " + json.dumps(result["summary"], sort_keys=True))
    if result["failure_reasons"]:
        print("Failure reasons: " + json.dumps(result["failure_reasons"], sort_keys=True))
    if output_path:
        print(f"Wrote: {output_path}")
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(build_cli_main())
