#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "trace_net_image_route_nonredundancy_audit_v1"
CAPABILITIES = {
    "route_dispatch": ["image_visual_observer_route", "route_brain_image_page", "image_route"],
    "llava_visual_observation": ["llava_visual_summary", "visual_observer"],
    "visual_summary": ["image_visual_summary"],
    "image_ocr_callout_extraction": ["image_ocr_figure_callout_extractor"],
    "visual_evidence_pack": ["image_visual_evidence_pack"],
    "nomenclature_merge": ["image_visual_evidence_nomenclature_merger", "visual_part_nomenclature_enricher"],
    "callout_part_verification": ["callout_visual_part_verifier"],
    "figure_chart_understanding": ["figure_chart_understanding"],
    "callout_table_linking": ["visual_callout_table_linker"],
    "visual_context_builder": ["visual_context_builder"],
    "retrieval_adapter": ["image_route_fast_chat_adapter", "webui_visual_context_bridge"],
    "page_context_v2": ["page_context_v2"],
}
DESIRED_FIELDS = {
    "object_description": ["primary_object", "object_category", "physical_description", "functional_description"],
    "identifiers": ["part_number", "ata_number", "figure", "callout", "nomenclature"],
    "ocr_vision_reconciliation": ["ocr_agreement", "vision_text", "ocr_text", "character_conflict"],
    "proof_status": ["proof_status", "citation_ready", "source_trace_ready", "candidate_only"],
    "page_visual_link": ["page_context_v2", "page_id", "visual_region"],
}

def iter_files(repo: Path):
    for base in (repo / "scripts", repo / "src", repo / "tests"):
        if base.exists():
            yield from (p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"})

def read_text(path: Path) -> str:
    try: return path.read_text(encoding="utf-8", errors="ignore")
    except OSError: return ""

def scan(repo: Path, artifact_root: Path | None) -> dict[str, Any]:
    files=list(iter_files(repo)); names=[str(p.relative_to(repo)).replace("\\","/") for p in files]
    lower_names=[n.lower() for n in names]
    capability_records=[]
    for cap, needles in CAPABILITIES.items():
        matches=[names[i] for i,n in enumerate(lower_names) if any(x in n for x in needles)]
        capability_records.append({"capability":cap,"status":"existing_reuse" if matches else "not_found_in_code_scan","matches":matches[:30]})
    corpus="\n".join(read_text(p) for p in files if any(k in p.name.lower() for k in ("visual","image","llava","callout","figure","context_v2")))
    field_map=[]
    for group, fields in DESIRED_FIELDS.items():
        found=[f for f in fields if re.search(rf"\b{re.escape(f)}\b", corpus, re.I)]
        missing=[f for f in fields if f not in found]
        status="already_available" if not missing else "partially_available" if found else "missing"
        field_map.append({"field_group":group,"status":status,"found_fields":found,"missing_fields":missing})
    artifact_matches=[]
    if artifact_root and artifact_root.exists():
        for p in artifact_root.rglob("*.json"):
            n=p.name.lower()
            if any(k in n for k in ("visual","image","llava","callout","figure","context_v2")):
                artifact_matches.append(str(p))
                if len(artifact_matches)>=200: break
    existing={r['capability'] for r in capability_records if r['status']=='existing_reuse'}
    prohibited=[]
    for cap in ("route_dispatch","llava_visual_observation","image_ocr_callout_extraction","visual_evidence_pack","nomenclature_merge","callout_part_verification","figure_chart_understanding","callout_table_linking","retrieval_adapter"):
        if cap in existing: prohibited.append(f"do_not_rebuild:{cap}")
    recommended=[
        "build_read_only_visual_summary_v2_v3_adapter_over_existing_artifacts",
        "add_explicit_ocr_vs_existing_llava_token_reconciliation_only_if_not_already_present",
        "link_visual_summary_to_existing_page_context_v2_without_renaming_HAS_CONTEXT_V2",
        "use_targeted_llava_retry_only_for_unresolved_regions_or_character_conflicts",
        "preserve_candidate_only_and_no_answer_permission_defaults",
    ]
    return {
        "schema_version":SCHEMA_VERSION,
        "quality_status":"PASS" if "llava_visual_observation" in existing and "page_context_v2" in existing else "WARN",
        "repo_root":str(repo), "artifact_root":str(artifact_root) if artifact_root else None,
        "capabilities":capability_records,"desired_field_gap_map":field_map,
        "artifact_match_count":len(artifact_matches),"artifact_matches":artifact_matches,
        "nonredundancy_contract":prohibited,"recommended_new_work":recommended,
        "safety_contract":{"read_only":True,"final_answer_allowed":False,"source_truth_mutation_allowed":False,"postgres_write_attempt_count":0,"qdrant_write_attempt_count":0,"opensearch_write_attempt_count":0},
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--artifact-root", type=Path, default=Path("local_data/organization/trace_net"))
    ap.add_argument("--output-dir", type=Path, required=True)
    a=ap.parse_args(); out=a.output_dir; out.mkdir(parents=True,exist_ok=True)
    result=scan(a.repo_root.resolve(), a.artifact_root.resolve() if a.artifact_root else None)
    (out/"trace_net_image_route_nonredundancy_audit_v1.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    lines=[f"quality_status={result['quality_status']}",f"artifact_match_count={result['artifact_match_count']}","", "Existing capabilities:"]
    lines += [f"- {r['capability']}: {r['status']} ({len(r['matches'])} files)" for r in result['capabilities']]
    lines += ["", "Non-redundancy contract:"]+[f"- {x}" for x in result['nonredundancy_contract']]
    lines += ["", "Recommended new work:"]+[f"- {x}" for x in result['recommended_new_work']]
    (out/"trace_net_image_route_nonredundancy_audit_v1_report.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"quality_status={result['quality_status']}"); print(f"artifact_match_count={result['artifact_match_count']}")
    print(f"json={out/'trace_net_image_route_nonredundancy_audit_v1.json'}")
    print(f"report={out/'trace_net_image_route_nonredundancy_audit_v1_report.txt'}")
if __name__=="__main__": main()
