"""TRACE-Net Layer Confidence Stage 3 policy builder.

Stage 1 wrote advisory numeric confidence scores to Evidence Consensus.
Stage 2 compared those score-derived tiers against the current rule tiers.
Stage 3 materializes a layer-specific confidence policy so future code has a
single, measured place to read how confidence should be interpreted per layer.

This module does not change RAG routing by itself. It writes a policy/report
that can later be consumed by Evidence Consensus or retrievers.
"""
from __future__ import annotations

import argparse
import html
import json
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_CONFIDENCE_DIR = Path("local_data/organization/trace_net/confidence")
DEFAULT_STAGE2_EVAL = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage2_eval.json"
DEFAULT_POLICY = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy.json"
DEFAULT_REPORT_MD = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy_report.md"
DEFAULT_REPORT_HTML = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy_report.html"
DEFAULT_QUALITY = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy_quality.json"

POLICY_VERSION = "trace_lc_confidence_policy_v1"

DEFAULT_BASE_WEIGHTS = {
    "source_trace": 0.30,
    "graph_support": 0.25,
    "ocr_support": 0.20,
    "part_catalog": 0.20,
    "extraction_layer": 0.05,
}
DEFAULT_THRESHOLDS = {"A": 0.90, "B": 0.70, "C": 0.45}


@dataclass(frozen=True)
class ConfidencePolicyPaths:
    stage2_eval_path: Path = DEFAULT_STAGE2_EVAL
    output_dir: Path = DEFAULT_CONFIDENCE_DIR
    policy_path: Path | None = None
    report_md_path: Path | None = None
    report_html_path: Path | None = None
    quality_path: Path | None = None

    @property
    def policy(self) -> Path:
        return self.policy_path or (self.output_dir / DEFAULT_POLICY.name)

    @property
    def report_md(self) -> Path:
        return self.report_md_path or (self.output_dir / DEFAULT_REPORT_MD.name)

    @property
    def report_html(self) -> Path:
        return self.report_html_path or (self.output_dir / DEFAULT_REPORT_HTML.name)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / DEFAULT_QUALITY.name)


@dataclass
class ConfidencePolicyOptions:
    open_report: bool = False
    require_stage2: bool = False


@dataclass
class LayerConfidenceRule:
    layer: str
    purpose: str
    policy_role: str
    routing_authority: str
    confidence_use: str
    base_weights: dict[str, float]
    thresholds: dict[str, float]
    max_auto_trust_tier: str
    min_rag_tier: str | None
    hard_blocks: list[str] = field(default_factory=list)
    hard_promotions: list[str] = field(default_factory=list)
    hard_demotions: list[str] = field(default_factory=list)
    required_supports_for_A: list[str] = field(default_factory=list)
    required_supports_for_B: list[str] = field(default_factory=list)
    default_rag_action: str = "exclude_from_rag"
    default_repair_action: str = "human_review"
    notes: list[str] = field(default_factory=list)
    stage2_metrics: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Basic IO helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _layer_metrics(stage2: Mapping[str, Any], layer: str) -> dict[str, Any]:
    per_layer = stage2.get("per_layer")
    if isinstance(per_layer, Mapping):
        return _as_dict(per_layer.get(layer))
    if isinstance(per_layer, list):
        for row in per_layer:
            if isinstance(row, Mapping) and row.get("layer") == layer:
                return dict(row)
    return {}


# ---------------------------------------------------------------------------
# Policy construction
# ---------------------------------------------------------------------------


def _source_trace_rule(metrics: Mapping[str, Any]) -> LayerConfidenceRule:
    return LayerConfidenceRule(
        layer="source_trace",
        purpose="source_truth",
        policy_role="proves_page_source_exists",
        routing_authority="rule_tier_controls_routing_confidence_is_diagnostic",
        confidence_use="calibrate_source_completeness_not_claim_truth",
        base_weights={
            "source_trace": 0.70,
            "graph_support": 0.20,
            "ocr_support": 0.05,
            "part_catalog": 0.00,
            "extraction_layer": 0.05,
        },
        thresholds={"A": 0.75, "B": 0.60, "C": 0.40},
        max_auto_trust_tier="A",
        min_rag_tier="A",
        hard_blocks=["missing_page", "missing_tiff", "missing_source_url", "source_untraceable"],
        hard_promotions=[
            "source_trace.status in source_verified,local_source_verified",
            "page_exists and tiff_exists and source_url_present",
        ],
        hard_demotions=["source_trace.status not in source_verified,local_source_verified,source_link_only"],
        required_supports_for_A=["source_trace_verified", "graph_support_strong", "tiff_file_exists", "source_url_present"],
        default_rag_action="include_as_source_evidence",
        default_repair_action="none",
        notes=[
            "Stage 2 showed all source_trace records were below confidence A under the generic formula.",
            "This layer is not a claim extraction layer, so OCR/catalog absence must not demote source truth.",
        ],
        stage2_metrics=dict(metrics),
    )


def _part_catalog_rule(metrics: Mapping[str, Any]) -> LayerConfidenceRule:
    return LayerConfidenceRule(
        layer="part_catalog",
        purpose="verified_part_evidence",
        policy_role="promotes_catalog_supported_part_mentions",
        routing_authority="rule_tier_controls_until_claim_level_calibration",
        confidence_use="rank_part_evidence_strength_and_review_edge_cases",
        base_weights={
            "source_trace": 0.25,
            "graph_support": 0.20,
            "ocr_support": 0.10,
            "part_catalog": 0.40,
            "extraction_layer": 0.05,
        },
        thresholds={"A": 0.82, "B": 0.66, "C": 0.42},
        max_auto_trust_tier="A",
        min_rag_tier="A",
        hard_blocks=["catalog_conflict", "invalid_part_pattern", "source_untraceable"],
        hard_promotions=["catalog_verified and source_trace_verified", "same_page_part_mention_present"],
        hard_demotions=["unsupported_part_candidate_only", "catalog_conflict"],
        required_supports_for_A=["source_trace_verified", "part_catalog_verified", "graph_support_strong"],
        required_supports_for_B=["valid_part_pattern", "source_trace_verified"],
        default_rag_action="include_as_verified_part_evidence",
        default_repair_action="none",
        notes=[
            "Catalog evidence is allowed to be A when source trace and catalog support agree.",
            "Generic confidence marked catalog records as B because it lacked layer-specific promotions.",
        ],
        stage2_metrics=dict(metrics),
    )


def _table_tile_text_refined_rule(metrics: Mapping[str, Any]) -> LayerConfidenceRule:
    return LayerConfidenceRule(
        layer="table_tile_text_refined",
        purpose="derived_table_text_and_part_evidence",
        policy_role="gates_refined_tile_text_before_rag",
        routing_authority="hybrid_rule_and_confidence_after_more_validation",
        confidence_use="decide_A_B_C_for_refined_table_text",
        base_weights={
            "source_trace": 0.25,
            "graph_support": 0.20,
            "ocr_support": 0.10,
            "part_catalog": 0.35,
            "extraction_layer": 0.10,
        },
        thresholds={"A": 0.82, "B": 0.64, "C": 0.40},
        max_auto_trust_tier="A",
        min_rag_tier="B",
        hard_blocks=["index_label_as_part", "metadata_leakage", "prompt_template_leakage", "source_untraceable"],
        hard_promotions=["catalog_supported_part_numbers_found and source_trace_verified"],
        hard_demotions=["only_index_labels_found", "only_unsupported_part_candidates_found"],
        required_supports_for_A=["catalog_supported_part_number", "source_trace_verified", "graph_support_strong"],
        required_supports_for_B=["catalog_supported_part_number", "source_trace_verified"],
        default_rag_action="include_as_derived_context",
        default_repair_action="run_table_tile_ocr_or_human_review",
        notes=[
            "B tier is appropriate for derived table context even when not canonical source truth.",
            "A tier should require catalog support and source trace; C tier remains review/exclude.",
        ],
        stage2_metrics=dict(metrics),
    )


def _visual_text_rule(metrics: Mapping[str, Any]) -> LayerConfidenceRule:
    return LayerConfidenceRule(
        layer="visual_text",
        purpose="model_derived_visual_context",
        policy_role="keeps_vision_model_output_conservative",
        routing_authority="rule_tier_controls_until_claim_level_review",
        confidence_use="identify_safe_derived_context_and_high_risk_visual_claims",
        base_weights={
            "source_trace": 0.25,
            "graph_support": 0.25,
            "ocr_support": 0.15,
            "part_catalog": 0.10,
            "extraction_layer": 0.25,
        },
        thresholds={"A": 0.92, "B": 0.74, "C": 0.45},
        max_auto_trust_tier="B",
        min_rag_tier="B",
        hard_blocks=["metadata_leakage", "prompt_template_leakage", "refusal_like", "section_bleed_unrepaired"],
        hard_promotions=["low_risk and graph_support_strong and source_trace_verified"],
        hard_demotions=["hallucination_risk", "suspicious_phrase", "unsupported_specific_claim"],
        required_supports_for_A=[],
        required_supports_for_B=["source_trace_verified", "graph_support_not_conflict", "low_or_medium_risk"],
        default_rag_action="include_as_derived_context",
        default_repair_action="ocr_graph_validation_or_human_review",
        notes=[
            "Visual text remains derived context, not canonical source truth.",
            "Stage 2 showed high risk and low average confidence for visual_text.",
        ],
        stage2_metrics=dict(metrics),
    )


def _table_candidate_rule(metrics: Mapping[str, Any]) -> LayerConfidenceRule:
    return LayerConfidenceRule(
        layer="table_candidate",
        purpose="routing_signal",
        policy_role="routes_pages_to_table_crop_tile_or_review",
        routing_authority="route_grouping_controls_operations",
        confidence_use="prioritize_table_candidate_review_not_rag_truth",
        base_weights={
            "source_trace": 0.20,
            "graph_support": 0.35,
            "ocr_support": 0.05,
            "part_catalog": 0.05,
            "extraction_layer": 0.35,
        },
        thresholds={"A": 0.90, "B": 0.66, "C": 0.40},
        max_auto_trust_tier="B",
        min_rag_tier=None,
        hard_blocks=["graph_gate_blocked", "layout_gate_blocked", "figure_without_table_trait"],
        hard_promotions=["passed_graph_gate and passed_layout_gate"],
        hard_demotions=["candidate_review_only", "skip_non_table"],
        required_supports_for_A=[],
        required_supports_for_B=["source_trace_verified", "table_candidate_signal"],
        default_rag_action="exclude_until_table_tiles_exist",
        default_repair_action="run_table_crop_tile",
        notes=[
            "Table candidates are routing artifacts; they should not enter RAG directly.",
            "High confidence here means process priority, not factual confidence.",
        ],
        stage2_metrics=dict(metrics),
    )


def _table_tiles_rule(metrics: Mapping[str, Any]) -> LayerConfidenceRule:
    return LayerConfidenceRule(
        layer="table_tiles",
        purpose="preprocessing_artifact",
        policy_role="proves_table_regions_were_cut_for_extraction",
        routing_authority="route_grouping_controls_operations",
        confidence_use="verify_tiles_exist_before_tile_text_ocr",
        base_weights={
            "source_trace": 0.25,
            "graph_support": 0.25,
            "ocr_support": 0.00,
            "part_catalog": 0.00,
            "extraction_layer": 0.50,
        },
        thresholds={"A": 0.90, "B": 0.65, "C": 0.40},
        max_auto_trust_tier="B",
        min_rag_tier=None,
        hard_blocks=["missing_tile_images", "missing_preprocessed_image", "source_untraceable"],
        hard_promotions=["tile_images_created and source_trace_verified"],
        hard_demotions=["tile_generation_failed"],
        required_supports_for_A=[],
        required_supports_for_B=["source_trace_verified", "tile_images_created"],
        default_rag_action="exclude_until_table_text_exists",
        default_repair_action="run_table_tile_ocr",
        notes=[
            "Table tiles are not text evidence yet; they trigger the next OCR/extraction step.",
            "Stage 2 showed perfect agreement for table_tiles, so this policy preserves current behavior.",
        ],
        stage2_metrics=dict(metrics),
    )


def build_layer_rules(stage2: Mapping[str, Any]) -> dict[str, LayerConfidenceRule]:
    return {
        "source_trace": _source_trace_rule(_layer_metrics(stage2, "source_trace")),
        "part_catalog": _part_catalog_rule(_layer_metrics(stage2, "part_catalog")),
        "table_tile_text_refined": _table_tile_text_refined_rule(_layer_metrics(stage2, "table_tile_text_refined")),
        "visual_text": _visual_text_rule(_layer_metrics(stage2, "visual_text")),
        "table_candidate": _table_candidate_rule(_layer_metrics(stage2, "table_candidate")),
        "table_tiles": _table_tiles_rule(_layer_metrics(stage2, "table_tiles")),
    }


def build_confidence_policy(paths: ConfidencePolicyPaths, options: ConfidencePolicyOptions | None = None) -> dict[str, Any]:
    options = options or ConfidencePolicyOptions()
    stage2 = _read_json(paths.stage2_eval_path, {})
    stage2_present = isinstance(stage2, Mapping) and bool(stage2)
    if options.require_stage2 and not stage2_present:
        raise FileNotFoundError(f"Stage 2 evaluation report is required but missing: {paths.stage2_eval_path}")
    stage2 = _as_dict(stage2)

    rules = build_layer_rules(stage2)
    stage2_summary = {
        "stage2_present": stage2_present,
        "stage2_eval_path": str(paths.stage2_eval_path),
        "agreement_rate": _num(stage2.get("agreement_rate")),
        "within_one_tier_rate": _num(stage2.get("within_one_tier_rate")),
        "disagreement_records": _int(stage2.get("disagreement_records")),
        "source_trace_confidence_below_A_records": _int(stage2.get("source_trace_confidence_below_A_records")),
        "rule_excludes_confidence_high_records": _int(stage2.get("rule_excludes_confidence_high_records")),
        "rule_includes_confidence_low_records": _int(stage2.get("rule_includes_confidence_low_records")),
        "avg_usable_confidence": _num(stage2.get("avg_usable_confidence")),
    }

    global_hard_safety_gates = [
        "source_untraceable_records_must_not_enter_rag",
        "metadata_leakage_records_must_not_enter_rag",
        "prompt_template_leakage_records_must_not_enter_rag",
        "refusal_like_records_must_not_enter_rag",
        "D_tier_records_must_not_enter_rag",
        "community_algorithms_must_not_prove_source_truth",
    ]
    default_policy = {
        "source_truth_layers": ["source_trace"],
        "verified_fact_layers": ["part_catalog"],
        "derived_context_layers": ["visual_text", "table_tile_text_refined"],
        "routing_only_layers": ["table_candidate", "table_tiles"],
        "rag_safe_actions": ["include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context"],
        "rag_blocked_actions": ["exclude_from_rag", "exclude_until_table_text_exists", "exclude_until_table_tiles_exist"],
    }

    policy = {
        "status": "OK",
        "version": POLICY_VERSION,
        "description": "Layer-specific TRACE-LC confidence policy generated from Stage 2 evaluation.",
        "stage2_summary": stage2_summary,
        "base_formula": {
            "support_score": "sum(weight_i * layer_score_i)",
            "usable_confidence": "support_score * (1 - risk_score)",
            "note": "Layer-specific hard gates and promotions override the generic formula for routing decisions.",
        },
        "global_default_weights": dict(DEFAULT_BASE_WEIGHTS),
        "global_default_thresholds": dict(DEFAULT_THRESHOLDS),
        "global_hard_safety_gates": global_hard_safety_gates,
        "default_policy": default_policy,
        "layers": {key: rule.to_json() for key, rule in rules.items()},
        "recommended_next_step": "use_policy_for_advisory_layer_specific_tier_eval_before_routing",
    }

    _write_json(paths.policy, policy)
    _write_report(paths.report_md, paths.report_html, policy)
    if options.open_report:
        try:
            webbrowser.open(paths.report_html.resolve().as_uri())
        except Exception:
            pass
    return {"policy": policy, "paths": {"policy": str(paths.policy), "report_md": str(paths.report_md), "report_html": str(paths.report_html)}}


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _write_report(md_path: Path, html_path: Path, policy: Mapping[str, Any]) -> None:
    layers = _as_dict(policy.get("layers"))
    stage2 = _as_dict(policy.get("stage2_summary"))
    lines: list[str] = []
    lines.append("# TRACE-Net Layer Confidence Stage 3 Policy")
    lines.append("")
    lines.append(f"Status: **{policy.get('status', 'unknown')}**")
    lines.append(f"Version: `{policy.get('version', '')}`")
    lines.append("")
    lines.append("## Stage 2 signal")
    lines.append("")
    for key in (
        "agreement_rate",
        "within_one_tier_rate",
        "disagreement_records",
        "source_trace_confidence_below_A_records",
        "rule_excludes_confidence_high_records",
        "rule_includes_confidence_low_records",
        "avg_usable_confidence",
    ):
        lines.append(f"- **{key}**: {stage2.get(key)}")
    lines.append("")
    lines.append("## Policy summary")
    lines.append("")
    lines.append("| Layer | Purpose | Routing authority | Max auto tier | Min RAG tier | Default RAG action |")
    lines.append("|---|---|---|---|---|---|")
    for name, raw in sorted(layers.items()):
        layer = _as_dict(raw)
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    _text(layer.get("purpose")),
                    _text(layer.get("routing_authority")),
                    _text(layer.get("max_auto_trust_tier")),
                    _text(layer.get("min_rag_tier"), "none"),
                    _text(layer.get("default_rag_action")),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Layer details")
    lines.append("")
    for name, raw in sorted(layers.items()):
        layer = _as_dict(raw)
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- purpose: `{layer.get('purpose')}`")
        lines.append(f"- policy role: `{layer.get('policy_role')}`")
        lines.append(f"- confidence use: `{layer.get('confidence_use')}`")
        lines.append(f"- thresholds: `{layer.get('thresholds')}`")
        lines.append(f"- weights: `{layer.get('base_weights')}`")
        blocks = layer.get("hard_blocks") or []
        if blocks:
            lines.append(f"- hard blocks: `{blocks}`")
        promotions = layer.get("hard_promotions") or []
        if promotions:
            lines.append(f"- hard promotions: `{promotions}`")
        notes = layer.get("notes") or []
        for note in notes:
            lines.append(f"- note: {note}")
        lines.append("")
    report = "\n".join(lines)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report + "\n", encoding="utf-8")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line else "" for line in lines)
    # Keep HTML simple and local-file safe.
    html_doc = f"""<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<title>TRACE-Net Layer Confidence Stage 3 Policy</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; line-height: 1.45; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; }}
code {{ background: #f3f3f3; padding: 1px 4px; }}
pre {{ background: #f7f7f7; padding: 12px; overflow-x: auto; }}
</style>
</head>
<body>
<pre>{html.escape(report)}</pre>
</body>
</html>
"""
    html_path.write_text(html_doc, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_result(result: Mapping[str, Any]) -> None:
    policy = _as_dict(result.get("policy"))
    stage2 = _as_dict(policy.get("stage2_summary"))
    layers = _as_dict(policy.get("layers"))
    print("TRACE-Net Layer Confidence Stage 3 policy")
    print(f"  Status: {policy.get('status')}")
    print(f"  Version: {policy.get('version')}")
    print("  Stage 2:")
    print(f"    agreement_rate: {stage2.get('agreement_rate')}")
    print(f"    within_one_tier_rate: {stage2.get('within_one_tier_rate')}")
    print(f"    disagreement_records: {stage2.get('disagreement_records')}")
    print(f"    source_trace_confidence_below_A_records: {stage2.get('source_trace_confidence_below_A_records')}")
    print("  Layer policy:")
    for name in sorted(layers):
        layer = _as_dict(layers[name])
        print(
            f"    {name}: purpose={layer.get('purpose')} max_auto={layer.get('max_auto_trust_tier')} "
            f"min_rag={layer.get('min_rag_tier')} default_rag={layer.get('default_rag_action')}"
        )
    paths = _as_dict(result.get("paths"))
    print("Files written:")
    for key in ("policy", "report_md", "report_html"):
        if paths.get(key):
            print(f"  {key}: {paths[key]}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net layer-specific confidence policy")
    parser.add_argument("--stage2-eval", type=Path, default=DEFAULT_STAGE2_EVAL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CONFIDENCE_DIR)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--report-md", type=Path, default=None)
    parser.add_argument("--report-html", type=Path, default=None)
    parser.add_argument("--require-stage2", action="store_true")
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)

    paths = ConfidencePolicyPaths(
        stage2_eval_path=args.stage2_eval,
        output_dir=args.output_dir,
        policy_path=args.policy,
        report_md_path=args.report_md,
        report_html_path=args.report_html,
    )
    options = ConfidencePolicyOptions(open_report=args.open_report, require_stage2=args.require_stage2)
    try:
        result = build_confidence_policy(paths, options)
    except FileNotFoundError as exc:
        print(f"TRACE-Net Layer Confidence Stage 3 policy\n  Status: FAIL\n  Error: {exc}")
        return 1
    _print_result(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
