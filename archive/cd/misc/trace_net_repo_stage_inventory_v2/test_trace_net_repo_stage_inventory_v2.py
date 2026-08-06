from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "trace_net_repo_stage_inventory_v2.py"
spec = importlib.util.spec_from_file_location("inventory_v2", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_engram_classification():
    sig = mod.ParsedSignals(imports=["scripts.trace_net_engineering_engram_core_v1"])
    scores, _ = mod.score_stages("scripts/build_trace_net_engram_skill_cards_v1.py", sig)
    primary, secondary, confidence = mod.choose_stages(scores)
    assert primary == "brain_engram"
    assert confidence > 0

def test_ocr_classification():
    sig = mod.ParsedSignals(symbols=["run_tesseract_fishnet_ocr"])
    scores, _ = mod.score_stages("scripts/build/ocr/build_trace_net_fishnet_ocr_grid_v1.py", sig)
    primary, _, _ = mod.choose_stages(scores)
    assert primary == "ocr"

def test_protected_launcher():
    sig = mod.ParsedSignals(ports=[8128, 8131])
    protected, reasons = mod.is_protected(
        "scripts/operations/launch_trace_net_gemma_resident_openwebui_v2_1.sh",
        sig,
        [],
    )
    assert protected
    assert reasons

def test_version_family():
    family = mod.version_family("scripts/example_router_v6_1.py")
    assert family is not None
    _, version = family
    assert version == (6, 1)

def test_legacy_not_safe_when_referenced():
    status, reason, legacy_evidence = mod.status_for(
        "patches/old_patch/APPLY_ME.py",
        False,
        ["docs/README.md"],
        [],
        [],
    )
    assert status == "active_or_review"
    assert not legacy_evidence

def test_destination_does_not_move_artifact_tree():
    assert (
        mod.destination_for(
            "local_data/organization/trace_net/foo/data.json",
            "graph",
            "active_or_review",
        )
        == "local_data/organization/trace_net/foo/data.json"
    )
