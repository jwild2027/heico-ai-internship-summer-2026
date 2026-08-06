"""TRACE-Net Layer Confidence Stage 4 policy simulation.

Stage 3 writes a layer-specific confidence policy. Stage 4 safely simulates
what would happen if that policy recommended trust tiers, RAG actions, and
repair actions for Evidence Consensus records.

This module is intentionally read-only with respect to Evidence Consensus. It
writes a simulation report and does not change routing, trust traits, RAG
inputs, or graph artifacts.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_CONSENSUS_DIR = DEFAULT_TRACE_NET_DIR / "evidence_consensus"
DEFAULT_CONFIDENCE_DIR = DEFAULT_TRACE_NET_DIR / "confidence"
DEFAULT_CONSENSUS_RECORDS = DEFAULT_CONSENSUS_DIR / "evidence_consensus_records.jsonl"
DEFAULT_POLICY = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy.json"
DEFAULT_OUTPUT_JSON = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage4_policy_simulation.json"
DEFAULT_REPORT_MD = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage4_policy_simulation.md"
DEFAULT_REPORT_HTML = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage4_policy_simulation.html"

SIMULATION_VERSION = "trace_lc_stage4_policy_simulation_v1"
TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}
TIERS = ["A", "B", "C", "D"]
SOURCE_OK = {"source_verified", "local_source_verified", "source_link_only"}
SOURCE_STRONG = {"source_verified", "local_source_verified"}
RAG_INCLUDE_PREFIX = "include_"


@dataclass(frozen=True)
class ConfidenceStage4Paths:
    consensus_records: Path = DEFAULT_CONSENSUS_RECORDS
    confidence_policy: Path = DEFAULT_POLICY
    output_dir: Path = DEFAULT_CONFIDENCE_DIR
    eval_json_path: Path | None = None
    report_md_path: Path | None = None
    report_html_path: Path | None = None

    @property
    def eval_json(self) -> Path:
        return self.eval_json_path or (self.output_dir / DEFAULT_OUTPUT_JSON.name)

    @property
    def report_md(self) -> Path:
        return self.report_md_path or (self.output_dir / DEFAULT_REPORT_MD.name)

    @property
    def report_html(self) -> Path:
        return self.report_html_path or (self.output_dir / DEFAULT_REPORT_HTML.name)


@dataclass
class ConfidenceStage4Options:
    open_report: bool = False
    max_samples: int = 40


# ---------------------------------------------------------------------------
# IO/helpers
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
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


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


def _cap_tier(tier: str, max_tier: str | None) -> str:
    tier = _tier(tier)
    max_tier = _tier(max_tier or "A")
    if _rank(tier) > _rank(max_tier):
        return max_tier
    return tier


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _status(record: Mapping[str, Any], key: str) -> str:
    return _text(_as_dict(record.get(key)).get("status")).lower()


def _score(record: Mapping[str, Any], key: str) -> float:
    return _num(_as_dict(record.get(key)).get("score"), 0.0)


def _confidence_scores(record: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(record.get("confidence_scores"))


def _record_id(record: Mapping[str, Any]) -> str:
    return _text(record.get("record_id") or record.get("evidence_id") or f"{record.get('page_id', 'unknown')}:{record.get('evidence_layer', 'unknown')}")


def _rag_includes(action: str) -> bool:
    return _text(action).startswith(RAG_INCLUDE_PREFIX)


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


def _has_flag(record: Mapping[str, Any], flag: str) -> bool:
    flag_l = flag.lower()
    props = _as_dict(record.get("properties"))
    if props.get(flag) is True or props.get(flag_l) is True:
        return True
    # Some records only expose risk through reasons/status text.
    haystack_parts: list[str] = []
    for key in ("reasons", "review_flags", "traits"):
        value = record.get(key)
        if isinstance(value, list):
            haystack_parts.extend(str(v) for v in value)
    for key in ("hallucination_risk", "part_catalog_support", "graph_support", "source_trace"):
        value = record.get(key)
        if isinstance(value, Mapping):
            haystack_parts.extend(str(v) for v in value.values())
    haystack = " ".join(haystack_parts).lower()
    return flag_l in haystack


def _hard_blocked(record: Mapping[str, Any], rule: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not _source_ok(record):
        reasons.append("source_untraceable")
    blocks = [str(item) for item in _as_list(rule.get("hard_blocks"))]
    for block in blocks:
        block_l = block.lower()
        if block_l in {"source_untraceable", "missing_page", "missing_tiff", "missing_source_url"}:
            if not _source_ok(record):
                reasons.append(block)
        elif block_l in {"metadata_leakage", "prompt_template_leakage", "refusal_like", "section_bleed_unrepaired", "index_label_as_part"}:
            if _has_flag(record, block_l):
                reasons.append(block)
        elif block_l == "catalog_conflict":
            if "conflict" in _status(record, "part_catalog_support"):
                reasons.append(block)
        elif block_l == "invalid_part_pattern":
            if _has_flag(record, "invalid_part_pattern"):
                reasons.append(block)
        elif block_l in {"missing_tile_images", "missing_preprocessed_image"}:
            if _has_flag(record, block_l):
                reasons.append(block)
        elif block_l in {"graph_gate_blocked", "layout_gate_blocked", "figure_without_table_trait"}:
            if _has_flag(record, block_l):
                reasons.append(block)
    # Stage 1 hard gates should remain blocking if they are present.
    scores = _confidence_scores(record)
    if scores.get("hard_gate_blocked") is True:
        reasons.extend(str(x) for x in _as_list(scores.get("hard_gate_reasons")) if str(x))
    return bool(reasons), sorted(set(reasons))


def _tier_from_score(record: Mapping[str, Any], rule: Mapping[str, Any]) -> str:
    scores = _confidence_scores(record)
    usable = _num(scores.get("usable_confidence"), 0.0)
    thresholds = _as_dict(rule.get("thresholds"))
    a = _num(thresholds.get("A"), 0.90)
    b = _num(thresholds.get("B"), 0.70)
    c = _num(thresholds.get("C"), 0.45)
    if usable >= a:
        return "A"
    if usable >= b:
        return "B"
    if usable >= c:
        return "C"
    return "D"


def _policy_tier(record: Mapping[str, Any], rule: Mapping[str, Any]) -> tuple[str, list[str]]:
    layer = _text(record.get("evidence_layer"), "unknown")
    current = _tier(record.get("trust_tier"))
    scored = _tier_from_score(record, rule)
    max_tier = _text(rule.get("max_auto_trust_tier"), "A")
    tier = _cap_tier(scored, max_tier)
    reasons: list[str] = [f"score_tier={scored}", f"max_auto_tier={max_tier}"]

    blocked, block_reasons = _hard_blocked(record, rule)
    if blocked:
        return "D", ["hard_blocked"] + block_reasons

    if layer == "source_trace":
        if _source_strong(record) and _graph_strong(record):
            return "A", ["source_trace_verified", "graph_support_strong", "source_truth_layer"]
        if _source_ok(record):
            return max(tier, "B", key=_rank), reasons + ["source_trace_ok"]
        return "D", reasons + ["source_trace_not_ok"]

    if layer == "part_catalog":
        if _source_ok(record) and _catalog_supported(record) and _graph_strong(record):
            return "A", ["source_trace_verified", "catalog_supported", "graph_support_strong"]
        if _source_ok(record) and _catalog_supported(record):
            return max(tier, "B", key=_rank), reasons + ["catalog_supported"]
        return min(tier, "C", key=_rank), reasons + ["no_catalog_support"]

    if layer == "table_candidate":
        # Routing signal only: never direct RAG evidence, and never above B.
        if _source_ok(record) and _graph_strong(record):
            return max(_cap_tier(tier, "B"), "C", key=_rank), reasons + ["routing_signal_only"]
        return "C", reasons + ["routing_signal_review"]

    if layer == "table_tiles":
        if _source_ok(record):
            return max(_cap_tier(tier, "B"), "B", key=_rank), reasons + ["preprocessing_artifact_tiles_exist"]
        return "D", reasons + ["tiles_untraceable"]

    if layer == "table_tile_text_refined":
        if _source_ok(record) and _catalog_supported(record):
            # Do not force A for all refined tile text: A is possible, B is safe default.
            return max(_cap_tier(tier, "A"), "B", key=_rank), reasons + ["catalog_supported_part_numbers_found"]
        if _source_ok(record):
            return min(max(tier, "C", key=_rank), "C", key=_rank), reasons + ["refined_text_without_catalog_support"]
        return "D", reasons + ["refined_text_untraceable"]

    if layer == "visual_text":
        # Visual model evidence is conservative: max B unless claim-level review exists.
        if _source_ok(record) and _graph_strong(record) and _status(record, "hallucination_risk") in {"low_risk", "medium_risk", "not_applicable"}:
            return max(_cap_tier(tier, "B"), "C", key=_rank), reasons + ["model_derived_context"]
        return min(tier, "C", key=_rank), reasons + ["visual_review_needed"]

    return tier, reasons


def _policy_rag_action(record: Mapping[str, Any], rule: Mapping[str, Any], tier: str) -> str:
    layer = _text(record.get("evidence_layer"), "unknown")
    if tier == "D":
        return "exclude_from_rag"
    if layer == "source_trace":
        return "include_as_source_evidence" if tier == "A" else "exclude_from_rag"
    if layer == "part_catalog":
        return "include_as_verified_part_evidence" if tier == "A" else "exclude_from_rag"
    if layer == "table_candidate":
        return "exclude_until_table_tiles_exist"
    if layer == "table_tiles":
        return "exclude_until_table_text_exists"
    if layer == "table_tile_text_refined":
        return "include_as_derived_context" if _rank(tier) >= _rank("B") else "exclude_from_rag"
    if layer == "visual_text":
        return "include_as_derived_context" if _rank(tier) >= _rank("B") else "exclude_from_rag"
    # Fall back to the layer default only if safe.
    default = _text(rule.get("default_rag_action"), "exclude_from_rag")
    if default.startswith("include") and _rank(tier) < _rank(_text(rule.get("min_rag_tier") or "A")):
        return "exclude_from_rag"
    return default


def _policy_repair_action(record: Mapping[str, Any], rule: Mapping[str, Any], tier: str, rag_action: str) -> str:
    layer = _text(record.get("evidence_layer"), "unknown")
    if rag_action.startswith("include") and layer in {"source_trace", "part_catalog"}:
        return "none"
    if layer == "table_candidate":
        return "run_table_crop_tile"
    if layer == "table_tiles":
        return "run_table_tile_ocr"
    if layer == "table_tile_text_refined":
        return "none" if rag_action.startswith("include") else "run_table_tile_ocr_or_human_review"
    if layer == "visual_text":
        return "none" if rag_action.startswith("include") else "ocr_graph_validation_or_human_review"
    if tier == "D":
        return "human_review"
    return _text(rule.get("default_repair_action"), "human_review")


def _unsafe_policy_include(record: Mapping[str, Any], tier: str, rag_action: str, rule: Mapping[str, Any]) -> bool:
    if not rag_action.startswith("include"):
        return False
    if tier == "D":
        return True
    blocked, _ = _hard_blocked(record, rule)
    if blocked:
        return True
    if not _source_ok(record):
        return True
    layer = _text(record.get("evidence_layer"))
    if layer == "table_candidate":
        return True
    return False


def _sim_record(record: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    layer = _text(record.get("evidence_layer"), "unknown")
    rule = _as_dict(_as_dict(policy.get("layers")).get(layer))
    current_tier = _tier(record.get("trust_tier"))
    current_rag = _text(record.get("rag_action"), "")
    current_repair = _text(record.get("repair_action"), "")
    if not rule:
        policy_tier = current_tier
        reasons = ["no_layer_policy_found"]
        policy_rag = current_rag or "exclude_from_rag"
        policy_repair = current_repair or "human_review"
    else:
        policy_tier, reasons = _policy_tier(record, rule)
        policy_rag = _policy_rag_action(record, rule, policy_tier)
        policy_repair = _policy_repair_action(record, rule, policy_tier, policy_rag)

    confidence = _confidence_scores(record)
    unsafe = _unsafe_policy_include(record, policy_tier, policy_rag, rule)
    return {
        "record_id": _record_id(record),
        "page_id": _text(record.get("page_id")),
        "evidence_layer": layer,
        "current_trust_tier": current_tier,
        "policy_trust_tier": policy_tier,
        "current_rag_action": current_rag,
        "policy_rag_action": policy_rag,
        "current_repair_action": current_repair,
        "policy_repair_action": policy_repair,
        "confidence_tier": _tier(confidence.get("confidence_tier")),
        "usable_confidence": round(_num(confidence.get("usable_confidence")), 6),
        "support_score": round(_num(confidence.get("support_score")), 6),
        "risk_score": round(_num(confidence.get("risk_score")), 6),
        "source_trace_status": _status(record, "source_trace"),
        "graph_support_status": _status(record, "graph_support"),
        "part_catalog_status": _status(record, "part_catalog_support"),
        "hallucination_risk_status": _status(record, "hallucination_risk"),
        "trust_changed": current_tier != policy_tier,
        "rag_action_changed": bool(current_rag) and current_rag != policy_rag,
        "repair_action_changed": bool(current_repair) and current_repair != policy_repair,
        "unsafe_policy_rag_include": unsafe,
        "policy_reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Main evaluation/report
# ---------------------------------------------------------------------------


def simulate_confidence_policy(paths: ConfidenceStage4Paths, options: ConfidenceStage4Options | None = None) -> dict[str, Any]:
    options = options or ConfidenceStage4Options()
    records = _read_jsonl(paths.consensus_records)
    policy = _as_dict(_read_json(paths.confidence_policy, {}))
    layer_rules = _as_dict(policy.get("layers"))

    simulated = [_sim_record(record, policy) for record in records]
    total = len(simulated)
    pages = sorted({row["page_id"] for row in simulated if row.get("page_id")})

    trust_changes = [row for row in simulated if row["trust_changed"]]
    rag_changes = [row for row in simulated if row["rag_action_changed"]]
    repair_changes = [row for row in simulated if row["repair_action_changed"]]
    unsafe = [row for row in simulated if row["unsafe_policy_rag_include"]]
    table_candidate_direct = [row for row in simulated if row["evidence_layer"] == "table_candidate" and row["policy_rag_action"].startswith("include")]
    visual_above_b = [row for row in simulated if row["evidence_layer"] == "visual_text" and _rank(row["policy_trust_tier"]) > _rank("B")]
    source_trace_a = [row for row in simulated if row["evidence_layer"] == "source_trace" and row["policy_trust_tier"] == "A"]
    source_trace_records = [row for row in simulated if row["evidence_layer"] == "source_trace"]
    policy_includes = [row for row in simulated if row["policy_rag_action"].startswith("include")]

    per_layer: dict[str, dict[str, Any]] = {}
    for row in simulated:
        layer = row["evidence_layer"]
        bucket = per_layer.setdefault(layer, {
            "records": 0,
            "current_trust_tier_counts": {},
            "policy_trust_tier_counts": {},
            "current_rag_action_counts": {},
            "policy_rag_action_counts": {},
            "trust_changed_records": 0,
            "rag_action_changed_records": 0,
            "repair_action_changed_records": 0,
            "unsafe_policy_rag_include_records": 0,
            "avg_usable_values": [],
        })
        bucket["records"] += 1
        bucket["current_trust_tier_counts"][row["current_trust_tier"]] = bucket["current_trust_tier_counts"].get(row["current_trust_tier"], 0) + 1
        bucket["policy_trust_tier_counts"][row["policy_trust_tier"]] = bucket["policy_trust_tier_counts"].get(row["policy_trust_tier"], 0) + 1
        bucket["current_rag_action_counts"][row["current_rag_action"]] = bucket["current_rag_action_counts"].get(row["current_rag_action"], 0) + 1
        bucket["policy_rag_action_counts"][row["policy_rag_action"]] = bucket["policy_rag_action_counts"].get(row["policy_rag_action"], 0) + 1
        bucket["trust_changed_records"] += int(row["trust_changed"])
        bucket["rag_action_changed_records"] += int(row["rag_action_changed"])
        bucket["repair_action_changed_records"] += int(row["repair_action_changed"])
        bucket["unsafe_policy_rag_include_records"] += int(row["unsafe_policy_rag_include"])
        bucket["avg_usable_values"].append(row["usable_confidence"])

    for layer, bucket in per_layer.items():
        values = bucket.pop("avg_usable_values")
        bucket["avg_usable_confidence"] = round(sum(values) / len(values), 6) if values else 0.0
        for key in ("current_trust_tier_counts", "policy_trust_tier_counts", "current_rag_action_counts", "policy_rag_action_counts"):
            bucket[key] = dict(sorted(bucket[key].items()))

    result = {
        "status": "OK" if records and policy else "FAIL",
        "version": SIMULATION_VERSION,
        "created_at": _utc_now(),
        "records": total,
        "pages": len(pages),
        "policy_present": bool(policy),
        "policy_version": policy.get("version"),
        "policy_layers": len(layer_rules),
        "current_trust_tier_counts": _count([row["current_trust_tier"] for row in simulated]),
        "policy_trust_tier_counts": _count([row["policy_trust_tier"] for row in simulated]),
        "current_rag_action_counts": _count([row["current_rag_action"] for row in simulated]),
        "policy_rag_action_counts": _count([row["policy_rag_action"] for row in simulated]),
        "policy_repair_action_counts": _count([row["policy_repair_action"] for row in simulated]),
        "policy_rag_include_records": len(policy_includes),
        "trust_changed_records": len(trust_changes),
        "rag_action_changed_records": len(rag_changes),
        "repair_action_changed_records": len(repair_changes),
        "unsafe_policy_rag_include_records": len(unsafe),
        "source_trace_records": len(source_trace_records),
        "source_trace_policy_A_records": len(source_trace_a),
        "table_candidate_direct_rag_records": len(table_candidate_direct),
        "visual_text_above_B_records": len(visual_above_b),
        "per_layer": dict(sorted(per_layer.items())),
        "samples": {
            "trust_changes": trust_changes[: options.max_samples],
            "rag_action_changes": rag_changes[: options.max_samples],
            "unsafe_policy_rag_include": unsafe[: options.max_samples],
            "source_trace_not_A": [row for row in simulated if row["evidence_layer"] == "source_trace" and row["policy_trust_tier"] != "A"][: options.max_samples],
            "table_candidate_direct_rag": table_candidate_direct[: options.max_samples],
            "visual_text_above_B": visual_above_b[: options.max_samples],
        },
        "records_path": str(paths.consensus_records),
        "policy_path": str(paths.confidence_policy),
        "recommended_next_step": "review_policy_simulation_then_select_low_risk_layers_for_stage5_control",
    }

    _write_json(paths.eval_json, result)
    _write_report(paths.report_md, paths.report_html, result)
    if options.open_report:
        try:
            webbrowser.open(paths.report_html.resolve().as_uri())
        except Exception:
            pass
    return result


def _write_report(md_path: Path, html_path: Path, result: Mapping[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# TRACE-Net Layer Confidence Stage 4 Policy Simulation")
    lines.append("")
    lines.append(f"Status: **{result.get('status')}**")
    lines.append(f"Version: `{result.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    summary_keys = [
        "records",
        "pages",
        "policy_version",
        "policy_layers",
        "policy_rag_include_records",
        "trust_changed_records",
        "rag_action_changed_records",
        "repair_action_changed_records",
        "unsafe_policy_rag_include_records",
        "source_trace_policy_A_records",
        "table_candidate_direct_rag_records",
        "visual_text_above_B_records",
    ]
    for key in summary_keys:
        lines.append(f"- **{key}**: {result.get(key)}")
    lines.append("")
    lines.append("## Current vs policy trust tiers")
    lines.append("")
    lines.append(f"Current: `{result.get('current_trust_tier_counts')}`")
    lines.append(f"Policy: `{result.get('policy_trust_tier_counts')}`")
    lines.append("")
    lines.append("## Current vs policy RAG actions")
    lines.append("")
    lines.append(f"Current: `{result.get('current_rag_action_counts')}`")
    lines.append(f"Policy: `{result.get('policy_rag_action_counts')}`")
    lines.append("")
    lines.append("## Per-layer metrics")
    lines.append("")
    lines.append("| Layer | Records | Current tiers | Policy tiers | Trust changes | RAG changes | Unsafe includes | Avg confidence |")
    lines.append("|---|---:|---|---|---:|---:|---:|---:|")
    for layer, row in _as_dict(result.get("per_layer")).items():
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join([
                str(layer),
                str(row.get("records", 0)),
                "`" + str(row.get("current_trust_tier_counts", {})) + "`",
                "`" + str(row.get("policy_trust_tier_counts", {})) + "`",
                str(row.get("trust_changed_records", 0)),
                str(row.get("rag_action_changed_records", 0)),
                str(row.get("unsafe_policy_rag_include_records", 0)),
                str(row.get("avg_usable_confidence", 0.0)),
            ])
            + " |"
        )
    lines.append("")
    lines.append("## Sample trust changes")
    lines.append("")
    for row in _as_list(_as_dict(result.get("samples")).get("trust_changes")):
        lines.append(
            f"- `{row.get('record_id')}` layer=`{row.get('evidence_layer')}` "
            f"current=`{row.get('current_trust_tier')}` policy=`{row.get('policy_trust_tier')}` "
            f"usable=`{row.get('usable_confidence')}` rag=`{row.get('policy_rag_action')}`"
        )
    lines.append("")
    lines.append("## Unsafe policy includes")
    lines.append("")
    unsafe = _as_list(_as_dict(result.get("samples")).get("unsafe_policy_rag_include"))
    if not unsafe:
        lines.append("None.")
    else:
        for row in unsafe:
            lines.append(f"- `{row.get('record_id')}` layer=`{row.get('evidence_layer')}` tier=`{row.get('policy_trust_tier')}` rag=`{row.get('policy_rag_action')}`")
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append(str(result.get("recommended_next_step")))

    md = "\n".join(lines) + "\n"
    _write_text(md_path, md)
    body = html.escape(md)
    html_doc = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>TRACE-Net Stage 4 Policy Simulation</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;line-height:1.45}}pre{{white-space:pre-wrap;background:#f7f7f7;padding:16px;border-radius:8px}}code{{background:#f2f2f2;padding:2px 4px;border-radius:4px}}</style></head>
<body><pre>{body}</pre></body></html>
"""
    _write_text(html_path, html_doc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_result(result: Mapping[str, Any], paths: ConfidenceStage4Paths) -> None:
    print("TRACE-Net Layer Confidence Stage 4 policy simulation")
    print(f"  Status: {result.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "pages",
        "policy_version",
        "policy_rag_include_records",
        "trust_changed_records",
        "rag_action_changed_records",
        "repair_action_changed_records",
        "unsafe_policy_rag_include_records",
        "source_trace_policy_A_records",
        "table_candidate_direct_rag_records",
        "visual_text_above_B_records",
    ):
        print(f"    {key}: {result.get(key)}")
    print("  Policy trust tiers:")
    for key, value in _as_dict(result.get("policy_trust_tier_counts")).items():
        print(f"    {key}: {value}")
    print("  Policy RAG actions:")
    for key, value in _as_dict(result.get("policy_rag_action_counts")).items():
        print(f"    {key}: {value}")
    print("Files written:")
    print(f"  eval_json: {paths.eval_json}")
    print(f"  report_md: {paths.report_md}")
    print(f"  report_html: {paths.report_html}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate TRACE-Net Stage 3 confidence policy on Evidence Consensus records")
    parser.add_argument("--records", type=Path, default=DEFAULT_CONSENSUS_RECORDS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CONFIDENCE_DIR)
    parser.add_argument("--max-samples", type=int, default=40)
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)

    paths = ConfidenceStage4Paths(consensus_records=args.records, confidence_policy=args.policy, output_dir=args.output_dir)
    options = ConfidenceStage4Options(open_report=args.open_report, max_samples=args.max_samples)
    result = simulate_confidence_policy(paths, options)
    _print_result(result, paths)
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
