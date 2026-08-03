from pathlib import Path
import ast
import importlib.util


def _load_module():
    path = Path("scripts/migration/visual/fix_trace_net_image_route_adapter_output_dirs_v1.py")
    spec = importlib.util.spec_from_file_location("fix_trace_net_image_route_adapter_output_dirs_v1", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_patch_inserts_parent_mkdir_before_write_text():
    mod = _load_module()
    original = '''
def build_adapter():
    out_path = output_dir / "trace_net_image_route_fast_chat_adapter_v1.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
'''
    patched, changed, failures = mod._patch_text(original)
    assert changed is True
    assert failures == []
    assert "out_path.parent.mkdir(parents=True, exist_ok=True)" in patched
    assert patched.index("out_path.parent.mkdir") < patched.index("out_path.write_text")
    ast.parse(patched)


def test_patch_is_idempotent():
    mod = _load_module()
    original = '''
def build_adapter():
    out_path = output_dir / "trace_net_image_route_fast_chat_adapter_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
'''
    patched, changed, failures = mod._patch_text(original)
    assert changed is False
    assert failures == []
    assert patched.count("out_path.parent.mkdir(parents=True, exist_ok=True)") == 1
    ast.parse(patched)
