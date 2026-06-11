import json
from pathlib import Path

from tiff.trace_net_incremental_corpus_manifest_v1 import quality_report


def test_quality_report_passes_expected_counts(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "summary": {
            "status": "PASS",
            "page_count": 2,
            "source_record_count": 2,
            "dirty_page_count": 1,
            "unsafe_manifest_record_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "quality_checks": {
                "page_count_matches_required": True,
                "source_record_count_min_met": True,
                "missing_page_id_count_zero": True,
                "unsafe_manifest_record_count_zero": True,
                "source_truth_mutation_allowed_count_zero": True,
            },
        }
    }), encoding="utf-8")

    report = quality_report(path, require_page_count=2, min_source_records=2)
    assert report["status"] == "PASS"
    assert report["dirty_page_count"] == 1


def test_quality_report_fails_wrong_page_count(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "summary": {
            "page_count": 1,
            "source_record_count": 1,
            "quality_checks": {
                "page_count_matches_required": True,
                "source_record_count_min_met": True,
                "missing_page_id_count_zero": True,
                "unsafe_manifest_record_count_zero": True,
                "source_truth_mutation_allowed_count_zero": True,
            },
        }
    }), encoding="utf-8")

    report = quality_report(path, require_page_count=2, min_source_records=1)
    assert report["status"] == "FAIL"
