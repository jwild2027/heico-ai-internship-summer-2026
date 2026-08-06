#!/usr/bin/env python3
"""Apply full-corpus serving + typed query-atom router patch."""
from pathlib import Path
import shutil
import re

patch = Path(__file__).resolve().parent
repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run from repository root.")

copy_files = [
    "tiff/trace_net_query_atom_router_v1.py",
    "scripts/build/tables/build_trace_net_full_corpus_serving_pack_v1.py",
    "tests/unit/test_trace_net_query_atom_router_v1.py",
    "tests/unit/test_trace_net_full_corpus_serving_pack_v1.py",
    "docs/trace_net/TRACE_NET_FULL_CORPUS_TYPED_ROUTER_V1.md",
]
for rel in copy_files:
    src, dst = patch / rel, repo / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("applied", rel)

target = repo / "scripts/operations/serving/serve_trace_net_openwebui_unified_rag_v2.py"
text = target.read_text(encoding="utf-8")
import_line = "from tiff.trace_net_query_atom_router_v1 import analyze_query\n"
if import_line not in text:
    marker = "from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple\n"
    if marker not in text:
        raise SystemExit("Could not find unified-router typing import marker.")
    text = text.replace(marker, marker + "\n" + import_line, 1)

old = '        route = route_kind(query)\n        engrams = self.engram.select(query)\n'
new = '        router_decision = analyze_query(query)\n        route = str(router_decision["execution_route"])\n        engrams = self.engram.select(query)\n'
if old in text:
    text = text.replace(old, new, 1)
elif "router_decision = analyze_query(query)" not in text:
    raise SystemExit("Could not find process route assignment marker.")

old_update = '            "module": MODULE,\n            "model": MODEL_ID,\n'
new_update = '            "module": MODULE,\n            "model": MODEL_ID,\n            "router_decision": router_decision,\n            "retrieval_tunnel": router_decision.get("selected_tunnel"),\n'
if old_update in text:
    text = text.replace(old_update, new_update, 1)
elif '"router_decision": router_decision' not in text:
    raise SystemExit("Could not find final result update marker.")

target.write_text(text, encoding="utf-8", newline="\n")
print("updated scripts/operations/serving/serve_trace_net_openwebui_unified_rag_v2.py")
print("status=TRACE_NET_FULL_CORPUS_TYPED_ROUTER_V1_PATCH_APPLIED")
