#!/usr/bin/env python3
"""Hotfix q044 v6.1 test loader for Python 3.14 dataclass import behavior.

The router patch itself is not changed. This updates only the q044 regression
unit test so dynamically imported dataclasses can resolve their module through
sys.modules before exec_module runs.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
TEST_PATH = ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v6_1_q044.py"
DOC_PATH = ROOT / "docs" / "trace_net_router_proxy_v6_1_q044_test_loader_hotfix_README.md"

TEST_CONTENT = """from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_router_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py"
    module_name = "trace_net_router_proxy_v6_q044"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Python 3.14 dataclasses resolve string annotations through sys.modules
    # while @dataclass executes. Register the module before exec_module.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_q044_loose_contains_exact_policy_routes_to_fast_guided_clarification():
    router = _load_router_module()
    question = "I want to know if a loose contains match should be treated as exact."

    decision = router.route_question(question)

    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is True
    assert decision.partial_part_lookup is True


def test_q044_clarifying_questions_match_expected_policy_themes():
    router = _load_router_module()
    question = "I want to know if a loose contains match should be treated as exact."

    questions = router.build_fast_clarification_questions(question)
    lowered = "\\n".join(questions).lower()

    assert len(questions) >= 3
    assert "what exact clue and candidate are being compared" in lowered
    assert "start with the clue" in lowered
    assert "only contain" in lowered
    assert "source evidence" in lowered
    assert "promoting" in lowered


def test_q044_route_payload_stays_read_only_and_does_not_call_normal_ask():
    router = _load_router_module()
    config = router.ServerConfig(
        host="127.0.0.1",
        port=8017,
        normal_base_url="http://127.0.0.1:8014",
        guided_base_url="http://127.0.0.1:8016",
        model="trace-net-router-proxy-v6",
        timeout_seconds=1.0,
        default_top_k=8,
        default_loose_top_k=8,
    )

    response = router.route_payload(
        {
            "model": "trace-net-router-proxy-v6",
            "messages": [
                {
                    "role": "user",
                    "content": "I want to know if a loose contains match should be treated as exact.",
                }
            ],
        },
        config,
    )

    assert response["quality_status"] == "PASS"
    assert response["route"] == "guided_discovery"
    assert response["fast_clarification_only"] is True
    assert response["downstream_endpoint"] == "internal://trace-net/router/fast-clarification"
    assert response["final_answer_allowed"] is False
    assert response["source_truth_mutation_allowed_count"] == 0
    assert response["postgres_write_attempt_count"] == 0
    assert response["qdrant_write_attempt_count"] == 0
    assert response["opensearch_write_attempt_count"] == 0
    assert len(response["clarifying_questions"]) >= 3


def test_clear_strict_prefix_query_still_uses_full_guided_discovery_not_fast_clarification():
    router = _load_router_module()
    question = "Find part candidates that start with 24."

    decision = router.route_question(question)

    assert decision.route == "guided_discovery"
    assert decision.fast_clarification_only is False


def test_exact_part_lookup_still_routes_to_normal_ask():
    router = _load_router_module()
    question = "Find part number 120-36833-001."

    decision = router.route_question(question)

    assert decision.route == "normal_ask"
    assert decision.fast_clarification_only is False
"""

DOC_CONTENT = """# TRACE-Net q044 v6.1 test-loader hotfix

This hotfix changes only the q044 regression test loader.

## Why

On Python 3.14, `@dataclass` may inspect `sys.modules[cls.__module__]` while the module is being dynamically imported. The original q044 test used `importlib.util.module_from_spec()` and then called `exec_module()` without first registering the module in `sys.modules`, causing:

```text
AttributeError: 'NoneType' object has no attribute '__dict__'
```

## Fix

The test now does:

```python
sys.modules[module_name] = module
spec.loader.exec_module(module)
```

before loading the router file.

## Scope

No router behavior, launcher behavior, source artifacts, stores, endpoints, or safety gates are changed.
"""


def main() -> int:
    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(DOC_CONTENT, encoding="utf-8")
    print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_TEST_LOADER_HOTFIX_APPLIED")
    print(f"test_file={TEST_PATH}")
    print(f"doc_file={DOC_PATH}")
    print("router_changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
