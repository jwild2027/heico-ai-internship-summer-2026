import json
from pathlib import Path

from tiff.trace_net_engineering_engram_core_v1 import build_engram_core, check_engram_core


def _smoke(tmp_path: Path, quality_status="PASS") -> Path:
    p = tmp_path / "smoke.json"
    p.write_text(json.dumps({
        "quality_status": quality_status,
        "summary": {
            "smoke_question_count": 30,
            "good_answer_count": 28,
            "partial_answer_count": 2,
            "bad_answer_count": 0,
            "blocked_answer_count": 0,
            "unsupported_claim_count": 0,
        },
        "records": [
            {"question": "What does figure 999 show?", "category": "unknown_figure", "grade": "PARTIAL"},
            {"question": "Find part 999", "category": "unknown_part", "grade": "PARTIAL"},
            {"question": "What does figure 69 show?", "category": "figure_lookup", "grade": "GOOD"},
        ],
    }, indent=2), encoding="utf-8")
    return p


def test_build_default_engram_core_passes(tmp_path):
    result = build_engram_core(output_dir=tmp_path / "engram", require_quality_pass=True)
    assert result["quality_status"] == "PASS"
    assert result["summary"]["engram_atom_count"] >= 10
    assert result["summary"]["policy_trait_count"] >= 3
    assert result["summary"]["ready_for_engram_prompt_injector"] is True
    assert Path(result["paths"]["core"]).exists()
    assert Path(result["paths"]["memory_atoms"]).exists()
    assert Path(result["paths"]["traits"]).exists()


def test_shared_nomenclature_policy_atom_exists(tmp_path):
    result = build_engram_core(output_dir=tmp_path / "engram")
    atoms = result["records"]
    text = json.dumps(atoms).lower()
    assert "shared nomenclature" in text
    assert "not proof of interchangeability" in text
    assert any(a["engram_id"] == "policy_no_interchangeability_without_authority_v1" for a in atoms)


def test_build_with_smoke_eval_adds_eval_memory(tmp_path):
    smoke = _smoke(tmp_path)
    result = build_engram_core(output_dir=tmp_path / "engram", smoke_test=[smoke], require_eval_source_pass=True)
    assert result["quality_status"] == "PASS"
    assert result["summary"]["eval_source_count"] == 1
    assert result["summary"]["episodic_eval_memory_count"] == 1
    assert any(a["memory_type"] == "episodic_eval_memory" for a in result["records"])
    assert any("unknown_figure" in a.get("trigger_text", "") for a in result["records"])


def test_check_engram_core_passes(tmp_path):
    result = build_engram_core(output_dir=tmp_path / "engram", require_quality_pass=True)
    check = check_engram_core(
        engram_core=result["paths"]["core"],
        output=tmp_path / "check.json",
        require_quality_pass=True,
    )
    assert check["quality_status"] == "PASS"
    assert Path(tmp_path / "check.json").exists()


def test_check_engram_core_fails_threshold(tmp_path):
    result = build_engram_core(output_dir=tmp_path / "engram")
    check = check_engram_core(
        engram_core=result["paths"]["core"],
        output=tmp_path / "check.json",
        min_engram_atoms=999,
    )
    assert check["quality_status"] == "FAIL"
    assert any("engram_atom_count below minimum" in f for f in check["failures"])


def test_failed_eval_source_can_be_required(tmp_path):
    smoke = _smoke(tmp_path, quality_status="FAIL")
    try:
        build_engram_core(output_dir=tmp_path / "engram", smoke_test=[smoke], require_eval_source_pass=True, require_quality_pass=True)
    except SystemExit as e:
        assert "quality_status is not PASS" in str(e)
    else:
        raise AssertionError("expected SystemExit")
