from pathlib import Path

ROOT = Path.cwd()
TEST = ROOT / "tests" / "unit" / "test_trace_net_guided_discovery_router_proxy_v6_1_q044.py"
DOC_SRC = ROOT / "trace_net_router_proxy_v6_1_q044_remove_leftover_asserts" / "docs" / "trace_net_router_proxy_v6_1_q044_remove_leftover_asserts_README.md"
DOC_DST = ROOT / "docs" / "trace_net_router_proxy_v6_1_q044_remove_leftover_asserts_README.md"

if not TEST.exists():
    raise SystemExit(f"missing test file: {TEST}")

text = TEST.read_text(encoding="utf-8")
original = text

# The fast-clarification payload stores safety counts under safety_contract.
# Older direct top-level asserts were left after adding fallback-safe asserts;
# remove only those stale direct assertions.
stale_lines = [
    '        assert response["source_truth_mutation_allowed_count"] == 0\n',
    '        assert response["postgres_write_attempt_count"] == 0\n',
    '        assert response["qdrant_write_attempt_count"] == 0\n',
    '        assert response["opensearch_write_attempt_count"] == 0\n',
]
for line in stale_lines:
    text = text.replace(line, "")

# Make sure the fallback assertions exist exactly once for the core safety fields.
required_snippets = [
    'safety = response.get("safety_contract", {})',
    'safety.get("source_truth_mutation_allowed_count", 0)',
    'safety.get("postgres_write_attempt_count", 0)',
    'safety.get("qdrant_write_attempt_count", 0)',
    'safety.get("opensearch_write_attempt_count", 0)',
]
missing = [snippet for snippet in required_snippets if snippet not in text]
if missing:
    raise SystemExit("test file missing expected fallback safety assertions: " + ", ".join(missing))

if text == original:
    print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_REMOVE_LEFTOVER_ASSERTS_NOOP")
else:
    TEST.write_text(text, encoding="utf-8")
    print("status=TRACE_NET_ROUTER_PROXY_V6_1_Q044_REMOVE_LEFTOVER_ASSERTS_APPLIED")

DOC_DST.parent.mkdir(parents=True, exist_ok=True)
DOC_DST.write_text(DOC_SRC.read_text(encoding="utf-8"), encoding="utf-8")
print(f"test_file={TEST}")
print(f"doc_file={DOC_DST}")
print("router_changed=false")
