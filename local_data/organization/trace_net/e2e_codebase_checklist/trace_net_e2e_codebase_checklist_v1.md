```text
TRACE-Net E2E Codebase Checklist v1
Overall status: PASS
Blocking items: 0

Hybrid search assessment:
- Current WebUI endpoint uses artifact-backed planned hybrid retrieval outputs. The planned runtime includes query planning/routing tunnels, table bridge signals, exact/table evidence, and context/final-gate artifacts, but it is not yet a fully dynamic per-query live retrieval runner.

[e2e_chain]
  [PASS] E2E query input — quality_status=PASS (local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json)
  [PASS] E2E query input status — READY_FOR_RETRIEVAL_RUNTIME (local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json)
  [PASS] E2E query input e2e_query_input_record_count — observed=5 expected>=5 (local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json)
  [PASS] E2E query input safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json)
  [PASS] E2E query planning/routing tunnels — quality_status=PASS (local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json)
  [PASS] E2E query planning/routing tunnels status — READY_FOR_HYBRID_RETRIEVAL_RUNTIME (local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json)
  [PASS] E2E query planning/routing tunnels query_route_plan_count — observed=5 expected>=5 (local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json)
  [PASS] E2E query planning/routing tunnels total_query_tunnel_count — observed=30 expected>=15 (local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json)
  [PASS] E2E query planning/routing tunnels safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_query_planning_routing/trace_net_e2e_query_planning_routing_v1.json)
  [PASS] Planned hybrid retrieval runtime — quality_status=PASS (local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json)
  [PASS] Planned hybrid retrieval runtime status — READY_FOR_CONTEXT_PACK (local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json)
  [PASS] Planned hybrid retrieval runtime successful_retrieval_query_count — observed=5 expected>=4 (local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json)
  [PASS] Planned hybrid retrieval runtime total_retrieval_hit_count — observed=50 expected>=10 (local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json)
  [PASS] Planned hybrid retrieval runtime safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_hybrid_retrieval_runtime_planned/trace_net_e2e_hybrid_retrieval_runtime_v1.json)
  [PASS] Planned context pack builder — quality_status=PASS (local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json)
  [PASS] Planned context pack builder status — READY_FOR_FINAL_GATE (local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json)
  [PASS] Planned context pack builder context_pack_count — observed=5 expected>=5 (local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json)
  [PASS] Planned context pack builder citation_ready_context_item_count — observed=25 expected>=20 (local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json)
  [PASS] Planned context pack builder safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_context_pack_builder_planned/trace_net_e2e_context_pack_builder_v1.json)
  [PASS] Planned evidence sufficiency gate — quality_status=PASS (local_data/organization/trace_net/e2e_evidence_sufficiency_gate_planned/trace_net_e2e_evidence_sufficiency_gate_v1.json)
  [PASS] Planned evidence sufficiency gate status — READY_FOR_FINAL_GATE_SMOKE (local_data/organization/trace_net/e2e_evidence_sufficiency_gate_planned/trace_net_e2e_evidence_sufficiency_gate_v1.json)
  [PASS] Planned evidence sufficiency gate final_gate_review_ready_pack_count — observed=5 expected>=4 (local_data/organization/trace_net/e2e_evidence_sufficiency_gate_planned/trace_net_e2e_evidence_sufficiency_gate_v1.json)
  [PASS] Planned evidence sufficiency gate safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_evidence_sufficiency_gate_planned/trace_net_e2e_evidence_sufficiency_gate_v1.json)
  [PASS] Planned final gate smoke — quality_status=PASS (local_data/organization/trace_net/e2e_final_gate_smoke_planned/trace_net_e2e_final_gate_smoke_v1.json)
  [PASS] Planned final gate smoke status — READY_FOR_API_OR_AUDIT_RESPONSE (local_data/organization/trace_net/e2e_final_gate_smoke_planned/trace_net_e2e_final_gate_smoke_v1.json)
  [PASS] Planned final gate smoke safe_response_draft_count — observed=5 expected>=4 (local_data/organization/trace_net/e2e_final_gate_smoke_planned/trace_net_e2e_final_gate_smoke_v1.json)
  [PASS] Planned final gate smoke total_citation_count — observed=15 expected>=10 (local_data/organization/trace_net/e2e_final_gate_smoke_planned/trace_net_e2e_final_gate_smoke_v1.json)
  [PASS] Planned final gate smoke safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_final_gate_smoke_planned/trace_net_e2e_final_gate_smoke_v1.json)
  [PASS] E2E RAG demo report — quality_status=PASS (local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json)
  [PASS] E2E RAG demo report status — READY_FOR_API_WRAPPER (local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json)
  [PASS] E2E RAG demo report complete_demo_flow_count — observed=5 expected>=5 (local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json)
  [PASS] E2E RAG demo report citation_backed_response_draft_count — observed=5 expected>=4 (local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json)
  [PASS] E2E RAG demo report safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_rag_demo_report/trace_net_e2e_rag_demo_report_v1.json)

[endpoint]
  [PASS] E2E API wrapper smoke — quality_status=PASS (local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json)
  [PASS] E2E API wrapper smoke status — READY_FOR_LOCAL_ENDPOINT (local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json)
  [PASS] E2E API wrapper smoke api_wrapper_response_count — observed=5 expected>=5 (local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json)
  [PASS] E2E API wrapper smoke citation_backed_api_response_count — observed=5 expected>=4 (local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json)
  [PASS] E2E API wrapper smoke safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_api_wrapper_smoke/trace_net_e2e_api_wrapper_smoke_v1.json)
  [PASS] E2E local endpoint manifest — quality_status=PASS (local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json)
  [PASS] E2E local endpoint manifest status — READY_FOR_OPEN_WEBUI_SMOKE (local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json)
  [PASS] E2E local endpoint manifest endpoint_route_count — observed=4 expected>=4 (local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json)
  [PASS] E2E local endpoint manifest api_response_count — observed=5 expected>=5 (local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json)
  [PASS] E2E local endpoint manifest safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json)

[source]
  [PASS] E2E query input harness — present (tiff/trace_net_e2e_query_input_v1.py)
  [PASS] E2E query planning/routing tunnels — present (tiff/trace_net_e2e_query_planning_routing_v1.py)
  [PASS] E2E hybrid retrieval runtime — present (tiff/trace_net_e2e_hybrid_retrieval_runtime_v1.py)
  [PASS] E2E context pack builder — present (tiff/trace_net_e2e_context_pack_builder_v1.py)
  [PASS] E2E evidence sufficiency gate — present (tiff/trace_net_e2e_evidence_sufficiency_gate_v1.py)
  [PASS] E2E final gate smoke — present (tiff/trace_net_e2e_final_gate_smoke_v1.py)
  [PASS] E2E RAG demo report — present (tiff/trace_net_e2e_rag_demo_report_v1.py)
  [PASS] E2E API wrapper smoke — present (tiff/trace_net_e2e_api_wrapper_smoke_v1.py)
  [PASS] E2E local endpoint module — present (tiff/trace_net_e2e_local_endpoint_v1.py)
  [PASS] E2E local endpoint server — present (scripts/serve_trace_net_e2e_local_endpoint_v1.py)
  [PASS] Codebase checklist — present (tiff/trace_net_e2e_codebase_checklist_v1.py)

[table_route]
  [PASS] Table exact-search adapter — quality_status=PASS (local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json)
  [PASS] Table exact-search adapter table_exact_search_document_count — observed=1497 expected>=1000 (local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json)
  [PASS] Table exact-search adapter safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json)
  [PASS] Table exact-search smoke — quality_status=PASS (local_data/organization/trace_net/table_exact_search_smoke/trace_net_table_exact_search_smoke_v1.json)
  [PASS] Table exact-search smoke successful_smoke_query_count — observed=6 expected>=3 (local_data/organization/trace_net/table_exact_search_smoke/trace_net_table_exact_search_smoke_v1.json)
  [PASS] Table exact-search smoke total_match_count — observed=42 expected>=3 (local_data/organization/trace_net/table_exact_search_smoke/trace_net_table_exact_search_smoke_v1.json)
  [PASS] Table exact-search smoke safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/table_exact_search_smoke/trace_net_table_exact_search_smoke_v1.json)
  [PASS] Table hybrid retrieval bridge — quality_status=PASS (local_data/organization/trace_net/table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json)
  [PASS] Table hybrid retrieval bridge table_hybrid_bridge_record_count — observed=1497 expected>=1000 (local_data/organization/trace_net/table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json)
  [PASS] Table hybrid retrieval bridge safety/write counters — all observed authority/write counters are zero (local_data/organization/trace_net/table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json)
```
