#!/usr/bin/env python3
"""Apply TRACE-Net router proxy v6.1 q044 runtime-order fix.

Moves the q044 loose-contains/exact-policy monkeypatch shim so it is defined
before the `if __name__ == "__main__": main()` guard. Without this, imports and
unit tests can see the shim, but running the file as a server blocks inside
main() before the shim executes.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
ROUTER = ROOT / "scripts" / "serve_trace_net_guided_discovery_router_proxy_v6.py"
TEST = ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v6_1_q044.py"
DOC = ROOT / "docs" / "trace_net_router_proxy_v6_1_q044_runtime_order_fix_README.md"

SHIM_MARKER = "# A routing-policy question about whether a loose contains match can be treated"
MAIN_GUARD_DOUBLE = '\nif __name__ == "__main__":'
MAIN_GUARD_SINGLE = "\nif __name__ == '__main__':"


def _find_main_guard(text: str) -> int:
    idx = text.rfind(MAIN_GUARD_DOUBLE)
    if idx >= 0:
        return idx
    return text.rfind(MAIN_GUARD_SINGLE)


def fix_router() -> bool:
    text = ROUTER.read_text(encoding="utf-8")
    marker_idx = text.find(SHIM_MARKER)
    if marker_idx < 0:
        raise SystemExit(f"ERROR: q044 shim marker not found in {ROUTER}")

    main_idx = _find_main_guard(text)
    if main_idx < 0:
        raise SystemExit(f"ERROR: main guard not found in {ROUTER}")

    if marker_idx < main_idx:
        return False

    prefix_with_main = text[:marker_idx].rstrip()
    shim_block = text[marker_idx:].strip()

    main_idx_in_prefix = _find_main_guard(prefix_with_main)
    if main_idx_in_prefix < 0:
        raise SystemExit("ERROR: could not locate main guard before q044 shim")

    pre_main = prefix_with_main[:main_idx_in_prefix].rstrip()
    main_block = prefix_with_main[main_idx_in_prefix:].strip()

    new_text = pre_main + "\n\n" + shim_block + "\n\n" + main_block + "\n"
    ROUTER.write_text(new_text, encoding="utf-8")
    return True


def ensure_runtime_order_test() -> bool:
    test_text = TEST.read_text(encoding="utf-8")
    test_name = "def test_q044_runtime_shim_is_defined_before_main_guard():"
    if test_name in test_text:
        return False

    block = r'''


def test_q044_runtime_shim_is_defined_before_main_guard():
    """Server runtime must execute the q044 shim before entering blocking main()."""
    text = ROUTER_PATH.read_text(encoding="utf-8")
    shim_idx = text.find("# A routing-policy question about whether a loose contains match can be treated")
    main_idx = text.rfind('\nif __name__ == "__main__":')
    if main_idx < 0:
        main_idx = text.rfind("\nif __name__ == '__main__':")

    assert shim_idx >= 0
    assert main_idx >= 0
    assert shim_idx < main_idx
'''
    TEST.write_text(test_text.rstrip() + block + "\n", encoding="utf-8")
    return True


def write_doc() -> None:
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(
        "# TRACE-Net router proxy v6.1 q044 runtime-order fix\n\n"
        "This patch moves the q044 loose-contains/exact-policy shim above the "
        "`if __name__ == \"__main__\": main()` guard. The previous placement allowed "
        "import-based unit tests to pass while the live server still ran the old route, "
        "because the process entered blocking `main()` before executing the shim.\n\n"
        "Safety contract is unchanged: read-only, no source-truth mutation, no database "
        "writes, and no final-answer permission.\n\n"
        "Validation target: the q044 direct curl should return `route=guided_discovery`, "
        "`fast_clarification_only=true`, and at least three assistant questions before the "
        "full 50-question benchmark is rerun.\n",
        encoding="utf-8",
    )


def main() -> None:
    router_changed = fix_router()
    test_changed = ensure_runtime_order_test()
    write_doc()
    print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_RUNTIME_ORDER_FIX_APPLIED")
    print(f"router_file={ROUTER}")
    print(f"test_file={TEST}")
    print(f"doc_file={DOC}")
    print(f"router_changed={str(router_changed).lower()}")
    print(f"test_changed={str(test_changed).lower()}")


if __name__ == "__main__":
    main()
