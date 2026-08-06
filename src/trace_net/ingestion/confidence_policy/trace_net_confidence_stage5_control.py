"""TRACE-Net Layer Confidence Stage 5b policy control view.

Stage 5b extends the Stage 5a controlled decision artifact by enabling the
layer-specific confidence policy for refined table-tile text in addition to
the deterministic source/part layers. It still does not mutate the main
Evidence Consensus records.

Default controlled layers:
- source_trace
- part_catalog
- table_tile_text_refined

Still rule-controlled by default:
- visual_text
- table_candidate
- table_tiles
"""
from __future__ import annotations

import argparse
import html
import json
import math
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_CONSENSUS_DIR = DEFAULT_TRACE_NET_DIR / "evidence_consensus"
DEFAULT_CONFIDENCE_DIR = DEFAULT_TRACE_NET_DIR / "confidence"
DEFAULT_CONSENSUS_RECORDS = DEFAULT_CONSENSUS_DIR / "evidence_consensus_records.jsonl"
DEFAULT_POLICY = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy.json"
DEFAULT_OUTPUT_DIR = DEFAULT_CONFIDENCE_DIR / "stage5_control"

CONTROL_RECORDS_FILE = "trace_lc_stage5_policy_control_records.jsonl"
SUMMARY_FILE = "trace_lc_stage5_policy_control_summary.json"
REPORT_MD_FILE = "trace_lc_stage5_policy_control_report.md"
REPORT_HTML_FILE = "trace_lc_stage5_policy_control_report.html"
GRAPH_NODES_FILE = "trace_lc_stage5_policy_control_graph_nodes.json"
GRAPH_EDGES_FILE = "trace_lc_stage5_policy_control_graph_edges.json"
QUALITY_FILE = "trace_lc_stage5_policy_control_quality.json"

STAGE5_VERSION = "trace_lc_stage5b_policy_control_v1"
TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}
SOURCE_OK = {"source_verified", "local_source_verified", "source_link_only"}
SOURCE_STRONG = {"source_verified", "local_source_verified"}
RAG_INCLUDE_PREFIX = "include_"
DEFAULT_CONTROLLED_LAYERS = ("source_trace", "part_catalog", "table_tile_text_refined")


@dataclass(frozen=True)
class ConfidenceStage5Paths:
    consensus_records: Path = DEFAULT_CONSENSUS_RECORDS
    confidence_policy: Path = DEFAULT_POLICY
    output_dir: Path = DEFAULT_OUTPUT_DIR
    records_path: Path | None = None
    summary_path: Path | None = None
    report_md_path: Path | None = None
    report_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def records(self) -> Path:
        return self.records_path or (self.output_dir / CONTROL_RECORDS_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def report_md(self) -> Path:
        return self.report_md_path or (self.output_dir / REPORT_MD_FILE)

    @property
    def report_html(self) -> Path:
        return self.report_html_path or (self.output_dir / REPORT_HTML_FILE)

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
class ConfidenceStage5Options:
    controlled_layers: tuple[str, ...] = DEFAULT_CONTROLLED_LAYERS
    open_report: bool = False
    max_samples: int = 40


# ---------------------------------------------------------------------------
# Basic IO/helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


def _tier(value: Any, default: str = "D") -> str:
    out = _text(value, default).upper()
    return out if out in TIER_ORDER else default


def _rank(tier: str) -> int:
    return TIER_ORDER.get(_tier(tier), 0)


def _count(values: Sequence[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _record_id(record: Mapping[str, Any]) -> str:
    return _text(record.get("record_id") or record.get("evidence_id") or f"{record.get('page_id', 'unknown')}:{record.get('evidence_layer', 'unknown')}")


def _status(record: Mapping[str, Any], key: str) -> str:
    value = _as_dict(record.get(key)).get("status")
    return _text(value).lower()


def _confidence_scores(record: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(record.get("confidence_scores"))


def _source_ok(record: Mapping[str, Any]) -> bool:
    return _status(record, "source_trace") in SOURCE_OK


def _source_strong(record: Mapping[str, Any]) -> bool:
    return _status(record, "source_trace") in SOURCE_STRONG


def _graph_strong(record: Mapping[str, Any]) -> bool:
    return _status(record, "graph_support") in {"strong_support", "supported", "source_verified"}


def _catalog_supported(record: Mapping[str, Any]) -> bool:
    status = _status(record, "part_catalog_support")
    if any(token in status for token in ("catalog", "page_part_mentions_present", "verified", "supported")):
        if "not_applicable" not in status and "unsupported" not in status and "conflict" not in status:
            return True
    props = _as_dict(record.get("properties"))
    for key in ("catalog_supported_part_numbers", "canonical_part_numbers", "catalog_supported_parts"):
        if _as_list(props.get(key)):
            return True
    return False


def _rag_includes(action: str) -> bool:
    return _text(action).startswith(RAG_INCLUDE_PREFIX)


def _has_hard_block(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not _source_ok(record):
        reasons.append("source_untraceable")
    scores = _confidence_scores(record)
    if scores.get("hard_gate_blocked") is True:
        reasons.extend(str(x) for x in _as_list(scores.get("hard_gate_reasons")) if str(x))
    # Check common risk keys/reasons for hard blockers.
    haystack_parts: list[str] = []
    for key in ("reasons", "review_flags", "traits"):
        value = record.get(key)
        if isinstance(value, list):
            haystack_parts.extend(str(v) for v in value)
    props = _as_dict(record.get("properties"))
    for key in ("metadata_leakage", "prompt_template_leakage", "refusal_like", "section_bleed_unrepaired"):
        if props.get(key) is True:
            reasons.append(key)
    haystack = " ".join(haystack_parts).lower()
    for token in ("metadata_leakage", "prompt_template_leakage", "refusal_like", "section_bleed_unrepaired"):
        if token in haystack:
            reasons.append(token)
    return bool(reasons), sorted(set(reasons))


# ---------------------------------------------------------------------------
# Stage 5b policy control
# ---------------------------------------------------------------------------


def _policy_decision_for_controlled_layer(record: Mapping[str, Any], layer_policy: Mapping[str, Any]) -> tuple[str, str, str, list[str]]:
    layer = _text(record.get("evidence_layer"), "unknown")
    blocked, block_reasons = _has_hard_block(record)
    if blocked:
        return "D", "exclude_from_rag", "human_review", ["hard_blocked"] + block_reasons

    if layer == "source_trace":
        if _source_strong(record) and _graph_strong(record):
            return "A", "include_as_source_evidence", "none", ["stage5_policy_control", "source_trace_verified", "graph_support_strong"]
        if _source_ok(record):
            return "B", "exclude_from_rag", "source_trace_review", ["stage5_policy_control", "source_trace_ok_but_not_strong"]
        return "D", "exclude_from_rag", "source_repair", ["stage5_policy_control", "source_trace_not_ok"]

    if layer == "part_catalog":
        if _source_ok(record) and _catalog_supported(record) and _graph_strong(record):
            return "A", "include_as_verified_part_evidence", "none", ["stage5_policy_control", "catalog_supported", "source_trace_verified", "graph_support_strong"]
        if _source_ok(record) and _catalog_supported(record):
            # Policy can acknowledge B strength, but the min RAG tier for part catalog is A.
            return "B", "exclude_from_rag", "part_catalog_review", ["stage5_policy_control", "catalog_supported_without_strong_graph_support"]
        return "C", "exclude_from_rag", "part_catalog_review", ["stage5_policy_control", "no_catalog_supported_part_claim"]


    if layer == "table_tile_text_refined":
        scores = _confidence_scores(record)
        thresholds = _as_dict(layer_policy.get("thresholds"))
        threshold_a = _num(thresholds.get("A"), 0.82)
        threshold_b = _num(thresholds.get("B"), 0.64)
        usable = _num(scores.get("usable_confidence"), 0.0)
        if _source_ok(record) and _catalog_supported(record):
            if usable >= threshold_a and _graph_strong(record):
                return "A", "include_as_derived_context", "none", [
                    "stage5b_policy_control",
                    "refined_table_text_catalog_supported",
                    "source_trace_verified",
                    "confidence_at_or_above_A_threshold",
                ]
            if usable >= threshold_b:
                return "B", "include_as_derived_context", "none", [
                    "stage5b_policy_control",
                    "refined_table_text_catalog_supported",
                    "source_trace_verified",
                    "confidence_at_or_above_B_threshold",
                ]
            return "C", "exclude_from_rag", "run_table_tile_ocr_or_human_review", [
                "stage5b_policy_control",
                "catalog_supported_but_confidence_below_B_threshold",
            ]
        if _source_ok(record):
            return "C", "exclude_from_rag", "run_table_tile_ocr_or_human_review", [
                "stage5b_policy_control",
                "refined_table_text_without_catalog_supported_part",
            ]
        return "D", "exclude_from_rag", "human_review", [
            "stage5b_policy_control",
            "refined_table_text_source_untraceable",
        ]

    # Should not reach this for controlled layers, but keep safe behavior.
    current_tier = _tier(record.get("trust_tier"), "C")
    current_rag = _text(record.get("rag_action"), "exclude_from_rag")
    current_repair = _text(record.get("repair_action"), "human_review")
    return current_tier, current_rag, current_repair, ["stage5_policy_control", "unsupported_controlled_layer_retained_current"]


def _stage5_record(record: Mapping[str, Any], controlled_layers: set[str], policy: Mapping[str, Any]) -> dict[str, Any]:
    layer = _text(record.get("evidence_layer"), "unknown")
    current_tier = _tier(record.get("trust_tier"), "D")
    current_rag = _text(record.get("rag_action"), "exclude_from_rag")
    current_repair = _text(record.get("repair_action"), "human_review")
    scores = _confidence_scores(record)
    rule = _as_dict(_as_dict(policy.get("layers")).get(layer))
    controlled = layer in controlled_layers

    if controlled:
        selected_tier, selected_rag, selected_repair, reasons = _policy_decision_for_controlled_layer(record, rule)
        decision_source = "confidence_policy_controlled"
    else:
        selected_tier, selected_rag, selected_repair = current_tier, current_rag, current_repair
        reasons = ["rule_decision_retained", "layer_not_enabled_for_stage5_control"]
        decision_source = "rule_retained"

    unsafe = False
    unsafe_reasons: list[str] = []
    if _rag_includes(selected_rag):
        if selected_tier == "D":
            unsafe = True
            unsafe_reasons.append("D_tier_include")
        if not _source_ok(record):
            unsafe = True
            unsafe_reasons.append("source_untraceable_include")
        if layer in {"table_candidate", "table_tiles"}:
            unsafe = True
            unsafe_reasons.append("routing_or_preprocessing_artifact_direct_include")
        blocked, block_reasons = _has_hard_block(record)
        if blocked:
            unsafe = True
            unsafe_reasons.extend(block_reasons)

    return {
        "record_id": _record_id(record),
        "page_id": _text(record.get("page_id")),
        "evidence_layer": layer,
        "stage5_controlled": controlled,
        "decision_source": decision_source,
        "control_status": "policy_controlled" if controlled else "rule_controlled",
        "current_trust_tier": current_tier,
        "selected_trust_tier": selected_tier,
        "final_trust_tier": selected_tier,
        "current_rag_action": current_rag,
        "selected_rag_action": selected_rag,
        "final_rag_action": selected_rag,
        "current_repair_action": current_repair,
        "selected_repair_action": selected_repair,
        "final_repair_action": selected_repair,
        "confidence_tier": _tier(scores.get("confidence_tier"), "D"),
        "usable_confidence": round(_num(scores.get("usable_confidence"), 0.0), 6),
        "support_score": round(_num(scores.get("support_score"), 0.0), 6),
        "risk_score": round(_num(scores.get("risk_score"), 0.0), 6),
        "source_trace_status": _status(record, "source_trace"),
        "graph_support_status": _status(record, "graph_support"),
        "part_catalog_status": _status(record, "part_catalog_support"),
        "hallucination_risk_status": _status(record, "hallucination_risk"),
        "trust_changed_by_stage5": current_tier != selected_tier,
        "rag_action_changed_by_stage5": current_rag != selected_rag,
        "repair_action_changed_by_stage5": current_repair != selected_repair,
        "unsafe_stage5_rag_include": unsafe,
        "unsafe_reasons": sorted(set(unsafe_reasons)),
        "stage5_reasons": reasons,
    }


def build_confidence_stage5_control(paths: ConfidenceStage5Paths, options: ConfidenceStage5Options | None = None) -> dict[str, Any]:
    options = options or ConfidenceStage5Options()
    records = _read_jsonl(paths.consensus_records)
    policy = _as_dict(_read_json(paths.confidence_policy, {}))
    controlled_layers = {layer.strip() for layer in options.controlled_layers if layer.strip()}
    controlled_records = [_stage5_record(record, controlled_layers, policy) for record in records]
    pages = sorted({row["page_id"] for row in controlled_records if row.get("page_id")})

    stage5_controlled = [row for row in controlled_records if row["stage5_controlled"]]
    stage5_uncontrolled = [row for row in controlled_records if not row["stage5_controlled"]]
    unsafe = [row for row in controlled_records if row["unsafe_stage5_rag_include"]]
    source_trace = [row for row in controlled_records if row["evidence_layer"] == "source_trace"]
    source_trace_a = [row for row in source_trace if row["selected_trust_tier"] == "A"]
    part_catalog = [row for row in controlled_records if row["evidence_layer"] == "part_catalog"]
    part_catalog_a = [row for row in part_catalog if row["selected_trust_tier"] == "A"]
    table_candidate_direct = [row for row in controlled_records if row["evidence_layer"] == "table_candidate" and _rag_includes(row["selected_rag_action"])]
    table_tiles_direct = [row for row in controlled_records if row["evidence_layer"] == "table_tiles" and _rag_includes(row["selected_rag_action"])]
    visual_controlled = [row for row in controlled_records if row["evidence_layer"] == "visual_text" and row["stage5_controlled"]]
    table_tile_text_refined = [row for row in controlled_records if row["evidence_layer"] == "table_tile_text_refined"]
    table_tile_text_refined_controlled = [row for row in table_tile_text_refined if row["stage5_controlled"]]
    table_tile_text_refined_derived = [row for row in table_tile_text_refined if row["selected_rag_action"] == "include_as_derived_context"]
    table_tile_text_refined_direct_verified = [row for row in table_tile_text_refined if row["selected_rag_action"] in {"include_as_verified_part_evidence", "include_as_source_evidence"}]
    table_tile_text_refined_a = [row for row in table_tile_text_refined if row["selected_trust_tier"] == "A"]
    table_tile_text_refined_b = [row for row in table_tile_text_refined if row["selected_trust_tier"] == "B"]
    table_tile_text_refined_c = [row for row in table_tile_text_refined if row["selected_trust_tier"] == "C"]
    rag_includes = [row for row in controlled_records if _rag_includes(row["selected_rag_action"])]
    trust_changes = [row for row in controlled_records if row["trust_changed_by_stage5"]]
    rag_changes = [row for row in controlled_records if row["rag_action_changed_by_stage5"]]
    repair_changes = [row for row in controlled_records if row["repair_action_changed_by_stage5"]]

    layer_counts = _count([row["evidence_layer"] for row in controlled_records])
    per_layer: dict[str, dict[str, Any]] = {}
    for row in controlled_records:
        layer = row["evidence_layer"]
        bucket = per_layer.setdefault(layer, {
            "records": 0,
            "controlled_records": 0,
            "selected_trust_tier_counts": {},
            "selected_rag_action_counts": {},
            "trust_changed_records": 0,
            "rag_action_changed_records": 0,
            "repair_action_changed_records": 0,
            "unsafe_stage5_rag_include_records": 0,
            "usable_values": [],
        })
        bucket["records"] += 1
        bucket["controlled_records"] += int(row["stage5_controlled"])
        bucket["selected_trust_tier_counts"][row["selected_trust_tier"]] = bucket["selected_trust_tier_counts"].get(row["selected_trust_tier"], 0) + 1
        bucket["selected_rag_action_counts"][row["selected_rag_action"]] = bucket["selected_rag_action_counts"].get(row["selected_rag_action"], 0) + 1
        bucket["trust_changed_records"] += int(row["trust_changed_by_stage5"])
        bucket["rag_action_changed_records"] += int(row["rag_action_changed_by_stage5"])
        bucket["repair_action_changed_records"] += int(row["repair_action_changed_by_stage5"])
        bucket["unsafe_stage5_rag_include_records"] += int(row["unsafe_stage5_rag_include"])
        bucket["usable_values"].append(row["usable_confidence"])
    for bucket in per_layer.values():
        values = bucket.pop("usable_values")
        bucket["avg_usable_confidence"] = round(sum(values) / len(values), 6) if values else 0.0
        bucket["selected_trust_tier_counts"] = dict(sorted(bucket["selected_trust_tier_counts"].items()))
        bucket["selected_rag_action_counts"] = dict(sorted(bucket["selected_rag_action_counts"].items()))

    result = {
        "status": "OK" if records and policy and not unsafe else ("FAIL" if not records or not policy else "OK_WITH_WARNINGS"),
        "version": STAGE5_VERSION,
        "created_at": _utc_now(),
        "records": len(controlled_records),
        "pages": len(pages),
        "policy_present": bool(policy),
        "policy_version": policy.get("version"),
        "controlled_layers": sorted(controlled_layers),
        "policy_controlled_records": len(stage5_controlled),
        "rule_controlled_records": len(stage5_uncontrolled),
        "controlled_record_count": len(stage5_controlled),
        "uncontrolled_record_count": len(stage5_uncontrolled),
        "uncontrolled_records": len(stage5_uncontrolled),
        "layer_counts": layer_counts,
        "selected_trust_tier_counts": _count([row["selected_trust_tier"] for row in controlled_records]),
        "final_trust_tier_counts": _count([row["selected_trust_tier"] for row in controlled_records]),
        "selected_rag_action_counts": _count([row["selected_rag_action"] for row in controlled_records]),
        "final_rag_action_counts": _count([row["selected_rag_action"] for row in controlled_records]),
        "selected_repair_action_counts": _count([row["selected_repair_action"] for row in controlled_records]),
        "final_repair_action_counts": _count([row["selected_repair_action"] for row in controlled_records]),
        "stage5_rag_include_records": len(rag_includes),
        "trust_changed_records": len(trust_changes),
        "rag_action_changed_records": len(rag_changes),
        "repair_action_changed_records": len(repair_changes),
        "controlled_routing_changed_records": len(rag_changes) + len(repair_changes),
        "unsafe_stage5_rag_include_records": len(unsafe),
        "unsafe_final_rag_include_records": len(unsafe),
        "source_trace_records": len(source_trace),
        "source_trace_policy_A_records": len(source_trace_a),
        "source_trace_final_A_records": len(source_trace_a),
        "part_catalog_records": len(part_catalog),
        "part_catalog_policy_A_records": len(part_catalog_a),
        "part_catalog_final_A_records": len(part_catalog_a),
        "table_candidate_direct_rag_records": len(table_candidate_direct),
        "table_tiles_direct_rag_records": len(table_tiles_direct),
        "table_tile_text_refined_records": len(table_tile_text_refined),
        "table_tile_text_refined_controlled_records": len(table_tile_text_refined_controlled),
        "table_tile_text_refined_derived_context_records": len(table_tile_text_refined_derived),
        "table_tile_text_refined_direct_verified_records": len(table_tile_text_refined_direct_verified),
        "visual_text_controlled_records": len(visual_controlled),
        "table_tile_text_refined_records": len(table_tile_text_refined),
        "table_tile_text_refined_controlled_records": len(table_tile_text_refined_controlled),
        "table_tile_text_refined_final_A_records": len(table_tile_text_refined_a),
        "table_tile_text_refined_final_B_records": len(table_tile_text_refined_b),
        "table_tile_text_refined_final_C_records": len(table_tile_text_refined_c),
        "table_tile_text_refined_derived_context_records": len(table_tile_text_refined_derived),
        "per_layer": dict(sorted(per_layer.items())),
        "policy_controlled_records": len(stage5_controlled),
        "rule_controlled_records": len(stage5_uncontrolled),
        "controlled_records": len(stage5_controlled),
        "stage5_control_records": controlled_records,
        "samples": {
            "controlled_changes": (trust_changes + rag_changes + repair_changes)[: options.max_samples],
            "unsafe_stage5_rag_include": unsafe[: options.max_samples],
            "source_trace_not_A": [row for row in source_trace if row["selected_trust_tier"] != "A"][: options.max_samples],
            "part_catalog_not_A": [row for row in part_catalog if row["selected_trust_tier"] != "A"][: options.max_samples],
        },
        "records_path": str(paths.records),
        "summary_path": str(paths.summary),
        "consensus_records_path": str(paths.consensus_records),
        "confidence_policy_path": str(paths.confidence_policy),
        "routing_mutated": False,
        "recommendation": _recommendation(len(unsafe), len(source_trace_a), len(source_trace), len(visual_controlled), len(table_candidate_direct), len(table_tiles_direct), len(table_tile_text_refined_controlled), len(table_tile_text_refined_direct_verified)),
    }

    graph_nodes, graph_edges = _build_graph(controlled_records)
    result["graph_nodes"] = len(graph_nodes)
    result["graph_edges"] = len(graph_edges)

    _write_jsonl(paths.records, controlled_records)
    _write_json(paths.summary, result)
    _write_json(paths.graph_nodes, graph_nodes)
    _write_json(paths.graph_edges, graph_edges)
    _write_report(paths.report_md, paths.report_html, result)
    if options.open_report:
        try:
            webbrowser.open(paths.report_html.resolve().as_uri())
        except Exception:
            pass
    return result


def _recommendation(unsafe: int, source_a: int, source_total: int, visual_controlled: int, table_candidate_direct: int, table_tiles_direct: int, table_tile_text_controlled: int = 0, table_tile_text_direct_verified: int = 0) -> str:
    if unsafe:
        return "do_not_use_stage5_control_unsafe_rag_include_detected"
    if source_total and source_a < source_total:
        return "do_not_use_stage5_control_source_trace_not_all_A"
    if visual_controlled:
        return "do_not_use_stage5_control_visual_text_enabled_too_early"
    if table_candidate_direct or table_tiles_direct:
        return "do_not_use_stage5_control_routing_artifacts_enter_rag"
    if table_tile_text_direct_verified:
        return "do_not_use_stage5_control_table_tile_text_marked_as_verified_source"
    return "stage5b_safe_for_downstream_controlled_decision_view"


def _build_graph(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, kind: str, **props: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "kind": kind, **props}

    def add_edge(src: str, dst: str, edge_type: str, **props: Any) -> None:
        edges.append({"source": src, "target": dst, "type": edge_type, **props})

    for row in rows:
        page_id = _text(row.get("page_id"))
        record_id = _text(row.get("record_id"))
        layer = _text(row.get("evidence_layer"))
        if page_id:
            page_node = f"page:{page_id}"
            add_node(page_node, "page", page_id=page_id)
        else:
            page_node = "page:unknown"
            add_node(page_node, "page", page_id="unknown")
        decision_node = f"confidence_policy_decision:{record_id or layer}"
        add_node(decision_node, "confidence_policy_decision", evidence_layer=layer, selected_trust_tier=row.get("selected_trust_tier"), selected_rag_action=row.get("selected_rag_action"), stage5_controlled=row.get("stage5_controlled"))
        add_edge(page_node, decision_node, "HAS_CONFIDENCE_POLICY_DECISION", evidence_layer=layer)
        tier_node = f"trait:trust:{layer}:{row.get('selected_trust_tier')}"
        add_node(tier_node, "trait", namespace="trust", evidence_layer=layer, value=row.get("selected_trust_tier"))
        add_edge(decision_node, tier_node, "ASSERTS_POLICY_TRUST")
        rag_node = f"trait:rag:{layer}:{row.get('selected_rag_action')}"
        add_node(rag_node, "trait", namespace="rag", evidence_layer=layer, value=row.get("selected_rag_action"))
        add_edge(decision_node, rag_node, "ASSERTS_POLICY_RAG_ACTION")
    return list(nodes.values()), edges


def _write_report(md_path: Path, html_path: Path, result: Mapping[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# TRACE-Net Layer Confidence Stage 5b Policy Control")
    lines.append("")
    lines.append(f"Status: **{result.get('status')}**")
    lines.append(f"Version: `{result.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "records", "pages", "policy_version", "controlled_layers", "policy_controlled_records", "rule_controlled_records",
        "stage5_rag_include_records", "trust_changed_records", "rag_action_changed_records", "repair_action_changed_records",
        "unsafe_stage5_rag_include_records", "source_trace_policy_A_records", "part_catalog_policy_A_records",
        "table_candidate_direct_rag_records", "table_tiles_direct_rag_records", "visual_text_controlled_records",
        "table_tile_text_refined_controlled_records", "table_tile_text_refined_derived_context_records",
        "table_tile_text_refined_direct_verified_records", "recommendation",
    ):
        lines.append(f"- **{key}**: {result.get(key)}")
    lines.append("")
    lines.append("## Selected trust tiers")
    lines.append("")
    lines.append(f"`{result.get('selected_trust_tier_counts')}`")
    lines.append("")
    lines.append("## Selected RAG actions")
    lines.append("")
    lines.append(f"`{result.get('selected_rag_action_counts')}`")
    lines.append("")
    lines.append("## Per-layer metrics")
    lines.append("")
    lines.append("| Layer | Records | Controlled | Selected tiers | Selected RAG actions | Unsafe includes | Avg confidence |")
    lines.append("|---|---:|---:|---|---|---:|---:|")
    for layer, row in _as_dict(result.get("per_layer")).items():
        row = _as_dict(row)
        lines.append(
            "| " + " | ".join([
                str(layer),
                str(row.get("records", 0)),
                str(row.get("controlled_records", 0)),
                "`" + str(row.get("selected_trust_tier_counts", {})) + "`",
                "`" + str(row.get("selected_rag_action_counts", {})) + "`",
                str(row.get("unsafe_stage5_rag_include_records", 0)),
                str(row.get("avg_usable_confidence", 0.0)),
            ]) + " |"
        )
    lines.append("")
    samples = _as_dict(result.get("samples"))
    lines.append("## Controlled change samples")
    if samples.get("controlled_changes"):
        for row in _as_list(samples.get("controlled_changes"))[:40]:
            row = _as_dict(row)
            lines.append(f"- `{row.get('record_id')}` layer=`{row.get('evidence_layer')}` current=`{row.get('current_trust_tier')}` selected=`{row.get('selected_trust_tier')}` rag=`{row.get('selected_rag_action')}`")
    else:
        lines.append("None.")
    lines.append("")
    lines.append("## Unsafe include samples")
    if samples.get("unsafe_stage5_rag_include"):
        for row in _as_list(samples.get("unsafe_stage5_rag_include"))[:40]:
            row = _as_dict(row)
            lines.append(f"- `{row.get('record_id')}` layer=`{row.get('evidence_layer')}` reasons=`{row.get('unsafe_reasons')}`")
    else:
        lines.append("None.")

    md = "\n".join(lines) + "\n"
    html_doc = "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Stage 5b Control</title><style>body{font-family:Arial,sans-serif;margin:2rem;line-height:1.45}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}code{background:#f4f4f4;padding:1px 4px}</style></head><body><pre>" + html.escape(md) + "</pre></body></html>"
    _write_text(md_path, md)
    _write_text(html_path, html_doc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Layer Confidence Stage 5b controlled decision view.")
    parser.add_argument("--records", type=Path, default=DEFAULT_CONSENSUS_RECORDS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--controlled-layers", default=",".join(DEFAULT_CONTROLLED_LAYERS), help="Comma-separated evidence layers controlled by policy. Default: source_trace,part_catalog,table_tile_text_refined.")
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)

    layers = tuple(layer.strip() for layer in args.controlled_layers.split(",") if layer.strip())
    paths = ConfidenceStage5Paths(consensus_records=args.records, confidence_policy=args.policy, output_dir=args.output_dir)
    result = build_confidence_stage5_control(paths, ConfidenceStage5Options(controlled_layers=layers, open_report=args.open_report))

    print("TRACE-Net Layer Confidence Stage 5b policy control")
    print(f"  Status: {result.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records", "pages", "controlled_layers", "policy_controlled_records", "rule_controlled_records",
        "stage5_rag_include_records", "unsafe_stage5_rag_include_records",
        "source_trace_policy_A_records", "part_catalog_policy_A_records",
        "table_tile_text_refined_controlled_records", "table_tile_text_refined_derived_context_records",
        "table_tile_text_refined_direct_verified_records", "table_candidate_direct_rag_records",
        "visual_text_controlled_records", "recommendation",
    ):
        print(f"    {key}: {result.get(key)}")
    print("  Selected trust tiers:")
    for key, value in _as_dict(result.get("selected_trust_tier_counts")).items():
        print(f"    {key}: {value}")
    print("Files written:")
    print(f"  records: {paths.records}")
    print(f"  summary: {paths.summary}")
    print(f"  report_html: {paths.report_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

# Backwards-compatible function name used by early Stage 5 drafts.
build_confidence_policy_control = build_confidence_stage5_control
