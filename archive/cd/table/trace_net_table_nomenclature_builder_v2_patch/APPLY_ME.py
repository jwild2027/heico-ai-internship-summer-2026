#!/usr/bin/env python3
from pathlib import Path
import shutil

patch = Path(__file__).resolve().parent
repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run from repository root.")

for rel in [
    "scripts/build/tables/build_trace_net_full_corpus_serving_pack_v1.py",
    "tests/unit/test_trace_net_full_corpus_serving_pack_v1.py",
    "tests/unit/test_trace_net_table_text_matching_v1.py",
    "docs/trace_net/TRACE_NET_TABLE_NOMENCLATURE_BUILDER_V2.md",
]:
    src = patch / rel
    dst = repo / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("applied", rel)

target = repo / "tiff/trace_net_e2e_live_orchestrator_endpoint_v25.py"
text = target.read_text(encoding="utf-8")

helper = '''

def _significant_text_tokens(value: str) -> set[str]:
    stop = {"a", "an", "and", "or", "the", "of", "for", "to", "in", "on", "with"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_value(value))
        if len(token) > 1 and token not in stop
    }
'''

if "def _significant_text_tokens(" not in text:
    marker = "\ndef _target_matches_value(target: str, value: str, intent: str) -> Tuple[bool, str, int]:\n"
    if marker not in text:
        raise SystemExit("Could not find _target_matches_value marker in v25.")
    text = text.replace(marker, helper + marker, 1)

old = '''    # Free-text table searches may match a longer cell or OCR-normalized value.
    # Structured part/manual-reference targets require exact normalized/compact equality
    # so unrelated values do not inflate counts or create false positives.
    if intent == "table_text" and target_comp in value_comp and len(target_comp) > 3:
        return True, "target_contained_in_value", 800
    if intent == "table_text" and value_comp in target_comp and len(value_comp) > 3:
        return True, "value_contained_in_target", 500
    return False, "no_match", 0
'''

new = '''    # Free-text table/nomenclature searches may match a longer cell or OCR-normalized
    # value. They also support token-order-insensitive matching, so queries like
    # "LOCKING RING" can match source nomenclature written as "RING, LOCKING".
    # Structured part/manual-reference targets remain exact normalized/compact equality
    # so unrelated values do not inflate counts or create false positives.
    if intent == "table_text":
        target_tokens = _significant_text_tokens(target)
        value_tokens = _significant_text_tokens(value)
        if target_tokens and target_tokens.issubset(value_tokens):
            return True, "target_tokens_in_value_any_order", 750
        if value_tokens and value_tokens.issubset(target_tokens):
            return True, "value_tokens_in_target_any_order", 550
        if target_comp in value_comp and len(target_comp) > 3:
            return True, "target_contained_in_value", 800
        if value_comp in target_comp and len(value_comp) > 3:
            return True, "value_contained_in_target", 500
    return False, "no_match", 0
'''

if old in text:
    text = text.replace(old, new, 1)
elif "target_tokens_in_value_any_order" not in text:
    raise SystemExit("Could not replace table-text matching block in v25.")

target.write_text(text, encoding="utf-8", newline="\n")
print("updated tiff/trace_net_e2e_live_orchestrator_endpoint_v25.py")
print("status=TRACE_NET_TABLE_NOMENCLATURE_BUILDER_V2_PATCH_APPLIED")
