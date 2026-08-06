from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from src.trace_net.graph.trace_net_nha_phase0_3_v1 import (
    CorpusSource,
    build_answer_key,
    build_graph_bundle,
    build_relationships,
    discover_assembly_anchors,
    expand_printed_part_group,
    parse_mets_inventory,
    parse_page_spec,
    reconstruct_ipl_rows,
    validate_artifacts,
)


def mini_mets() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:mods="http://www.loc.gov/mods/v3" xmlns:xlink="http://www.w3.org/1999/xlink" LABEL="EMB CMM ATA 25-21-00 REV.4" OBJID="obj-1">
  <mets:dmdSec ID="DMD0001"><mets:mdWrap MDTYPE="MODS"><mets:xmlData><mods:mods><mods:titleInfo><mods:title>EMB CMM ATA 25-21-00 REV.4</mods:title></mods:titleInfo></mods:mods></mets:xmlData></mets:mdWrap></mets:dmdSec>
  <mets:fileSec><mets:fileGrp>
    <mets:file ID="FID0001" SIZE="3" CHECKSUM="abc" CHECKSUMTYPE="SHA-1" MIMETYPE="image/tiff"><mets:FLocat xlink:href="file://./00000001.tif"/></mets:file>
    <mets:file ID="FID0002" SIZE="4" CHECKSUM="def" CHECKSUMTYPE="SHA-1" MIMETYPE="image/tiff"><mets:FLocat xlink:href="file://./00000002.tif"/></mets:file>
  </mets:fileGrp></mets:fileSec>
  <mets:structMap TYPE="physical"><mets:div TYPE="monograph">
    <mets:div TYPE="page" ORDER="1" LABEL="1"><mets:fptr FILEID="FID0001"/></mets:div>
    <mets:div TYPE="page" ORDER="2" LABEL="2"><mets:fptr FILEID="FID0002"/></mets:div>
  </mets:div></mets:structMap>
</mets:mets>'''


def make_zip(tmp_path: Path) -> Path:
    path = tmp_path / "manual.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("metadata.xml", mini_mets())
        archive.writestr("00000001.tif", b"abc")
        archive.writestr("00000002.tif", b"defg")
    return path


def test_parse_page_spec_and_group_expansion():
    assert parse_page_spec("1-3,5,3", maximum=5) == [1, 2, 3, 5]
    assert expand_printed_part_group("120-29067-003/021/031") == [
        "120-29067-003", "120-29067-021", "120-29067-031"
    ]
    assert expand_printed_part_group("120-29067-001") == ["120-29067-001"]


def test_phase0_inventory_maps_mets_pages(tmp_path):
    inventory, summary = parse_mets_inventory(CorpusSource(make_zip(tmp_path)))
    assert summary["page_count"] == 2
    assert summary["ata"] == "25-21-00"
    assert summary["document_revision"] == "4"
    assert inventory[0]["canonical_page_id"] == "t_p_120_1176_p000001"
    assert inventory[1]["tiff_filename"] == "00000002.tif"
    assert all(row["source_exists"] and row["size_matches_metadata"] for row in inventory)


def single_parent_text() -> str:
    return '''Single Passenger Seat Structure (120-29067-001)
Figure 79
Sheet 2
79 - | 120-29067-001 STRUCTURE ASSY WS4956 A REF
1 | 120-29073-001 . STRUCTURE, LATERAL LEG WS4956 1
ATTACHING PARTS
20 | 42952-10 . FITTING, ATTACH 1
'''


def multi_parent_text() -> str:
    return '''Single Passenger Seat Structure (120-29067-003/021/031)
Figure 81
Sheet 2
81 - | 120-29067-003 STRUCTURE ASSY WS4956 A REF
- | 120-29067-021 STRUCTURE ASSY WS4956 B REF
1 | 120-29073-001 . STRUCTURE, LATERAL LEG WS4956 C 1
'''


def test_phase1_anchor_and_phase2_rows_are_extracted():
    pid = "t_p_120_1176_p000343"
    anchors = discover_assembly_anchors(pid, single_parent_text())
    rows = reconstruct_ipl_rows(pid, single_parent_text(), anchors)
    assert len(anchors) == 1
    assert anchors[0]["assembly_part_variants"] == ["120-29067-001"]
    assert anchors[0]["figure"] == "79"
    assert [row["part_number"] for row in rows] == ["120-29067-001", "120-29073-001", "42952-10"]
    assert rows[0]["row_type"] == "assembly_reference"
    assert rows[1]["quantity"] == "1"
    assert rows[2]["attaching_parts_context"] is True


def test_phase3_single_parent_is_supported_but_attaching_part_is_candidate():
    pid = "t_p_120_1176_p000343"
    anchors = discover_assembly_anchors(pid, single_parent_text())
    rows = reconstruct_ipl_rows(pid, single_parent_text(), anchors)
    relationships = build_relationships(pid, anchors, rows)
    by_child = {row["child_part"]: row for row in relationships}
    direct = by_child["120-29073-001"]
    assert direct["relationship_status"] == "source_supported"
    assert direct["direct_nha"] == "120-29067-001"
    assert direct["can_prove_direct_nha"] is True
    attaching = by_child["42952-10"]
    assert attaching["relationship_status"] == "candidate"
    assert attaching["relationship_type"] == "attaching_part_candidate"
    assert attaching["guidance_only"] is True


def test_phase3_multi_parent_group_stays_ambiguous():
    pid = "t_p_120_1176_p000349"
    anchors = discover_assembly_anchors(pid, multi_parent_text())
    rows = reconstruct_ipl_rows(pid, multi_parent_text(), anchors)
    relationships = build_relationships(pid, anchors, rows)
    row = next(item for item in relationships if item["child_part"] == "120-29073-001")
    assert row["relationship_status"] == "ambiguous"
    assert row["direct_nha"] == ""
    assert row["parent_candidates"] == ["120-29067-003", "120-29067-021", "120-29067-031"]
    assert row["can_prove_direct_nha"] is False


def test_answer_key_and_graph_only_emit_direct_edges_for_supported():
    pid = "t_p_120_1176_p000343"
    anchors = discover_assembly_anchors(pid, single_parent_text())
    rows = reconstruct_ipl_rows(pid, single_parent_text(), anchors)
    relationships = build_relationships(pid, anchors, rows)
    answer_key = build_answer_key(relationships)
    assert answer_key["direct_answer_case_count"] == 1
    assert answer_key["candidate_case_count"] == 1
    inventory = [{
        "canonical_page_id": pid,
        "truth_mode": "real_source",
        "source_truth": True,
        "source_exists": True,
        "tiff_filename": "00000343.tif",
    }]
    graph = build_graph_bundle(inventory, relationships, document_id="120-1176", revision="4")
    direct_edges = [edge for edge in graph["edges"] if edge["edge_type"] == "DIRECT_COMPONENT_OF"]
    assert len(direct_edges) == 1
    assert direct_edges[0]["from"] == "part:120-29073-001"
    assert direct_edges[0]["to"] == "part:120-29067-001"


def test_validation_rejects_cycle_and_synthetic_leak():
    inventory = [
        {"canonical_page_id": "p1", "tiff_filename": "1.tif", "source_exists": True, "truth_mode": "real_source", "source_truth": True},
        {"canonical_page_id": "p2", "tiff_filename": "2.tif", "source_exists": True, "truth_mode": "real_source", "source_truth": True},
    ]
    relationships = [
        {"relationship_id": "r1", "truth_mode": "real_source", "source_truth": True, "child_part": "A", "direct_nha": "B", "parent_candidates": ["B"], "relationship_status": "source_supported", "guidance_only": False, "can_prove_direct_nha": True, "anchor_page_id": "p1", "row_page_id": "p1"},
        {"relationship_id": "r2", "truth_mode": "real_source", "source_truth": True, "child_part": "B", "direct_nha": "A", "parent_candidates": ["A"], "relationship_status": "source_supported", "guidance_only": False, "can_prove_direct_nha": True, "anchor_page_id": "p2", "row_page_id": "p2"},
    ]
    result = validate_artifacts(inventory, [], [], relationships, expected_page_count=2)
    assert result["quality_status"] == "FAIL"
    assert any("cycle" in failure for failure in result["failures"])

    inventory[0]["truth_mode"] = "synthetic_benchmark"
    result = validate_artifacts(inventory, [], [], [], expected_page_count=2)
    assert "synthetic_or_unknown_truth_mode_in_phase0_3" in result["failures"]
# TRACE_NET_NHA_PHASE0_3_CLI_IMPORT_FIX_V1
def test_cli_entrypoints_bootstrap_repo_root_when_run_directly(tmp_path):
    repo_root = Path(__file__).resolve().parents[5]
    for relative in (
        "scripts/build/graph/build_trace_net_nha_phase0_3_v1.py",
        "scripts/maintenance/graph/check_trace_net_nha_phase0_3_v1.py",
    ):
        completed = subprocess.run(
            [sys.executable, "-B", str(repo_root / relative), "--help"],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "usage:" in completed.stdout.lower()
