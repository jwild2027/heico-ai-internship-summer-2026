
import json
from tiff.trace_net_engineering_webui_answer_server_v1 import check_engineering_webui_answer_server_quality

def test_quality_flags_retry_disabled(tmp_path):
    path = tmp_path/'report.json'
    path.write_text(json.dumps({'summary':{'page_record_count':10,'gated_draft_count':1,'ready_for_webui':True,'openai_compatible_chat_completions_route':True,'server_llm_mode':'ollama_openai','server_llm_model':'gemma4:26b','retry_empty_response_enabled':False,'unsafe_record_count':0,'answer_permission_count':0,'can_answer_directly_count':0,'can_prove_claims_count':0,'retrieval_execution_allowed_count':0,'source_truth_mutation_allowed_count':0}}), encoding='utf-8')
    assert check_engineering_webui_answer_server_quality(report_path=path, require_retry_empty_response=True)['quality_status'] == 'FAIL'

def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path/'report.json'
    path.write_text(json.dumps({'summary':{'page_record_count':10,'gated_draft_count':1,'ready_for_webui':True,'openai_compatible_chat_completions_route':True,'server_llm_mode':'ollama_openai','server_llm_model':'gemma4:26b','retry_empty_response_enabled':True,'unsafe_record_count':0,'answer_permission_count':1,'can_answer_directly_count':0,'can_prove_claims_count':0,'retrieval_execution_allowed_count':0,'source_truth_mutation_allowed_count':0}}), encoding='utf-8')
    assert check_engineering_webui_answer_server_quality(report_path=path, require_no_answer_permission=True)['quality_status'] == 'FAIL'
