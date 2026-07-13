from pathlib import Path

def test_no_duplicated_function_headers():
    root = Path(__file__).resolve().parents[2]
    guided = (root / "scripts/run_trace_net_guided_candidate_discovery_v4.py").read_text(encoding="utf-8")
    wrapper = (root / "scripts/serve_trace_net_full_gemma_user_query_canary_v1.py").read_text(encoding="utf-8")
    assert "def iter_text_files(\ndef iter_text_files(" not in guided
    assert "def iter_text_files(\n\ndef iter_text_files(" not in guided
    assert "def append_followups(\ndef append_followups(" not in wrapper
    assert "def preserve_safety_boundary(\ndef preserve_safety_boundary(" not in wrapper
