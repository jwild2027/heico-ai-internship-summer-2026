import json
import subprocess
import sys
from pathlib import Path

from tiff.trace_net_leiden_community_quality_audit_v1 import QualityThresholds, build_leiden_community_quality_audit, write_json


def test_quality_checker_fails_when_community_as_proof_nonzero(tmp_path):
    report = build_leiden_community_quality_audit(
        leiden_communities={
            "quality_status": "PASS",
            "summary": {"community_count": 1, "page_count": 509, "community_as_proof_count": 2},
            "communities": [{"community_id": "c1", "label": "bad", "page_ids": ["t_p_120_1176_p000001"]}],
        },
        thresholds=QualityThresholds(min_communities=1, min_audit_records=1),
    )
    path = tmp_path / "report.json"
    write_json(path, report)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/check_trace_net_leiden_community_quality_audit_v1_quality.py",
            "--report-path",
            str(path),
            "--min-communities",
            "1",
            "--min-audit-records",
            "1",
            "--max-community-as-proof",
            "0",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 2
    assert "community_as_proof_count_above_limit" in proc.stdout


def test_build_script_and_check_script_end_to_end(tmp_path):
    leiden = {
        "quality_status": "PASS",
        "summary": {"community_count": 1, "page_count": 509, "orphan_edge_count": 0},
        "communities": [
            {
                "community_id": "c1",
                "label": "Part family 120-46137",
                "page_ids": ["t_p_120_1176_p000003"],
                "category_counts": {"part": 4},
            }
        ],
    }
    cat = {"quality_status": "PASS", "summary": {"community_count": 1, "page_category_profile_count": 509}}
    leiden_path = tmp_path / "leiden.json"
    cat_path = tmp_path / "cat.json"
    out_dir = tmp_path / "out"
    leiden_path.write_text(json.dumps(leiden), encoding="utf-8")
    cat_path.write_text(json.dumps(cat), encoding="utf-8")

    build = subprocess.run(
        [
            sys.executable,
            "scripts/build_trace_net_leiden_community_quality_audit_v1.py",
            "--leiden-communities",
            str(leiden_path),
            "--category-aware-leiden-overlay",
            str(cat_path),
            "--output-dir",
            str(out_dir),
            "--require-page-count",
            "509",
            "--min-communities",
            "1",
            "--min-audit-records",
            "1",
            "--require-leiden-quality-pass",
            "--require-category-overlay-quality-pass",
            "--require-no-orphan-edges",
            "--quality",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert build.returncode == 0, build.stderr + build.stdout
    assert "Quality status: PASS" in build.stdout

    report_path = out_dir / "trace_net_leiden_community_quality_audit_v1.json"
    check = subprocess.run(
        [
            sys.executable,
            "scripts/check_trace_net_leiden_community_quality_audit_v1_quality.py",
            "--report-path",
            str(report_path),
            "--require-page-count",
            "509",
            "--min-communities",
            "1",
            "--min-audit-records",
            "1",
            "--require-leiden-quality-pass",
            "--require-category-overlay-quality-pass",
            "--require-no-orphan-edges",
            "--write-json",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert check.returncode == 0, check.stderr + check.stdout
    assert "Quality status: PASS" in check.stdout
