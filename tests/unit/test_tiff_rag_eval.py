from tiff.rag_eval import EvalQuestion, judge_answer, load_eval_questions, summarize_eval_records
from tiff.rag_answer import RagAnswer
from tiff.rag_retriever import RagSource


def test_load_eval_questions_defaults():
    questions = load_eval_questions(None)
    assert questions
    assert any("120-37313-001" in q.question for q in questions)


def test_judge_answer_passes_expected_terms_and_sources():
    source = RagSource(
        source_id="s1",
        source_type="part_catalog_clean",
        page_id="p1",
        manual_id="m1",
        publication_number="T.P. 120/1176",
        ata_code="25-21-00",
        page_label="1056",
        chunk_text="120-37313-001 HOLDER, MAGAZINE",
        matched_part_number="120-37313-001",
        part_nomenclature="HOLDER, MAGAZINE",
    )
    answer = RagAnswer(
        question="What is part number 120-37313-001?",
        answer="120-37313-001 is listed as HOLDER, MAGAZINE.",
        sources=(source,),
        used_llm=False,
        used_embeddings=False,
    )
    q = EvalQuestion(
        id="q1",
        question=answer.question,
        expected_terms=("HOLDER, MAGAZINE", "120-37313-001"),
        expected_sources=("Page 1056",),
    )
    status, missing_terms, missing_sources = judge_answer(answer, q)
    assert status == "pass"
    assert missing_terms == ()
    assert missing_sources == ()


def test_summarize_eval_records_counts():
    from tiff.rag_eval import EvalRecord

    records = [
        EvalRecord("a", "q", "a", "auto", "auto", "gemma", "bge", False, False, 0.1, 1, status="pass"),
        EvalRecord("b", "q", "a", "auto", "auto", "gemma", "bge", True, True, 0.2, 2, status="manual_review"),
    ]
    summary = summarize_eval_records(records)
    assert summary["total"] == 2
    assert summary["pass"] == 1
    assert summary["manual_review"] == 1
    assert summary["llm_used"] == 1
    assert summary["embeddings_used"] == 1
