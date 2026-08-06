"""Quality gate for TRACE-Net RAG candidate index artifacts."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_rag_candidate_index import (
    DEFAULT_OUTPUT_DIR,
    ALL_CANDIDATES_FILE,
    SOURCE_CANDIDATES_FILE,
    SOURCE_TEXT_CANDIDATES_FILE,
    VERIFIED_PART_CANDIDATES_FILE,
    DERIVED_CANDIDATES_FILE,
    SUMMARY_FILE,
    GRAPH_NODES_FILE,
    GRAPH_EDGES_FILE,
    QUALITY_FILE,
)

DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / SUMMARY_FILE
DEFAULT_ALL = DEFAULT_OUTPUT_DIR / ALL_CANDIDATES_FILE
DEFAULT_SOURCE = DEFAULT_OUTPUT_DIR / SOURCE_CANDIDATES_FILE
DEFAULT_SOURCE_TEXT = DEFAULT_OUTPUT_DIR / SOURCE_TEXT_CANDIDATES_FILE
DEFAULT_VERIFIED = DEFAULT_OUTPUT_DIR / VERIFIED_PART_CANDIDATES_FILE
DEFAULT_DERIVED = DEFAULT_OUTPUT_DIR / DERIVED_CANDIDATES_FILE
DEFAULT_NODES = DEFAULT_OUTPUT_DIR / GRAPH_NODES_FILE
DEFAULT_EDGES = DEFAULT_OUTPUT_DIR / GRAPH_EDGES_FILE
DEFAULT_QUALITY = DEFAULT_OUTPUT_DIR / QUALITY_FILE


@dataclass(frozen=True)
class RagCandidateIndexQualityPaths:
    summary: Path = DEFAULT_SUMMARY
    all_candidates: Path = DEFAULT_ALL
    source_candidates: Path = DEFAULT_SOURCE
    source_text_candidates: Path = DEFAULT_SOURCE_TEXT
    verified_part_candidates: Path = DEFAULT_VERIFIED
    derived_candidates: Path = DEFAULT_DERIVED
    graph_nodes: Path = DEFAULT_NODES
    graph_edges: Path = DEFAULT_EDGES
    quality: Path = DEFAULT_QUALITY


@dataclass
class RagCandidateIndexQualityOptions:
    min_records: int = 1
    min_pages: int = 1
    min_source_candidates: int | None = None
    min_source_text_candidates: int | None = None
    min_source_text_ocr_joined_records: int | None = None
    min_verified_part_candidates: int | None = None
    min_derived_candidates: int | None = None
    min_derived_joined_records: int | None = None
    max_derived_unjoined_records: int | None = None
    max_unsafe_candidate_records: int = 0
    max_empty_text_records: int = 0
    max_table_candidate_indexed_records: int = 0
    max_table_tiles_indexed_records: int = 0
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, Mapping):
                rows.append(dict(row))
    return rows


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_rag_candidate_index_quality(paths: RagCandidateIndexQualityPaths, options: RagCandidateIndexQualityOptions | None = None) -> dict[str, Any]:
    options = options or RagCandidateIndexQualityOptions()
    summary = _read_json(paths.summary, {}) or {}
    all_rows = _read_jsonl(paths.all_candidates)
    source_rows = _read_jsonl(paths.source_candidates)
    source_text_rows = _read_jsonl(paths.source_text_candidates)
    verified_rows = _read_jsonl(paths.verified_part_candidates)
    derived_rows = _read_jsonl(paths.derived_candidates)
    nodes_count = len(_read_json(paths.graph_nodes, []) or [])
    edges_count = len(_read_json(paths.graph_edges, []) or [])
    unsafe_scan = len([r for r in all_rows if r.get("rag_bucket") not in {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"} or r.get("evidence_layer") in {"table_candidate", "table_tiles"} or not str(r.get("text") or "").strip() or r.get("final_trust_tier") == "D"])
    table_candidate_indexed = len([r for r in all_rows if r.get("evidence_layer") == "table_candidate"])
    table_tiles_indexed = len([r for r in all_rows if r.get("evidence_layer") == "table_tiles"])
    empty_text = len([r for r in all_rows if not str(r.get("text") or "").strip()])
    source_text_ocr_joined_scan = len([r for r in source_text_rows if isinstance(r.get("metadata"), Mapping) and r.get("metadata", {}).get("source_text_ocr_joined")])
    derived_joined_scan = len([r for r in derived_rows if isinstance(r.get("metadata"), Mapping) and r.get("metadata", {}).get("refined_tile_joined")])
    derived_unjoined_scan = len([r for r in derived_rows if not (isinstance(r.get("metadata"), Mapping) and r.get("metadata", {}).get("refined_tile_joined"))])

    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.summary.exists() and paths.all_candidates.exists(), f"summary={paths.summary.exists()}; all_candidates={paths.all_candidates.exists()}"))
    checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')!r}"))
    checks.append(_check("records", int(summary.get("records") or 0) >= options.min_records and len(all_rows) >= options.min_records, f"records summary={summary.get('records')}; jsonl={len(all_rows)}; minimum={options.min_records}"))
    checks.append(_check("pages", int(summary.get("pages") or 0) >= options.min_pages, f"pages={summary.get('pages')}; minimum={options.min_pages}"))
    checks.append(_check("source_count_match", len(source_rows) == int(summary.get("source_candidate_records", -1)), f"source jsonl={len(source_rows)}; summary={summary.get('source_candidate_records')}"))
    checks.append(_check("source_text_count_match", len(source_text_rows) == int(summary.get("source_text_candidate_records", -1)), f"source_text jsonl={len(source_text_rows)}; summary={summary.get('source_text_candidate_records')}"))
    checks.append(_check("verified_count_match", len(verified_rows) == int(summary.get("verified_part_candidate_records", -1)), f"verified jsonl={len(verified_rows)}; summary={summary.get('verified_part_candidate_records')}"))
    checks.append(_check("derived_count_match", len(derived_rows) == int(summary.get("derived_context_candidate_records", -1)), f"derived jsonl={len(derived_rows)}; summary={summary.get('derived_context_candidate_records')}"))
    checks.append(_check("unsafe_candidates", int(summary.get("unsafe_candidate_records") or 0) <= options.max_unsafe_candidate_records and unsafe_scan <= options.max_unsafe_candidate_records, f"unsafe summary={summary.get('unsafe_candidate_records')}; scan={unsafe_scan}; max={options.max_unsafe_candidate_records}"))
    checks.append(_check("empty_text", empty_text <= options.max_empty_text_records and int(summary.get("empty_text_records") or 0) <= options.max_empty_text_records, f"empty_text summary={summary.get('empty_text_records')}; scan={empty_text}; max={options.max_empty_text_records}"))
    checks.append(_check("no_table_candidate_indexed", table_candidate_indexed <= options.max_table_candidate_indexed_records, f"table_candidate_indexed={table_candidate_indexed}; max={options.max_table_candidate_indexed_records}"))
    checks.append(_check("no_table_tiles_indexed", table_tiles_indexed <= options.max_table_tiles_indexed_records, f"table_tiles_indexed={table_tiles_indexed}; max={options.max_table_tiles_indexed_records}"))
    if options.min_source_candidates is not None:
        checks.append(_check("source_candidates", len(source_rows) >= options.min_source_candidates, f"source_candidates={len(source_rows)}; minimum={options.min_source_candidates}"))
    if options.min_source_text_candidates is not None:
        checks.append(_check("source_text_candidates", len(source_text_rows) >= options.min_source_text_candidates, f"source_text_candidates={len(source_text_rows)}; minimum={options.min_source_text_candidates}"))
    if options.min_source_text_ocr_joined_records is not None:
        checks.append(_check("source_text_ocr_joined", source_text_ocr_joined_scan >= options.min_source_text_ocr_joined_records and int(summary.get("source_text_ocr_joined_records") or 0) >= options.min_source_text_ocr_joined_records, f"source_text_ocr_joined summary={summary.get('source_text_ocr_joined_records')}; scan={source_text_ocr_joined_scan}; minimum={options.min_source_text_ocr_joined_records}"))
    if options.min_verified_part_candidates is not None:
        checks.append(_check("verified_part_candidates", len(verified_rows) >= options.min_verified_part_candidates, f"verified_part_candidates={len(verified_rows)}; minimum={options.min_verified_part_candidates}"))
    if options.min_derived_candidates is not None:
        checks.append(_check("derived_candidates", len(derived_rows) >= options.min_derived_candidates, f"derived_candidates={len(derived_rows)}; minimum={options.min_derived_candidates}"))
    if options.min_derived_joined_records is not None:
        checks.append(_check("derived_joined_records", derived_joined_scan >= options.min_derived_joined_records and int(summary.get("derived_context_joined_records") or 0) >= options.min_derived_joined_records, f"derived_joined summary={summary.get('derived_context_joined_records')}; scan={derived_joined_scan}; minimum={options.min_derived_joined_records}"))
    if options.max_derived_unjoined_records is not None:
        checks.append(_check("derived_unjoined_records", derived_unjoined_scan <= options.max_derived_unjoined_records and int(summary.get("derived_context_unjoined_records") or 0) <= options.max_derived_unjoined_records, f"derived_unjoined summary={summary.get('derived_context_unjoined_records')}; scan={derived_unjoined_scan}; max={options.max_derived_unjoined_records}"))
    if options.min_graph_nodes is not None:
        checks.append(_check("graph_nodes", nodes_count >= options.min_graph_nodes, f"graph_nodes={nodes_count}; minimum={options.min_graph_nodes}"))
    else:
        checks.append(_check("graph_nodes", nodes_count > 0, f"graph_nodes={nodes_count}"))
    if options.min_graph_edges is not None:
        checks.append(_check("graph_edges", edges_count >= options.min_graph_edges, f"graph_edges={edges_count}; minimum={options.min_graph_edges}"))
    else:
        checks.append(_check("graph_edges", edges_count > 0, f"graph_edges={edges_count}"))

    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    result = {
        "status": status,
        "rag_candidate_summary_present": paths.summary.exists(),
        "rag_candidate_records_present": paths.all_candidates.exists(),
        "rag_candidate_status": summary.get("status"),
        "rag_candidate_version": summary.get("version"),
        "rag_candidate_records": summary.get("records"),
        "rag_candidate_jsonl_records": len(all_rows),
        "rag_candidate_pages": summary.get("pages"),
        "source_candidate_records": len(source_rows),
        "source_text_candidate_records": len(source_text_rows),
        "source_text_ocr_joined_records": summary.get("source_text_ocr_joined_records"),
        "source_text_ocr_joined_scan": source_text_ocr_joined_scan,
        "verified_part_candidate_records": len(verified_rows),
        "derived_context_candidate_records": len(derived_rows),
        "derived_context_joined_records": summary.get("derived_context_joined_records"),
        "derived_context_joined_scan": derived_joined_scan,
        "derived_context_unjoined_records": summary.get("derived_context_unjoined_records"),
        "derived_context_unjoined_scan": derived_unjoined_scan,
        "derived_context_catalog_supported_records": summary.get("derived_context_catalog_supported_records"),
        "unsafe_candidate_records": summary.get("unsafe_candidate_records"),
        "unsafe_candidate_scan": unsafe_scan,
        "empty_text_records": summary.get("empty_text_records"),
        "empty_text_scan": empty_text,
        "table_candidate_indexed_records": table_candidate_indexed,
        "table_tiles_indexed_records": table_tiles_indexed,
        "rag_bucket_counts": summary.get("rag_bucket_counts"),
        "evidence_layer_counts": summary.get("evidence_layer_counts"),
        "trust_tier_counts": summary.get("trust_tier_counts"),
        "candidate_type_counts": summary.get("candidate_type_counts"),
        "graph_nodes": nodes_count,
        "graph_edges": edges_count,
        "summary_path": str(paths.summary),
        "records_path": str(paths.all_candidates),
        "checks": checks,
    }
    if options.write_json:
        paths.quality.parent.mkdir(parents=True, exist_ok=True)
        paths.quality.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net RAG candidate index artifacts.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--all-candidates", type=Path, default=DEFAULT_ALL)
    parser.add_argument("--source-candidates", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-text-candidates", type=Path, default=DEFAULT_SOURCE_TEXT)
    parser.add_argument("--verified-part-candidates", type=Path, default=DEFAULT_VERIFIED)
    parser.add_argument("--derived-candidates", type=Path, default=DEFAULT_DERIVED)
    parser.add_argument("--graph-nodes", type=Path, default=DEFAULT_NODES)
    parser.add_argument("--graph-edges", type=Path, default=DEFAULT_EDGES)
    parser.add_argument("--quality", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-source-candidates", type=int, default=None)
    parser.add_argument("--min-source-text-candidates", type=int, default=None)
    parser.add_argument("--min-source-text-ocr-joined-records", type=int, default=None)
    parser.add_argument("--min-verified-part-candidates", type=int, default=None)
    parser.add_argument("--min-derived-candidates", type=int, default=None)
    parser.add_argument("--min-derived-joined-records", type=int, default=None)
    parser.add_argument("--max-derived-unjoined-records", type=int, default=None)
    parser.add_argument("--max-unsafe-candidate-records", type=int, default=0)
    parser.add_argument("--max-empty-text-records", type=int, default=0)
    parser.add_argument("--max-table-candidate-indexed-records", type=int, default=0)
    parser.add_argument("--max-table-tiles-indexed-records", type=int, default=0)
    parser.add_argument("--min-graph-nodes", type=int, default=None)
    parser.add_argument("--min-graph-edges", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    result = run_rag_candidate_index_quality(
        RagCandidateIndexQualityPaths(
            summary=args.summary,
            all_candidates=args.all_candidates,
            source_candidates=args.source_candidates,
            source_text_candidates=args.source_text_candidates,
            verified_part_candidates=args.verified_part_candidates,
            derived_candidates=args.derived_candidates,
            graph_nodes=args.graph_nodes,
            graph_edges=args.graph_edges,
            quality=args.quality,
        ),
        RagCandidateIndexQualityOptions(
            min_records=args.min_records,
            min_pages=args.min_pages,
            min_source_candidates=args.min_source_candidates,
            min_source_text_candidates=args.min_source_text_candidates,
            min_source_text_ocr_joined_records=args.min_source_text_ocr_joined_records,
            min_verified_part_candidates=args.min_verified_part_candidates,
            min_derived_candidates=args.min_derived_candidates,
            min_derived_joined_records=args.min_derived_joined_records,
            max_derived_unjoined_records=args.max_derived_unjoined_records,
            max_unsafe_candidate_records=args.max_unsafe_candidate_records,
            max_empty_text_records=args.max_empty_text_records,
            max_table_candidate_indexed_records=args.max_table_candidate_indexed_records,
            max_table_tiles_indexed_records=args.max_table_tiles_indexed_records,
            min_graph_nodes=args.min_graph_nodes,
            min_graph_edges=args.min_graph_edges,
            write_json=args.write_json,
        ),
    )
    print("TRACE-Net RAG candidate index quality gate")
    print(f"  Status: {result['status']}")
    print("  Summary:")
    for key in (
        "rag_candidate_records", "rag_candidate_pages", "source_candidate_records", "source_text_candidate_records", "source_text_ocr_joined_records", "verified_part_candidate_records",
        "derived_context_candidate_records", "derived_context_joined_records", "derived_context_unjoined_records", "unsafe_candidate_records", "empty_text_records", "table_candidate_indexed_records",
        "table_tiles_indexed_records", "graph_nodes", "graph_edges",
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
