from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_confidence_stage3_policy import (
    ConfidencePolicyOptions,
    ConfidencePolicyPaths,
    build_confidence_policy,
)


def _write_stage2(path: Path) -> None:
    data = {
        "status": "OK",
        "records": 1813,
        "agreement_rate": 0.239382,
        "within_one_tier_rate": 0.986762,
        "disagreement_records": 1379,
        "source_trace_confidence_below_A_records": 509,
        "rule_excludes_confidence_high_records": 710,
        "rule_includes_confidence_low_records": 24,
        "avg_usable_confidence": 0.787436,
        "per_layer": {
            "source_trace": {"records": 509, "agreement_rate": 0.0, "avg_usable_confidence": 0.796367},
            "part_catalog": {"records": 364, "agreement_rate": 0.0, "avg_usable_confidence": 0.871051},
            "table_tile_text_refined": {"records": 120, "agreement_rate": 0.466667, "avg_usable_confidence": 0.72576},
            "visual_text": {"records": 25, "agreement_rate": 0.0, "avg_usable_confidence": 0.404285},
            "table_candidate": {"records": 509, "agreement_rate": 0.180747, "avg_usable_confidence": 0.747131},
            "table_tiles": {"records": 286, "agreement_rate": 1.0, "avg_usable_confidence": 0.796223},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_build_confidence_policy_writes_layer_specific_rules(tmp_path: Path) -> None:
    stage2 = tmp_path / "stage2.json"
    _write_stage2(stage2)
    paths = ConfidencePolicyPaths(stage2_eval_path=stage2, output_dir=tmp_path / "out")

    result = build_confidence_policy(paths, ConfidencePolicyOptions(require_stage2=True))
    policy = result["policy"]

    assert policy["status"] == "OK"
    assert policy["version"] == "trace_lc_confidence_policy_v1"
    assert policy["stage2_summary"]["stage2_present"] is True
    assert set(policy["layers"]) >= {
        "source_trace",
        "part_catalog",
        "table_tile_text_refined",
        "visual_text",
        "table_candidate",
        "table_tiles",
    }

    source = policy["layers"]["source_trace"]
    assert source["max_auto_trust_tier"] == "A"
    assert source["default_rag_action"] == "include_as_source_evidence"
    assert "missing_tiff" in source["hard_blocks"]

    table_text = policy["layers"]["table_tile_text_refined"]
    assert table_text["min_rag_tier"] == "B"
    assert "catalog_supported_part_number" in table_text["required_supports_for_B"]

    visual = policy["layers"]["visual_text"]
    assert visual["max_auto_trust_tier"] == "B"
    assert "refusal_like" in visual["hard_blocks"]

    candidate = policy["layers"]["table_candidate"]
    assert candidate["purpose"] == "routing_signal"
    assert candidate["min_rag_tier"] is None

    assert paths.policy.exists()
    assert paths.report_md.exists()
    assert paths.report_html.exists()


def test_build_policy_without_stage2_still_writes_defaults(tmp_path: Path) -> None:
    paths = ConfidencePolicyPaths(stage2_eval_path=tmp_path / "missing.json", output_dir=tmp_path / "out")
    result = build_confidence_policy(paths)
    policy = result["policy"]
    assert policy["status"] == "OK"
    assert policy["stage2_summary"]["stage2_present"] is False
    assert len(policy["layers"]) == 6
