import json
from pathlib import Path

from scripts.operations.retrieval.run_trace_net_guided_candidate_discovery_v3 import (
    build_result,
    classify_candidate_quality,
    collect_evidence,
    is_probable_part_token,
    merge_candidate_routes,
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


def test_part_token_filter_rejects_ata_decimal_hash_and_junk():
    assert is_probable_part_token("240118-002")
    assert is_probable_part_token("120-48024-001")
    assert not is_probable_part_token("25-21-00")
    assert not is_probable_part_token("u2026")
    assert not is_probable_part_token("1001")
    assert not is_probable_part_token("24.689877")
    assert not is_probable_part_token("244cc597a1a4730bbd5ba454475e853d9bc9e424741a81fdd1a110fa824566cb")


def test_context_quality_rejects_short_numeric_and_accepts_structured():
    q, reason = classify_candidate_quality("24143", "page text with no part_number field", "ocr.txt")
    assert q == "weak_token"
    assert "short numeric" in reason
    q2, _ = classify_candidate_quality("240118-002", "part_number 240118-002 BRACKET ASSY", "ocr.txt")
    assert q2 == "valid_part_like"
    q3, _ = classify_candidate_quality("MS24693-C5", "part number MS24693-C5", "ipl.csv")
    assert q3 == "valid_part_like"


def test_collect_evidence_filters_noisy_strict_and_keeps_valid_loose(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "ocr_text.txt").write_text(
        "page t_p_120_1176_p000082 token 24.689877 noise\n"
        "page t_p_120_1176_p000034 token 24270 random\n"
        "page t_p_120_1176_p000245 token 244cc597a1a4730bbd5ba454475e853d9bc9e424741a81fdd1a110fa824566cb hash\n"
        "page t_p_120_1176_p000055 part_number 120-48024-001 RING LOCKING ATA 25-21-00\n",
        encoding="utf-8",
    )
    clues = parse_query_clues("part starts with 24")
    hits, evidence_count, rejected, weak = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits, top_k=8, loose_top_k=8)
    assert evidence_count >= 1
    assert rejected >= 1
    assert weak >= 1
    assert not [r for r in routes if r.route_group == "strict_prefix"]
    assert any(r.candidate_part_number == "120-48024-001" and r.route_group == "loose_contains" for r in routes)


def test_valid_strict_prefix_survives_validation(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "data.txt").write_text("t_p_120_1176_p000001 part_number 240118-002 BRACKET ASSY ATA 25-21-00", encoding="utf-8")
    clues = parse_query_clues("part starts with 24")
    hits, evidence_count, rejected, weak = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits)
    strict = [r for r in routes if r.route_group == "strict_prefix"]
    assert evidence_count >= 1
    assert any(r.candidate_part_number == "240118-002" for r in strict)
    assert all(r.candidate_quality == "valid_part_like" for r in routes)


def test_render_view_explicitly_labels_no_strict_match(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "visual.json").write_text("t_p_120_1176_p000094 part_number 120-41824-007 visual candidate", encoding="utf-8")
    clues = parse_query_clues("I need a part that starts with 24")
    hits, evidence_count, rejected, weak = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits)
    result = build_result(clues.question, routes, clues, evidence_count, rejected, weak)
    view = render_view([result])
    assert "Strict prefix matches for 24" in view
    assert "No source-traceable selected candidates starting exactly with 24 were found." in view
    assert "Weaker related candidates" in view
    assert "does not start with 24" in view
    assert "Candidate quality: valid_part_like" in view


def test_summary_pollution_is_not_used_as_v2_summary(tmp_path: Path):
    root = tmp_path / "artifacts"
    (root / "answer_context_pack").mkdir(parents=True)
    (root / "page_context_v2").mkdir()
    (root / "answer_context_pack" / "fake_v2.json").write_text('{"user_query":"Find part number 120-36834-509", "query_plan": {}} t_p_120_1176_p000001 part_number 240118-002', encoding="utf-8")
    (root / "page_context_v2" / "page.json").write_text('t_p_120_1176_p000001 page context v2 says this page contains a bracket part candidate. part_number 240118-002', encoding="utf-8")
    clues = parse_query_clues("part starts with 24")
    hits, _, _, _ = collect_evidence(root, clues)
    routes = merge_candidate_routes(hits)
    assert routes
    assert "user_query" not in routes[0].v2_summary
    assert "page context v2" in routes[0].v2_summary


def test_main_outputs_summary_with_noise_counts(tmp_path: Path):
    from scripts.operations.retrieval.run_trace_net_guided_candidate_discovery_v3 import main

    root = tmp_path / "artifacts"
    out = tmp_path / "out"
    root.mkdir()
    (root / "data.txt").write_text("t_p_120_1176_p000001 part_number 240999-001 BOLT ASSY ATA 25-21-00 24.12345", encoding="utf-8")
    rc = main([
        "--artifact-root", str(root),
        "--output-dir", str(out),
        "--question", "part starts with 24",
    ])
    assert rc == 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["strict_prefix_candidate_count"] >= 1
    assert "rejected_noise_token_count" in summary
    assert (out / "candidate_discovery_view.txt").exists()
