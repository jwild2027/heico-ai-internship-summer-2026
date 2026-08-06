
import json
from pathlib import Path
from tiff.trace_net_engineering_webui_answer_server_v1 import LLMConfig, _clean_trace_text, answer_question, build_engineering_webui_answer_manifest, check_engineering_webui_answer_server_quality

def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')

def _make_artifacts(tmp_path):
    pc, fish, route, gate, runner, draft = [tmp_path / n for n in ['page_context.json','fishnet.json','route.json','gate.json','runner.json','draft_response.json']]
    _write(pc, {'quality_status':'PASS','records':[{'page_id':'source_p000001','page_number':1,'route':'normal_text','summary':'This page introduces the maintenance manual and explains workshop operations for passenger seats.'},{'page_id':'source_p000002','page_number':2,'route':'table','text':'Part number 120-45851-003 DOUBLE PASSENGER SEAT ASSY appears in a parts list context.'}]})
    _write(fish, {'records':[{'page_id':'source_p000002','fishnet_ocr_sample_text':'trace_net_fishnet_ocr_grid_v1 fishnet_page_grid_card source_p000002_r00_c01 router_classifier_input_only 120-45851-003 DOUBLE PASSENGER SEAT ASSY'}]})
    _write(route, {'records':[{'page_id':'source_p000001','accepted_route':'normal_text'},{'page_id':'source_p000002','accepted_route':'table'}]})
    _write(draft, {'draft_text':'Source-backed facts: page_id source_p000999 contains 120-29073-001. Candidate context remains for review.'})
    _write(runner, {'quality_status':'PASS','records':[{'runner_record_id':'runner_1','source_draft_packet_id':'draft_1','draft_response_path':str(draft)}]})
    _write(gate, {'quality_status':'PASS','records':[{'final_gate_record_id':'gate_1','source_runner_record_id':'runner_1','source_draft_packet_id':'draft_1','user_question':'Find part number 120-29073-001 and nearby similar parts.','final_gate_status':'FINAL_GATE_DRAFT_ACCEPTED_FOR_MANUAL_REVIEW','ready_for_manual_review':True}]})
    return pc, fish, route, gate, runner

def test_clean_trace_text_removes_debug_tokens():
    cleaned = _clean_trace_text('trace_net_fishnet_ocr_grid_v1 fishnet_page_grid_card source_p000326_r01_c01 router_classifier_input_only 120-45851-003 DOUBLE PASSENGER SEAT ASSY')
    assert 'router_classifier_input_only' not in cleaned
    assert 'fishnet_page_grid_card' not in cleaned
    assert '120-45851-003' in cleaned

def test_non_matching_part_number_uses_artifact_search_not_gated_lookup(tmp_path):
    pages = [{'page_id':'source_p000002','page_number':2,'route':'table','text':'Part number 120-45851-003 DOUBLE PASSENGER SEAT ASSY appears in a parts list context.','has_text':True,'has_v2_summary':True}]
    gated = [{'user_question':'Find part number 120-29073-001 and nearby similar parts.','seed_part_numbers':['120-29073-001'],'draft_text':'wrong gated draft','final_gate_record_id':'gate_1'}]
    ans = answer_question(question='find part number 120-45851-003', pages=pages, gated_drafts=gated, llm_config=LLMConfig(mode='off'))
    assert ans['intent'] == 'fallback_search'
    assert '120-45851-003' in ans['response_text']
    assert 'wrong gated draft' not in ans['response_text']
    assert 'Source notes:' in ans['response_text']

def test_manifest_quality_requires_retry_empty_response(tmp_path):
    pc, fish, route, gate, runner = _make_artifacts(tmp_path)
    build_engineering_webui_answer_manifest(output_dir=tmp_path/'out', final_gate_path=gate, runner_path=runner, page_context_path=pc, fishnet_path=fish, route_handoff_path=route, llm_config=LLMConfig(mode='ollama_openai', model='gemma4:26b', retry_empty_response=True))
    report = tmp_path/'out'/'trace_net_engineering_webui_answer_server_v1.json'
    result = check_engineering_webui_answer_server_quality(report_path=report, min_page_records=1, min_gated_drafts=1, require_ready_for_webui=True, require_llm_mode='ollama_openai', require_llm_model='gemma4:26b', require_retry_empty_response=True, require_no_answer_permission=True, require_no_retrieval_execution=True, require_no_source_truth_mutation=True)
    assert result['quality_status'] == 'PASS'
