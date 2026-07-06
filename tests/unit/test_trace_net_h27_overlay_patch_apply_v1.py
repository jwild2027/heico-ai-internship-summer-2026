from pathlib import Path


def test_patch_script_exists():
    assert Path("scripts/apply_trace_net_h27_engram_overlay_map_to_answer_smoke_v1.py").exists()
