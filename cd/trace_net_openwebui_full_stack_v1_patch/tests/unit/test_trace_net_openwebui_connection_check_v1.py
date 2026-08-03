from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/maintenance/serving/check_trace_net_openwebui_connection_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("openwebui_check_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["openwebui_check_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_extract_assistant_json_from_openai_response() -> None:
    mod = load_module()
    response = {
        "choices": [
            {
                "message": {
                    "content": '{"route": "gemma_confirmed_image_visual", "citation_count": 8}'
                }
            }
        ]
    }

    parsed = mod.extract_assistant_json(response)

    assert parsed["route"] == "gemma_confirmed_image_visual"
    assert parsed["citation_count"] == 8
