from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _load_module():
    path = Path("scripts/fix_trace_net_fast_chat_runner_image_adapter_import_path_v1.py")
    spec = importlib.util.spec_from_file_location("fix_import_path", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_insert_snippet_after_future_import_is_valid_python():
    mod = _load_module()
    source = '"""doc"""\nfrom __future__ import annotations\nimport json\n'
    updated, changed, reason = mod._insert_snippet(source)
    assert changed is True
    assert reason == "inserted_repo_root_sys_path"
    assert "_TRACE_NET_REPO_ROOT" in updated
    ast.parse(updated)
    assert updated.index("from __future__ import annotations") < updated.index("TRACE_NET_IMAGE_ROUTE_IMPORT_PATH_FIX_V1_BEGIN")


def test_insert_snippet_idempotent():
    mod = _load_module()
    source = 'from __future__ import annotations\nprint("x")\n'
    updated, changed, _ = mod._insert_snippet(source)
    assert changed is True
    updated2, changed2, reason2 = mod._insert_snippet(updated)
    assert changed2 is False
    assert reason2 == "already_present"
    assert updated2 == updated
