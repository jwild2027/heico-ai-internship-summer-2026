
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import py_compile


TARGET = Path("tiff/trace_net_h38_diversity_task_runner_v1.py")


NEW_CONTAINS_SAFE_NEGATION = """
def _contains_safe_negation(text: str, term: str) -> bool:
    t = text.lower()
    term_l = term.lower()
    term_pattern = r"\\b" + re.escape(term_l) + r"\\b"

    patterns = [
        rf"\\bdoes\\s+not\\s+(?:prove|verify|establish|show|confirm)\\b[\\s\\S]{{0,160}}{term_pattern}",
        rf"\\bdo\\s+not\\s+(?:prove|verify|establish|show|confirm)\\b[\\s\\S]{{0,160}}{term_pattern}",
        rf"\\bnot\\s+(?:prove|verified|established|shown|confirmed|source-trace-ready)\\b[\\s\\S]{{0,160}}{term_pattern}",
        rf"\\bcannot\\s+(?:prove|verify|establish|show|confirm)\\b[\\s\\S]{{0,160}}{term_pattern}",
        rf"\\bcan\\s+not\\s+(?:prove|verify|establish|show|confirm)\\b[\\s\\S]{{0,160}}{term_pattern}",
        rf"\\bnot\\b[\\s\\S]{{0,120}}{term_pattern}",
        rf"\\bno\\b[\\s\\S]{{0,160}}{term_pattern}",
        rf"{term_pattern}[\\s\\S]{{0,80}}\\b(?:not|cannot|not proven|not verified|not established)\\b",
    ]
    return any(re.search(p, t) for p in patterns)
"""


NEW_UNSAFE_FORBIDDEN_CLAIMS = """
def unsafe_forbidden_claims(answer: str) -> List[str]:
    claims = []
    terms = [
        "interchangeability",
        "interchangeable",
        "approved replacement",
        "replacement approval",
        "installation safety",
        "installation safe",
        "effectivity",
        "fit approval",
        "safe to install",
    ]
    text = answer.lower()

    for term in terms:
        # Use word-boundary matching instead of raw substring matching so
        # "installation safe" does not falsely match "installation safety".
        term_pattern = r"\\b" + re.escape(term.lower()) + r"\\b"
        if not re.search(term_pattern, text):
            continue
        if _contains_safe_negation(answer, term):
            continue
        claims.append(f"possible_forbidden_claim:{term}")
    return sorted(set(claims))
"""


def _function_bounds(src: str, name: str) -> tuple[int, int]:
    needle = f"def {name}("
    start = src.find(needle)
    if start < 0:
        raise RuntimeError(f"function_not_found:{name}")
    probe = start + len(needle)
    candidates = []
    for marker in ("\ndef ", "\nclass "):
        idx = src.find(marker, probe)
        if idx >= 0:
            candidates.append(idx + 1)
    end = min(candidates) if candidates else len(src)
    return start, end


def _replace_function(src: str, name: str, replacement: str) -> tuple[str, bool]:
    start, end = _function_bounds(src, name)
    return src[:start] + replacement.strip() + "\n\n" + src[end:], True


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"missing target: {TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(TARGET.suffix + ".bak_h38b_negation_artifact_repair_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.write_text(src, encoding="utf-8")

    try:
        changed = False

        src, ok = _replace_function(src, "_contains_safe_negation", NEW_CONTAINS_SAFE_NEGATION)
        changed = changed or ok
        src, ok = _replace_function(src, "unsafe_forbidden_claims", NEW_UNSAFE_FORBIDDEN_CLAIMS)
        changed = changed or ok

        old = '                q_lines.append(f"{i}. No. The evidence supports identification only, not interchangeability, fit, or installation safety [{label}].")\n'
        new = '                q_lines.append(f"{i}. No. TRACE-Net cannot prove interchangeability, fit, or installation safety from the selected evidence [{label}].")\n'
        if old in src:
            src = src.replace(old, new, 1)
            changed = True

        TARGET.write_text(src, encoding="utf-8")
        py_compile.compile(str(TARGET), doraise=True)

    except Exception as e:
        TARGET.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        print("status=TRACE_NET_H38B_NEGATION_ARTIFACT_REPAIR_FAILED_RESTORED")
        print(f"error={e}")
        print(f"backup={backup}")
        return 1

    print("status=TRACE_NET_H38B_NEGATION_ARTIFACT_REPAIR_APPLIED")
    print("quality_status=PASS")
    print(f"changed={changed}")
    print(f"backup={backup}")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
