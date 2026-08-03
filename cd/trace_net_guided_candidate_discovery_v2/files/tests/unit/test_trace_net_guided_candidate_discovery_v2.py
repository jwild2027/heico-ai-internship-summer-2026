import json
from pathlib import Path

import pytest

from scripts.operations.retrieval.run_trace_net_guided_candidate_discovery_v2 import (
    build_result,
    collect_evidence,
    is_probable_part_token,
    merge_candidate_routes,
    normalize_part_token,
    parse_query_clues,
    render_view,
)


def test_parse_starts_with_numbers_two_and_four():
    clues = parse_query_clues("I am looking for a part that starts with numbers 2 and 4 but I do not have the rest")
    assert clues.part_prefix == "24"
    assert clues.strict_prefix_requested is True
    assert clues.intent == "partial_part_prefix_lookup"
    assert "physical_description_or_nomenclature" in clues.missing_clues
    assert len(clues.clarifying_questions) >= 3


def test_part_token_filter_rejects_ata_and_junk():
    assert is_probable_part_token("240118-002")
    assert is_probable_part_token("120-48024-001")
    assert not is_probable_part_token("25-21-00")
    assert not is_probable_part_token("u2026")
    assert not is_probable_part_token("1001")


def test_collect_evidence_separates_strict_and_loose(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "ocr_text.txt").write_text(
        "page t_p_120_1176_p000055 ATA 25-21-00 part 240118-002 BRACKET ASSY\n"
        "page t_p_120_1176_p000056 part 120-48024-001 SEAT STRUCTURE\n",
        encoding="utf-8",
    )
    clues = parse_query_clues("part starts with 24")
    hits, evidence_count = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits, top_k=8, loose_top_k=8)
    assert evidence_count >= 2
    strict = [r for r in routes if r.route_group == "strict_prefix"]
    loose = [r for r in routes if r.route_group == "loose_contains"]
    assert any(r.candidate_part_number == "240118-002" for r in strict)
    assert any(r.candidate_part_number == "120-48024-001" for r in loose)
    assert not any(r.candidate_part_number == "120-48024-001" and r.route_group == "strict_prefix" for r in routes)


def test_render_view_explicitly_labels_no_strict_match(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "visual.json").write_text("t_p_120_1176_p000094 part 120-41824 visual candidate", encoding="utf-8")
    clues = parse_query_clues("I need a part that starts with 24")
    hits, evidence_count = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits)
    result = build_result(clues.question, routes, clues, evidence_count)
    view = render_view([result])
    assert "Strict prefix matches for 24" in view
    assert "No source-traceable selected candidates starting exactly with 24 were found." in view
    assert "Weaker related candidates" in view
    assert "does not start with 24" in view


def test_page_id_normalization_avoids_part_like_p250001(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "ocr.txt").write_text("Part 120TP250001.MCI is in ATA 25-21-00 but no explicit page id", encoding="utf-8")
    clues = parse_query_clues("part contains 25")
    hits, _ = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits)
    assert routes
    assert all(r.page_id != "t_p_120_1176_p250001" for r in routes)


def test_main_outputs_summary(tmp_path: Path):
    from scripts.operations.retrieval.run_trace_net_guided_candidate_discovery_v2 import main

    root = tmp_path / "artifacts"
    out = tmp_path / "out"
    root.mkdir()
    (root / "data.txt").write_text("t_p_120_1176_p000001 part 240999 BOLT ASSY ATA 25-21-00", encoding="utf-8")
    rc = main([
        "--artifact-root", str(root),
        "--output-dir", str(out),
        "--question", "part starts with 24",
    ])
    assert rc == 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["strict_prefix_candidate_count"] >= 1
    assert (out / "candidate_discovery_view.txt").exists()
