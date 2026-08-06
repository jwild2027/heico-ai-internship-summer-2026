import json
from pathlib import Path

from scripts.benchmark.context.run_trace_net_tiff_content_gemma_evidence_pack_fixed50_v1 import (
    build_local_index,
    load_questions,
    make_prompt,
    make_terms,
    retrieve_evidence,
)


def test_load_questions_accepts_list_and_dict(tmp_path: Path):
    p = tmp_path / "q.json"
    p.write_text(json.dumps([{"question_id":"q01","question":"Which page contains Figure 69?"}]), encoding="utf-8")
    assert load_questions(p)[0]["question_id"] == "q01"
    p.write_text(json.dumps({"questions":[{"question_id":"q02","question":"What ATA number starts with 2?"}]}), encoding="utf-8")
    assert load_questions(p)[0]["question_id"] == "q02"


def test_make_terms_expands_figure_and_ata():
    terms = make_terms("I need an ATA number starting with 2 near Figure 69")
    assert "figure 69" in terms
    assert "ata" in terms
    assert "25-21-00" in terms


def test_index_and_retrieve_evidence_from_json(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "visual_understanding.json").write_text(json.dumps({
        "page_id": "t_p_120_1176_p000069",
        "figure_title": "Figure 69 Paper Towel Dispenser",
        "nomenclature": "PAPER TOWEL DISPENSER",
        "part_number": "120-36833-001",
    }), encoding="utf-8")
    records = build_local_index(root)
    got = retrieve_evidence(records, "What nomenclature is associated with Figure 69?", top_k=5)
    assert got
    assert any("PAPER TOWEL" in r.text or "Figure 69" in r.text for r in got)


def test_prompt_contains_evidence_not_answer_key(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "ocr.json").write_text(json.dumps({"page_id":"t_p_120_1176_p000003", "text":"ATA 25-21-00 REV.4"}), encoding="utf-8")
    records = build_local_index(root)
    evidence = retrieve_evidence(records, "I need an ATA number that starts with 2. What page and document is that?", top_k=3)
    prompt = make_prompt("q01", "I need an ATA number that starts with 2. What page and document is that?", evidence)
    assert "SOURCE EVIDENCE SNIPPETS" in prompt
    assert "ATA 25-21-00" in prompt
    assert "expected_answer" not in prompt.lower()
