from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_embedding_candidates_v1 import (
    DEFAULT_CANDIDATES_FILE,
    DEFAULT_CONTEXT_HELPER_QUALITY_FILE,
    DEFAULT_QUALITY_FILE,
    build_embedding_candidate_bundle,
    build_embedding_candidate_records,
    evaluate_embedding_candidate_quality,
    main_quality,
    write_embedding_candidate_outputs,
    write_quality_result,
)


def make_rag(page: int, bucket: str = "source_text_evidence") -> dict:
    return {
        "chunk_id": f"chunk-{bucket}-{page}",
        "candidate_id": f"cand-{bucket}-{page}",
        "page_id": f"t_p_120_1176_p{page:06d}",
        "rag_bucket": bucket,
        "chunk_text": f"Safe candidate text for page {page} bucket {bucket}.",
        "final_trust_tier": "A",
        "final_rag_action": "include",
    }


def make_citation(page: int, bucket: str = "source_text_evidence") -> dict:
    return {
        "citation_id": f"cite-{bucket}-{page}",
        "candidate_id": f"cand-{bucket}-{page}",
        "page_id": f"t_p_120_1176_p{page:06d}",
        "source_url": f"https://example.test/source/page-{page}",
    }


def make_helper(page: int) -> dict:
    return {
        "helper_id": f"ctx-helper-{page}",
        "source_context_id": f"ctx-{page}",
        "page_id": f"t_p_120_1176_p{page:06d}",
        "record_type": "context_retrieval_helper",
        "safety_bucket": "context_retrieval_helper",
        "authority": "retrieval_helper_only",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "helper_text": f"TRACE-Net helper for page {page}; placards; labels; part lookup.",
    }


def make_baseline(tmp_path: Path, status: str = "PASS") -> Path:
    checkpoint = {
        "checkpoint_name": "trace_net_graph_ui_context_v2_nomenclature_baseline_v1",
        "checkpoint_sha256": "abc123",
        "retrieval_safety_baseline": {"rag_candidate_count": 1426, "source_citation_count": 1426},
    }
    checkpoint_path = tmp_path / "trace_net_graph_baseline_checkpoint_v1.json"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    quality_path = tmp_path / "trace_net_graph_baseline_checkpoint_v1_quality.json"
    quality_path.write_text(json.dumps({"status": status}), encoding="utf-8")
    return checkpoint_path


def make_context_helpers_file(tmp_path: Path, status: str = "PASS") -> Path:
    helpers_path = tmp_path / "trace_net_context_retrieval_helpers_v1.json"
    helpers_path.write_text(json.dumps({"records": [make_helper(i) for i in range(1, 4)]}), encoding="utf-8")
    quality_path = tmp_path / DEFAULT_CONTEXT_HELPER_QUALITY_FILE
    quality_path.write_text(json.dumps({"status": status}), encoding="utf-8")
    return helpers_path


def build_small_safe_records() -> tuple[list[dict], list[dict]]:
    rag_rows = [make_rag(1), make_rag(2, "verified_part_evidence"), make_rag(3, "derived_context")]
    citations = [make_citation(1), make_citation(2, "verified_part_evidence"), make_citation(3, "derived_context")]
    helpers = [make_helper(1), make_helper(2), make_helper(3)]
    return build_embedding_candidate_records(rag_rows, helpers, citation_rows=citations)


def test_evaluate_quality_passes_for_safe_records(tmp_path: Path) -> None:
    records, rejected = build_small_safe_records()
    baseline_path = make_baseline(tmp_path, "PASS")
    helpers_path = make_context_helpers_file(tmp_path, "PASS")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    quality = evaluate_embedding_candidate_quality(
        records,
        rejected,
        baseline_checkpoint=baseline,
        baseline_checkpoint_path=baseline_path,
        context_helpers_path=helpers_path,
        min_safe_candidates=6,
        min_rag_candidates=3,
        min_context_helper_candidates=3,
        min_pages_with_candidates=3,
        require_pages=[1, 2, 3],
        require_baseline_quality_pass=True,
        require_context_helper_quality_pass=True,
    )
    assert quality.status == "PASS"
    assert quality.summary["unsafe_embedding_candidate_count"] == 0
    assert quality.summary["baseline_quality_status"] == "PASS"
    assert quality.summary["context_helper_quality_status"] == "PASS"


def test_evaluate_quality_fails_when_vector_payload_can_answer() -> None:
    records, rejected = build_small_safe_records()
    records[0]["can_answer_directly"] = True
    quality = evaluate_embedding_candidate_quality(
        records,
        rejected,
        min_safe_candidates=6,
        min_rag_candidates=3,
        min_context_helper_candidates=3,
        min_pages_with_candidates=3,
        require_pages=[1, 2, 3],
    )
    assert quality.status == "FAIL"
    assert quality.summary["can_answer_directly_true_count"] == 1
    assert quality.summary["unsafe_embedding_candidate_count"] >= 1


def test_evaluate_quality_fails_when_context_page_missing() -> None:
    rag_rows = [make_rag(1), make_rag(2), make_rag(3)]
    citations = [make_citation(1), make_citation(2), make_citation(3)]
    helpers = [make_helper(1), make_helper(2)]
    records, rejected = build_embedding_candidate_records(rag_rows, helpers, citation_rows=citations)
    quality = evaluate_embedding_candidate_quality(
        records,
        rejected,
        min_safe_candidates=5,
        min_rag_candidates=3,
        min_context_helper_candidates=2,
        min_pages_with_candidates=3,
        require_pages=[1, 2, 3],
    )
    assert quality.status == "FAIL"
    assert quality.summary["required_context_helper_page_missing_count"] == 1
    assert quality.summary["required_context_helper_page_coverage"]["missing_page_numbers"] == [3]


def test_write_quality_result_creates_json(tmp_path: Path) -> None:
    records, rejected = build_small_safe_records()
    quality = evaluate_embedding_candidate_quality(
        records,
        rejected,
        min_safe_candidates=6,
        min_rag_candidates=3,
        min_context_helper_candidates=3,
        min_pages_with_candidates=3,
        require_pages=[1, 2, 3],
    )
    output_path = tmp_path / DEFAULT_QUALITY_FILE
    write_quality_result(quality, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["summary"]["safe_embedding_candidate_count"] == 6


def test_main_quality_passes_and_writes_json(tmp_path: Path, capsys) -> None:
    rag_rows = [make_rag(1), make_rag(2), make_rag(3)]
    citations = [make_citation(1), make_citation(2), make_citation(3)]
    helpers = [make_helper(1), make_helper(2), make_helper(3)]
    bundle = build_embedding_candidate_bundle(rag_rows, helpers, citation_rows=citations, require_pages=[1, 2, 3])
    write_embedding_candidate_outputs(bundle, tmp_path)
    baseline_path = make_baseline(tmp_path, "PASS")
    helpers_path = make_context_helpers_file(tmp_path, "PASS")
    code = main_quality(
        [
            "--candidates-path",
            str(tmp_path / DEFAULT_CANDIDATES_FILE),
            "--baseline-checkpoint",
            str(baseline_path),
            "--context-helpers",
            str(helpers_path),
            "--require-baseline-quality-pass",
            "--require-context-helper-quality-pass",
            "--require-first-pages",
            "1-3",
            "--min-safe-candidates",
            "6",
            "--min-rag-candidates",
            "3",
            "--min-context-helper-candidates",
            "3",
            "--min-pages-with-candidates",
            "3",
            "--write-json",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Status: PASS" in output
    assert (tmp_path / DEFAULT_QUALITY_FILE).exists()


def test_main_quality_fails_for_source_truth_mutation(tmp_path: Path, capsys) -> None:
    records, _rejected = build_small_safe_records()
    records[0]["can_mutate_source_truth"] = True
    candidates_path = tmp_path / DEFAULT_CANDIDATES_FILE
    candidates_path.write_text(json.dumps({"records": records}), encoding="utf-8")
    code = main_quality(
        [
            "--candidates-path",
            str(candidates_path),
            "--require-first-pages",
            "1-3",
            "--min-safe-candidates",
            "6",
            "--min-rag-candidates",
            "3",
            "--min-context-helper-candidates",
            "3",
            "--min-pages-with-candidates",
            "3",
        ]
    )
    assert code == 1
    output = capsys.readouterr().out
    assert "Status: FAIL" in output
    assert "unsafe_embedding_candidate_count" in output
