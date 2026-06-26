from __future__ import annotations

from tiff.trace_net_fishnet_ocr_grid_v1 import evaluate_quality


def _payload() -> dict:
    return {
        "quality_status": "PASS",
        "summary": {
            "source_page_count": 2,
            "page_record_count": 2,
            "grid_rows": 2,
            "grid_cols": 3,
            "expected_cells_per_page": 6,
            "total_cell_count": 12,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "records": [
            {"page_id": "p1", "cell_count": 6},
            {"page_id": "p2", "cell_count": 6},
        ],
        "errors": [],
    }


def test_evaluate_quality_passes_with_required_checks() -> None:
    quality = evaluate_quality(
        _payload(),
        require_page_count=2,
        min_page_records=2,
        min_total_cell_records=12,
        min_grid_rows=2,
        min_grid_cols=3,
        max_unsafe=0,
        require_all_pages_have_grid=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
    )
    assert quality["quality_status"] == "PASS"
    assert all(check["passed"] for check in quality["checks"])


def test_evaluate_quality_fails_when_unsafe_count_is_nonzero() -> None:
    payload = _payload()
    payload["summary"]["unsafe_record_count"] = 1
    quality = evaluate_quality(payload, require_page_count=2, max_unsafe=0)
    assert quality["quality_status"] == "FAIL"
    assert any(check["name"] == "max_unsafe" and not check["passed"] for check in quality["checks"])


def test_evaluate_quality_fails_when_ocr_failures_are_forbidden() -> None:
    payload = _payload()
    payload["summary"]["ocr_ok_page_count"] = 0
    payload["summary"]["ocr_failed_page_count"] = 2
    payload["summary"]["ocr_unavailable_page_count"] = 0

    quality = evaluate_quality(
        payload,
        require_page_count=2,
        require_no_ocr_failures=True,
        min_ocr_ok_pages=1,
        max_ocr_failed_pages=0,
    )

    assert quality["quality_status"] == "FAIL"
    failed_names = {check["name"] for check in quality["checks"] if not check["passed"]}
    assert "require_no_ocr_failures" in failed_names
    assert "min_ocr_ok_pages" in failed_names
    assert "max_ocr_failed_pages" in failed_names


def test_evaluate_quality_can_limit_image_visual_ratio() -> None:
    payload = _payload()
    payload["summary"]["route_candidate_counts"] = {"image_visual": 2}

    quality = evaluate_quality(payload, max_image_visual_ratio=0.25)

    assert quality["quality_status"] == "FAIL"
    assert any(check["name"] == "max_image_visual_ratio" and not check["passed"] for check in quality["checks"])


def test_evaluate_quality_fails_when_ocr_is_empty_but_text_required() -> None:
    payload = _payload()
    payload["summary"]["ocr_ok_page_count"] = 2
    payload["summary"]["ocr_empty_page_count"] = 2
    payload["summary"]["ocr_nonempty_page_count"] = 0
    payload["summary"]["total_ocr_text_char_count"] = 0

    quality = evaluate_quality(
        payload,
        require_page_count=2,
        min_ocr_nonempty_pages=1,
        min_total_ocr_text_chars=10,
        max_ocr_empty_pages=0,
        require_no_ocr_empty=True,
    )

    assert quality["quality_status"] == "FAIL"
    failed_names = {check["name"] for check in quality["checks"] if not check["passed"]}
    assert "min_ocr_nonempty_pages" in failed_names
    assert "min_total_ocr_text_chars" in failed_names
    assert "max_ocr_empty_pages" in failed_names
    assert "require_no_ocr_empty" in failed_names


def test_evaluate_quality_can_require_word_boxes() -> None:
    payload = _payload()
    payload["summary"]["total_ocr_word_box_count"] = 0

    quality = evaluate_quality(payload, min_ocr_word_boxes=1)

    assert quality["quality_status"] == "FAIL"
    assert any(check["name"] == "min_ocr_word_boxes" and not check["passed"] for check in quality["checks"])



def test_evaluate_quality_can_limit_table_ratio() -> None:
    payload = _payload()
    payload["summary"]["route_candidate_counts"] = {"table": 2}

    quality = evaluate_quality(payload, max_table_ratio=0.25)

    assert quality["quality_status"] == "FAIL"
    assert any(check["name"] == "max_table_ratio" and not check["passed"] for check in quality["checks"])


def test_evaluate_quality_can_limit_review_required_ratio() -> None:
    payload = _payload()
    payload["summary"]["route_candidate_counts"] = {"review_required": 2}

    quality = evaluate_quality(payload, max_review_required_ratio=0.25)

    assert quality["quality_status"] == "FAIL"
    assert any(check["name"] == "max_review_required_ratio" and not check["passed"] for check in quality["checks"])
