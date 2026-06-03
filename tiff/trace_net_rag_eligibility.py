"""TRACE-Net RAG eligibility builder v1.

This module converts the Stage 5 policy-controlled decision view into stable
RAG evidence pools. It does not embed, index, or answer questions. It simply
separates policy-controlled evidence records into source evidence, verified
part evidence, derived context, and excluded evidence.

Input defaults:
  local_data/organization/trace_net/confidence/stage5_control/
    trace_lc_stage5_policy_control_records.jsonl

Output defaults:
  local_data/organization/trace_net/rag_eligibility/
"""
from __future__ import annotations

import argparse
import html
import json
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_STAGE5_DIR = DEFAULT_TRACE_NET_DIR / "confidence" / "stage5_control"
DEFAULT_STAGE5_RECORDS = DEFAULT_STAGE5_DIR / "trace_lc_stage5_policy_control_records.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_TRACE_NET_DIR / "rag_eligibility"

ALL_RECORDS_FILE = "rag_eligibility_records.jsonl"
SOURCE_FILE = "rag_eligible_source_evidence.jsonl"
VERIFIED_PART_FILE = "rag_eligible_verified_part_evidence.jsonl"
DERIVED_FILE = "rag_eligible_derived_context.jsonl"
EXCLUDED_FILE = "rag_excluded_records.jsonl"
SUMMARY_FILE = "rag_eligibility_summary.json"
REVIEW_MD_FILE = "rag_eligibility_review.md"
REVIEW_HTML_FILE = "rag_eligibility_review.html"
GRAPH_NODES_FILE = "rag_eligibility_graph_nodes.json"
GRAPH_EDGES_FILE = "rag_eligibility_graph_edges.json"
QUALITY_FILE = "rag_eligibility_quality.json"

VERSION = "trace_net_rag_eligibility_v1"
RAG_INCLUDE_ACTIONS = {
    "include_as_source_evidence",
    "include_as_verified_part_evidence",
    "include_as_derived_context",
    "include_in_rag",
}
SOURCE_OK = {"source_verified", "local_source_verified", "source_link_only"}
TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}


@dataclass(frozen=True)
class RagEligibilityPaths:
    stage5_records: Path = DEFAULT_STAGE5_RECORDS
    output_dir: Path = DEFAULT_OUTPUT_DIR
    all_records_path: Path | None = None
    source_path: Path | None = None
    verified_part_path: Path | None = None
    derived_path: Path | None = None
    excluded_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def all_records(self) -> Path:
        return self.all_records_path or (self.output_dir / ALL_RECORDS_FILE)

    @property
    def source(self) -> Path:
        return self.source_path or (self.output_dir / SOURCE_FILE)

    @property
    def verified_part(self) -> Path:
        return self.verified_part_path or (self.output_dir / VERIFIED_PART_FILE)

    @property
    def derived(self) -> Path:
        return self.derived_path or (self.output_dir / DERIVED_FILE)

    @property
    def excluded(self) -> Path:
        return self.excluded_path or (self.output_dir / EXCLUDED_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / REVIEW_HTML_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / GRAPH_EDGES_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass
class RagEligibilityOptions:
    open_report: bool = False
    max_samples: int = 40


# ---------------------------------------------------------------------------
# IO/helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _tier(value: Any, default: str = "D") -> str:
    out = _text(value, default).upper()
    return out if out in TIER_ORDER else default


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _count(values: Sequence[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _record_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("record_id") or row.get("evidence_id") or f"{row.get('page_id','unknown')}:{row.get('evidence_layer','unknown')}")


def _final_rag_action(row: Mapping[str, Any]) -> str:
    return _text(row.get("final_rag_action") or row.get("selected_rag_action") or row.get("rag_action"), "exclude_from_rag")


def _final_trust_tier(row: Mapping[str, Any]) -> str:
    return _tier(row.get("final_trust_tier") or row.get("selected_trust_tier") or row.get("trust_tier"), "D")


def _final_repair_action(row: Mapping[str, Any]) -> str:
    return _text(row.get("final_repair_action") or row.get("selected_repair_action") or row.get("repair_action"), "human_review")


def _source_trace_status(row: Mapping[str, Any]) -> str:
    return _text(row.get("source_trace_status") or _as_dict(row.get("source_trace")).get("status"), "unknown")


def _rag_bucket(action: str) -> str:
    if action == "include_as_source_evidence":
        return "source_evidence"
    if action == "include_as_verified_part_evidence":
        return "verified_part_evidence"
    if action in {"include_as_derived_context", "include_in_rag"}:
        return "derived_context"
    return "excluded"


def _is_rag_include(action: str) -> bool:
    return action in RAG_INCLUDE_ACTIONS or action.startswith("include_")


def _eligibility_record(row: Mapping[str, Any]) -> dict[str, Any]:
    action = _final_rag_action(row)
    tier = _final_trust_tier(row)
    layer = _text(row.get("evidence_layer"), "unknown")
    page_id = _text(row.get("page_id"), "")
    source_trace_status = _source_trace_status(row)
    bucket = _rag_bucket(action)
    unsafe_reasons: list[str] = []
    if _is_rag_include(action):
        if tier == "D":
            unsafe_reasons.append("D_tier_rag_include")
        if source_trace_status not in SOURCE_OK:
            unsafe_reasons.append("source_untraceable_rag_include")
        if layer in {"table_candidate", "table_tiles"}:
            unsafe_reasons.append("routing_or_preprocessing_artifact_direct_rag_include")
        if row.get("unsafe_stage5_rag_include") is True:
            unsafe_reasons.extend(_text(x) for x in _as_list(row.get("unsafe_reasons")) if _text(x))
    return {
        "eligibility_id": f"rag:{_record_id(row)}",
        "source_record_id": _record_id(row),
        "page_id": page_id,
        "evidence_layer": layer,
        "rag_bucket": bucket,
        "rag_eligible": bucket != "excluded" and not unsafe_reasons,
        "final_rag_action": action,
        "final_trust_tier": tier,
        "final_repair_action": _final_repair_action(row),
        "stage5_controlled": bool(row.get("stage5_controlled")),
        "decision_source": _text(row.get("decision_source"), "unknown"),
        "control_status": _text(row.get("control_status"), "unknown"),
        "confidence_tier": _tier(row.get("confidence_tier"), "D"),
        "usable_confidence": round(_num(row.get("usable_confidence"), 0.0), 6),
        "support_score": round(_num(row.get("support_score"), 0.0), 6),
        "risk_score": round(_num(row.get("risk_score"), 0.0), 6),
        "source_trace_status": source_trace_status,
        "graph_support_status": _text(row.get("graph_support_status"), "unknown"),
        "part_catalog_status": _text(row.get("part_catalog_status"), "unknown"),
        "hallucination_risk_status": _text(row.get("hallucination_risk_status"), "unknown"),
        "unsafe_rag_eligible": bool(unsafe_reasons),
        "unsafe_reasons": sorted(set(unsafe_reasons)),
        "eligibility_reasons": _eligibility_reasons(row, bucket, unsafe_reasons),
    }


def _eligibility_reasons(row: Mapping[str, Any], bucket: str, unsafe_reasons: Sequence[str]) -> list[str]:
    if unsafe_reasons:
        return ["unsafe_rag_include_blocked"] + list(unsafe_reasons)
    layer = _text(row.get("evidence_layer"), "unknown")
    action = _final_rag_action(row)
    if bucket == "source_evidence":
        return ["source_trace_or_source_evidence_selected", "safe_for_source_index"]
    if bucket == "verified_part_evidence":
        return ["verified_part_evidence_selected", "safe_for_verified_part_index"]
    if bucket == "derived_context":
        if layer == "table_tile_text_refined":
            return ["refined_table_tile_text_selected", "derived_context_only", "not_canonical_source_truth"]
        return ["derived_context_selected", "not_canonical_source_truth"]
    if action == "exclude_until_table_text_exists":
        return ["table_tiles_exist_but_text_not_ready"]
    if action == "exclude_until_table_tiles_exist":
        return ["table_candidate_requires_tiles"]
    return ["excluded_by_stage5_decision"]


# ---------------------------------------------------------------------------
# Build output artifacts
# ---------------------------------------------------------------------------


def build_rag_eligibility(paths: RagEligibilityPaths, options: RagEligibilityOptions | None = None) -> dict[str, Any]:
    options = options or RagEligibilityOptions()
    source_rows = _read_jsonl(paths.stage5_records)
    rows = [_eligibility_record(row) for row in source_rows]
    pages = sorted({row["page_id"] for row in rows if row.get("page_id")})

    source_evidence = [row for row in rows if row["rag_bucket"] == "source_evidence" and row["rag_eligible"]]
    verified_part = [row for row in rows if row["rag_bucket"] == "verified_part_evidence" and row["rag_eligible"]]
    derived = [row for row in rows if row["rag_bucket"] == "derived_context" and row["rag_eligible"]]
    excluded = [row for row in rows if row["rag_bucket"] == "excluded" or not row["rag_eligible"]]
    unsafe = [row for row in rows if row["unsafe_rag_eligible"]]

    summary = {
        "status": "OK",
        "version": VERSION,
        "created_at": _utc_now(),
        "stage5_records_path": str(paths.stage5_records),
        "records": len(rows),
        "pages": len(pages),
        "rag_eligible_records": len(source_evidence) + len(verified_part) + len(derived),
        "rag_excluded_records": len(excluded),
        "source_evidence_records": len(source_evidence),
        "verified_part_evidence_records": len(verified_part),
        "derived_context_records": len(derived),
        "unsafe_rag_eligible_records": len(unsafe),
        "rag_bucket_counts": _count([row["rag_bucket"] for row in rows]),
        "rag_action_counts": _count([row["final_rag_action"] for row in rows]),
        "trust_tier_counts": _count([row["final_trust_tier"] for row in rows]),
        "evidence_layer_counts": _count([row["evidence_layer"] for row in rows]),
        "source_trace_status_counts": _count([row["source_trace_status"] for row in rows]),
        "stage5_controlled_records": len([row for row in rows if row["stage5_controlled"]]),
        "derived_context_layer_counts": _count([row["evidence_layer"] for row in derived]),
        "excluded_action_counts": _count([row["final_rag_action"] for row in excluded]),
        "paths": {
            "all_records": str(paths.all_records),
            "source_evidence": str(paths.source),
            "verified_part_evidence": str(paths.verified_part),
            "derived_context": str(paths.derived),
            "excluded_records": str(paths.excluded),
            "summary": str(paths.summary),
            "review_html": str(paths.review_html),
            "graph_nodes": str(paths.graph_nodes),
            "graph_edges": str(paths.graph_edges),
        },
        "samples": {
            "source_evidence": source_evidence[: options.max_samples],
            "verified_part_evidence": verified_part[: options.max_samples],
            "derived_context": derived[: options.max_samples],
            "excluded": excluded[: options.max_samples],
            "unsafe": unsafe[: options.max_samples],
        },
    }

    graph_nodes, graph_edges = _build_graph(rows)
    summary["graph_nodes"] = len(graph_nodes)
    summary["graph_edges"] = len(graph_edges)

    _write_jsonl(paths.all_records, rows)
    _write_jsonl(paths.source, source_evidence)
    _write_jsonl(paths.verified_part, verified_part)
    _write_jsonl(paths.derived, derived)
    _write_jsonl(paths.excluded, excluded)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, graph_nodes)
    _write_json(paths.graph_edges, graph_edges)
    _write_text(paths.review_md, _render_markdown(summary))
    _write_text(paths.review_html, _render_html(summary))

    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return summary


def _build_graph(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, kind: str, **props: Any) -> None:
        if not node_id:
            return
        node = nodes.setdefault(node_id, {"id": node_id, "kind": kind})
        node.update({k: v for k, v in props.items() if v is not None})

    def add_edge(src: str, dst: str, kind: str, **props: Any) -> None:
        if not src or not dst:
            return
        edges.append({"source": src, "target": dst, "kind": kind, **{k: v for k, v in props.items() if v is not None}})

    root = "rag_eligibility:root"
    add_node(root, "rag_eligibility_root", version=VERSION)
    for pool in ("source_evidence", "verified_part_evidence", "derived_context", "excluded"):
        pool_id = f"rag_pool:{pool}"
        add_node(pool_id, "rag_pool", value=pool)
        add_edge(root, pool_id, "HAS_RAG_POOL")

    for row in rows:
        rec_id = f"rag_evidence:{row.get('source_record_id')}"
        page_id = f"page:{row.get('page_id')}" if row.get("page_id") else ""
        pool_id = f"rag_pool:{row.get('rag_bucket')}"
        layer_id = f"trait:evidence_layer:{row.get('evidence_layer')}"
        action_id = f"trait:rag_action:{row.get('final_rag_action')}"
        tier_id = f"trait:trust:{row.get('evidence_layer')}:{row.get('final_trust_tier')}"
        add_node(rec_id, "rag_evidence_record", page_id=row.get("page_id"), evidence_layer=row.get("evidence_layer"), rag_bucket=row.get("rag_bucket"), rag_eligible=row.get("rag_eligible"), final_rag_action=row.get("final_rag_action"), final_trust_tier=row.get("final_trust_tier"), usable_confidence=row.get("usable_confidence"))
        add_node(pool_id, "rag_pool", value=row.get("rag_bucket"))
        add_node(layer_id, "trait", namespace="evidence_layer", value=row.get("evidence_layer"))
        add_node(action_id, "trait", namespace="rag_action", value=row.get("final_rag_action"))
        add_node(tier_id, "trait", namespace="trust", evidence_layer=row.get("evidence_layer"), value=row.get("final_trust_tier"))
        add_edge(root, rec_id, "HAS_RAG_ELIGIBILITY_RECORD")
        add_edge(rec_id, pool_id, "IN_RAG_POOL")
        add_edge(rec_id, layer_id, "HAS_EVIDENCE_LAYER")
        add_edge(rec_id, action_id, "HAS_RAG_ACTION")
        add_edge(rec_id, tier_id, "HAS_TRUST_TIER")
        if page_id:
            add_node(page_id, "page", page_id=row.get("page_id"))
            add_edge(page_id, rec_id, "HAS_RAG_ELIGIBILITY_RECORD")
    return list(nodes.values()), edges


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(out)


def _render_markdown(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net RAG Eligibility v1")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append(f"Version: `{summary.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "records", "pages", "rag_eligible_records", "rag_excluded_records", "source_evidence_records",
        "verified_part_evidence_records", "derived_context_records", "unsafe_rag_eligible_records",
        "stage5_controlled_records", "graph_nodes", "graph_edges",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## RAG buckets")
    lines.append("`" + str(summary.get("rag_bucket_counts", {})) + "`")
    lines.append("")
    lines.append("## RAG actions")
    lines.append("`" + str(summary.get("rag_action_counts", {})) + "`")
    lines.append("")
    lines.append("## Trust tiers")
    lines.append("`" + str(summary.get("trust_tier_counts", {})) + "`")
    lines.append("")
    sample_groups = [
        ("Source evidence", summary.get("samples", {}).get("source_evidence", [])),
        ("Verified part evidence", summary.get("samples", {}).get("verified_part_evidence", [])),
        ("Derived context", summary.get("samples", {}).get("derived_context", [])),
        ("Excluded", summary.get("samples", {}).get("excluded", [])),
    ]
    for title, rows in sample_groups:
        lines.append(f"## {title} samples")
        table_rows = []
        for row in rows[:20]:
            table_rows.append([
                row.get("page_id", ""),
                row.get("evidence_layer", ""),
                row.get("final_trust_tier", ""),
                row.get("final_rag_action", ""),
                row.get("usable_confidence", ""),
                "; ".join(row.get("eligibility_reasons", [])[:3]),
            ])
        lines.append(_md_table(["Page", "Layer", "Trust", "RAG action", "Confidence", "Reasons"], table_rows) if table_rows else "None.")
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_html(summary: Mapping[str, Any]) -> str:
    md = _render_markdown(summary)
    # Small self-contained HTML without markdown conversion dependency.
    def esc(x: Any) -> str:
        return html.escape(str(x))
    sections: list[str] = []
    sections.append("<h1>TRACE-Net RAG Eligibility v1</h1>")
    sections.append(f"<p><b>Status:</b> {esc(summary.get('status'))} &nbsp; <b>Version:</b> <code>{esc(summary.get('version'))}</code></p>")
    sections.append("<h2>Summary</h2><table><tbody>")
    for key in (
        "records", "pages", "rag_eligible_records", "rag_excluded_records", "source_evidence_records",
        "verified_part_evidence_records", "derived_context_records", "unsafe_rag_eligible_records",
        "stage5_controlled_records", "graph_nodes", "graph_edges",
    ):
        sections.append(f"<tr><th>{esc(key)}</th><td>{esc(summary.get(key))}</td></tr>")
    sections.append("</tbody></table>")
    sections.append("<h2>Counts</h2>")
    for key in ("rag_bucket_counts", "rag_action_counts", "trust_tier_counts", "evidence_layer_counts"):
        sections.append(f"<h3>{esc(key)}</h3><pre>{esc(json.dumps(summary.get(key, {}), indent=2, sort_keys=True))}</pre>")
    for title, rows in (
        ("Source evidence", summary.get("samples", {}).get("source_evidence", [])),
        ("Verified part evidence", summary.get("samples", {}).get("verified_part_evidence", [])),
        ("Derived context", summary.get("samples", {}).get("derived_context", [])),
        ("Excluded", summary.get("samples", {}).get("excluded", [])),
        ("Unsafe", summary.get("samples", {}).get("unsafe", [])),
    ):
        sections.append(f"<h2>{esc(title)} samples</h2>")
        sections.append("<table><thead><tr><th>Page</th><th>Layer</th><th>Trust</th><th>RAG action</th><th>Confidence</th><th>Reasons</th></tr></thead><tbody>")
        for row in rows[:40]:
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('page_id',''))}</td>"
                f"<td>{esc(row.get('evidence_layer',''))}</td>"
                f"<td>{esc(row.get('final_trust_tier',''))}</td>"
                f"<td><code>{esc(row.get('final_rag_action',''))}</code></td>"
                f"<td>{esc(row.get('usable_confidence',''))}</td>"
                f"<td>{esc('; '.join(row.get('eligibility_reasons', [])[:4]))}</td>"
                "</tr>"
            )
        sections.append("</tbody></table>")
    css = "body{font-family:Arial,sans-serif;margin:24px;line-height:1.35}table{border-collapse:collapse;margin:12px 0;width:100%}th,td{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#f6f6f6;text-align:left}pre{background:#f6f6f6;padding:10px;overflow:auto}code{background:#f6f6f6;padding:1px 3px}"
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net RAG Eligibility</title><style>" + css + "</style></head><body>" + "\n".join(sections) + "</body></html>\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net RAG eligibility pools from Stage 5 policy-controlled decisions.")
    parser.add_argument("--stage5-records", type=Path, default=DEFAULT_STAGE5_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--open", action="store_true", dest="open_report")
    parser.add_argument("--samples", type=int, default=40)
    args = parser.parse_args(argv)

    paths = RagEligibilityPaths(stage5_records=args.stage5_records, output_dir=args.output_dir)
    result = build_rag_eligibility(paths, RagEligibilityOptions(open_report=args.open_report, max_samples=args.samples))
    print("TRACE-Net RAG eligibility builder")
    print(f"  Status: {result['status']}")
    print(f"  Output dir: {args.output_dir}")
    print("  Summary:")
    for key in (
        "records", "pages", "rag_eligible_records", "rag_excluded_records", "source_evidence_records",
        "verified_part_evidence_records", "derived_context_records", "unsafe_rag_eligible_records",
        "stage5_controlled_records", "graph_nodes", "graph_edges",
    ):
        print(f"    {key}: {result.get(key)}")
    print("  RAG buckets:", result.get("rag_bucket_counts"))
    print("Files written:")
    for key, value in result.get("paths", {}).items():
        print(f"  {key}: {value}")
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
