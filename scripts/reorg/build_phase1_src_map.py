"""Phase 1 (READ-ONLY) — propose a target path for every src/trace_net file.

Emits REORG_PHASE1_SRC_MAP.md (current_path | proposed_path | why | FLAG). Leaf
assignments inside a stage are FILENAME-INFERRED and must be confirmed against file
contents during Phase 2 (per the plan's `‹inferred›` note). This script moves
nothing — it only reads the tracked file list and writes a report.
"""
from __future__ import annotations
import subprocess, re
from pathlib import Path
from collections import Counter

files = subprocess.run(["git", "ls-files", "src/trace_net"], capture_output=True, text=True).stdout.split("\n")
files = [f for f in files if f.strip().endswith(".py")]

PIPE = "src/trace_net/pipeline"


def _match(name, table, default):
    for kws, leaf in table:
        if any(k in name for k in kws):
            return leaf
    return default


def classify(path: str):
    """Return (proposed_path, why, flag)."""
    rel = path[len("src/trace_net/"):]
    sp = rel.split("/", 1)[0]
    base = Path(path).name
    n = base.lower()
    is_quality = "/quality/" in path
    q = "/quality" if is_quality else ""
    flag = ""

    if base == "__init__.py":
        return (path, "package marker stays with its package (renamed dirs keep __init__)", "")

    # Decision (e): keep these route/classify files in their CURRENT location (no move).
    EXCEPTIONS = {
        "trace_net_ocr_route_scan_pack_v1.py", "trace_net_ocr_classifier_pipeline_runner_v1.py",
        "document_classifier.py", "trace_net_page_route_manifest_v1.py",
    }
    if base in EXCEPTIONS:
        return (path, "kept in current location per decision (e)", "EXCEPTION: no move (approved)")
    # Decision (e)+(2) Option B: the manifest's quality sibling moves UP beside the
    # (pinned) manifest in ingestion/, eliminating the single-file ingestion/quality leaf.
    if base == "trace_net_page_route_manifest_v1_quality.py":
        return ("src/trace_net/ingestion/trace_net_page_route_manifest_v1_quality.py",
                "beside pinned page_route_manifest_v1 in ingestion/ (decision e + option B)",
                "EXCEPTION(e)+B: bumped beside its module")

    # ---- tables -> s2_ocr/table_ocr (+ cross-stage escapes) ----
    if sp == "tables":
        if "visual_callout_table_linker" in n:
            return (f"src/trace_net/visual/callout_linker/{base}", "callout↔table linker", "APPROVED cross-stage: table->visual (d)")
        if "gold_label_review_workbook" in n or "human_review" in n:
            return (f"src/trace_net/validation/gold_labels/{base}", "human/gold-label review", "APPROVED cross-stage: table->validation (d)")
        if "hybrid_retrieval" in n or "exact_search" in n or ("retrieval" in n and "readiness" not in n):
            return (f"src/trace_net/pipeline/s6_retrieval/search/{base}", "table→retrieval bridge", "CROSS-STAGE: table->s6 retrieval (PENDING decision)")
        leaf = _match(n, [
            (["line_geometry", "morphology"], "line_geometry"),
            (["cell_normalizer", "cell_extractor", "cell_extraction"], "cell_extraction"),
            (["nomenclature"], "nomenclature"),
            (["full_region_recovery", "full_enclosure", "structure_bbox", "reconstructor", "crop"], "structure_recovery"),
            (["bbox", "localizer", "sidecar", "enrichment", "image_resolver", "paddle_style"], "bbox"),
            (["direct_evidence", "route_evidence", "route_value", "understanding", "presence_verifier",
              "candidate_scan", "row_context"], "direct_evidence"),
            (["overlay_export", "packager", "readiness_report", "demo_query_pack", "tile", "tiles"], "export"),
            (["detector_overlay", "geometry_review", "route_contract_audit", "parity", "diagnostics", "guard"], "structure_recovery"),
        ], "direct_evidence")
        return (f"{PIPE}/s2_ocr/table_ocr/{leaf}{q}/{base}", f"table_ocr/{leaf}", flag)

    # ---- ocr -> s2_ocr ----
    if sp == "ocr":
        if base == "trace_net_ocr_cleanup_extraction_v1.py" or "ocr_cleanup" in n:
            return (f"{PIPE}/s2_ocr/cleanup/{base}", "OCR cleanup", "")
        if "coverage_audit" in n or "depth_audit" in n:
            return (f"{PIPE}/s2_ocr/quality/{base}", "OCR coverage/depth audit", "")
        if "fishnet" in n:
            return (f"{PIPE}/s2_ocr/fishnet/{base}", "fishnet OCR grid/route (leaf not in inferred plan)", "NEW-LEAF: s2_ocr/fishnet")
        if "figure_callout" in n or "title_block" in n:
            return (f"{PIPE}/s2_ocr/image_ocr/{base}", "figure/callout/title-block OCR", "")
        if "scan_pack" in n or "classifier_pipeline_runner" in n:
            return (f"{PIPE}/s1_classify/dispatch/{base}", "route/scan-pack classification", "CROSS-STAGE: s1/s2 (route classifier)")
        leaf = _match(n, [
            (["coordinate_evidence", "layout_aware", "raw_ocr_nomenclature", "paddleocr", "pilot", "ocr_util",
              "embedding_candidates"], "text_ocr"),
        ], "text_ocr")
        return (f"{PIPE}/s2_ocr/{leaf}/{base}", f"s2_ocr/{leaf}", flag)

    # ---- graph -> s3_graph_store ----
    if sp == "graph":
        if "org_chart_site" in n or "ui_community_overlay" in n or "graph_ui" in n or "graph_explorer" in n:
            return (f"src/trace_net/serving/graph_ui/{base}", "graph UI/site", "APPROVED cross-stage: graph->serving (d)")
        if n.startswith("trace_net_nha_phase"):
            return (f"{PIPE}/s3_graph_store/nha/{base}", "NHA phase pipeline (leaf not in inferred plan)", "NEW-LEAF: s3/nha; may be multi-stage")
        if "leiden" in n or "community" in n:
            return (f"{PIPE}/s3_graph_store/communities/{base}", "leiden/community (leaf not in inferred plan)", "NEW-LEAF: s3/communities")
        leaf = _match(n, [
            (["postgres_loader", "writeback", "attachment_plan", "part_lineage", "part_property", "context_overlay",
              "trust_overlay"], "writers"),
            (["postgres_quality", "graph_audit", "postgres_graph_audit", "baseline_checkpoint", "setup_report"], "schema"),
            (["query", "traversal", "traceability", "explorer", "retrieval", "expander", "enrichment"], "queries"),
            (["entity_trait", "document_organization_graph", "document_graph", "element_graph"], "nodes"),
        ], "writers")
        return (f"{PIPE}/s3_graph_store/{leaf}{q}/{base}", f"s3_graph_store/{leaf}", flag)

    # ---- embeddings -> s4_embed ----
    if sp == "embeddings":
        if "chroma" in n:
            return (f"{PIPE}/s4_embed/qdrant/{base}", "OLD Chroma client", "OLD-STACK: retire with Chroma")
        leaf = _match(n, [(["qdrant"], "qdrant"), (["colpali", "candidates"], "models")], "models")
        return (f"{PIPE}/s4_embed/{leaf}/{base}", f"s4_embed/{leaf}", flag)

    # ---- retrieval / router / context -> s6_retrieval ----
    if sp == "retrieval":
        leaf = _match(n, [
            (["grouper", "merge", "rerank", "weighted"], "rerank"),
            (["answer", "synthesis"], "answer"),
            (["feedback"], "search"),
            (["search", "candidate_index", "opensearch", "hybrid", "rag"], "search"),
        ], "search")
        return (f"{PIPE}/s6_retrieval/{leaf}{q}/{base}", f"s6_retrieval/{leaf}", flag)
    if sp == "router":
        return (f"{PIPE}/s6_retrieval/routing{q}/{base}", "router → s6/routing", "")
    if sp == "context":
        return (f"{PIPE}/s6_retrieval/context_build{q}/{base}", "context → s6/context_build", "")

    # ---- engram -> s5_engram (FUNCTION leaves; NOT the inferred 'layers/') ----
    if sp == "engram":
        # Decision (c): ALL engram smoke modules go to s5_engram/smoke/ regardless of subsystem.
        if "smoke" in n or "integration_gate" in n or "unified_runtime_gate" in n:
            leaf = "smoke"
        else:
            leaf = _match(n, [
                (["memory_layers", "feedback_ledger"], "memory"),
                (["vector_loader", "vector_retriever", "qdrant_adapter"], "io"),
                (["prompt_retrieval", "retrieval_bridge"], "retrieval"),
                (["overlay", "prompt_overlay"], "overlay"),
                (["skill_cards", "skill_shadow", "canonical_registry", "policy_compiler", "planner", "cognitive_precision"], "skills"),
                (["nha_engram"], "nha"),
                (["core"], "core"),
                (["trust_trait"], "overlay"),
            ], "core")
        return (f"{PIPE}/s5_engram/{leaf}/{base}", f"s5_engram/{leaf} (function, not layer)", "TAXONOMY: engram has no layer_N structure")

    # ---- ingestion (orchestration) ----
    if sp == "ingestion":
        if "source_link" in n or "rescarta_deeplink" in n:
            return (f"{PIPE}/s3_graph_store/source_links/{base}", "source links → s3", "APPROVED cross-stage: ingestion->s3 source_links (d)")
        if "ocr_cleanup_extraction" in n:
            return (f"{PIPE}/s2_ocr/cleanup/{base}", "OCR cleanup", "CROSS-STAGE: ingestion/s2")
        if "page_route_manifest" in n or "route_dispatch" in n or "classif" in n:
            return (f"{PIPE}/s1_classify/dispatch/{base}", "page route/classify", "CROSS-STAGE: ingestion/s1")
        leaf = _match(n, [
            (["changed_page", "incremental"], "incremental"),
            (["inventory", "hash_crawler", "scan"], "tiff_inventory"),
            (["part_catalog", "part_qa"], "part_catalog"),
            (["document_organization", "manual_grouping"], "document_org"),
            (["pipeline_manifest", "rag_ingestion", "ingest_bridge", "readiness"], "pipeline"),
        ], "pipeline")
        return (f"src/trace_net/ingestion/{leaf}/{base}", f"ingestion/{leaf}", flag)

    # ---- serving ----
    if sp == "serving":
        leaf = _match(n, [(["openwebui", "open_webui"], "openwebui"), (["console"], "console"),
                          (["api", "endpoint"], "api"), (["adapter", "bridge"], "adapters")], "adapters")
        return (f"src/trace_net/serving/{leaf}/{base}", f"serving/{leaf}", flag)

    # ---- validation ----
    if sp == "validation":
        leaf = _match(n, [
            (["gold_label", "review_workbook"], "gold_labels"),
            (["eval_set", "eval_questions", "question_set", "eval_runner"], "eval_sets"),
            (["negation"], "negation"),
            (["citation"], "citation"),
            (["regression"], "regression"),
            (["score", "metric", "grade", "accuracy", "audit", "checker", "baseline"], "scoring"),
        ], "scoring")
        return (f"src/trace_net/validation/{leaf}{q}/{base}", f"validation/{leaf}", flag)

    # ---- visual ----
    if sp == "visual":
        leaf = _match(n, [(["callout"], "callout_linker"), (["retrieval_clean", "cleaner"], "retrieval_clean"),
                          (["card"], "cards"), (["vqa", "question_context", "gate", "adapter"], "vqa")], "vqa")
        return (f"src/trace_net/visual/{leaf}/{base}", f"visual/{leaf}", flag)

    # ---- writing ----
    if sp == "writing":
        leaf = _match(n, [(["format"], "formatters"), (["card"], "cards")], "output")
        return (f"src/trace_net/writing/{leaf}/{base}", f"writing/{leaf}", flag)

    # ---- core / feedback ----
    if sp == "core":
        if "database" in n or "storage" in n or "schema" in n or "postgres" in n:
            return (f"src/trace_net/core/db/{base}", "DB/schema", "")
        if "dublin_core" in n:
            return (f"src/trace_net/core/types/{base}", "Dublin-core DTO/crosswalk", "REVIEW: metadata type vs ingestion")
        if "prompt_contract" in n:
            return (f"src/trace_net/core/prompt_contract/{base}", "LLM prompt contract", "REVIEW: core vs serving")
        return (f"src/trace_net/core/runtime/{base}", "runtime/loader/map", "REVIEW: core/runtime bucket")
    if sp == "feedback":
        return (f"src/trace_net/feedback/{base}", "kept flat (only ~7 files)", "")

    return (path, "unclassified", "REVIEW")


rows = [(f, *classify(f)) for f in files]

# one-file-leaf detection: bump a proposed leaf holding a single file up one level
leaf_counts = Counter(str(Path(p).parent) for _, p, _, _ in rows)
final = []
for cur, prop, why, flag in rows:
    parent = str(Path(prop).parent)
    fl = flag
    if leaf_counts[parent] == 1 and Path(cur).name != "__init__.py" and parent != str(Path(cur).parent):
        fl = (fl + "; " if fl else "") + "ONE-FILE-LEAF: bump up one level"
    final.append((cur, prop, why, fl))

lines = ["# Phase 1 — src/trace_net target map (READ-ONLY proposal, nothing moved)", "",
         f"Total files: {len(final)}. Leaf assignments are filename-inferred; confirm from contents in Phase 2.", "",
         "| current_path | proposed_path | why | FLAG |", "|---|---|---|---|"]
for cur, prop, why, fl in sorted(final, key=lambda r: r[1]):
    lines.append(f"| `{cur}` | `{prop}` | {why} | {fl} |")
Path("REORG_PHASE1_SRC_MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# console summary
flagged = [r for r in final if r[3]]
print("files mapped:", len(final))
print("flagged:", len(flagged))
print("\n=== proposed target leaves (counts) ===")
for leaf, c in sorted(leaf_counts.items()):
    print(f"{c:4d}  {leaf}")
print("\n=== FLAG breakdown ===")
fc = Counter(re.split(r"[:;]", r[3])[0] for r in flagged)
for k, v in fc.most_common():
    print(f"{v:4d}  {k}")
