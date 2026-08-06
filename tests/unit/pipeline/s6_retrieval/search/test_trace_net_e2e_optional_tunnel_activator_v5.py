from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_optional_tunnel_activator_v5 import build_optional_tunnel_activation_report


def test_optional_tunnel_activator_builds_missing_artifacts(tmp_path):
    root = tmp_path / "trace_net"
    exact_path = tmp_path / "exact.json"
    bridge_path = tmp_path / "bridge.json"
    profiles_path = tmp_path / "profiles.json"
    out_dir = tmp_path / "out"

    exact_path.write_text(json.dumps({
        "quality_status": "PASS",
        "exact_search_documents": [
            {"page_id": "p1", "field_name": "covered_part_number", "normalized_value": "120-1"},
            {"page_id": "p2", "field_name": "manual_page_reference", "normalized_value": "25-21-00"},
        ],
    }), encoding="utf-8")
    bridge_path.write_text(json.dumps({"quality_status": "PASS", "table_hybrid_bridge_records": [{"page_id": "p1"}]}), encoding="utf-8")
    profiles_path.write_text(json.dumps({"page_profiles": [{"page_id": "p1", "route": "table"}, {"page_id": "p2", "route": "table"}]}), encoding="utf-8")

    report = build_optional_tunnel_activation_report(
        trace_net_root=root,
        table_exact_search_adapter=exact_path,
        table_hybrid_retrieval_bridge=bridge_path,
        page_retrieval_profiles=profiles_path,
        output_dir=out_dir,
    )

    assert report["quality_status"] == "PASS"
    assert (root / "page_context_v2/trace_net_page_context_v2.json").exists()
    assert (root / "leiden_communities/trace_net_leiden_communities_v1.json").exists()
    assert (root / "community_navigation_metadata_bridge/trace_net_community_navigation_metadata_bridge_v1.json").exists()
    assert (root / "table_route_retrieval_handoff_summary/trace_net_table_route_retrieval_handoff_summary_v1.json").exists()
    assert report["activation_contract"]["reruns_ocr"] is False
    assert report["activation_contract"]["graph_is_not_proof_authority"] is True


def test_optional_tunnel_activator_does_not_grant_answer_authority(tmp_path):
    root = tmp_path / "trace_net"
    exact_path = tmp_path / "exact.json"
    bridge_path = tmp_path / "bridge.json"
    profiles_path = tmp_path / "profiles.json"
    exact_path.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": [{"page_id": "p1", "field_name": "x", "normalized_value": "y"}]}), encoding="utf-8")
    bridge_path.write_text(json.dumps({"quality_status": "PASS", "table_hybrid_bridge_records": []}), encoding="utf-8")
    profiles_path.write_text(json.dumps({"page_profiles": [{"page_id": "p1"}]}), encoding="utf-8")

    report = build_optional_tunnel_activation_report(
        trace_net_root=root,
        table_exact_search_adapter=exact_path,
        table_hybrid_retrieval_bridge=bridge_path,
        page_retrieval_profiles=profiles_path,
        output_dir=tmp_path / "out",
    )
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
    for state in report["artifact_states"]:
        assert state["answer_authority"] == "blocked"
