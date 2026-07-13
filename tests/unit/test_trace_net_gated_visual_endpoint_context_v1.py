from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_gated_visual_endpoint_context_v1.py")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )


def test_gated_visual_endpoint_context_builds_payload_and_excludes_review_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    review = tmp_path / "review.jsonl"
    out = tmp_path / "out"

    write_jsonl(
        docs,
        [
            {
                "document_id": "doc1",
                "page_id": "p001",
                "search_ready": True,
                "review_only": False,
                "visual_route": "image_visual",
                "visual_subtype": "confirmed_diagram_dominant",
                "route_confidence": 0.8,
                "visual_summaries": ["Technical drawing showing passenger seat assembly callouts."],
                "identifiers": {
                    "part_numbers": ["120-12345-001"],
                    "figure_refs": ["figure 601"],
                    "callouts": ["1", "2"],
                    "nomenclature": ["seat assembly"],
                },
                "search_text": "passenger seat assembly diagram callout figure 601 part 120-12345-001",
                "citation_ready": True,
                "source_trace_ready": True,
            }
        ],
    )
    write_jsonl(
        review,
        [
            {
                "document_id": "review1",
                "page_id": "p999",
                "search_ready": False,
                "review_only": True,
                "visual_route": "visual_candidate_review",
                "visual_subtype": "borderline_old_image_visual",
                "search_text": "passenger seat assembly review only should not be used",
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--gated-visual-retrieval-documents-jsonl",
            str(docs),
            "--review-only-documents-jsonl",
            str(review),
            "--output-dir",
            str(out),
            "--query",
            "Find the passenger seat assembly diagram with callouts",
            "--top-k",
            "5",
            "--min-retrieval-documents",
            "1",
            "--min-query-count",
            "1",
            "--min-triggered-query-count",
            "1",
            "--min-successful-query-count",
            "1",
            "--min-total-citations",
            "1",
            "--min-cited-pages",
            "1",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["summary"]["review_only_docs_used_for_context_count"] == 0
    assert summary["summary"]["final_answer_allowed_true_count"] == 0
    assert summary["endpoint_contract"]["route_name"] == "gated_image_visual"

    payloads = [
        json.loads(x)
        for x in (out / "trace_net_gated_visual_endpoint_context_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    assert payloads[0]["route_triggered"] is True
    assert payloads[0]["citation_count"] == 1
    assert payloads[0]["citations"][0]["page_id"] == "p001"
    assert payloads[0]["answer_contract"]["final_answer_allowed"] is False
    assert payloads[0]["endpoint_payload_type"] == "trace_net_route_context"
    assert all(c["page_id"] != "p999" for c in payloads[0]["citations"])


def test_gated_visual_endpoint_context_does_not_trigger_for_plain_nonvisual_query(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    out = tmp_path / "out"

    write_jsonl(
        docs,
        [
            {
                "document_id": "doc1",
                "page_id": "p001",
                "search_ready": True,
                "review_only": False,
                "visual_route": "image_visual",
                "visual_subtype": "confirmed_diagram_dominant",
                "search_text": "seat assembly diagram",
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--gated-visual-retrieval-documents-jsonl",
            str(docs),
            "--output-dir",
            str(out),
            "--query",
            "What is the torque limit",
            "--min-retrieval-documents",
            "1",
            "--min-query-count",
            "1",
            "--min-triggered-query-count",
            "0",
            "--min-successful-query-count",
            "0",
            "--min-total-citations",
            "0",
            "--min-cited-pages",
            "0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payloads = [
        json.loads(x)
        for x in (out / "trace_net_gated_visual_endpoint_context_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    assert payloads[0]["route_triggered"] is False
    assert payloads[0]["context_pack_status"] == "visual_route_not_triggered"
    assert payloads[0]["citation_count"] == 0
