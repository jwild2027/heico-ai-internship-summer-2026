from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_weights_policy import WeightPolicyOptions, build_trace_net_weights_policy
from tiff.trace_net_weights_policy_quality import QualityOptions, check_trace_net_weights_policy_quality


def test_weights_policy_quality_passes_on_built_policy(tmp_path: Path) -> None:
    build_trace_net_weights_policy(WeightPolicyOptions(output_dir=tmp_path))
    quality = check_trace_net_weights_policy_quality(
        QualityOptions(
            policy_path=tmp_path / "trace_net_weights_policy.json",
            summary_path=tmp_path / "trace_net_weights_policy_summary.json",
            graph_nodes_path=tmp_path / "trace_net_weights_policy_graph_nodes.json",
            graph_edges_path=tmp_path / "trace_net_weights_policy_graph_edges.json",
            quality_path=tmp_path / "quality.json",
            write_json=True,
        )
    )
    assert quality["status"] == "OK"
    assert quality["policy_layers"] >= 7
    assert quality["feedback_reason_count"] >= 5
    assert (tmp_path / "quality.json").exists()


def test_weights_policy_quality_fails_missing_source_text_when_required(tmp_path: Path) -> None:
    result = build_trace_net_weights_policy(WeightPolicyOptions(output_dir=tmp_path))
    policy_path = tmp_path / "trace_net_weights_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    del policy["confidence"]["layers"]["source_text_evidence"]
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    quality = check_trace_net_weights_policy_quality(
        QualityOptions(
            policy_path=policy_path,
            summary_path=tmp_path / "trace_net_weights_policy_summary.json",
            graph_nodes_path=tmp_path / "trace_net_weights_policy_graph_nodes.json",
            graph_edges_path=tmp_path / "trace_net_weights_policy_graph_edges.json",
        )
    )
    assert quality["status"] == "FAIL"
    assert any("source_text" in failure for failure in quality["failures"])
