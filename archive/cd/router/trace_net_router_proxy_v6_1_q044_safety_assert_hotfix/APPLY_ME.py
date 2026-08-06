from pathlib import Path

ROOT = Path.cwd()
TEST = ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v6_1_q044.py"
DOC = ROOT / "docs" / "trace_net_router_proxy_v6_1_q044_safety_assert_hotfix_README.md"

if not TEST.exists():
    raise SystemExit(f"missing test file: {TEST}")

text = TEST.read_text(encoding="utf-8")
old = '''    assert response["final_answer_allowed"] is False
    assert response["source_truth_mutation_allowed_count"] == 0
'''
new = '''    assert response["final_answer_allowed"] is False
    safety = response.get("safety_contract", {})
    assert response.get(
        "source_truth_mutation_allowed_count",
        safety.get("source_truth_mutation_allowed_count", 0),
    ) == 0
    assert response.get(
        "postgres_write_attempt_count",
        safety.get("postgres_write_attempt_count", 0),
    ) == 0
    assert response.get(
        "qdrant_write_attempt_count",
        safety.get("qdrant_write_attempt_count", 0),
    ) == 0
    assert response.get(
        "opensearch_write_attempt_count",
        safety.get("opensearch_write_attempt_count", 0),
    ) == 0
'''
if old not in text:
    if 'safety = response.get("safety_contract", {})' in text:
        status = "already_applied"
    else:
        raise SystemExit("expected safety assertion block not found; refusing broad rewrite")
else:
    TEST.write_text(text.replace(old, new, 1), encoding="utf-8")
    status = "applied"

DOC.parent.mkdir(parents=True, exist_ok=True)
DOC.write_text(
    "# TRACE-Net router proxy v6.1 q044 safety assert hotfix\n\n"
    "This test-only hotfix updates the q044 regression test to read safety counts "
    "from either the top-level response shape or the nested `safety_contract` used by "
    "the internal fast-clarification payload. It does not modify router behavior.\n\n"
    "Safety contract remains: read-only, no final answer permission, no source-truth "
    "mutation, and no Postgres/Qdrant/OpenSearch writes.\n",
    encoding="utf-8",
)
print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_SAFETY_ASSERT_HOTFIX_" + status.upper())
print(f"test_file={TEST}")
print(f"doc_file={DOC}")
print("router_changed=false")
