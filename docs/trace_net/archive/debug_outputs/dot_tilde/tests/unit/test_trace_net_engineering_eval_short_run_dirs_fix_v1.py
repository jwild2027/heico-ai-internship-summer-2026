from scripts.fix_trace_net_engineering_eval_short_run_dirs_v1 import patch_text


def test_patch_replaces_long_question_slug_line():
    src = '''import argparse\n\ndef _slug(text):\n    return text\n\ndef build():\n        run_dir = runs_dir / f"q{idx:02d}_{_slug(question)}"\n'''
    patched, details = patch_text(src)
    assert details["changed"] is True
    assert 'run_dir = runs_dir / f"q{idx:02d}_{_slug(question)}"' not in patched
    assert "hashlib.sha1" in patched
    assert "_eval_run_task_hint" in patched
    assert "run_dir.mkdir(parents=True, exist_ok=True)" in patched


def test_patch_is_idempotent():
    src = '''import argparse\n\ndef _slug(text):\n    return text\n\ndef build():\n        run_dir = runs_dir / f"q{idx:02d}_{_slug(question)}"\n'''
    once, _ = patch_text(src)
    twice, details = patch_text(once)
    assert twice == once
    assert details["legacy_long_slug_line_present"] is False


def test_patch_adds_hashlib_import_when_missing():
    src = '''from pathlib import Path\n\ndef _slug(text):\n    return text\n\ndef build():\n        run_dir = runs_dir / f"q{idx:02d}_{_slug(question)}"\n'''
    patched, _ = patch_text(src)
    assert "import hashlib" in patched
