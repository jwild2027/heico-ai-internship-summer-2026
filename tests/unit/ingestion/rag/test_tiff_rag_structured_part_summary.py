from __future__ import annotations

from tiff.rag_answer import build_structured_part_summary_answer
from tiff.rag_retriever import RagSource, RetrievalResult


def src(
    source_id: str,
    source_type: str,
    part: str | None,
    page_label: str,
    *,
    nom: str | None = None,
    seq: int = 1,
    evidence: str | None = None,
) -> RagSource:
    return RagSource(
        source_id=source_id,
        source_type=source_type,
        page_id=f"page_{source_id}",
        manual_id="t_p_120_1176",
        publication_number="T.P. 120/1176",
        ata_code="25-21-00",
        page_sequence=seq,
        page_label=page_label,
        chunk_text=evidence or f"evidence for {source_id}",
        evidence_text=evidence or f"evidence for {source_id}",
        score=146.0 if "catalog" in source_type else 80.0,
        matched_part_number=part,
        part_nomenclature=nom,
        tiff_path=f"{source_id}.tif",
        ocr_text_path=f"{source_id}.txt",
    )


def retrieval(*sources: RagSource) -> RetrievalResult:
    return RetrievalResult(
        query="Summarize the sources related to magazine holder parts.",
        sources=tuple(sources),
        used_embeddings=True,
        answer_mode="summarize",
        retrieval_mode="hybrid",
        intent="nomenclature_summary",
    )


def test_structured_summary_groups_mentions_under_matching_part_only() -> None:
    result = retrieval(
        src("cat_a", "nomenclature_catalog_clean", "120-AAA", "1056", nom="HOLDER, MAGAZINE", seq=1),
        src("cat_b", "nomenclature_catalog_clean", "120-BBB", "1082", nom="HOLDER, MAGAZINE", seq=2),
        src("mention_a", "part_mentions", "120-AAA", "1059", seq=3),
        src("mention_b", "part_mentions", "120-BBB", "1079", seq=4),
        src("wrong_part", "part_mentions", "999-XXX", "9999", seq=5),
    )
    answer = build_structured_part_summary_answer(result.query, result)
    assert answer is not None
    assert "120-AAA - HOLDER, MAGAZINE" in answer
    assert "120-BBB - HOLDER, MAGAZINE" in answer
    assert "Page 1059" in answer
    assert "Page 1079" in answer
    assert "999-XXX" not in answer
    a_section = answer.split("2. 120-BBB", 1)[0]
    b_section = answer.split("2. 120-BBB", 1)[1]
    assert "Page 1059" in a_section
    assert "Page 1079" not in a_section
    assert "Page 1079" in b_section


def test_structured_summary_lists_keyword_and_vector_only_as_supplemental() -> None:
    result = retrieval(
        src("cat_a", "nomenclature_catalog_clean", "120-AAA", "1056", nom="HOLDER, MAGAZINE", seq=1),
        src("cat_b", "nomenclature_catalog_clean", "120-BBB", "1082", nom="HOLDER, MAGAZINE", seq=2),
        src("kw", "keyword-or", None, "1163", seq=8),
        src("vec", "vector", None, "1188", seq=9),
    )
    answer = build_structured_part_summary_answer(result.query, result)
    assert answer is not None
    assert "Supplemental related pages from keyword/vector retrieval:" in answer
    assert "Page 1163 (keyword-or)" in answer
    assert "Page 1188 (vector)" in answer
    assert "not catalog proof" in answer


def test_structured_summary_surfaces_item_not_illustrated_note() -> None:
    result = retrieval(
        src(
            "cat_a",
            "nomenclature_catalog_clean",
            "120-AAA",
            "1056",
            nom="HOLDER, MAGAZINE",
            seq=1,
            evidence="120-AAA HOLDER, MAGAZINE",
        ),
        src(
            "cat_b",
            "nomenclature_catalog_clean",
            "120-BBB",
            "1082",
            nom="HOLDER, MAGAZINE",
            seq=2,
            evidence="120-BBB HOLDER, MAGAZINE -ITEM NOT ILLUSTRATED",
        ),
    )
    answer = build_structured_part_summary_answer(result.query, result)
    assert answer is not None
    assert "ITEM NOT ILLUSTRATED" in answer
