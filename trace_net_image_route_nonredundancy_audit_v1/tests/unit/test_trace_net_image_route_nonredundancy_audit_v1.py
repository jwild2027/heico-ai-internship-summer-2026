import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/"scripts"/"audit_trace_net_image_route_nonredundancy_v1.py"
def load():
 s=importlib.util.spec_from_file_location("audit",SCRIPT); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def test_detects_existing_and_safety(tmp_path):
 m=load(); (tmp_path/"scripts").mkdir();
 for n in ["trace_net_llava_visual_summary_batch_v1.py","trace_net_page_context_v2.py","trace_net_image_ocr_figure_callout_extractor_v1.py"]:
  (tmp_path/"scripts"/n).write_text("part_number ata_number page_context_v2 visual_region citation_ready",encoding="utf-8")
 r=m.scan(tmp_path,None)
 assert r["safety_contract"]["read_only"] is True
 assert r["safety_contract"]["source_truth_mutation_allowed"] is False
 assert any(x=="do_not_rebuild:llava_visual_observation" for x in r["nonredundancy_contract"])
def test_missing_repo_warns(tmp_path):
 m=load(); r=m.scan(tmp_path,None); assert r["quality_status"]=="WARN"
