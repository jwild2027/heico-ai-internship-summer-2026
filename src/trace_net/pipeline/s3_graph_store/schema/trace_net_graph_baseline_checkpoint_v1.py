"""TRACE-Net graph/baseline checkpoint freezer v1.

This module is intentionally read-only. It snapshots the current TRACE-Net
Postgres graph plus the local graph-explorer artifacts into JSON files so the
next retrieval stages can compare against a known-good baseline.

The checkpoint is designed for the current TRACE-Net sequence:
1. graph UI has page/part/nomenclature/context-v2 overlays,
2. freeze baseline,
3. turn context-v2 into safe retrieval helper records,
4. build embeddings / vector / hybrid retrieval behind flags.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA_VERSION = "trace_net_graph_baseline_checkpoint_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1")
DEFAULT_GRAPH_EXPLORER_DIR = Path("local_data/organization/trace_net/graph_explorer")
DEFAULT_CHECKPOINT_FILE = "trace_net_graph_baseline_checkpoint_v1.json"
DEFAULT_SUMMARY_FILE = "trace_net_graph_baseline_checkpoint_v1_summary.json"
DEFAULT_MANIFEST_FILE = "trace_net_graph_baseline_checkpoint_v1_manifest.json"
DEFAULT_QUALITY_FILE = "trace_net_graph_baseline_checkpoint_v1_quality.json"

CORE_TABLES = (
    "pages",
    "graph_nodes",
    "graph_edges",
    "page_context_v2_records",
)

RETRIEVAL_SAFETY_TABLES = (
    "rag_candidate_chunks",
    "source_citations",
    "rag_eligibility_records",
    "evidence_consensus_records",
    "trust_authority_records",
    "trust_tier_overlay_records",
    "page_trust_traits",
    "feedback_events",
    "feedback_policy_signals",
)

GRAPH_EXPLORER_ARTIFACTS = (
    "trace_net_graph_explorer.html",
    "trace_net_graph_explorer_data.json",
    "trace_net_graph_explorer_summary.json",
    "trace_net_graph_explorer_nodes.json",
    "trace_net_graph_explorer_edges.json",
    "trace_net_graph_explorer_v2_nomenclature_quality.json",
)

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PAGE_NUMBER_RE = re.compile(r"(\d+)(?!.*\d)")


class CheckpointError(RuntimeError):
    """Raised when a checkpoint or quality gate cannot be produced safely."""


@dataclass(frozen=True)
class QualityResult:
    status: str
    checks: list[dict[str, Any]]
    summary: dict[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_page_range(raw: str | None) -> list[int]:
    """Parse a page range string such as "1-50, 75, 80-82"."""
    if raw is None or not str(raw).strip():
        return []
    pages: list[int] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start = int(left.strip())
            end = int(right.strip())
            if start <= 0 or end <= 0:
                raise ValueError("page numbers must be positive")
            if end < start:
                raise ValueError(f"invalid page range: {token}")
            pages.extend(range(start, end + 1))
        else:
            value = int(token)
            if value <= 0:
                raise ValueError("page numbers must be positive")
            pages.append(value)
    # preserve order while removing duplicates
    seen: set[int] = set()
    unique: list[int] = []
    for page in pages:
        if page not in seen:
            unique.append(page)
            seen.add(page)
    return unique


def extract_page_number(page_id: Any) -> int | None:
    """Extract a canonical page number from ids like t_p_120_1176_p000001."""
    if page_id is None:
        return None
    text = str(page_id)
    match = PAGE_NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def expected_page_id_aliases(page_number: int) -> set[str]:
    return {
        f"t_p_120_1176_p{page_number:06d}",
        f"zip_page_{page_number:06d}",
        f"page_{page_number:06d}",
        f"p{page_number:06d}",
        str(page_number),
    }


def required_page_coverage(
    required_pages: Sequence[int],
    page_ids: Iterable[Any],
    context_page_ids: Iterable[Any],
) -> dict[str, Any]:
    """Return coverage info for required pages against context-v2 page ids."""
    page_id_text = {str(value) for value in page_ids if value is not None}
    context_id_text = {str(value) for value in context_page_ids if value is not None}

    ids_by_number: dict[int, set[str]] = {}
    for value in page_id_text | context_id_text:
        number = extract_page_number(value)
        if number is not None:
            ids_by_number.setdefault(number, set()).add(value)

    covered: list[int] = []
    missing: list[int] = []
    details: dict[str, dict[str, Any]] = {}

    for page_number in required_pages:
        aliases = ids_by_number.get(page_number, set()) | expected_page_id_aliases(page_number)
        matched_context_ids = sorted(alias for alias in aliases if alias in context_id_text)
        is_covered = bool(matched_context_ids)
        if is_covered:
            covered.append(page_number)
        else:
            missing.append(page_number)
        details[str(page_number)] = {
            "covered": is_covered,
            "matched_context_ids": matched_context_ids,
            "known_page_ids": sorted(alias for alias in aliases if alias in page_id_text),
        }

    return {
        "required_page_numbers": list(required_pages),
        "required_page_count": len(required_pages),
        "covered_page_numbers": covered,
        "covered_page_count": len(covered),
        "missing_page_numbers": missing,
        "missing_page_count": len(missing),
        "details": details,
    }


def validate_identifier(identifier: str) -> str:
    if not IDENT_RE.match(identifier):
        raise CheckpointError(f"unsafe SQL identifier: {identifier!r}")
    return identifier


def quote_ident(identifier: str) -> str:
    validate_identifier(identifier)
    return '"' + identifier.replace('"', '""') + '"'


def mask_database_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    parts = urlsplit(database_url)
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        username = userinfo.split(":", 1)[0]
        netloc = f"{username}:***@{hostinfo}"
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in {"password", "pass", "secret", "token"}:
            value = "***"
        query_items.append((key, value))
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query_items), parts.fragment))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(encoded)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_checkpoint_for_hash(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    canonical = copy.deepcopy(dict(checkpoint))
    canonical.pop("generated_at_utc", None)
    canonical.pop("checkpoint_sha256", None)
    return canonical


def get_psycopg() -> Any:
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised by local runtime only
        raise CheckpointError(
            "psycopg is required for Postgres checkpointing. Install with: "
            "python -m pip install 'psycopg[binary]'"
        ) from exc
    return psycopg


def table_exists(conn: Any, table_name: str) -> bool:
    validate_identifier(table_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            select exists(
              select 1
              from information_schema.tables
              where table_schema = current_schema()
                and table_name = %s
            )
            """,
            (table_name,),
        )
        row = cur.fetchone()
        return bool(row and row[0])


def table_columns(conn: Any, table_name: str) -> list[str]:
    validate_identifier(table_name)
    if not table_exists(conn, table_name):
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = current_schema()
              and table_name = %s
            order by ordinal_position
            """,
            (table_name,),
        )
        return [str(row[0]) for row in cur.fetchall()]


def scalar(conn: Any, sql: str, params: Sequence[Any] | None = None) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None


def table_count(conn: Any, table_name: str) -> int | None:
    if not table_exists(conn, table_name):
        return None
    return int(scalar(conn, f"select count(*) from {quote_ident(table_name)}") or 0)


def grouped_counts(conn: Any, table_name: str, column_name: str) -> dict[str, int]:
    if not table_exists(conn, table_name):
        return {}
    columns = table_columns(conn, table_name)
    if column_name not in columns:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select {quote_ident(column_name)}, count(*)
            from {quote_ident(table_name)}
            group by {quote_ident(column_name)}
            order by count(*) desc, {quote_ident(column_name)} asc
            """
        )
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def distinct_column_values(conn: Any, table_name: str, column_name: str) -> list[str]:
    if not table_exists(conn, table_name):
        return []
    columns = table_columns(conn, table_name)
    if column_name not in columns:
        return []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select distinct {quote_ident(column_name)}
            from {quote_ident(table_name)}
            where {quote_ident(column_name)} is not null
            order by {quote_ident(column_name)} asc
            """
        )
        return [str(row[0]) for row in cur.fetchall()]


def get_table_presence(conn: Any, table_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for table_name in table_names:
        exists = table_exists(conn, table_name)
        result[table_name] = {
            "exists": exists,
            "row_count": table_count(conn, table_name) if exists else None,
            "columns": table_columns(conn, table_name) if exists else [],
        }
    return result


def get_graph_baseline(conn: Any, required_pages: Sequence[int]) -> dict[str, Any]:
    node_type_counts = grouped_counts(conn, "graph_nodes", "node_type")
    edge_type_counts = grouped_counts(conn, "graph_edges", "edge_type")
    page_ids = distinct_column_values(conn, "pages", "page_id")
    context_page_ids = distinct_column_values(conn, "page_context_v2_records", "page_id")

    coverage = required_page_coverage(required_pages, page_ids, context_page_ids)

    page_count = table_count(conn, "pages") or 0
    graph_node_count = table_count(conn, "graph_nodes") or 0
    graph_edge_count = table_count(conn, "graph_edges") or 0
    page_context_v2_records = table_count(conn, "page_context_v2_records") or 0

    return {
        "page_count": page_count,
        "graph_node_count": graph_node_count,
        "graph_edge_count": graph_edge_count,
        "node_type_counts": node_type_counts,
        "edge_type_counts": edge_type_counts,
        "page_node_count": node_type_counts.get("page", node_type_counts.get("Page", 0)),
        "part_node_count": node_type_counts.get("part", node_type_counts.get("Part", 0)),
        "nomenclature_node_count": node_type_counts.get(
            "nomenclature",
            node_type_counts.get("Nomenclature", 0),
        ),
        "has_nomenclature_edge_count": edge_type_counts.get("HAS_NOMENCLATURE", 0),
        "has_context_v2_edge_count": edge_type_counts.get("HAS_CONTEXT_V2", 0),
        "page_context_v2_record_count": page_context_v2_records,
        "page_context_v2_page_count": len(set(context_page_ids)),
        "required_context_v2_coverage": coverage,
    }


def get_retrieval_safety_baseline(conn: Any) -> dict[str, Any]:
    tables = get_table_presence(conn, RETRIEVAL_SAFETY_TABLES)
    candidate_count = tables.get("rag_candidate_chunks", {}).get("row_count") or 0
    citation_count = tables.get("source_citations", {}).get("row_count") or 0
    rag_eligibility_count = tables.get("rag_eligibility_records", {}).get("row_count") or 0
    evidence_consensus_count = tables.get("evidence_consensus_records", {}).get("row_count") or 0

    candidate_bucket_counts: dict[str, int] = {}
    candidate_authority_counts: dict[str, int] = {}
    candidate_trust_counts: dict[str, int] = {}
    if table_exists(conn, "rag_candidate_chunks"):
        columns = table_columns(conn, "rag_candidate_chunks")
        for preferred in ("bucket", "candidate_bucket", "evidence_bucket", "record_bucket"):
            if preferred in columns:
                candidate_bucket_counts = grouped_counts(conn, "rag_candidate_chunks", preferred)
                break
        for preferred in ("authority", "trust_authority", "claim_authority", "answer_authority"):
            if preferred in columns:
                candidate_authority_counts = grouped_counts(conn, "rag_candidate_chunks", preferred)
                break
        for preferred in ("trust_tier", "tier", "evidence_tier"):
            if preferred in columns:
                candidate_trust_counts = grouped_counts(conn, "rag_candidate_chunks", preferred)
                break

    notes: list[str] = []
    if candidate_count and citation_count and citation_count < candidate_count:
        notes.append("source citation count is lower than RAG candidate count; later stages should resolve per-candidate citation coverage before answering")
    if not candidate_count:
        notes.append("rag_candidate_chunks table missing or empty; checkpoint still freezes graph/UI baseline but retrieval candidate baseline is not populated")

    return {
        "tables": tables,
        "rag_candidate_count": int(candidate_count),
        "source_citation_count": int(citation_count),
        "rag_eligibility_count": int(rag_eligibility_count),
        "evidence_consensus_count": int(evidence_consensus_count),
        "candidate_bucket_counts": candidate_bucket_counts,
        "candidate_authority_counts": candidate_authority_counts,
        "candidate_trust_tier_counts": candidate_trust_counts,
        "unsafe_embedding_candidate_count": 0,
        "notes": notes,
    }


def get_artifact_baseline(graph_explorer_dir: Path) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for filename in GRAPH_EXPLORER_ARTIFACTS:
        path = graph_explorer_dir / filename
        if path.exists() and path.is_file():
            entry: dict[str, Any] = {
                "exists": True,
                "relative_path": str(path.as_posix()),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            if path.suffix.lower() == ".json":
                try:
                    parsed = load_json(path)
                    if isinstance(parsed, dict):
                        entry["json_keys"] = sorted(parsed.keys())[:100]
                        if "status" in parsed:
                            entry["status"] = parsed.get("status")
                        if "summary" in parsed and isinstance(parsed["summary"], dict):
                            entry["summary_keys"] = sorted(parsed["summary"].keys())[:100]
                    elif isinstance(parsed, list):
                        entry["json_list_count"] = len(parsed)
                except Exception as exc:  # pragma: no cover - defensive local artifact parsing
                    entry["json_parse_error"] = str(exc)
            files[filename] = entry
        else:
            files[filename] = {"exists": False, "relative_path": str(path.as_posix())}

    quality_path = graph_explorer_dir / "trace_net_graph_explorer_v2_nomenclature_quality.json"
    quality: dict[str, Any] | None = None
    if quality_path.exists():
        try:
            parsed = load_json(quality_path)
            if isinstance(parsed, dict):
                quality = parsed
        except Exception as exc:  # pragma: no cover
            quality = {"status": "ERROR", "error": str(exc)}

    return {
        "graph_explorer_dir": str(graph_explorer_dir.as_posix()),
        "files": files,
        "graph_explorer_v2_nomenclature_quality": quality,
    }


def build_checkpoint_payload(
    *,
    database_url: str,
    output_dir: Path,
    graph_explorer_dir: Path,
    checkpoint_name: str,
    required_pages: Sequence[int],
    include_artifacts: bool = True,
) -> dict[str, Any]:
    psycopg = get_psycopg()
    with psycopg.connect(database_url) as conn:
        core_presence = get_table_presence(conn, CORE_TABLES)
        missing_core = [table for table, info in core_presence.items() if not info["exists"]]
        if missing_core:
            raise CheckpointError(f"missing required TRACE-Net core tables: {', '.join(missing_core)}")
        graph_baseline = get_graph_baseline(conn, required_pages)
        retrieval_safety = get_retrieval_safety_baseline(conn)

    artifact_baseline = get_artifact_baseline(graph_explorer_dir) if include_artifacts else {
        "graph_explorer_dir": str(graph_explorer_dir.as_posix()),
        "files": {},
        "graph_explorer_v2_nomenclature_quality": None,
    }

    checkpoint: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_name": checkpoint_name,
        "generated_at_utc": utc_now_iso(),
        "read_only": True,
        "inputs": {
            "database_url_masked": mask_database_url(database_url),
            "output_dir": str(output_dir.as_posix()),
            "graph_explorer_dir": str(graph_explorer_dir.as_posix()),
            "required_first_pages": list(required_pages),
        },
        "core_table_presence": core_presence,
        "graph_baseline": graph_baseline,
        "retrieval_safety_baseline": retrieval_safety,
        "artifact_baseline": artifact_baseline,
        "trace_net_boundary": {
            "page_context_v2_role": "retrieval_helper_only",
            "page_context_v2_can_answer_directly": False,
            "nomenclature_role": "part_metadata_display_and_graph_navigation",
            "source_truth_authority": "postgres_graph_plus_source_citation_plus_trust_authority",
            "vector_indexes_are_authoritative": False,
            "feedback_can_mutate_source_truth": False,
        },
        "next_step": {
            "name": "context_retrieval_helper_records_v1",
            "allowed_use": "turn PageContextV2 into safe routing/helper records; do not answer directly from summaries",
        },
    }
    checkpoint["checkpoint_sha256"] = sha256_json(canonical_checkpoint_for_hash(checkpoint))
    return checkpoint


def checkpoint_summary(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    graph = checkpoint.get("graph_baseline", {})
    coverage = graph.get("required_context_v2_coverage", {}) if isinstance(graph, dict) else {}
    safety = checkpoint.get("retrieval_safety_baseline", {})
    return {
        "schema_version": checkpoint.get("schema_version"),
        "checkpoint_name": checkpoint.get("checkpoint_name"),
        "generated_at_utc": checkpoint.get("generated_at_utc"),
        "checkpoint_sha256": checkpoint.get("checkpoint_sha256"),
        "page_count": graph.get("page_count"),
        "part_node_count": graph.get("part_node_count"),
        "nomenclature_node_count": graph.get("nomenclature_node_count"),
        "has_nomenclature_edge_count": graph.get("has_nomenclature_edge_count"),
        "page_context_v2_page_count": graph.get("page_context_v2_page_count"),
        "has_context_v2_edge_count": graph.get("has_context_v2_edge_count"),
        "required_context_v2_missing_page_count": coverage.get("missing_page_count"),
        "rag_candidate_count": safety.get("rag_candidate_count"),
        "source_citation_count": safety.get("source_citation_count"),
        "unsafe_embedding_candidate_count": safety.get("unsafe_embedding_candidate_count"),
        "read_only": checkpoint.get("read_only"),
    }


def write_checkpoint_files(checkpoint: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    checkpoint_path = output_dir / DEFAULT_CHECKPOINT_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE

    summary = checkpoint_summary(checkpoint)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_name": checkpoint.get("checkpoint_name"),
        "generated_at_utc": checkpoint.get("generated_at_utc"),
        "files": {
            DEFAULT_CHECKPOINT_FILE: {
                "sha256": checkpoint.get("checkpoint_sha256"),
            },
            DEFAULT_SUMMARY_FILE: {
                "sha256": sha256_json(summary),
            },
        },
        "read_only": True,
    }

    write_json(checkpoint_path, checkpoint)
    write_json(summary_path, summary)
    manifest["files"][DEFAULT_CHECKPOINT_FILE]["size_bytes"] = checkpoint_path.stat().st_size
    manifest["files"][DEFAULT_SUMMARY_FILE]["size_bytes"] = summary_path.stat().st_size
    manifest["files"][DEFAULT_MANIFEST_FILE] = {
        "sha256": sha256_json(manifest),
    }
    write_json(manifest_path, manifest)

    return {
        "checkpoint_path": str(checkpoint_path.as_posix()),
        "summary_path": str(summary_path.as_posix()),
        "manifest_path": str(manifest_path.as_posix()),
    }


def build_graph_baseline_checkpoint(
    *,
    database_url: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    graph_explorer_dir: Path = DEFAULT_GRAPH_EXPLORER_DIR,
    checkpoint_name: str = "trace_net_graph_ui_context_v2_nomenclature_baseline_v1",
    require_first_pages: str | None = "1-50",
    include_artifacts: bool = True,
) -> dict[str, Any]:
    required_pages = parse_page_range(require_first_pages)
    checkpoint = build_checkpoint_payload(
        database_url=database_url,
        output_dir=output_dir,
        graph_explorer_dir=graph_explorer_dir,
        checkpoint_name=checkpoint_name,
        required_pages=required_pages,
        include_artifacts=include_artifacts,
    )
    paths = write_checkpoint_files(checkpoint, output_dir)
    return {"checkpoint": checkpoint, "paths": paths, "summary": checkpoint_summary(checkpoint)}


def add_quality_check(checks: list[dict[str, Any]], name: str, passed: bool, actual: Any, expected: Any, detail: str = "") -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "actual": actual,
            "expected": expected,
            "detail": detail,
        }
    )


def evaluate_checkpoint_quality(
    checkpoint: Mapping[str, Any],
    *,
    min_page_count: int = 509,
    min_part_nodes: int = 1,
    min_nomenclature_nodes: int = 1,
    min_has_nomenclature_edges: int = 1,
    min_context_v2_pages: int = 50,
    min_has_context_v2_edges: int = 50,
    require_first_pages: str | None = "1-50",
    min_rag_candidates: int = 0,
    min_source_citations: int = 0,
    max_unsafe_embedding_candidates: int = 0,
    require_graph_explorer_quality_pass: bool = False,
) -> QualityResult:
    graph = checkpoint.get("graph_baseline", {})
    safety = checkpoint.get("retrieval_safety_baseline", {})
    artifact = checkpoint.get("artifact_baseline", {})
    required_pages = parse_page_range(require_first_pages)
    coverage = graph.get("required_context_v2_coverage", {}) if isinstance(graph, Mapping) else {}
    missing_required = coverage.get("missing_page_numbers", []) if isinstance(coverage, Mapping) else []

    checks: list[dict[str, Any]] = []
    add_quality_check(checks, "schema_version", checkpoint.get("schema_version") == SCHEMA_VERSION, checkpoint.get("schema_version"), SCHEMA_VERSION)
    add_quality_check(checks, "read_only", checkpoint.get("read_only") is True, checkpoint.get("read_only"), True)
    add_quality_check(checks, "page_count", int(graph.get("page_count", 0)) >= min_page_count, graph.get("page_count", 0), f">= {min_page_count}")
    add_quality_check(checks, "part_node_count", int(graph.get("part_node_count", 0)) >= min_part_nodes, graph.get("part_node_count", 0), f">= {min_part_nodes}")
    add_quality_check(checks, "nomenclature_node_count", int(graph.get("nomenclature_node_count", 0)) >= min_nomenclature_nodes, graph.get("nomenclature_node_count", 0), f">= {min_nomenclature_nodes}")
    add_quality_check(checks, "has_nomenclature_edge_count", int(graph.get("has_nomenclature_edge_count", 0)) >= min_has_nomenclature_edges, graph.get("has_nomenclature_edge_count", 0), f">= {min_has_nomenclature_edges}")
    add_quality_check(checks, "page_context_v2_page_count", int(graph.get("page_context_v2_page_count", 0)) >= min_context_v2_pages, graph.get("page_context_v2_page_count", 0), f">= {min_context_v2_pages}")
    add_quality_check(checks, "has_context_v2_edge_count", int(graph.get("has_context_v2_edge_count", 0)) >= min_has_context_v2_edges, graph.get("has_context_v2_edge_count", 0), f">= {min_has_context_v2_edges}")

    if required_pages:
        expected_detail = f"all pages in {require_first_pages} have context-v2"
        add_quality_check(checks, "required_context_v2_missing_pages", not missing_required, missing_required, [], expected_detail)

    add_quality_check(checks, "rag_candidate_count", int(safety.get("rag_candidate_count", 0)) >= min_rag_candidates, safety.get("rag_candidate_count", 0), f">= {min_rag_candidates}")
    add_quality_check(checks, "source_citation_count", int(safety.get("source_citation_count", 0)) >= min_source_citations, safety.get("source_citation_count", 0), f">= {min_source_citations}")
    add_quality_check(
        checks,
        "unsafe_embedding_candidate_count",
        int(safety.get("unsafe_embedding_candidate_count", 0)) <= max_unsafe_embedding_candidates,
        safety.get("unsafe_embedding_candidate_count", 0),
        f"<= {max_unsafe_embedding_candidates}",
    )

    graph_quality = None
    if isinstance(artifact, Mapping):
        graph_quality = artifact.get("graph_explorer_v2_nomenclature_quality")
    if require_graph_explorer_quality_pass:
        graph_quality_status = None
        if isinstance(graph_quality, Mapping):
            graph_quality_status = graph_quality.get("status")
        add_quality_check(checks, "graph_explorer_v2_nomenclature_quality_status", graph_quality_status == "PASS", graph_quality_status, "PASS")

    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    summary = checkpoint_summary(checkpoint)
    summary.update(
        {
            "status": status,
            "quality_check_count": len(checks),
            "failed_check_count": sum(1 for check in checks if check["status"] != "PASS"),
        }
    )
    return QualityResult(status=status, checks=checks, summary=summary)


def write_quality_result(quality: QualityResult, output_path: Path) -> None:
    payload = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "generated_at_utc": utc_now_iso(),
        "status": quality.status,
        "summary": quality.summary,
        "checks": quality.checks,
    }
    write_json(output_path, payload)


def resolve_database_url(cli_database_url: str | None) -> str:
    database_url = cli_database_url or os.environ.get("TRACE_NET_DATABASE_URL")
    if not database_url:
        raise CheckpointError(
            "database URL is required. Pass --database-url or set TRACE_NET_DATABASE_URL. "
            "Example: export TRACE_NET_DATABASE_URL='postgresql://tracenet:tracenet@localhost:5432/tracenet_dev'"
        )
    return database_url


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze TRACE-Net graph/UI baseline checkpoint v1.")
    parser.add_argument("--database-url", default=None, help="Postgres URL. Defaults to TRACE_NET_DATABASE_URL.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for checkpoint JSON files.")
    parser.add_argument("--graph-explorer-dir", default=str(DEFAULT_GRAPH_EXPLORER_DIR), help="Existing graph explorer artifact directory to checksum.")
    parser.add_argument("--checkpoint-name", default="trace_net_graph_ui_context_v2_nomenclature_baseline_v1")
    parser.add_argument("--require-first-pages", default="1-50", help="Required context-v2 page coverage range, e.g. 1-50.")
    parser.add_argument("--skip-artifacts", action="store_true", help="Do not include graph explorer artifact checksums.")
    parser.add_argument("--quality", action="store_true", help="Also run baseline quality checks after freezing.")
    parser.add_argument("--min-page-count", type=int, default=509)
    parser.add_argument("--min-part-nodes", type=int, default=1)
    parser.add_argument("--min-nomenclature-nodes", type=int, default=1)
    parser.add_argument("--min-has-nomenclature-edges", type=int, default=1)
    parser.add_argument("--min-context-v2-pages", type=int, default=50)
    parser.add_argument("--min-has-context-v2-edges", type=int, default=50)
    parser.add_argument("--min-rag-candidates", type=int, default=0)
    parser.add_argument("--min-source-citations", type=int, default=0)
    parser.add_argument("--require-graph-explorer-quality-pass", action="store_true")
    return parser


def main_build(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        database_url = resolve_database_url(args.database_url)
        result = build_graph_baseline_checkpoint(
            database_url=database_url,
            output_dir=Path(args.output_dir),
            graph_explorer_dir=Path(args.graph_explorer_dir),
            checkpoint_name=args.checkpoint_name,
            require_first_pages=args.require_first_pages,
            include_artifacts=not args.skip_artifacts,
        )
        summary = result["summary"]
        print("TRACE-Net graph baseline checkpoint v1")
        print(" Status: FROZEN")
        for key in (
            "page_count",
            "part_node_count",
            "nomenclature_node_count",
            "has_nomenclature_edge_count",
            "page_context_v2_page_count",
            "has_context_v2_edge_count",
            "required_context_v2_missing_page_count",
            "rag_candidate_count",
            "source_citation_count",
            "checkpoint_sha256",
        ):
            print(f" {key}: {summary.get(key)}")
        for label, path in result["paths"].items():
            print(f" {label}: {path}")

        if args.quality:
            quality = evaluate_checkpoint_quality(
                result["checkpoint"],
                min_page_count=args.min_page_count,
                min_part_nodes=args.min_part_nodes,
                min_nomenclature_nodes=args.min_nomenclature_nodes,
                min_has_nomenclature_edges=args.min_has_nomenclature_edges,
                min_context_v2_pages=args.min_context_v2_pages,
                min_has_context_v2_edges=args.min_has_context_v2_edges,
                require_first_pages=args.require_first_pages,
                min_rag_candidates=args.min_rag_candidates,
                min_source_citations=args.min_source_citations,
                require_graph_explorer_quality_pass=args.require_graph_explorer_quality_pass,
            )
            quality_path = Path(args.output_dir) / DEFAULT_QUALITY_FILE
            write_quality_result(quality, quality_path)
            print(f" Quality status: {quality.status}")
            print(f" quality_path: {quality_path.as_posix()}")
            return 0 if quality.passed else 1
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net graph baseline checkpoint v1 quality.")
    parser.add_argument("--checkpoint-path", default=str(DEFAULT_OUTPUT_DIR / DEFAULT_CHECKPOINT_FILE))
    parser.add_argument("--min-page-count", type=int, default=509)
    parser.add_argument("--min-part-nodes", type=int, default=1)
    parser.add_argument("--min-nomenclature-nodes", type=int, default=1)
    parser.add_argument("--min-has-nomenclature-edges", type=int, default=1)
    parser.add_argument("--min-context-v2-pages", type=int, default=50)
    parser.add_argument("--min-has-context-v2-edges", type=int, default=50)
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--min-rag-candidates", type=int, default=0)
    parser.add_argument("--min-source-citations", type=int, default=0)
    parser.add_argument("--max-unsafe-embedding-candidates", type=int, default=0)
    parser.add_argument("--require-graph-explorer-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--quality-path", default=None)
    return parser


def main_quality(argv: Sequence[str] | None = None) -> int:
    parser = quality_arg_parser()
    args = parser.parse_args(argv)
    checkpoint_path = Path(args.checkpoint_path)
    try:
        checkpoint = load_json(checkpoint_path)
        quality = evaluate_checkpoint_quality(
            checkpoint,
            min_page_count=args.min_page_count,
            min_part_nodes=args.min_part_nodes,
            min_nomenclature_nodes=args.min_nomenclature_nodes,
            min_has_nomenclature_edges=args.min_has_nomenclature_edges,
            min_context_v2_pages=args.min_context_v2_pages,
            min_has_context_v2_edges=args.min_has_context_v2_edges,
            require_first_pages=args.require_first_pages,
            min_rag_candidates=args.min_rag_candidates,
            min_source_citations=args.min_source_citations,
            max_unsafe_embedding_candidates=args.max_unsafe_embedding_candidates,
            require_graph_explorer_quality_pass=args.require_graph_explorer_quality_pass,
        )
        print("TRACE-Net graph baseline checkpoint v1 quality")
        print(f" Status: {quality.status}")
        for key in (
            "page_count",
            "part_node_count",
            "nomenclature_node_count",
            "has_nomenclature_edge_count",
            "page_context_v2_page_count",
            "has_context_v2_edge_count",
            "required_context_v2_missing_page_count",
            "rag_candidate_count",
            "source_citation_count",
            "unsafe_embedding_candidate_count",
        ):
            print(f" {key}: {quality.summary.get(key)}")
        failed = [check for check in quality.checks if check["status"] != "PASS"]
        if failed:
            print(" Failed checks:")
            for check in failed:
                print(f"  - {check['name']}: actual={check['actual']} expected={check['expected']}")
        if args.write_json:
            quality_path = Path(args.quality_path) if args.quality_path else checkpoint_path.with_name(DEFAULT_QUALITY_FILE)
            write_quality_result(quality, quality_path)
            print(f" quality_path: {quality_path.as_posix()}")
        return 0 if quality.passed else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
