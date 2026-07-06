# TRACE-Net repo audit: Engram / Self-RAG / CRAG / answer pipeline

Repo: `C:\Users\juswil\Documents\GitHub\heico-ai-internship-summer-2026`
Matched files: `19322`

## Category counts
- `table_visual_ocr`: 17113
- `graph_vector`: 7319
- `context_pack`: 3581
- `webui`: 1369
- `feedback`: 1126
- `crag`: 1078
- `self_rag`: 916
- `engram`: 815
- `final_gate`: 596
- `planner`: 78

## Highest-signal files

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L62 `self_rag`: st": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true }, "forbidden_answer_claims": [
- L71 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part
- L157 `planner`: mission": false, "answers_user_question": false, "artifact_authority": "query_planning_only", "can_answer_directly": false, "can_prove_claims": false, "llm_call_allowed": false, "opensearch_
- L14 `context_pack`: "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": { "compression_policy": { "deduplicate_by_page_id_and_source_trace": true, "inc
- L59 `final_gate`: anguage_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates":

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L62 `self_rag`: st": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true }, "forbidden_answer_claims": [
- L71 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part
- L157 `planner`: mission": false, "answers_user_question": false, "artifact_authority": "query_planning_only", "can_answer_directly": false, "can_prove_claims": false, "llm_call_allowed": false, "opensearch_
- L14 `context_pack`: "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": { "compression_policy": { "deduplicate_by_page_id_and_source_trace": true, "inc
- L59 `final_gate`: anguage_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates":

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L62 `self_rag`: st": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true }, "forbidden_answer_claims": [
- L71 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part
- L157 `planner`: mission": false, "answers_user_question": false, "artifact_authority": "query_planning_only", "can_answer_directly": false, "can_prove_claims": false, "llm_call_allowed": false, "opensearch_
- L14 `context_pack`: "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": { "compression_policy": { "deduplicate_by_page_id_and_source_trace": true, "inc
- L59 `final_gate`: anguage_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates":

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L252 `self_rag`: 001" ], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": { "crag_retry_triggers": [ "seed entity not resolved", "exact table evidenc
- L265 `self_rag`: it/safety/approval claims unless source explicitly says so" ], "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do
- L299 `self_rag`: }, "source_query_planner_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\query_planner\\trace_net_engineering_query_planner_v1.json", "status": "ENGINEERING_CONTE
- L26 `crag`: o install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "required_blocks": [
- L69 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: ties": ["120-29073-001"], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": {"crag_retry_triggers": ["seed entity not resolved", "exact table evidence missing for part-number ques
- L1 `self_rag`: guage", "forbid fit/safety/approval claims unless source explicitly says so"], "self_rag_checks": ["every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved r
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "required_blocks": ["what_is_proven", "candidate_or_relat
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "intent_family": "exact_part_lookup", "llm_call_allowed":
- L1 `crag`: eated as exact proof", "semantic-only evidence is not treated as exact proof", "repair/procedure claims include warnings/cautions if present"]}, "source_truth_mutation_allowed": false, "source_truth_require

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L75 `self_rag`: ": "engineering_q0001", "ready_for_gemma_context": true, "ready_for_self_rag_check": true, "requested_change": null, "required_route_slot_count": 4, "retrieval_execution_allowed"
- L1517 `self_rag`: 001" ], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": { "crag_retry_triggers": [ "seed entity not resolved", "exact table evidenc
- L1530 `self_rag`: it/safety/approval claims unless source explicitly says so" ], "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do
- L1557 `self_rag`: lse }, "source_blueprint_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "status":
- L1594 `self_rag`: t_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_a

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: "question_id": "engineering_q0001", "ready_for_gemma_context": true, "ready_for_self_rag_check": true, "requested_change": null, "required_route_slot_count": 4, "retrieval_execution_allowed": false, "route_ev
- L1 `self_rag`: ties": ["120-29073-001"], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": {"crag_retry_triggers": ["seed entity not resolved", "exact table evidence missing for part-number ques
- L1 `self_rag`: guage", "forbid fit/safety/approval claims unless source explicitly says so"], "self_rag_checks": ["every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved r
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "required_blocks": ["what_is_proven", "candidate_or_relat
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "high_signal_evidence_capsule_count": 30, "high_signal_fi

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L252 `self_rag`: 001" ], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": { "crag_retry_triggers": [ "seed entity not resolved", "exact table evidenc
- L265 `self_rag`: it/safety/approval claims unless source explicitly says so" ], "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do
- L299 `self_rag`: }, "source_query_planner_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\query_planner\\trace_net_engineering_query_planner_v1.json", "status": "ENGINE
- L26 `crag`: o install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "required_blocks": [
- L69 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: ties": ["120-29073-001"], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": {"crag_retry_triggers": ["seed entity not resolved", "exact table evidence missing for part-number ques
- L1 `self_rag`: guage", "forbid fit/safety/approval claims unless source explicitly says so"], "self_rag_checks": ["every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved r
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "required_blocks": ["what_is_proven", "candidate_or_relat
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "intent_family": "exact_part_lookup", "llm_call_allowed":
- L1 `crag`: eated as exact proof", "semantic-only evidence is not treated as exact proof", "repair/procedure claims include warnings/cautions if present"]}, "source_truth_mutation_allowed": false, "source_truth_require

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L75 `self_rag`: ": "engineering_q0001", "ready_for_gemma_context": true, "ready_for_self_rag_check": true, "requested_change": null, "required_route_slot_count": 4, "retrieval_execution_allowed"
- L1517 `self_rag`: 001" ], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": { "crag_retry_triggers": [ "seed entity not resolved", "exact table evidenc
- L1530 `self_rag`: it/safety/approval claims unless source explicitly says so" ], "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do
- L1557 `self_rag`: lse }, "source_blueprint_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json",
- L1594 `self_rag`: t_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_a

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: "question_id": "engineering_q0001", "ready_for_gemma_context": true, "ready_for_self_rag_check": true, "requested_change": null, "required_route_slot_count": 4, "retrieval_execution_allowed": false, "route_ev
- L1 `self_rag`: ties": ["120-29073-001"], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": {"crag_retry_triggers": ["seed entity not resolved", "exact table evidence missing for part-number ques
- L1 `self_rag`: guage", "forbid fit/safety/approval claims unless source explicitly says so"], "self_rag_checks": ["every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved r
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "required_blocks": ["what_is_proven", "candidate_or_relat
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "high_signal_evidence_capsule_count": 30, "high_signal_fi

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L252 `self_rag`: 001" ], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": { "crag_retry_triggers": [ "seed entity not resolved", "exact table evidenc
- L265 `self_rag`: it/safety/approval claims unless source explicitly says so" ], "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do
- L299 `self_rag`: }, "source_query_planner_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\query_planner\\trace_net_engineering_query_planner_v1.json", "status": "ENGINEERIN
- L26 `crag`: o install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "required_blocks": [
- L69 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: ties": ["120-29073-001"], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": {"crag_retry_triggers": ["seed entity not resolved", "exact table evidence missing for part-number ques
- L1 `self_rag`: guage", "forbid fit/safety/approval claims unless source explicitly says so"], "self_rag_checks": ["every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved r
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "required_blocks": ["what_is_proven", "candidate_or_relat
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "intent_family": "exact_part_lookup", "llm_call_allowed":
- L1 `crag`: eated as exact proof", "semantic-only evidence is not treated as exact proof", "repair/procedure claims include warnings/cautions if present"]}, "source_truth_mutation_allowed": false, "source_truth_require

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L75 `self_rag`: ": "engineering_q0001", "ready_for_gemma_context": true, "ready_for_self_rag_check": true, "requested_change": null, "required_route_slot_count": 4, "retrieval_execution_allowed"
- L1517 `self_rag`: 001" ], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": { "crag_retry_triggers": [ "seed entity not resolved", "exact table evidenc
- L1530 `self_rag`: it/safety/approval claims unless source explicitly says so" ], "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do
- L1557 `self_rag`: lse }, "source_blueprint_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "st
- L1594 `self_rag`: t_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_a

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: "question_id": "engineering_q0001", "ready_for_gemma_context": true, "ready_for_self_rag_check": true, "requested_change": null, "required_route_slot_count": 4, "retrieval_execution_allowed": false, "route_ev
- L1 `self_rag`: ties": ["120-29073-001"], "selected_playbook_id": "part_number_evidence_pack", "self_rag_crag_contract": {"crag_retry_triggers": ["seed entity not resolved", "exact table evidence missing for part-number ques
- L1 `self_rag`: guage", "forbid fit/safety/approval claims unless source explicitly says so"], "self_rag_checks": ["every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved r
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "required_blocks": ["what_is_proven", "candidate_or_relat
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "high_signal_evidence_capsule_count": 30, "high_signal_fi

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: e_exact_seed_first": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true}, "forbidden_answer_claims": ["approved replacement wit
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "intent_family": "exact_part_lookup", "intent_score": 4,
- L1 `context_pack`: tion": false, "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": {"compression_policy": {"deduplicate_by_page_id_and_source_trace": true, "include_missing_evidence_explicit
- L1 `final_gate`: ": {"candidate_language_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates": true, "self_rag_
- L1 `graph_vector`: ering_playbook_cards": 1, "exact_evidence_records": 8, "few_shot_examples": 1, "graph_neighbors": 12, "normal_text_context_pages": 4, "table_records": 8, "visual_or_callout_records": 4}, "route_context_nee

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: e_exact_seed_first": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true}, "forbidden_answer_claims": ["approved replacement wit
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "intent_family": "exact_part_lookup", "intent_score": 4,
- L1 `context_pack`: tion": false, "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": {"compression_policy": {"deduplicate_by_page_id_and_source_trace": true, "include_missing_evidence_explicit
- L1 `final_gate`: ": {"candidate_language_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates": true, "self_rag_
- L1 `graph_vector`: ering_playbook_cards": 1, "exact_evidence_records": 8, "few_shot_examples": 1, "graph_neighbors": 12, "normal_text_context_pages": 4, "table_records": 8, "visual_or_callout_records": 4}, "route_context_nee

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1_records.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: e_exact_seed_first": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true}, "forbidden_answer_claims": ["approved replacement wit
- L1 `crag`: m/function", "safe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part"], "intent_family": "exact_part_lookup", "intent_score": 4,
- L1 `context_pack`: tion": false, "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": {"compression_policy": {"deduplicate_by_page_id_and_source_trace": true, "include_missing_evidence_explicit
- L1 `final_gate`: ": {"candidate_language_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates": true, "self_rag_
- L1 `graph_vector`: ering_playbook_cards": 1, "exact_evidence_records": 8, "few_shot_examples": 1, "graph_neighbors": 12, "normal_text_context_pages": 4, "table_records": 8, "visual_or_callout_records": 4}, "route_context_nee

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.md`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L1 `context_pack`: # TRACE-Net Engineering Context Pack Blueprint v1 Quality status: **PASS** ## Summary - Blueprints: 1 - Route evidence slots: `{'graph': 1, 'normal_text'
- L13 `context_pack`: ch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### context_pack_blueprint_0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearby similar parts. Use every TRA
- L8 `graph_vector`: uality status: **PASS** ## Summary - Blueprints: 1 - Route evidence slots: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### con
- L17 `graph_vector`: d show source boundaries.` - Playbook: `part_number_evidence_pack` - Routes: `['graph', 'normal_text', 'route_dispatch', 'table']` - Candidate language required: `False` - Answer mode: `exact_evidence_firs
- L8 `table_visual_ocr`: 1 - Route evidence slots: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### context_pack_blueprint_0001 — exact_part_lookup - Que

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_quality.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L9 `context_pack`: ": 1, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_blueprint_count": 1, "intent_family_counts": { "exact_part_lookup": 1 }, "llm_call_allowed_count": 0,
- L16 `graph_vector`: opensearch_write_attempt_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph":
- L19 `graph_vector`: trieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "
- L22 `table_visual_ocr`: : { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query_planner_quality_status": "PASS", "source_truth_mutat

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_summary.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L7 `context_pack`: _count": 1, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_blueprint_count": 1, "intent_family_counts": { "exact_part_lookup": 1 }, "llm_call_allowed_count": 0, "open
- L14 `graph_vector`: "opensearch_write_attempt_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1,
- L17 `graph_vector`: "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query
- L20 `table_visual_ocr`: _counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query_planner_quality_status": "PASS", "source_truth_mutation_allo

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1.md`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L1 `context_pack`: # TRACE-Net Engineering Context Pack Builder v1.2 Quality status: **PASS** ## Summary - Context packs: 1 - Artifact corpus records: 23044 - Artifact reco
- L7 `context_pack`: Engineering Context Pack Builder v1.2 Quality status: **PASS** ## Summary - Context packs: 1 - Artifact corpus records: 23044 - Artifact record counts: `{'fishnet_route_dispatch_handoff': 1019, 'table_exact_s
- L19 `context_pack`: spatch': 8, 'table': 8}` - Missing evidence notes: 0 ## Packs ### engineering_context_pack_0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evi
- L9 `graph_vector`: ch_handoff': 1019, 'table_exact_search_adapter': 1515, 'page_context_v2': 510, 'leiden_communities': 20000, 'image_visual_observer': 0}` - Missing optional artifact inputs: `[{'artifact_name': 'image_visual
- L14 `graph_vector`: 30 - High-signal capsules: 30 - Fallback capsules: 0 - Route capsule counts: `{'graph': 8, 'normal_text': 6, 'route_dispatch': 8, 'table': 8}` - Missing evidence notes: 0 ## Packs ### engineering_context

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_quality.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L38 `self_rag`: t_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_a
- L25 `context_pack`: }, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_di
- L19 `graph_vector`: fishnet_route_dispatch_handoff": 1019, "image_visual_observer": 0, "leiden_communities": 20000, "page_context_v2": 510, "table_exact_search_adapter": 1515 }, "can_answer_dire
- L27 `graph_vector`: ntext_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch": 8, "table": 8 }, "intent_family_counts": { "ex
- L40 `graph_vector`: ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_capsule_counts": { "grap

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_summary.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L36 `self_rag`: tempt_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed
- L23 `context_pack`: : 1515 }, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch":
- L17 `graph_vector`: "fishnet_route_dispatch_handoff": 1019, "image_visual_observer": 0, "leiden_communities": 20000, "page_context_v2": 510, "table_exact_search_adapter": 1515 }, "can_answer_directly_cou
- L25 `graph_vector`: "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch": 8, "table": 8 }, "intent_family_counts": { "exact_part_loo
- L38 `graph_vector`: cks_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_capsule_counts": { "graph": 8,

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.md`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L1 `context_pack`: # TRACE-Net Engineering Context Pack Blueprint v1 Quality status: **PASS** ## Summary - Blueprints: 1 - Route evidence slots: `{'graph': 1, 'normal_text'
- L13 `context_pack`: ch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### context_pack_blueprint_0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearby similar parts. Use every TRA
- L8 `graph_vector`: uality status: **PASS** ## Summary - Blueprints: 1 - Route evidence slots: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### con
- L17 `graph_vector`: d show source boundaries.` - Playbook: `part_number_evidence_pack` - Routes: `['graph', 'normal_text', 'route_dispatch', 'table']` - Candidate language required: `False` - Answer mode: `exact_evidence_firs
- L8 `table_visual_ocr`: 1 - Route evidence slots: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### context_pack_blueprint_0001 — exact_part_lookup - Que

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_quality.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L9 `context_pack`: ": 1, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_blueprint_count": 1, "intent_family_counts": { "exact_part_lookup": 1 }, "llm_call_allowed_count": 0,
- L16 `graph_vector`: opensearch_write_attempt_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph":
- L19 `graph_vector`: trieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "
- L22 `table_visual_ocr`: : { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query_planner_quality_status": "PASS", "source_truth_mutat

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_summary.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L7 `context_pack`: _count": 1, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_blueprint_count": 1, "intent_family_counts": { "exact_part_lookup": 1 }, "llm_call_allowed_count": 0, "open
- L14 `graph_vector`: "opensearch_write_attempt_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1,
- L17 `graph_vector`: "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query
- L20 `table_visual_ocr`: _counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query_planner_quality_status": "PASS", "source_truth_mutation_allo

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1.md`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L1 `context_pack`: # TRACE-Net Engineering Context Pack Builder v1.2 Quality status: **PASS** ## Summary - Context packs: 1 - Artifact corpus records: 23044 - Artifact reco
- L7 `context_pack`: Engineering Context Pack Builder v1.2 Quality status: **PASS** ## Summary - Context packs: 1 - Artifact corpus records: 23044 - Artifact record counts: `{'fishnet_route_dispatch_handoff': 1019, 'table_exact_s
- L19 `context_pack`: spatch': 8, 'table': 8}` - Missing evidence notes: 0 ## Packs ### engineering_context_pack_0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evi
- L9 `graph_vector`: ch_handoff': 1019, 'table_exact_search_adapter': 1515, 'page_context_v2': 510, 'leiden_communities': 20000, 'image_visual_observer': 0}` - Missing optional artifact inputs: `[{'artifact_name': 'image_visual
- L14 `graph_vector`: 30 - High-signal capsules: 30 - Fallback capsules: 0 - Route capsule counts: `{'graph': 8, 'normal_text': 6, 'route_dispatch': 8, 'table': 8}` - Missing evidence notes: 0 ## Packs ### engineering_context

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_quality.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L38 `self_rag`: t_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_a
- L25 `context_pack`: }, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_di
- L19 `graph_vector`: fishnet_route_dispatch_handoff": 1019, "image_visual_observer": 0, "leiden_communities": 20000, "page_context_v2": 510, "table_exact_search_adapter": 1515 }, "can_answer_dire
- L27 `graph_vector`: ntext_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch": 8, "table": 8 }, "intent_family_counts": { "ex
- L40 `graph_vector`: ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_capsule_counts": { "grap

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_summary.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L36 `self_rag`: tempt_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed
- L23 `context_pack`: : 1515 }, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch":
- L17 `graph_vector`: "fishnet_route_dispatch_handoff": 1019, "image_visual_observer": 0, "leiden_communities": 20000, "page_context_v2": 510, "table_exact_search_adapter": 1515 }, "can_answer_directly_cou
- L25 `graph_vector`: "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch": 8, "table": 8 }, "intent_family_counts": { "exact_part_loo
- L38 `graph_vector`: cks_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_capsule_counts": { "graph": 8,

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1.md`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L1 `context_pack`: # TRACE-Net Engineering Context Pack Blueprint v1 Quality status: **PASS** ## Summary - Blueprints: 1 - Route evidence slots: `{'graph': 1, 'normal_text'
- L13 `context_pack`: ch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### context_pack_blueprint_0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearby similar parts. Use every TRA
- L8 `graph_vector`: uality status: **PASS** ## Summary - Blueprints: 1 - Route evidence slots: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### con
- L17 `graph_vector`: d show source boundaries.` - Playbook: `part_number_evidence_pack` - Routes: `['graph', 'normal_text', 'route_dispatch', 'table']` - Candidate language required: `False` - Answer mode: `exact_evidence_firs
- L8 `table_visual_ocr`: 1 - Route evidence slots: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` - Blueprints requiring source truth: 1 ## Blueprints ### context_pack_blueprint_0001 — exact_part_lookup - Que

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_quality.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L9 `context_pack`: ": 1, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_blueprint_count": 1, "intent_family_counts": { "exact_part_lookup": 1 }, "llm_call_allowed_count": 0,
- L16 `graph_vector`: opensearch_write_attempt_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph":
- L19 `graph_vector`: trieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "
- L22 `table_visual_ocr`: : { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query_planner_quality_status": "PASS", "source_truth_mutat

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_blueprint/trace_net_engineering_context_pack_blueprint_v1_summary.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L7 `context_pack`: _count": 1, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_blueprint_count": 1, "intent_family_counts": { "exact_part_lookup": 1 }, "llm_call_allowed_count": 0, "open
- L14 `graph_vector`: "opensearch_write_attempt_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1,
- L17 `graph_vector`: "retrieval_execution_allowed_count": 0, "route_evidence_slot_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query
- L20 `table_visual_ocr`: _counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "source_query_plan_count": 1, "source_query_planner_quality_status": "PASS", "source_truth_mutation_allo

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1.md`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L1 `context_pack`: # TRACE-Net Engineering Context Pack Builder v1.2 Quality status: **PASS** ## Summary - Context packs: 1 - Artifact corpus records: 23044 - Artifact reco
- L7 `context_pack`: Engineering Context Pack Builder v1.2 Quality status: **PASS** ## Summary - Context packs: 1 - Artifact corpus records: 23044 - Artifact record counts: `{'fishnet_route_dispatch_handoff': 1019, 'table_exact_s
- L19 `context_pack`: spatch': 8, 'table': 8}` - Missing evidence notes: 0 ## Packs ### engineering_context_pack_0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evi
- L9 `graph_vector`: ch_handoff': 1019, 'table_exact_search_adapter': 1515, 'page_context_v2': 510, 'leiden_communities': 20000, 'image_visual_observer': 0}` - Missing optional artifact inputs: `[{'artifact_name': 'image_visual
- L14 `graph_vector`: 30 - High-signal capsules: 30 - Fallback capsules: 0 - Route capsule counts: `{'graph': 8, 'normal_text': 6, 'route_dispatch': 8, 'table': 8}` - Missing evidence notes: 0 ## Packs ### engineering_context

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_quality.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L38 `self_rag`: t_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_a
- L25 `context_pack`: }, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_di
- L19 `graph_vector`: fishnet_route_dispatch_handoff": 1019, "image_visual_observer": 0, "leiden_communities": 20000, "page_context_v2": 510, "table_exact_search_adapter": 1515 }, "can_answer_dire
- L27 `graph_vector`: ntext_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch": 8, "table": 8 }, "intent_family_counts": { "ex
- L40 `graph_vector`: ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_capsule_counts": { "grap

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/context_pack_builder/trace_net_engineering_context_pack_builder_v1_summary.json`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L36 `self_rag`: tempt_count": 0, "packs_ready_for_gemma_context_count": 1, "packs_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed
- L23 `context_pack`: : 1515 }, "can_answer_directly_count": 0, "can_prove_claims_count": 0, "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch":
- L17 `graph_vector`: "fishnet_route_dispatch_handoff": 1019, "image_visual_observer": 0, "leiden_communities": 20000, "page_context_v2": 510, "table_exact_search_adapter": 1515 }, "can_answer_directly_cou
- L25 `graph_vector`: "context_pack_count": 1, "high_signal_route_evidence_capsule_counts": { "graph": 8, "normal_text": 6, "route_dispatch": 8, "table": 8 }, "intent_family_counts": { "exact_part_loo
- L38 `graph_vector`: cks_ready_for_self_rag_check_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "retrieval_execution_allowed_count": 0, "route_evidence_capsule_counts": { "graph": 8,

### `tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: """TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/st
- L22 `self_rag`: le, List, Mapping, Optional, Sequence, Tuple MODULE_VERSION = "trace_net_webui_self_rag_crag_bridge_v1" REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json" STAGE_REPORT_NAMES = { "query_planner
- L23 `self_rag`: SION = "trace_net_webui_self_rag_crag_bridge_v1" REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json" STAGE_REPORT_NAMES = { "query_planner": "trace_net_engineering_query_planner_v1.json", "c
- L29 `self_rag`: ntext_pack_builder": "trace_net_engineering_context_pack_builder_v1.json", "self_rag": "trace_net_engineering_context_self_rag_check_v1.json", "crag_retry": "trace_net_engineering_context_crag_retry_p
- L29 `self_rag`: g_context_pack_builder_v1.json", "self_rag": "trace_net_engineering_context_self_rag_check_v1.json", "crag_retry": "trace_net_engineering_context_crag_retry_plan_v1.json", } ARTIFACT_TOOL_KEYS = {

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
Categories: graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `planner`: # TRACE-Net Engineering Query Planner v1 Quality status: **PASS** ## Summary - Query plans: 1 - Intent families: `{'exact_part_lookup': 1}` - Route contex
- L9 `graph_vector`: lans: 1 - Intent families: `{'exact_part_lookup': 1}` - Route context needs: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` ## Query plans ### engineering_q0001 — exact_part_lookup -
- L19 `graph_vector`: act_search', 'promoted_table_value_evidence_search', 'page_context_v2_search', 'graph_neighbor_search', 'route_handoff_lookup']` - Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']
- L20 `graph_vector`: ', 'graph_neighbor_search', 'route_handoff_lookup']` - Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']`
- L9 `table_visual_ocr`: }` - Route context needs: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` ## Query plans ### engineering_q0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearb

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
Categories: graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `planner`: # TRACE-Net Engineering Query Planner v1 Quality status: **PASS** ## Summary - Query plans: 1 - Intent families: `{'exact_part_lookup': 1}` - Route contex
- L9 `graph_vector`: lans: 1 - Intent families: `{'exact_part_lookup': 1}` - Route context needs: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` ## Query plans ### engineering_q0001 — exact_part_lookup -
- L19 `graph_vector`: act_search', 'promoted_table_value_evidence_search', 'page_context_v2_search', 'graph_neighbor_search', 'route_handoff_lookup']` - Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']
- L20 `graph_vector`: ', 'graph_neighbor_search', 'route_handoff_lookup']` - Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']`
- L9 `table_visual_ocr`: }` - Route context needs: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` ## Query plans ### engineering_q0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearb

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
Categories: graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `planner`: # TRACE-Net Engineering Query Planner v1 Quality status: **PASS** ## Summary - Query plans: 1 - Intent families: `{'exact_part_lookup': 1}` - Route contex
- L9 `graph_vector`: lans: 1 - Intent families: `{'exact_part_lookup': 1}` - Route context needs: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` ## Query plans ### engineering_q0001 — exact_part_lookup -
- L19 `graph_vector`: act_search', 'promoted_table_value_evidence_search', 'page_context_v2_search', 'graph_neighbor_search', 'route_handoff_lookup']` - Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']
- L20 `graph_vector`: ', 'graph_neighbor_search', 'route_handoff_lookup']` - Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']`
- L9 `table_visual_ocr`: }` - Route context needs: `{'graph': 1, 'normal_text': 1, 'route_dispatch': 1, 'table': 1}` ## Query plans ### engineering_q0001 — exact_part_lookup - Question: `Find part number 120-29073-001 and nearb

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1_quality.json`
Categories: graph_vector, self_rag, table_visual_ocr, webui
- L16 `graph_vector`: plans_with_seed_entities_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "query_plan_count": 1, "retrieval_execution_allowed_count": 0, "route_context_need
- L20 `graph_vector`: etrieval_execution_allowed_count": 0, "route_context_need_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": {
- L23 `table_visual_ocr`: : { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_number_evidence_pack": 1 }, "source_kernel_quality_sta

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1_summary.json`
Categories: graph_vector, self_rag, table_visual_ocr, webui
- L14 `graph_vector`: "plans_with_seed_entities_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "query_plan_count": 1, "retrieval_execution_allowed_count": 0, "route_context_need_count
- L18 `graph_vector`: "retrieval_execution_allowed_count": 0, "route_context_need_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_numbe
- L21 `table_visual_ocr`: _counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_number_evidence_pack": 1 }, "source_kernel_quality_status": "PAS

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1_quality.json`
Categories: graph_vector, self_rag, table_visual_ocr, webui
- L16 `graph_vector`: plans_with_seed_entities_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "query_plan_count": 1, "retrieval_execution_allowed_count": 0, "route_context_need
- L20 `graph_vector`: etrieval_execution_allowed_count": 0, "route_context_need_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": {
- L23 `table_visual_ocr`: : { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_number_evidence_pack": 1 }, "source_kernel_quality_sta

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1_summary.json`
Categories: graph_vector, self_rag, table_visual_ocr, webui
- L14 `graph_vector`: "plans_with_seed_entities_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "query_plan_count": 1, "retrieval_execution_allowed_count": 0, "route_context_need_count
- L18 `graph_vector`: "retrieval_execution_allowed_count": 0, "route_context_need_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_numbe
- L21 `table_visual_ocr`: _counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_number_evidence_pack": 1 }, "source_kernel_quality_status": "PAS

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1_quality.json`
Categories: graph_vector, self_rag, table_visual_ocr, webui
- L16 `graph_vector`: plans_with_seed_entities_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "query_plan_count": 1, "retrieval_execution_allowed_count": 0, "route_context_need
- L20 `graph_vector`: etrieval_execution_allowed_count": 0, "route_context_need_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": {
- L23 `table_visual_ocr`: : { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_number_evidence_pack": 1 }, "source_kernel_quality_sta

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1_summary.json`
Categories: graph_vector, self_rag, table_visual_ocr, webui
- L14 `graph_vector`: "plans_with_seed_entities_count": 1, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "query_plan_count": 1, "retrieval_execution_allowed_count": 0, "route_context_need_count
- L18 `graph_vector`: "retrieval_execution_allowed_count": 0, "route_context_need_counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_numbe
- L21 `table_visual_ocr`: _counts": { "graph": 1, "normal_text": 1, "route_dispatch": 1, "table": 1 }, "selected_playbook_counts": { "part_number_evidence_pack": 1 }, "source_kernel_quality_status": "PAS

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L2 `self_rag`: ncontext pack builder: used \u2014 stage report built with quality_status=PASS\nSelf-RAG: used \u2014 stage report built with quality_status=PASS\nCRAG retry: skipped_not_needed \u2014 Self-RAG did not requir
- L2 `self_rag`: ge report built with quality_status=PASS\nCRAG retry: skipped_not_needed \u2014 Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans\nroute/dispatch: used \u2014 context
- L2 `self_rag`: re\nGemma LLM: not_called_by_design \u2014 this bridge stops before drafting so Self-RAG/CRAG can be audited separately\nfinal gate: not_called_by_design \u2014 no answer draft is produced by this bridge, so
- L11 `self_rag`: ver\\trace_net_image_visual_observer_v1.json" }, "module": "trace_net_webui_self_rag_crag_bridge_v1", "quality_status": "PASS", "question": "Find part number 120-29073-001 and nearby similar parts. Us
- L28 `self_rag`: s": { "context_pack_blueprint": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "context

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.md`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: # TRACE-Net WebUI Self-RAG / CRAG Bridge v1 Quality status: **PASS** ## Question `Find part number 120-29073-001 and nearby similar parts. Use
- L11 `self_rag`: ed tools: `['query_planner', 'context_pack_blueprint', 'context_pack_builder', 'self_rag', 'route_dispatch', 'table_route', 'page_context_v2', 'graph_leiden']` - CRAG retry status: `skipped_not_needed` - Self
- L13 `self_rag`: 'page_context_v2', 'graph_leiden']` - CRAG retry status: `skipped_not_needed` - Self-RAG status counts: `{'READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY': 1}` - CRAG retry plans: `0` - Evidence capsules: `30` ## Checkl
- L23 `self_rag`: s=PASS context pack builder: used — stage report built with quality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retr
- L24 `self_rag`: — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack b

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L4 `self_rag`: s=PASS context pack builder: used — stage report built with quality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retr
- L5 `self_rag`: — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack b
- L12 `self_rag`: put here Gemma LLM: not_called_by_design — this bridge stops before drafting so Self-RAG/CRAG can be audited separately final gate: not_called_by_design — no answer draft is produced by this bridge, so final
- L5 `crag`: uality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans
- L5 `crag`: h quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack builder selected/loade

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: , "label": "query planner", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\query_planner\\trace_net_engineering_query_planner_v1.json", "quality_status": "PASS", "rea
- L2 `self_rag`: : "context pack blueprint", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "quality_sta
- L3 `self_rag`: l": "context pack builder", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\context_pack_builder\\trace_net_engineering_context_pack_builder_v1.json", "quality_status"
- L4 `self_rag`: S", "status": "used", "tool_id": "context_pack_builder"} {"count": 1, "label": "Self-RAG", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\self_rag_check\\trace_net_en
- L4 `self_rag`: t": 1, "label": "Self-RAG", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\stage_reports\\self_rag_check\\trace_net_engineering_context_self_rag_check_v1.json", "quality_status": "P

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L2 `self_rag`: ncontext pack builder: used \u2014 stage report built with quality_status=PASS\nSelf-RAG: used \u2014 stage report built with quality_status=PASS\nCRAG retry: skipped_not_needed \u2014 Self-RAG did not requir
- L2 `self_rag`: ge report built with quality_status=PASS\nCRAG retry: skipped_not_needed \u2014 Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans\nroute/dispatch: used \u2014 context
- L2 `self_rag`: re\nGemma LLM: not_called_by_design \u2014 this bridge stops before drafting so Self-RAG/CRAG can be audited separately\nfinal gate: not_called_by_design \u2014 no answer draft is produced by this bridge, so
- L11 `self_rag`: ver\\trace_net_image_visual_observer_v1.json" }, "module": "trace_net_webui_self_rag_crag_bridge_v1", "quality_status": "PASS", "question": "Find part number 120-29073-001 and nearby similar parts. Us
- L28 `self_rag`: s": { "context_pack_blueprint": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json",

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1.md`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: # TRACE-Net WebUI Self-RAG / CRAG Bridge v1 Quality status: **PASS** ## Question `Find part number 120-29073-001 and nearby similar parts. Use
- L11 `self_rag`: ed tools: `['query_planner', 'context_pack_blueprint', 'context_pack_builder', 'self_rag', 'route_dispatch', 'table_route', 'page_context_v2', 'graph_leiden']` - CRAG retry status: `skipped_not_needed` - Self
- L13 `self_rag`: 'page_context_v2', 'graph_leiden']` - CRAG retry status: `skipped_not_needed` - Self-RAG status counts: `{'READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY': 1}` - CRAG retry plans: `0` - Evidence capsules: `30` ## Checkl
- L23 `self_rag`: s=PASS context pack builder: used — stage report built with quality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retr
- L24 `self_rag`: — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack b

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L4 `self_rag`: s=PASS context pack builder: used — stage report built with quality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retr
- L5 `self_rag`: — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack b
- L12 `self_rag`: put here Gemma LLM: not_called_by_design — this bridge stops before drafting so Self-RAG/CRAG can be audited separately final gate: not_called_by_design — no answer draft is produced by this bridge, so final
- L5 `crag`: uality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans
- L5 `crag`: h quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack builder selected/loade

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: , "label": "query planner", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\query_planner\\trace_net_engineering_query_planner_v1.json", "quality_status": "
- L2 `self_rag`: : "context pack blueprint", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "
- L3 `self_rag`: l": "context pack builder", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\context_pack_builder\\trace_net_engineering_context_pack_builder_v1.json", "qual
- L4 `self_rag`: S", "status": "used", "tool_id": "context_pack_builder"} {"count": 1, "label": "Self-RAG", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\self_rag_check\\t
- L4 `self_rag`: t": 1, "label": "Self-RAG", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_fresh_test\\stage_reports\\self_rag_check\\trace_net_engineering_context_self_rag_check_v1.json", "quality_

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L2 `self_rag`: ncontext pack builder: used \u2014 stage report built with quality_status=PASS\nSelf-RAG: used \u2014 stage report built with quality_status=PASS\nCRAG retry: skipped_not_needed \u2014 Self-RAG did not requir
- L2 `self_rag`: ge report built with quality_status=PASS\nCRAG retry: skipped_not_needed \u2014 Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans\nroute/dispatch: used \u2014 context
- L2 `self_rag`: re\nGemma LLM: not_called_by_design \u2014 this bridge stops before drafting so Self-RAG/CRAG can be audited separately\nfinal gate: not_called_by_design \u2014 no answer draft is produced by this bridge, so
- L12 `self_rag`: race_net_webui_visual_context_bridge_v1.json" }, "module": "trace_net_webui_self_rag_crag_bridge_v1", "quality_status": "PASS", "question": "Find part number 120-29073-001 and nearby similar parts. Us
- L29 `self_rag`: s": { "context_pack_blueprint": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1.md`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: # TRACE-Net WebUI Self-RAG / CRAG Bridge v1 Quality status: **PASS** ## Question `Find part number 120-29073-001 and nearby similar parts. Use
- L11 `self_rag`: ed tools: `['query_planner', 'context_pack_blueprint', 'context_pack_builder', 'self_rag', 'route_dispatch', 'table_route', 'page_context_v2', 'graph_leiden', 'visual_image_route', 'webui_visual_context_bridg
- L13 `self_rag`: e', 'webui_visual_context_bridge']` - CRAG retry status: `skipped_not_needed` - Self-RAG status counts: `{'READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY': 1}` - CRAG retry plans: `0` - Evidence capsules: `30` - Visual c
- L25 `self_rag`: s=PASS context pack builder: used — stage report built with quality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retr
- L26 `self_rag`: — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack b

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L4 `self_rag`: s=PASS context pack builder: used — stage report built with quality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retr
- L5 `self_rag`: — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack b
- L13 `self_rag`: put here Gemma LLM: not_called_by_design — this bridge stops before drafting so Self-RAG/CRAG can be audited separately final gate: not_called_by_design — no answer draft is produced by this bridge, so final
- L5 `crag`: uality_status=PASS Self-RAG: used — stage report built with quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans
- L5 `crag`: h quality_status=PASS CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans route/dispatch: used — context pack builder selected/loade

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: , "label": "query planner", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\query_planner\\trace_net_engineering_query_planner_v1.json", "quality_status": "PASS
- L2 `self_rag`: : "context pack blueprint", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\context_pack_blueprint\\trace_net_engineering_context_pack_blueprint_v1.json", "qual
- L3 `self_rag`: l": "context pack builder", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\context_pack_builder\\trace_net_engineering_context_pack_builder_v1.json", "quality_
- L4 `self_rag`: S", "status": "used", "tool_id": "context_pack_builder"} {"count": 1, "label": "Self-RAG", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\self_rag_check\\trace
- L4 `self_rag`: t": 1, "label": "Self-RAG", "path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\stage_reports\\self_rag_check\\trace_net_engineering_context_self_rag_check_v1.json", "quality_stat

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: """TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/st
- L22 `self_rag`: le, List, Mapping, Optional, Sequence, Tuple MODULE_VERSION = "trace_net_webui_self_rag_crag_bridge_v1" REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json" STAGE_REPORT_NAMES = { "query_planner
- L23 `self_rag`: SION = "trace_net_webui_self_rag_crag_bridge_v1" REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json" STAGE_REPORT_NAMES = { "query_planner": "trace_net_engineering_query_planner_v1.json", "c
- L29 `self_rag`: ntext_pack_builder": "trace_net_engineering_context_pack_builder_v1.json", "self_rag": "trace_net_engineering_context_self_rag_check_v1.json", "crag_retry": "trace_net_engineering_context_crag_retry_p
- L29 `self_rag`: g_context_pack_builder_v1.json", "self_rag": "trace_net_engineering_context_self_rag_check_v1.json", "crag_retry": "trace_net_engineering_context_crag_retry_plan_v1.json", } ARTIFACT_TOOL_KEYS = {

### `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L4 `self_rag`: import json from pathlib import Path from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge def _write(path: Path, payload: dict) -> dict: path.parent.mkdir(parents=True, exist_ok=
- L13 `self_rag`: t=2), encoding="utf-8") return payload def test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch): kernel = tmp_path / "kernel.json" kernel.write_text(j
- L58 `self_rag`: r"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"], payload) def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score): assert context_pack_p
- L63 `self_rag`: "quality_status": "PASS", "summary": { "self_rag_record_count": 1, "ready_for_gemma_draft_count": 0, "crag_retry_required_count": 1,
- L66 `self_rag`: aft_count": 0, "crag_retry_required_count": 1, "self_rag_status_counts": {"CRAG_RETRY_REQUIRED": 1}, }, "records": [{"self_rag_record_id": "sr1", "crag_

### `local_data/organization/trace_net/engineering_engram_answer_runner_prompt_overlay_smoke_v1/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.json`
Categories: context_pack, crag, engram, feedback, graph_vector, self_rag, table_visual_ocr, webui
- L12 `engram`: unner overlay smoke behind explicit CLI flag", "proof_boundary": "Retrieved Engram overlays shape answer behavior only; factual manual claims require current proof_context citations." }, "output_pat
- L14 `engram`: context citations." }, "output_path": "local_data\\organization\\trace_net\\engineering_engram_answer_runner_prompt_overlay_smoke_v1\\trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.json", "ove
- L14 `engram`: \trace_net\\engineering_engram_answer_runner_prompt_overlay_smoke_v1\\trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.json", "overlay_map_path": "local_data\\organization\\trace_net\\engineering_en
- L15 `engram`: lay_smoke_v1.json", "overlay_map_path": "local_data\\organization\\trace_net\\engineering_engram_answer_runner_prompt_overlay_smoke_v1\\trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_overlay_map.j
- L15 `engram`: \trace_net\\engineering_engram_answer_runner_prompt_overlay_smoke_v1\\trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_overlay_map.json", "overlay_records": [ { "answer_permission": false,

### `local_data/organization/trace_net/engineering_engram_answer_runner_prompt_overlay_smoke_v1/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_records.jsonl`
Categories: context_pack, crag, engram, feedback, graph_vector, self_rag, table_visual_ocr, webui
- L1 `engram`: erlay_char_count": 1768, "overlay_text": "TRACE-NET H24 ANSWER-RUNNER RETRIEVED ENGRAM OVERLAY\nUse this overlay as behavior guidance only. It is not proof.\nManual/source claims still require current proof
- L1 `engram`: Manual/source claims still require current proof_context citations.\nDo not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.\ntarget_question_id: q12\n\n--- retrie
- L1 `engram`: nterchangeability_boundary task_type=interchangeability_boundary ---\nTRACE-NET ENGRAM RETRIEVAL GUIDANCE \u2014 BEHAVIOR ONLY, NOT PROOF\nquery_id: h19_q_interchangeability_boundary\ntask_type: interchange
- L1 `engram`: approved replacement? Require explicit source authority.\n\nUse these retrieved Engram atoms to shape answer behavior only. Do not use Engram memory as manual evidence.\nManual/source claims still require c
- L1 `engram`: .\n\nUse these retrieved Engram atoms to shape answer behavior only. Do not use Engram memory as manual evidence.\nManual/source claims still require current proof_context citations from TRACE-Net.\n\n- [pr

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1_quality_check.json`
Categories: context_pack, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L2 `self_rag`: { "checked_report_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\trace_net_webui_self_rag_crag_bridge_v1.json", "failures": [], "quality_status": "PASS", "summary":
- L2 `self_rag`: ocal_data\\organization\\trace_net\\webui_self_rag_crag_bridge\\trace_net_webui_self_rag_crag_bridge_v1.json", "failures": [], "quality_status": "PASS", "summary": { "answer_permission_count": 0,
- L35 `self_rag`: y TRACE-Net evidence route that is available and show source boundaries.", "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "RE
- L36 `self_rag`: and show source boundaries.", "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 },
- L37 `self_rag`: g_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mut

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1_summary.json`
Categories: context_pack, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L31 `self_rag`: ery TRACE-Net evidence route that is available and show source boundaries.", "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FO
- L32 `self_rag`: ble and show source boundaries.", "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self
- L33 `self_rag`: _crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mutation_al
- L36 `self_rag`: "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mutation_allowed_count": 0, "status_counts": { "input_missing": 1, "not_called_b
- L54 `self_rag`: "query_planner", "context_pack_blueprint", "context_pack_builder", "self_rag", "route_dispatch", "table_route", "page_context_v2", "graph_leiden" ] }

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1_summary.json`
Categories: context_pack, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L31 `self_rag`: ery TRACE-Net evidence route that is available and show source boundaries.", "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FO
- L32 `self_rag`: ble and show source boundaries.", "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self
- L33 `self_rag`: _crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mutation_al
- L36 `self_rag`: "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mutation_allowed_count": 0, "status_counts": { "input_missing": 1, "not_called_b
- L54 `self_rag`: "query_planner", "context_pack_blueprint", "context_pack_builder", "self_rag", "route_dispatch", "table_route", "page_context_v2", "graph_leiden" ] }

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1_quality_check.json`
Categories: context_pack, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L2 `self_rag`: { "checked_report_path": "local_data\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\trace_net_webui_self_rag_crag_bridge_v1.json", "failures": [], "quality_status": "PASS", "sum
- L2 `self_rag`: ta\\organization\\trace_net\\webui_self_rag_crag_bridge_visual\\trace_net_webui_self_rag_crag_bridge_v1.json", "failures": [], "quality_status": "PASS", "summary": { "answer_permission_count": 0,
- L35 `self_rag`: source boundaries.", "review_only_visual_context_excluded_count": 10, "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "RE
- L36 `self_rag`: _context_excluded_count": 10, "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 },
- L37 `self_rag`: g_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mut

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1_summary.json`
Categories: context_pack, final_gate, graph_vector, self_rag, table_visual_ocr, webui
- L31 `self_rag`: show source boundaries.", "review_only_visual_context_excluded_count": 10, "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FO
- L32 `self_rag`: sual_context_excluded_count": 10, "self_rag_crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self
- L33 `self_rag`: _crag_retry_required_count": 0, "self_rag_ready_for_gemma_draft_count": 1, "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mutation_al
- L36 `self_rag`: "self_rag_status_counts": { "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY": 1 }, "self_rag_used": true, "source_truth_mutation_allowed_count": 0, "status_counts": { "not_called_by_design": 2, "not_w
- L53 `self_rag`: "query_planner", "context_pack_blueprint", "context_pack_builder", "self_rag", "route_dispatch", "table_route", "page_context_v2", "graph_leiden", "visual_image_route", "we

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
Categories: context_pack, crag, graph_vector, planner, self_rag, webui
- L1 `self_rag`: # TRACE-Net WebUI Self-RAG / CRAG Bridge v1 — directory fix This focused fix preserves the existing bridge behavior while making the bridge safe
- L7 `self_rag`: e making the bridge safe on clean output directories. ## Fix `trace_net_webui_self_rag_crag_bridge_v1` now pre-creates every nested stage report directory before calling the existing stage builders: - `sta
- L12 `self_rag`: context_pack_blueprint` - `stage_reports/context_pack_builder` - `stage_reports/self_rag_check` - `stage_reports/crag_retry_plan` This fixes the observed WebUI bridge-server failure where `context_pack_bluep
- L35 `self_rag`: ight should now both reach: - query planner used - context pack builder used - Self-RAG used - CRAG evaluated as `used` or `skipped_not_needed` - quality PASS
- L1 `crag`: # TRACE-Net WebUI Self-RAG / CRAG Bridge v1 — directory fix This focused fix preserves the existing bridge behavior while making the bridge safe on clea

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/README_trace_net_webui_self_rag_crag_bridge_v1.md`
Categories: crag, graph_vector, planner, self_rag, table_visual_ocr, webui
- L1 `self_rag`: # TRACE-Net WebUI Self-RAG / CRAG Bridge v1 This module runs the current engineering-brain artifact stages for one WebUI-style question and write
- L12 `self_rag`: engineering query planner 2. context-pack blueprint 3. context-pack builder 4. Self-RAG evidence check 5. CRAG retry planner CRAG is always evaluated. If Self-RAG does not require retry, the checklist recor
- L15 `self_rag`: 4. Self-RAG evidence check 5. CRAG retry planner CRAG is always evaluated. If Self-RAG does not require retry, the checklist records `crag_retry: skipped_not_needed` instead of falsely saying CRAG was used.
- L35 `self_rag`: # Outputs The main report is: ```text local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.json ``` It also writes: - `trace_net_webui_self_rag_crag_bridge_
- L35 `self_rag`: xt local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.json ``` It also writes: - `trace_net_webui_self_rag_crag_bridge_v1_summary.json` - `trace_net_webui_s

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/self_rag_check/trace_net_engineering_context_self_rag_check_v1.json`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L2 `self_rag`: { "module": "trace_net_engineering_context_self_rag_check_v1", "quality_status": "PASS", "records": [ { "answer_permission": false, "answers_user_quest
- L34 `self_rag`: 01", "crag_retry_reasons": [], "crag_retry_required": false, "critical_missing_evidence_types": [], "draft_mode": "context_draft_allowed_no_final_answer", "evidence_strength_sc
- L69 `self_rag`: lations": [], "selected_playbook_id": "part_number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_00
- L69 `self_rag`: _evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CON
- L70 `self_rag`: f_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_b

### `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/self_rag_check/trace_net_engineering_context_self_rag_check_v1_records.jsonl`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: ng_context_pack_0001", "crag_retry_reasons": [], "crag_retry_required": false, "critical_missing_evidence_types": [], "draft_mode": "context_draft_allowed_no_final_answer", "evidence_strength_score": 90, "f
- L1 `self_rag`: "safety_violations": [], "selected_playbook_id": "part_number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "
- L1 `self_rag`: number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY",
- L1 `self_rag`: , "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_blueprint_id"
- L1 `self_rag`: _net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_blueprint_id": "context_pack_blueprint_0001", "

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/self_rag_check/trace_net_engineering_context_self_rag_check_v1.json`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L2 `self_rag`: { "module": "trace_net_engineering_context_self_rag_check_v1", "quality_status": "PASS", "records": [ { "answer_permission": false, "answers_user_quest
- L34 `self_rag`: 01", "crag_retry_reasons": [], "crag_retry_required": false, "critical_missing_evidence_types": [], "draft_mode": "context_draft_allowed_no_final_answer", "evidence_strength_sc
- L69 `self_rag`: lations": [], "selected_playbook_id": "part_number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_00
- L69 `self_rag`: _evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CON
- L70 `self_rag`: f_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_b

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/self_rag_check/trace_net_engineering_context_self_rag_check_v1_records.jsonl`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: ng_context_pack_0001", "crag_retry_reasons": [], "crag_retry_required": false, "critical_missing_evidence_types": [], "draft_mode": "context_draft_allowed_no_final_answer", "evidence_strength_score": 90, "f
- L1 `self_rag`: "safety_violations": [], "selected_playbook_id": "part_number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "
- L1 `self_rag`: number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY",
- L1 `self_rag`: , "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_blueprint_id"
- L1 `self_rag`: _net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_blueprint_id": "context_pack_blueprint_0001", "

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/self_rag_check/trace_net_engineering_context_self_rag_check_v1.json`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L2 `self_rag`: { "module": "trace_net_engineering_context_self_rag_check_v1", "quality_status": "PASS", "records": [ { "answer_permission": false, "answers_user_quest
- L34 `self_rag`: 01", "crag_retry_reasons": [], "crag_retry_required": false, "critical_missing_evidence_types": [], "draft_mode": "context_draft_allowed_no_final_answer", "evidence_strength_sc
- L69 `self_rag`: lations": [], "selected_playbook_id": "part_number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_00
- L69 `self_rag`: _evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CON
- L70 `self_rag`: f_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_b

### `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/self_rag_check/trace_net_engineering_context_self_rag_check_v1_records.jsonl`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L1 `self_rag`: ng_context_pack_0001", "crag_retry_reasons": [], "crag_retry_required": false, "critical_missing_evidence_types": [], "draft_mode": "context_draft_allowed_no_final_answer", "evidence_strength_score": 90, "f
- L1 `self_rag`: "safety_violations": [], "selected_playbook_id": "part_number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "
- L1 `self_rag`: number_evidence_pack", "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY",
- L1 `self_rag`: , "self_rag_check_version": "trace_net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_blueprint_id"
- L1 `self_rag`: _net_engineering_context_self_rag_check_v1", "self_rag_record_id": "engineering_self_rag_0001", "self_rag_status": "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY", "source_blueprint_id": "context_pack_blueprint_0001", "

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
Categories: context_pack, crag, graph_vector, self_rag, table_visual_ocr, webui
- L4 `self_rag`: import json from pathlib import Path from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge def _write(path: Path, payload: dict) -> dict: path.parent.mkdir(parents=True, exist_ok=
- L13 `self_rag`: t=2), encoding="utf-8") return payload def test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch): kernel = tmp_path / "kernel.json" kernel.write_text(j
- L58 `self_rag`: r"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"], payload) def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score): assert context_pack_p
- L63 `self_rag`: "quality_status": "PASS", "summary": { "self_rag_record_count": 1, "ready_for_gemma_draft_count": 0, "crag_retry_required_count": 1,
- L66 `self_rag`: aft_count": 0, "crag_retry_required_count": 1, "self_rag_status_counts": {"CRAG_RETRY_REQUIRED": 1}, }, "records": [{"self_rag_record_id": "sr1", "crag_

### `tiff/trace_net_engineering_engram_crag_repair_v1.py`
Categories: crag, engram, feedback, final_gate, graph_vector, self_rag
- L9 `engram`: hlib import Path from typing import Any, Mapping, Sequence MODULE = "trace_net_engineering_engram_crag_repair_v1" VERSION = "v1" REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"}
- L243 `engram`: if not quality_failures else "FAIL" records_path = output_dir / "trace_net_engineering_engram_crag_repair_records_v1.jsonl" candidates_path = output_dir / "trace_net_engineering_engram_crag_repair_candidates_v
- L244 `engram`: ram_crag_repair_records_v1.jsonl" candidates_path = output_dir / "trace_net_engineering_engram_crag_repair_candidates_v1.jsonl" check_path = output_dir / "trace_net_engineering_engram_crag_repair_v1_quality_che
- L245 `engram`: ngram_crag_repair_candidates_v1.jsonl" check_path = output_dir / "trace_net_engineering_engram_crag_repair_v1_quality_check.json" manifest_path = output_dir / "trace_net_engineering_engram_crag_repair_v1.json"
- L246 `engram`: _crag_repair_v1_quality_check.json" manifest_path = output_dir / "trace_net_engineering_engram_crag_repair_v1.json" summary = { "module": MODULE, "version": VERSION, "critic_record_coun

### `tiff/trace_net_engineering_engram_crag_repair_v1.py.bak_h29_cli_alias_repair_v1_20260701_150010`
Categories: crag, engram, feedback, final_gate, graph_vector, self_rag
- L9 `engram`: hlib import Path from typing import Any, Mapping, Sequence MODULE = "trace_net_engineering_engram_crag_repair_v1" VERSION = "v1" REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"}
- L243 `engram`: if not quality_failures else "FAIL" records_path = output_dir / "trace_net_engineering_engram_crag_repair_records_v1.jsonl" candidates_path = output_dir / "trace_net_engineering_engram_crag_repair_candidates_v
- L244 `engram`: ram_crag_repair_records_v1.jsonl" candidates_path = output_dir / "trace_net_engineering_engram_crag_repair_candidates_v1.jsonl" check_path = output_dir / "trace_net_engineering_engram_crag_repair_v1_quality_che
- L245 `engram`: ngram_crag_repair_candidates_v1.jsonl" check_path = output_dir / "trace_net_engineering_engram_crag_repair_v1_quality_check.json" manifest_path = output_dir / "trace_net_engineering_engram_crag_repair_v1.json"
- L246 `engram`: _crag_repair_v1_quality_check.json" manifest_path = output_dir / "trace_net_engineering_engram_crag_repair_v1.json" summary = { "module": MODULE, "version": VERSION, "critic_record_coun

### `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_visual_context.py`
Categories: context_pack, graph_vector, self_rag, table_visual_ocr, webui
- L4 `self_rag`: import json from pathlib import Path from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge def _write(path: Path, payload: dict) -> dict: path.parent.mkdir(parents=True, exist_ok=
- L68 `self_rag`: ecords": [{"answer_permission": False}], }, ) def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score): return _write(
- L70 `self_rag`: re): return _write( output_dir / bridge.STAGE_REPORT_NAMES["self_rag"], {"quality_status": "PASS", "summary": {"self_rag_record_count": 1, "crag_retry_required_count": 0}, "rec
- L71 `self_rag`: E_REPORT_NAMES["self_rag"], {"quality_status": "PASS", "summary": {"self_rag_record_count": 1, "crag_retry_required_count": 0}, "records": [{"answer_permission": False}]}, ) def fake_
- L74 `self_rag`: 0}, "records": [{"answer_permission": False}]}, ) def fake_crag(*, self_rag_report_path, output_dir): return _write( output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"],

### `local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1/sample_bridge_preflight/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
Categories: context_pack, crag, final_gate, graph_vector, planner, self_rag, table_visual_ocr, webui
- L62 `self_rag`: st": true, "must_separate_proven_facts_from_candidates": true, "self_rag_required": true, "source_truth_required_for_final_claims": true }, "forbidden_answer_claims": [
- L71 `crag`: fe to install", "uncited dimension or material claim", "uncited repair procedure", "unproven synonym", "unverified alternate part" ], "intent_family": "exact_part
- L157 `planner`: mission": false, "answers_user_question": false, "artifact_authority": "query_planning_only", "can_answer_directly": false, "can_prove_claims": false, "llm_call_allowed": false, "opensearch_
- L14 `context_pack`: "can_answer_directly": false, "can_prove_claims": false, "dynamic_context_pack_blueprint": { "compression_policy": { "deduplicate_by_page_id_and_source_trace": true, "inc
- L59 `final_gate`: anguage_required": false, "crag_retry_if_evidence_weak": true, "final_gate_required": true, "must_retrieve_exact_seed_first": true, "must_separate_proven_facts_from_candidates":

## Files by category

### context_pack
- `docs/README_trace_net_openwebui_page_context_bridge_v1.md`
- `docs/README_trace_net_page_context_pack_v3.md`
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_engineering_eval_short_run_dirs_fix_v1_README.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/fix_trace_net_engineering_eval_short_run_dirs_v1.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_anchor_injector_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_engineering_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_evidence_enricher_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_exact_row_proof_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_graph_leiden_expander_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_pack_v1_answer_support_expansion_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_quality_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_citation_answer_draft_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_crag_retry_plan_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_draft_packet_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_force_writer_dirs.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_json_writer_fix2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_writer_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_builder_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_self_rag_check_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_claims_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_cleaner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_context_validation_v1_1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_figure_item_fast_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_part_family_fast_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_raw_to_answer_context_engineered_native_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net_e2e_codebase_checklist_v1.md`
- `docs/trace_net_e2e_context_pack_builder_v1.md`
- `docs/trace_net_e2e_crag_retrieval_corrector_v10.md`
- `docs/trace_net_e2e_dynamic_context_pack_v8.md`
- `docs/trace_net_e2e_dynamic_plan_executor_v18.md`
- `docs/trace_net_e2e_evidence_sufficiency_gate_v1.md`
- `docs/trace_net_e2e_executed_plan_context_pack_v19.md`
- `docs/trace_net_e2e_live_llm_final_gate_v23.md`
- `docs/trace_net_e2e_live_llm_prompt_contract_v21.md`
- `docs/trace_net_e2e_live_query_pipeline_v15.md`
- `docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net_e2e_llm_assisted_query_planner_v17.md`
- `docs/trace_net_e2e_llm_prompt_contract_v11.md`
- `docs/trace_net_e2e_rag_demo_report_v1.md`
- `docs/trace_net_e2e_self_rag_context_critic_v9.md`
- `docs/trace_net_engineering_answer_composer_v1_README.md`
- `docs/trace_net_engineering_answer_context_pack_v1_README.md`
- `docs/trace_net_engineering_answer_runner_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_memory_layers_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_injector_reliability_v1_README.md`
- `docs/trace_net_engineering_engram_self_rag_critic_v1_README.md`
- `docs/trace_net_engineering_eval_short_run_dirs_fix_v1_README.md`
- `docs/trace_net_engineering_exact_part_lookup_support_v1_README.md`
- `docs/trace_net_engineering_intent_answer_composer_v1_README.md`
- `docs/trace_net_engineering_llm_answer_smoke_v1_README.md`
- `docs/trace_net_h27e_retry_overlay_citation_patch_v1_README.md`
- `local_data/organization/trace_net/answer_context_anchor_injector_gemma4_native_001/trace_net_answer_context_anchor_injector_v1.md`
- `local_data/organization/trace_net/answer_context_engineering_pack_gemma4_native_001/trace_net_answer_context_engineering_pack_v1.json`
- `local_data/organization/trace_net/answer_context_engineering_pack_gemma4_native_001/trace_net_answer_context_engineering_pack_v1.md`
- `local_data/organization/trace_net/answer_context_engineering_pack_gemma4_native_001/trace_net_answer_context_engineering_pack_v1_quality_check.json`
- `local_data/organization/trace_net/answer_context_engineering_pack_gemma4_native_001/trace_net_answer_context_engineering_pack_v1_summary.json`
- `local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1.json`
- `local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1.md`
- `local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1_quality_check.json`
- `local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1_summary.json`
- `local_data/organization/trace_net/answer_context_exact_row_proof_gemma4_native_001/trace_net_answer_context_exact_row_proof_v1.md`
- `local_data/organization/trace_net/answer_context_graph_leiden_expander_gemma4_native_001/trace_net_answer_context_graph_leiden_expander_v1.md`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.html`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.md`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_groups.jsonl`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_manifest.json`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_quality.json`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_records.jsonl`
- `local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_summary.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001/trace_net_answer_quality_gate_v1.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001_deterministic/trace_net_answer_quality_gate_v1.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001_deterministic_safe/trace_net_answer_quality_gate_v1.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_composer_120_29073_001/trace_net_answer_quality_gate_v1.json`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.html`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.json`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.md`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_edges.jsonl`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_records.jsonl`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_summary.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_artifact_cards.jsonl`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_page_artifact_cards.jsonl`
- `local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1.json`
- `local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1_manifest.json`
- `local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1_quality.json`
- `local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1_summary.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.md`
- `local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_items_v1.jsonl`
- `local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json`
- `local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1_inspect.md`
- `local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1_quality.json`
- `local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_packs_v1.jsonl`
- `local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_items_v1.jsonl`
- `local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json`
- `local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1_inspect.md`
- `local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1_quality.json`
- `local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_packs_v1.jsonl`
- `local_data/organization/trace_net/e2e_crag_retrieval_corrector/trace_net_e2e_crag_retrieval_corrector_plans_v10.jsonl`
- `local_data/organization/trace_net/e2e_crag_retrieval_corrector/trace_net_e2e_crag_retrieval_corrector_v10.json`
- `local_data/organization/trace_net/e2e_dynamic_context_pack/trace_net_e2e_dynamic_context_pack_evidence_v8.jsonl`
- `local_data/organization/trace_net/e2e_dynamic_context_pack/trace_net_e2e_dynamic_context_pack_records_v8.jsonl`
- `local_data/organization/trace_net/e2e_dynamic_context_pack/trace_net_e2e_dynamic_context_pack_v8.json`
- `local_data/organization/trace_net/e2e_dynamic_context_pack/trace_net_e2e_dynamic_context_pack_v8.md`
- `local_data/organization/trace_net/e2e_dynamic_plan_executor/trace_net_e2e_dynamic_plan_executor_records_v18.jsonl`
- `local_data/organization/trace_net/e2e_dynamic_plan_executor/trace_net_e2e_dynamic_plan_executor_v18.json`

### crag
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/check_trace_net_e2e_live_self_rag_crag_evaluator_v20_quality.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_algorithm_policy.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_all_page_table_scan.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_hybrid_v3_routing_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_cleanup_repair_executor.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_ablation_eval.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage4_policy_simulation.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage5_policy_control.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_corrective_retrieval_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_crosswalk_refinement_v1_type_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_e2e_tool_usage_audit_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_graph_attachment_plan_v1_table_cell_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_crag_retry_plan_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_self_rag_check_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_visual_context.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus_router.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_decision_recorder_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_promotion_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_queue_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_triage_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_hybrid_retrieval_v3.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_leiden_community_overlay.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_loader_contract_audit_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_rag_eligibility.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_repair_planner.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_cell_normalizer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_geometry_review_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_graph_gate.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_ocr_bbox_sidecar_generator_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_route_refinement.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_tiles.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_stage_dir_fix2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_visual_context.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net_e2e_crag_retrieval_corrector_v10.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34_1.md`
- `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.md`
- `docs/trace_net_e2e_live_llm_final_gate_v23.md`
- `docs/trace_net_e2e_live_llm_prompt_contract_v21.md`
- `docs/trace_net_e2e_live_query_pipeline_v15.md`
- `docs/trace_net_e2e_live_relationship_final_gated_endpoint_v31.md`
- `docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.md`
- `docs/trace_net_e2e_llm_prompt_contract_v11.md`
- `docs/trace_net_e2e_local_endpoint_formatter_hotfix_v3.md`
- `docs/trace_net_e2e_relationship_final_gate_hardener_v30.md`
- `docs/trace_net_e2e_self_rag_context_critic_v9.md`
- `docs/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_README.md`
- `docs/trace_net_engineering_engram_core_v1_README.md`
- `docs/trace_net_engineering_engram_crag_repair_v1_README.md`
- `docs/trace_net_engineering_engram_memory_layers_v1_README.md`
- `docs/trace_net_engineering_engram_postgres_feedback_ledger_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_reliability_h16d_README.md`
- `docs/trace_net_engineering_engram_prompt_retrieval_injector_v1_README.md`
- `docs/trace_net_engineering_engram_qdrant_adapter_v1_README.md`
- `docs/trace_net_engineering_engram_self_rag_critic_v1_README.md`
- `docs/trace_net_engineering_engram_unified_runtime_gate_v1_README.md`
- `docs/trace_net_engineering_engram_vector_retriever_v1_README.md`
- `docs/trace_net_fast_chat_runner_image_route_syntax_fix_v1_README.md`
- `docs/trace_net_h16c_v1c_repair_README.md`
- `docs/trace_net_h22_prompt_boundary_phrase_fix_v1_README.md`
- `docs/trace_net_h27_engram_answer_smoke_overlay_map_v1_README.md`
- `docs/trace_net_h27e_retry_overlay_citation_patch_v1_README.md`
- `docs/trace_net_h29_cli_alias_repair_v1_README.md`
- `docs/trace_net_h36b_validator_negation_regrade_patch_v1_README.md`
- `docs/trace_net_h38b_negation_artifact_repair_v1_README.md`
- `docs/trace_net_h38c_diversity_task_repair_runner_v1_README.md`
- `docs/trace_net_visual_callout_table_linker_v1_README.md`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_artifact_cards.jsonl`
- `local_data/organization/trace_net/backups/context_nomenclature_before_cleanup.sql`
- `local_data/organization/trace_net/baseline/pre_algorithm_filter_v1/trace_net_pre_algorithm_baseline_flat_metrics.json`
- `local_data/organization/trace_net/baseline/pre_algorithm_filter_v1/trace_net_pre_algorithm_baseline_metrics.json`
- `local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json`
- `local_data/organization/trace_net/category_aware_graph_ui_overlay/trace_net_category_aware_graph_ui_overlay_v1.json`
- `local_data/organization/trace_net/category_aware_graph_ui_overlay/trace_net_category_aware_graph_ui_overlay_v1_summary.json`
- `local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1_communities.jsonl`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_quality.json`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_review.html`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_review.md`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_summary.json`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repaired_records.jsonl`
- `local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_policy_control_records.jsonl`
- `local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_policy_control_report.html`
- `local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_policy_control_report.md`
- `local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_policy_control_summary.json`
- `local_data/organization/trace_net/confidence/trace_lc_confidence_policy.json`
- `local_data/organization/trace_net/confidence/trace_lc_confidence_policy_quality.json`
- `local_data/organization/trace_net/confidence/trace_lc_confidence_policy_report.html`
- `local_data/organization/trace_net/confidence/trace_lc_confidence_policy_report.md`
- `local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation.html`
- `local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation.json`
- `local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation.md`
- `local_data/organization/trace_net/confidence/trace_lc_stage4_policy_simulation_quality.json`
- `local_data/organization/trace_net/context_overlay/trace_net_context_overlay_normalized_preview.json`
- `local_data/organization/trace_net/context_overlay/trace_net_context_seed.json`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1.json`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1_records.jsonl`
- `local_data/organization/trace_net/dublin_core_crosswalk/trace_net_dublin_core_crosswalk_v1.json`
- `local_data/organization/trace_net/dublin_core_crosswalk/trace_net_dublin_core_crosswalk_v1_summary.json`
- `local_data/organization/trace_net/dublin_core_crosswalk/trace_net_dublin_core_pages_v1.jsonl`
- `local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_crosswalk_refinement_v1.json`
- `local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_refined_pages_v1.jsonl`
- `local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json`
- `local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_pages_v1.jsonl`
- `local_data/organization/trace_net/e2e_crag_retrieval_corrector/trace_net_e2e_crag_retrieval_corrector_v10.md`
- `local_data/organization/trace_net/e2e_image_visual_observer_route/trace_net_e2e_image_visual_observer_route_records_v34.jsonl`
- `local_data/organization/trace_net/e2e_image_visual_observer_route/trace_net_e2e_image_visual_observer_route_v34.json`
- `local_data/organization/trace_net/e2e_image_visual_observer_route/trace_net_e2e_image_visual_observer_route_v34.md`
- `local_data/organization/trace_net/e2e_image_visual_observer_route_v34_1/trace_net_e2e_image_visual_observer_route_records_v34_1.jsonl`

### engram
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_decision_recorder_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_queue_v1.md`
- `docs/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_README.md`
- `docs/trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1_README.md`
- `docs/trace_net_engineering_engram_core_v1_README.md`
- `docs/trace_net_engineering_engram_crag_repair_v1_README.md`
- `docs/trace_net_engineering_engram_memory_layers_v1_README.md`
- `docs/trace_net_engineering_engram_postgres_feedback_ledger_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_injector_reliability_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_injector_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_reliability_h16c_README.md`
- `docs/trace_net_engineering_engram_prompt_reliability_h16d_README.md`
- `docs/trace_net_engineering_engram_prompt_retrieval_injector_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_prompt_retrieval_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_qdrant_adapter_v1_README.md`
- `docs/trace_net_engineering_engram_self_rag_critic_v1_README.md`
- `docs/trace_net_engineering_engram_unified_runtime_gate_v1_README.md`
- `docs/trace_net_engineering_engram_vector_loader_v1_README.md`
- `docs/trace_net_engineering_engram_vector_retriever_v1_README.md`
- `docs/trace_net_h22_prompt_boundary_phrase_fix_v1_README.md`
- `docs/trace_net_h27d_engram_answer_smoke_overlay_map_v1_README.md`
- `docs/trace_net_h27e_retry_overlay_citation_patch_v1_README.md`
- `docs/trace_net_h33_full30_progress_runner_v1_README.md`
- `docs/trace_net_h34b_custom_question_progress_runner_v1_README.md`
- `docs/trace_net_h35_custom_task_contract_runner_v1_README.md`
- `docs/trace_net_h39a_whole_page_vision_summary_v1_README.md`
- `docs/trace_net_llama32_vision_image_route_summary_v2_README.md`
- `docs/trace_net_openwebui_gemma4_engram_bridge_v1_README.md`
- `docs/trace_net_openwebui_gemma4_engram_bridge_v2_README.md`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_artifact_cards.jsonl`
- `local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json`
- `local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1_quality.json`
- `local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1_summary.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q12/q12_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q12/q12_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q12/q12_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q16/q16_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q16/q16_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q16/q16_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q18/q18_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q18/q18_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q18/q18_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q25/q25_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q25/q25_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q25/q25_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q29/q29_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q29/q29_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/q/q29/q29_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_artifact/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_records.jsonl`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q12/q12_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q12/q12_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q12/q12_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q16/q16_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q16/q16_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q16/q16_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q18/q18_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q18/q18_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q18/q18_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q25/q25_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q25/q25_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q25/q25_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q29/q29_answer.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q29/q29_prompt.txt`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/q/q29/q29_trace.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_overlay_llm_smoke_v1_ollama/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_records.jsonl`
- `local_data/organization/trace_net/engineering_engram_answer_runner_prompt_overlay_smoke_v1/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_prompt_overlay_smoke_v1/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_overlay_map.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_prompt_overlay_smoke_v1/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_prompt_overlay_smoke_v1/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_records.jsonl`
- `local_data/organization/trace_net/engineering_engram_answer_runner_retrieval_bridge_v1/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_retrieval_bridge_v1/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_guidance_map.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_retrieval_bridge_v1/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_answer_runner_retrieval_bridge_v1/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_records.jsonl`
- `local_data/organization/trace_net/engineering_engram_answer_smoke_overlay_integration_gate_v1/trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.json`
- `local_data/organization/trace_net/engineering_engram_answer_smoke_overlay_integration_gate_v1/trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_answer_smoke_overlay_integration_gate_v1/trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1_records.jsonl`
- `local_data/organization/trace_net/engineering_engram_answer_smoke_overlay_integration_gate_v1/trace_net_engineering_engram_answer_smoke_overlay_map_v1.json`
- `local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json`
- `local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1_quality_check_cli.json`
- `local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_memory_atoms_v1.csv`
- `local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_memory_atoms_v1.json`
- `local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_traits_v1.json`
- `local_data/organization/trace_net/engineering_engram_crag_repair_v1/trace_net_engineering_engram_crag_repair_candidates_v1.jsonl`
- `local_data/organization/trace_net/engineering_engram_crag_repair_v1/trace_net_engineering_engram_crag_repair_records_v1.jsonl`
- `local_data/organization/trace_net/engineering_engram_crag_repair_v1/trace_net_engineering_engram_crag_repair_v1.json`
- `local_data/organization/trace_net/engineering_engram_crag_repair_v1/trace_net_engineering_engram_crag_repair_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1.json`
- `local_data/organization/trace_net/engineering_engram_memory_layers_v1/trace_net_engineering_engram_memory_layers_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_postgres_feedback_ledger_v1/trace_net_engineering_engram_feedback_ledger_records_v1.jsonl`
- `local_data/organization/trace_net/engineering_engram_postgres_feedback_ledger_v1/trace_net_engineering_engram_feedback_ledger_schema_v1.sql`
- `local_data/organization/trace_net/engineering_engram_postgres_feedback_ledger_v1/trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl`
- `local_data/organization/trace_net/engineering_engram_postgres_feedback_ledger_v1/trace_net_engineering_engram_postgres_feedback_ledger_v1.json`
- `local_data/organization/trace_net/engineering_engram_postgres_feedback_ledger_v1/trace_net_engineering_engram_postgres_feedback_ledger_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_injector_v1/trace_net_engineering_engram_prompt_retrieval_injector_v1.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_injector_v1/trace_net_engineering_engram_prompt_retrieval_injector_v1_external_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_injector_v1/trace_net_engineering_engram_prompt_retrieval_injector_v1_prompt_bundles.jsonl`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_injector_v1/trace_net_engineering_engram_prompt_retrieval_injector_v1_quality_check.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_installation_fit_effectivity_limit/answer.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_installation_fit_effectivity_limit/prompt.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_installation_fit_effectivity_limit/trace.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_interchangeability_boundary/answer.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_interchangeability_boundary/prompt.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_interchangeability_boundary/trace.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_safe_but_too_generic_repair/answer.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_safe_but_too_generic_repair/prompt.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_safe_but_too_generic_repair/trace.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_summary_only_limit/answer.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_summary_only_limit/prompt.txt`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_summary_only_limit/trace.json`
- `local_data/organization/trace_net/engineering_engram_prompt_retrieval_llm_smoke_v1_artifact/runs/h19_q_unknown_part_not_source_trace_ready/answer.txt`

### feedback
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_003.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_005.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_006.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_009.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_013.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_014.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_015.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_016.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_017.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_018.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_019.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_020.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_021.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_022.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_038.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_040.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_043.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_047.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_048.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_049.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_050.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_055.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_061.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_063.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_064.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_065.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_073.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_075.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_087.txt`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_claim_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_artifact_dirty_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_dynamic_retrieval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_final_return_policy_v21.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_feedback_mode_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_claim_evidence_entailment_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1_api_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1_import_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_context_overlay.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_corrective_retrieval_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_crosswalk_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dynamic_final_gate_execution_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_category_taxonomy_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_question_orchestrator_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus_router.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_claims_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_cleaner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_sufficiency_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_aware_ask_simulation_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_context_validation_v1_1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_graph_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_memory_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_search_simulation_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_figure_chart_understanding_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_retry_engine_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_four_route_operational_resolver_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_gold_label_decision_merge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_baseline_checkpoint_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_baseline_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_explorer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_explorer_v1_3_context_overlay.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_ui_community_overlay_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_decision_recorder_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_promotion_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_queue_table_geometry_integration_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_queue_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_triage_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_workbench_preview_wiring_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_workbench_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_hybrid_retrieval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_hybrid_retrieval_v3.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_incident_review_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_incremental_corpus_manifest_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_issue_origin_test_matrix_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_operations_console_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_operations_console_v1_self_exclude_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_leiden_graph_communities_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ocr_classifier_pipeline_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_opensearch_adapter_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_opensearch_live_loader_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_opensearch_loader_smoke_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_postgres_loader_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_postgres_trust_overlay_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_promotion_writeback_dry_run_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_rag_eligibility.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_repair_planner.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1_dynamic_gate_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1_retrieval_consistency_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_route_confidence_resolver_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_route_unresolved_retry_probe_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_route_validator_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1_postgres_storage.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1_random_incident_button.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_detector_overlay_review_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_image_resolver_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_trust_authority_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_weighted_search_calibration_report_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_weighted_search_calibration_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_weighted_search_simulation_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_weights_policy_v1.md`
- `docs/trace_net_e2e_calibrated_cascade_route_brain_v35_3.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34_1.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34_3.md`
- `docs/trace_net_e2e_self_rag_context_critic_v9.md`
- `docs/trace_net_engineering_engram_postgres_feedback_ledger_v1_README.md`
- `docs/trace_net_engineering_engram_qdrant_adapter_v1_README.md`
- `docs/trace_net_engineering_engram_unified_runtime_gate_v1_README.md`
- `docs/trace_net_engineering_real_answer_smoke_test_v1_README.md`
- `docs/trace_net_h34b_custom_question_progress_runner_v1_README.md`
- `docs/trace_net_table_route_retrieval_demo_query_pack_v1.md`
- `docs/trace_net_v2_summary_guidance_index_strict_filter_v1_README.md`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1.json`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1_quality.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.md`

### final_gate
- `docs/README_trace_net_openwebui_page_context_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_claim_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_dynamic_retrieval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_final_return_policy_v21.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_hybrid_v3_routing_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_final_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_callout_visual_part_verifier_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_citation_answer_draft_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_claim_evidence_entailment_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dynamic_final_gate_execution_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_e2e_tool_usage_audit_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_draft_final_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_adapter_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_retry_prompt_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_question_orchestrator_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_claims_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_cleaner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_sufficiency_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_multi_route_quality_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_memory_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_final_answer_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_query_evidence_enrichment_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_graph_ui_community_overlay_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_hybrid_retrieval_sim_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_hybrid_retrieval_v3.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_issue_origin_test_matrix_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_opensearch_adapter_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_page_retrieval_large_eval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_real_embeddings_bge_m3_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1_dynamic_gate_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1_retrieval_consistency_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_runtime_hybrid_v3_v22.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1_random_incident_button.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_table_cell_normalizer_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net_e2e_codebase_checklist_v1.md`
- `docs/trace_net_e2e_evidence_sufficiency_gate_v1.md`
- `docs/trace_net_e2e_final_answer_gate_v13.md`
- `docs/trace_net_e2e_final_gate_smoke_v1.md`
- `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.md`
- `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.md`
- `docs/trace_net_e2e_live_llm_final_gate_v23.md`
- `docs/trace_net_e2e_live_llm_prompt_contract_v21.md`
- `docs/trace_net_e2e_live_query_pipeline_v15.md`
- `docs/trace_net_e2e_live_relationship_final_gated_endpoint_v31.md`
- `docs/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.md`
- `docs/trace_net_e2e_rag_demo_report_v1.md`
- `docs/trace_net_e2e_reasoned_response_draft_v12.md`
- `docs/trace_net_e2e_relationship_final_gate_hardener_v30.md`
- `docs/trace_net_e2e_webui_final_answer_endpoint_v14.md`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1.json`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1.md`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1_quality.json`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1_records.jsonl`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.html`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.md`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_claims.jsonl`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_manifest.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_quality.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_records.jsonl`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_summary.json`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.html`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.json`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.md`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_records.jsonl`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_summary.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_artifact_cards.jsonl`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_page_artifact_cards.jsonl`
- `local_data/organization/trace_net/artifact_dirty_planner/trace_net_artifact_dirty_planner_v1.json`
- `local_data/organization/trace_net/artifact_dirty_planner/trace_net_artifact_dirty_planner_v1.md`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21.html`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21.json`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21.md`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21_quality.json`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21_records.jsonl`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21_summary.json`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1.json`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1_answer.html`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1_answer.md`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1_claims.jsonl`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1_manifest.json`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1_quality.json`
- `local_data/organization/trace_net/ask_final_gate/trace_net_ask_final_gate_v1_summary.json`
- `local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.html`
- `local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.md`
- `local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1.json`
- `local_data/organization/trace_net/citation_answer_draft/trace_net_citation_answer_draft_v1_claims.jsonl`
- `local_data/organization/trace_net/claim_evidence_entailment/trace_net_claim_evidence_entailment_v1.json`
- `local_data/organization/trace_net/claim_evidence_entailment/trace_net_claim_evidence_entailment_v1_quality.json`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1.json`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1_quality.json`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1_records.jsonl`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1_summary.md`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.html`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.md`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_blocked_claims.jsonl`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_claims.jsonl`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_manifest.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_quality.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_results.jsonl`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_summary.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1.html`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1.md`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_blocked_claims.jsonl`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_claims.jsonl`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_manifest.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_quality.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_results.jsonl`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_summary.json`
- `local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_requests_v1.jsonl`
- `local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_responses_v1.jsonl`
- `local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.json`

### graph_vector
- `docs/README_trace_net_openwebui_page_context_bridge_v1.md`
- `docs/README_trace_net_page_context_pack_v3.md`
- `docs/tiff_document_type_pipeline.md`
- `docs/tiff_inventory_hash_crawler.md`
- `docs/tiff_pipeline_start.md`
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/README_trace_net_incremental_orchestrator_v1.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_engineering_eval_short_run_dirs_fix_v1_README.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/fix_trace_net_engineering_eval_short_run_dirs_v1.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_incremental_orchestrator_v1.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_incremental_orchestrator_v1.py`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_021.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_029.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_031.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_033.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_051.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_065.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_071.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_073.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_075.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_077.txt`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ai_trace_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_algorithm_policy.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_all_page_table_scan.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_anchor_aware_graph_leiden_expander_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_claim_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_anchor_injector_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_engineering_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_evidence_enricher_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_exact_row_proof_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_graph_leiden_expander_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_pack_v1_answer_support_expansion_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_quality_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_artifact_dependency_registry_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_artifact_dependency_registry_v1_cycle_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_artifact_dependency_registry_v1_helper_legacy_normalization.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_artifact_detector_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_artifact_dirty_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_dynamic_retrieval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_final_return_policy_hybrid_v3_v22.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_final_return_policy_v21.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_hybrid_v3_routing_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_cli.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_final_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_hybrid_flag_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_hybrid_flag_v1_inmemory_hydration_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_callout_visual_part_verifier_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_category_aware_graph_ui_overlay_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_category_aware_leiden_overlay_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_citation_answer_draft_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_claim_evidence_entailment_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_ablation_eval.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1_api_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_sim_v1_import_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_community_aware_retrieval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage4_policy_simulation.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage5_control.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_context_retrieval_helper_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_corrective_retrieval_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dry_run_loader_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_crosswalk_refinement_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_crosswalk_refinement_v1_type_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_crosswalk_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_source_package_extension_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dynamic_final_gate_execution_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_e2e_tool_usage_audit_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_category_taxonomy_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_category_taxonomy_v1_label_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_category_taxonomy_v1_leiden_hint_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_graph_attachment_plan_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_element_graph_attachment_plan_v1_table_cell_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_embedding_candidates_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_force_writer_dirs.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_json_writer_fix2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_writer_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_draft_final_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_adapter_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_retry_prompt_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_question_orchestrator_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_visual_context.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus_router.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_claims_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_cleaner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_sufficiency_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_multi_route_quality_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_aware_ask_simulation_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_context_validation_v1_1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_graph_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_memory_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_search_simulation_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_figure_chart_understanding_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_figure_item_fast_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_final_answer_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_accepted_route_manifest_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_ocr_grid_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_retry_engine_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_retry_refinement_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_route_manifest_overlay_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_route_review_packet_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_route_signal_workbench_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fishnet_router_hardening_policy_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_four_route_operational_resolver_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_four_route_storage_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_gold_label_auto_review_seed_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_gold_label_decision_merge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_gold_label_review_reduction_v1.md`

### planner
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_query_planner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net_e2e_llm_assisted_query_planner_v17.md`
- `docs/trace_net_e2e_query_planning_routing_v1.md`
- `docs/trace_net_engineering_answer_context_pack_v1_README.md`
- `docs/trace_net_engineering_answer_runner_v1_README.md`
- `docs/trace_net_engineering_query_planner_v1_README.md`
- `docs/trace_net_v2_summary_guidance_index_strict_filter_v1_README.md`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.md`
- `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json`
- `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1_quality.json`
- `local_data/organization/trace_net/e2e_live_deterministic_answer_planner/trace_net_e2e_live_deterministic_answer_planner_samples_v28.jsonl`
- `local_data/organization/trace_net/e2e_live_deterministic_answer_planner/trace_net_e2e_live_deterministic_answer_planner_v28.json`
- `local_data/organization/trace_net/e2e_live_eval_latency_harness_v27_endpoint/trace_net_e2e_live_eval_latency_harness_records_v26.jsonl`
- `local_data/organization/trace_net/e2e_live_eval_latency_harness_v27_endpoint/trace_net_e2e_live_eval_latency_harness_v26.json`
- `local_data/organization/trace_net/e2e_live_eval_latency_harness_v28_endpoint/trace_net_e2e_live_eval_latency_harness_records_v26.jsonl`
- `local_data/organization/trace_net/e2e_live_eval_latency_harness_v28_endpoint/trace_net_e2e_live_eval_latency_harness_v26.json`
- `local_data/organization/trace_net/e2e_live_orchestrator_stage_timing_fastpath/trace_net_e2e_live_orchestrator_stage_timing_fastpath_samples_v27.jsonl`
- `local_data/organization/trace_net/e2e_live_orchestrator_stage_timing_fastpath/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.json`
- `local_data/organization/trace_net/e2e_live_relationship_synthesis_planner/trace_net_e2e_live_relationship_synthesis_planner_samples_v29.jsonl`
- `local_data/organization/trace_net/e2e_live_relationship_synthesis_planner/trace_net_e2e_live_relationship_synthesis_planner_v29.json`
- `local_data/organization/trace_net/e2e_llm_assisted_query_planner/trace_net_e2e_llm_assisted_query_planner_records_v17.jsonl`
- `local_data/organization/trace_net/e2e_llm_assisted_query_planner/trace_net_e2e_llm_assisted_query_planner_v17.json`
- `local_data/organization/trace_net/e2e_llm_assisted_query_planner/trace_net_e2e_llm_assisted_query_planner_v17.md`
- `local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json`
- `local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1_inspect.md`
- `local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1_quality.json`
- `local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_route_plans_v1.jsonl`
- `local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json`
- `local_data/organization/trace_net/e2e_relationship_router_hardening/trace_net_e2e_relationship_router_hardening_samples_v29_1.jsonl`
- `local_data/organization/trace_net/e2e_relationship_router_hardening/trace_net_e2e_relationship_router_hardening_v29_1.json`
- `local_data/organization/trace_net/engineering_query_planner/trace_net_engineering_query_planner_v1.json`
- `local_data/organization/trace_net/engineering_query_planner/trace_net_engineering_query_planner_v1.md`
- `local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1/sample_bridge_preflight/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
- `local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1/sample_bridge_preflight/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
- `local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1_visual/sample_bridge_preflight/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
- `local_data/organization/trace_net/engineering_webui_answer_server_v1_3_bridge_v1_visual/sample_bridge_preflight/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.json`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge/trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1.json`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_fresh_test/trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1.json`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/stage_reports/query_planner/trace_net_engineering_query_planner_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1.json`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1.md`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1_checklist.txt`
- `local_data/organization/trace_net/webui_self_rag_crag_bridge_visual/trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl`
- `scripts/build_trace_net_e2e_llm_assisted_query_planner_v17.py`
- `scripts/build_trace_net_e2e_query_planning_routing_v1.py`
- `scripts/build_trace_net_e2e_rag_demo_report_v1.py`
- `scripts/check_trace_net_e2e_llm_assisted_query_planner_v17_quality.py`
- `scripts/check_trace_net_e2e_query_planning_routing_v1_quality.py`
- `tests/unit/test_trace_net_e2e_query_planning_routing_v1.py`
- `tests/unit/test_trace_net_e2e_query_planning_routing_v1_script_imports.py`
- `tests/unit/test_trace_net_e2e_rag_demo_report_v1.py`
- `tiff/trace_net_e2e_codebase_checklist_v1.py`
- `tiff/trace_net_e2e_live_deterministic_answer_planner_v28.py`
- `tiff/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py`
- `tiff/trace_net_e2e_llm_assisted_query_planner_v17.py`
- `tiff/trace_net_e2e_query_planning_routing_v1.py`
- `tiff/trace_net_e2e_rag_demo_report_v1.py`
- `tiff/trace_net_e2e_relationship_router_hardening_v29_1.py`
- `tiff/trace_net_engineering_context_pack_blueprint_v1.py`
- `tiff/trace_net_engineering_query_planner_v1.py`
- `tiff/trace_net_webui_self_rag_crag_bridge_v1.py`

### self_rag
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/build_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/check_trace_net_e2e_live_self_rag_crag_evaluator_v20_quality.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20_script_imports.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_021.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_024.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_037.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_040.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_055.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_057.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_059.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_065.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_066.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_074.txt`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ai_trace_pack_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_claim_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_final_return_policy_v21.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_claim_evidence_entailment_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_e2e_tool_usage_audit_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_crag_retry_plan_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_draft_packet_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_self_rag_check_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_gemma_draft_adapter_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_visual_context.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_sufficiency_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_triage_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_workbench_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_issue_origin_test_matrix_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_operations_console_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_operations_console_v1_self_exclude_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_operations_console_v1_synthetic_exclude_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1_dynamic_gate_tightening.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_retrieval_critic_v1_retrieval_consistency_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_stage_dir_fix2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_visual_context.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_visual_context_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/scripts/check_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_script_imports.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net_e2e_codebase_checklist_v1.md`
- `docs/trace_net_e2e_crag_retrieval_corrector_v10.md`
- `docs/trace_net_e2e_dynamic_context_pack_v8.md`
- `docs/trace_net_e2e_evidence_sufficiency_gate_v1.md`
- `docs/trace_net_e2e_final_gate_smoke_v1.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34_1.md`
- `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.md`
- `docs/trace_net_e2e_live_llm_prompt_contract_v21.md`
- `docs/trace_net_e2e_live_query_pipeline_v15.md`
- `docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- `docs/trace_net_e2e_llm_prompt_contract_v11.md`
- `docs/trace_net_e2e_rag_demo_report_v1.md`
- `docs/trace_net_e2e_self_rag_context_critic_v9.md`
- `docs/trace_net_engineering_engram_core_v1_README.md`
- `docs/trace_net_engineering_engram_crag_repair_v1_README.md`
- `docs/trace_net_engineering_engram_memory_layers_v1_README.md`
- `docs/trace_net_engineering_engram_postgres_feedback_ledger_v1_README.md`
- `docs/trace_net_engineering_engram_qdrant_adapter_v1_README.md`
- `docs/trace_net_engineering_engram_self_rag_critic_v1_README.md`
- `docs/trace_net_engineering_engram_unified_runtime_gate_v1_README.md`
- `docs/trace_net_engineering_engram_vector_retriever_v1_README.md`
- `docs/trace_net_h29_cli_alias_repair_v1_README.md`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1.json`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1_quality.json`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1_records.jsonl`
- `local_data/organization/trace_net/ai_trace_pack/trace_net_ai_trace_pack_v1_review_records.jsonl`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.html`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.md`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_claims.jsonl`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_manifest.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_quality.json`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_records.jsonl`
- `local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1_summary.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001/trace_net_answer_quality_gate_v1.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001/trace_net_answer_quality_gate_v1.md`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001/trace_net_answer_quality_gate_v1_quality_check.json`
- `local_data/organization/trace_net/answer_quality_gate_fast_120_29073_001/trace_net_answer_quality_gate_v1_violations.csv`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.html`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.json`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1.md`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_records.jsonl`
- `local_data/organization/trace_net/artifact_dependency_registry/trace_net_artifact_dependency_registry_v1_summary.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_artifact_cards.jsonl`
- `local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1_page_artifact_cards.jsonl`
- `local_data/organization/trace_net/artifact_dirty_planner/trace_net_artifact_dirty_planner_v1.json`
- `local_data/organization/trace_net/artifact_dirty_planner/trace_net_artifact_dirty_planner_v1.md`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21.json`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21_records.jsonl`
- `local_data/organization/trace_net/ask_api_final_return_policy_v21/trace_net_ask_api_final_return_policy_v21_summary.json`
- `local_data/organization/trace_net/claim_evidence_entailment/trace_net_claim_evidence_entailment_v1.json`
- `local_data/organization/trace_net/claim_evidence_entailment/trace_net_claim_evidence_entailment_v1.md`
- `local_data/organization/trace_net/claim_evidence_entailment/trace_net_claim_evidence_entailment_v1_quality.json`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_review.html`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repair_review.md`
- `local_data/organization/trace_net/cleanup_repair/trace_net_cleanup_repaired_records.jsonl`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1.json`
- `local_data/organization/trace_net/corrective_retrieval_planner/trace_net_corrective_retrieval_planner_v1_records.jsonl`
- `local_data/organization/trace_net/dublin_core_crosswalk/trace_net_dublin_core_crosswalk_v1_quality.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1_quality.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1.json`
- `local_data/organization/trace_net/dynamic_final_gate_execution_part_120_46137_001/trace_net_dynamic_final_gate_execution_v1_quality.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.md`
- `local_data/organization/trace_net/e2e_crag_retrieval_corrector/trace_net_e2e_crag_retrieval_corrector_plans_v10.jsonl`
- `local_data/organization/trace_net/e2e_crag_retrieval_corrector/trace_net_e2e_crag_retrieval_corrector_v10.json`
- `local_data/organization/trace_net/e2e_crag_retrieval_corrector/trace_net_e2e_crag_retrieval_corrector_v10.md`
- `local_data/organization/trace_net/e2e_dynamic_context_pack/trace_net_e2e_dynamic_context_pack_records_v8.jsonl`

### table_visual_ocr
- `docs/README_trace_net_openwebui_page_context_bridge_v1.md`
- `docs/README_trace_net_page_context_pack_v3.md`
- `docs/manual_grouping_and_rescarta_staging.md`
- `docs/tiff_batch_scan.md`
- `docs/tiff_changed_scan_bridge.md`
- `docs/tiff_document_type_pipeline.md`
- `docs/tiff_incremental_scan_bridge.md`
- `docs/tiff_inventory_hash_crawler.md`
- `docs/tiff_pipeline_start.md`
- `docs/tiff_sqlite_persistence.md`
- `docs/tiff_title_block_ocr.md`
- `docs/tiff_upload_scan.md`
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/README_trace_net_incremental_orchestrator_v1.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_engineering_eval_short_run_dirs_fix_v1_README.md`
- `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/fix_trace_net_engineering_eval_short_run_dirs_v1.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20_script_imports.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_incremental_orchestrator_v1.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_incremental_orchestrator_v1.py`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_001.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_001.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_002.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_002.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_003.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_004.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_004.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_005.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_005.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_006.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_006.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_007.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_007.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_008.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_009.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_009.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_010.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_010.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_011.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_011.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_012.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_012.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_013.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_014.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_015.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_016.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_017.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_018.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_019.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_020.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_021.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_022.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_023.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_024.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_025.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_026.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_027.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_028.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_029.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_030.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_031.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_032.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_033.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_034.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_035.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_036.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_037.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_038.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_039.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_040.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_041.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_042.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_043.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_044.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_045.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_046.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_047.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_048.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_049.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_050.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_051.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_052.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_053.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_054.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_055.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_056.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_057.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_058.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_059.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_060.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_061.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_062.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_063.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_064.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_065.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_066.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_067.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_068.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_069.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_070.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_071.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_072.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_073.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_074.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_075.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_076.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_077.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_078.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_079.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_080.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_080.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_081.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_081.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_082.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_083.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_083.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_084.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_085.png`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_085.txt`
- `docs/trace_net/archive/debug_outputs/ocr_debug/page_086.txt`

### webui
- `docs/README_trace_net_openwebui_page_context_bridge_v1.md`
- `docs/README_trace_net_page_context_pack_v3.md`
- `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_dynamic_retrieval_v2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_final_return_policy_hybrid_v3_v22.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_hybrid_v3_routing_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_e2e_tool_usage_audit_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_force_writer_dirs.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_json_writer_fix2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_writer_fix.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_visual_context.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_answer_composer_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_multi_route_quality_gate_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_fast_chat_runner_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_image_visual_summary_v1_semantic_validator.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_raw_to_answer_e2e_smoke_native_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_runtime_hybrid_v3_v22.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_stage_dir_fix2.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_visual_context.md`
- `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_visual_context_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/scripts/check_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_script_imports.py`
- `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- `docs/trace_net_e2e_codebase_checklist_v1.md`
- `docs/trace_net_e2e_dynamic_endpoint_broad_covered_part_v7.md`
- `docs/trace_net_e2e_dynamic_query_endpoint_v1.md`
- `docs/trace_net_e2e_final_answer_gate_v13.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34_1.md`
- `docs/trace_net_e2e_image_visual_observer_route_v34_2.md`
- `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.md`
- `docs/trace_net_e2e_live_llm_draft_adapter_v22.md`
- `docs/trace_net_e2e_live_llm_final_gate_v23.md`
- `docs/trace_net_e2e_live_orchestrator_endpoint_v25.md`
- `docs/trace_net_e2e_live_query_pipeline_v15.md`
- `docs/trace_net_e2e_live_relationship_final_gated_endpoint_v31.md`
- `docs/trace_net_e2e_live_relationship_synthesis_planner_v29.md`
- `docs/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.md`
- `docs/trace_net_e2e_local_endpoint_citation_value_hotfix_v2.md`
- `docs/trace_net_e2e_local_endpoint_formatter_hotfix_v3.md`
- `docs/trace_net_e2e_local_endpoint_v1.md`
- `docs/trace_net_e2e_reasoned_response_draft_v12.md`
- `docs/trace_net_e2e_relationship_final_gate_hardener_v30.md`
- `docs/trace_net_e2e_webui_final_answer_endpoint_v14.md`
- `docs/trace_net_engineering_answer_runner_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_README.md`
- `docs/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_README.md`
- `docs/trace_net_engineering_exact_part_lookup_support_v1_README.md`
- `docs/trace_net_engineering_intent_answer_composer_v1_README.md`
- `docs/trace_net_engineering_real_answer_smoke_test_v1_README.md`
- `docs/trace_net_image_route_endpoint_consolidated_v1_README.md`
- `docs/trace_net_image_route_endpoint_direct_fallback_v1_README.md`
- `docs/trace_net_image_route_endpoint_direct_smoke_hardening_v1_README.md`
- `docs/trace_net_image_route_endpoint_runner_report_fix_v1_README.md`
- `docs/trace_net_image_route_multi_route_quality_gate_v1_README.md`
- `docs/trace_net_image_route_openwebui_endpoint_v1_README.md`
- `docs/trace_net_openwebui_e2e_launcher_v1_README.md`
- `docs/trace_net_openwebui_gemma4_engram_bridge_v1_README.md`
- `docs/trace_net_openwebui_gemma4_engram_bridge_v2_README.md`
- `docs/trace_net_visual_part_nomenclature_enricher_v1_README.md`
- `local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_requests_v1.jsonl`
- `local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json`
- `local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1_inspect.md`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.json`
- `local_data/organization/trace_net/e2e_codebase_checklist/trace_net_e2e_codebase_checklist_v1.md`
- `local_data/organization/trace_net/e2e_dynamic_query_endpoint/trace_net_e2e_dynamic_query_endpoint_v1.json`
- `local_data/organization/trace_net/e2e_dynamic_query_endpoint/trace_net_e2e_dynamic_query_endpoint_v1.md`
- `local_data/organization/trace_net/e2e_dynamic_query_tunnels/trace_net_e2e_dynamic_query_tunnels_v3.json`
- `local_data/organization/trace_net/e2e_final_answer_gate/trace_net_e2e_final_answer_gate_records_v13.jsonl`
- `local_data/organization/trace_net/e2e_final_answer_gate/trace_net_e2e_final_answer_gate_v13.json`
- `local_data/organization/trace_net/e2e_final_answer_gate/trace_net_e2e_final_answer_gate_v13.md`
- `local_data/organization/trace_net/e2e_image_visual_observer_route/trace_net_e2e_image_visual_observer_route_v34.json`
- `local_data/organization/trace_net/e2e_image_visual_observer_route_v34_1/trace_net_e2e_image_visual_observer_route_v34_1.json`
- `local_data/organization/trace_net/e2e_image_visual_observer_route_v34_2/trace_net_e2e_image_visual_observer_route_v34_2.json`
- `local_data/organization/trace_net/e2e_image_visual_observer_route_v34_3/trace_net_e2e_image_visual_observer_route_v34_3.json`
- `local_data/organization/trace_net/e2e_live_deterministic_answer_planner/trace_net_e2e_live_deterministic_answer_planner_samples_v28.jsonl`
- `local_data/organization/trace_net/e2e_live_deterministic_answer_planner/trace_net_e2e_live_deterministic_answer_planner_v28.json`
- `local_data/organization/trace_net/e2e_live_deterministic_answer_planner/trace_net_e2e_live_deterministic_answer_planner_v28.md`
- `local_data/organization/trace_net/e2e_live_dynamic_fallback/trace_net_e2e_live_dynamic_fallback_records_v16.jsonl`
- `local_data/organization/trace_net/e2e_live_dynamic_fallback/trace_net_e2e_live_dynamic_fallback_v16.json`
- `local_data/organization/trace_net/e2e_live_dynamic_fallback/trace_net_e2e_live_dynamic_fallback_v16.md`
- `local_data/organization/trace_net/e2e_live_gemma_answer_writer_endpoint/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.json`
- `local_data/organization/trace_net/e2e_live_gemma_answer_writer_endpoint/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.md`
- `local_data/organization/trace_net/e2e_live_gemma_answer_writer_endpoint_v33/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.json`
- `local_data/organization/trace_net/e2e_live_gemma_answer_writer_endpoint_v33/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.md`
- `local_data/organization/trace_net/e2e_live_llm_draft_adapter/trace_net_e2e_live_llm_draft_adapter_v22.md`
- `local_data/organization/trace_net/e2e_live_llm_draft_adapter_smoke/trace_net_e2e_live_llm_draft_adapter_v22.md`
- `local_data/organization/trace_net/e2e_live_llm_final_gate/trace_net_e2e_live_llm_final_answers_v23.jsonl`
- `local_data/organization/trace_net/e2e_live_llm_final_gate/trace_net_e2e_live_llm_final_gate_records_v23.jsonl`
- `local_data/organization/trace_net/e2e_live_llm_final_gate/trace_net_e2e_live_llm_final_gate_v23.json`
- `local_data/organization/trace_net/e2e_live_llm_final_gate/trace_net_e2e_live_llm_final_gate_v23.md`
- `local_data/organization/trace_net/e2e_live_orchestrator_endpoint/trace_net_e2e_live_orchestrator_endpoint_samples_v25.jsonl`
- `local_data/organization/trace_net/e2e_live_orchestrator_endpoint/trace_net_e2e_live_orchestrator_endpoint_v25.json`
- `local_data/organization/trace_net/e2e_live_orchestrator_endpoint/trace_net_e2e_live_orchestrator_endpoint_v25.md`
- `local_data/organization/trace_net/e2e_live_orchestrator_stage_timing_fastpath/trace_net_e2e_live_orchestrator_stage_timing_fastpath_samples_v27.jsonl`
- `local_data/organization/trace_net/e2e_live_orchestrator_stage_timing_fastpath/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.json`
- `local_data/organization/trace_net/e2e_live_orchestrator_stage_timing_fastpath/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.md`
- `local_data/organization/trace_net/e2e_live_query_pipeline/trace_net_e2e_live_query_pipeline_records_v15.jsonl`
- `local_data/organization/trace_net/e2e_live_query_pipeline/trace_net_e2e_live_query_pipeline_v15.json`
- `local_data/organization/trace_net/e2e_live_query_pipeline/trace_net_e2e_live_query_pipeline_v15.md`
- `local_data/organization/trace_net/e2e_live_relationship_final_gated_endpoint/trace_net_e2e_live_relationship_final_gated_endpoint_v31.json`
- `local_data/organization/trace_net/e2e_live_relationship_final_gated_endpoint/trace_net_e2e_live_relationship_final_gated_endpoint_v31.md`
- `local_data/organization/trace_net/e2e_live_relationship_synthesis_planner/trace_net_e2e_live_relationship_synthesis_planner_samples_v29.jsonl`
- `local_data/organization/trace_net/e2e_live_relationship_synthesis_planner/trace_net_e2e_live_relationship_synthesis_planner_v29.json`
- `local_data/organization/trace_net/e2e_live_relationship_synthesis_planner/trace_net_e2e_live_relationship_synthesis_planner_v29.md`
- `local_data/organization/trace_net/e2e_live_webui_final_gated_gemma_endpoint/trace_net_e2e_live_webui_final_gated_gemma_endpoint_responses_v24.jsonl`
- `local_data/organization/trace_net/e2e_live_webui_final_gated_gemma_endpoint/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.json`
- `local_data/organization/trace_net/e2e_live_webui_final_gated_gemma_endpoint/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.md`
- `local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json`