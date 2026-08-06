import json
from pathlib import Path

from tiff.trace_net_anchor_aware_graph_leiden_expander_v1 import build_anchor_aware_graph_leiden_expander


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_anchor_aware_expander_prioritizes_exact_anchors_and_same_community(tmp_path):
    anchor = _write(tmp_path / "anchor.json", {
        "quality_status": "PASS",
        "summary": {"question": "Find part number 120-29073-001", "query_part_numbers": ["120-29073-001"]},
        "records": [
            {"citation_label": "E1", "anchor_role": "direct_exact_match_anchor", "proof_strength": "direct_exact_proof", "page_id": "t_p_120_1176_p000343", "page_number": 343, "source_member": "00000343.tif", "excerpt": "120-29073-001 STRUCTURE"},
            {"citation_label": "E2", "anchor_role": "family_variant_anchor", "proof_strength": "related_variant", "page_id": "t_p_120_1176_p000346", "page_number": 346, "source_member": "00000346.tif", "excerpt": "120-29073-005 STRUCTURE"},
            {"citation_label": "E3", "anchor_role": "similar_table_candidate", "proof_strength": "weak_candidate", "page_id": "t_p_120_1176_p000055", "page_number": 55, "source_member": "00000055.tif", "excerpt": "unrelated"},
        ],
    })
    leiden = _write(tmp_path / "leiden.json", {
        "quality_status": "PASS",
        "nodes": [
            {"page_id": "t_p_120_1176_p000343", "leiden_community_id": "37"},
            {"page_id": "t_p_120_1176_p000346", "leiden_community_id": "37"},
            {"page_id": "t_p_120_1176_p000055", "leiden_community_id": "2"},
        ],
    })
    out = tmp_path / "out"
    payload = build_anchor_aware_graph_leiden_expander(
        anchor_injector=anchor,
        leiden_communities=leiden,
        output_dir=out,
        require_source_quality_pass=True,
        require_anchor_communities=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["direct_exact_anchor_count"] == 1
    assert summary["anchor_community_count"] >= 1
    assert summary["same_anchor_leiden_community_count"] >= 2
    roles = {r["citation_label"]: r["anchor_aware_role"] for r in payload["records"]}
    assert roles["E1"] == "direct_exact_match_anchor"
    assert roles["E2"] == "same_anchor_community_variant"
    assert roles["E3"] == "similar_table_candidate"
    assert "120-29073-001" in (out / "trace_net_anchor_aware_graph_leiden_expander_v1_prompt.txt").read_text(encoding="utf-8")


def test_anchor_aware_expander_nearby_page_variant_without_community(tmp_path):
    anchor = _write(tmp_path / "anchor.json", {
        "quality_status": "PASS",
        "summary": {"question": "q", "query_part_numbers": ["PN"]},
        "records": [
            {"citation_label": "E1", "anchor_role": "direct_exact_match_anchor", "proof_strength": "direct_exact_proof", "page_id": "t_p_120_1176_p000100", "page_number": 100, "excerpt": "PN"},
            {"citation_label": "E2", "anchor_role": "family_variant_anchor", "proof_strength": "related_variant", "page_id": "t_p_120_1176_p000102", "page_number": 102, "excerpt": "PN-2"},
        ],
    })
    payload = build_anchor_aware_graph_leiden_expander(anchor_injector=anchor, output_dir=tmp_path / "out")
    roles = {r["citation_label"]: r["anchor_aware_role"] for r in payload["records"]}
    assert roles["E2"] == "same_anchor_page_variant"


def test_anchor_aware_expander_demotes_old_direct_candidate(tmp_path):
    anchor = _write(tmp_path / "anchor.json", {
        "quality_status": "PASS",
        "summary": {"question": "q", "query_part_numbers": ["PN"]},
        "records": [
            {"citation_label": "E1", "anchor_role": "direct_exact_match_anchor", "proof_strength": "direct_exact_proof", "page_id": "t_p_120_1176_p000343", "page_number": 343, "excerpt": "PN"},
            {"citation_label": "E2", "anchor_role": "direct_exact_match_candidate", "proof_strength": "direct_candidate", "page_id": "t_p_120_1176_p000005", "page_number": 5, "excerpt": "old weak"},
        ],
    })
    payload = build_anchor_aware_graph_leiden_expander(anchor_injector=anchor, output_dir=tmp_path / "out")
    e2 = next(r for r in payload["records"] if r["citation_label"] == "E2")
    assert e2["anchor_aware_role"] == "superseded_direct_candidate"
    assert "retained_old_direct_candidate_demoted_by_exact_anchors" in e2["anchor_aware_warnings"]


def test_anchor_aware_expander_fails_when_required_anchor_communities_missing(tmp_path):
    anchor = _write(tmp_path / "anchor.json", {
        "quality_status": "PASS",
        "summary": {"question": "q", "query_part_numbers": ["PN"]},
        "records": [
            {"citation_label": "E1", "anchor_role": "direct_exact_match_anchor", "proof_strength": "direct_exact_proof", "page_id": "t_p_120_1176_p000343", "page_number": 343, "excerpt": "PN"},
        ],
    })
    payload = build_anchor_aware_graph_leiden_expander(
        anchor_injector=anchor,
        output_dir=tmp_path / "out",
        require_anchor_communities=True,
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["violation_record_count"] == 1
