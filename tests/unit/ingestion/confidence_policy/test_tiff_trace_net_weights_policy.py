from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_weights_policy import (
    REQUIRED_LAYERS,
    WEIGHT_KEYS,
    WeightPolicyOptions,
    build_trace_net_weights_policy,
    default_weight_policy,
    validate_weight_policy,
)


def test_default_policy_has_recommended_layers_and_weights_sum_to_one() -> None:
    policy = default_weight_policy()
    layers = policy["confidence"]["layers"]
    assert set(REQUIRED_LAYERS).issubset(layers)
    for layer in REQUIRED_LAYERS:
        weights = layers[layer]["weights"]
        assert set(WEIGHT_KEYS).issubset(weights)
        assert abs(sum(weights[k] for k in WEIGHT_KEYS) - 1.0) < 1e-9


def test_default_policy_validates_cleanly() -> None:
    policy = default_weight_policy()
    checks, errors, metrics = validate_weight_policy(policy)
    assert not errors
    assert metrics["layer_count"] >= 7
    assert any("source_text_policy" in check for check in checks)


def test_build_weights_policy_writes_artifacts(tmp_path: Path) -> None:
    result = build_trace_net_weights_policy(WeightPolicyOptions(output_dir=tmp_path))
    assert result["status"] == "OK"
    for key in ["policy", "summary", "report_md", "report_html", "graph_nodes", "graph_edges"]:
        assert result["paths"][key].exists()
    summary = json.loads(result["paths"]["summary"].read_text(encoding="utf-8"))
    assert summary["layer_count"] >= 7
    assert summary["production_ranking_changed"] is False


def test_validation_catches_bad_weight_sum() -> None:
    policy = default_weight_policy()
    policy["confidence"]["layers"]["source_trace"]["weights"]["source_trace"] = 0.5
    checks, errors, metrics = validate_weight_policy(policy)
    assert errors
    assert any("source_trace weights sum" in error for error in errors)
