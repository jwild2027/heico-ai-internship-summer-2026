"""Quality gate for TRACE-Net RAG eligibility artifacts."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_rag_eligibility import (
    DEFAULT_OUTPUT_DIR,
    ALL_RECORDS_FILE,
    SOURCE_FILE,
    VERIFIED_PART_FILE,
    DERIVED_FILE,
    EXCLUDED_FILE,
    SUMMARY_FILE,
    GRAPH_NODES_FILE,
    GRAPH_EDGES_FILE,
    QUALITY_FILE,
)

DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / SUMMARY_FILE
DEFAULT_ALL = DEFAULT_OUTPUT_DIR / ALL_RECORDS_FILE
DEFAULT_SOURCE = DEFAULT_OUTPUT_DIR / SOURCE_FILE
DEFAULT_VERIFIED = DEFAULT_OUTPUT_DIR / VERIFIED_PART_FILE
DEFAULT_DERIVED = DEFAULT_OUTPUT_DIR / DERIVED_FILE
DEFAULT_EXCLUDED = DEFAULT_OUTPUT_DIR / EXCLUDED_FILE
DEFAULT_NODES = DEFAULT_OUTPUT_DIR / GRAPH_NODES_FILE
DEFAULT_EDGES = DEFAULT_OUTPUT_DIR / GRAPH_EDGES_FILE
DEFAULT_QUALITY = DEFAULT_OUTPUT_DIR / QUALITY_FILE


@dataclass(frozen=True)
class RagEligibilityQualityPaths:
    summary: Path = DEFAULT_SUMMARY
    all_records: Path = DEFAULT_ALL
    source_evidence: Path = DEFAULT_SOURCE
    verified_part_evidence: Path = DEFAULT_VERIFIED
    derived_context: Path = DEFAULT_DERIVED
    excluded_records: Path = DEFAULT_EXCLUDED
    graph_nodes: Path = DEFAULT_NODES
    graph_edges: Path = DEFAULT_EDGES
    quality: Path = DEFAULT_QUALITY


@dataclass
class RagEligibilityQualityOptions:
    min_records: int = 1
    min_pages: int = 1
    min_source_evidence_records: int | None = None
    min_verified_part_records: int | None = None
    min_derived_context_records: int | None = None
    max_unsafe_rag_eligible_records: int = 0
    max_table_candidate_eligible_records: int = 0
    max_table_tiles_eligible_records: int = 0
    min_graph_nodes: int | None = None
    min_graph_edges: int | None = None
    write_json: bool = False


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                if isinstance(json.loads(line), dict):
                    count += 1
            except Exception:
                continue
    return count


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_rag_eligibility_quality(paths: RagEligibilityQualityPaths, options: RagEligibilityQualityOptions | None = None) -> dict[str, Any]:
    options = options or RagEligibilityQualityOptions()
    summary = _read_json(paths.summary, {}) or {}
    all_count = _read_jsonl_count(paths.all_records)
    source_count = _read_jsonl_count(paths.source_evidence)
    verified_count = _read_jsonl_count(paths.verified_part_evidence)
    derived_count = _read_jsonl_count(paths.derived_context)
    excluded_count = _read_jsonl_count(paths.excluded_records)
    nodes_count = len(_read_json(paths.graph_nodes, []) or [])
    edges_count = len(_read_json(paths.graph_edges, []) or [])
    all_records = _read_jsonl(paths.all_records)
    table_candidate_eligible = len([r for r in all_records if r.get("evidence_layer") == "table_candidate" and r.get("rag_eligible") is True])
    table_tiles_eligible = len([r for r in all_records if r.get("evidence_layer") == "table_tiles" and r.get("rag_eligible") is True])
    unsafe_scan = len([r for r in all_records if r.get("unsafe_rag_eligible") is True])

    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.summary.exists() and paths.all_records.exists(), f"summary={paths.summary.exists()}; all_records={paths.all_records.exists()}"))
    checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')!r}"))
    checks.append(_check("records", int(summary.get("records") or 0) >= options.min_records and all_count >= options.min_records, f"records summary={summary.get('records')}; jsonl={all_count}; minimum={options.min_records}"))
    checks.append(_check("pages", int(summary.get("pages") or 0) >= options.min_pages, f"pages={summary.get('pages')}; minimum={options.min_pages}"))
    checks.append(_check("source_pool_count_match", source_count == int(summary.get("source_evidence_records") or -1), f"source jsonl={source_count}; summary={summary.get('source_evidence_records')}"))
    checks.append(_check("verified_part_pool_count_match", verified_count == int(summary.get("verified_part_evidence_records") or -1), f"verified jsonl={verified_count}; summary={summary.get('verified_part_evidence_records')}"))
    checks.append(_check("derived_pool_count_match", derived_count == int(summary.get("derived_context_records") or -1), f"derived jsonl={derived_count}; summary={summary.get('derived_context_records')}"))
    checks.append(_check("excluded_pool_count_match", excluded_count == int(summary.get("rag_excluded_records") or -1), f"excluded jsonl={excluded_count}; summary={summary.get('rag_excluded_records')}"))
    checks.append(_check("unsafe_rag_eligible", int(summary.get("unsafe_rag_eligible_records") or 0) <= options.max_unsafe_rag_eligible_records and unsafe_scan <= options.max_unsafe_rag_eligible_records, f"unsafe summary={summary.get('unsafe_rag_eligible_records')}; scan={unsafe_scan}; max={options.max_unsafe_rag_eligible_records}"))
    checks.append(_check("no_table_candidate_eligible", table_candidate_eligible <= options.max_table_candidate_eligible_records, f"table_candidate_eligible={table_candidate_eligible}; max={options.max_table_candidate_eligible_records}"))
    checks.append(_check("no_table_tiles_eligible", table_tiles_eligible <= options.max_table_tiles_eligible_records, f"table_tiles_eligible={table_tiles_eligible}; max={options.max_table_tiles_eligible_records}"))
    if options.min_source_evidence_records is not None:
        checks.append(_check("source_evidence_records", source_count >= options.min_source_evidence_records, f"source_evidence_records={source_count}; minimum={options.min_source_evidence_records}"))
    if options.min_verified_part_records is not None:
        checks.append(_check("verified_part_records", verified_count >= options.min_verified_part_records, f"verified_part_records={verified_count}; minimum={options.min_verified_part_records}"))
    if options.min_derived_context_records is not None:
        checks.append(_check("derived_context_records", derived_count >= options.min_derived_context_records, f"derived_context_records={derived_count}; minimum={options.min_derived_context_records}"))
    if options.min_graph_nodes is not None:
        checks.append(_check("graph_nodes", nodes_count >= options.min_graph_nodes, f"graph_nodes={nodes_count}; minimum={options.min_graph_nodes}"))
    else:
        checks.append(_check("graph_nodes", nodes_count > 0, f"graph_nodes={nodes_count}"))
    if options.min_graph_edges is not None:
        checks.append(_check("graph_edges", edges_count >= options.min_graph_edges, f"graph_edges={edges_count}; minimum={options.min_graph_edges}"))
    else:
        checks.append(_check("graph_edges", edges_count > 0, f"graph_edges={edges_count}"))

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    result = {
        "status": status,
        "rag_eligibility_summary_present": paths.summary.exists(),
        "rag_eligibility_records_present": paths.all_records.exists(),
        "rag_eligibility_status": summary.get("status"),
        "rag_eligibility_version": summary.get("version"),
        "rag_eligibility_records": summary.get("records"),
        "rag_eligibility_jsonl_records": all_count,
        "rag_eligibility_pages": summary.get("pages"),
        "rag_eligible_records": summary.get("rag_eligible_records"),
        "rag_excluded_records": summary.get("rag_excluded_records"),
        "source_evidence_records": source_count,
        "verified_part_evidence_records": verified_count,
        "derived_context_records": derived_count,
        "excluded_records": excluded_count,
        "unsafe_rag_eligible_records": summary.get("unsafe_rag_eligible_records"),
        "unsafe_rag_eligible_record_scan": unsafe_scan,
        "table_candidate_eligible_records": table_candidate_eligible,
        "table_tiles_eligible_records": table_tiles_eligible,
        "rag_bucket_counts": summary.get("rag_bucket_counts"),
        "rag_action_counts": summary.get("rag_action_counts"),
        "trust_tier_counts": summary.get("trust_tier_counts"),
        "evidence_layer_counts": summary.get("evidence_layer_counts"),
        "graph_nodes": nodes_count,
        "graph_edges": edges_count,
        "summary_path": str(paths.summary),
        "records_path": str(paths.all_records),
        "checks": checks,
    }
    if options.write_json:
        paths.quality.parent.mkdir(parents=True, exist_ok=True)
        paths.quality.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net RAG eligibility artifacts.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--all-records", type=Path, default=DEFAULT_ALL)
    parser.add_argument("--source-evidence", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--verified-part-evidence", type=Path, default=DEFAULT_VERIFIED)
    parser.add_argument("--derived-context", type=Path, default=DEFAULT_DERIVED)
    parser.add_argument("--excluded-records", type=Path, default=DEFAULT_EXCLUDED)
    parser.add_argument("--graph-nodes", type=Path, default=DEFAULT_NODES)
    parser.add_argument("--graph-edges", type=Path, default=DEFAULT_EDGES)
    parser.add_argument("--quality", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-source-evidence-records", type=int, default=None)
    parser.add_argument("--min-verified-part-records", type=int, default=None)
    parser.add_argument("--min-derived-context-records", type=int, default=None)
    parser.add_argument("--max-unsafe-rag-eligible-records", type=int, default=0)
    parser.add_argument("--max-table-candidate-eligible-records", type=int, default=0)
    parser.add_argument("--max-table-tiles-eligible-records", type=int, default=0)
    parser.add_argument("--min-graph-nodes", type=int, default=None)
    parser.add_argument("--min-graph-edges", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    result = run_rag_eligibility_quality(
        RagEligibilityQualityPaths(
            summary=args.summary,
            all_records=args.all_records,
            source_evidence=args.source_evidence,
            verified_part_evidence=args.verified_part_evidence,
            derived_context=args.derived_context,
            excluded_records=args.excluded_records,
            graph_nodes=args.graph_nodes,
            graph_edges=args.graph_edges,
            quality=args.quality,
        ),
        RagEligibilityQualityOptions(
            min_records=args.min_records,
            min_pages=args.min_pages,
            min_source_evidence_records=args.min_source_evidence_records,
            min_verified_part_records=args.min_verified_part_records,
            min_derived_context_records=args.min_derived_context_records,
            max_unsafe_rag_eligible_records=args.max_unsafe_rag_eligible_records,
            max_table_candidate_eligible_records=args.max_table_candidate_eligible_records,
            max_table_tiles_eligible_records=args.max_table_tiles_eligible_records,
            min_graph_nodes=args.min_graph_nodes,
            min_graph_edges=args.min_graph_edges,
            write_json=args.write_json,
        ),
    )
    print("TRACE-Net RAG eligibility quality gate")
    print(f"  Status: {result['status']}")
    print("  Summary:")
    for key in (
        "rag_eligibility_records", "rag_eligibility_pages", "rag_eligible_records", "rag_excluded_records",
        "source_evidence_records", "verified_part_evidence_records", "derived_context_records",
        "unsafe_rag_eligible_records", "table_candidate_eligible_records", "table_tiles_eligible_records",
        "graph_nodes", "graph_edges",
    ):
        print(f"    {key}: {result.get(key)}")
    print("  Checks:")
    for check in result["checks"]:
        print(f"    {'OK' if check['ok'] else 'FAIL'} {check['name']}: {check['detail']}")
    if args.write_json:
        print(f"\nJSON: {args.quality}")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
