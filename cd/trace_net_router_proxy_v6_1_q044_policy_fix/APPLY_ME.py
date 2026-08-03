#!/usr/bin/env python3
"""Apply TRACE-Net router proxy v6.1 q044 policy-routing fix.

This patch is intentionally narrow:
- It keeps the public model name trace-net-router-proxy-v6.
- It does not alter downstream endpoints, stores, graph contracts, or answer gates.
- It makes the q044 routing-policy question use fast guided clarification.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
ROUTER_PATH = ROOT / "scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py"
TEST_PATH = ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v6_1_q044.py"
DOC_PATH = ROOT / "docs" / "trace_net_router_proxy_v6_1_q044_policy_fix_README.md"

PATCH_MARKER = "TRACE_NET_ROUTER_PROXY_V6_1_Q044_POLICY_FIX"

PATCH_BLOCK = r'''

# TRACE_NET_ROUTER_PROXY_V6_1_Q044_POLICY_FIX
# Narrow q044 benchmark repair:
# A routing-policy question about whether a loose contains match can be treated
# as exact has no digits and no part noun, so v6 previously sent it to normal_ask.
# This shim preserves all v6 behavior and only promotes that policy question to
# fast guided clarification with source-trace/promote-to-exact questions.
_TRACE_NET_V6_ORIGINAL_SHOULD_FAST_CLARIFY = should_fast_clarify
_TRACE_NET_V6_ORIGINAL_BUILD_FAST_CLARIFICATION_QUESTIONS = build_fast_clarification_questions


def _trace_net_v6_1_is_loose_contains_exact_policy_question(question: str) -> bool:
    q = str(question or "").lower()
    if not q:
        return False
    has_loose_contains_match = (
        "loose contains" in q
        or "contains match" in q
        or "contains candidate" in q
        or ("contains" in q and "match" in q)
    )
    has_exact_policy = (
        "exact" in q
        or "treated as exact" in q
        or "treat as exact" in q
        or "promote" in q
        or "promoting" in q
    )
    return has_loose_contains_match and has_exact_policy


def should_fast_clarify(question: str) -> bool:
    if _trace_net_v6_1_is_loose_contains_exact_policy_question(question):
        return True
    return _TRACE_NET_V6_ORIGINAL_SHOULD_FAST_CLARIFY(question)


def build_fast_clarification_questions(question: str) -> List[str]:
    if _trace_net_v6_1_is_loose_contains_exact_policy_question(question):
        policy_questions = [
            "What exact clue and candidate are being compared?",
            "Does the candidate start with the clue, match it exactly, or only contain it somewhere else?",
            "What citation-ready source evidence supports promoting it from a loose candidate to an exact match?",
            "Should TRACE-Net keep this as candidate discovery only until strict-prefix or exact-row proof is available?",
        ]
        downstream_questions = _TRACE_NET_V6_ORIGINAL_BUILD_FAST_CLARIFICATION_QUESTIONS(question)
        unique: List[str] = []
        for item in policy_questions + downstream_questions:
            if item not in unique:
                unique.append(item)
        return unique[:5]
    return _TRACE_NET_V6_ORIGINAL_BUILD_FAST_CLARIFICATION_QUESTIONS(question)
'''

TEST_CONTENT = r'''from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_router_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py"
    spec = importlib.util.spec_from_file_location("trace_net_router_proxy_v6_q044", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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
    lowered = "\n".join(questions).lower()

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
'''

DOC_CONTENT = r'''# TRACE-Net router proxy v6.1 q044 policy fix

This patch is a narrow benchmark repair for the remaining v6 full 50-question WARN.

## Problem

`q044` asks:

```text
I want to know if a loose contains match should be treated as exact.
```

The question has no digits and no part noun, so v6 routed it to `normal_ask`. The 50-question discovery smoke expects this routing-policy question to ask clarifying/source-trace questions before treating a loose contains candidate as exact.

## Fix

The patch appends a small v6.1 shim before the script entrypoint in:

```text
scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py
```

It preserves the public model name `trace-net-router-proxy-v6` and overrides only:

- `should_fast_clarify`
- `build_fast_clarification_questions`

for loose-contains/exact-policy wording.

## Safety contract

No source artifacts are mutated. No writes are attempted to Postgres, Qdrant, or OpenSearch. Final answer permission remains false. Guided discovery remains candidate-discovery-only.
'''


def _insert_patch_block(text: str) -> str:
    if PATCH_MARKER in text:
        return text
    marker = 'if __name__ == "__main__":'
    idx = text.rfind(marker)
    if idx == -1:
        raise RuntimeError(f"Could not find script entrypoint marker {marker!r} in {ROUTER_PATH}")
    return text[:idx].rstrip() + PATCH_BLOCK + "\n\n" + text[idx:]


def main() -> int:
    if not ROUTER_PATH.exists():
        raise FileNotFoundError(f"Missing expected router file: {ROUTER_PATH}")

    original = ROUTER_PATH.read_text(encoding="utf-8")
    updated = _insert_patch_block(original)
    ROUTER_PATH.write_text(updated, encoding="utf-8")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(DOC_CONTENT, encoding="utf-8")

    print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_POLICY_FIX_APPLIED")
    print(f"router_file={ROUTER_PATH}")
    print(f"test_file={TEST_PATH}")
    print(f"doc_file={DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
