from pathlib import Path
import shutil
src = Path(__file__).resolve().parent
repo = Path.cwd()
for rel in [
    "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1_2.py",
    "tests/unit/test_trace_net_visual_question_context_adapter_v1_2.py",
    "docs/trace_net_visual_question_context_adapter_v1_2_README.md",
]:
    target = repo/rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src/rel, target)
    print(f"installed={target}")
print("status=TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_2_APPLIED")
