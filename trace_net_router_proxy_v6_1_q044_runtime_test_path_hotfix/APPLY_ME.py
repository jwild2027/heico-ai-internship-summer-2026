#!/usr/bin/env python3
"""Hotfix q044 runtime-order test path variable.

The previous runtime-order regression test referenced ROUTER_PATH, but some
q044 test-file versions only define a local module_path inside _load_router_module().
This test-only patch defines ROUTER_PATH once at module scope and makes the loader
reuse it.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
TEST = ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v6_1_q044.py"
DOC = ROOT / "docs" / "trace_net_router_proxy_v6_1_q044_runtime_test_path_hotfix_README.md"

ROUTER_PATH_LINE = 'ROUTER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v6.py"\n'


def fix_test() -> bool:
    text = TEST.read_text(encoding="utf-8")
    original = text

    if "ROUTER_PATH =" not in text:
        needle = "from pathlib import Path\n"
        if needle not in text:
            raise SystemExit(f"ERROR: expected pathlib import not found in {TEST}")
        text = text.replace(needle, needle + "\n" + ROUTER_PATH_LINE, 1)

    # Prefer the shared ROUTER_PATH in the dynamic import loader too. This is safe
    # whether the line exists or not.
    text = text.replace(
        '    module_path = Path(__file__).resolve().parents[2] / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v6.py"\n'
        '    module_name = "trace_net_router_proxy_v6_q044"\n'
        '    spec = importlib.util.spec_from_file_location(module_name, module_path)\n',
        '    module_name = "trace_net_router_proxy_v6_q044"\n'
        '    spec = importlib.util.spec_from_file_location(module_name, ROUTER_PATH)\n',
    )

    if "def test_q044_runtime_shim_is_defined_before_main_guard():" in text and "ROUTER_PATH.read_text" not in text:
        raise SystemExit("ERROR: runtime-order test exists but does not reference ROUTER_PATH as expected")

    if text != original:
        TEST.write_text(text, encoding="utf-8")
        return True
    return False


def write_doc() -> None:
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(
        "# TRACE-Net q044 runtime test path hotfix\n\n"
        "This is a test-only cleanup for the q044 runtime-order regression test. "
        "The previous test referenced `ROUTER_PATH` but did not define it in some "
        "test-file versions. This patch defines `ROUTER_PATH` at module scope and "
        "uses it for dynamic router imports.\n\n"
        "Router behavior, endpoint behavior, launcher behavior, and the read-only "
        "safety contract are unchanged.\n",
        encoding="utf-8",
    )


def main() -> int:
    changed = fix_test()
    write_doc()
    print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_RUNTIME_TEST_PATH_HOTFIX_APPLIED")
    print(f"test_file={TEST}")
    print(f"doc_file={DOC}")
    print(f"test_changed={str(changed).lower()}")
    print("router_changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
