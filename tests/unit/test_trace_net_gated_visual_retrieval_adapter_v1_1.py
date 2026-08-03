from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/benchmark/visual/build_trace_net_gated_visual_retrieval_adapter_v1_1.py")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )


def test_gated_visual_retrieval_adapter_builds_search_ready_and_review_docs(tmp_path: Path) -> None:
    confirmed = tmp_path / "confirmed.jsonl"
    review = tmp_path / "review.jsonl"
    out = tmp_path / "out"

    write_jsonl(
        confirmed,
        [
            {
                "page_id": "p1",
                "visual_summary": {
                    "summary": "Technical drawing showing a passenger seat assembly with callouts."
                },
                "visual_ids": ["vis_region__p1__abc"],
                "identifiers": {
                    "figure_refs": ["figure 601"],
                    "part_numbers": ["120-12345-001"],
                    "callouts": ["1", "2"],
                },
                "evidence_status": {"source_trace_ready": True, "citation_ready": True},
                "meaningful_image_gate": {
                    "detector_route": "image_visual",
                    "visual_subtype": "confirmed_diagram_dominant",
                    "meaningful_image_visual": True,
                    "route_confidence": 0.8,
                    "route_reasons": ["old_image_route_with_strong_diagram_signal"],
                },
            }
        ],
    )
    write_jsonl(
        review,
        [
            {
                "page_id": "p2",
                "visual_summary": {"summary": "Borderline visual candidate."},
                "meaningful_image_gate": {
                    "detector_route": "visual_candidate_review",
                    "visual_subtype": "borderline_old_image_visual",
                    "meaningful_image_visual": False,
                    "route_confidence": 0.5,
                },
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--confirmed-image-context-jsonl",
            str(confirmed),
            "--visual-candidate-review-jsonl",
            str(review),
            "--output-dir",
            str(out),
            "--min-confirmed-contexts",
            "1",
            "--min-search-ready-documents",
            "1",
            "--min-pages-with-summary",
            "1",
            "--max-empty-search-text",
            "0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["summary"]["search_ready_document_count"] == 1
    assert summary["summary"]["review_only_document_count"] == 1
    assert summary["summary"]["pages_with_part_numbers"] == 1
    assert summary["summary"]["final_answer_allowed_true_count"] == 0
    assert summary["summary"]["source_truth_mutation_allowed_count"] == 0

    docs = [
        json.loads(x)
        for x in (out / "trace_net_gated_visual_retrieval_documents_v1_1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    assert docs[0]["search_ready"] is True
    assert docs[0]["review_only"] is False
    assert docs[0]["retrieval_guidance"]["visual_observation_is_candidate_only"] is True
    assert "passenger seat assembly" in docs[0]["search_text"]
    assert "120-12345-001" in docs[0]["search_text"]


def test_gated_visual_retrieval_adapter_uses_evidence_fallback_summary(tmp_path: Path) -> None:
    confirmed = tmp_path / "confirmed.jsonl"
    out = tmp_path / "out"

    write_jsonl(
        confirmed,
        [
            {
                "page_id": "p9",
                "identifiers": {
                    "figure_refs": ["figure 601"],
                    "part_numbers": ["120-99999-001"],
                },
                "meaningful_image_gate": {
                    "detector_route": "image_visual",
                    "visual_subtype": "confirmed_diagram_dominant",
                    "meaningful_image_visual": True,
                    "route_confidence": 0.8,
                },
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--confirmed-image-context-jsonl",
            str(confirmed),
            "--output-dir",
            str(out),
            "--min-confirmed-contexts",
            "1",
            "--min-search-ready-documents",
            "1",
            "--min-pages-with-summary",
            "1",
            "--max-empty-search-text",
            "0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    docs = [
        json.loads(x)
        for x in (out / "trace_net_gated_visual_retrieval_documents_v1_1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    assert docs[0]["visual_summary_source"] == "deterministic_evidence_fallback"
    assert "figure 601" in docs[0]["search_text"]
    assert "120-99999-001" in docs[0]["search_text"]


def test_gated_visual_retrieval_adapter_fails_empty_confirmed_when_required(tmp_path: Path) -> None:
    confirmed = tmp_path / "confirmed.jsonl"
    out = tmp_path / "out"
    write_jsonl(confirmed, [])

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--confirmed-image-context-jsonl",
            str(confirmed),
            "--output-dir",
            str(out),
            "--min-confirmed-contexts",
            "1",
            "--min-search-ready-documents",
            "1",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "FAIL"
