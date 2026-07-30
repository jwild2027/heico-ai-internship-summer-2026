from __future__ import annotations

import json
from pathlib import Path

from scripts.serve_trace_net_nha_phase12_release_proxy_v1 import decision_headers, synthetic_block_answer
from scripts.trace_net_nha_phase9_12_release_v1 import (
    build_live20_bank,
    check_promoted_release,
    evaluate_live_case,
    promote_real_release,
    validate_live20,
)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def rel(child: str, parent: str, page: int, *, status: str = "source_supported", candidates=None, depth: int = 1, item: int = 10):
    candidates = list(candidates or ([parent] if parent else []))
    return {
        "relationship_id": f"r:{child}:{parent}:{page}:{item}",
        "truth_mode": "real_source",
        "source_truth": True,
        "relationship_status": status,
        "child_part": child,
        "direct_nha": parent if status == "source_supported" else "",
        "parent_candidates": candidates,
        "row_page_id": f"t_p_120_1176_p{page:06d}",
        "anchor_page_ids": [f"t_p_120_1176_p{page - 1:06d}"],
        "item_number": str(item),
        "quantity": "1",
        "hierarchy_depth": depth,
        "guidance_only": status != "source_supported",
        "can_prove_direct_nha": status == "source_supported",
    }


def make_phase4(tmp_path: Path) -> Path:
    root = tmp_path / "phase4"
    rows = []
    # Root A: direct children plus two supported chains for chain/tree cases.
    root_a = "120-50000-001"
    for index in range(1, 9):
        rows.append(rel(f"120-5100{index}-001", root_a if index <= 4 else "120-50010-001", 100 + index, item=index * 10))
    rows.extend([
        rel("120-52001-001", "120-52002-001", 130, depth=2, item=10),
        rel("120-52002-001", root_a, 131, depth=1, item=20),
        rel("120-53001-001", "120-53002-001", 140, depth=2, item=10),
        rel("120-53002-001", "120-50010-001", 141, depth=1, item=20),
    ])
    # Three context-limited children.
    for index in range(1, 4):
        rows.append(rel(
            f"120-5400{index}-001",
            "",
            150 + index,
            status="ambiguous",
            candidates=["120-54010-001", "120-54020-001"],
            item=index * 10,
        ))
    # A third direct-parent group.
    rows.extend([
        rel("120-55001-001", "120-50020-001", 160, item=10),
        rel("120-55002-001", "120-50020-001", 161, item=20),
    ])
    answer_cases = [
        {
            "case_id": f"case-{index}",
            "child_part": row["child_part"],
            "expected_behavior": "direct_answer" if row["relationship_status"] == "source_supported" else "candidate_or_clarification",
            "expected_direct_nha": row["direct_nha"],
            "expected_parent_candidates": row["parent_candidates"],
            "expected_pages": [row["row_page_id"], *row["anchor_page_ids"]],
            "expected_hierarchy_depth": row["hierarchy_depth"],
        }
        for index, row in enumerate(rows, 1)
    ]
    quality = {"quality_status": "PASS", "counts": {"hierarchy_relationships": len(rows)}}
    write_json(root / "trace_net_nha_hierarchy_relationships_v1.json", {"records": rows})
    write_json(root / "trace_net_nha_phase4_answer_key_v1.json", {"case_count": len(answer_cases), "cases": answer_cases})
    write_json(root / "trace_net_nha_phase4_quality_v1.json", quality)
    return root


def test_phase9_promotes_only_real_release_files(tmp_path):
    source = make_phase4(tmp_path)
    output = tmp_path / "release"
    result = promote_real_release(source, output)
    assert result["quality_status"] == "PASS"
    assert (output / "trace_net_nha_real_release_manifest_v1.json").exists()
    assert not any("synthetic" in path.name for path in output.iterdir())


def test_phase9_rejects_synthetic_content(tmp_path):
    source = make_phase4(tmp_path)
    path = source / "trace_net_nha_hierarchy_relationships_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][0]["child_part"] = "990-91001-001"
    write_json(path, payload)
    result = promote_real_release(source, tmp_path / "release")
    assert result["quality_status"] == "FAIL"
    assert "synthetic_content_in_real_release" in result["failures"]


def test_phase9_checker_detects_tamper(tmp_path):
    source = make_phase4(tmp_path)
    output = tmp_path / "release"
    assert promote_real_release(source, output)["quality_status"] == "PASS"
    target = output / "trace_net_nha_phase4_quality_v1.json"
    target.write_text("{}\n", encoding="utf-8")
    result = check_promoted_release(output)
    assert result["quality_status"] == "FAIL"
    assert any("checksum_mismatch" in value for value in result["failures"])


def test_phase10_builds_exact_live20_bank(tmp_path):
    source = make_phase4(tmp_path)
    bank = build_live20_bank(source, total=20)
    assert len(bank) == 20
    assert len({row["case_id"] for row in bank}) == 20
    assert sum(row["expected_action"] == "override" for row in bank) == 18
    assert sum(row["expected_action"] == "passthrough" for row in bank) == 1
    assert sum(row["expected_action"] == "synthetic_blocked" for row in bank) == 1


def test_synthetic_block_is_production_safe():
    answer = synthetic_block_answer()
    lowered = answer.casefold()
    assert "reserved benchmark identifier" in lowered
    assert "not available to production" in lowered
    assert "not forwarded" in lowered
    assert "source page" not in lowered


def test_decision_headers_distinguish_routes():
    assert decision_headers({"action": "override", "route_id": "assembly_relationship_reasoning"})["X-Trace-Net-Route"] == "assembly_relationship_reasoning"
    assert decision_headers({"action": "passthrough"})["X-Trace-Net-Route"] == "upstream"
    assert decision_headers({"action": "synthetic_blocked"})["X-Trace-Net-Route"] == "synthetic_identifier_blocked"


def test_live_override_evaluator_accepts_contract():
    case = {
        "case_id": "x",
        "kind": "direct_nha",
        "expected_action": "override",
        "expected_behavior": "direct_answer",
        "expected_direct_nha": "120-50000-001",
        "expected_pages": ["p1"],
    }
    answer = "## Answer\n\nThe direct NHA is `120-50000-001` [1].\n\n## Evidence\n\n- [1] Source page `p1`.\n\n## Limits\n\n- Real only."
    response = {
        "http_status": 200,
        "answer": answer,
        "latency_seconds": 0.1,
        "headers": {
            "x-trace-net-nha-action": "override",
            "x-trace-net-nha-behavior": "direct_answer",
            "x-trace-net-route": "assembly_relationship_reasoning",
        },
    }
    assert evaluate_live_case(case, response, latency_hard_limit=180)["passed"]


def test_live_synthetic_evaluator_requires_safe_block():
    case = {"case_id": "x", "kind": "synthetic", "expected_action": "synthetic_blocked"}
    response = {
        "http_status": 200,
        "answer": synthetic_block_answer(),
        "latency_seconds": 0.1,
        "headers": {
            "x-trace-net-nha-action": "synthetic_blocked",
            "x-trace-net-nha-behavior": "",
            "x-trace-net-route": "synthetic_identifier_blocked",
        },
    }
    assert evaluate_live_case(case, response, latency_hard_limit=180)["passed"]


def test_live20_validator_passes_twenty_clean_records():
    rows = [
        {
            "passed": True,
            "http_status": 200,
            "expected_action": "override" if index < 18 else "passthrough" if index == 18 else "synthetic_blocked",
            "actual_action": "override" if index < 18 else "passthrough" if index == 18 else "synthetic_blocked",
            "stream": bool(index % 2),
            "latency_seconds": 0.1,
        }
        for index in range(20)
    ]
    result = validate_live20(rows)
    assert result["quality_status"] == "PASS"
    assert result["counts"]["pass_count"] == 20


def test_release_manifest_is_deterministically_checkable(tmp_path):
    source = make_phase4(tmp_path)
    output = tmp_path / "release"
    first = promote_real_release(source, output)
    second = check_promoted_release(output)
    assert first["quality_status"] == second["quality_status"] == "PASS"
    assert second["counts"]["synthetic_record_count"] == 0


def test_phase9_checker_accepts_line_ending_only_change(tmp_path):
    source = make_phase4(tmp_path)
    output = tmp_path / "release"
    assert promote_real_release(source, output)["quality_status"] == "PASS"
    manifest = json.loads(
        (output / "trace_net_nha_real_release_manifest_v1.json").read_text(
            encoding="utf-8"
        )
    )
    for record in manifest["files"]:
        path = output / record["name"]
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        path.write_bytes(normalized.replace(b"\n", b"\r\n"))
    result = check_promoted_release(output)
    assert result["quality_status"] == "PASS"
    assert result["failures"] == []


def test_phase9_manifest_records_portable_checksum(tmp_path):
    source = make_phase4(tmp_path)
    output = tmp_path / "release"
    assert promote_real_release(source, output)["quality_status"] == "PASS"
    manifest = json.loads(
        (output / "trace_net_nha_real_release_manifest_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["files"]
    for record in manifest["files"]:
        assert record["checksum_mode"] == "text_eol_portable_v1"
        assert len(record["sha256_lf"]) == 64

