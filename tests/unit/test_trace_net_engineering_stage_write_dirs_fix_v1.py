from scripts.migration.ingestion.fix_trace_net_engineering_stage_write_dirs_v1 import patch_write_json_text


def test_patch_write_json_adds_parent_mkdir_before_write_text():
    src = '''def _write_json(path, data):
    p = Path(path)
    p.write_text(json.dumps(data), encoding="utf-8")
'''
    patched, changed = patch_write_json_text(src)
    assert changed is True
    assert "p.parent.mkdir(parents=True, exist_ok=True)" in patched
    assert patched.index("p.parent.mkdir") < patched.index("p.write_text")


def test_patch_write_json_is_idempotent_when_mkdir_exists():
    src = '''def _write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
'''
    patched, changed = patch_write_json_text(src)
    assert changed is False
    assert patched.count("p.parent.mkdir(parents=True, exist_ok=True)") == 1


def test_patch_write_json_ignores_non_helper_write_text():
    src = '''def other(path, data):
    p = Path(path)
    p.write_text("x", encoding="utf-8")
'''
    patched, changed = patch_write_json_text(src)
    assert changed is False
    assert "p.parent.mkdir" not in patched
