from pathlib import Path
import shutil

package = Path(__file__).resolve().parent
repo = package.parent
files = [
    (package / "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1.py", repo / "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1.py"),
    (package / "tests/unit/test_trace_net_visual_question_context_adapter_v1.py", repo / "tests/unit/test_trace_net_visual_question_context_adapter_v1.py"),
    (package / "docs/trace_net_visual_question_context_adapter_v1_README.md", repo / "docs/trace_net_visual_question_context_adapter_v1_README.md"),
]
for src, dst in files:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"installed={dst}")
print("status=TRACE_NET_VISUAL_QUESTION_CONTEXT_ADAPTER_V1_APPLIED")
