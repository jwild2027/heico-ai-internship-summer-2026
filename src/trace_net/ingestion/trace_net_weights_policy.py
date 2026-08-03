"""TRACE-Net weights policy v1.

This module writes a versioned policy/config artifact for the first official
TRACE-Net weight recommendations. It does not mutate Evidence Consensus,
search ranking, feedback ranking, RAG eligibility, or source truth. It simply
stores the layer-specific confidence weights, risk scores, retrieval ranking
weights, and feedback adjustment weights in a quality-gated form so downstream
modules can opt in deliberately.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

WEIGHTS_POLICY_VERSION = "trace_net_weights_policy_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/weights")

WEIGHT_KEYS = [
    "source_trace",
    "graph_support",
    "ocr_support",
    "part_catalog",
    "extraction_layer",
]

REQUIRED_LAYERS = [
    "source_trace",
    "source_text_evidence",
    "part_catalog",
    "table_tile_text_refined",
    "visual_text",
    "table_candidate",
    "table_tiles",
]

REQUIRED_GLOBAL_SAFETY_GATES = [
    "source_untraceable_records_must_not_enter_rag",
    "metadata_leakage_records_must_not_enter_rag",
    "prompt_template_leakage_records_must_not_enter_rag",
    "refusal_like_records_must_not_enter_rag",
    "D_tier_records_must_not_enter_rag",
    "routing_only_layers_must_not_enter_rag_directly",
    "feedback_must_not_mutate_source_truth",
    "context_warning_feedback_must_not_adjust_ranking",
]


@dataclass(frozen=True)
class WeightPolicyOptions:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    open_result: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_relative(path: Path) -> str:
    return str(path).replace("/", os.sep)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def default_weight_policy() -> Dict[str, Any]:
    """Return the first official TRACE-Net weights policy.

    The values here are intentionally conservative. They encode three separate
    concerns rather than one giant score:
      * evidence confidence weights
      * search/group retrieval weights
      * validated feedback adjustment weights
    """
    return {
        "status": "OK",
        "version": WEIGHTS_POLICY_VERSION,
        "created_at": _utc_now(),
        "mode": "advisory_config_only",
        "purpose": "versioned_weight_policy_for_trace_net_confidence_retrieval_and_feedback",
        "notes": [
            "This policy does not apply weights to production ranking by itself.",
            "Downstream modules must opt in explicitly and pass quality gates.",
            "Confidence, retrieval ranking, and feedback adjustment weights are intentionally separate.",
            "Only TRACE-Net RAG-eligible candidates should be searched, embedded, or ranked for answers.",
        ],
        "confidence": {
            "formula": "support_score = weighted(source_trace, graph_support, ocr_support, part_catalog, extraction_layer); usable_confidence = support_score * (1 - risk_score)",
            "weight_keys": list(WEIGHT_KEYS),
            "layers": {
                "source_trace": {
                    "purpose": "source_truth",
                    "max_auto_tier": "A",
                    "min_rag_tier": "A",
                    "default_rag_action": "include_as_source_evidence",
                    "weights": {
                        "source_trace": 0.70,
                        "graph_support": 0.20,
                        "ocr_support": 0.05,
                        "part_catalog": 0.00,
                        "extraction_layer": 0.05,
                    },
                    "thresholds": {"A": 0.75, "B": 0.60, "C": 0.40},
                    "hard_blocks": ["missing_page", "missing_tiff", "missing_source_url", "source_untraceable"],
                    "hard_promotions": ["source_trace_verified", "page_exists_and_source_paths_present"],
                    "note": "Source trace proves page/source existence, not claim truth; OCR/catalog absence should not demote source truth.",
                },
                "source_text_evidence": {
                    "purpose": "source_backed_text_evidence",
                    "max_auto_tier": "A",
                    "min_rag_tier": "B",
                    "default_rag_action": "include_as_source_text_evidence",
                    "weights": {
                        "source_trace": 0.30,
                        "graph_support": 0.20,
                        "ocr_support": 0.40,
                        "part_catalog": 0.05,
                        "extraction_layer": 0.05,
                    },
                    "thresholds": {"A": 0.80, "B": 0.65, "C": 0.45},
                    "hard_blocks": ["source_untraceable", "missing_ocr_text", "unsafe_candidate"],
                    "hard_promotions": ["ocr_text_present_and_source_trace_verified"],
                    "note": "Source text is source-backed OCR/page text; OCR signal should dominate but source trace remains required.",
                },
                "part_catalog": {
                    "purpose": "verified_part_evidence",
                    "max_auto_tier": "A",
                    "min_rag_tier": "A",
                    "default_rag_action": "include_as_verified_part_evidence",
                    "weights": {
                        "source_trace": 0.25,
                        "graph_support": 0.20,
                        "ocr_support": 0.10,
                        "part_catalog": 0.40,
                        "extraction_layer": 0.05,
                    },
                    "thresholds": {"A": 0.82, "B": 0.66, "C": 0.42},
                    "hard_blocks": ["catalog_conflict", "invalid_part_pattern", "source_untraceable"],
                    "hard_promotions": ["catalog_verified_and_source_trace_verified", "same_page_part_mention_present"],
                    "note": "Catalog support dominates verified part evidence.",
                },
                "table_tile_text_refined": {
                    "purpose": "derived_table_text_and_part_evidence",
                    "max_auto_tier": "A",
                    "min_rag_tier": "B",
                    "default_rag_action": "include_as_derived_context",
                    "weights": {
                        "source_trace": 0.25,
                        "graph_support": 0.20,
                        "ocr_support": 0.10,
                        "part_catalog": 0.35,
                        "extraction_layer": 0.10,
                    },
                    "thresholds": {"A": 0.82, "B": 0.64, "C": 0.40},
                    "hard_blocks": ["index_label_as_part", "metadata_leakage", "prompt_template_leakage", "source_untraceable", "unjoined_derived_context"],
                    "hard_promotions": ["catalog_supported_part_numbers_found_and_source_trace_verified"],
                    "note": "A-tier inside this layer can still route as derived context only, not canonical source truth.",
                },
                "visual_text": {
                    "purpose": "model_derived_visual_context",
                    "max_auto_tier": "B",
                    "min_rag_tier": "B",
                    "default_rag_action": "include_as_derived_context",
                    "weights": {
                        "source_trace": 0.25,
                        "graph_support": 0.30,
                        "ocr_support": 0.20,
                        "part_catalog": 0.10,
                        "extraction_layer": 0.15,
                    },
                    "thresholds": {"A": 0.92, "B": 0.74, "C": 0.45},
                    "hard_blocks": ["metadata_leakage", "prompt_template_leakage", "refusal_like", "section_bleed_unrepaired", "source_untraceable"],
                    "hard_promotions": ["low_risk_and_graph_support_strong_and_source_trace_verified"],
                    "note": "Vision model output remains conservative and should not become canonical source truth.",
                },
                "table_candidate": {
                    "purpose": "routing_signal",
                    "max_auto_tier": "B",
                    "min_rag_tier": None,
                    "default_rag_action": "exclude_until_table_tiles_exist",
                    "weights": {
                        "source_trace": 0.15,
                        "graph_support": 0.40,
                        "ocr_support": 0.05,
                        "part_catalog": 0.00,
                        "extraction_layer": 0.40,
                    },
                    "thresholds": {"A": 0.90, "B": 0.66, "C": 0.40},
                    "hard_blocks": ["graph_gate_blocked", "layout_gate_blocked", "figure_without_table_trait", "source_untraceable"],
                    "hard_promotions": ["passed_graph_gate_and_passed_layout_gate"],
                    "note": "High confidence means process priority, not factual/RAG truth.",
                },
                "table_tiles": {
                    "purpose": "preprocessing_artifact",
                    "max_auto_tier": "B",
                    "min_rag_tier": None,
                    "default_rag_action": "exclude_until_table_text_exists",
                    "weights": {
                        "source_trace": 0.25,
                        "graph_support": 0.25,
                        "ocr_support": 0.00,
                        "part_catalog": 0.00,
                        "extraction_layer": 0.50,
                    },
                    "thresholds": {"A": 0.90, "B": 0.65, "C": 0.40},
                    "hard_blocks": ["missing_tile_images", "missing_preprocessed_image", "source_untraceable"],
                    "hard_promotions": ["tile_images_created_and_source_trace_verified"],
                    "note": "Tiles prove preprocessing happened; table text still needs extraction/refinement before RAG.",
                },
            },
        },
        "risk_scores": {
            "source_untraceable": 1.00,
            "metadata_leakage": 1.00,
            "prompt_template_leakage": 1.00,
            "refusal_like": 0.95,
            "catalog_conflict": 0.80,
            "graph_conflict": 0.70,
            "context_warning_feedback": 0.60,
            "unsupported_specific_claim": 0.50,
            "hallucination_risk_low": 0.40,
            "hallucination_risk_high": 0.70,
            "noisy_ocr_or_tile_text": 0.30,
            "low_risk": 0.05,
        },
        "risk_combination": {
            "method": "max",
            "note": "Use max risk rather than average so one severe failure is not averaged away.",
        },
        "retrieval_ranking": {
            "group_score_formula": "best_chunk_score + evidence_diversity_bonus + exact_match_bonus + bucket_bonus + confidence_bonus + feedback_adjustment",
            "exact_match_bonuses": {
                "exact_part_number_match": 20.0,
                "exact_page_id_match": 25.0,
                "exact_phrase_match": 8.0,
                "all_query_terms_matched": 10.0,
                "per_matched_term": 2.0,
            },
            "bucket_bonuses": {
                "verified_part_evidence": 8.0,
                "source_text_evidence": 5.0,
                "derived_context": 3.0,
                "source_evidence": 2.0,
            },
            "evidence_diversity": {
                "per_bucket_bonus": 4.0,
                "max_bucket_bonus": 12.0,
                "note": "Pages supported by multiple safe evidence buckets should outrank equally matching single-evidence pages.",
            },
            "confidence_bonus": {
                "multiplier": 3.0,
                "source": "usable_confidence",
            },
        },
        "feedback_ranking": {
            "eligible_only_when": ["context_status_valid", "policy_signal_eligible_true"],
            "ignore_when": ["context_warning", "needs_review", "source_truth_mutation_requested"],
            "reason_weights": {
                "answer_correct": 6.0,
                "source_helpful": 5.0,
                "citation_useful": 4.0,
                "wrong_page": -8.0,
                "wrong_part": -10.0,
                "citation_not_supporting_answer": -7.0,
                "answer_too_vague": -3.0,
                "expected_page_boost": 8.0,
            },
            "expert_multiplier": 2.0,
            "cap_min": -15.0,
            "cap_max": 15.0,
            "note": "Feedback can reorder close safe results but cannot prove source truth or include unsafe records.",
        },
        "global_safety_gates": list(REQUIRED_GLOBAL_SAFETY_GATES),
        "rollout": {
            "stage": "policy_config_only",
            "production_ranking_changed": False,
            "source_truth_mutation_allowed": False,
            "recommended_next": "simulate_weighted_search_before_applying_any_ranking_changes",
        },
    }


def _sum_weights(weights: Dict[str, Any]) -> float:
    return float(sum(float(weights.get(k, 0.0)) for k in WEIGHT_KEYS))


def validate_weight_policy(policy: Dict[str, Any]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """Validate a TRACE-Net weights policy.

    Returns (checks, errors, metrics). The checks list contains readable OK/FAIL
    descriptions suitable for reports; errors controls final status.
    """
    checks: List[str] = []
    errors: List[str] = []
    metrics: Dict[str, Any] = {}

    version = policy.get("version")
    if version == WEIGHTS_POLICY_VERSION:
        checks.append(f"OK version: {version}")
    else:
        errors.append(f"version expected {WEIGHTS_POLICY_VERSION}; got {version!r}")
        checks.append(f"FAIL version: {version!r}")

    layers = ((policy.get("confidence") or {}).get("layers") or {})
    metrics["layer_count"] = len(layers)
    missing_layers = [layer for layer in REQUIRED_LAYERS if layer not in layers]
    metrics["missing_layers"] = missing_layers
    if not missing_layers:
        checks.append(f"OK required_layers: {len(REQUIRED_LAYERS)} present")
    else:
        errors.append(f"missing required layers: {missing_layers}")
        checks.append(f"FAIL required_layers: missing={missing_layers}")

    weight_sums: Dict[str, float] = {}
    threshold_errors: List[str] = []
    for layer, cfg in sorted(layers.items()):
        weights = cfg.get("weights") or {}
        missing_weight_keys = [k for k in WEIGHT_KEYS if k not in weights]
        if missing_weight_keys:
            errors.append(f"{layer} missing weight keys {missing_weight_keys}")
            checks.append(f"FAIL weights[{layer}]: missing {missing_weight_keys}")
        total = round(_sum_weights(weights), 6)
        weight_sums[layer] = total
        if math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            checks.append(f"OK weights[{layer}]: sum={total}")
        else:
            errors.append(f"{layer} weights sum to {total}, expected 1.0")
            checks.append(f"FAIL weights[{layer}]: sum={total}")
        thresholds = cfg.get("thresholds") or {}
        try:
            a = float(thresholds["A"])
            b = float(thresholds["B"])
            c = float(thresholds["C"])
            if 1.0 >= a > b > c >= 0.0:
                checks.append(f"OK thresholds[{layer}]: A={a} B={b} C={c}")
            else:
                threshold_errors.append(f"{layer} thresholds must satisfy 1 >= A > B > C >= 0; got {thresholds}")
                checks.append(f"FAIL thresholds[{layer}]: {thresholds}")
        except Exception:
            threshold_errors.append(f"{layer} thresholds missing/invalid: {thresholds}")
            checks.append(f"FAIL thresholds[{layer}]: {thresholds}")
    if threshold_errors:
        errors.extend(threshold_errors)
    metrics["weight_sums"] = weight_sums

    # Layer-specific policy sanity checks.
    source_trace = layers.get("source_trace", {})
    visual_text = layers.get("visual_text", {})
    table_candidate = layers.get("table_candidate", {})
    table_tiles = layers.get("table_tiles", {})
    table_tile_text = layers.get("table_tile_text_refined", {})
    source_text = layers.get("source_text_evidence", {})

    if source_trace.get("max_auto_tier") == "A" and source_trace.get("default_rag_action") == "include_as_source_evidence":
        checks.append("OK source_trace_policy: max=A and source evidence action")
    else:
        errors.append("source_trace policy must allow A and include_as_source_evidence")
        checks.append("FAIL source_trace_policy")

    if source_text.get("default_rag_action") == "include_as_source_text_evidence" and float((source_text.get("weights") or {}).get("ocr_support", 0.0)) >= 0.35:
        checks.append("OK source_text_policy: OCR-weighted source text evidence present")
    else:
        errors.append("source_text_evidence policy must be present and OCR weighted")
        checks.append("FAIL source_text_policy")

    if visual_text.get("max_auto_tier") == "B" and "prompt_template_leakage" in (visual_text.get("hard_blocks") or []):
        checks.append("OK visual_text_policy: conservative max=B and prompt leakage hard block")
    else:
        errors.append("visual_text must remain conservative with max_auto_tier B and prompt leakage hard block")
        checks.append("FAIL visual_text_policy")

    for layer_name, layer_cfg in [("table_candidate", table_candidate), ("table_tiles", table_tiles)]:
        if layer_cfg.get("min_rag_tier") is None and str(layer_cfg.get("default_rag_action", "")).startswith("exclude_until"):
            checks.append(f"OK {layer_name}_policy: routing/preprocessing only, no direct RAG")
        else:
            errors.append(f"{layer_name} must not have direct RAG min tier")
            checks.append(f"FAIL {layer_name}_policy")

    if table_tile_text.get("default_rag_action") == "include_as_derived_context" and table_tile_text.get("min_rag_tier") == "B":
        checks.append("OK table_tile_text_policy: B+ routes as derived context")
    else:
        errors.append("table_tile_text_refined must route B+ as derived context")
        checks.append("FAIL table_tile_text_policy")

    risk_scores = policy.get("risk_scores") or {}
    metrics["risk_score_count"] = len(risk_scores)
    required_risk = ["source_untraceable", "metadata_leakage", "prompt_template_leakage", "low_risk"]
    missing_risk = [r for r in required_risk if r not in risk_scores]
    if not missing_risk and all(0.0 <= float(v) <= 1.0 for v in risk_scores.values()):
        checks.append(f"OK risk_scores: count={len(risk_scores)}")
    else:
        errors.append(f"risk scores missing/invalid: missing={missing_risk}")
        checks.append(f"FAIL risk_scores: missing={missing_risk}")
    if (policy.get("risk_combination") or {}).get("method") == "max":
        checks.append("OK risk_combination: max")
    else:
        errors.append("risk_combination method must be max")
        checks.append("FAIL risk_combination")

    retrieval = policy.get("retrieval_ranking") or {}
    bucket_bonuses = retrieval.get("bucket_bonuses") or {}
    metrics["retrieval_bucket_bonus_count"] = len(bucket_bonuses)
    required_buckets = ["verified_part_evidence", "source_text_evidence", "derived_context", "source_evidence"]
    missing_buckets = [b for b in required_buckets if b not in bucket_bonuses]
    if not missing_buckets:
        checks.append("OK retrieval_bucket_bonuses: required buckets present")
    else:
        errors.append(f"missing retrieval bucket bonuses: {missing_buckets}")
        checks.append(f"FAIL retrieval_bucket_bonuses: missing={missing_buckets}")

    feedback = policy.get("feedback_ranking") or {}
    reason_weights = feedback.get("reason_weights") or {}
    metrics["feedback_reason_count"] = len(reason_weights)
    if float(reason_weights.get("wrong_page", 0.0)) < 0 and float(reason_weights.get("wrong_part", 0.0)) < 0 and float(reason_weights.get("answer_correct", 0.0)) > 0:
        checks.append("OK feedback_reason_weights: positive and negative signs sane")
    else:
        errors.append("feedback reason weights must include positive answer_correct and negative wrong_page/wrong_part")
        checks.append("FAIL feedback_reason_weights")
    if float(feedback.get("cap_min", 0.0)) < 0 < float(feedback.get("cap_max", 0.0)):
        checks.append(f"OK feedback_caps: {feedback.get('cap_min')}..{feedback.get('cap_max')}")
    else:
        errors.append("feedback caps must straddle zero")
        checks.append("FAIL feedback_caps")
    if "context_status_valid" in (feedback.get("eligible_only_when") or []) and "context_warning" in (feedback.get("ignore_when") or []):
        checks.append("OK feedback_context_validation: valid-only and warning ignored")
    else:
        errors.append("feedback must require context-valid events and ignore context warnings")
        checks.append("FAIL feedback_context_validation")

    gates = policy.get("global_safety_gates") or []
    missing_gates = [g for g in REQUIRED_GLOBAL_SAFETY_GATES if g not in gates]
    metrics["global_safety_gate_count"] = len(gates)
    if not missing_gates:
        checks.append(f"OK global_safety_gates: count={len(gates)}")
    else:
        errors.append(f"missing global safety gates: {missing_gates}")
        checks.append(f"FAIL global_safety_gates: missing={missing_gates}")

    rollout = policy.get("rollout") or {}
    if rollout.get("production_ranking_changed") is False and rollout.get("source_truth_mutation_allowed") is False:
        checks.append("OK rollout: config only, no production ranking/source truth mutation")
    else:
        errors.append("rollout must be config-only with no production ranking/source truth mutation")
        checks.append("FAIL rollout")

    metrics["error_count"] = len(errors)
    return checks, errors, metrics


def build_graph_overlay(policy: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    root_id = f"weight_policy:{policy.get('version', WEIGHTS_POLICY_VERSION)}"
    nodes.append({
        "id": root_id,
        "label": "TRACE-Net Weights Policy",
        "kind": "trace_net_weight_policy",
        "version": policy.get("version"),
    })

    layers = ((policy.get("confidence") or {}).get("layers") or {})
    for layer, cfg in sorted(layers.items()):
        layer_id = f"weight_layer:{layer}"
        nodes.append({
            "id": layer_id,
            "label": layer,
            "kind": "confidence_weight_layer",
            "purpose": cfg.get("purpose"),
            "max_auto_tier": cfg.get("max_auto_tier"),
            "default_rag_action": cfg.get("default_rag_action"),
        })
        edges.append({
            "source": root_id,
            "target": layer_id,
            "type": "HAS_CONFIDENCE_LAYER_POLICY",
        })
        for key, value in sorted((cfg.get("weights") or {}).items()):
            weight_id = f"weight:{layer}:{key}"
            nodes.append({
                "id": weight_id,
                "label": f"{key}={value}",
                "kind": "confidence_weight",
                "layer": layer,
                "feature": key,
                "weight": value,
            })
            edges.append({
                "source": layer_id,
                "target": weight_id,
                "type": "HAS_WEIGHT",
                "weight": value,
            })

    feedback_id = "weight_policy:feedback_ranking"
    nodes.append({"id": feedback_id, "label": "Feedback Ranking Weights", "kind": "feedback_weight_policy"})
    edges.append({"source": root_id, "target": feedback_id, "type": "HAS_FEEDBACK_POLICY"})
    for reason, value in sorted(((policy.get("feedback_ranking") or {}).get("reason_weights") or {}).items()):
        node_id = f"feedback_weight:{reason}"
        nodes.append({"id": node_id, "label": f"{reason}={value}", "kind": "feedback_reason_weight", "reason": reason, "weight": value})
        edges.append({"source": feedback_id, "target": node_id, "type": "HAS_FEEDBACK_WEIGHT", "weight": value})

    retrieval_id = "weight_policy:retrieval_ranking"
    nodes.append({"id": retrieval_id, "label": "Retrieval Ranking Weights", "kind": "retrieval_weight_policy"})
    edges.append({"source": root_id, "target": retrieval_id, "type": "HAS_RETRIEVAL_POLICY"})
    for bucket, value in sorted(((policy.get("retrieval_ranking") or {}).get("bucket_bonuses") or {}).items()):
        node_id = f"retrieval_bucket_bonus:{bucket}"
        nodes.append({"id": node_id, "label": f"{bucket}=+{value}", "kind": "retrieval_bucket_bonus", "bucket": bucket, "bonus": value})
        edges.append({"source": retrieval_id, "target": node_id, "type": "HAS_BUCKET_BONUS", "weight": value})

    return nodes, edges


def render_policy_report(policy: Dict[str, Any], checks: List[str], metrics: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net Weights Policy v1")
    lines.append("")
    lines.append(f"Status: **{policy.get('status', 'UNKNOWN')}**")
    lines.append(f"Version: `{policy.get('version')}`")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append("This policy stores the first official TRACE-Net weight recommendations for confidence scoring, retrieval ranking, and validated feedback adjustments.")
    lines.append("")
    lines.append("It is **configuration only**. It does not change production ranking or source truth by itself.")
    lines.append("")
    lines.append("## Confidence layer weights")
    lines.append("")
    lines.append("| Layer | Source | Graph | OCR | Catalog | Extraction | A | B | C | Max tier | RAG action |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    layers = ((policy.get("confidence") or {}).get("layers") or {})
    for layer in REQUIRED_LAYERS:
        cfg = layers.get(layer, {})
        weights = cfg.get("weights") or {}
        th = cfg.get("thresholds") or {}
        lines.append(
            "| "
            + " | ".join([
                layer,
                f"{float(weights.get('source_trace', 0.0)):.2f}",
                f"{float(weights.get('graph_support', 0.0)):.2f}",
                f"{float(weights.get('ocr_support', 0.0)):.2f}",
                f"{float(weights.get('part_catalog', 0.0)):.2f}",
                f"{float(weights.get('extraction_layer', 0.0)):.2f}",
                str(th.get("A")),
                str(th.get("B")),
                str(th.get("C")),
                str(cfg.get("max_auto_tier")),
                str(cfg.get("default_rag_action")),
            ])
            + " |"
        )
    lines.append("")
    lines.append("## Retrieval ranking weights")
    lines.append("")
    lines.append("Bucket bonuses:")
    for bucket, bonus in sorted(((policy.get("retrieval_ranking") or {}).get("bucket_bonuses") or {}).items()):
        lines.append(f"- `{bucket}`: +{bonus}")
    lines.append("")
    lines.append("Exact-match bonuses:")
    for key, bonus in sorted(((policy.get("retrieval_ranking") or {}).get("exact_match_bonuses") or {}).items()):
        lines.append(f"- `{key}`: +{bonus}")
    lines.append("")
    lines.append("## Feedback ranking weights")
    lines.append("")
    for reason, weight in sorted(((policy.get("feedback_ranking") or {}).get("reason_weights") or {}).items()):
        lines.append(f"- `{reason}`: {weight:+g}")
    fb = policy.get("feedback_ranking") or {}
    lines.append(f"- feedback cap: `{fb.get('cap_min')}` to `{fb.get('cap_max')}`")
    lines.append("")
    lines.append("## Risk scores")
    lines.append("")
    for risk, score in sorted((policy.get("risk_scores") or {}).items()):
        lines.append(f"- `{risk}`: {score}")
    lines.append("")
    lines.append("## Global safety gates")
    lines.append("")
    for gate in policy.get("global_safety_gates") or []:
        lines.append(f"- `{gate}`")
    lines.append("")
    lines.append("## Validation checks")
    lines.append("")
    for check in checks:
        lines.append(f"- {check}")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    for key, value in sorted(metrics.items()):
        lines.append(f"- **{key}**: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _markdown_to_html(md: str, title: str) -> str:
    # Simple report renderer; good enough for local review artifacts.
    body_parts: List[str] = []
    in_table = False
    for line in md.splitlines():
        if line.startswith("# "):
            body_parts.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_parts.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body_parts.append(f"<p>• {html.escape(line[2:])}</p>")
        elif line.startswith("| "):
            # Render tables as preformatted Markdown to keep implementation tiny.
            body_parts.append(f"<pre>{html.escape(line)}</pre>")
        elif not line.strip():
            body_parts.append("")
        else:
            body_parts.append(f"<p>{html.escape(line)}</p>")
    body = "\n".join(body_parts)
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; line-height: 1.4; }}
pre {{ background: #f6f8fa; padding: 6px; overflow-x: auto; }}
code {{ background: #f6f8fa; padding: 1px 3px; }}
</style></head><body>{body}</body></html>
"""


def build_trace_net_weights_policy(options: WeightPolicyOptions) -> Dict[str, Any]:
    out = options.output_dir
    out.mkdir(parents=True, exist_ok=True)
    policy = default_weight_policy()
    checks, errors, metrics = validate_weight_policy(policy)
    policy["status"] = "OK" if not errors else "FAIL"
    policy["validation"] = {
        "checks": checks,
        "errors": errors,
        "metrics": metrics,
    }

    nodes, edges = build_graph_overlay(policy)

    policy_path = out / "trace_net_weights_policy.json"
    summary_path = out / "trace_net_weights_policy_summary.json"
    report_md_path = out / "trace_net_weights_policy_report.md"
    report_html_path = out / "trace_net_weights_policy_report.html"
    nodes_path = out / "trace_net_weights_policy_graph_nodes.json"
    edges_path = out / "trace_net_weights_policy_graph_edges.json"

    confidence_layers = (policy.get("confidence") or {}).get("layers") or {}
    summary = {
        "status": policy["status"],
        "version": policy["version"],
        "created_at": policy["created_at"],
        "layer_count": len(confidence_layers),
        "confidence_layers": sorted(confidence_layers),
        "required_layers_present": not metrics.get("missing_layers"),
        "weight_sums": metrics.get("weight_sums", {}),
        "risk_score_count": metrics.get("risk_score_count", 0),
        "retrieval_bucket_bonus_count": metrics.get("retrieval_bucket_bonus_count", 0),
        "feedback_reason_count": metrics.get("feedback_reason_count", 0),
        "global_safety_gate_count": metrics.get("global_safety_gate_count", 0),
        "production_ranking_changed": bool((policy.get("rollout") or {}).get("production_ranking_changed")),
        "source_truth_mutation_allowed": bool((policy.get("rollout") or {}).get("source_truth_mutation_allowed")),
        "validation_error_count": len(errors),
        "policy_path": _repo_relative(policy_path),
        "report_md_path": _repo_relative(report_md_path),
        "report_html_path": _repo_relative(report_html_path),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
    }

    report_md = render_policy_report(policy, checks, metrics)
    report_html = _markdown_to_html(report_md, "TRACE-Net Weights Policy v1")

    _write_json(policy_path, policy)
    _write_json(summary_path, summary)
    report_md_path.write_text(report_md, encoding="utf-8")
    report_html_path.write_text(report_html, encoding="utf-8")
    _write_json(nodes_path, nodes)
    _write_json(edges_path, edges)

    result = {
        "status": policy["status"],
        "policy": policy,
        "summary": summary,
        "paths": {
            "policy": policy_path,
            "summary": summary_path,
            "report_md": report_md_path,
            "report_html": report_html_path,
            "graph_nodes": nodes_path,
            "graph_edges": edges_path,
        },
        "checks": checks,
        "errors": errors,
    }
    if options.open_result:
        try:
            webbrowser.open(report_html_path.resolve().as_uri())
        except Exception:
            pass
    return result


def print_result(result: Dict[str, Any]) -> None:
    summary = result.get("summary") or {}
    print("TRACE-Net weights policy")
    print(f"  Status: {result.get('status')}")
    print(f"  Version: {summary.get('version')}")
    print(f"  Output dir: {Path(result['paths']['summary']).parent}")
    print("  Summary:")
    print(f"    layer_count: {summary.get('layer_count')}")
    print(f"    confidence_layers: {summary.get('confidence_layers')}")
    print(f"    risk_score_count: {summary.get('risk_score_count')}")
    print(f"    retrieval_bucket_bonus_count: {summary.get('retrieval_bucket_bonus_count')}")
    print(f"    feedback_reason_count: {summary.get('feedback_reason_count')}")
    print(f"    global_safety_gate_count: {summary.get('global_safety_gate_count')}")
    print(f"    production_ranking_changed: {summary.get('production_ranking_changed')}")
    print(f"    source_truth_mutation_allowed: {summary.get('source_truth_mutation_allowed')}")
    print(f"    graph_nodes: {summary.get('graph_nodes')}")
    print(f"    graph_edges: {summary.get('graph_edges')}")
    print("Files written:")
    for key, path in result.get("paths", {}).items():
        print(f"  {key}: {_repo_relative(Path(path))}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net weights policy v1.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for policy artifacts.")
    parser.add_argument("--open", action="store_true", help="Open the HTML report after writing.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    options = WeightPolicyOptions(output_dir=Path(args.output_dir), open_result=bool(args.open))
    result = build_trace_net_weights_policy(options)
    print_result(result)
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
