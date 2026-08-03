from pathlib import Path
import shutil

src = Path(__file__).resolve().parent
repo = Path.cwd()

files = [
    ("scripts/build/visual/build_trace_net_visual_question_context_adapter_v1_1.py", "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1_1.py"),
    ("tests/unit/test_trace_net_visual_question_context_adapter_v1_1.py", "tests/unit/test_trace_net_visual_question_context_adapter_v1_1.py"),
    ("docs/trace_net_visual_question_context_adapter_v1_1_README.md", "docs/trace_net_visual_question_context_adapter_v1_1_README.md"),
]
for source, dest in files:
    target = repo / dest
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / source, target)
    print(f"installed={target}")
print("status=TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_1_APPLIED")
