from tiff.page_context_v2_quality import run_quality


def test_quality_passes_safe_records():
    records = [{
        "page_id": "p1",
        "retrieval_cues": ["seat"],
        "answerable_questions": ["Where is seat described?"],
        "supporting_ocr_phrases": ["PASSENGER SEAT"],
        "authority": {"can_answer_directly": False, "canonical_source_truth": False, "source_truth_mutation_allowed": False},
    }]
    report = run_quality(records, {"min_context_records": 1, "min_contexts_with_retrieval_cues": 1, "min_contexts_with_answerable_questions": 1})
    assert report["status"] == "OK"


def test_quality_fails_direct_answer_context():
    records = [{"page_id": "p1", "authority": {"can_answer_directly": True}}]
    report = run_quality(records, {"min_context_records": 1, "max_direct_answer_context_records": 0})
    assert report["status"] == "FAIL"
