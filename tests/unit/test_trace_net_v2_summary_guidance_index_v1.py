import json
from pathlib import Path

from tiff.trace_net_v2_summary_guidance_index_v1 import (
    build_guidance_index,
    check_guidance_index,
    collect_summary_records,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_collects_page_level_v2_summary_and_entities(tmp_path):
    art = tmp_path / "artifact.json"
    _write(art, {
        "records": [
            {
                "page_id": "t_p_120_1176_p000316",
                "page_number": 316,
                "route_label": ["table", "image"],
                "page_context_v2_summary": "Illustrated parts list page for Figure 69 showing part 120-50645-005 and double passenger seat assembly.",
            }
        ]
    })
    records, meta = collect_summary_records(tmp_path)
    assert meta["source_artifact_scan_count"] == 1
    assert len(records) == 1
    r = records[0]
    assert r["guidance_only"] is True
    assert r["source_trace_ready"] is True
    assert r["detected_figures"] == ["69"]
    assert "120-50645-005" in r["detected_part_numbers"]
    assert r["manual_section_hint"] == "illustrated_parts_list"
    assert r["answer_permission"] is False


def test_build_guidance_index_passes_and_writes_outputs(tmp_path):
    _write(tmp_path / "page_context_v2" / "summary.json", {
        "page_records": [
            {
                "page_id": "t_p_120_1176_p000384",
                "canonical_page_number": 384,
                "summary_v2": {"text": "Figure 91 page mentions 120-29068-003 and structure assembly in the illustrated parts list."},
            }
        ]
    })
    out = tmp_path / "out"
    result = build_guidance_index(artifact_root=tmp_path, output_dir=out, min_summary_records=1, min_source_trace_ready=1)
    assert result["quality_status"] == "PASS"
    assert result["summary"]["summary_record_count"] == 1
    assert (out / "trace_net_v2_summary_guidance_index_v1.json").exists()
    assert (out / "trace_net_v2_summary_guidance_index_v1_records.csv").exists()


def test_check_guidance_index_rejects_summary_as_proof_flags(tmp_path):
    bad_index = tmp_path / "bad.json"
    _write(bad_index, {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "summary_text": "A summary with a page source but bad proof flags.",
                "guidance_only": False,
                "source_trace_ready": True,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "unsafe": False,
            }
        ],
    })
    result = check_guidance_index(index=bad_index, output=tmp_path / "check.json", require_quality_pass=True)
    assert result["quality_status"] == "FAIL"
    assert any("guidance_only" in f for f in result["failures"])


def test_skips_summary_without_page_trace(tmp_path):
    _write(tmp_path / "run.json", {"summary": "This is a run summary with no page trace and should be ignored."})
    records, _ = collect_summary_records(tmp_path)
    assert records == []


def test_quality_threshold_failure_when_no_records(tmp_path):
    result = build_guidance_index(artifact_root=tmp_path, output_dir=tmp_path / "out", min_summary_records=1, min_source_trace_ready=1)
    assert result["quality_status"] == "FAIL"
    assert any("summary_record_count" in f for f in result["failures"])


def test_strict_filter_rejects_path_feedback_and_page_id_only_summaries(tmp_path):
    _write(tmp_path / "noisy.json", {
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "summary_path": "local_data/organization/trace_net/foo/trace_net_foo_summary.json",
                "feedback_summary": "Prior feedback marked answer trace_net_final_answer_gate_v1 as helpful for similar queries.",
                "v2_summary_page_first": "t_p_120_1176_p000001",
                "summary": "This page appears to be a revision notice and title block for a technical manual, superseding an earlier version.",
            }
        ]
    })
    records, meta = collect_summary_records(tmp_path)
    assert len(records) == 1
    assert records[0]["summary_field"] == "summary"
    assert "revision notice" in records[0]["summary_text"]
    assert meta["rejected_summary_candidate_count"] >= 3


def test_deduplicates_same_page_summary_across_artifact_copies(tmp_path):
    payload = {
        "page_id": "t_p_120_1176_p000003",
        "page_number": 3,
        "summary": "This page appears to be a parts list or applicability section from a maintenance manual, listing numerous part numbers and referencing the document scope.",
    }
    _write(tmp_path / "a.json", {"records": [payload]})
    _write(tmp_path / "b.json", {"records": [dict(payload)]})
    records, meta = collect_summary_records(tmp_path)
    assert len(records) == 1
    assert meta["rejected_summary_candidate_count"] >= 1
