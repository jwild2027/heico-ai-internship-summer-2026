
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import py_compile
import re


TARGET = Path("tiff/trace_net_h37_diversity_evidence_planner_v1.py")


NEW_EXTRACT_FIGURE = '''def _extract_figure(record: Mapping[str, Any]) -> str:
    fig = _first(record, ["figure", "figure_number", "linked_figure", "source_figure"])
    if not fig:
        blob = json.dumps(record, ensure_ascii=False)
        m = re.search(r"\\bfigure\\s+([0-9A-Za-z.-]+)\\b", blob, re.I)
        fig = m.group(1) if m else ""
    fig = _norm_text(fig)
    if fig.lower() in {"anchor", "none", "null", "n/a", "na", "unknown"}:
        return ""
    if "_" in fig or fig.lower().endswith("_count"):
        return ""
    return fig
'''


NEW_EXTRACT_NOMENCLATURE = '''def _looks_like_metadata_value(value: str) -> bool:
    raw = _norm_text(value)
    low = raw.lower()
    if not low:
        return False
    metadata_markers = (
        "source_",
        "record_count",
        "_count",
        "quality_status",
        "schema_version",
        "trace_net_",
        "artifact",
        "manifest",
        "module",
        "version",
    )
    if any(m in low for m in metadata_markers):
        return True
    if "_" in raw and " " not in raw:
        return True
    return False


def _extract_nomenclature(record: Mapping[str, Any]) -> str:
    nom = _first(record, ["nomenclature", "part_name", "description", "name", "part_description"])
    if nom and not _looks_like_metadata_value(nom):
        return nom
    line = _first(record, ["line_text", "text", "ocr_text"])
    m = re.search(r"\\b\\d{3}-\\d{5}-\\d{3}\\s+([A-Z0-9][A-Z0-9 /.-]{4,80}?)(?:\\.{2,}|VS|REF|$)", line)
    if m:
        candidate = _norm_text(m.group(1))
        if not _looks_like_metadata_value(candidate):
            return candidate
    return ""
'''


def _replace_function(src: str, name: str, replacement: str) -> tuple[str, bool]:
    pattern = rf"def {re.escape(name)}\\(.*?\\n(?=def |\\n\\ndef |\\Z)"
    new_src, n = re.subn(pattern, replacement.rstrip() + "\\n\\n", src, count=1, flags=re.S)
    return new_src, bool(n)


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"missing target: {TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(TARGET.suffix + ".bak_h37b_diversity_planner_cleanup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.write_text(src, encoding="utf-8")

    changed = False

    src, ok = _replace_function(src, "_extract_figure", NEW_EXTRACT_FIGURE)
    changed = changed or ok
    if not ok:
        raise SystemExit("failed_to_replace_extract_figure")

    src, ok = _replace_function(src, "_extract_nomenclature", NEW_EXTRACT_NOMENCLATURE)
    changed = changed or ok
    if not ok:
        raise SystemExit("failed_to_replace_extract_nomenclature")

    if "used_labels: set[str] = set()" not in src:
        anchor = "    per_route_idx: Counter[str] = Counter()\\n"
        if anchor not in src:
            raise SystemExit("failed_to_find_per_route_idx_anchor")
        src = src.replace(anchor, anchor + "    used_labels: set[str] = set()\\n", 1)
        changed = True

    old = "            label = _label_for(rec, route, per_route_idx[route])\\n"
    new = '''            label = _label_for(rec, route, per_route_idx[route])
            if label in used_labels:
                label = f"{ROUTE_PREFIX.get(route, 'X')}{per_route_idx[route]}"
            while label in used_labels:
                per_route_idx[route] += 1
                label = f"{ROUTE_PREFIX.get(route, 'X')}{per_route_idx[route]}"
            used_labels.add(label)
'''
    if old in src and "while label in used_labels:" not in src:
        src = src.replace(old, new, 1)
        changed = True

    old_block = '''            if not (part or fig or page or nom or sid):
                continue
'''
    new_block = '''            if nom and _looks_like_metadata_value(nom):
                nom = ""
            if not (part or fig or page or nom or sid):
                continue
            if not (part or fig or page or nom) and sid:
                # Do not let manifest-only records become diversity evidence.
                continue
'''
    if old_block in src and "Do not let manifest-only records become diversity evidence" not in src:
        src = src.replace(old_block, new_block, 1)
        changed = True

    TARGET.write_text(src, encoding="utf-8")
    try:
        py_compile.compile(str(TARGET), doraise=True)
    except Exception as e:
        TARGET.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        print("status=TRACE_NET_H37B_DIVERSITY_PLANNER_CLEANUP_FAILED_RESTORED")
        print(f"error={e}")
        print(f"backup={backup}")
        return 1

    print("status=TRACE_NET_H37B_DIVERSITY_PLANNER_CLEANUP_APPLIED")
    print("quality_status=PASS")
    print(f"changed={changed}")
    print(f"backup={backup}")
    print("safety_contract=no_llm_calls_no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
