import json
from pathlib import Path

from tiff.trace_net_leiden_category_summary_hydrator_v1 import main


def write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cli_build_and_quality_pass(tmp_path):
    leiden = {
        "quality_status": "PASS",
        "communities": [
            {"community_id": "tracenet_community_00001", "label": "Part family", "page_ids": ["t_p_120_1176_p000001"]}
        ],
    }
    overlay = {"quality_status": "PASS", "page_category_profiles": [{"page_id": "t_p_120_1176_p000001", "page_category_label": "text_source_page"}]}
    taxonomy = {"quality_status": "PASS", "page_profiles": [{"page_id": "t_p_120_1176_p000001", "categories": ["part", "citation"]}]}
    dc = {"quality_status": "PASS", "page_records": [{"page_id": "t_p_120_1176_p000001", "dc": {"dc:type": ["technical_manual_page"]}}]}
    graph_ui = {"quality_status": "PASS", "community_cards": []}
    audit = {"quality_status": "PASS", "community_audit_records": []}

    leiden_p = tmp_path / "leiden.json"
    overlay_p = tmp_path / "overlay.json"
    taxonomy_p = tmp_path / "taxonomy.json"
    dc_p = tmp_path / "dc.json"
    graph_ui_p = tmp_path / "graph_ui.json"
    audit_p = tmp_path / "audit.json"
    out = tmp_path / "out"
    for path, payload in [
        (leiden_p, leiden),
        (overlay_p, overlay),
        (taxonomy_p, taxonomy),
        (dc_p, dc),
        (graph_ui_p, graph_ui),
        (audit_p, audit),
    ]:
        write(path, payload)

    rc = main([
        "--leiden-communities", str(leiden_p),
        "--category-aware-leiden-overlay", str(overlay_p),
        "--element-category-taxonomy", str(taxonomy_p),
        "--dublin-core-refined", str(dc_p),
        "--graph-ui-community-overlay", str(graph_ui_p),
        "--leiden-community-quality-audit", str(audit_p),
        "--output-dir", str(out),
        "--require-page-count", "1",
        "--min-communities", "1",
        "--min-hydrated-communities", "1",
        "--max-missing-page-membership", "0",
        "--max-missing-category-summary", "0",
        "--require-leiden-quality-pass",
        "--require-category-overlay-quality-pass",
        "--require-dublin-core-quality-pass",
        "--quality",
    ])
    assert rc == 0
    report = json.loads((out / "trace_net_leiden_category_summary_hydrator_v1.json").read_text(encoding="utf-8"))
    quality = json.loads((out / "trace_net_leiden_category_summary_hydrator_v1_quality.json").read_text(encoding="utf-8"))
    assert report["quality_status"] == "PASS"
    assert quality["quality_status"] == "PASS"
    assert (out / "trace_net_leiden_category_summary_hydrator_v1_records.jsonl").exists()
    assert (out / "trace_net_leiden_category_summary_hydrator_v1.md").exists()


def test_quality_report_fails_when_missing_page_membership_exceeds_threshold(tmp_path):
    leiden = {"quality_status": "PASS", "communities": [{"community_id": "c1", "page_ids": []}]}
    p = tmp_path / "leiden.json"
    overlay = tmp_path / "overlay.json"
    taxonomy = tmp_path / "taxonomy.json"
    dc = tmp_path / "dc.json"
    out = tmp_path / "out"
    write(p, leiden)
    write(overlay, {"quality_status": "PASS"})
    write(taxonomy, {"quality_status": "PASS"})
    write(dc, {"quality_status": "PASS"})
    rc = main([
        "--leiden-communities", str(p),
        "--category-aware-leiden-overlay", str(overlay),
        "--element-category-taxonomy", str(taxonomy),
        "--dublin-core-refined", str(dc),
        "--output-dir", str(out),
        "--min-communities", "1",
        "--min-hydrated-communities", "0",
        "--max-missing-page-membership", "0",
        "--quality",
    ])
    assert rc == 2
    quality = json.loads((out / "trace_net_leiden_category_summary_hydrator_v1_quality.json").read_text(encoding="utf-8"))
    assert quality["quality_status"] == "FAIL"
    assert any("missing_page_membership_count" in issue for issue in quality["issues"])
