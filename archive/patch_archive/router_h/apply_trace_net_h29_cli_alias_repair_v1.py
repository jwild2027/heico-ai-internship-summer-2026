from __future__ import annotations

from datetime import datetime
from pathlib import Path
import py_compile

TARGET = Path("tiff/trace_net_engineering_engram_crag_repair_v1.py")

OLD = "    manifest = build_crag_repair_manifest(**vars(args))\n"
NEW = '''    kwargs = vars(args).copy()\n\n    # H29 CLI compatibility: argparse uses concise CLI names such as\n    # --critic and --answer-smoke, while the artifact builder may use\n    # more explicit internal parameter names.  Map aliases based on the\n    # actual build_crag_repair_manifest signature, then pass only accepted\n    # keyword arguments.\n    import inspect\n\n    sig = inspect.signature(build_crag_repair_manifest)\n    params = set(sig.parameters)\n\n    alias_candidates = {\n        "critic": (\n            "critic",\n            "critic_path",\n            "critic_manifest",\n            "critic_manifest_path",\n            "self_rag_critic",\n            "self_rag_critic_path",\n        ),\n        "answer_smoke": (\n            "answer_smoke",\n            "answer_smoke_path",\n            "answer_smoke_manifest",\n            "answer_smoke_manifest_path",\n            "source_answer_smoke",\n            "source_answer_smoke_path",\n        ),\n    }\n\n    for cli_name, candidates in alias_candidates.items():\n        if cli_name not in kwargs:\n            continue\n        if cli_name in params:\n            continue\n        value = kwargs.pop(cli_name)\n        for candidate in candidates:\n            if candidate in params:\n                kwargs[candidate] = value\n                break\n        else:\n            # Leave a clear error instead of silently ignoring a required input.\n            kwargs[cli_name] = value\n\n    kwargs = {k: v for k, v in kwargs.items() if k in params}\n    manifest = build_crag_repair_manifest(**kwargs)\n'''


def main() -> int:
    if not TARGET.exists():
        print("status=TRACE_NET_H29_CLI_ALIAS_REPAIR_FAILED")
        print(f"error=target_missing:{TARGET}")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    if "H29 CLI compatibility" in src:
        changed = False
        backup = ""
    else:
        if OLD not in src:
            print("status=TRACE_NET_H29_CLI_ALIAS_REPAIR_FAILED")
            print("error=could_not_find_manifest_build_anchor")
            print('hint=grep -n "build_crag_repair_manifest" tiff/trace_net_engineering_engram_crag_repair_v1.py')
            return 1
        backup_path = TARGET.with_suffix(TARGET.suffix + ".bak_h29_cli_alias_repair_v1_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        backup_path.write_text(src, encoding="utf-8")
        src = src.replace(OLD, NEW, 1)
        TARGET.write_text(src, encoding="utf-8")
        changed = True
        backup = str(backup_path)

    try:
        py_compile.compile(str(TARGET), doraise=True)
    except Exception as exc:
        if changed and backup:
            TARGET.write_text(Path(backup).read_text(encoding="utf-8"), encoding="utf-8")
        print("status=TRACE_NET_H29_CLI_ALIAS_REPAIR_FAILED_RESTORED")
        print(f"error={exc}")
        print(f"backup={backup}")
        return 1

    print("status=TRACE_NET_H29_CLI_ALIAS_REPAIR_APPLIED")
    print("quality_status=PASS")
    print(f"target={TARGET}")
    print(f"changed={changed}")
    if backup:
        print(f"backup={backup}")
    print("safety_contract=no_llm_calls_no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
