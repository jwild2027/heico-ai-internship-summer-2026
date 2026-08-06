from __future__ import annotations

from tiff.rag_answer import build_rag_prompt, pack_sources_for_llm
from tiff.rag_retriever import RagSource


def src(source_id: str, source_type: str, page_id: str, part: str | None = None, nom: str | None = None, seq: int = 1) -> RagSource:
    return RagSource(
        source_id=source_id,
        source_type=source_type,
        page_id=page_id,
        manual_id="m1",
        publication_number="T.P. 120/1176",
        ata_code="25-21-00",
        page_sequence=seq,
        page_label=str(1000 + seq),
        chunk_text=f"evidence {source_id}",
        score=100.0 if "catalog" in source_type else 80.0,
        matched_part_number=part,
        part_nomenclature=nom,
        evidence_text=f"evidence {source_id}",
        tiff_path=f"{page_id}.tif",
        ocr_text_path=f"{page_id}.txt",
    )


def test_pack_sources_groups_mentions_by_catalog_part() -> None:
    raw = [
        src("kw", "keyword-or", "kw", seq=20),
        src("cat_a", "nomenclature_catalog_clean", "cat_a", "120-AAA", "HOLDER, MAGAZINE", 1),
        src("cat_b", "nomenclature_catalog_clean", "cat_b", "120-BBB", "HOLDER, MAGAZINE", 2),
        src("mention_b", "part_mentions", "mention_b", "120-BBB", None, 3),
        src("mention_a", "part_mentions", "mention_a", "120-AAA", None, 4),
        src("unrelated", "part_mentions", "unrelated", "999-XXX", None, 5),
        src("vec", "vector", "vec", seq=30),
    ]
    packed = pack_sources_for_llm(raw, answer_mode="nomenclature_summary", top_k=3)
    parts = [s.matched_part_number for s in packed]
    assert parts[:2] == ["120-AAA", "120-BBB"]
    assert "999-XXX" not in parts
    assert any(s.source_type == "keyword-or" for s in packed)
    assert any(s.source_type == "vector" for s in packed)


def test_prompt_includes_structured_evidence_map_with_per_part_citations() -> None:
    packed = pack_sources_for_llm(
        [
            src("cat_a", "nomenclature_catalog_clean", "cat_a", "120-AAA", "HOLDER, MAGAZINE", 1),
            src("mention_a", "part_mentions", "mention_a", "120-AAA", None, 4),
            src("cat_b", "nomenclature_catalog_clean", "cat_b", "120-BBB", "HOLDER, MAGAZINE", 2),
            src("mention_b", "part_mentions", "mention_b", "120-BBB", None, 3),
        ],
        answer_mode="nomenclature_summary",
        top_k=3,
    )
    messages = build_rag_prompt("Summarize magazine holder parts", packed)
    user_text = messages[1]["content"]
    system_text = messages[0]["content"]
    assert "STRUCTURED EVIDENCE MAP" in user_text
    assert "PART 120-AAA: HOLDER, MAGAZINE" in user_text
    assert "PART 120-BBB: HOLDER, MAGAZINE" in user_text
    assert "never attach a citation to a part number" in system_text
