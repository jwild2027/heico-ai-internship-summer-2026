import json
import subprocess
import sys
from pathlib import Path

from scripts.run_trace_net_guided_candidate_discovery_v1 import (
    build_discovery_result,
    detect_clues,
    extract_parts,
    is_good_part,
)


def test_detect_partial_prefix_from_numbers_2_and_4():
    clues = detect_clues("I am looking for a part that starts with numbers 2 and 4 but dont have the rest")
    assert clues.intent == "partial_part_lookup"
    assert clues.part_prefix == "24"
    assert clues.part_digits == ["2", "4"]
    assert "full_part_number" in __import__("scripts.run_trace_net_guided_candidate_discovery_v1", fromlist=["missing_clues"]).missing_clues(clues)


def test_part_filter_rejects_ata_and_junk():
    assert not is_good_part("25-21-00")
    assert not is_good_part("u2026")
    assert not is_good_part("1001")
    assert is_good_part("120-36833-001")
    assert is_good_part("PE21052-2")


def test_extract_parts_filters_ata_but_keeps_real_parts():
    text = "ATA 25-21-00 includes 120-36833-001 and PE21052-2 but not u2026 or 1001"
    parts = extract_parts(text)
    assert "120-36833-001" in parts
    assert "PE21052-2" in parts
    assert "25-21-00" not in parts
    assert "1001" not in parts


def test_build_candidate_routes_from_sample_artifacts(tmp_path):
    root = tmp_path / "artifact"
    (root / "ocr_route_scan_pack_tesseract_full" / "ocr_text").mkdir(parents=True)
    (root / "page_context_v2").mkdir()
    (root / "page_context_v3").mkdir()
    (root / "table_route").mkdir()
    (root / "ocr_route_scan_pack_tesseract_full" / "ocr_text" / "t_p_120_1176_p000024.txt").write_text(
        "t_p_120_1176_p000024 ATA 25-21-00 243904 BOLT SEAT ASSY bracket text", encoding="utf-8"
    )
    (root / "page_context_v2" / "trace_net_page_context_v2_records.jsonl").write_text(
        json.dumps({"page_id": "t_p_120_1176_p000024", "summary": "V2: page appears to discuss seat assembly parts and bolts", "part": "243904"}) + "\n",
        encoding="utf-8",
    )
    (root / "page_context_v3" / "trace_net_page_context_v3_records.jsonl").write_text(
        json.dumps({"page_id": "t_p_120_1176_p000024", "summary": "V3: part-like token 243904 appears near seat nomenclature", "part": "243904"}) + "\n",
        encoding="utf-8",
    )
    (root / "table_route" / "records.csv").write_text(
        "page_id,part,nomenclature\nt_p_120_1176_p000024,243904,BOLT SEAT ASSY\n", encoding="utf-8"
    )
    result = build_discovery_result("q01", "I am looking for a part that starts with numbers 2 and 4 but do not have the rest", root, top_k=5, max_records=1000)
    assert result["intent"] == "partial_part_lookup"
    assert result["final_answer_allowed"] is False
    assert result["candidate_routes"]
    first = result["candidate_routes"][0]
    assert first["candidate_part_number"] == "243904"
    assert first["ata"] == "25-21-00"
    assert "t_p_120_1176_p000024" in first["candidate_pages"]
    assert result["clarifying_questions"]


def test_cli_writes_outputs(tmp_path):
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "records.txt").write_text("t_p_120_1176_p000024 ATA 25-21-00 243904 BOLT SEAT ASSY", encoding="utf-8")
    out = tmp_path / "out"
    cmd = [
        sys.executable,
        "-B",
        "scripts/run_trace_net_guided_candidate_discovery_v1.py",
        "--artifact-root",
        str(root),
        "--output-dir",
        str(out),
        "--question",
        "part starts with 24",
        "--top-k",
        "3",
    ]
    p = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True, check=True)
    assert "quality_status=PASS" in p.stdout
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["final_answer_allowed_count"] == 0
    assert (out / "candidate_discovery_view.txt").exists()
