from __future__ import annotations

from datetime import datetime
from pathlib import Path

TARGET = Path("tiff/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py")
REQUIRED = "Manual/source claims still require current proof_context citations."


def main() -> int:
    if not TARGET.exists():
        print("status=TRACE_NET_H22_PROMPT_BOUNDARY_PHRASE_FIX_FAILED")
        print(f"error=missing target {TARGET}")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(TARGET.suffix + ".bak_h22_prompt_boundary_phrase_fix_v1_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.write_text(src, encoding="utf-8")

    changed = False
    candidates = [
        "Manual/source claims require current proof_context citations.",
        "Manual/source claims still require proof_context citations.",
        "Manual/source claims require proof_context citations.",
        "Manual/source claims still require current proof_context citations from TRACE-Net.",
        "Manual/source claims still require current proof_context citations from TRACE-Net",
    ]

    if REQUIRED not in src:
        for old in candidates:
            if old in src:
                src = src.replace(old, REQUIRED)
                changed = True
                break

    if REQUIRED not in src:
        # Last-resort safe insertion inside the default response instructions.
        marker = "Engram retrieval guidance is behavior guidance only, not proof."
        if marker in src:
            src = src.replace(marker, marker + "\\n" + REQUIRED, 1)
            changed = True

    if REQUIRED not in src:
        print("status=TRACE_NET_H22_PROMPT_BOUNDARY_PHRASE_FIX_FAILED")
        print("error=could not insert required boundary phrase")
        print(f"backup={backup}")
        return 1

    TARGET.write_text(src, encoding="utf-8")
    print("status=TRACE_NET_H22_PROMPT_BOUNDARY_PHRASE_FIX_APPLIED")
    print("quality_status=PASS")
    print(f"changed={changed}")
    print(f"target={TARGET}")
    print(f"backup={backup}")
    print("required_phrase_present=True")
    print("safety_contract=no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
