#!/usr/bin/env python3
"""Fix table-text direct evidence confirmation for order-insensitive nomenclature matches."""
from pathlib import Path

repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run from repository root.")

target = repo / "tiff/trace_net_e2e_live_orchestrator_endpoint_v25.py"
text = target.read_text(encoding="utf-8")

old = '        if target:\n            is_direct = is_direct and (compact_value(target) in compact_value(value) or compact_value(value) in compact_value(target))\n'

new = '        if target:\n            matched_for_direct, _, _ = _target_matches_value(target, value, str(plan.get("query_intent") or ""))\n            is_direct = is_direct and matched_for_direct\n'

if old in text:
    text = text.replace(old, new, 1)
elif "matched_for_direct, _, _ = _target_matches_value" in text:
    print("already_applied=true")
else:
    raise SystemExit("Could not find direct-evidence target confirmation block in v25.")

target.write_text(text, encoding="utf-8", newline="\n")
print("updated tiff/trace_net_e2e_live_orchestrator_endpoint_v25.py")
print("status=TRACE_NET_TABLE_DIRECT_EVIDENCE_FIX_V2_1_APPLIED")
