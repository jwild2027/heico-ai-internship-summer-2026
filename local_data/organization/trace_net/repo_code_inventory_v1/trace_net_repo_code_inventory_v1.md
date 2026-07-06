# TRACE-Net repo code inventory v1

This is a code-content audit, not just a keyword scan.

## Counts
- Records: `13883`

### By location
- `generated_or_runtime_artifact`: 10836
- `active_source_code`: 1395
- `active_tests`: 1055
- `archived_reference`: 408
- `active_docs`: 165
- `tooling_or_patch_archive`: 24

### By category
- `table_visual_ocr`: 11661
- `server`: 8090
- `graph_vector`: 6815
- `safety`: 6515
- `page`: 6491
- `context_pack`: 4874
- `webui`: 1338
- `feedback`: 1066
- `crag`: 1042
- `self_rag`: 884
- `engram`: 795
- `final_gate`: 588
- `planner`: 257

## Highest-signal active source files

### `tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- Score: `398`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/stage checklist that proves which gates were actually executed. This bridge is intentionally pre-answer and artifact-only: - it does not call Gemma - it does not replace the WebUI server yet - it does not execute database/vector/search writes - it does not mutate source truth - it does not grant answer permission
- Functions: _read_json(path)@L53; _write_json(path, payload)@L59; _write_jsonl(path, records)@L64; _as_path(value)@L71; _path_status(path)@L77; _stage_row()@L83; _safe_summary(payload)@L108; _records(payload)@L113; _stage_used_row(tool_id, label, report_path, payload, count_key)@L118; _visual_context_bridge_counts(payload)@L134; _webui_visual_context_bridge_row(path, payload)@L154; _artifact_tool_rows(context_pack_payload, input_paths)@L186; _crag_row(crag_payload, crag_path, self_rag_payload)@L245; _checklist_text(rows)@L274; _rollup_safety(stage_payloads)@L287; _import_stage_builders()@L314; build_webui_self_rag_crag_bridge()@L330; _write_markdown(path, payload)@L570
- CLI args: --question, --kernel, --output-dir, --route-dispatch-handoff, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --image-visual-observer, --webui-visual-context-bridge, --max-records-per-slot, --min-high-signal-capsules, --min-evidence-strength-score, --quality, --report-path, --write-json, --min-checklist-count, --min-used-tool-count, --require-query-planner-used, --require-context-pack-builder-used, --require-self-rag-used, --require-crag-evaluated, --require-no-answer-permission, --require-no-source-truth-mutation, --require-no-write-attempts, --require-tool-status, --require-webui-visual-context-bridge-used, --min-visual-context-cards
- Tiff imports: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner; from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint; from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder; from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check; from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan
- Has __main__ guard.
- Signal snippets:
  - L22 `self_rag`: ons import Counter from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple MODULE_VERSION = "trace_net_webui_self_rag_crag_bridge_v1" REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json" STAGE_REPORT_NAMES = { "query_planner": "trace_net_engineering_query_planner_v1.json", "context_pack_blueprint": "trace_net_engineering_context_pack_blueprint_v1.json", "context_pack_builder": "trace_net_engineering_context_pack_builder_v1.json", "self_rag"
  - L1 `self-rag`: """TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/stage checklist that proves which gates were actually executed. This bridge is intentionally pre-answer and artifact-only: - it does not call Gemma - it does not replace the WebUI server yet - it does not execute database/vector/sear
  - L1 `crag`: """TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/stage checklist that proves which gates were actually executed. This bridge is intentionally pre-answer and artifact-only: - it does not call Gemma - it does not replace the WebUI server yet - it does not execute database/vector/search writes -
  - L27 `context_pack`: " REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json" STAGE_REPORT_NAMES = { "query_planner": "trace_net_engineering_query_planner_v1.json", "context_pack_blueprint": "trace_net_engineering_context_pack_blueprint_v1.json", "context_pack_builder": "trace_net_engineering_context_pack_builder_v1.json", "self_rag": "trace_net_engineering_context_self_rag_check_v1.json", "crag_retry": "trace_net_engineering_context_crag_retry_plan_v1.json", } ARTIFACT_TOOL_KEYS = { "route_dispatch": "f
  - L213 `context pack`: ath = webui_visual_context_bridge_path or path count = visual_card_count elif count > 0: status = "used" reason = f"context pack builder selected/loaded {count} records from {artifact_name}" elif path_state == "available": status = "available_not_used" reason = f"artifact exists but no records were loaded/selected from {artifact_name}" elif path_state == "input_missing": status = "input_missing" reason = f"co

### `scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py`
- Score: `332`
- Categories: `page, self_rag, server, webui`
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_build
- Has __main__ guard.
- Signal snippets:
  - L8 `self_rag`: port Path REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_build if __name__ == "__main__": raise SystemExit(main_build())
  - L8 `crag`: REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_build if __name__ == "__main__": raise SystemExit(main_build())

### `scripts/check_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Score: `332`
- Categories: `page, self_rag, server, webui`
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_check
- Has __main__ guard.
- Signal snippets:
  - L8 `self_rag`: port Path REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_check if __name__ == "__main__": raise SystemExit(main_check())
  - L8 `crag`: REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_check if __name__ == "__main__": raise SystemExit(main_check())

### `tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Score: `324`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: load_json(path)@L21; write_json(path, data)@L25; write_jsonl(path, rows)@L30; _as_int(value, default)@L37; _as_bool(value, default)@L52; _first_present(mapping, keys, default)@L62; _first_list(mapping, keys)@L69; _count_records(value)@L77; _nested(mapping, path, default)@L99; _extract_context_packs(report)@L108; _get_evidence_records(pack)@L170; _get_graph_guidance_records(pack)@L201; _get_summary_guidance_records(pack)@L214; _get_aggregation_box(pack)@L227; _has_answer_rules(pack)@L234; _guidance_authority_ok(pack)@L243; evaluate_pack(pack, idx)@L268; _quality_check(name, observed, op, expected)@L407
- CLI args: --min-context-packs, --min-self-rag-evaluations, --min-crag-plans, --min-ready-for-llm, --min-contexts-with-source-truth-evidence, --min-contexts-with-graph-guidance, --min-contexts-with-v2-summary-guidance, --min-contexts-with-aggregation-or-cap-disclosure, --max-retry-required-count, --max-audit-only-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --executed-plan-context-pack, --output-dir, --quality
- Has __main__ guard.
- Signal snippets:
  - L9 `self_rag`: taclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple MODULE = "trace_net_e2e_live_self_rag_crag_evaluator_v20" VERSION = "v20" READY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_READY_FOR_LIVE_LLM_PROMPT" NEEDS_RETRY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_NEEDS_CRAG_RETRY_OR_REPAIR" READY_SELF_RAG_STATUSES = { "CONTEXT_READY_FOR_LLM", "CONTEXT_READY_WITH_CAP_DISCLOSURE", "CONTEXT_PARTIAL_NEEDS_LIMITATION", } def load_json
  - L604 `self-rag`: ath) write_json(report_path, report) return report def render_markdown(report: Mapping[str, Any]) -> str: lines = [ "# TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20", "", f"Quality status: **{report.get('quality_status')}**", f"Status: `{report.get('status')}`", "", "## Summary", ] for key in [ "context_pack_count", "self_rag_evaluation_count", "crag_plan_count", "ready_for_llm_count", "ready_with_cap_di
  - L9 `crag`: rom pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple MODULE = "trace_net_e2e_live_self_rag_crag_evaluator_v20" VERSION = "v20" READY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_READY_FOR_LIVE_LLM_PROMPT" NEEDS_RETRY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_NEEDS_CRAG_RETRY_OR_REPAIR" READY_SELF_RAG_STATUSES = { "CONTEXT_READY_FOR_LLM", "CONTEXT_READY_WITH_CAP_DISCLOSURE", "CONTEXT_PARTIAL_NEEDS_LIMITATION", } def load_json(path: st
  - L12 `repair`: = "v20" READY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_READY_FOR_LIVE_LLM_PROMPT" NEEDS_RETRY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_NEEDS_CRAG_RETRY_OR_REPAIR" READY_SELF_RAG_STATUSES = { "CONTEXT_READY_FOR_LLM", "CONTEXT_READY_WITH_CAP_DISCLOSURE", "CONTEXT_PARTIAL_NEEDS_LIMITATION", } def load_json(path: str | Path) -> Any: return json.loads(Path(path).read_text(encoding="utf-8")) def write_json(path: str | Path, data: Any) -> None: Path(path).parent.mkdir(parents=True, exist_ok=T
  - L108 `context_pack`: for key in path: if not isinstance(cur, Mapping) or key not in cur: return default cur = cur[key] return cur def _extract_context_packs(report: Mapping[str, Any]) -> List[Mapping[str, Any]]: for key in ( "context_packs", "executed_plan_context_packs", "executed_plan_context_pack_records", "packs", "records", ): value = report.get(key) if isinstance(value, list) and value: return [v for v in value if isi

### `tiff/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Score: `317`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1. Artifact-first targeted smoke for retrieved Engram overlays. This module prepends H24 retrieved Engram overlay guidance to saved engineering answer-runner prompts from an existing answer-smoke manifest. It can run in: * artifact mode: deterministic scaffold answers, no LLM call * ollama mode: targeted local Gemma/Ollama calls Safety contract: - no Postgres writes - no Qdrant reads/writes - no OpenSearch writes/uploads - no source-t
- Functions: _norm(value)@L68; _read_json(path)@L72; _write_json(path, data)@L76; _write_jsonl(path, rows)@L81; _compact_text(text, max_chars)@L88; _parse_question_ids(value)@L99; _index_by_question_id(records)@L109; _load_prompt_from_source_record(record, repo_root)@L113; _source_records(answer_smoke)@L127; _overlay_records(overlay_smoke)@L131; _match_overlay_for_question(question_id, overlays)@L135; _prompt_hash(text)@L142; build_overlay_llm_prompt()@L146; _artifact_answer(question_id, source_record, overlay_record)@L179; _call_ollama(prompt)@L206; _count_unsupported_claims(answer)@L252; _contains_boundary(answer)@L264; grade_h25_answer(question_id, answer, source_grade)@L275
- CLI args: --overlay-smoke, --source-answer-smoke, --output-dir, --question-ids, --llm-mode, --ollama-model, --ollama-url, --timeout-seconds, --max-prompt-chars, --max-overlay-chars, --max-source-prompt-chars, --min-queries, --min-llm-answered, --min-good-answers, --min-good-or-partial-answers, --max-bad-answers, --max-unsupported-claims, --max-unsafe, --max-write-attempts, --require-h24-quality-pass, --require-source-answer-smoke-quality-pass, --require-no-answer-permission, --llm-smoke, --min-queries, --min-llm-answered, --min-good-answers, --min-good-or-partial-answers, --require-quality-pass, --require-no-answer-permission, --max-bad-answers
- Routes: http://127.0.0.1:11434/api/generate@L355, http://127.0.0.1:11434/api/generate@L643
- Has __main__ guard.
- Signal snippets:
  - L1 `engram`: """TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1. Artifact-first targeted smoke for retrieved Engram overlays. This module prepends H24 retrieved Engram overlay guidance to saved engineering answer-runner prompts from an existing answer-smoke manifest. It can run in: * artifact mode: deterministic scaffold answers, no LLM call * ollama mode: targeted local Gemma
  - L299 `repair`: , "nomenclature", "visual route", "figure-to-part", "line-text"]): return "GOOD", unsupported, [] return "PARTIAL", unsupported, ["route_or_repair_explanation_weak"] if _contains_boundary(answer): return "GOOD", unsupported, [] return "PARTIAL", unsupported, ["boundary_language_missing"] def _quality_status( *, query_count: int, llm_answered_count: int, good_answer_count: int, good_or_partial_answer_count: int, bad_answer_count: int, unsupported_clai
  - L18 `proof`: earch writes/uploads - no source-truth mutation - no answer permission - Engram overlay is behavior guidance only; source/manual claims still require current proof_context citations. """ from __future__ import annotations import argparse import hashlib import json import re import urllib.error import urllib.request from dataclasses import dataclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple MODULE = "trace_net_engineering_engram_answer_runner_overl
  - L5 `guidance`: ing Engram Answer-Runner Overlay LLM Smoke v1. Artifact-first targeted smoke for retrieved Engram overlays. This module prepends H24 retrieved Engram overlay guidance to saved engineering answer-runner prompts from an existing answer-smoke manifest. It can run in: * artifact mode: deterministic scaffold answers, no LLM call * ollama mode: targeted local Gemma/Ollama calls Safety contract: - no Postgres writes - no Qdrant reads/writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permissi
  - L9 `ollama`: saved engineering answer-runner prompts from an existing answer-smoke manifest. It can run in: * artifact mode: deterministic scaffold answers, no LLM call * ollama mode: targeted local Gemma/Ollama calls Safety contract: - no Postgres writes - no Qdrant reads/writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permission - Engram overlay is behavior guidance only; source/manual claims still require current proof_context citations. """ from __future__ import annotations import argpar

### `tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Score: `310`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _missing_boundary_groups(text)@L56; _norm(value)@L65; _read_json(path)@L69; _write_json(path, data)@L73; _write_jsonl(path, records)@L78; _as_list(value)@L85; _safety_counts_zero(data)@L95; _compact_text(text, max_chars)@L111; _prompt_bundles(prompt_injector)@L118; _llm_smoke_records(llm_smoke)@L122; build_bridge_records(prompt_injector, llm_smoke)@L128; _count_task_types(records)@L175; _count_layers(records)@L183; build_answer_runner_retrieval_bridge_manifest()@L192; check_answer_runner_retrieval_bridge_manifest()@L324; build_arg_parser()@L359; main(argv)@L375
- CLI args: --prompt-injector, --h22-llm-smoke, --output-dir, --max-guidance-chars, --min-bridge-records, --min-task-types, --require-h20-quality-pass, --require-h22-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L8 `engram`: otations import argparse import json from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Sequence MODULE = "trace_net_engineering_engram_answer_runner_retrieval_bridge_v1" VERSION = "v1" SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_read_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attempt":
  - L28 `critic`: nterchangeability_boundary": ["q12", "q21"], "approval_boundary": ["q13", "q14", "q15", "q30"], "route_explanation": ["q16", "q17", "q27", "q28"], "critic_repair": ["q16", "q18", "q27"], "unknown_part": ["q25"], "summary_limit": ["q29"], } REQUIRED_BOUNDARY_GROUPS = { "behavior_guidance_boundary": [ "behavior guidance only", "behavior only", "answer behavior only", "shape answer behavior only", "shapes answer behavior only", ], "not_proof_boun
  - L28 `repair`: ngeability_boundary": ["q12", "q21"], "approval_boundary": ["q13", "q14", "q15", "q30"], "route_explanation": ["q16", "q17", "q27", "q28"], "critic_repair": ["q16", "q18", "q27"], "unknown_part": ["q25"], "summary_limit": ["q29"], } REQUIRED_BOUNDARY_GROUPS = { "behavior_guidance_boundary": [ "behavior guidance only", "behavior only", "answer behavior only", "shape answer behavior only", "shapes answer behavior only", ], "not_proof_boundary":
  - L21 `proof`: "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attempt": False, "live_qdrant_io_attempted": False, "engram_is_proof": False, } TASK_TYPE_TO_TARGET_QUESTIONS = { "interchangeability_boundary": ["q12", "q21"], "approval_boundary": ["q13", "q14", "q15", "q30"], "route_explanation": ["q16", "q17", "q27", "q28"], "critic_repair": ["q16", "q18", "q27"], "unknown_part": ["q25"], "summary_limit": ["q29"], } REQUIRED_BOUNDARY_GROUPS = { "behavio
  - L34 `guidance`: ", "q28"], "critic_repair": ["q16", "q18", "q27"], "unknown_part": ["q25"], "summary_limit": ["q29"], } REQUIRED_BOUNDARY_GROUPS = { "behavior_guidance_boundary": [ "behavior guidance only", "behavior only", "answer behavior only", "shape answer behavior only", "shapes answer behavior only", ], "not_proof_boundary": [ "not proof", "not manual evidence", "do not use engram memory as manual evidence", "engram memory as ma

### `tiff/trace_net_engineering_engram_crag_repair_v1.py`
- Score: `307`
- Categories: `crag, engram, feedback, final_gate, graph_vector, page, safety, self_rag, server`
- Functions: _read_json(path)@L16; _write_json(path, data)@L21; _write_jsonl(path, rows)@L27; _norm(value)@L35; _preview(value, limit)@L39; _sha(text)@L46; _record_question_id(record)@L50; _answer_text(record)@L54; _critic_records(critic)@L58; _answer_records(answer_smoke)@L63; critic_recommends_repair(record)@L75; is_expected_boundary(record)@L82; build_artifact_repair_answer()@L87; build_crag_repair_manifest()@L107; check_crag_repair_manifest()@L312; build_arg_parser()@L357; main(argv)@L374
- CLI args: --critic, --answer-smoke, --output-dir, --llm-mode, --min-records, --min-crag-pass-or-no-repair, --max-repair-attempts, --require-source-quality-pass, --require-critic-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L9 `engram`: tations import argparse import json import hashlib from pathlib import Path from typing import Any, Mapping, Sequence MODULE = "trace_net_engineering_engram_crag_repair_v1" VERSION = "v1" REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"} PASS_STATUSES = {"PASS", "EXPECTED_BOUNDARY", "NO_REPAIR_REQUIRED", "REPAIRED_ARTIFACT"} def _read_json(path: str | Path) -> dict[str, Any]: p = Path(path) return json.loads(p.read_text(encoding="utf-8")) def
  - L394 `self_rag`: = { "critic": ( "critic", "critic_path", "critic_manifest", "critic_manifest_path", "self_rag_critic", "self_rag_critic_path", ), "answer_smoke": ( "answer_smoke", "answer_smoke_path", "answer_smoke_manifest", "answer_smoke_manifest_path", "source_answer_smoke", "source_answer_smoke_path", ), } for cli_name, candi
  - L95 `self-rag`: is candidate does not add new proof and must remain bounded by current proof_context citations.\n\n" "Evidence:\n" "- The original answer and Self-RAG critic record were used as behavior guidance only, not as manual/source proof.\n\n" "Repair guidance:\n" f"{hint_text}\n\n" "Original answer preview:\n" f"{original}\n\n" "Engineering confidence:\n" "LOW until the repaired answer is rerun through the answer-smoke citation and unsupported-claim ga
  - L9 `crag`: import argparse import json import hashlib from pathlib import Path from typing import Any, Mapping, Sequence MODULE = "trace_net_engineering_engram_crag_repair_v1" VERSION = "v1" REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"} PASS_STATUSES = {"PASS", "EXPECTED_BOUNDARY", "NO_REPAIR_REQUIRED", "REPAIRED_ARTIFACT"} def _read_json(path: str | Path) -> dict[str, Any]: p = Path(path) return json.loads(p.read_text(encoding="utf-8")) def _write_
  - L12 `critic`: Any, Mapping, Sequence MODULE = "trace_net_engineering_engram_crag_repair_v1" VERSION = "v1" REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"} PASS_STATUSES = {"PASS", "EXPECTED_BOUNDARY", "NO_REPAIR_REQUIRED", "REPAIRED_ARTIFACT"} def _read_json(path: str | Path) -> dict[str, Any]: p = Path(path) return json.loads(p.read_text(encoding="utf-8")) def _write_json(path: str | Path, data: Mapping[str, Any]) -> None: p = Path(path) p.parent.mkdi

### `tiff/trace_net_engineering_engram_self_rag_critic_v1.py`
- Score: `299`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server`
- Doc: TRACE-Net Engineering Engram Self-RAG Critic v1. Artifact-only critic for targeted Engram overlay answer-smoke runs. It reads an answer-smoke manifest and emits per-answer Self-RAG style critic records. It does not call an LLM and does not write to databases or vector/search systems.
- Functions: _read_json(path)@L25; _write_json(path, data)@L30; _write_jsonl(path, rows)@L36; _as_int(value, default)@L44; _text(record)@L53; _is_expected_unknown_boundary(record)@L57; _has_required_sections(answer)@L68; _safe_but_generic_risk(record)@L73; critique_answer_record(record)@L85; build_self_rag_critic_manifest()@L209; check_self_rag_critic_manifest()@L315; build_arg_parser()@L353; check_arg_parser()@L367; main(argv)@L380; check_main(argv)@L398
- CLI args: --answer-smoke, --output-dir, --min-records, --min-critic-pass-or-expected, --max-repair-recommended, --max-unsafe, --max-write-attempts, --require-source-quality-pass, --require-no-answer-permission, --critic, --min-records, --min-critic-pass-or-expected, --max-repair-recommended, --max-unsafe, --max-write-attempts, --require-quality-pass, --require-no-answer-permission
- Has __main__ guard.
- Signal snippets:
  - L1 `engram`: """TRACE-Net Engineering Engram Self-RAG Critic v1. Artifact-only critic for targeted Engram overlay answer-smoke runs. It reads an answer-smoke manifest and emits per-answer Self-RAG style critic records. It does not call an LLM and does not write to databases or vector/search systems. """ from __future__ import annotations import argparse import json import re from dataclasses i
  - L17 `self_rag`: ort json import re from dataclasses import dataclass from pathlib import Path from typing import Any, Iterable, Mapping MODULE = "trace_net_engineering_engram_self_rag_critic_v1" VERSION = "v1" EXPECTED_UNKNOWN_CATEGORIES = {"unknown_part", "unknown_figure"} CITATION_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_\-]*\]") GROUPED_CITATION_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_\-]*\s*,\s*[A-Za-z]") def _read_json(path: str | Path) -> dict[str, Any]: p = Path(path) return json.loads(p.read_text(encoding="utf-8")
  - L1 `self-rag`: """TRACE-Net Engineering Engram Self-RAG Critic v1. Artifact-only critic for targeted Engram overlay answer-smoke runs. It reads an answer-smoke manifest and emits per-answer Self-RAG style critic records. It does not call an LLM and does not write to databases or vector/search systems. """ from __future__ import annotations import argparse import json import re from dataclasses import d
  - L163 `crag`: status = "EXPECTED_BOUNDARY" elif grade not in {"GOOD", "PARTIAL"}: findings.append("bad_or_blocked_answer_grade") repair_hints.append("Run CRAG-style repair before accepting this answer.") critic_status = "REPAIR_RECOMMENDED" elif grade == "PARTIAL" and critic_status == "PASS": findings.append("unexpected_partial_answer") repair_hints.append("Review for missing citations, incomplete answer, or over-generic refusal.") critic_status = "REVIEW" if unsafe:
  - L1 `critic`: """TRACE-Net Engineering Engram Self-RAG Critic v1. Artifact-only critic for targeted Engram overlay answer-smoke runs. It reads an answer-smoke manifest and emits per-answer Self-RAG style critic records. It does not call an LLM and does not write to databases or vector/search systems. """ from __future__ import annotations import argparse import json import re from dataclasses import dataclass

### `tiff/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Score: `294`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, server, webui`
- Functions: _norm(value)@L50; _read_json(path)@L54; _write_json(path, data)@L58; _write_jsonl(path, records)@L63; _as_list(value)@L70; _parse_question_ids(value)@L80; _compact_text(text, max_chars)@L93; _missing_boundary_groups(text)@L100; _records_by_question_id(source_answer_smoke)@L109; _bridge_records(bridge)@L115; _bridge_records_for_question(bridge, question_id)@L119; _combine_layers(records)@L127; _combine_proof_roles(records)@L131; build_overlay_text(question_id, bridge_records, max_overlay_chars)@L135; build_overlay_records(bridge, source_answer_smoke)@L155; _count_layers(records)@L209; _count_matched_task_types(records)@L218; _safety_counts_zero(data)@L227
- CLI args: --bridge, --source-answer-smoke, --output-dir, --question-ids, --max-overlay-chars, --min-overlay-records, --min-matched-bridge-records, --require-h23-quality-pass, --require-source-answer-smoke-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L8 `engram`: otations import argparse import json from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Sequence MODULE = "trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1" VERSION = "v1" SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_read_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attemp
  - L151 `repair`: end("Required response discipline: answer from current proof_context only; use retrieved Engram overlay only to shape wording, boundaries, route awareness, and repair behavior.") return _compact_text("\n".join(chunks).strip(), max_overlay_chars) def build_overlay_records( bridge: Mapping[str, Any], source_answer_smoke: Mapping[str, Any] | None = None, *, question_ids: str | Sequence[str] | None = None, max_overlay_chars: int = 1800, ) -> List[Dict[str, Any]]: qids = _parse_question_ids
  - L21 `proof`: "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attempt": False, "live_qdrant_io_attempted": False, "engram_is_proof": False, } DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"] ALLOWED_PROOF_ROLES = {"guidance_only", "current_proof_context_only"} REQUIRED_BOUNDARY_GROUPS = { "behavior_guidance_boundary": [ "behavior guidance only", "behavior only", "answer behavior only", "shape answer behavior only", "sh
  - L25 `guidance`: "live_qdrant_io_attempted": False, "engram_is_proof": False, } DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"] ALLOWED_PROOF_ROLES = {"guidance_only", "current_proof_context_only"} REQUIRED_BOUNDARY_GROUPS = { "behavior_guidance_boundary": [ "behavior guidance only", "behavior only", "answer behavior only", "shape answer behavior only", "shapes answer behavior only", ], "not_proof_boundary": [ "not proof", "not manual evid
  - L15 `qdrant`: e_v1" VERSION = "v1" SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_read_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attempt": False, "live_qdrant_io_attempted": False, "engram_is_proof": False, } DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"] ALLOWED_PROOF_ROLES = {"guidance_only", "current_pr

### `scripts/check_trace_net_e2e_live_self_rag_crag_evaluator_v20_quality.py`
- Score: `292`
- Categories: `crag, page, self_rag, server`
- Functions: main()@L14
- CLI args: --report-path, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json
- Has __main__ guard.
- Signal snippets:
  - L11 `self_rag`: t Path REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net live Self-RAG + CRAG evaluator v20 quality") parser.add_argument("--report-path", required=True) parser.add_argument("--write-json", action="store_true") add_common_args
  - L15 `self-rag`: v20 import add_common_args, evaluate_quality, load_json, write_json def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net live Self-RAG + CRAG evaluator v20 quality") parser.add_argument("--report-path", required=True) parser.add_argument("--write-json", action="store_true") add_common_args(parser) args = parser.parse_args() report = load_json(args.report_path) checks = evaluate_quality(report, args) quality_status = "PASS" if all(c["passed"] for c in ch
  - L11 `crag`: EPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net live Self-RAG + CRAG evaluator v20 quality") parser.add_argument("--report-path", required=True) parser.add_argument("--write-json", action="store_true") add_common_args(parser)

### `scripts/check_trace_net_engineering_engram_crag_repair_v1.py`
- Score: `283`
- Categories: `crag, engram, page, safety, self_rag, server`
- Functions: main()@L12
- CLI args: --crag-repair, --min-records, --min-crag-pass-or-no-repair, --require-quality-pass, --require-no-answer-permission, --max-repair-attempts, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest
- Has __main__ guard.
- Signal snippets:
  - L9 `engram`: rgparse import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram CRAG repair artifact v1") parser.add_argument("--crag-repair", required=True) parser.add_argument("--min-records", type=int, default=1) parser.add_argument("--min-crag-pass-or-no-repair"
  - L9 `crag`: import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram CRAG repair artifact v1") parser.add_argument("--crag-repair", required=True) parser.add_argument("--min-records", type=int, default=1) parser.add_argument("--min-crag-pass-or-no-repair", type=
  - L26 `critic`: crag_repair_manifest(**vars(args)) print("status=" + str(result.get("status"))) print("quality_status=" + str(result.get("quality_status"))) print("critic_record_count=" + str(result.get("critic_record_count"))) print("crag_pass_or_no_repair_count=" + str(result.get("crag_pass_or_no_repair_count"))) print("repair_recommended_count=" + str(result.get("repair_recommended_count"))) print("repair_attempt_count=" + str(result.get("repair_attempt_count"))) print("unsafe_finding_count=" + str(r
  - L9 `repair`: rt sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram CRAG repair artifact v1") parser.add_argument("--crag-repair", required=True) parser.add_argument("--min-records", type=int, default=1) parser.add_argument("--min-crag-pass-or-no-repair", type=int,
  - L31 `answer_permission`: rint("repair_attempt_count=" + str(result.get("repair_attempt_count"))) print("unsafe_finding_count=" + str(result.get("unsafe_finding_count"))) print("answer_permission_count=" + str(result.get("answer_permission_count"))) print("write_attempt_count=" + str(result.get("write_attempt_count"))) if result.get("quality_failures"): print("quality_failures=" + repr(result.get("quality_failures"))) return 0 if result.get("quality_status") == "PASS" else 1 if __name__ == "__main__": raise

### `scripts/build_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Score: `274`
- Categories: `page, self_rag, server`
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main
- Has __main__ guard.
- Signal snippets:
  - L10 `self_rag`: t Path REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main if __name__ == "__main__": raise SystemExit(main())
  - L10 `crag`: EPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main if __name__ == "__main__": raise SystemExit(main())

### `scripts/build_trace_net_page_context_pack_v3.py`
- Score: `273`
- Categories: `context_pack, graph_vector, page, server, table_visual_ocr, webui`
- Doc: Build TRACE-Net Page Context Pack v3.
- Functions: parse_args()@L19; _warn_missing_optional_path(label, value)@L38; _resolve_sidecar_path(base_path, value)@L43; _read_jsonl(path)@L58; load_artifact_with_sidecars(path)@L85; main()@L122
- CLI args: --question, --pages, --max-pages, --route-manifest, --graph-export, --ocr-records, --table-evidence, --exact-part-records, --visual-summaries, --vector-hits, --output
- Tiff imports: from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, load_json, write_json
- Has __main__ guard.
- Signal snippets:
  - L16 `context_pack`: import Any REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, load_json, write_json def parse_args() -> argparse.Namespace: parser = argparse.ArgumentParser(description="Build a TRACE-Net page context pack v3 JSON artifact.") parser.add_argument("--question", default="", help="User question used to select pages/entities.") parser.add_argument("--pages", n
  - L2 `context pack`: #!/usr/bin/env python3 """Build TRACE-Net Page Context Pack v3.""" from __future__ import annotations import argparse from pathlib import Path import sys import json from typing import Any REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, load_json, write
  - L153 `proof`: cted_page_count: {summary.get('selected_page_count')}") print(f"source_trace_ready_page_count: {summary.get('source_trace_ready_page_count')}") print(f"proof_record_count: {summary.get('proof_record_count')}") print(f"guidance_record_count: {summary.get('guidance_record_count')}") print(f"source_file_count: {summary.get('source_file_count')}") print(f"source_link_count: {summary.get('source_link_count')}") print(f"ocr_excerpt_count: {summary.get('ocr_excerpt_count')}") print(f"visual_gui
  - L91 `guidance`: ge cards live in a `records_jsonl_path` or similar sidecar. v3.2 follows those read-only sidecars so page 202-style image routes can attach visual guidance instead of only a manifest summary. """ payload = load_json(path, {}) if not isinstance(payload, dict): return payload merged = dict(payload) linked_keys = ( "records_jsonl_path", "records_path", "sample_records_jsonl_path", "visual_records_jsonl_path", "llava_records_jsonl_path",
  - L88 `openwebui`: return rows def load_artifact_with_sidecars(path: str | None) -> Any: """Load a JSON artifact and hydrate common linked JSONL sidecars. Some visual/OpenWebUI route artifacts are manifests whose real page cards live in a `records_jsonl_path` or similar sidecar. v3.2 follows those read-only sidecars so page 202-style image routes can attach visual guidance instead of only a manifest summary. """ payload = load_json(path, {}) if not isinstance(payload, dict): return payload

### `scripts/check_trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Score: `270`
- Categories: `engram, page, safety, server, webui`
- Functions: main()@L14
- CLI args: --overlay-smoke, --min-overlay-records, --min-matched-bridge-records, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import check_answer_runner_prompt_overlay_smoke_manifest
- Has __main__ guard.
- Signal snippets:
  - L11 `engram`: athlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import check_answer_runner_prompt_overlay_smoke_manifest def main() -> int: p = argparse.ArgumentParser(description="Check TRACE-Net H24 Engram answer-runner prompt overlay smoke.") p.add_argument("--overlay-smoke", required=True) p.add_argument("--min-overlay-records", type=int, default=5) p.add
  - L11 `answer_runner`: import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import check_answer_runner_prompt_overlay_smoke_manifest def main() -> int: p = argparse.ArgumentParser(description="Check TRACE-Net H24 Engram answer-runner prompt overlay smoke.") p.add_argument("--overlay-smoke", required=True) p.add_argument("--min-overlay-records", type=int, default=5) p.add_argume
  - L29 `answer_permission`: overlay_records, min_matched_bridge_records=args.min_matched_bridge_records, require_quality_pass=args.require_quality_pass, require_no_answer_permission=args.require_no_answer_permission, max_unsafe=args.max_unsafe, max_write_attempts=args.max_write_attempts, ) s = result.get("summary", {}) print("status=" + str(result.get("status"))) print("quality_status=" + str(result.get("quality_status"))) print("overlay_record_count=" + str(s.get("overlay_record_cou

### `scripts/check_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Score: `270`
- Categories: `engram, page, safety, server, webui`
- Functions: build_arg_parser()@L14; main(argv)@L26
- CLI args: --bridge, --min-bridge-records, --min-task-types, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import check_answer_runner_retrieval_bridge_manifest
- Has __main__ guard.
- Signal snippets:
  - L11 `engram`: rt json import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import check_answer_runner_retrieval_bridge_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net H23 Engram answer-runner retrieval bridge.") p.add_argument("--bridge", required=True) p.add_argument("--min-bridge-records", type=int, default=
  - L11 `answer_runner`: import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import check_answer_runner_retrieval_bridge_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net H23 Engram answer-runner retrieval bridge.") p.add_argument("--bridge", required=True) p.add_argument("--min-bridge-records", type=int, default=6)
  - L36 `answer_permission`: runner_question_count=" + str(s.get("target_answer_runner_question_count"))) print("unsafe_finding_count=" + str(s.get("unsafe_finding_count"))) print("answer_permission_count=" + str(s.get("answer_permission_count"))) print("write_attempt_count=" + str(s.get("write_attempt_count"))) if result.get("quality_failures"): print("quality_failures=" + json.dumps(result.get("quality_failures"))) return 0 if result.get("quality_status") == "PASS" else 1 if __name__ == "__main__": raise Sys

### `tiff/trace_net_e2e_live_llm_final_gate_v23.py`
- Score: `270`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live LLM Final Gate v23. Validates and repairs live Gemma/LLM draft answers before they can be used as WebUI final answers. The gate is intentionally non-mutating: it reads v21 prompt contracts and v22 LLM drafts, checks authority boundaries, and emits final-gated answers that use direct source-truth evidence only.
- Functions: load_json(path)@L40; write_json(path, data)@L44; write_jsonl(path, rows)@L49; _first_list(obj, keys)@L56; prompt_contracts(data)@L74; llm_drafts(data)@L78; _messages(row)@L82; _context_message(row)@L86; _block_between(text, start_marker, end_markers)@L94; _parse_json_after_marker(text, marker, end_markers)@L107; _parse_evidence_line(line)@L117; _extract_evidence(context)@L137; _citation_nums(text)@L163; _safe_str(value)@L173; _cap_sentence(aggregation)@L177; _unique_pages(direct)@L192; _field_counts(direct)@L203; _query_kind(query, direct)@L207
- CLI args: --live-llm-prompt-contract, --live-llm-draft-adapter, --output-dir, --min-llm-drafts, --min-final-gates, --min-passed-final-gates, --min-final-answers-ready-for-webui, --min-repaired-final-answers, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality, --write-json, --report-path, --min-llm-drafts, --min-final-gates, --min-passed-final-gates, --min-final-answers-ready-for-webui, --min-repaired-final-answers, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations
- Has __main__ guard.
- Signal snippets:
  - L29 `self_rag`: OURCE-TRUTH EVIDENCE" _NEARBY_HEADER = "NEARBY SOURCE-TRUTH CONTEXT" _GRAPH_HEADER = "GRAPH / LEIDEN GUIDANCE" _AGG_MARKER = "AGGREGATION / CAPPING METADATA:" _SELF_RAG_MARKER = "SELF-RAG / CRAG STATUS:" _ANSWER_RULES_MARKER = "ANSWER RULES:" _EVIDENCE_RE = re.compile( r"^-\s*\[(?P<marker>\d+)\]\s+page=(?P<page>\S+)\s+field=(?P<field>\S+)\s+value=(?P<value>.*?)(?:\s+occurrence_count=(?P<count>\d+))?\s*$" ) _CITATION_RE = re.compile(r"\[(\d+)\]") _PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b") _MAN
  - L29 `self-rag`: E" _NEARBY_HEADER = "NEARBY SOURCE-TRUTH CONTEXT" _GRAPH_HEADER = "GRAPH / LEIDEN GUIDANCE" _AGG_MARKER = "AGGREGATION / CAPPING METADATA:" _SELF_RAG_MARKER = "SELF-RAG / CRAG STATUS:" _ANSWER_RULES_MARKER = "ANSWER RULES:" _EVIDENCE_RE = re.compile( r"^-\s*\[(?P<marker>\d+)\]\s+page=(?P<page>\S+)\s+field=(?P<field>\S+)\s+value=(?P<value>.*?)(?:\s+occurrence_count=(?P<count>\d+))?\s*$" ) _CITATION_RE = re.compile(r"\[(\d+)\]") _PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b") _MANUAL_REF_RE = re.com
  - L29 `crag`: HEADER = "NEARBY SOURCE-TRUTH CONTEXT" _GRAPH_HEADER = "GRAPH / LEIDEN GUIDANCE" _AGG_MARKER = "AGGREGATION / CAPPING METADATA:" _SELF_RAG_MARKER = "SELF-RAG / CRAG STATUS:" _ANSWER_RULES_MARKER = "ANSWER RULES:" _EVIDENCE_RE = re.compile( r"^-\s*\[(?P<marker>\d+)\]\s+page=(?P<page>\S+)\s+field=(?P<field>\S+)\s+value=(?P<value>.*?)(?:\s+occurrence_count=(?P<count>\d+))?\s*$" ) _CITATION_RE = re.compile(r"\[(\d+)\]") _PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b") _MANUAL_REF_RE = re.compile(r"\b\d
  - L3 `repair`: """TRACE-Net E2E Live LLM Final Gate v23. Validates and repairs live Gemma/LLM draft answers before they can be used as WebUI final answers. The gate is intentionally non-mutating: it reads v21 prompt contracts and v22 LLM drafts, checks authority boundaries, and emits final-gated answers that use direct source-truth evidence only. """ from __future__ import annotations import argparse import json import re fr
  - L370 `context_pack`: nal_gate_v23_{idx:04d}", "llm_draft_id": draft.get("llm_draft_id"), "prompt_contract_id": draft.get("prompt_contract_id"), "context_pack_id": draft.get("context_pack_id"), "user_query": query, "final_gate_status": "LIVE_LLM_FINAL_GATE_PASS" if passed else "LIVE_LLM_FINAL_GATE_BLOCKED", "final_gate_passed": passed, "ready_for_webui_endpoint": passed, "draft_text": draft_text, "final_answer": repaired_answer if

### `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- Score: `269`
- Categories: `context_pack, engram, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net OpenWebUI page-context bridge v1. This module is intentionally a thin adapter. It does not replace the current V3 bridge or Gemma answer runner. Instead, it detects page-centered questions, builds a page_context_pack_v3 binder, and injects that binder into OpenAI-style chat messages before forwarding to the existing V3 bridge. Safety contract: - read-only artifact access - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/summa
- Classes: PageContextArtifactPaths@L51 methods=['existing_cli_args', 'missing_paths']; NativePageAnswerError@L458 methods=['__init__']; PageContextBridgeServer@L1051 methods=['__init__']; PageContextBridgeHandler@L1090 methods=['log_message', 'do_GET', 'do_POST']
- Functions: _dedupe_ints(values)@L81; extract_page_numbers(question)@L93; should_use_page_context(question)@L140; latest_user_question(messages)@L145; _safe_filename_fragment(text, limit)@L160; default_output_path(question, pages)@L166; build_page_context_pack_via_cli()@L174; count_pack_records(pack)@L248; _sample(value, max_chars)@L261; render_page_context_binder(pack)@L277; enrich_openai_messages(messages, pack)@L350; enrich_chat_payload(payload)@L368; normalize_ollama_openai_base_url(base_url)@L420; ollama_native_api_base_url(base_url)@L440; render_native_page_answer_messages(pack)@L467; call_native_ollama_openai_chat()@L505; build_native_page_context_response()@L584; build_native_failure_fallback_response()@L697
- CLI args: --question, --pages, --repo-root, --output-context-pack, --output, --host, --port, --repo-root, --upstream-base-url, --model-id, --upstream-model, --max-pages, --max-binder-chars, --native-page-answer-mode, --native-llm-base-url, --native-llm-model, --native-llm-api-key, --native-temperature, --native-request-timeout, --native-num-ctx, --native-max-tokens
- Routes: Normalize Ollama/OpenAI-compatible base URL to the /v1 base.

    The lower-level OpenAI-compatible call appends /chat/completions, so a raw
    Ollama root suc@L421, Return the root Ollama URL for /api/chat calls.

    The OpenAI-compatible base is usually http://host:11434/v1, but the native
    Ollama chat endpoint lives a@L441, Call Ollama native /api/chat for page-binder answers.

    Ollama's OpenAI-compatible endpoint can return a large `reasoning` field
    and an empty `message.co@L517, /chat/completions@L430, /chat/completions@L450, /api/chat@L527, /v1/models@L1122, /v1/chat/completions@L1142, /api/trace-net/page-context-preview@L1226, /health@L1097
- Has __main__ guard.
- Signal snippets:
  - L36 `engram`: "trace_net_openwebui_page_context_bridge_v1" VERSION = "1.0.0" DEFAULT_MODEL_ID = "trace-net-page-context-v3-bridge" DEFAULT_UPSTREAM_MODEL = "trace-net-gemma4-engram-e2e-v3" DEFAULT_NATIVE_LLM_BASE_URL = "http://127.0.0.1:11434/v1" DEFAULT_NATIVE_LLM_MODEL = "gemma4:26b" DEFAULT_NATIVE_NUM_CTX = 8192 DEFAULT_NATIVE_MAX_TOKENS = 1200 _PAGE_PHRASE_RE = re.compile( r"\bpages?\s+(?P<body>(?:p0*\d{1,6}|\d{1,4}|and|to|through|,|\s|-)+)", re.IGNORECASE, ) _P_ID_RE = re.compile(r"\bp0*(?P<num>\d{1,6})\b", re.IGNO
  - L5 `context_pack`: e is intentionally a thin adapter. It does not replace the current V3 bridge or Gemma answer runner. Instead, it detects page-centered questions, builds a page_context_pack_v3 binder, and injects that binder into OpenAI-style chat messages before forwarding to the existing V3 bridge. Safety contract: - read-only artifact access - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/summary records remain guidance unless backed by proof """ from __future__ im
  - L869 `context pack`: page records, but the response must stay within the source-trace limits of the binder.") lines.append("") lines.append("Evidence") lines.append(f"Context pack quality: {pack.get('quality_status') or meta.get('context_pack_quality_status')}") if isinstance(summary, Mapping): lines.append( "Counts: " f"selected_page_count={summary.get('selected_page_count', 0)}, " f"source_trace_ready_page_count={summary.get('source_trace_ready_page_count', 0)}, "
  - L5 `binder`: ly a thin adapter. It does not replace the current V3 bridge or Gemma answer runner. Instead, it detects page-centered questions, builds a page_context_pack_v3 binder, and injects that binder into OpenAI-style chat messages before forwarding to the existing V3 bridge. Safety contract: - read-only artifact access - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/summary records remain guidance unless backed by proof """ from __future__ import annotations
  - L13 `proof`: - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/summary records remain guidance unless backed by proof """ from __future__ import annotations import argparse import json import os import re import subprocess import sys import time import urllib.error import urllib.parse import urllib.request from dataclasses import asdict, dataclass from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer from pathlib import Path from typing import Any, Dic

### `tiff/trace_net_page_context_pack_v3.py`
- Score: `269`
- Categories: `context_pack, engram, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Page Context Pack v3.3. Builds a source-bounded page context pack for page-specific and complex engineering questions. The pack is intentionally a *binder*, not a canned answer: it gives the LLM proof, guidance, source locators, and route-aware reasoning tasks so the model can synthesize cautiously for harder questions. Safety contract: - read-only inputs - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/page-summary records 
- Classes: PageContextRecord@L430 methods=['finalize', 'to_dict']; PageContextIndex@L490 methods=['__init__', 'ensure_page', 'add_aliases', 'resolve']
- Functions: load_json(path, default)@L74; write_json(path, payload)@L86; _norm_text(value)@L92; _first_present(record, keys)@L98; _first_text(record, keys)@L106; _truthy(value)@L130; _looks_page_or_evidence_like(record)@L140; _as_records(payload)@L181; normalize_page_id(value)@L267; page_number_from_any(value)@L279; page_key(record)@L304; page_aliases(record)@L317; _dedupe_dicts(items)@L354; _record_can_prove(record)@L369; _route_evidence_priority(route)@L402; _page_reasoning_tasks(page)@L413; _attach_source_locators(page, record)@L552; _make_compact(record)@L573
- Signal snippets:
  - L847 `engram`: approval, installation safety, or procurement authority without explicit source proof.", "Do not cite unrelated records.", "Do not use Engram, vector hits, graph neighbors, page summaries, route guidance, or visual summaries as factual proof unless a proof record backs them.", ], "proof_ready_pages": proof_ready_pages, "guidance_only_pages": guidance_only_pages, "route_awareness": { "table_pages": [r["page_id"] for r in selected_records if "table"
  - L859 `context_pack`: x in ("image", "visual", "diagram"))], }, "answer_sections": ["Answer", "Evidence", "Engineering confidence", "Limits"], } def build_page_context_pack_v3( *, question: str | None = None, requested_pages: Iterable[str | int] | None = None, route_manifest: Any = None, graph_export: Any = None, ocr_records: Any = None, table_evidence: Any = None, exact_part_records: Any = None, visual_summaries: Any = None, vector_hits: Any = None, max_pages: int = 8, )
  - L1 `context pack`: """TRACE-Net Page Context Pack v3.3. Builds a source-bounded page context pack for page-specific and complex engineering questions. The pack is intentionally a *binder*, not a canned answer: it gives the LLM proof, guidance, source locators, and route-aware reasoning tasks so the model can synthesize cautiously for harder questions. Safety contract: - read-only inputs - no
  - L4 `binder`: TRACE-Net Page Context Pack v3.3. Builds a source-bounded page context pack for page-specific and complex engineering questions. The pack is intentionally a *binder*, not a canned answer: it gives the LLM proof, guidance, source locators, and route-aware reasoning tasks so the model can synthesize cautiously for harder questions. Safety contract: - read-only inputs - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/page-summary records are guidance unle
  - L5 `proof`: rce-bounded page context pack for page-specific and complex engineering questions. The pack is intentionally a *binder*, not a canned answer: it gives the LLM proof, guidance, source locators, and route-aware reasoning tasks so the model can synthesize cautiously for harder questions. Safety contract: - read-only inputs - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/page-summary records are guidance unless backed by proof """ from __future__ import

### `tiff/trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py`
- Score: `265`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering WebUI Answer Server v1.3 + Self-RAG/CRAG bridge v1. This module wraps the active v1.3 WebUI answer server with a live pre-answer engineering-brain bridge: question -> Self-RAG/CRAG bridge -> v1.3 answer composer -> trace checklist It intentionally preserves the v1.3 answer behavior and model id, while adding an auditable preflight gate that proves query planning, context pack building, Self-RAG, and CRAG evaluation ran for the request.
- Classes: BridgeConfig@L70 methods=[]; TraceNetWebUIHandlerV13BridgeV1@L652 methods=['_json_response', '_read_body_json', 'do_GET', 'do_POST']; TraceNetHTTPServerV13BridgeV1@L732 methods=['__init__']
- Functions: _as_path(value)@L89; _safe_slug(text)@L95; _new_request_dir(base_dir, question)@L101; _summary(payload)@L106; _statuses(payload)@L111; _bridge_passed(payload)@L116; _ensure_bridge_stage_dirs(target_dir)@L131; _patch_stage_writer_parent_dirs_for_in_process_bridge()@L153; _bridge_status_payload(question, bridge_payload)@L195; merge_bridge_trace(answer_record, bridge_payload)@L241; bridge_failure_record(question)@L256; _bridge_cli_command(question, config, target_dir)@L298; _run_bridge_cli_fallback(question, config, target_dir)@L331; run_bridge_preflight(question, config)@L358; answer_question_with_bridge_v1()@L396; _bridge_config_from_args(args)@L435; _add_bridge_args(parser)@L454; build_manifest_bridge_v1()@L469
- CLI args: --kernel, --bridge-output-dir, --table-exact-search-adapter, --leiden-communities, --image-visual-observer, --webui-visual-context-bridge, --max-records-per-slot, --min-high-signal-capsules, --min-evidence-strength-score, --disable-self-rag-crag-bridge, --allow-answer-if-bridge-fails, --disable-bridge-cli-fallback, --output-dir, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff, --sample-question, --quality, --report-path, --write-json, --min-page-records, --min-gated-drafts, --require-llm-model, --require-bridge-preflight, --require-self-rag-used, --require-crag-evaluated, --require-webui-visual-context-bridge-used, --min-visual-context-cards
- Routes: /health@L563, /v1/models@L563, /v1/chat/completions@L563, /health@L671, /v1/models@L692, /api/models@L692, /v1/chat/completions@L698, /api/chat/completions@L698
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1_3 import DEFAULT_FINAL_GATE, DEFAULT_FISHNET, DEFAULT_PAGE_CONTEXT, DEFAULT_ROUTE_HANDOFF, DEFAULT_RUNNER, LLMConfig, MODEL_ID, _add_llm_args, _llm_config_from_args, _read_json, _write_json, _write_jsonl, answer_question_v13, load_gated_drafts, load_page_index; from tiff.trace_net_webui_self_rag_crag_bridge_v1 import REPORT_NAME, build_webui_self_rag_crag_bridge
- Has __main__ guard.
- Signal snippets:
  - L42 `self_rag`: _from_args, _read_json, _write_json, _write_jsonl, answer_question_v13, load_gated_drafts, load_page_index, ) from tiff.trace_net_webui_self_rag_crag_bridge_v1 import ( REPORT_NAME as BRIDGE_REPORT_NAME, build_webui_self_rag_crag_bridge, ) MODULE_VERSION = "trace_net_engineering_webui_answer_server_v1_3_bridge_v1" REPORT_NAME = "trace_net_engineering_webui_answer_server_v1_3_bridge_v1.json" DEFAULT_KERNEL = Path("local_data/organization/trace_net/engineering_reasoning_kernel/trace_
  - L1 `self-rag`: """TRACE-Net Engineering WebUI Answer Server v1.3 + Self-RAG/CRAG bridge v1. This module wraps the active v1.3 WebUI answer server with a live pre-answer engineering-brain bridge: question -> Self-RAG/CRAG bridge -> v1.3 answer composer -> trace checklist It intentionally preserves the v1.3 answer behavior and model id, while adding an auditable preflight gate that proves query planning, context pack build
  - L1 `crag`: """TRACE-Net Engineering WebUI Answer Server v1.3 + Self-RAG/CRAG bridge v1. This module wraps the active v1.3 WebUI answer server with a live pre-answer engineering-brain bridge: question -> Self-RAG/CRAG bridge -> v1.3 answer composer -> trace checklist It intentionally preserves the v1.3 answer behavior and model id, while adding an auditable preflight gate that proves query planning, context pack building, Self
  - L122 `context_pack`: = _statuses(payload) return ( payload.get("quality_status") == "PASS" and statuses.get("query_planner") == "used" and statuses.get("context_pack_builder") == "used" and statuses.get("self_rag") == "used" and statuses.get("crag_retry") in {"used", "skipped_not_needed"} and int(summary.get("answer_permission_count") or 0) == 0 and int(summary.get("source_truth_mutation_allowed_count") or 0) == 0 ) def _ensure_bridge_stage_dirs(target_dir: Path) -> Non
  - L9 `context pack`: oser -> trace checklist It intentionally preserves the v1.3 answer behavior and model id, while adding an auditable preflight gate that proves query planning, context pack building, Self-RAG, and CRAG evaluation ran for the request. """ from __future__ import annotations import argparse import json import re import subprocess import sys import time from dataclasses import dataclass from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer from pathlib import Path from typing import Any, Dict, List, Mapp

### `scripts/build_trace_net_engineering_engram_crag_repair_v1.py`
- Score: `257`
- Categories: `crag, engram, page, server`
- Tiff imports: from tiff.trace_net_engineering_engram_crag_repair_v1 import main
- Has __main__ guard.
- Signal snippets:
  - L8 `engram`: rt Path import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_crag_repair_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L8 `crag`: import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_crag_repair_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L8 `repair`: rt sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_crag_repair_v1 import main if __name__ == "__main__": raise SystemExit(main())

### `scripts/build_trace_net_engineering_engram_self_rag_critic_v1.py`
- Score: `257`
- Categories: `engram, page, self_rag, server`
- Tiff imports: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main
- Has __main__ guard.
- Signal snippets:
  - L9 `engram`: athlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L9 `self_rag`: import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L9 `critic`: th ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main if __name__ == "__main__": raise SystemExit(main())

### `scripts/check_trace_net_engineering_engram_self_rag_critic_v1.py`
- Score: `257`
- Categories: `engram, page, self_rag, server`
- Tiff imports: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import check_main
- Has __main__ guard.
- Signal snippets:
  - L9 `engram`: athlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_self_rag_critic_v1 import check_main if __name__ == "__main__": raise SystemExit(check_main())
  - L9 `self_rag`: import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_self_rag_critic_v1 import check_main if __name__ == "__main__": raise SystemExit(check_main())
  - L9 `critic`: th ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_self_rag_critic_v1 import check_main if __name__ == "__main__": raise SystemExit(check_main())

### `scripts/check_trace_net_page_context_pack_v3_quality.py`
- Score: `257`
- Categories: `context_pack, page, safety, server`
- Doc: Quality gate for TRACE-Net Page Context Pack v3.
- Functions: parse_args()@L17; main()@L30
- CLI args: --input, --output, --min-pages, --min-guidance-records, --min-source-trace-ready-pages, --min-source-locators, --require-no-answer-permission, --require-reasoning-work-order
- Tiff imports: from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json
- Has __main__ guard.
- Signal snippets:
  - L14 `context_pack`: import sys REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json def parse_args() -> argparse.Namespace: parser = argparse.ArgumentParser(description="Check TRACE-Net page context pack v3 quality.") parser.add_argument("--input", required=True) parser.add_argument("--output", default=None) parser.add_argument("--min-pages",
  - L2 `context pack`: #!/usr/bin/env python3 """Quality gate for TRACE-Net Page Context Pack v3.""" from __future__ import annotations import argparse from pathlib import Path import sys REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json def parse_args() ->
  - L22 `guidance`: t", required=True) parser.add_argument("--output", default=None) parser.add_argument("--min-pages", type=int, default=1) parser.add_argument("--min-guidance-records", type=int, default=0) parser.add_argument("--min-source-trace-ready-pages", type=int, default=0) parser.add_argument("--min-source-locators", type=int, default=0) parser.add_argument("--require-no-answer-permission", action="store_true") parser.add_argument("--require-reasoning-work-order", action="store_true") return pa
  - L14 `page_context`: Path import sys REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json def parse_args() -> argparse.Namespace: parser = argparse.ArgumentParser(description="Check TRACE-Net page context pack v3 quality.") parser.add_argument("--input", required=True) parser.add_argument("--output", default=None) parser.add_argument("--min-pag
  - L36 `answer_permission`: rgs() pack = load_json(args.input, {}) quality = check_page_context_pack_v3_quality( pack, min_pages=args.min_pages, require_no_answer_permission=args.require_no_answer_permission, require_reasoning_work_order=args.require_reasoning_work_order, min_guidance_records=args.min_guidance_records, min_source_trace_ready_pages=args.min_source_trace_ready_pages, min_source_locators=args.min_source_locators, ) if args.output: write_json(args.out

### `scripts/build_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Score: `254`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Functions: main()@L14
- CLI args: --relationship-router-hardening, --relationship-final-gate-hardener, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --graph-signal-artifact, --output-dir, --host, --port, --llm-mode, --llm-model, --include-standard-demo-queries, --min-sample-queries, --min-sample-successes, --min-relationship-final-gate-applied, --min-relationship-records, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import build_report
- Has __main__ guard.
- Signal snippets:
  - L67 `repair`: [ "sample_query_count", "sample_success_count", "relationship_final_gate_applied_count", "relationship_record_count", "repaired_relationship_sample_count", "post_gate_issue_count", "exact_search_document_count", "page_context_v2_page_count", "graph_has_nomenclature_page_count", "answer_permission_count", "source_truth_mutation_allowed_count", "base_url_windows", "base_url_open_webui_docker", "report_path
  - L11 `final_gate`: le__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) import argparse from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import build_report def main() -> None: parser = argparse.ArgumentParser(description="Build TRACE-Net live relationship final-gated endpoint v31 artifact.") parser.add_argument("--relationship-router-hardening", required=True, type=Path) parser.add_argument("--relationship-final-gate-hardener", required=True, type=Path)
  - L25 `ollama`: parser.add_argument("--host", default="127.0.0.1") parser.add_argument("--port", type=int, default=8026) parser.add_argument("--llm-mode", default="ollama") parser.add_argument("--llm-model", default="gemma4:26b") parser.add_argument("--include-standard-demo-queries", action="store_true") parser.add_argument("--min-sample-queries", type=int, default=0) parser.add_argument("--min-sample-successes", type=int, default=0) parser.add_argument("--min-relationship-final-gate-applied", type=
  - L43 `page_context`: ng, relationship_final_gate_hardener=args.relationship_final_gate_hardener, table_exact_search_adapter=args.table_exact_search_adapter, page_context_v2=args.page_context_v2, leiden_communities=args.leiden_communities, graph_signal_paths=args.graph_signal_artifact or None, output_dir=args.output_dir, include_standard_demo_queries=args.include_standard_demo_queries, min_sample_queries=args.min_sample_queries, min_sample_successes=args.min_sample_
  - L54 `source_truth_mutation_allowed`: ip_records, max_post_gate_issue_count=args.max_post_gate_issue_count, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, quality=args.quality, ) print("TRACE-Net E2E Live Relationship Final-Gated Endpoint v31") print(f" Status: {report['status']}") print(f" Quality status: {report['quality_status']}") for key

### `scripts/serve_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Score: `253`
- Categories: `final_gate, graph_vector, page, server, table_visual_ocr, webui`
- Classes: Handler@L37 methods=['do_OPTIONS', 'do_GET', 'do_POST', 'log_message']
- Functions: _send_json(handler, status, payload)@L24; make_handler(state, model_id)@L36; main()@L90; do_OPTIONS(self)@L38; do_GET(self)@L41; do_POST(self)@L69; log_message(self, format)@L84
- CLI args: --relationship-router-hardening, --relationship-final-gate-hardener, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --graph-signal-artifact, --host, --port, --model-id, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --relationship-mode
- Routes: /health@L42, /v1/models@L60, /v1/chat/completions@L70
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import MODEL_ID, SAFETY_CONTRACT, RuntimeState, _extract_user_text, make_chat_completion_response
- Has __main__ guard.
- Signal snippets:
  - L15 `final_gate`: se import json from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer from typing import Any, Dict from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import ( MODEL_ID, SAFETY_CONTRACT, RuntimeState, _extract_user_text, make_chat_completion_response, ) def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None: body = json.dumps(payload, indent=2).encode("utf-8") handler.send_response(status) handler.
  - L70 `chat/completions`: _send_json(self, 404, {"error": f"Unknown route: {self.path}"}) def do_POST(self) -> None: # noqa: N802 if self.path != "/v1/chat/completions": _send_json(self, 404, {"error": f"Unknown route: {self.path}"}) return length = int(self.headers.get("Content-Length", "0")) raw = self.rfile.read(length).decode("utf-8") if length else "{}" try: payload = json.loads(raw) except json.JSON
  - L102 `ollama`: # Accepted for CLI compatibility; v31 can wrap a router that has already made the LLM/deterministic decision. parser.add_argument("--llm-mode", default="ollama") parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1") parser.add_argument("--llm-model", default="gemma4:26b") parser.add_argument("--llm-api-key", default="ollama") parser.add_argument("--request-timeout", type=int, default=240) parser.add_argument("--relationship-mode", default="guarded") args = p
  - L54 `page_context`: et("quality_status"), "exact_search_document_count": state.router_report.get("exact_search_document_count"), "page_context_v2_page_count": state.router_report.get("page_context_v2_page_count"), "graph_has_nomenclature_page_count": state.router_report.get("graph_has_nomenclature_page_count"), "safety": dict(SAFETY_CONTRACT, response_is_final_gated=True), }, ) retu

### `scripts/build_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import main
- Has __main__ guard.
- Signal snippets:
  - L1 `engram`: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L1 `answer_runner`: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import main if __name__ == "__main__": raise SystemExit(main())

### `scripts/build_trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import main
- Has __main__ guard.
- Signal snippets:
  - L10 `engram`: athlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L10 `answer_runner`: import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import main if __name__ == "__main__": raise SystemExit(main())

### `scripts/build_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import main
- Has __main__ guard.
- Signal snippets:
  - L9 `engram`: rt Path import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import main if __name__ == "__main__": raise SystemExit(main())
  - L9 `answer_runner`: import sys ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import main if __name__ == "__main__": raise SystemExit(main())

### `scripts/check_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import check_main
- Has __main__ guard.
- Signal snippets:
  - L1 `engram`: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import check_main if __name__ == "__main__": raise SystemExit(check_main())
  - L1 `answer_runner`: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import check_main if __name__ == "__main__": raise SystemExit(check_main())

### `tiff/trace_net_engineering_engram_core_v1.py`
- Score: `252`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _read_json(path)@L25; _write_json(path, data)@L30; _write_csv(path, rows)@L36; _csv_value(v)@L56; _as_list(v)@L64; _default_memory_atoms()@L72; _summarize_smoke(path)@L234; _eval_memory_atoms(eval_summaries)@L256; _slug(text, max_len)@L297; _quality_gate(atoms, eval_summaries)@L303; build_engram_core(output_dir, smoke_test, min_engram_atoms, min_policy_traits, min_memory_types, max_unsafe, max_answer_permission, max_source_truth_mutation_allowed)@L340; check_engram_core(engram_core, output, min_engram_atoms, min_policy_traits, min_memory_types, max_unsafe, max_answer_permission, max_source_truth_mutation_allowed)@L501; _build_parser()@L554; main_build(argv)@L570; _check_parser()@L596; main_check(argv)@L611
- CLI args: --output-dir, --smoke-test, --min-engram-atoms, --min-policy-traits, --min-memory-types, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --require-quality-pass, --require-eval-source-pass, --engram-core, --output, --min-engram-atoms, --min-policy-traits, --min-memory-types, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --require-quality-pass
- Has __main__ guard.
- Signal snippets:
  - L10 `engram`: collections import Counter from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence MODULE = "trace_net_engineering_engram_core_v1" VERSION = "v1" SAFETY_ZERO_FIELDS = [ "answer_permission_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count", "opensearch_upload_attempt_count", "write_attempt_count", "unsafe_record_count", ] def _read_json(path: Any)
  - L206 `self_rag`: dows.", "source": "H14B/H14C path hardening", "status": "active", }, { "engram_id": "critic_answer_behavior_self_rag_v1", "memory_type": "critic_trait", "priority": "high", "trait": "self_rag_behavior_check", "triggers": ["answer critique", "Self-RAG", "unsupported claim", "intent mismatch"], "trigger_text": "Self-RAG answer behavior critique", "rule": "Self-RAG should check whether the draft
  - L210 `self-rag`: "memory_type": "critic_trait", "priority": "high", "trait": "self_rag_behavior_check", "triggers": ["answer critique", "Self-RAG", "unsupported claim", "intent mismatch"], "trigger_text": "Self-RAG answer behavior critique", "rule": "Self-RAG should check whether the draft obeys source-trace boundaries, answers the actual intent, cites claims, and avoids over/under-refusal.", "good_behavior": "Critique answers for evidence support and behav
  - L219 `crag`: tent failure.", "source": "H10 semantic answer quality eval", "status": "active", }, { "engram_id": "repair_crag_engram_repair_v1", "memory_type": "repair_trait", "priority": "high", "trait": "crag_repair_reflex", "triggers": ["CRAG", "repair", "weak answer", "retry"], "trigger_text": "CRAG repair | weak answer retry", "rule": "CRAG should retrieve relevant failure/repair engrams and regenerat
  - L206 `critic`: ing written/read on Windows.", "source": "H14B/H14C path hardening", "status": "active", }, { "engram_id": "critic_answer_behavior_self_rag_v1", "memory_type": "critic_trait", "priority": "high", "trait": "self_rag_behavior_check", "triggers": ["answer critique", "Self-RAG", "unsupported claim", "intent mismatch"], "trigger_text": "Self-RAG answer behavior critique", "rule": "Self-RAG should c

### `tiff/trace_net_engineering_engram_postgres_feedback_ledger_v1.py`
- Score: `252`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _read_json(path)@L64; _write_json(path, data)@L68; _write_jsonl(path, records)@L73; _stable_id(prefix)@L78; _load_jsonl(path)@L86; _records_by_id(records, key)@L100; _answer_records(answer_smoke)@L104; _critic_records(critic)@L108; _crag_records(crag)@L112; _rating_for(answer, critic, crag)@L116; _normalize_feedback_records(records)@L152; build_feedback_ledger_manifest(answer_smoke, critic, crag_repair, output_dir, feedback_jsonl, postgres_dsn, enable_live_postgres_write, min_feedback_records)@L180; _count(records, key)@L361; check_feedback_ledger_manifest(ledger, min_feedback_records, min_candidate_records, require_quality_pass, require_no_answer_permission, max_unsafe, max_write_attempts)@L370; build_arg_parser()@L406; main(argv)@L426
- CLI args: --answer-smoke, --critic, --crag-repair, --output-dir, --feedback-jsonl, --postgres-dsn, --enable-live-postgres-write, --min-feedback-records, --min-candidate-records, --require-source-quality-pass, --require-critic-quality-pass, --require-crag-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L10 `engram`: mport hashlib import json from dataclasses import dataclass from pathlib import Path from typing import Any, Iterable, Mapping MODULE = "trace_net_engineering_engram_postgres_feedback_ledger_v1" VERSION = "v1" MEMORY_LAYERS = {"working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory"} SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_write_attempt": False, "qdrant_
  - L217 `self_rag`: _text") or "") feedback_records.append({ "feedback_id": feedback_id, "source_question_id": qid, "feedback_source": "self_rag_crag_eval", "rating": rating, "explanation": explanation, "source_grade": str(a.get("grade") or "UNKNOWN"), "critic_status": str((c or {}).get("critic_status") or "UNKNOWN"), "crag_status": str((cr or {}).get("crag_status") or "NO_REPAIR"), "recommended_memory_layer": layer,
  - L142 `self-rag`: "critic_memory", "critic recommended review/repair; retrieve this feedback before regenerating similar answers.", "repair recommended; self-rag review; crag repair", ) return ( "neutral_review", "episodic_memory", "record preserved as evaluation memory; do not treat as proof.", "evaluation memory; behavior guidance", ) def _normalize_feedback_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]: out: list[dict[str, Any]]
  - L37 `crag`: d TEXT NOT NULL, feedback_source TEXT NOT NULL, rating TEXT NOT NULL, explanation TEXT NOT NULL, source_grade TEXT, critic_status TEXT, crag_status TEXT, recommended_memory_layer TEXT NOT NULL, recommended_memory_type TEXT NOT NULL, proof_role TEXT NOT NULL DEFAULT 'guidance_only', answer_permission BOOLEAN NOT NULL DEFAULT FALSE, source_truth_mutation_allowed BOOLEAN NOT NULL DEFAULT FALSE, payload_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(
  - L13 `critic`: ram_postgres_feedback_ledger_v1" VERSION = "v1" MEMORY_LAYERS = {"working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory"} SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_write_attempt": False, "qdrant_read_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attempt": False, } SCHEMA_SQL = """ -- TRACE-Net E

### `tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py`
- Score: `252`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net H32 Engineering Engram unified runtime gate v1. This module is intentionally artifact-first. It joins the already-built Engram runtime pieces into one inspectable targeted gate: - H27E answer smoke records with retrieved Engram overlays applied. - H28 Self-RAG critic records. - H29 CRAG repair records. - H30 Qdrant/vector adapter records. - H31 Postgres feedback ledger records. - Optional graph-route guidance manifest, when available. It does not perform LLM calls, graph traversal, Qdr
- Functions: _read_json(path)@L59; _write_json(path, data)@L64; _write_jsonl(path, rows)@L69; _summary(manifest)@L76; _quality(manifest)@L81; _records(manifest)@L85; _by_key(rows, key)@L93; _feedback_by_question(rows)@L102; _candidate_by_feedback(rows)@L111; _vector_queries_by_id(rows)@L120; _source_count(manifest, key)@L124; _combine_source_safety()@L131; _hash_record_id()@L144; _safe_preview(text, n)@L149; _graph_guidance_for_question(qid, graph_manifest)@L154; _runtime_status(answer, critic, crag)@L172; build_unified_runtime_gate(answer_smoke, critic, crag_repair, qdrant_adapter, feedback_ledger, output_dir, graph_route_manifest, question_ids)@L187; check_unified_runtime_gate(unified_runtime_gate, min_runtime_records, min_pass_or_expected, require_quality_pass, require_no_answer_permission, require_connections, max_unsafe, max_write_attempts)@L422
- CLI args: --answer-smoke, --critic, --crag-repair, --qdrant-adapter, --feedback-ledger, --graph-route-manifest, --output-dir, --question-ids, --min-runtime-records, --min-pass-or-expected, --require-answer-quality-pass, --require-critic-quality-pass, --require-crag-quality-pass, --require-qdrant-quality-pass, --require-feedback-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L2 `engram`: """TRACE-Net H32 Engineering Engram unified runtime gate v1. This module is intentionally artifact-first. It joins the already-built Engram runtime pieces into one inspectable targeted gate: - H27E answer smoke records with retrieved Engram overlays applied. - H28 Self-RAG critic records. - H29 CRAG repair records. - H30 Qdrant/vector adapter records. - H31 Postgres feedback ledger re
  - L273 `self_rag`: context", "apply_retrieved_engram_overlay_behavior_guidance", "draft_answer_with_proof_context_citations", "run_self_rag_engram_critic", "run_crag_repair_only_if_critic_recommends_repair", "emit_feedback_ledger_and_memory_candidates_for_human_review", "consult_graph_route_guidance_when_manifest_supplied_without_using_graph_as_proof", ], "proof_boundary": "Engram, feedback, graph, and vector memori
  - L8 `self-rag`: It joins the already-built Engram runtime pieces into one inspectable targeted gate: - H27E answer smoke records with retrieved Engram overlays applied. - H28 Self-RAG critic records. - H29 CRAG repair records. - H30 Qdrant/vector adapter records. - H31 Postgres feedback ledger records. - Optional graph-route guidance manifest, when available. It does not perform LLM calls, graph traversal, Qdrant IO, Postgres IO, OpenSearch IO, or source-truth mutation. It proves runtime wiring readiness. """ from __future__ im
  - L9 `crag`: am runtime pieces into one inspectable targeted gate: - H27E answer smoke records with retrieved Engram overlays applied. - H28 Self-RAG critic records. - H29 CRAG repair records. - H30 Qdrant/vector adapter records. - H31 Postgres feedback ledger records. - Optional graph-route guidance manifest, when available. It does not perform LLM calls, graph traversal, Qdrant IO, Postgres IO, OpenSearch IO, or source-truth mutation. It proves runtime wiring readiness. """ from __future__ import annotations import argpar
  - L8 `critic`: the already-built Engram runtime pieces into one inspectable targeted gate: - H27E answer smoke records with retrieved Engram overlays applied. - H28 Self-RAG critic records. - H29 CRAG repair records. - H30 Qdrant/vector adapter records. - H31 Postgres feedback ledger records. - Optional graph-route guidance manifest, when available. It does not perform LLM calls, graph traversal, Qdrant IO, Postgres IO, OpenSearch IO, or source-truth mutation. It proves runtime wiring readiness. """ from __future__ import anno

### `tiff/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py`
- Score: `251`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server`
- Functions: _read_json(path)@L46; _write_json(path, data)@L50; _write_jsonl(path, records)@L55; _norm(s)@L62; _compact_text(text, max_chars)@L66; build_llm_prompt(record, max_prompt_chars)@L74; call_ollama()@L98; deterministic_behavior_answer(record)@L129; _is_negated_window(text, start)@L174; detect_unsupported_claims(answer_text)@L191; grade_h22_answer(answer_text, unsupported_claims)@L203; _select_records(prompt_smoke, max_queries)@L223; build_prompt_retrieval_llm_smoke()@L230; check_prompt_retrieval_llm_smoke()@L425; build_arg_parser()@L470; main(argv)@L490
- CLI args: --prompt-smoke, --output-dir, --llm-mode, --ollama-model, --ollama-url, --timeout-seconds, --max-queries, --max-prompt-chars, --min-queries, --min-llm-answered, --min-good-answers, --max-bad-answers, --max-unsupported-claims, --max-unsafe, --max-write-attempts
- Routes: http://127.0.0.1:11434/api/generate@L236, http://127.0.0.1:11434/api/generate@L476
- Has __main__ guard.
- Signal snippets:
  - L12 `engram`: sses import dataclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence MODULE = "trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1" VERSION = "v1" SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_read_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_att
  - L142 `critic`: limits = "No current proof_context was provided; retrieved Engram guidance and summaries are not proof." elif task_type in {"route_explanation", "critic_repair"}: answer = "The retrieved Engram guidance should shape behavior only." limits = "Manual claims still require current proof_context citations before they can be treated as proven." else: answer = "Not proven / not source-trace-ready from this H22 prompt smoke." limits = "Retrieved Engram guidance is beha
  - L142 `repair`: limits = "No current proof_context was provided; retrieved Engram guidance and summaries are not proof." elif task_type in {"route_explanation", "critic_repair"}: answer = "The retrieved Engram guidance should shape behavior only." limits = "Manual claims still require current proof_context citations before they can be treated as proven." else: answer = "Not proven / not source-trace-ready from this H22 prompt smoke." limits = "Retrieved Engram guidance is behavior-on
  - L25 `proof`: opensearch_write_attempt": False, "opensearch_upload_attempt": False, "write_attempt": False, "live_qdrant_io_attempted": False, "engram_is_proof": False, } DEFAULT_SYNTHETIC_PROOF_CONTEXT = ( "No current proof_context is provided in this H22 prompt-retrieval smoke. " "Retrieved Engram memory is behavior guidance only and cannot prove manual facts." ) DEFAULT_RESPONSE_INSTRUCTIONS = """Return a concise TRACE-Net engineering answer with these sections: Answer Evidence Enginee
  - L30 `guidance`: DEFAULT_SYNTHETIC_PROOF_CONTEXT = ( "No current proof_context is provided in this H22 prompt-retrieval smoke. " "Retrieved Engram memory is behavior guidance only and cannot prove manual facts." ) DEFAULT_RESPONSE_INSTRUCTIONS = """Return a concise TRACE-Net engineering answer with these sections: Answer Evidence Engineering confidence Limits Rules: - Treat the retrieved Engram guidance as behavior guidance only, not source evidence. - Do not claim interchangeability, approved replacement, f

### `tiff/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Score: `249`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24. This module serves already-final-gated live Gemma answers through an OpenAI-compatible local endpoint shape. It does not call the LLM. It does not perform retrieval. It reads v23 final gate artifacts and exposes only answers that already passed the final gate.
- Classes: TraceNetV24Handler@L429 methods=['_send_json', 'log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: read_json(path)@L27; write_json(path, payload)@L35; write_jsonl(path, rows)@L40; normalize_query(query)@L47; citation_like_count(text)@L51; _to_bool(value)@L55; _to_int(value, default)@L59; get_final_gate_records(data)@L66; record_query(record)@L74; record_final_answer(record)@L78; is_final_gate_pass(record)@L82; final_answer_has_cap_disclosure(record)@L97; final_answer_has_source_truth_citation(record)@L102; final_answer_ready_record(record, idx)@L106; build_endpoint_state(live_llm_final_gate_path, host, port, model_id)@L142; evaluate_quality(state, min_final_gates, min_ready_final_answers, min_endpoint_routes, min_final_answers_with_source_truth_citations, min_cap_disclosures_in_final_answers, max_unsupported_claim_count, max_final_non_direct_citation_marker_count)@L212; attach_quality(state, quality_status, quality_checks)@L257; render_markdown_report(state)@L264
- Routes: /health@L24, /v1/models@L24, /v1/chat/completions@L24, /v1/models@L453, /v1/chat/completions@L459, /health@L450
- Signal snippets:
  - L20 `repair`: dpoint_v24" VERSION = "v24" MODEL_ID = "trace-net-e2e-live-final-gated-gemma-v24" STATUS_READY = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_READY" STATUS_NEEDS_REPAIR = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"] def read_json(path: Path) -> Dict[str, Any]: with path.open("r", encoding="utf-8") as f: data = json.load(f) if not isinstance(data, dict): raise Val
  - L90 `proof`: 0) > 0: return False if _to_int(record.get("final_non_direct_citation_marker_count"), 0) > 0: return False if _to_int(record.get("graph_proof_authority_violation_count"), 0) > 0: return False if _to_int(record.get("summary_proof_authority_violation_count"), 0) > 0: return False return bool(record_final_answer(record).strip()) def final_answer_has_cap_disclosure(record: Mapping[str, Any]) -> bool: text = record_final_answer(record).lower() return "results wer
  - L185 `guidance`: time": False, "reads_v23_final_gate_artifact": True, "source_truth_evidence_required_for_final_claims": True, "graph_leiden_guidance_only": True, "v2_summaries_guidance_only": True, "nearby_context_not_direct_proof": True, "raw_5tb_scan_at_query_time": False, "graph_rebuild_at_query_time": False, "source_truth_mutation_allowed": False, "answer_permission": False, "can_answer_directly": False,
  - L16 `final_gate`: PRequestHandler, HTTPServer from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple MODULE = "trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24" VERSION = "v24" MODEL_ID = "trace-net-e2e-live-final-gated-gemma-v24" STATUS_READY = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_READY" STATUS_NEEDS_REPAIR = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions",
  - L24 `chat/completions`: EPAIR = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"] def read_json(path: Path) -> Dict[str, Any]: with path.open("r", encoding="utf-8") as f: data = json.load(f) if not isinstance(data, dict): raise ValueError(f"Expected JSON object at {path}") return data def write_json(path: Path, payload: Mapping[str, Any]) -> None: path.parent.mkdir(parents=True,

### `tiff/trace_net_engineering_webui_answer_server_v1.py`
- Score: `249`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering WebUI Answer Server v1.2. OpenAI-compatible local server for Open WebUI. v1.2 quality patch: - retries Gemma4 once when the first LLM response is empty - cleans OCR/fishnet/router debug text before prompts and fallback output - only uses gated lookup when requested seed part matches the gated draft - adds visible source notes to answers - preserves exact lookup, random page summary, and fallback artifact search Safety: - no Postgres/Qdrant/OpenSearch writes - no source-trut
- Classes: LLMConfig@L44 methods=['enabled']; TraceNetWebUIHandler@L360 methods=['_json_response', '_read_body_json', 'do_GET', 'do_POST']; TraceNetHTTPServer@L386 methods=['__init__']
- Functions: _read_json(path)@L57; _write_json(path, payload)@L63; _write_jsonl(path, records)@L67; _norm(text)@L72; _lower(text)@L75; _path(path_text)@L78; _part_numbers(text)@L81; _clean_trace_text(text)@L84; _flatten_strings(value)@L101; _records_from_payload(payload)@L118; _page_id(record, index)@L128; _page_num(record, index)@L133; _route(record)@L141; load_page_index()@L146; _read_gated_draft_text(runner_record)@L167; load_gated_drafts()@L174; _match_score(query, candidate)@L187; _choose_random_page(pages, question)@L195
- CLI args: --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --llm-temperature, --llm-max-tokens, --disable-empty-response-retry, --output-dir, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff, --sample-question, --sample-call-llm, --quality, --report-path, --write-json, --min-page-records, --min-gated-drafts, --require-ready-for-webui, --require-llm-mode, --require-llm-model, --require-retry-empty-response, --max-unsafe, --require-no-answer-permission, --require-no-retrieval-execution, --require-no-source-truth-mutation, --host
- Routes: /chat/completions@L223, /health@L337, /v1/models@L337, /v1/chat/completions@L337, /api/chat/completions@L337, /health@L368, /v1/models@L370, /api/models@L370, /v1/chat/completions@L374, /api/chat/completions@L374
- Has __main__ guard.
- Signal snippets:
  - L288 `repair`: n))) if not q_terms: return [] if q_terms & {'diagram','visual','callout'}: q_terms |= {'figure','illustrated','item','assy','assembly','view'} if 'repair' in q_terms: q_terms |= {'doubler','rivet','leg','lateral','epoxy'} scored = [] for page in pages: text = _lower(page.get('text') or '') if not text: continue score = sum(1 for term in q_terms if term in text) for part in _part_numbers(question): if part.lower() in text: score += 15 if score:
  - L313 `proof`: route={c.get('route')}): {_clean_trace_text(b, max_chars=550)}" for c, b in zip(citations, blocks)) + '\n\nBoundary: these are search/summarization leads, not proof of fit, replacement, safety, or engineering approval.' llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='fallback_search', citations=citations, config=llm_config) return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error
  - L37 `final_gate`: _net_engineering_webui_answer_server_v1" REPORT_NAME = "trace_net_engineering_webui_answer_server_v1.json" MODEL_ID = "trace-net-engineering-webui-v1" DEFAULT_FINAL_GATE = Path("local_data/organization/trace_net/engineering_draft_final_gate_retry_micro/trace_net_engineering_draft_final_gate_v1.json") DEFAULT_RUNNER = Path("local_data/organization/trace_net/engineering_gemma_draft_runner_retry_micro/trace_net_engineering_gemma_draft_runner_v1.json") DEFAULT_PAGE_CONTEXT = Path("local_data/organization/trace_net/pag
  - L335 `openwebui`: .enabled else None, 'retry_empty_response_enabled': llm_config.retry_empty_response, 'webui_route_count': 4, 'openai_compatible_chat_completions_route': True, 'openwebui_api_chat_completions_route': True, 'models_route': True, 'health_route': True, 'ready_for_webui': True, 'answer_permission_count': sum(1 for r in records if r.get('answer_permission')), 'can_answer_directly_count': sum(1 for r in records if r.get('can_answer_directly')), 'can_prove_claims_count': sum(1 for r in records if r.get('can_prove_claims'))
  - L223 `chat/completions`: '; '.join(parts) + '.' if parts else '' def _llm_endpoint(config: LLMConfig) -> str: base = config.base_url.rstrip('/') return base if base.endswith('/chat/completions') else f"{base}/chat/completions" def _call_openai_compatible_llm(*, config: LLMConfig, messages: Sequence[Mapping[str, str]]) -> Tuple[str, Optional[str]]: if not config.enabled: return '', 'llm_mode_off' payload = {'model': config.model, 'messages': list(messages), 'temperature': config.temperature, 'max_tokens': config.max_tokens

### `tiff/trace_net_engineering_context_crag_retry_plan_v1.py`
- Score: `247`
- Categories: `context_pack, crag, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context CRAG Retry Plan v1. Builds corrective retrieval/repackaging plans for engineering context packs that failed Self-RAG checks. v1.1: - avoids duplicate retry actions when both structured missing notes and reason strings describe the same gap - suppresses target_route="unknown" when the same missing type already has a structured routed action - adds unknown_target_route_count quality visibility Safety: - no LLM calls - no live retrieval execution - no DB/search/vector 
- Functions: _read_json(path)@L35; _write_json(path, payload)@L41; _write_jsonl(path, records)@L46; _seed_terms(record)@L53; _retry_action_for_missing()@L71; _structured_missing_keys(record)@L221; _has_structured_key_for_missing()@L235; _actions_from_record(record)@L243; _retry_priority(record, actions)@L304; build_retry_record(record, index)@L316; build_engineering_context_crag_retry_plan()@L376; _write_markdown(path, payload)@L464; check_engineering_context_crag_retry_plan_quality()@L498; main_build(argv)@L548; main_check(argv)@L565; fail_if(condition, msg)@L516
- CLI args: --self-rag-report, --output-dir, --quality, --report-path, --write-json, --require-source-self-rag-quality-pass, --min-crag-retry-plans, --min-retry-actions, --min-ready-for-crag-execution, --max-unknown-target-routes, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.
- Signal snippets:
  - L335 `self_rag`: t) return { "crag_retry_plan_version": MODULE_VERSION, "crag_retry_plan_id": f"engineering_crag_retry_plan_{index+1:04d}", "source_self_rag_record_id": record.get("self_rag_record_id"), "context_pack_id": record.get("context_pack_id"), "question_id": record.get("question_id"), "user_question": record.get("user_question"), "intent_family": record.get("intent_family"), "selected_playbook_id": record.get("selected_playbook_id"), "source_self_
  - L5 `self-rag`: """TRACE-Net Engineering Context CRAG Retry Plan v1. Builds corrective retrieval/repackaging plans for engineering context packs that failed Self-RAG checks. v1.1: - avoids duplicate retry actions when both structured missing notes and reason strings describe the same gap - suppresses target_route="unknown" when the same missing type already has a structured routed action - adds unknown_target_route_count quality visibility Safety: - no LLM calls - no live retrieval execution - no DB/search
  - L2 `crag`: """TRACE-Net Engineering Context CRAG Retry Plan v1. Builds corrective retrieval/repackaging plans for engineering context packs that failed Self-RAG checks. v1.1: - avoids duplicate retry actions when both structured missing notes and reason strings describe the same gap - suppresses target_route="unknown" when the same missing type already has a structured routed action - adds unkno
  - L264 `critic`: continue parts = reason.split(":") missing_type: Optional[str] = None route: Optional[str] = None if reason.startswith("critical_missing:") and len(parts) >= 2: missing_type = parts[1] route = None elif reason.startswith("missing_evidence:") and len(parts) >= 3: missing_type = parts[1] route = parts[2] elif reason == "exact_part_lookup_missing_exact_source_evidence": missing_type = "exact_source_evide
  - L105 `repair`: sion", "length", "inch", "inches", "mm", "cm"]), "same part family dash number variant dimension length", "IPL table dimensions repair material part number", ], "success_conditions": [ "at least one table/source record contains the seed entity or same-family candidate", "selected evidence contains a dimension/length/size term", "page_id/source_trace is present", "context pack no longer reports sou

### `tiff/trace_net_engineering_context_self_rag_check_v1.py`
- Score: `247`
- Categories: `context_pack, crag, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context Self-RAG Check v1. Scores engineering context packs before Gemma drafting. This module checks: - source-truth evidence strength - candidate-only evidence - missing evidence notes - route coverage - forbidden-claim risk - CRAG retry need - draft readiness Safety: - does not answer the user question - does not call an LLM - does not execute retrieval - does not mutate source truth - does not grant final answer permission
- Functions: _read_json(path)@L50; _write_json(path, payload)@L56; _write_jsonl(path, records)@L61; _all_capsules(pack)@L68; _missing_notes(pack)@L82; _clamp(value, lo, hi)@L87; _critical_missing_types(pack)@L91; _capsule_counts(capsules)@L107; _route_coverage(pack)@L137; _source_truth_strength(pack, counts, missing_count)@L161; _evidence_strength_score()@L179; evaluate_context_pack()@L207; _crag_retry_reasons()@L329; build_engineering_context_self_rag_check()@L355; _write_markdown(path, payload)@L451; check_engineering_context_self_rag_check_quality()@L486; main_build(argv)@L533; main_check(argv)@L554
- CLI args: --context-pack, --output-dir, --min-high-signal-capsules, --min-evidence-strength-score, --quality, --report-path, --write-json, --require-source-context-pack-quality-pass, --min-self-rag-records, --min-ready-for-gemma-draft, --min-crag-retry-required, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.
- Signal snippets:
  - L32 `self_rag`: tions import Counter from pathlib import Path from typing import Any, Dict, List, Mapping, Optional, Sequence MODULE_VERSION = "trace_net_engineering_context_self_rag_check_v1" REPORT_NAME = "trace_net_engineering_context_self_rag_check_v1.json" SOURCE_TRUTH_TIERS = { "exact_source_evidence_candidate", "source_context_guidance", "structured_table_candidate", } CANDIDATE_TIERS = { "relationship_candidate", "visual_candidate_only", "semantic_lead_only", "routing_metadata_not_source_tru
  - L2 `self-rag`: """TRACE-Net Engineering Context Self-RAG Check v1. Scores engineering context packs before Gemma drafting. This module checks: - source-truth evidence strength - candidate-only evidence - missing evidence notes - route coverage - forbidden-claim risk - CRAG retry need - draft readiness Safety: - does not answer the user question - does not call an LLM - does not execute retrieval - does
  - L12 `crag`: ma drafting. This module checks: - source-truth evidence strength - candidate-only evidence - missing evidence notes - route coverage - forbidden-claim risk - CRAG retry need - draft readiness Safety: - does not answer the user question - does not call an LLM - does not execute retrieval - does not mutate source truth - does not grant final answer permission """ from __future__ import annotations import argparse import json from collections import Counter from pathlib import Path from typing import Any, Dict, L
  - L91 `critic`: [n for n in notes if isinstance(n, dict)] def _clamp(value: float, lo: int = 0, hi: int = 100) -> int: return max(lo, min(hi, int(round(value)))) def _critical_missing_types(pack: Mapping[str, Any]) -> List[str]: intent = pack.get("intent_family") critical = [] for note in _missing_notes(pack): mtype = note.get("missing_type") if mtype == "route_slot_unfilled": critical.append(str(mtype)) if intent == "engineering_change_candidate" and mtype == "source_dimens
  - L100 `repair`: if intent == "engineering_change_candidate" and mtype == "source_dimension_not_confirmed": critical.append(str(mtype)) if intent == "repair_or_fault_context" and mtype == "warning_caution_not_confirmed": critical.append(str(mtype)) if intent == "visual_or_callout_similarity" and note.get("route") == "image_visual": critical.append(str(mtype)) return sorted(set(critical)) def _capsule_counts(capsules: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:

### `tiff/trace_net_engineering_engram_qdrant_adapter_v1.py`
- Score: `244`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _read_json(path)@L26; _write_json(path, data)@L30; _write_jsonl(path, rows)@L35; _norm_text(value)@L42; _as_bool(value)@L46; _point_id_from_atom(atom_id)@L50; _sanitize_payload(payload)@L54; normalize_qdrant_records(vector_loader)@L69; _cosine(a, b)@L103; _hash_embed(text, dim)@L114; local_search(points, query)@L126; _qdrant_request(method, url, payload, timeout)@L149; _create_collection(qdrant_url, collection_name, vector_dim, timeout)@L157; _upsert_points(qdrant_url, collection_name, points, timeout)@L167; _query_points(qdrant_url, collection_name, vector, top_k, timeout)@L173; build_qdrant_adapter_manifest()@L180; check_qdrant_adapter_manifest()@L362; build_arg_parser()@L407
- CLI args: --vector-loader, --output-dir, --collection-name, --qdrant-url, --vector-dim, --top-k, --min-records, --min-local-queries, --require-all-layers, --require-source-quality-pass, --require-no-answer-permission, --enable-live-qdrant-write, --enable-live-qdrant-read, --qdrant-timeout-seconds, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L13 `engram`: uest from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple MODULE = "trace_net_engineering_engram_qdrant_adapter_v1" VERSION = "v1" REQUIRED_LAYERS = { "working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory", } def _read_json(path: str | Path) -> Dict[str, Any]: return json.loads(Path(path).read_text(encoding="utf-8")) def _write_json(path: str | Path, data: Mapp
  - L229 `crag`: "query_text": "unknown part no proof_context not source trace ready"}, {"query_id": "q_safe_generic", "query_text": "safe but too generic repair critic CRAG"}, {"query_id": "q_summary_limit", "query_text": "v2 summaries guidance only not proof"}, {"query_id": "q_installation_limit", "query_text": "installation safety fit effectivity approval not proven"}, ] local_queries = default_queries[: max(min_local_queries, 0)] local_records = [] for q in local_queries: local_re
  - L22 `critic`: r_v1" VERSION = "v1" REQUIRED_LAYERS = { "working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory", } def _read_json(path: str | Path) -> Dict[str, Any]: return json.loads(Path(path).read_text(encoding="utf-8")) def _write_json(path: str | Path, data: Mapping[str, Any]) -> None: Path(path).parent.mkdir(parents=True, exist_ok=True) Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8") def _writ
  - L229 `repair`: nknown_part", "query_text": "unknown part no proof_context not source trace ready"}, {"query_id": "q_safe_generic", "query_text": "safe but too generic repair critic CRAG"}, {"query_id": "q_summary_limit", "query_text": "v2 summaries guidance only not proof"}, {"query_id": "q_installation_limit", "query_text": "installation safety fit effectivity approval not proven"}, ] local_queries = default_queries[: max(min_local_queries, 0)] local_records = [] for q in local_queries:
  - L65 `proof`: r. Runtime write attempt is tracked elsewhere. safe["qdrant_write_attempt"] = False safe["engram_guidance_only"] = True safe["manual_claims_require_proof_context"] = True return safe def normalize_qdrant_records(vector_loader: Mapping[str, Any], *, collection_name: str | None = None) -> List[Dict[str, Any]]: records = list(vector_loader.get("qdrant_ready_records") or []) out: List[Dict[str, Any]] = [] for rec in records: atom_id = _norm_text(rec.get("atom_id")) or _norm_text(re

### `tiff/trace_net_engineering_context_pack_blueprint_v1.py`
- Score: `240`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context Pack Blueprint v1. Turns engineering query plans into dynamic context-pack contracts for Gemma/TRACE-Net. This is the bridge between: - the engineering brain (playbooks/examples/trust tiers) - dynamic context engineering (what context to assemble at runtime) - future retrieval/evidence pack building Safety: - does not answer questions - does not call an LLM - does not execute retrieval - does not mutate source truth - does not write DB/search/vector indexes
- Functions: _read_json(path)@L30; _write_json(path, payload)@L36; _write_jsonl(path, records)@L41; _write_markdown(path, payload)@L48; _route_slot(route, plan)@L81; _section_contracts(plan)@L172; _answer_format_contract(plan)@L279; _self_rag_crag_contract(plan)@L318; build_context_pack_blueprint_record(plan, index)@L342; build_engineering_context_pack_blueprint()@L391; check_engineering_context_pack_blueprint_quality()@L472; main_build(argv)@L521; main_check(argv)@L537; fail_if(condition, msg)@L489
- CLI args: --query-planner, --output-dir, --quality, --report-path, --write-json, --require-source-query-planner-quality-pass, --min-blueprints, --min-total-route-slots, --min-source-truth-required-blueprints, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.
- Signal snippets:
  - L318 `self_rag`: "source_truth_evidence", "candidate_evidence", "missing_evidence", "forbidden_claims", ], } def _self_rag_crag_contract(plan: Mapping[str, Any]) -> Dict[str, Any]: return { "self_rag_checks": [ "every factual claim has source evidence or is labeled candidate", "candidate claims do not become approved replacement claims", "visual-only evidence is not treated as exact proof", "semantic-only evide
  - L232 `crag`: ource_truth_required": True, "may_use_summary_guidance": False, "missing_behavior": "mark_answer_not_proven_and_trigger_crag_retry", } ) elif section == "candidate_evidence": contract.update( { "purpose": "candidate evidence for engineering review only", "max_tokens_hint": 1400, "source_truth_required": False, } ) elif
  - L109 `repair`: t": base.update( { "evidence_role": "procedure_description_warning_context", "max_records": 8 if intent == "repair_or_fault_context" else 6, "preferred_artifacts": [ "page_context_v2", "normal_text_route_handoff", "Dublin Core metadata", ], "trust_tier": "source_context_guidance", } ) elif route == "image_visual": base.update(
  - L26 `context_pack`: om collections import Counter from pathlib import Path from typing import Any, Dict, List, Mapping, Optional, Sequence MODULE_VERSION = "trace_net_engineering_context_pack_blueprint_v1" REPORT_NAME = "trace_net_engineering_context_pack_blueprint_v1.json" def _read_json(path: Path) -> Dict[str, Any]: if not path.exists(): raise FileNotFoundError(f"missing JSON file: {path}") return json.loads(path.read_text(encoding="utf-8")) def _write_json(path: Path, payload: Mapping[str, Any]) -> None: p
  - L1 `context pack`: """TRACE-Net Engineering Context Pack Blueprint v1. Turns engineering query plans into dynamic context-pack contracts for Gemma/TRACE-Net. This is the bridge between: - the engineering brain (playbooks/examples/trust tiers) - dynamic context engineering (what context to assemble at runtime) - future retrieval/evidence pack building Safety: - does not answer questions - does not c

### `tiff/trace_net_engineering_context_pack_builder_v1.py`
- Score: `240`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context Pack Builder v1. Fills engineering context-pack blueprints with available TRACE-Net artifacts. v1.2: - optional artifact paths no longer crash when missing - missing optional artifacts are recorded in artifact_missing_inputs - quality checker can require no required-missing inputs while allowing optional missing inputs Safety: - no LLM calls - no live retrieval execution - no DB writes - no source-truth mutation - no answer permission
- Classes: FileNotErrorForOptional@L69 methods=[]
- Functions: _read_json(path)@L63; _write_json(path, payload)@L73; _write_jsonl(path, records)@L78; _looks_like_record(record)@L85; _flatten_records(payload)@L104; _recursive_text_values(obj, limit)@L151; _recursive_first(obj, keys)@L197; _compact_text(text, limit)@L215; _tokenize_question(question)@L220; _record_text_blob(record)@L238; _match_score(record)@L243; _artifact_records(path, route, artifact_name)@L263; _build_artifact_corpus()@L290; _trust_tier_for_route(route, score, seed_entities)@L317; _evidence_capsule(record)@L333; _select_capsules_for_slot()@L355; _missing_evidence_notes(blueprint, slot_capsules)@L376; _pack_sections(blueprint, slot_capsules, missing_notes)@L422
- CLI args: --blueprint, --output-dir, --route-dispatch-handoff, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --image-visual-observer, --max-records-per-slot, --quality, --report-path, --write-json, --require-source-blueprint-quality-pass, --min-context-packs, --min-artifact-corpus-records, --min-evidence-capsules, --min-high-signal-evidence-capsules, --min-packs-ready-for-gemma-context, --max-missing-optional-artifact-inputs, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.
- Signal snippets:
  - L516 `self_rag`: quired_route_slot_count": len(blueprint.get("route_evidence_slots") or []), "answer_format_contract": blueprint.get("answer_format_contract"), "self_rag_crag_contract": blueprint.get("self_rag_crag_contract"), "forbidden_answer_claims": blueprint.get("forbidden_answer_claims") or [], "ready_for_self_rag_check": True, "ready_for_gemma_context": high_signal_capsule_count > 0, "answers_user_question": False, "llm_call_allowed": False, "answer_permission":
  - L386 `crag`: "route_slot_unfilled", "route": route, "reason": f"no available artifact evidence selected for route {route}", "crag_retry_recommended": True, }) elif all(c.get("fallback_available_context") for c in capsules): notes.append({ "missing_type": "route_slot_has_only_fallback_context", "route": route, "reason": f"route {route} has artifact records but no high-signal match for this question",
  - L410 `repair`: e evidence does not clearly prove a source dimension", "crag_retry_recommended": True, }) if blueprint.get("intent_family") == "repair_or_fault_context": text = " ".join(c.get("source_text_excerpt", "") for caps in slot_capsules.values() for c in caps).lower() if "warning" not in text and "caution" not in text: notes.append({ "missing_type": "warning_caution_not_confirmed", "route": "normal_text", "reason": "
  - L29 `context_pack`: s import Counter from pathlib import Path from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple MODULE_VERSION = "trace_net_engineering_context_pack_builder_v1" REPORT_NAME = "trace_net_engineering_context_pack_builder_v1.json" TEXT_KEYS = ( "text", "sample", "sample_text", "content", "body", "snippet", "ocr_text", "fishnet_ocr_sample_text", "page_text", "page_summary", "page_summary_v2", "summary", "description", "title", "nomenclature", "covered_part_number", "part_number"
  - L2 `context pack`: """TRACE-Net Engineering Context Pack Builder v1. Fills engineering context-pack blueprints with available TRACE-Net artifacts. v1.2: - optional artifact paths no longer crash when missing - missing optional artifacts are recorded in artifact_missing_inputs - quality checker can require no required-missing inputs while allowing optional missing inputs Safety: - no LLM calls - no

### `tiff/trace_net_engineering_engram_memory_layers_v1.py`
- Score: `240`
- Categories: `context_pack, crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Engram Memory Layers v1. Artifact-only taxonomy builder for TRACE-Net Engram records. The layer taxonomy is deliberately behavior guidance, not source truth. It can shape answer style, route interpretation, critique, and repair behavior, but it must never prove manual facts, mutate source truth, or grant answer permission.
- Functions: utc_now_iso()@L170; stable_hash(value)@L174; load_json(path)@L179; write_json(path, data)@L183; _as_list(value)@L189; _lower_text()@L199; extract_engram_atoms(core)@L211; infer_memory_layer(atom)@L257; infer_proof_role(atom, layer)@L294; normalize_atom(atom)@L303; seed_layer_atoms()@L329; build_layered_atoms(core)@L333; group_layer_counts(atoms)@L343; unsafe_findings(atoms, manifest)@L352; validate_layered_manifest(manifest)@L386; build_memory_layer_manifest()@L444; check_memory_layer_manifest()@L511
- Signal snippets:
  - L1 `engram`: """TRACE-Net Engineering Engram Memory Layers v1. Artifact-only taxonomy builder for TRACE-Net Engram records. The layer taxonomy is deliberately behavior guidance, not source truth. It can shape answer style, route interpretation, critique, and repair behavior, but it must never prove manual facts, mutate source truth, or grant answer permission. """ from __future__ import anno
  - L281 `self_rag`: "working memory", "current question", "context pack", "proof_context")): return "working_memory" if any(k in text for k in ("critic", "self-rag", "self_rag", "crag", "repair", "fallback", "retry", "too generic")): return "critic_memory" if any(k in text for k in ("episodic", "episode", "h13", "h14", "h16", "eval", "smoke", "failure", "regression")): return "episodic_memory" if any(k in text for k in ("procedural", "policy", "rule", "if user", "interchange", "replacement", "effec
  - L72 `self-rag`: ewed_trait", "style_rule", "answer_shape", "engram_core"], "must_not_persist_source_truth": True, }, "critic_memory": { "description": "Self-RAG and CRAG critique/repair lessons, including safe-but-too-generic drafts, retry patterns, and repair examples.", "runtime_role": "draft_critique_and_repair", "proof_role": "guidance_only", "allowed_sources": ["critic_lesson", "repair_lesson", "eval_failure", "engram_core"], "must_not_persist_source_truth": True, },
  - L72 `crag`: "style_rule", "answer_shape", "engram_core"], "must_not_persist_source_truth": True, }, "critic_memory": { "description": "Self-RAG and CRAG critique/repair lessons, including safe-but-too-generic drafts, retry patterns, and repair examples.", "runtime_role": "draft_critique_and_repair", "proof_role": "guidance_only", "allowed_sources": ["critic_lesson", "repair_lesson", "eval_failure", "engram_core"], "must_not_persist_source_truth": True, }, } DEFAULT_L
  - L32 `critic`: sion" MEMORY_LAYERS: Tuple[str, ...] = ( "working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory", ) LAYER_DEFINITIONS: Dict[str, Dict[str, Any]] = { "working_memory": { "description": "Current question, current context pack, and current proof citations used only at answer time.", "runtime_role": "temporary_answer_state", "proof_role": "current_proof_context_only", "allowed_sources": ["current_question"

### `tiff/trace_net_engineering_engram_vector_retriever_v1.py`
- Score: `240`
- Categories: `context_pack, crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Engram Vector Retriever v1. Artifact-only local retriever for H18 Engram vector-loader records. This module intentionally does not contact Qdrant or any live service. It uses the same style of deterministic hashing-vector scoring as the H18 local loader so the retrieval behavior is reproducible in tests and git artifacts. A later live adapter can use the same payload contract after explicit write gates are added.
- Functions: _stable_id(text, prefix)@L85; tokenize(text)@L89; hashing_vector(text, dim)@L93; cosine_similarity(a, b)@L117; keyword_overlap_score(query_text, candidate_text)@L129; _coerce_vector(value, dim, text_fallback)@L139; _record_text(record)@L147; normalize_qdrant_ready_record(record, vector_dim)@L164; load_vector_loader(path)@L191; load_queries(path, inline_queries)@L196; retrieve_for_query(query, records)@L220; _counter(values)@L269; _write_json(path, obj)@L276; _write_jsonl(path, records)@L281; build_vector_retriever_manifest()@L286; check_vector_retriever_manifest()@L412
- Signal snippets:
  - L1 `engram`: """TRACE-Net Engineering Engram Vector Retriever v1. Artifact-only local retriever for H18 Engram vector-loader records. This module intentionally does not contact Qdrant or any live service. It uses the same style of deterministic hashing-vector scoring as the H18 local loader so the retrieval behavior is reproducible in tests and git artifacts. A later live adapter can use the
  - L40 `critic`: attempted": False, } REQUIRED_LAYERS = [ "working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory", ] DEFAULT_RETRIEVAL_QUERIES = [ { "query_id": "h19_q_interchangeability_boundary", "text": "Is part 120-50645-005 interchangeable with 120-50645-011 or an approved replacement? Require explicit source authority.", "expected_layers": ["procedural_memory", "trait_memory"], "task_type": "interchangeability_bo
  - L63 `repair`: "expected_layers": ["working_memory", "procedural_memory"], "task_type": "unknown_part", }, { "query_id": "h19_q_safe_but_too_generic_repair", "text": "The answer was safe but too generic. Retrieve repair behavior before regenerating.", "expected_layers": ["critic_memory", "episodic_memory", "trait_memory"], "task_type": "critic_repair", }, { "query_id": "h19_q_summary_only_limit", "text": "Can v2 summaries alone prove Figure 69 part identity
  - L58 `proof`: ation", }, { "query_id": "h19_q_unknown_part_not_source_trace_ready", "text": "Find part number 999-99999-999 and cite a source when no proof_context exists.", "expected_layers": ["working_memory", "procedural_memory"], "task_type": "unknown_part", }, { "query_id": "h19_q_safe_but_too_generic_repair", "text": "The answer was safe but too generic. Retrieve repair behavior before regenerating.", "expected_layers": ["critic_memory", "episodic_memo
  - L170 `guidance`: er = str(record.get("memory_layer") or payload.get("memory_layer") or "unknown") proof_role = str(record.get("proof_role") or payload.get("proof_role") or "guidance_only") text = _record_text(record) vector = _coerce_vector(record.get("vector") or record.get("embedding"), vector_dim, text) point_id = str(record.get("point_id") or payload.get("point_id") or hashlib.sha256(atom_id.encode("utf-8")).hexdigest()) return { "atom_id": atom_id, "point_id": point_id, "memory_layer

### `tiff/trace_net_engineering_webui_answer_server_v1_3.py`
- Score: `239`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering WebUI Answer Server v1.3. Small quality layer over v1/v1.2 server. v1.3 fixes the remaining weak spot from the v1.2 rerun: - if Gemma4 returns empty on artifact-search questions, fallback is now a clean deterministic mini-answer instead of raw page-lead text - repair/material/table pages are summarized as "what TRACE-Net found" - visible source notes are always included - keeps exact lookup and random page behavior from v1.2
- Classes: TraceNetWebUIHandlerV13@L344 methods=['_json_response', '_read_body_json', 'do_GET', 'do_POST']; TraceNetHTTPServerV13@L417 methods=['__init__']
- Functions: _query_type(question)@L57; _extract_key_terms(text)@L68; build_clean_search_fallback()@L102; answer_search_summary_v13(question, pages)@L139; answer_question_v13()@L206; build_manifest_v13()@L233; check_manifest_v13()@L305; run_server_v13()@L425; main_build(argv)@L448; main_check(argv)@L477; main_run(argv)@L509; fail_if(condition, msg)@L319; _json_response(self, status, payload)@L347; _read_body_json(self)@L355; do_GET(self)@L362; do_POST(self)@L382; __init__(self, server_address, handler_class)@L418
- CLI args: --output-dir, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff, --sample-question, --quality, --report-path, --write-json, --min-page-records, --min-gated-drafts, --require-llm-model, --require-clean-fallback, --require-no-answer-permission, --require-no-source-truth-mutation, --host, --port, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff
- Routes: /health@L287, /v1/models@L287, /v1/chat/completions@L287, /health@L363, /v1/models@L377, /api/models@L377, /v1/chat/completions@L383, /api/chat/completions@L383
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1 import DEFAULT_FINAL_GATE, DEFAULT_FISHNET, DEFAULT_PAGE_CONTEXT, DEFAULT_ROUTE_HANDOFF, DEFAULT_RUNNER, LLMConfig, MODEL_ID, _add_llm_args, _clean_trace_text, _compose_with_llm, _extractive_summary, _llm_config_from_args, _part_numbers, _read_json, _records_from_payload, _response_record, _search_pages, _source_notes, _write_json, _write_jsonl, answer_gated_lookup, answer_random_page_summary, answer_v2_summary_inventory, load_gated_drafts, load_page_index
- Signal snippets:
  - L9 `repair`: rom the v1.2 rerun: - if Gemma4 returns empty on artifact-search questions, fallback is now a clean deterministic mini-answer instead of raw page-lead text - repair/material/table pages are summarized as "what TRACE-Net found" - visible source notes are always included - keeps exact lookup and random page behavior from v1.2 """ from __future__ import annotations import argparse import json import re import time from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer from pathlib import Path from typ
  - L134 `proof`: m interpretation as a candidate lead until the image/visual route verifies it.") else: lines.append("Treat these as source leads for review, not as proof of approval, interchangeability, fit, or safety.") return "\n".join(lines) def answer_search_summary_v13(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]: hits = _search_pages(question, pages) if not hits: response = ( "TRACE-Net did not find enough artifact text to answer
  - L25 `final_gate`: import Path from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple from tiff.trace_net_engineering_webui_answer_server_v1 import ( DEFAULT_FINAL_GATE, DEFAULT_FISHNET, DEFAULT_PAGE_CONTEXT, DEFAULT_ROUTE_HANDOFF, DEFAULT_RUNNER, LLMConfig, MODEL_ID, _add_llm_args, _clean_trace_text, _compose_with_llm, _extractive_summary, _llm_config_from_args, _part_numbers, _read_json, _records_from_payload, _response_record, _search_pages, _
  - L287 `chat/completions`: y": summary, "model_id": MODEL_ID, "records": records, "routes": {"health": "/health", "models": "/v1/models", "chat_completions": "/v1/chat/completions"}, "safety_contract": { "manual_review_required": True, "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_allowed": False, "qdrant_write_allowed": False, "opensearch_write_allowed": False, }, } output_dir.mkdir(pa
  - L383 `api/chat`: ._json_response(404, {"error": f"not found: {self.path}"}) def do_POST(self) -> None: # noqa: N802 if self.path not in {"/v1/chat/completions", "/api/chat/completions"}: self._json_response(404, {"error": f"not found: {self.path}"}) return try: body = self._read_body_json() messages = body.get("messages") or [] question = "" for msg in reversed(messages): if isinstance(msg, dict) and msg.get("role") == "use

### `scripts/build_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Score: `238`
- Categories: `final_gate, graph_vector, page, safety, server, webui`
- Functions: parse_args()@L18; main()@L41
- CLI args: --live-llm-final-gate, --output-dir, --host, --port, --model-id, --min-final-gates, --min-ready-final-answers, --min-endpoint-routes, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import MODEL_ID, attach_quality, build_endpoint_state, evaluate_quality, write_endpoint_files
- Has __main__ guard.
- Signal snippets:
  - L32 `proof`: rted-claim-count", type=int, default=0) p.add_argument("--max-final-non-direct-citation-marker-count", type=int, default=0) p.add_argument("--max-graph-proof-authority-violations", type=int, default=0) p.add_argument("--max-summary-proof-authority-violations", type=int, default=0) p.add_argument("--max-answer-permission-count", type=int, default=0) p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0) p.add_argument("--require-no-answer-permission", action="store_true")
  - L9 `final_gate`: REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import ( MODEL_ID, attach_quality, build_endpoint_state, evaluate_quality, write_endpoint_files, ) def parse_args(): p = argparse.ArgumentParser(description="Build TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24 artifact.") p.add_argument("--live-llm-final-gate", required=True) p.add_ar
  - L56 `source_truth_mutation_allowed`: mmary_proof_authority_violations=args.max_summary_proof_authority_violations, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, ) attach_quality(state, quality_status, checks) paths = write_endpoint_files(state, Path(args.output_dir)) print("TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24") print(f" Status: {state['
  - L55 `answer_permission`: y_violations=args.max_graph_proof_authority_violations, max_summary_proof_authority_violations=args.max_summary_proof_authority_violations, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, ) attach_quality(state, quality_status, checks) paths = write_endpoint_files(state, Path(args.output_dir)) print("TRACE-Net E2E Liv

### `scripts/check_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24_quality.py`
- Score: `238`
- Categories: `final_gate, graph_vector, page, safety, server, webui`
- Functions: parse_args()@L18; main()@L37
- CLI args: --report-path, --min-final-gates, --min-ready-final-answers, --min-endpoint-routes, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import QUALITY_PASS, attach_quality, evaluate_quality, read_json, write_json
- Has __main__ guard.
- Signal snippets:
  - L28 `proof`: rted-claim-count", type=int, default=0) p.add_argument("--max-final-non-direct-citation-marker-count", type=int, default=0) p.add_argument("--max-graph-proof-authority-violations", type=int, default=0) p.add_argument("--max-summary-proof-authority-violations", type=int, default=0) p.add_argument("--max-answer-permission-count", type=int, default=0) p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0) p.add_argument("--require-no-answer-permission", action="store_true")
  - L9 `final_gate`: REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import ( QUALITY_PASS, attach_quality, evaluate_quality, read_json, write_json, ) def parse_args(): p = argparse.ArgumentParser(description="Check TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24 quality.") p.add_argument("--report-path", required=True) p.add_argument("--min-final-gates"
  - L53 `source_truth_mutation_allowed`: mmary_proof_authority_violations=args.max_summary_proof_authority_violations, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, ) attach_quality(state, quality_status, checks) if args.write_json: write_json(path, state) print("TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24 Quality") print(f" quality_status:
  - L52 `answer_permission`: y_violations=args.max_graph_proof_authority_violations, max_summary_proof_authority_violations=args.max_summary_proof_authority_violations, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, ) attach_quality(state, quality_status, checks) if args.write_json: write_json(path, state) print("TRACE-Net E2E Live WebUI

### `scripts/check_trace_net_openwebui_page_context_bridge_v1_quality.py`
- Score: `238`
- Categories: `context_pack, graph_vector, page, safety, server, webui`
- Functions: _as_int(value)@L11; check_quality(manifest)@L18; main(argv)@L63
- CLI args: --input, --output, --min-pages, --allow-no-page-context
- Has __main__ guard.
- Signal snippets:
  - L21 `context_pack`: , Any]: failures: list[str] = [] meta = manifest.get("bridge_meta") if isinstance(manifest.get("bridge_meta"), Mapping) else {} summary = meta.get("context_pack_summary") if isinstance(meta.get("context_pack_summary"), Mapping) else {} if require_page_context_used and not meta.get("page_context_used"): failures.append("page_context_not_used") if meta.get("context_pack_quality_status") not in ("PASS", None): failures.append("context_pack_quality_not_pass") if _as_int(summary.
  - L42 `binder`: ) if isinstance(manifest.get("enriched_messages_preview"), list) else [] rendered = json.dumps(messages, ensure_ascii=False) if "TRACE-NET PAGE CONTEXT BINDER V3" not in rendered: failures.append("binder_preview_missing") if "model_should_think" not in rendered: failures.append("reasoning_work_order_missing_from_preview") return { "module": MODULE, "quality_status": "PASS" if not failures else "FAIL", "failure_reasons": failures, "summary": {
  - L55 `proof`: ext_pack_quality_status": meta.get("context_pack_quality_status"), "selected_page_count": _as_int(summary.get("selected_page_count")), "proof_record_count": _as_int(summary.get("proof_record_count")), "guidance_record_count": _as_int(summary.get("guidance_record_count")), "answer_permission_count": _as_int(summary.get("answer_permission_count")), "source_truth_mutation_allowed_count": _as_int(summary.get("source_truth_mutation_allowed_count")), },
  - L56 `guidance`: "selected_page_count": _as_int(summary.get("selected_page_count")), "proof_record_count": _as_int(summary.get("proof_record_count")), "guidance_record_count": _as_int(summary.get("guidance_record_count")), "answer_permission_count": _as_int(summary.get("answer_permission_count")), "source_truth_mutation_allowed_count": _as_int(summary.get("source_truth_mutation_allowed_count")), }, } def main(argv: Sequence[str] | None = None) -> int: parser = argpa
  - L8 `openwebui`: from __future__ import annotations import argparse import json from pathlib import Path from typing import Any, Mapping, Sequence MODULE = "check_trace_net_openwebui_page_context_bridge_v1_quality" def _as_int(value: Any) -> int: try: return int(value or 0) except (TypeError, ValueError): return 0 def check_quality(manifest: Mapping[str, Any], *, require_page_context_used: bool = True, min_pages: int = 1) -> dict[str, Any]: failures: list[str] = [] meta = manifest.get("bridge

### `tiff/trace_net_e2e_crag_retrieval_corrector_v10.py`
- Score: `237`
- Categories: `context_pack, crag, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E CRAG retrieval corrector v10. This module consumes Self-RAG context critic output and creates a corrective retrieval plan for each context. It is intentionally plan-only: it does not call an LLM, rerun retrieval, mutate source truth, or write to external services. Later endpoint/runtime modules can consume these plans to decide whether to retry retrieval, repair routing, or request human review.
- Functions: read_json(path)@L55; write_json(path, data)@L60; write_jsonl(path, rows)@L66; as_bool(value)@L74; as_int(value, default)@L86; safe_list(value)@L97; nested_get(data, path, default)@L105; extract_critiques(self_rag_report)@L114; _has_failed_findings(critique, severity)@L132; infer_retry_reasons(critique)@L145; build_corrective_actions(critique, retry_reasons)@L208; build_crag_plan(critique, index)@L299; build_crag_corrector_report(self_rag_context_critic, source_path)@L350; evaluate_quality(report, args)@L402; render_markdown(report)@L435; write_report_files(report, output_dir)@L477; add_quality_args(parser)@L496; print_quality_result(report, checks, title)@L512
- CLI args: --min-context-critiques, --min-crag-plans, --min-ready-crag-plans, --min-no-retry-needed-count, --min-corrective-actions, --max-retry-required-plan-count, --max-human-review-plan-count, --max-unresolved-plan-count, --max-graph-summary-proof-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission
- Signal snippets:
  - L30 `self_rag`: PLAN_READY" HUMAN_REVIEW_STATUS = "CRAG_HUMAN_REVIEW_PLAN_READY" UNRESOLVED_STATUS = "CRAG_UNRESOLVED" DEFAULT_CONTRACT: Dict[str, Any] = { "uses_prebuilt_self_rag_critiques": True, "uses_prebuilt_context_packs": True, "corrector_emits_plan_only": True, "corrector_does_not_call_llm": True, "corrector_does_not_rerun_retrieval": True, "corrector_does_not_rerun_ocr": True, "corrector_does_not_rerun_page_classification": True, "corrector_does_not_rerun_embeddings": True, "corrector_
  - L3 `self-rag`: """TRACE-Net E2E CRAG retrieval corrector v10. This module consumes Self-RAG context critic output and creates a corrective retrieval plan for each context. It is intentionally plan-only: it does not call an LLM, rerun retrieval, mutate source truth, or write to external services. Later endpoint/runtime modules can consume these plans to decide whether to retry retrieval, repair routing, or request human review. """ from __
  - L1 `crag`: """TRACE-Net E2E CRAG retrieval corrector v10. This module consumes Self-RAG context critic output and creates a corrective retrieval plan for each context. It is intentionally plan-only: it does not call an LLM, rerun retrieval, mutate source truth, or write to external services. Later endpoint/runtime modules can consume these plans to decide whether to retry retrieval, r
  - L3 `critic`: """TRACE-Net E2E CRAG retrieval corrector v10. This module consumes Self-RAG context critic output and creates a corrective retrieval plan for each context. It is intentionally plan-only: it does not call an LLM, rerun retrieval, mutate source truth, or write to external services. Later endpoint/runtime modules can consume these plans to decide whether to retry retrieval, repair routing, or request human review. """ from __future__ import a
  - L7 `repair`: run retrieval, mutate source truth, or write to external services. Later endpoint/runtime modules can consume these plans to decide whether to retry retrieval, repair routing, or request human review. """ from __future__ import annotations import argparse import json from dataclasses import dataclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple SCHEMA_VERSION = "v10" STATUS_BUILT = "E2E_CRAG_RETRIEVAL_CORRECTOR_BUILT" STATUS_READY = "E2

### `tiff/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py`
- Score: `237`
- Categories: `crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Classes: TraceNetArtifactsV33@L539 methods=['load', 'all_page_ids']; TraceNetGemmaAnswerWriterV33@L803 methods=['__init__', 'from_paths', '_page_metadata', 'build_package', '_llm_messages', '_simulate_llm', '_call_openai_compatible_llm', '_final_gate']
- Functions: _now()@L69; _read_json(path)@L73; _stable_id(prefix, text)@L85; _stringify(x)@L90; _norm(s)@L100; _lower(s)@L104; _looks_like_page_id(value)@L108; _extract_page_id(obj)@L112; _extract_field(obj)@L136; _extract_value(obj)@L148; _walk_json(obj)@L176; _candidate_record_dicts(data)@L186; _collect_page_contexts(data)@L214; _load_leiden_membership(data)@L231; _safe_join_items(items, max_items)@L261; _citation_lines(evidence)@L265; _dedupe_evidence(records, limit)@L276; _format_evidence_examples(evidence, max_items)@L298
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --output-dir, --host, --port, --llm-mode, --llm-model, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens, --include-standard-demo-queries, --min-sample-queries, --min-sample-successes, --min-llm-called-samples, --min-compact-prompt-samples, --min-normal-intent-samples, --min-self-rag-samples, --min-crag-samples, --max-crag-retry-required-count, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Routes: /chat/completions@L1062
- Has __main__ guard.
- Signal snippets:
  - L315 `self_rag`: : router_report.get("graph_has_nomenclature_page_count"), "exact_search_document_count": router_report.get("exact_search_document_count"), } def _self_rag_assessment(package: Mapping[str, Any]) -> Dict[str, Any]: """Small, deterministic Self-RAG-style package quality card. This is not a second model call. It is runtime telemetry that tells the endpoint and evaluator whether the package is strong enough, partial, guidance-only, metadata-only, or safely unanswerable. """ intent
  - L316 `self-rag`: : router_report.get("exact_search_document_count"), } def _self_rag_assessment(package: Mapping[str, Any]) -> Dict[str, Any]: """Small, deterministic Self-RAG-style package quality card. This is not a second model call. It is runtime telemetry that tells the endpoint and evaluator whether the package is strong enough, partial, guidance-only, metadata-only, or safely unanswerable. """ intent = _norm(package.get("query_intent")) mode = _norm(package.get("response_mode")) evidenc
  - L377 `crag`: imitation_disclosure_required": guidance_only or capped or not has_direct, "metadata_count_source": metadata.get("metadata_count_source"), } def _crag_assessment(package: Mapping[str, Any], self_rag: Mapping[str, Any]) -> Dict[str, Any]: """Small CRAG-style retry/fallback decision card. CRAG here means: if the first package is weak, identify whether we should retry a different route, or whether the safe audit-only answer is the correct final behavior. """ intent = _norm(packag
  - L1146 `repair`: proof" not in lower: issues.append("relationship_guidance_disclosure_missing") if issues: final = deterministic repaired = True else: final = text repaired = False # Normalize a few spacing artifacts. final = re.sub(r"(?<!\s)(\[\d+\])", r" \1", final) final = final.replace("doesnot", "does not").replace("onlyand", "only and").replace("availableevidence", "available evidence") final = re.sub(r"\s+", " ", f
  - L331 `proof`: y = bool(has_graph_guidance or has_v2 or intent in {"artifact_v2_summary_count", "field_or_graph_nomenclature_count", "nomenclature_relationship_question", "v2_proof_safety_question"}) capped = bool(package.get("result_was_capped")) missing_or_audit = mode in {"audit_only", "exact_missing_value"} or not (has_direct or has_metadata_answer or has_graph_guidance or has_v2) if has_direct and not capped: quality = "strong" status = "SELF_RAG_SOURCE_TRUTH_READY" answerable = True

### `tiff/trace_net_e2e_live_llm_draft_adapter_v22.py`
- Score: `237`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, webui`
- Classes: LlmConfig@L226 methods=[]
- Functions: load_json(path)@L25; write_json(path, data)@L29; write_jsonl(path, rows)@L34; _as_bool(value)@L41; _first_list(obj, candidate_keys)@L49; prompt_contracts(data)@L67; _contract_id(row, index)@L72; _contract_ready(row)@L76; _messages(row)@L85; _context_message(row)@L98; _extract_direct_evidence_lines(context)@L105; _extract_aggregation(context)@L121; _citation_like_count(text)@L142; _has_cap_disclosure(text)@L146; _simulate_draft(row)@L151; _call_openai_compatible_llm()@L180; build_drafts(contracts)@L236; evaluate_quality(report, thresholds)@L354
- CLI args: --live-llm-prompt-contract, --output-dir, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --temperature, --request-timeout, --max-contracts, --min-prompt-contracts, --min-llm-drafts, --min-drafts-ready-for-final-gate, --min-drafts-with-nonempty-content, --min-source-truth-supported-prompts, --min-successful-llm-calls, --min-live-llm-calls, --min-simulated-llm-drafts, --max-llm-call-errors, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality, --report-path, --min-prompt-contracts, --min-llm-drafts, --min-drafts-ready-for-final-gate, --min-drafts-with-nonempty-content, --min-source-truth-supported-prompts, --min-successful-llm-calls, --min-live-llm-calls
- Routes: /chat/completions@L189
- Has __main__ guard.
- Signal snippets:
  - L127 `self-rag`: REGATION / CAPPING METADATA:" start = context.find(marker) if start < 0: return {} rest = context[start + len(marker):] end_markers = ["SELF-RAG / CRAG STATUS:", "ANSWER RULES:"] end = len(rest) for m in end_markers: idx = rest.find(m) if idx >= 0: end = min(end, idx) block = rest[:end].strip() if not block.startswith("{"): return {} try: return json.loads(block) except Exception: return {} def _citation_like_count
  - L127 `crag`: CAPPING METADATA:" start = context.find(marker) if start < 0: return {} rest = context[start + len(marker):] end_markers = ["SELF-RAG / CRAG STATUS:", "ANSWER RULES:"] end = len(rest) for m in end_markers: idx = rest.find(m) if idx >= 0: end = min(end, idx) block = rest[:end].strip() if not block.startswith("{"): return {} try: return json.loads(block) except Exception: return {} def _citation_like_count(text: str)
  - L16 `repair`: uence, Tuple VERSION = "v22" MODULE = "trace_net_e2e_live_llm_draft_adapter_v22" STATUS_READY = "E2E_LIVE_LLM_DRAFT_ADAPTER_READY_FOR_FINAL_GATE" STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_DRAFT_ADAPTER_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" DEFAULT_LLM_BASE_URL = "http://127.0.0.1:11434/v1" DEFAULT_LLM_MODEL = "gemma4:26b" DEFAULT_LLM_API_KEY = "ollama" def load_json(path: str | Path) -> Any: return json.loads(Path(path).read_text(encoding="utf-8")) def write_json(path: str | Path, data: Any)
  - L256 `context_pack`: _draft_v22_{idx:04d}" base_record: Dict[str, Any] = { "llm_draft_id": draft_id, "prompt_contract_id": contract_id, "context_pack_id": contract.get("context_pack_id"), "user_query": contract.get("user_query"), "draft_adapter_status": "LLM_DRAFT_PENDING", "prompt_contract_ready": ready_contract, "llm_mode": config.mode, "llm_provider": "ollama_openai_compatible" if config.mode == "ollama" else "simulated_determinis
  - L100 `context pack`: role, "content": content}) return out def _context_message(row: Mapping[str, Any]) -> str: for msg in reversed(_messages(row)): if "TRACE-NET CONTEXT PACK" in msg.get("content", ""): return msg["content"] return _messages(row)[-1]["content"] if _messages(row) else "" def _extract_direct_evidence_lines(context: str) -> List[str]: lines = context.splitlines() in_direct = False out: List[str] = [] for line in lines: stripped = line.strip() if stripped

### `tiff/trace_net_e2e_self_rag_context_critic_v9.py`
- Score: `237`
- Categories: `context_pack, crag, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E Self-RAG Context Critic v9. This module critiques dynamic context packs before they are handed to an LLM. It is intentionally non-mutating: it reads prebuilt context-pack artifacts and writes an audit/critic artifact. It does not rerun OCR, embeddings, graph build, table extraction, or source ingest.
- Functions: load_json(path)@L41; write_json(path, data)@L46; write_jsonl(path, rows)@L52; as_list(value)@L60; as_bool(value)@L68; truthy_count(rows, key)@L76; get_context_packs(context_pack_report)@L80; get_evidence_items(pack)@L94; get_guidance_items(pack)@L101; get_rules_box(pack)@L108; expected_fields_for_intent(intent)@L113; field_relevant_for_intent(field_name, intent)@L122; guidance_item_is_safe(item)@L129; critique_context_pack(pack)@L137; make_quality_check(name, observed, expected, passed)@L324; build_self_rag_context_critic(dynamic_context_pack)@L328; render_markdown_report(report)@L461; write_report_files(report, output_dir)@L506
- CLI args: --dynamic-context-pack, --output-dir, --min-context-packs, --min-context-critiques, --min-ready-contexts, --min-contexts-with-source-truth-evidence, --min-contexts-with-guidance-separation, --max-needs-crag-retry-count, --max-human-review-count, --max-graph-summary-proof-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Signal snippets:
  - L18 `self_rag`: pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple SCHEMA_VERSION = "v9" STATUS_BUILT = "E2E_SELF_RAG_CONTEXT_CRITIC_BUILT" STATUS_READY_FOR_CRAG_OR_PROMPT = "E2E_SELF_RAG_CONTEXT_CRITIC_READY_FOR_CRAG_OR_PROMPT" STATUS_NOT_READY = "E2E_SELF_RAG_CONTEXT_CRITIC_NOT_READY" CRITIC_READY = "SELF_RAG_CONTEXT_READY" CRITIC_WEAK = "SELF_RAG_CONTEXT_WEAK" CRITIC_NEEDS_CRAG_RETRY = "SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY" CRITIC_NEEDS_HUMAN_REVIEW = "SELF_RAG_CO
  - L1 `self-rag`: """TRACE-Net E2E Self-RAG Context Critic v9. This module critiques dynamic context packs before they are handed to an LLM. It is intentionally non-mutating: it reads prebuilt context-pack artifacts and writes an audit/critic artifact. It does not rerun OCR, embeddings, graph build, table extraction, or source ingest. """ from __future__ import annotations import argparse
  - L19 `crag`: , Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple SCHEMA_VERSION = "v9" STATUS_BUILT = "E2E_SELF_RAG_CONTEXT_CRITIC_BUILT" STATUS_READY_FOR_CRAG_OR_PROMPT = "E2E_SELF_RAG_CONTEXT_CRITIC_READY_FOR_CRAG_OR_PROMPT" STATUS_NOT_READY = "E2E_SELF_RAG_CONTEXT_CRITIC_NOT_READY" CRITIC_READY = "SELF_RAG_CONTEXT_READY" CRITIC_WEAK = "SELF_RAG_CONTEXT_WEAK" CRITIC_NEEDS_CRAG_RETRY = "SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY" CRITIC_NEEDS_HUMAN_REVIEW = "SELF_RAG_CONTEXT_NEEDS_HUMAN_REVIEW" SOURCE_TRUTH_AUTHORIT
  - L1 `critic`: """TRACE-Net E2E Self-RAG Context Critic v9. This module critiques dynamic context packs before they are handed to an LLM. It is intentionally non-mutating: it reads prebuilt context-pack artifacts and writes an audit/critic artifact. It does not rerun OCR, embeddings, graph build, table extraction, or source ingest. """ from __future__ import annotations import argparse import json from
  - L80 `context_pack`: return bool(value) def truthy_count(rows: Iterable[Mapping[str, Any]], key: str) -> int: return sum(1 for row in rows if as_bool(row.get(key))) def get_context_packs(context_pack_report: Mapping[str, Any]) -> List[Dict[str, Any]]: for key in ("context_packs", "packs", "records", "context_pack_records"): rows = context_pack_report.get(key) if isinstance(rows, list): return [dict(row) for row in rows if isinstance(row, Mapping)] # Some generated artifacts may place packs un

### `tiff/trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Score: `234`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: RuntimeState@L125 methods=['__init__', 'answer']
- Functions: _now_ms()@L55; _quality_check(name, observed, op, expected)@L59; _router_result_to_gate_input(query, router_result)@L73; apply_relationship_final_gate(query, router_result)@L87; make_chat_completion_response(model, query, result)@L164; _sample_record(sample_id, query, result)@L228; build_report()@L248; write_inspect_md(path, report)@L373; check_report()@L428; __init__(self)@L126; answer(self, query)@L147
- Tiff imports: from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import MODEL_ID, SAFETY_CONTRACT, RuntimeState, _extract_user_text, _read_json, _write_json, _write_jsonl; from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import SAFETY_CONTRACT, final_gate_record
- Signal snippets:
  - L27 `repair`: endpoint_v31" MODEL_ID = "trace-net-e2e-live-relationship-final-gated-gemma-v31" STATUS_READY = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_READY" STATUS_NEEDS_REPAIR = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_NEEDS_REPAIR" SAFETY_CONTRACT = { **ROUTER_SAFETY_CONTRACT, **RELATIONSHIP_GATE_SAFETY_CONTRACT, "llm_called": False, "metadata_count_router_enabled": True, "relationship_final_gate_required": True, "relationship_final_gate_live_endpoint": True, "graph_leiden_guidance_only": Tr
  - L100 `proof`: te_record_id"] = gate.get("relationship_final_gate_id") final_result["relationship_gate_latency_ms"] = gate.get("latency_ms", 0) final_result["graph_as_proof_violation_detected"] = gate.get("graph_as_proof_violation_detected", False) final_result["v2_summary_as_proof_violation_detected"] = gate.get("v2_summary_as_proof_violation_detected", False) final_result["nomenclature_as_proof_violation_detected"] = gate.get("nomenclature_as_proof_violation_detected", False) final_result["unsupported_relati
  - L36 `guidance`: , "metadata_count_router_enabled": True, "relationship_final_gate_required": True, "relationship_final_gate_live_endpoint": True, "graph_leiden_guidance_only": True, "v2_summaries_guidance_only": True, "nomenclature_metadata_guidance_only": True, "source_truth_required_for_relationship_claims": True, } STANDARD_SAMPLE_QUERIES = [ "how many pages have a v2 summary", "how many pages mention a nomenclature", "find part number 120-36833-503", "Find part number DOES-NOT-EXIST
  - L18 `final_gate`: RACT, RuntimeState as RouterRuntimeState, _extract_user_text, _read_json, _write_json, _write_jsonl, ) from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import ( SAFETY_CONTRACT as RELATIONSHIP_GATE_SAFETY_CONTRACT, final_gate_record, ) VERSION = "v31" MODULE = "trace_net_e2e_live_relationship_final_gated_endpoint_v31" MODEL_ID = "trace-net-e2e-live-relationship-final-gated-gemma-v31" STATUS_READY = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_READY" STATUS_NEEDS_REPAIR = "E2E
  - L132 `page_context`: *, relationship_router_hardening: Path, relationship_final_gate_hardener: Optional[Path], table_exact_search_adapter: Path, page_context_v2: Optional[Path], leiden_communities: Optional[Path], graph_signal_paths: Optional[Sequence[Path]] = None, ): self.router_state = RouterRuntimeState( relationship_router_hardening, table_exact_search_adapter, page_context_v2, leiden_communities, graph_signa

### `scripts/serve_trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py`
- Score: `229`
- Categories: `final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Classes: Handler@L62 methods=['log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: _send_json(handler, data, status)@L21; main(argv)@L33; log_message(self, fmt)@L63; do_OPTIONS(self)@L66; do_GET(self)@L69; do_POST(self)@L109
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --host, --port, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --temperature, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens
- Routes: /health@L70, /v1/models@L104, /v1/chat/completions@L114
- Tiff imports: from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v33 import MODEL_ID, TraceNetGemmaAnswerWriterV33, _extract_messages_user_text
- Has __main__ guard.
- Signal snippets:
  - L95 `self_rag`: "llm_answer_writer_required": True, "compact_prompt_mode_supported": True, "self_rag_package_quality_telemetry_enabled": True, "crag_retry_telemetry_enabled": True, "rich_page_profile_package_supported": True, "timeout_fallback_supported": True, "response_is_final_gated": True, },
  - L96 `crag`: "compact_prompt_mode_supported": True, "self_rag_package_quality_telemetry_enabled": True, "crag_retry_telemetry_enabled": True, "rich_page_profile_package_supported": True, "timeout_fallback_supported": True, "response_is_final_gated": True, }, }, ) return if self.path.rstrip("/
  - L58 `final_gate`: page_context_v2, leiden_communities=ns.leiden_communities, relationship_router_hardening=ns.relationship_router_hardening, relationship_final_gate_hardener=ns.relationship_final_gate_hardener, ) metadata = writer._page_metadata() class Handler(BaseHTTPRequestHandler): def log_message(self, fmt: str, *args: Any) -> None: return def do_OPTIONS(self) -> None: _send_json(self, {"ok": True}) def do_GET(self) -> None: if se
  - L132 `openwebui`: ode=ns.llm_prompt_mode, llm_max_output_tokens=ns.llm_max_output_tokens, ) # Preserve requested model id for OpenWebUI compatibility. resp["model"] = MODEL_ID _send_json(self, resp) except Exception as exc: safe = { "id": "chatcmpl-tracenet-v33-error", "object": "chat.completion", "created": 0, "model": MODEL_ID,
  - L114 `chat/completions`: .rfile.read(length).decode("utf-8", errors="replace") payload = json.loads(raw) if raw else {} if self.path.rstrip("/") != "/v1/chat/completions": _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404) return query = _extract_messages_user_text(payload) if not query: _send_json(self, {"error": "No user message found"}, status=400) return resp

### `tiff/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.py`
- Score: `229`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: TraceNetArtifactsV32@L424 methods=['load', 'all_page_ids']; TraceNetGemmaAnswerWriterV32@L667 methods=['__init__', 'from_paths', '_page_metadata', 'build_package', '_llm_messages', '_simulate_llm', '_call_openai_compatible_llm', '_final_gate']
- Functions: _now()@L69; _read_json(path)@L73; _stable_id(prefix, text)@L85; _stringify(x)@L90; _norm(s)@L100; _lower(s)@L104; _looks_like_page_id(value)@L108; _extract_page_id(obj)@L112; _extract_field(obj)@L136; _extract_value(obj)@L148; _walk_json(obj)@L176; _candidate_record_dicts(data)@L186; _collect_page_contexts(data)@L214; _load_leiden_membership(data)@L231; _safe_join_items(items, max_items)@L261; _citation_lines(evidence)@L265; _dedupe_evidence(records, limit)@L276; _format_evidence_examples(evidence, max_items)@L298
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --output-dir, --host, --port, --llm-mode, --llm-model, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens, --include-standard-demo-queries, --min-sample-queries, --min-sample-successes, --min-llm-called-samples, --min-compact-prompt-samples, --min-normal-intent-samples, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Routes: /chat/completions@L910
- Has __main__ guard.
- Signal snippets:
  - L994 `repair`: proof" not in lower: issues.append("relationship_guidance_disclosure_missing") if issues: final = deterministic repaired = True else: final = text repaired = False # Normalize a few spacing artifacts. final = re.sub(r"(?<!\s)(\[\d+\])", r" \1", final) final = final.replace("doesnot", "does not").replace("onlyand", "only and").replace("availableevidence", "available evidence") final = re.sub(r"\s+", " ", f
  - L392 `proof`: package.get("v2_summary"), "drilldown_groups": package.get("drilldown_groups"), "limitations": [ "Source-truth records are the only proof authority for factual claims.", "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only, not proof.", "Do not invent physical part descriptions, page contents, or relationships.", ], "normal_intent_package": package.get("query_intent") in NORMAL_INTENTS_V32_2, "answer_styl
  - L43 `guidance`: mber_listing", "drilldown_covered_part_numbers_by_field", "page_records_lookup", "page_covered_part_numbers_lookup", "page_profile_summary", } GUIDANCE_ONLY_WARNING = ( "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only; " "source-truth evidence is required for factual claims." ) SAFETY_CONTRACT: Dict[str, Any] = { "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False
  - L60 `final_gate`: "uploads_to_opensearch": False, "raw_5tb_scan_at_query_time": False, "graph_rebuild_at_query_time": False, "llm_called": True, "response_is_final_gated": True, "llm_answer_writer_required": True, "source_truth_required_for_relationship_claims": True, "graph_leiden_guidance_only": True, "v2_summaries_guidance_only": True, "nomenclature_metadata_guidance_only": True, } def _now() -> int: return int(time.time()) def _read_json(path: str | Path | None) -> Dict[str, Any]:
  - L910 `chat/completions`: mpact", max_output_tokens: int = 180, max_prompt_evidence: int = 5, ) -> Tuple[str, Dict[str, Any]]: url = base_url.rstrip("/") + "/chat/completions" messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence) prompt_text = "\n".join(m.get("content", "") for m in messages) prompt_mode_norm = "compact" if (prompt_mode or "compact").lower().strip() != "full" else "full" payload = { "model": model,

### `tiff/trace_net_engineering_answer_runner_v1.py`
- Score: `226`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr, webui`
- Functions: _load_json(path)@L18; _write_json(path, data)@L27; _safe_int(value)@L33; _stage_status(stage)@L40; _first_record(manifest)@L46; _answer_text(composer)@L53; _quality_status(summary)@L57; build_engineering_answer_runner()@L88; check_engineering_answer_runner()@L299; _build_parser()@L351; main(argv)@L381; _check_parser()@L405; check_main(argv)@L425
- CLI args: --question, --v2-summary-guidance-index, --image-visual-evidence-pack, --raw-ocr-nomenclature-extractor, --table-route-evidence-packager, --table-exact-search-adapter, --output-dir, --max-guidance-pages, --min-planner-records, --min-required-routes, --min-guidance-context, --min-proof-context, --min-source-trace-ready, --min-answer-citations, --min-source-trace-ready-citations, --max-unsupported-claims, --max-summary-used-as-proof, --max-invalid-citations, --max-llava-only-part-identity-claims, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --require-quality-pass, --require-engineering-answer-ready, --runner, --output, --require-quality-pass, --require-engineering-answer-ready, --min-stage-passes
- Tiff imports: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner; from tiff.trace_net_engineering_answer_context_pack_v1 import build_engineering_answer_context_pack; from tiff.trace_net_engineering_answer_composer_v1 import build_engineering_answer_composer
- Has __main__ guard.
- Signal snippets:
  - L9 `context_pack`: ping, Optional, Sequence, Tuple from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner from tiff.trace_net_engineering_answer_context_pack_v1 import build_engineering_answer_context_pack from tiff.trace_net_engineering_answer_composer_v1 import build_engineering_answer_composer VERSION = "v1" MODULE = "trace_net_engineering_answer_runner_v1" STATUS_BUILT = "TRACE_NET_ENGINEERING_ANSWER_RUNNER_BUILT" STATUS_CHECKED = "TRACE_NET_ENGINEERING_ANSWER_RUNNER_QUALITY_CHECKED" def _load
  - L57 `proof`: g_answer_ready: bool, min_stage_passes: int, min_answer_citations: int, min_source_trace_ready_citations: int, max_unsupported_claims: int, max_summary_used_as_proof: int, max_invalid_citations: int, max_llava_only_part_identity_claims: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int) -> Tuple[str, List[str]]: failures: List[str] = [] if require_quality_pass and str(summary.get("runner_quality_status")) != "PASS": failures.append("run
  - L91 `guidance`: count above maximum") return ("PASS" if not failures else "FAIL", failures) def build_engineering_answer_runner( *, question: str, v2_summary_guidance_index: Any, output_dir: Any, image_visual_evidence_pack: Optional[Any] = None, raw_ocr_nomenclature_extractor: Optional[Any] = None, table_route_evidence_packager: Optional[Any] = None, table_exact_search_adapter: Optional[Any] = None, max_guidance_pages: int = 8, min_planner_records: int = 1, min_required_routes: int
  - L207 `qdrant`: answer_delivery")), "answer_permission_count": 0, "source_truth_mutation_allowed_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "opensearch_write_attempt_count": 0, "opensearch_upload_attempt_count": 0, "write_attempt_count": 0, "unsafe_record_count": 0, } # Stage failures are runner failures even before threshold checks. stage_failures = [f"{name} quality_status is {status}" for name, status in stage_quality
  - L208 `opensearch`: ssion_count": 0, "source_truth_mutation_allowed_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "opensearch_write_attempt_count": 0, "opensearch_upload_attempt_count": 0, "write_attempt_count": 0, "unsafe_record_count": 0, } # Stage failures are runner failures even before threshold checks. stage_failures = [f"{name} quality_status is {status}" for name, status in stage_quality_statuses.items() if status != "PASS"]

### `tiff/trace_net_e2e_live_query_pipeline_v15.py`
- Score: `225`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live Query Pipeline v15. This stage wraps the final-gated v14 WebUI answers in a live query-time orchestration endpoint. It is deliberately conservative: v15 proves the end-to-end control path that a WebUI query would take through retrieval, context engineering, Self-RAG, CRAG, prompt contract, reasoned draft, final answer gate, and WebUI response, while serving only already-final-gated answers. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild summar
- Classes: TraceNetLiveQueryPipelineHandler@L430 methods=['log_message', '_send_json', '_read_json', 'do_GET', 'do_POST']
- Functions: read_json(path)@L77; write_json(path, data)@L81; write_jsonl(path, rows)@L86; _summary(report)@L93; _ready_final_answers(webui_endpoint)@L98; _citations(answer)@L108; _answer_content(answer)@L125; build_pipeline_stages(answer)@L134; build_pipeline_record(answer, index)@L163; _quality_check(name, observed, op, expected)@L191; build_live_query_pipeline_manifest(webui_final_answer_endpoint)@L205; select_pipeline(query, pipelines)@L290; citations_text(citations)@L311; ask_live_query(query, state)@L324; make_chat_completion(query, ask_response, model)@L383; health_response(state)@L406; models_response(model)@L423; make_handler(state)@L427
- Routes: /health@L232, /v1/models@L233, /api/trace-net/ask@L234, /v1/chat/completions@L235, /health@L483, /api/trace-net/ask@L484, /v1/chat/completions@L485, /health@L456, /api/trace-net/ask@L466, /v1/models@L458
- Tiff imports: from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import QUALITY_PASS, clean_text, extract_query_from_chat_payload, select_final_answer
- Signal snippets:
  - L41 `self_rag`: TATUS = "E2E_LIVE_QUERY_PIPELINE_READY" QUALITY_FAIL = "FAIL" PIPELINE_STAGE_NAMES = [ "dynamic_retrieval", "tunnel_ranking", "context_pack", "self_rag_critic", "crag_corrector", "llm_prompt_contract", "reasoned_response_draft", "final_answer_gate", "webui_final_answer", ] CONTRACT: Dict[str, Any] = { "uses_prebuilt_final_answer_endpoint": True, "live_pipeline_orchestrates_query_time_path": True, "live_pipeline_serves_only_final_gated_answers": True, "unknown_qu
  - L6 `self-rag`: tration endpoint. It is deliberately conservative: v15 proves the end-to-end control path that a WebUI query would take through retrieval, context engineering, Self-RAG, CRAG, prompt contract, reasoned draft, final answer gate, and WebUI response, while serving only already-final-gated answers. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild summaries, rebuild graph, rerun table extraction, mutate source truth, or write to services. Queries that are not backed by a final-gated arti
  - L6 `crag`: dpoint. It is deliberately conservative: v15 proves the end-to-end control path that a WebUI query would take through retrieval, context engineering, Self-RAG, CRAG, prompt contract, reasoned draft, final answer gate, and WebUI response, while serving only already-final-gated answers. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild summaries, rebuild graph, rerun table extraction, mutate source truth, or write to services. Queries that are not backed by a final-gated artifact retur
  - L41 `critic`: E2E_LIVE_QUERY_PIPELINE_READY" QUALITY_FAIL = "FAIL" PIPELINE_STAGE_NAMES = [ "dynamic_retrieval", "tunnel_ranking", "context_pack", "self_rag_critic", "crag_corrector", "llm_prompt_contract", "reasoned_response_draft", "final_answer_gate", "webui_final_answer", ] CONTRACT: Dict[str, Any] = { "uses_prebuilt_final_answer_endpoint": True, "live_pipeline_orchestrates_query_time_path": True, "live_pipeline_serves_only_final_gated_answers": True, "unknown_queries_ret
  - L258 `repair`: LITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL status = READY_STATUS if quality_status == QUALITY_PASS else "E2E_LIVE_QUERY_PIPELINE_NEEDS_REPAIR" return { "schema_version": SCHEMA_VERSION, "status": "E2E_LIVE_QUERY_PIPELINE_BUILT", "e2e_live_query_pipeline_status": status, "quality_status": quality_status, "model": model, "host": host, "port": port, "base_url_windows": f"http://127.0.0.1:{port}/v1", "base_url_open_web

### `tiff/trace_net_dynamic_final_gate_execution_v1.py`
- Score: `224`
- Categories: `feedback, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Dynamic Final-Gate Execution v1. Read-only dynamic gate runner that takes Hybrid Retrieval v2 groups and tries to materialize final-answer candidates for arbitrary queries. It may approve a minimal final answer only when the selected dynamic retrieval groups have page lineage, citations, and answer-support authority. Otherwise it returns a retrieval-only, final-gate-required result. Safety contract: - Hybrid retrieval groups are possible evidence, not proof. - Dynamic final claims requ
- Functions: now_iso()@L94; as_text(value)@L98; as_bool(value, default)@L104; as_int(value, default)@L118; as_float(value, default)@L127; as_list(value)@L134; unique_texts(values)@L144; stable_json(value)@L148; stable_hash(value, length)@L152; read_json(path)@L156; write_json(path, payload)@L169; write_jsonl(path, rows)@L175; read_text_if_exists(path)@L186; quality_status(payload)@L195; normalize_query(value)@L208; page_number_from_page_id(page_id)@L212; sanitize_text(text, max_chars)@L219; query_results(report)@L231
- CLI args: --hybrid-v2-report, --final-answer-report, --final-answer-markdown, --query-file, --query, --output-dir, --max-claims, --min-claims-for-answer, --min-queries, --min-results, --require-hybrid-v2-quality-pass, --require-final-answer-quality-pass, --quality
- Has __main__ guard.
- Signal snippets:
  - L629 `critic`: mary"), Mapping) else summarize(report) checks: list[dict[str, Any]] = [] def add(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None: checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity}) add("dynamic_gate_query_count_min", as_int(summary.get("dynamic_gate_query_count")) >= min_queries, summary.get("dynamic_gate_query_count"), f">= {min_queries}") add("result_count_min", len(as_list(report.get(
  - L10 `proof`: r-support authority. Otherwise it returns a retrieval-only, final-gate-required result. Safety contract: - Hybrid retrieval groups are possible evidence, not proof. - Dynamic final claims require page/source lineage, citations, and answer-support buckets/authorities. - Feedback, communities, and categories are never proof. - No Postgres, Qdrant, OpenSearch, graph, citation, trust, or source writes occur. """ from __future__ import annotations import argparse import datetime as _dt import hashlib import html im
  - L28 `final_gate`: son import re from collections import Counter from pathlib import Path from typing import Any, Iterable, Mapping, Optional SCHEMA_VERSION = "trace_net_dynamic_final_gate_execution_v1" ALGORITHM = "trace_net_dynamic_retrieval_to_citation_authority_gate_v1" DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/dynamic_final_gate_execution") DEFAULT_HYBRID_V2_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json") DEFAULT_FINAL_ANSWER_REPORT = Path("local_data/
  - L14 `qdrant`: laims require page/source lineage, citations, and answer-support buckets/authorities. - Feedback, communities, and categories are never proof. - No Postgres, Qdrant, OpenSearch, graph, citation, trust, or source writes occur. """ from __future__ import annotations import argparse import datetime as _dt import hashlib import html import json import re from collections import Counter from pathlib import Path from typing import Any, Iterable, Mapping, Optional SCHEMA_VERSION = "trace_net_dynamic_final_gate_executi
  - L14 `opensearch`: quire page/source lineage, citations, and answer-support buckets/authorities. - Feedback, communities, and categories are never proof. - No Postgres, Qdrant, OpenSearch, graph, citation, trust, or source writes occur. """ from __future__ import annotations import argparse import datetime as _dt import hashlib import html import json import re from collections import Counter from pathlib import Path from typing import Any, Iterable, Mapping, Optional SCHEMA_VERSION = "trace_net_dynamic_final_gate_execution_v1" A

### `tiff/trace_net_e2e_context_pack_builder_v1.py`
- Score: `224`
- Categories: `context_pack, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E Context Pack Builder v1. Turns local ranked retrieval groups into retrieval-only context packs. The module intentionally does not answer questions, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime and later sufficiency/final-gate modules.
- Functions: _read_json(path)@L33; _write_json(path, data)@L41; _write_jsonl(path, rows)@L48; _safe_str(value)@L55; _as_bool(value, default)@L63; _num(value, default)@L73; _stable_id(prefix)@L82; _runtime_quality_pass(runtime)@L88; _runtime_ready(runtime)@L97; _get_retrieval_groups(runtime)@L108; _get_hits(group)@L119; _has_required_hit_keys(hit)@L129; build_context_item(query_id, query_index, hit_index, hit)@L133; build_context_pack(group, query_index)@L185; _count_bad(records, key)@L220; _quality_check(name, observed, expected, passed)@L224; evaluate_quality(report, args)@L233; build_report(runtime_path, output_dir)@L268
- CLI args: --e2e-hybrid-retrieval-runtime, --output-dir, --top-k, --min-source-retrieval-groups, --min-context-packs, --min-context-packs-with-items, --min-total-context-items, --min-pages-with-context-items, --min-citation-ready-items, --min-source-trace-ready-items, --min-field-count, --max-unsafe-records, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-source-runtime-quality-pass, --require-no-answer-permission, --quality
- Has __main__ guard.
- Signal snippets:
  - L21 `context_pack`: om typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" STATUS_BUILT = "E2E_CONTEXT_PACK_BUILT" READY_STATUS = "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE" REPORT_NAME = "trace_net_e2e_context_pack_builder_v1.json" QUALITY_NAME = "trace_net_e2e_context_pack_builder_v1_quality.json" CONTEXT_PACKS_JSONL_NAME = "trace_net_e2e_context_packs_v1.jsonl" CONTEXT_ITEMS_JSONL_NAME = "trace_net_e2e_context_items_v1.jsonl" INSPECT_MD_NAME = "trace_
  - L1 `context pack`: """TRACE-Net E2E Context Pack Builder v1. Turns local ranked retrieval groups into retrieval-only context packs. The module intentionally does not answer questions, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime and later sufficiency/final-gate modules. """ from __future__ import annotations import ar
  - L22 `final_gate`: ping, Optional, Sequence, Tuple QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" STATUS_BUILT = "E2E_CONTEXT_PACK_BUILT" READY_STATUS = "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE" REPORT_NAME = "trace_net_e2e_context_pack_builder_v1.json" QUALITY_NAME = "trace_net_e2e_context_pack_builder_v1_quality.json" CONTEXT_PACKS_JSONL_NAME = "trace_net_e2e_context_packs_v1.jsonl" CONTEXT_ITEMS_JSONL_NAME = "trace_net_e2e_context_items_v1.jsonl" INSPECT_MD_NAME = "trace_net_e2e_context_pack_builder_v1_inspect.md" REQUIRED_HIT_KEYS
  - L6 `qdrant`: etrieval groups into retrieval-only context packs. The module intentionally does not answer questions, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime and later sufficiency/final-gate modules. """ from __future__ import annotations import argparse import hashlib import json from dataclasses import dataclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple QUALITY_PASS =
  - L6 `opensearch`: l groups into retrieval-only context packs. The module intentionally does not answer questions, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime and later sufficiency/final-gate modules. """ from __future__ import annotations import argparse import hashlib import json from dataclasses import dataclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple QUALITY_PASS = "PASS"

### `tiff/trace_net_e2e_final_gate_smoke_v1.py`
- Score: `224`
- Categories: `context_pack, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E final gate smoke v1. This module consumes the E2E evidence sufficiency gate artifact and creates a local, deterministic final-gate smoke report. It is intentionally conservative: records can produce citation-backed response *drafts* for review, but they do not mutate source truth, write to runtime services, or grant proof authority.
- Functions: _read_json(path)@L45; _write_json(path, data)@L53; _write_jsonl(path, rows)@L60; _as_list(value)@L67; _bool(value)@L75; _safe_str(value, default)@L83; _slug(value)@L89; _collection_from(data, keys)@L94; _items_from_gate_record(record)@L102; _citation_id(query_id, item, index)@L134; _normalize_citation(query_id, item, index)@L140; _draft_response(user_query, citations, audit_only)@L165; _record_schema_complete(record)@L186; build_final_gate_smoke()@L190; evaluate_quality(summary)@L397; _write_inspect_md(path, report)@L458; add_common_args(parser)@L531; main(argv)@L554
- CLI args: --e2e-evidence-sufficiency-gate, --output-dir, --top-k, --min-citations-per-response, --min-source-traces-per-response, --min-source-gate-records, --min-final-gate-records, --min-safe-response-drafts, --min-citation-backed-response-drafts, --min-audit-or-safe-responses, --min-total-citations, --min-pages-cited, --min-field-count, --max-unsafe-records, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-source-sufficiency-quality-pass, --require-no-answer-permission, --quality
- Has __main__ guard.
- Signal snippets:
  - L214 `context_pack`: summary", {}) if isinstance(source.get("summary"), dict) else {} source_quality_pass = source.get("quality_status") == "PASS" or source_summary.get("source_context_pack_quality_pass") is True source_ready = _bool( source_summary.get("ready_for_final_gate_smoke") or source.get("evidence_sufficiency_contract", {}).get("ready_for_final_gate_smoke") ) gate_records = _collection_from(source, ("gate_records", "evidence_sufficiency_gate_records", "records")) final_records: List[Dict[s
  - L359 `context pack`: "final_gate_smoke_contract": { "purpose": "Create citation-backed final-gate smoke response drafts or audit-only responses from sufficiency-gated context packs.", "response_permission": "draft_for_review_or_audit_only", "answer_authority": "blocked_in_smoke_draft", "safety_note": "This smoke artifact demonstrates response shaping but does not grant direct answer/proof authority.", "can_answer_directly": False, "can_prove_claims": False,
  - L6 `proof`: onally conservative: records can produce citation-backed response *drafts* for review, but they do not mutate source truth, write to runtime services, or grant proof authority. """ from __future__ import annotations import argparse import json import re from collections import Counter from dataclasses import dataclass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple REPORT_FILENAME = "trace_net_e2e_final_gate_smoke_v1.json" QUALITY_FILENAME
  - L19 `final_gate`: ass from pathlib import Path from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple REPORT_FILENAME = "trace_net_e2e_final_gate_smoke_v1.json" QUALITY_FILENAME = "trace_net_e2e_final_gate_smoke_v1_quality.json" RECORDS_JSONL_FILENAME = "trace_net_e2e_final_gate_smoke_records_v1.jsonl" INSPECT_MD_FILENAME = "trace_net_e2e_final_gate_smoke_v1_inspect.md" STATUS_BUILT = "E2E_FINAL_GATE_SMOKE_BUILT" STATUS_READY = "E2E_FINAL_GATE_SMOKE_READY_FOR_API_OR_AUDIT_RESPONSE" DECISIO
  - L282 `qdrant`: on": "ranking_only_until_final_gate", "answer_authority": "blocked_in_smoke_draft", "writes_to_postgres": False, "writes_to_qdrant": False, "writes_to_opensearch": False, "uploads_to_opensearch": False, "unsafe_record": False, } record["schema_complete"] = _record_schema_complete(record) final_records.append(record) safe_response_draft_count = sum(1 for r in final_records if r["final_gate_decision"] == DECISION_SAFE

### `tiff/trace_net_engineering_engram_vector_loader_v1.py`
- Score: `224`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Engram Vector Loader v1. Artifact-only adapter that converts H17 Engram memory-layer atoms into a Qdrant-ready local vector manifest. This module does not connect to Qdrant, Postgres, OpenSearch, or any live service. It produces deterministic local records so CI and Git review can validate the vector payload shape before a future live loader is enabled.
- Classes: VectorLoaderConfig@L39 methods=[]
- Functions: utc_now_iso()@L47; read_json(path)@L51; write_json(path, data)@L60; stable_json_dumps(obj)@L68; normalize_text(text)@L72; atom_identifier(atom, index)@L78; infer_memory_layer(atom)@L86; infer_proof_role(atom, memory_layer)@L107; atom_to_text(atom)@L116; deterministic_hash_vector(text, dim)@L149; qdrant_point_id(atom_id)@L174; load_memory_atoms(memory_layers_manifest)@L178; make_vector_record(atom)@L197; safety_findings(records)@L236; layer_counts(records)@L264; build_vector_loader_manifest()@L275; check_vector_loader_manifest()@L391
- Signal snippets:
  - L1 `engram`: """TRACE-Net Engineering Engram Vector Loader v1. Artifact-only adapter that converts H17 Engram memory-layer atoms into a Qdrant-ready local vector manifest. This module does not connect to Qdrant, Postgres, OpenSearch, or any live service. It produces deterministic local records so CI and Git review can validate the vector payload shape before a future live loader is enabled. "
  - L94 `self-rag`: e", "description", "lesson", "failure_pattern", "repair_pattern")).lower() blob = f"{memory_type} {title} {text}" if any(t in blob for t in ("critic", "self-rag", "crag", "repair")): return "critic_memory" if any(t in blob for t in ("episode", "h13", "h14", "h15", "h16", "failure", "eval")): return "episodic_memory" if any(t in blob for t in ("style", "trait", "tone", "answer shape", "personality")): return "trait_memory" if any(t in blob for t in ("policy", "if user", "f
  - L94 `crag`: tion", "lesson", "failure_pattern", "repair_pattern")).lower() blob = f"{memory_type} {title} {text}" if any(t in blob for t in ("critic", "self-rag", "crag", "repair")): return "critic_memory" if any(t in blob for t in ("episode", "h13", "h14", "h15", "h16", "failure", "eval")): return "episodic_memory" if any(t in blob for t in ("style", "trait", "tone", "answer shape", "personality")): return "trait_memory" if any(t in blob for t in ("policy", "if user", "forbidden", "
  - L30 `critic`: ERSION = "v1" REQUIRED_MEMORY_LAYERS = ( "working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory", ) GUIDANCE_ONLY_PROOF_ROLES = {"guidance_only", "current_proof_context_only"} VECTOR_RECORD_STATUS = "ENGRAM_VECTOR_RECORD_READY" @dataclass(frozen=True) class VectorLoaderConfig: vector_dim: int = 64 collection_name: str = "trace_net_engineering_engram_memory_v1" encoder_name: str = "trace_net_hashing_encoder_v1" distance
  - L92 `repair`: om.get("title") or atom.get("atom_id") or "").lower() text = " ".join(str(atom.get(k) or "") for k in ("rule", "description", "lesson", "failure_pattern", "repair_pattern")).lower() blob = f"{memory_type} {title} {text}" if any(t in blob for t in ("critic", "self-rag", "crag", "repair")): return "critic_memory" if any(t in blob for t in ("episode", "h13", "h14", "h15", "h16", "failure", "eval")): return "episodic_memory" if any(t in blob for t in ("style", "trait", "tone", "answe

### `scripts/build_trace_net_e2e_crag_retrieval_corrector_v10.py`
- Score: `223`
- Categories: `crag, graph_vector, page, safety, self_rag, server`
- Functions: main()@L23
- CLI args: --self-rag-context-critic, --output-dir, --quality
- Tiff imports: from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import QUALITY_PASS, add_quality_args, build_crag_corrector_report, evaluate_quality, print_quality_result, read_json, write_report_files
- Has __main__ guard.
- Signal snippets:
  - L31 `self_rag`: quired=True) parser.add_argument("--quality", action="store_true") add_quality_args(parser) args = parser.parse_args() source = read_json(args.self_rag_context_critic) report = build_crag_corrector_report(source, source_path=args.self_rag_context_critic) quality_status, checks = evaluate_quality(report, args) report["quality_status"] = quality_status report["summary"]["quality_status"] = quality_status report["quality_checks"] = checks paths = write_report_files(report, args
  - L25 `self-rag`: def main() -> int: parser = argparse.ArgumentParser(description="Build TRACE-Net E2E CRAG retrieval corrector v10 artifact.") parser.add_argument("--self-rag-context-critic", required=True) parser.add_argument("--output-dir", required=True) parser.add_argument("--quality", action="store_true") add_quality_args(parser) args = parser.parse_args() source = read_json(args.self_rag_context_critic) report = build_crag_corrector_report(source, source_path=args.self_rag_context_critic)
  - L12 `crag`: s from pathlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import ( # noqa: E402 QUALITY_PASS, add_quality_args, build_crag_corrector_report, evaluate_quality, print_quality_result, read_json, write_report_files, ) def main() -> int: parser = argparse.ArgumentParser(description="Build TRACE-Net E2E CRAG retrieval corrector v10 artifact.") parser.add
  - L25 `critic`: int: parser = argparse.ArgumentParser(description="Build TRACE-Net E2E CRAG retrieval corrector v10 artifact.") parser.add_argument("--self-rag-context-critic", required=True) parser.add_argument("--output-dir", required=True) parser.add_argument("--quality", action="store_true") add_quality_args(parser) args = parser.parse_args() source = read_json(args.self_rag_context_critic) report = build_crag_corrector_report(source, source_path=args.self_rag_context_critic) quality_status
  - L52 `proof`: "retry_required_plan_count", "human_review_plan_count", "unresolved_plan_count", "corrective_action_count", "graph_summary_proof_violation_count", "answer_permission_count", "source_truth_mutation_allowed_count", ]: print(f" {key}: {summary.get(key, 0)}") for key, value in paths.items(): print(f" {key}: {value}") if args.quality and quality_status != QUALITY_PASS: return 1 return 0 if __name__ == "__main__": raise Sy

### `scripts/check_trace_net_e2e_self_rag_context_critic_v9_quality.py`
- Score: `223`
- Categories: `context_pack, crag, graph_vector, safety, self_rag, server`
- Functions: check(name, observed, expected, passed)@L9; main()@L13
- CLI args: --report-path, --min-context-packs, --min-context-critiques, --min-ready-contexts, --min-contexts-with-source-truth-evidence, --min-contexts-with-guidance-separation, --max-needs-crag-retry-count, --max-human-review-count, --max-graph-summary-proof-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --write-json
- Has __main__ guard.
- Signal snippets:
  - L37 `self_rag`: k_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", summary.get("context_pack_count", 0) >= args.min_context_packs), check("self_rag_critique_count", summary.get("self_rag_critique_count", 0), f">= {args.min_context_critiques}", summary.get("self_rag_critique_count", 0) >= args.min_context_critiques), check("ready_context_count", summary.get("ready_context_count", 0), f">= {args.min_ready_contexts}", summary.get("ready_context_count", 0) >= args.min_ready_contexts),
  - L14 `self-rag`: "observed": observed, "expected": expected, "passed": bool(passed)} def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net E2E Self-RAG Context Critic v9 quality") parser.add_argument("--report-path", required=True) parser.add_argument("--min-context-packs", type=int, default=1) parser.add_argument("--min-context-critiques", type=int, default=1) parser.add_argument("--min-ready-contexts", type=int, default=1) parser.add_argument("--min-contexts-with-source-truth-
  - L21 `crag`: th-evidence", type=int, default=1) parser.add_argument("--min-contexts-with-guidance-separation", type=int, default=1) parser.add_argument("--max-needs-crag-retry-count", type=int, default=None) parser.add_argument("--max-human-review-count", type=int, default=0) parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0) parser.add_argument("--max-answer-permission-count", type=int, default=0) parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=
  - L14 `critic`: rved, "expected": expected, "passed": bool(passed)} def main() -> int: parser = argparse.ArgumentParser(description="Check TRACE-Net E2E Self-RAG Context Critic v9 quality") parser.add_argument("--report-path", required=True) parser.add_argument("--min-context-packs", type=int, default=1) parser.add_argument("--min-context-critiques", type=int, default=1) parser.add_argument("--min-ready-contexts", type=int, default=1) parser.add_argument("--min-contexts-with-source-truth-evidence", type=i
  - L36 `context_pack`: mmary") or {}) checks = [ check("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == "PASS"), check("context_pack_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", summary.get("context_pack_count", 0) >= args.min_context_packs), check("self_rag_critique_count", summary.get("self_rag_critique_count", 0), f">= {args.min_context_critiques}", summary.get("self_rag_critique_count", 0) >= args.min_context_critiques), ch

### `tiff/trace_net_synthetic_incident_console_v1.py`
- Score: `223`
- Categories: `crag, engram, feedback, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net Synthetic Incident Console v1. A small local/admin incident console for testing TRACE-Net IT alert flows. The module is intentionally synthetic-only: - it does not write to Qdrant, OpenSearch, or source files; - it can store incidents in local JSONL or Postgres; - it does not mutate source truth; - it does not create answer-authoritative records; - local JSON/JSONL artifacts remain available as snapshots/reports.
- Classes: IncidentConsoleHandler@L990 methods=['_send_json', '_send_html', 'do_GET', 'do_POST', 'log_message']
- Functions: utc_now()@L275; stable_id(prefix, payload)@L279; ensure_dir(path)@L285; read_json(path)@L290; read_jsonl(path)@L296; write_json(path, payload)@L306; write_jsonl(path, rows)@L311; append_jsonl(path, row)@L316; postgres_schema_sql(table_name)@L322; write_postgres_schema_file(output_dir, table_name)@L371; _require_psycopg()@L378; init_postgres_storage(database_url)@L386; _postgres_row_from_incident(incident)@L396; save_incident_postgres(database_url, incident)@L428; load_incidents_postgres(database_url)@L472; clear_incidents_postgres(database_url)@L488; sanitize_message(message)@L500; artifact_paths(output_dir)@L512
- CLI args: --output-dir, --host, --port, --open, --build-only, --seed-samples, --clear, --storage-mode, --database-url, --postgres-table, --init-postgres
- Routes: </select>
        <select id="severity"><option>critical</option><option>warning</option><option selected>review</option><option>info</option></select>
        @L922, /api/health@L1018, /api/incidents@L1021, /api/simulate/random@L1024, /api/simulate/@L1028, /api/incidents/random@L1047, /api/incidents@L1056, /api/incidents/clear@L1073
- Has __main__ guard.
- Signal snippets:
  - L43 `critic`: "local" LOCAL_STORAGE_MODE = "local" POSTGRES_STORAGE_MODE = "postgres" DEFAULT_INCIDENT_TABLE = "trace_net_synthetic_incident_events" ALLOWED_SEVERITIES = {"critical", "warning", "review", "info"} SEVERITY_ORDER = {"critical": 0, "warning": 1, "review": 2, "info": 3} INCIDENT_ORIGINS: dict[str, dict[str, str]] = { "source_ingest": { "label": "Source ingest", "default_severity": "warning", "message": "Synthetic source-ingest issue: a new source file needs trace validation.", "
  - L68 `repair`: ion": { "label": "Table extraction", "default_severity": "warning", "message": "Synthetic table issue: normalized rows/cells need table repair review.", "recommended_action": "Review table rows/cells and compare part numbers against catalog/graph.", }, "visual_diagram": { "label": "Visual / diagram", "default_severity": "review", "message": "Synthetic visual issue: callout or visual part candidate needs verification.", "recommended_action": "Ve
  - L141 `proof`: thetic community issue: community hint must remain advisory-only.", "recommended_action": "Check community overlay and confirm community is not used as proof.", }, "human_review": { "label": "Human review", "default_severity": "review", "message": "Synthetic human-review issue: triage card needs reviewer action.", "recommended_action": "Open review triage and record a safe reviewer decision.", }, } RANDOM_INCIDENT_SCENARIOS: list[dict[str, str]] = [ {
  - L6 `qdrant`: ent Console v1. A small local/admin incident console for testing TRACE-Net IT alert flows. The module is intentionally synthetic-only: - it does not write to Qdrant, OpenSearch, or source files; - it can store incidents in local JSONL or Postgres; - it does not mutate source truth; - it does not create answer-authoritative records; - local JSON/JSONL artifacts remain available as snapshots/reports. """ from __future__ import annotations import argparse import hashlib import html import json import os import ran
  - L6 `opensearch`: ole v1. A small local/admin incident console for testing TRACE-Net IT alert flows. The module is intentionally synthetic-only: - it does not write to Qdrant, OpenSearch, or source files; - it can store incidents in local JSONL or Postgres; - it does not mutate source truth; - it does not create answer-authoritative records; - local JSON/JSONL artifacts remain available as snapshots/reports. """ from __future__ import annotations import argparse import hashlib import html import json import os import random impo

### `scripts/check_trace_net_e2e_live_relationship_final_gated_endpoint_v31_quality.py`
- Score: `222`
- Categories: `final_gate, page, safety, server`
- Functions: main()@L14
- CLI args: --report-path, --min-sample-queries, --min-sample-successes, --min-relationship-final-gate-applied, --min-relationship-records, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import check_report
- Has __main__ guard.
- Signal snippets:
  - L11 `final_gate`: le__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) import argparse from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import check_report def main() -> None: parser = argparse.ArgumentParser(description="Check TRACE-Net live relationship final-gated endpoint v31 quality.") parser.add_argument("--report-path", required=True, type=Path) parser.add_argument("--min-sample-queries", type=int, default=0) parser.add_argument("--min-sample
  - L36 `source_truth_mutation_allowed`: ip_records, max_post_gate_issue_count=args.max_post_gate_issue_count, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, write_json=args.write_json, ) print("TRACE-Net E2E Live Relationship Final-Gated Endpoint v31 Quality") print(f" quality_status: {report['quality_status']}") for check in report.get("quality_che
  - L35 `answer_permission`: nal_gate_applied, min_relationship_records=args.min_relationship_records, max_post_gate_issue_count=args.max_post_gate_issue_count, max_answer_permission_count=args.max_answer_permission_count, max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed, require_no_answer_permission=args.require_no_answer_permission, write_json=args.write_json, ) print("TRACE-Net E2E Live Relationship Final-Gated Endpoint v31 Quality") print(f" quality_status:

### `scripts/serve_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Score: `222`
- Categories: `final_gate, page, server, webui`
- Functions: parse_args()@L12; main()@L20
- CLI args: --live-webui-final-gated-gemma-endpoint, --host, --port
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import read_json, serve
- Has __main__ guard.
- Signal snippets:
  - L9 `final_gate`: REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import read_json, serve def parse_args(): p = argparse.ArgumentParser(description="Serve TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24.") p.add_argument("--live-webui-final-gated-gemma-endpoint", required=True) p.add_argument("--host", default="127.0.0.1") p.add_argument("--port", type=int, default=8

### `tiff/trace_net_e2e_live_llm_prompt_contract_v21.py`
- Score: `222`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: load_json(path)@L22; write_json(path, data)@L26; write_jsonl(path, rows)@L31; _as_list(value)@L38; _first_list(obj, candidate_keys)@L48; _truthy_bool(value)@L67; _get_path(obj, path, default)@L75; _context_packs(data)@L84; _evaluations(data)@L98; _pack_id(pack, fallback_index)@L113; _eval_pack_id(row)@L123; _evaluation_index(evals)@L133; _evidence_items(pack)@L141; _graph_guidance_items(pack)@L158; _summary_guidance_items(pack)@L177; _aggregation_box(pack)@L196; _answer_rules(pack)@L204; _evidence_page(item)@L212
- CLI args: --min-context-packs, --min-prompt-contracts, --min-ready-prompt-contracts, --min-total-prompt-messages, --min-contracts-with-source-truth-evidence, --min-contracts-with-graph-guidance, --min-contracts-with-v2-summary-guidance, --min-contracts-with-aggregation-or-cap-disclosure, --min-contracts-with-self-rag-ready, --min-contracts-with-crag-no-retry, --min-contracts-with-answer-rules, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --executed-plan-context-pack, --live-self-rag-crag-evaluator, --output-dir, --max-evidence-items, --quality, --report-path, --write-json
- Has __main__ guard.
- Signal snippets:
  - L102 `self_rag`: for r in rows if isinstance(r, Mapping)] def _evaluations(data: Any) -> List[Mapping[str, Any]]: rows = _first_list( data, [ "self_rag_crag_records", "self_rag_evaluations", "live_self_rag_crag_evaluations", "evaluations", "records", "context_evaluations", ], ) return [r for r in rows if isinstance(r, Mapping)] def _pack_id(pack: Mapping[str, Any], fallback_index: int = 0) -> str: return str(
  - L480 `self-rag`: lines.append(_compact_aggregation_json(aggregation)) else: lines.append("- No cap metadata supplied.") lines.append("") lines.append("SELF-RAG / CRAG STATUS:") lines.append(_compact_json(_normalize_evaluation_for_prompt(evaluation), max_chars=1800)) lines.append("") lines.append("ANSWER RULES:") if rules: lines.append(_compact_json(rules, max_chars=1200)) else: lines.append("- Cite every factual claim from source-truth evidence only.") lines.app
  - L102 `crag`: rows if isinstance(r, Mapping)] def _evaluations(data: Any) -> List[Mapping[str, Any]]: rows = _first_list( data, [ "self_rag_crag_records", "self_rag_evaluations", "live_self_rag_crag_evaluations", "evaluations", "records", "context_evaluations", ], ) return [r for r in rows if isinstance(r, Mapping)] def _pack_id(pack: Mapping[str, Any], fallback_index: int = 0) -> str: return str( pack.get(
  - L13 `repair`: ce, Tuple VERSION = "v21" MODULE = "trace_net_e2e_live_llm_prompt_contract_v21" STATUS_READY = "E2E_LIVE_LLM_PROMPT_CONTRACT_READY_FOR_LLM_DRAFT" STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_PROMPT_CONTRACT_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" SYSTEM_MESSAGE = """You are the TRACE-Net answer writer. Write only from the provided TRACE-Net context pack. Source-truth evidence may support factual claims. Graph/Leiden guidance, v2 summaries, route metadata, vector hints, and aggregation metadata are guidan
  - L84 `context_pack`: y = obj for key in path: if not isinstance(cur, Mapping) or key not in cur: return default cur = cur[key] return cur def _context_packs(data: Any) -> List[Mapping[str, Any]]: rows = _first_list( data, [ "context_packs", "executed_plan_context_packs", "context_pack_records", "packs", "records", ], ) return [r for r in rows if isinstance(r, Mapping)] def _evaluations(data: Any) -> Li

### `scripts/build_trace_net_e2e_llm_assisted_query_planner_v17.py`
- Score: `221`
- Categories: `crag, graph_vector, page, planner, safety, server, table_visual_ocr`
- Functions: parse_args()@L14; main()@L38
- CLI args: --live-dynamic-fallback, --page-context-v2, --leiden-communities, --community-navigation-metadata-bridge, --route-dispatch-manifest, --table-exact-search-adapter, --output-dir, --min-query-plans, --min-validated-query-plans, --min-plans-with-v2-summary-guidance, --min-plans-with-leiden-guidance, --min-plans-with-source-truth-fields, --min-allowed-tunnel-validations, --max-invalid-tunnel-count, --max-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Tiff imports: from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_report, load_json, write_report_files; from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, DEFAULT_STATUS_READY, DEFAULT_STATUS_NEEDS_REPAIR, evaluate_quality
- Has __main__ guard.
- Signal snippets:
  - L51 `repair`: rting threshold helpers lazily. from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, DEFAULT_STATUS_READY, DEFAULT_STATUS_NEEDS_REPAIR, evaluate_quality thresholds = QualityThresholds( min_query_plans=args.min_query_plans, min_validated_query_plans=args.min_validated_query_plans, min_plans_with_v2_summary_guidance=args.min_plans_with_v2_summary_guidance, min_plans_with_leiden_guidance=args.min_plans_with_leiden_guidance, min_plans_with_sou
  - L30 `proof`: in-allowed-tunnel-validations", type=int, default=20) parser.add_argument("--max-invalid-tunnel-count", type=int, default=0) parser.add_argument("--max-proof-authority-violations", type=int, default=0) parser.add_argument("--max-answer-permission-count", type=int, default=0) parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0) parser.add_argument("--require-no-answer-permission", action="store_true") parser.add_argument("--quality", action="store_true") return
  - L25 `guidance`: y-plans", type=int, default=5) parser.add_argument("--min-validated-query-plans", type=int, default=5) parser.add_argument("--min-plans-with-v2-summary-guidance", type=int, default=5) parser.add_argument("--min-plans-with-leiden-guidance", type=int, default=5) parser.add_argument("--min-plans-with-source-truth-fields", type=int, default=5) parser.add_argument("--min-allowed-tunnel-validations", type=int, default=20) parser.add_argument("--max-invalid-tunnel-count", type=int, default=0) p
  - L42 `page_context`: args() def main() -> int: args = parse_args() report = build_report( live_dynamic_fallback=load_json(args.live_dynamic_fallback, {}), page_context_v2=load_json(args.page_context_v2, {}), leiden_communities=load_json(args.leiden_communities, {}), community_navigation_metadata_bridge=load_json(args.community_navigation_metadata_bridge, {}), route_dispatch_manifest=load_json(args.route_dispatch_manifest, {}), table_exact_search_adapter=load_json(args.table_exac
  - L11 `query_planner`: REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_report, load_json, write_report_files def parse_args() -> argparse.Namespace: parser = argparse.ArgumentParser(description="Build TRACE-Net E2E LLM-assisted query planner v17 artifact.") parser.add_argument("--live-dynamic-fallback", required=True) parser.add_argument("--page-context-v2", required=True) parser

### `scripts/serve_trace_net_e2e_live_gemma_answer_writer_endpoint_v32.py`
- Score: `221`
- Categories: `final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: Handler@L62 methods=['log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: _send_json(handler, data, status)@L21; main(argv)@L33; log_message(self, fmt)@L63; do_OPTIONS(self)@L66; do_GET(self)@L69; do_POST(self)@L106
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --host, --port, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --temperature, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens
- Routes: /health@L70, /v1/models@L101, /v1/chat/completions@L111
- Tiff imports: from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v32 import MODEL_ID, TraceNetGemmaAnswerWriterV32, _extract_messages_user_text
- Has __main__ guard.
- Signal snippets:
  - L58 `final_gate`: page_context_v2, leiden_communities=ns.leiden_communities, relationship_router_hardening=ns.relationship_router_hardening, relationship_final_gate_hardener=ns.relationship_final_gate_hardener, ) metadata = writer._page_metadata() class Handler(BaseHTTPRequestHandler): def log_message(self, fmt: str, *args: Any) -> None: return def do_OPTIONS(self) -> None: _send_json(self, {"ok": True}) def do_GET(self) -> None: if se
  - L129 `openwebui`: ode=ns.llm_prompt_mode, llm_max_output_tokens=ns.llm_max_output_tokens, ) # Preserve requested model id for OpenWebUI compatibility. resp["model"] = MODEL_ID _send_json(self, resp) except Exception as exc: safe = { "id": "chatcmpl-tracenet-v32-error", "object": "chat.completion", "created": 0, "model": MODEL_ID,
  - L111 `chat/completions`: .rfile.read(length).decode("utf-8", errors="replace") payload = json.loads(raw) if raw else {} if self.path.rstrip("/") != "/v1/chat/completions": _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404) return query = _extract_messages_user_text(payload) if not query: _send_json(self, {"error": "No user message found"}, status=400) return resp
  - L42 `ollama`: fault=None) ap.add_argument("--host", default="127.0.0.1") ap.add_argument("--port", type=int, default=8027) ap.add_argument("--llm-mode", default="ollama") ap.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1") ap.add_argument("--llm-model", default="gemma4:26b") ap.add_argument("--llm-api-key", default="ollama") ap.add_argument("--request-timeout", type=int, default=240) ap.add_argument("--temperature", type=float, default=0.0) ap.add_argument("--llm-answer-mode
  - L55 `page_context`: ) ns = ap.parse_args(argv) writer = TraceNetGemmaAnswerWriterV32.from_paths( table_exact_search_adapter=ns.table_exact_search_adapter, page_context_v2=ns.page_context_v2, leiden_communities=ns.leiden_communities, relationship_router_hardening=ns.relationship_router_hardening, relationship_final_gate_hardener=ns.relationship_final_gate_hardener, ) metadata = writer._page_metadata() class Handler(BaseHTTPRequestHandler): def log_message(self, fmt:

### `tiff/trace_net_engineering_query_planner_v1.py`
- Score: `221`
- Categories: `context_pack, graph_vector, page, planner, safety, server, table_visual_ocr`
- Functions: _load_json(path)@L74; _write_json(path, payload)@L83; _write_csv(path, records)@L89; _norm_text(value)@L117; extract_entities(question)@L121; classify_task(question, entities)@L151; _guidance_records(index)@L181; _tokenize(s)@L192; score_guidance_record(record, question, entities)@L197; _is_specific_entity_query(entities, task_type)@L237; _has_strong_entity_reason(reasons)@L249; select_guidance_pages(index, question, entities, max_guidance_pages, task_type)@L254; _proof_requirements(task_type, entities)@L301; _optional_routes(task_type)@L319; build_plan_record(question, index, max_guidance_pages)@L329; summarize(records, source_index)@L373; _quality(summary)@L403; build_engineering_query_planner()@L422
- CLI args: --question, --v2-summary-guidance-index, --output-dir, --max-guidance-pages, --min-planner-records, --min-required-routes, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --planner, --output, --require-quality-pass, --min-planner-records, --min-required-routes, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L399 `context_pack`: _attempt")), "write_attempt_count": 0, "unsafe_record_count": sum(1 for r in records if r.get("unsafe_record")), "ready_for_engineering_context_pack": True, } def _quality(summary: Mapping[str, Any], *, min_planner_records: int, min_required_routes: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int, require_no_summary_only_answer: bool = True) -> Tuple[str, List[str]]: failures: List[str] = [] if int(summary.get("p
  - L46 `proof`: ctivity", "fit", "replacement approval", "installation safety", ] ROUTE_CAPABILITIES = { "exact_part_lookup": ["exact_part_number", "table_ocr_proof", "graph_leiden_neighbors", "answer_quality_gate"], "figure_item_lookup": ["figure_or_item", "table_ocr_proof", "multi_route_quality_gate"], "visual_part_identification": ["image_or_diagram", "table_ocr_proof", "raw_ocr_nomenclature", "image_route_quality_gate"], "part_family_expansion": ["part_family", "graph_leiden_neighbors", "table_ocr_
  - L53 `guidance`: ison_question": ["multi_entity_retrieval", "table_ocr_proof", "graph_leiden_neighbors", "engineering_quality_gate"], "procedure_question": ["manual_section_guidance", "ocr_text_support", "engineering_quality_gate"], "manual_section_summary": ["v2_summary_guidance", "ocr_text_support", "summary_not_proof_gate"], "general_engineering_question": ["v2_summary_guidance", "ocr_text_support", "engineering_quality_gate"], "unknown_or_insufficient_evidence": ["v2_summary_guidance", "clarify_or_retrieve_more"
  - L362 `qdrant`: st not be used as proof", "answer_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "unsafe_record": False, } record["entities_json"] = json.dumps(entities, ensure_ascii=False) record["required_routes_json"] = json.dumps(required_routes, ensure_ascii=False) record["optional_routes_json"] = json.dumps(r
  - L363 `opensearch`: er_permission": False, "source_truth_mutation_allowed": False, "postgres_write_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False, "opensearch_upload_attempt": False, "unsafe_record": False, } record["entities_json"] = json.dumps(entities, ensure_ascii=False) record["required_routes_json"] = json.dumps(required_routes, ensure_ascii=False) record["optional_routes_json"] = json.dumps(record["optional_routes"], ensure_ascii=

### `scripts/build_trace_net_engineering_engram_prompt_retrieval_injector_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L30
- CLI args: --vector-retriever, --output-dir, --max-atoms-per-query, --max-prompt-chars, --min-queries, --min-injected-atoms, --require-guidance-only, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_retrieval_injector_manifest
- Has __main__ guard.
- Signal snippets:
  - L12 `engram`: ath REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_retrieval_injector_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Prompt Retrieval Injector v1 artifact") p.add_argument("--vector-retriever", required=True) p.add_argument("--output-dir", required=Tru
  - L23 `guidance`: lt=1800) p.add_argument("--min-queries", type=int, default=1) p.add_argument("--min-injected-atoms", type=int, default=1) p.add_argument("--require-guidance-only", action="store_true") p.add_argument("--require-no-answer-permission", action="store_true") p.add_argument("--max-unsafe", type=int, default=0) p.add_argument("--max-write-attempts", type=int, default=0) return p def main(argv=None) -> int: args = build_arg_parser().parse_args(argv) result = build_prompt_retrieval_inj
  - L40 `answer_permission`: min_queries=args.min_queries, min_injected_atoms=args.min_injected_atoms, require_guidance_only=args.require_guidance_only, require_no_answer_permission=args.require_no_answer_permission, max_unsafe=args.max_unsafe, max_write_attempts=args.max_write_attempts, ) summary = result.get("summary", {}) print(f"status={result.get('status')}") print(f"quality_status={result.get('quality_status')}") print(f"query_count={summary.get('query_count')}") print(f"pr

### `scripts/build_trace_net_engineering_engram_vector_loader_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L27
- CLI args: --memory-layers, --output-dir, --collection-name, --vector-dim, --min-records, --require-all-layers, --max-unsafe
- Tiff imports: from tiff.trace_net_engineering_engram_vector_loader_v1 import build_vector_loader_manifest
- Has __main__ guard.
- Signal snippets:
  - L12 `engram`: athlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_vector_loader_v1 import build_vector_loader_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram vector loader manifest v1") p.add_argument("--memory-layers", required=True) p.add_argument("--output-dir", required=True) p.add_argument("--collection-nam
  - L41 `qdrant`: summary = manifest.get("summary", {}) print(f"status={manifest.get('status')}") print(f"quality_status={manifest.get('quality_status')}") print(f"qdrant_ready_record_count={summary.get('qdrant_ready_record_count')}") print(f"vector_dim={summary.get('vector_dim')}") print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}") print(f"answer_permission_count={summary.get('answer_permission_count')}") print(f"write_attempt_count={summary.get('write_attempt_count')}") print(f"o
  - L44 `answer_permission`: ady_record_count')}") print(f"vector_dim={summary.get('vector_dim')}") print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}") print(f"answer_permission_count={summary.get('answer_permission_count')}") print(f"write_attempt_count={summary.get('write_attempt_count')}") print(f"output={Path(args.output_dir) / 'trace_net_engineering_engram_vector_loader_v1.json'}") return 0 if manifest.get("quality_status") == "PASS" else 1 if __name__ == "__main__": raise SystemExit(main())

### `scripts/build_trace_net_engineering_engram_vector_retriever_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L30
- CLI args: --vector-loader, --output-dir, --queries-jsonl, --query, --top-k, --min-queries, --min-results-per-query, --require-all-layers, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_vector_retriever_v1 import build_vector_retriever_manifest
- Has __main__ guard.
- Signal snippets:
  - L12 `engram`: ath REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_engineering_engram_vector_retriever_v1 import build_vector_retriever_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Vector Retriever v1 artifact") p.add_argument("--vector-loader", required=True) p.add_argument("--output-dir", required=True) p.add_argument("--queri
  - L51 `answer_permission`: f"total_retrieved_item_count={summary.get('total_retrieved_item_count')}") print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}") print(f"answer_permission_count={summary.get('answer_permission_count')}") print(f"write_attempt_count={summary.get('write_attempt_count')}") print(f"output={result.get('output_path')}") return 0 if result.get("quality_status") == "PASS" else 1 if __name__ == "__main__": raise SystemExit(main())

### `scripts/check_trace_net_engineering_engram_postgres_feedback_ledger_v1.py`
- Score: `220`
- Categories: `engram, feedback, page, safety, server`
- Functions: build_arg_parser()@L7; main(argv)@L19
- CLI args: --feedback-ledger, --min-feedback-records, --min-candidate-records, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import check_feedback_ledger_manifest
- Has __main__ guard.
- Signal snippets:
  - L4 `engram`: from __future__ import annotations import argparse from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import check_feedback_ledger_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Postgres feedback ledger v1") p.add_argument("--feedback-ledger", required=True) p.add_argument("--min-feedback-records", type=int, default=5)
  - L4 `postgres`: from __future__ import annotations import argparse from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import check_feedback_ledger_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Postgres feedback ledger v1") p.add_argument("--feedback-ledger", required=True) p.add_argument("--min-feedback-records", type=int, default=5) p.add_
  - L26 `answer_permission`: args.min_feedback_records, min_candidate_records=args.min_candidate_records, require_quality_pass=args.require_quality_pass, require_no_answer_permission=args.require_no_answer_permission, max_unsafe=args.max_unsafe, max_write_attempts=args.max_write_attempts, ) print("status=" + result["status"]) print("quality_status=" + result["quality_status"]) print("feedback_record_count=" + str(result["feedback_record_count"])) print("candidate_record_count=" + str(

### `scripts/check_trace_net_engineering_engram_qdrant_adapter_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L7; main()@L20
- CLI args: --qdrant-adapter, --min-records, --min-local-queries, --require-quality-pass, --require-all-layers, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import check_qdrant_adapter_manifest
- Has __main__ guard.
- Signal snippets:
  - L4 `engram`: from __future__ import annotations import argparse from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import check_qdrant_adapter_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Qdrant adapter artifact.") p.add_argument("--qdrant-adapter", required=True) p.add_argument("--min-records", type=int, default=1) p.add_argument("--min-l
  - L4 `qdrant`: from __future__ import annotations import argparse from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import check_qdrant_adapter_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Qdrant adapter artifact.") p.add_argument("--qdrant-adapter", required=True) p.add_argument("--min-records", type=int, default=1) p.add_argument("--min-local-qu
  - L30 `answer_permission`: nt("qdrant_read_attempt_count=" + str(result["qdrant_read_attempt_count"])) print("unsafe_finding_count=" + str(result["unsafe_finding_count"])) print("answer_permission_count=" + str(result["answer_permission_count"])) print("write_attempt_count=" + str(result["write_attempt_count"])) if result.get("quality_failures"): print("quality_failures=" + str(result["quality_failures"])) return 0 if result["quality_status"] == "PASS" else 1 if __name__ == "__main__": raise SystemExit(main(

### `scripts/check_trace_net_engineering_engram_vector_loader_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L16; main(argv)@L29
- CLI args: --vector-loader, --min-records, --require-all-layers, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts, --output
- Tiff imports: from tiff.trace_net_engineering_engram_vector_loader_v1 import check_vector_loader_manifest, write_json
- Has __main__ guard.
- Signal snippets:
  - L13 `engram`: athlib import Path ROOT = Path(__file__).resolve().parents[1] if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT)) from tiff.trace_net_engineering_engram_vector_loader_v1 import check_vector_loader_manifest, write_json def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram vector loader manifest v1") p.add_argument("--vector-loader", required=True) p.add_argument("--min-records", type=int, default=1) p.add_argumen
  - L45 `qdrant`: lt) summary = result.get("summary", {}) print(f"status={result.get('status')}") print(f"quality_status={result.get('quality_status')}") print(f"qdrant_ready_record_count={summary.get('qdrant_ready_record_count')}") print(f"memory_layer_counts={summary.get('memory_layer_counts')}") print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}") print(f"answer_permission_count={summary.get('answer_permission_count')}") print(f"write_attempt_count={summary.get('write_attempt_count'
  - L36 `answer_permission`: min_records=args.min_records, require_all_layers=args.require_all_layers, require_quality_pass=args.require_quality_pass, require_no_answer_permission=args.require_no_answer_permission, max_unsafe=args.max_unsafe, max_write_attempts=args.max_write_attempts, ) if args.output: write_json(args.output, result) summary = result.get("summary", {}) print(f"status={result.get('status')}") print(f"quality_status={result.get('quality_status')}") print

### `scripts/check_trace_net_engineering_engram_vector_retriever_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L28
- CLI args: --vector-retriever, --min-queries, --min-results-per-query, --require-all-layers, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_vector_retriever_v1 import check_vector_retriever_manifest
- Has __main__ guard.
- Signal snippets:
  - L12 `engram`: ath REPO_ROOT = Path(__file__).resolve().parents[1] if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT)) from tiff.trace_net_engineering_engram_vector_retriever_v1 import check_vector_retriever_manifest def build_arg_parser() -> argparse.ArgumentParser: p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Vector Retriever v1 artifact") p.add_argument("--vector-retriever", required=True) p.add_argument("--min-queries", type=int, default=1) p.add_argumen
  - L36 `answer_permission`: uery=args.min_results_per_query, require_all_layers=args.require_all_layers, require_quality_pass=args.require_quality_pass, require_no_answer_permission=args.require_no_answer_permission, max_unsafe=args.max_unsafe, max_write_attempts=args.max_write_attempts, ) print(f"status={result.get('status')}") print(f"quality_status={result.get('quality_status')}") print(f"query_count={result.get('query_count')}") print(f"retrieval_record_count={result.get('retriev

### `tiff/trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.py`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Doc: TRACE-Net Engineering Engram Answer-Smoke Overlay Integration Gate v1. Artifact-only integration gate for carrying H24/H25 retrieved Engram overlays toward the real engineering LLM answer smoke builder without making the full 30-question path the default debug loop. Safety contract: - no live LLM calls - no Postgres writes - no Qdrant reads/writes - no OpenSearch reads/writes/uploads - no source-truth mutation - no answer permission - Engram overlays are behavior guidance only, never proof
- Functions: _read_json(path)@L42; _write_json(path, data)@L49; _write_jsonl(path, rows)@L54; _split_ids(value)@L61; _summary_count(summary, key)@L72; _by_question_id(records)@L79; _overlay_records_by_question(overlay_smoke)@L88; _h25_records_by_question(h25_smoke)@L92; _source_records_by_question(source_answer_smoke)@L96; _safe_bool(rec, key)@L100; build_overlay_integration_gate()@L104; check_overlay_integration_gate()@L311; build_arg_parser()@L349; check_arg_parser()@L368; main(argv)@L380; check_main(argv)@L395
- CLI args: --overlay-smoke, --overlay-llm-smoke, --source-answer-smoke, --output-dir, --question-ids, --max-overlay-chars, --min-gate-records, --min-h25-good-answers, --require-h24-quality-pass, --require-h25-quality-pass, --require-source-answer-smoke-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts, --integration-gate, --min-gate-records, --min-overlay-map-records, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.
- Signal snippets:
  - L1 `engram`: """TRACE-Net Engineering Engram Answer-Smoke Overlay Integration Gate v1. Artifact-only integration gate for carrying H24/H25 retrieved Engram overlays toward the real engineering LLM answer smoke builder without making the full 30-question path the default debug loop. Safety contract: - no live LLM calls - no Postgres writes - no Qdrant reads/writes - no OpenSearch reads/writes/u
  - L14 `proof`: Qdrant reads/writes - no OpenSearch reads/writes/uploads - no source-truth mutation - no answer permission - Engram overlays are behavior guidance only, never proof """ from __future__ import annotations import argparse import json from dataclasses import dataclass from pathlib import Path from typing import Any, Iterable, Mapping MODULE = "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1" VERSION = "v1" SAFETY_CONTRACT = { "answer_permission": False, "source_truth_mutation_allowed"
  - L14 `guidance`: Postgres writes - no Qdrant reads/writes - no OpenSearch reads/writes/uploads - no source-truth mutation - no answer permission - Engram overlays are behavior guidance only, never proof """ from __future__ import annotations import argparse import json from dataclasses import dataclass from pathlib import Path from typing import Any, Iterable, Mapping MODULE = "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1" VERSION = "v1" SAFETY_CONTRACT = { "answer_permission": False, "source_tr
  - L10 `qdrant`: ering LLM answer smoke builder without making the full 30-question path the default debug loop. Safety contract: - no live LLM calls - no Postgres writes - no Qdrant reads/writes - no OpenSearch reads/writes/uploads - no source-truth mutation - no answer permission - Engram overlays are behavior guidance only, never proof """ from __future__ import annotations import argparse import json from dataclasses import dataclass from pathlib import Path from typing import Any, Iterable, Mapping MODULE = "trace_net_engin
  - L11 `opensearch`: ilder without making the full 30-question path the default debug loop. Safety contract: - no live LLM calls - no Postgres writes - no Qdrant reads/writes - no OpenSearch reads/writes/uploads - no source-truth mutation - no answer permission - Engram overlays are behavior guidance only, never proof """ from __future__ import annotations import argparse import json from dataclasses import dataclass from pathlib import Path from typing import Any, Iterable, Mapping MODULE = "trace_net_engineering_engram_answer_smok

### `tiff/trace_net_e2e_live_deterministic_answer_planner_v28.py`
- Score: `217`
- Categories: `crag, final_gate, graph_vector, page, planner, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live Deterministic Answer Planner + Drilldown v28. v28 extends the v27 stage-timing fast path with an explicit deterministic answer planner. The goal is to keep operational/source-truth questions fast while reserving the local LLM for relationship or synthesis work. New response modes: - exact_single_value - exact_missing_value - field_listing - capped_listing - drilldown_request - relationship_or_synthesis_needs_llm The module never scans raw 5TB source data, rebuilds graph artifa
- Classes: TraceNetV28Handler@L874 methods=['_send_json', 'log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: read_json(path)@L64; write_json(path, payload)@L68; write_jsonl(path, rows)@L72; _now()@L76; _elapsed_ms(start)@L80; _to_int(value, default)@L84; _sum_timing(stage_timings_ms)@L88; _occurrence_count(row)@L98; _deduped_occurrence_count(rows)@L102; _polish_answer_text(text)@L106; normalize_query(query)@L119; detect_query_plan_v28(query)@L124; _compact(value)@L160; _target_matches_value(target, value)@L164; apply_strict_target_filter(plan, retrieval)@L172; _target_value(plan)@L236; _direct_evidence(retrieval)@L240; infer_response_mode(query, plan, retrieval)@L245
- Routes: /health@L42, /v1/models@L42, /v1/chat/completions@L42, /v1/models@L898, /v1/chat/completions@L904, /health@L895
- Tiff imports: from tiff import trace_net_e2e_live_orchestrator_endpoint_v25; from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27
- Signal snippets:
  - L38 `repair`: _v28" VERSION = "v28" MODEL_ID = "trace-net-e2e-live-deterministic-planner-gemma-v28" STATUS_READY = "E2E_LIVE_DETERMINISTIC_ANSWER_PLANNER_READY" STATUS_NEEDS_REPAIR = "E2E_LIVE_DETERMINISTIC_ANSWER_PLANNER_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"] DEFAULT_SAMPLE_QUERIES = [ "Find part number 120-36833-503", "Find part number DOES-NOT-EXIST-999", "Where is manual reference 25-21-00 used?", "Where is manual re
  - L17 `proof`: ans raw 5TB source data, rebuilds graph artifacts, reruns OCR, mutates source truth, or writes to Postgres/Qdrant/OpenSearch. Source-truth records are the only proof authority. Graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only. v28.1 also polishes deterministic answer spacing and preserves raw/collapsed match metadata for exact filtered responses. """ from __future__ import annotations import json import re import time import uuid from collections import Counter from
  - L18 `guidance`: rites to Postgres/Qdrant/OpenSearch. Source-truth records are the only proof authority. Graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only. v28.1 also polishes deterministic answer spacing and preserves raw/collapsed match metadata for exact filtered responses. """ from __future__ import annotations import json import re import time import uuid from collections import Counter from http.server import BaseHTTPRequestHandler, HTTPServer from pathlib import Path from typin
  - L417 `final_gate`: target_occurrence_count, "collapsed_duplicate_record_count": collapsed_duplicate_count, } return answer, meta def standard_safety(response_is_final_gated: bool = True, llm_called: bool = False) -> Dict[str, Any]: base = v25.standard_safety(response_is_final_gated=response_is_final_gated, llm_called=llm_called) base["deterministic_planner_can_skip_llm"] = True base["drilldown_supported"] = True return base def run_live_query_v28( query: str, state: Mapping[str, Any], l
  - L42 `chat/completions`: DS_REPAIR = "E2E_LIVE_DETERMINISTIC_ANSWER_PLANNER_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"] DEFAULT_SAMPLE_QUERIES = [ "Find part number 120-36833-503", "Find part number DOES-NOT-EXIST-999", "Where is manual reference 25-21-00 used?", "Where is manual reference 99-99-99 used?", "Search table text ILLUSTRATED PARTS LIST", "Search table text THIS TEXT DOES NOT EXIST", "What maintenance manual pages

### `tiff/trace_net_e2e_live_dynamic_fallback_v16.py`
- Score: `217`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live Dynamic Fallback v16. v16 is the next step after the v15 live query pipeline. v15 proves the full final-gated control path for a prebuilt set of final-gated answers. v16 adds a conservative dynamic fallback for new exact table/evidence queries: * first, reuse any v15 final-gated pipeline answer; * otherwise, search the prebuilt table exact-search adapter locally; * if citation/source-trace-ready source-truth evidence is found, build a deterministic final-gated answer from that
- Classes: TraceNetLiveDynamicFallbackHandler@L603 methods=['log_message', '_send_json', '_read_json', 'do_GET', 'do_POST']
- Functions: write_json(path, data)@L78; write_jsonl(path, rows)@L83; _summary(report)@L90; _ready_pipelines(live_pipeline)@L95; _exact_docs(table_exact_search_adapter)@L100; normalize_query(text)@L123; classify_query(query)@L129; _field_allowed(intent, field)@L150; rank_exact_docs(query, docs)@L160; _citation(doc, index)@L231; _format_dynamic_answer(query, intent, evidence)@L245; build_dynamic_fallback_record(query, docs, index)@L285; build_probe_queries(docs, existing_queries)@L330; _quality_check(name, observed, op, expected)@L395; build_live_dynamic_fallback_manifest(live_query_pipeline, table_exact_search_adapter)@L409; ask_live_dynamic_fallback(query, state)@L504; make_chat_completion(query, ask_response, model)@L555; health_response(state)@L579
- Routes: /health@L440, /v1/models@L441, /api/trace-net/ask@L442, /v1/chat/completions@L443, /health@L657, /api/trace-net/ask@L658, /v1/chat/completions@L659, /health@L630, /api/trace-net/ask@L640, /v1/models@L632
- Tiff imports: from tiff.trace_net_e2e_live_query_pipeline_v15 import PIPELINE_STAGE_NAMES, QUALITY_PASS, ask_live_query, build_pipeline_stages, citations_text, clean_text, extract_query_from_chat_payload, read_json, select_pipeline
- Signal snippets:
  - L466 `repair`: TY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL status = READY_STATUS if quality_status == QUALITY_PASS else "E2E_LIVE_DYNAMIC_FALLBACK_NEEDS_REPAIR" return { "schema_version": SCHEMA_VERSION, "status": "E2E_LIVE_DYNAMIC_FALLBACK_BUILT", "e2e_live_dynamic_fallback_status": status, "quality_status": quality_status, "model": model, "host": host, "port": port, "base_url_windows": f"http://127.0.0.1:{port}/v1", "base_url_open
  - L63 `proof`: e, "reruns_embeddings": False, "reruns_page_summaries": False, "reruns_graph_build": False, "reruns_table_extraction": False, "graph_is_not_proof_authority": True, "summaries_are_not_source_truth": True, "guidance_box_is_not_source_truth": True, "evidence_box_is_source_truth": True, "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False, "postgres_write_attempt_count": 0, "qdrant_write_attemp
  - L65 `guidance`: "reruns_graph_build": False, "reruns_table_extraction": False, "graph_is_not_proof_authority": True, "summaries_are_not_source_truth": True, "guidance_box_is_not_source_truth": True, "evidence_box_is_source_truth": True, "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "opensearch_write_attempt_count": 0, "opensearch_upl
  - L53 `final_gate`: ipeline": True, "uses_prebuilt_table_exact_search_adapter": True, "dynamic_fallback_searches_source_truth_exact_documents": True, "dynamic_fallback_final_gates_exact_source_truth_only": True, "unknown_queries_return_audit_limitation": True, "endpoint_does_not_call_llm": True, "endpoint_does_not_rerun_retrieval_artifact_build": True, "reruns_ocr": False, "reruns_page_classification": False, "reruns_embeddings": False, "reruns_page_summaries": False, "reruns_graph_build": F
  - L443 `chat/completions`: {"method": "POST", "path": "/api/trace-net/ask", "purpose": "TRACE-Net v16 live dynamic fallback ask endpoint"}, {"method": "POST", "path": "/v1/chat/completions", "purpose": "OpenAI-compatible chat wrapper"}, ] checks = [ _quality_check("existing_pipeline_query_count", len(pipelines), ">=", min_existing_pipeline_queries), _quality_check("exact_search_document_count", len(docs), ">=", min_exact_search_documents), _quality_check("dynamic_fallback_probe_count", len(fall

### `tiff/trace_net_e2e_live_orchestrator_endpoint_v25.py`
- Score: `217`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live Orchestrator Endpoint v25. This module provides a live OpenAI-compatible endpoint that runs a compact TRACE-Net query-time pipeline for new questions: user query -> query plan -> exact source-truth retrieval -> graph/summary guidance -> compact prompt -> optional local LLM draft -> deterministic final gate repair -> final-gated WebUI answer. The implementation remains local-only and retrieval-only: it does not scan raw 5TB corpus data, rebuild graph artifacts, rerun OCR, mutat
- Classes: TraceNetV25Handler@L953 methods=['_send_json', 'log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: read_json(path)@L50; write_json(path, payload)@L58; write_jsonl(path, rows)@L63; normalize_query(query)@L70; normalize_value(value)@L74; compact_value(value)@L78; citation_like_count(text)@L82; _to_int(value, default)@L86; _to_bool(value)@L93; first_str(row, keys)@L97; load_exact_docs(table_exact_search_adapter_path)@L108; read_jsonl(path)@L125; load_optional_page_summaries(page_context_v2_path)@L137; load_optional_leiden(leiden_path)@L168; _extract_requested_part_number(query, canonical_part_numbers)@L201; detect_query_plan(query)@L219; doc_field(doc)@L275; doc_value(doc)@L279
- Routes: /health@L36, /v1/models@L36, /v1/chat/completions@L36, /chat/completions@L532, /v1/models@L977, /v1/chat/completions@L983, /health@L974
- Signal snippets:
  - L7 `repair`: : user query -> query plan -> exact source-truth retrieval -> graph/summary guidance -> compact prompt -> optional local LLM draft -> deterministic final gate repair -> final-gated WebUI answer. The implementation remains local-only and retrieval-only: it does not scan raw 5TB corpus data, rebuild graph artifacts, rerun OCR, mutate source truth, or write to Postgres/Qdrant/OpenSearch. The LLM output is treated as draft text only; the final answer is rebuilt from direct source-truth evidence and cap/disclosure met
  - L478 `context pack`: Dict[str, str]]: direct = retrieval.get("direct_evidence") or [] nearby = retrieval.get("nearby_context") or [] lines: List[str] = ["TRACE-NET LIVE CONTEXT PACK", "", "SOURCE-TRUTH EVIDENCE (direct proof authority):"] if direct: for row in direct: occ = f" occurrence_count={row.get('occurrence_count')}" if _to_int(row.get("occurrence_count"), 1) > 1 else "" lines.append(f"- [{row.get('citation_id')}] page={row.get('page_id')} field={row.get('field_name')} value={row.g
  - L267 `proof`: nical) if intent == "part_number" else True, "strict_target_match_required": bool(target), "authority": { "source_truth_evidence_is_proof": True, "graph_leiden_guidance_is_proof": False, "v2_summary_guidance_is_proof": False, "nearby_context_is_direct_proof": False, }, } def doc_field(doc: Mapping[str, Any]) -> str: return first_str(doc, ("field_name", "field", "field_role", "normalized_field_name")) def doc_value(doc: Mapping[str,
  - L6 `guidance`: atible endpoint that runs a compact TRACE-Net query-time pipeline for new questions: user query -> query plan -> exact source-truth retrieval -> graph/summary guidance -> compact prompt -> optional local LLM draft -> deterministic final gate repair -> final-gated WebUI answer. The implementation remains local-only and retrieval-only: it does not scan raw 5TB corpus data, rebuild graph artifacts, rerun OCR, mutate source truth, or write to Postgres/Qdrant/OpenSearch. The LLM output is treated as draft text only; t
  - L652 `final_gate`: n(prompt_messages), "llm_mode": mode, "llm_status": llm_status, "llm_draft_text": draft, "llm_metadata": llm_metadata, "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS" if final_meta["answerable"] else "LIVE_ORCHESTRATOR_AUDIT_ONLY", "final_answer": final_answer, "final_answer_ready_for_webui": bool(final_meta["answerable"]), "unsupported_claim_count": final_meta["unsupported_claim_count"], "citation_like_count": final_meta["citation_lik

### `tiff/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py`
- Score: `217`
- Categories: `crag, final_gate, graph_vector, page, planner, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27. This module wraps the v25 live orchestrator with two production-facing additions: 1. Stage timing telemetry for query planning, retrieval, graph/v2 guidance, prompt packing, LLM draft generation, and final-gate repair. 2. A deterministic fast path for simple exact lookups and audit-only misses. The fast path is intentionally conservative. It skips the local LLM only when the retrieved direct source-truth evidence is already enough to 
- Classes: TraceNetV27Handler@L527 methods=['_send_json', 'log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: read_json(path)@L47; write_json(path, payload)@L51; write_jsonl(path, rows)@L55; _now()@L59; _elapsed_ms(start)@L63; _to_int(value, default)@L67; _to_bool(value)@L71; _sum_timing(stage_timings_ms)@L75; should_use_fast_path(plan, retrieval, fast_path_mode)@L85; run_live_query_v27(query, state, llm_mode, request_timeout)@L110; standard_safety(response_is_final_gated, llm_called)@L228; build_state(table_exact_search_adapter_path, output_dir, page_context_v2_path, leiden_communities_path, host, port, model_id, llm_mode)@L234; evaluate_quality(state, min_exact_search_documents, min_endpoint_routes, min_sample_queries, min_sample_successes, min_stage_timing_records, min_fast_path_samples, max_sample_llm_calls)@L328; attach_quality(state, quality_status, quality_checks)@L375; _state_for_file(state)@L382; render_markdown_report(state)@L391; write_endpoint_files(state, output_dir)@L450; load_state_for_serving(report_path)@L465
- Routes: /health@L35, /v1/models@L35, /v1/chat/completions@L35, /v1/models@L551, /v1/chat/completions@L557, /health@L548
- Tiff imports: from tiff import trace_net_e2e_live_orchestrator_endpoint_v25
- Signal snippets:
  - L6 `repair`: oduction-facing additions: 1. Stage timing telemetry for query planning, retrieval, graph/v2 guidance, prompt packing, LLM draft generation, and final-gate repair. 2. A deterministic fast path for simple exact lookups and audit-only misses. The fast path is intentionally conservative. It skips the local LLM only when the retrieved direct source-truth evidence is already enough to build the final gated answer, or when a strict exact lookup has zero direct evidence and must return an audit-only answer. Graph/Lei
  - L5 `guidance`: Path v27. This module wraps the v25 live orchestrator with two production-facing additions: 1. Stage timing telemetry for query planning, retrieval, graph/v2 guidance, prompt packing, LLM draft generation, and final-gate repair. 2. A deterministic fast path for simple exact lookups and audit-only misses. The fast path is intentionally conservative. It skips the local LLM only when the retrieved direct source-truth evidence is already enough to build the final gated answer, or when a strict exact lookup has ze
  - L188 `final_gate`: ms["llm_draft_ms"] = _elapsed_ms(stage) stage = _now() final_answer, final_meta = v25.build_final_answer(query, plan, retrieval) stage_timings_ms["final_gate_ms"] = _elapsed_ms(stage) total_latency_ms = _elapsed_ms(total_start) stage_timings_ms["total_request_ms"] = total_latency_ms non_llm_ms = round(total_latency_ms - float(stage_timings_ms.get("llm_draft_ms", 0.0)), 3) answerable = bool(final_meta["answerable"]) return { "user_query": query, "query_plan": plan,
  - L35 `chat/completions`: AIR = "E2E_LIVE_ORCHESTRATOR_STAGE_TIMING_FASTPATH_NEEDS_REPAIR" QUALITY_PASS = "PASS" QUALITY_FAIL = "FAIL" _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"] DEFAULT_SAMPLE_QUERIES = [ "Find part number 120-36833-503", "Find part number DOES-NOT-EXIST-999", "Where is manual reference 25-21-00 used?", "Where is manual reference 99-99-99 used?", "Search table text ILLUSTRATED PARTS LIST", "Search table text THIS TEXT DOES NOT EXIST", ] FAST_PATH_INTENTS = {"part_numbe
  - L165 `ollama`: _metadata = {"fast_path_reason": fast_path_reason} stage_timings_ms["llm_draft_ms"] = _elapsed_ms(stage) else: try: if mode == "ollama": draft, llm_metadata = v25.call_ollama_chat( prompt_messages, str(state.get("llm_base_url") or "http://127.0.0.1:11434/v1"), str(state.get("llm_model") or "gemma4:26b"), str(state.get("llm_api_key") or "ollama"), float(state.get("temper

## Highest-signal tests

### `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- Score: `307`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L7; test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch)@L13; test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path)@L113; test_checklist_text_includes_reasons()@L121; test_bridge_precreates_stage_report_directories_for_stage_builders(tmp_path, monkeypatch)@L130; fake_query_planner()@L19; fake_blueprint()@L28; fake_pack_builder()@L37; fake_self_rag()@L58; fake_crag()@L72; write_without_mkdir(path, payload)@L134; fake_query_planner()@L139; fake_blueprint()@L145; fake_pack_builder()@L152; fake_self_rag()@L168; fake_crag()@L179
- Tiff imports: from tiff import trace_net_webui_self_rag_crag_bridge_v1

### `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_visual_context.py`
- Score: `299`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L7; test_bridge_marks_visual_route_used_from_webui_visual_context_bridge(tmp_path, monkeypatch)@L13; test_quality_check_can_require_visual_context_bridge(tmp_path)@L109; fake_query_planner()@L41; fake_blueprint()@L47; fake_pack_builder()@L53; fake_self_rag()@L68; fake_crag()@L74
- Tiff imports: from tiff import trace_net_webui_self_rag_crag_bridge_v1

### `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Score: `291`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, webui`
- Functions: test_quality_check_passes_for_required_brain_gates(tmp_path)@L7; test_quality_check_fails_when_self_rag_not_used(tmp_path)@L46; test_quality_check_supports_explicit_tool_status_requirements(tmp_path)@L80
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality

### `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_script_imports.py`
- Score: `259`
- Categories: `self_rag, server, webui`
- Functions: test_build_script_imports()@L5; test_check_script_imports()@L15

### `tests/unit/test_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Score: `235`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _prompt_injector(tmp_path)@L11; _h22_smoke(tmp_path)@L39; test_bridge_records_map_to_answer_runner_questions(tmp_path)@L67; test_build_bridge_passes_with_h22(tmp_path)@L79; test_check_bridge_artifact(tmp_path)@L97; test_h20_prompt_wording_is_safe_boundary()@L117; test_missing_boundary_is_unsafe(tmp_path)@L147
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import build_answer_runner_retrieval_bridge_manifest, build_bridge_records, check_answer_runner_retrieval_bridge_manifest

### `tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Score: `233`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server`
- Functions: _args()@L10; sample_pack(capped)@L32; test_evaluate_pack_ready_with_cap_disclosure()@L54; test_evaluate_pack_weak_without_evidence()@L62; test_build_report_passes_quality(tmp_path)@L71; test_graph_proof_authority_violation_blocks()@L84; test_v20_reads_v19_evidence_box_items_shape()@L92
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import build_report, evaluate_pack; from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import evaluate_pack

### `tests/unit/test_trace_net_engineering_engram_self_rag_critic_v1.py`
- Score: `216`
- Categories: `context_pack, crag, engram, page, safety, self_rag, server`
- Functions: test_good_record_passes()@L11; test_unknown_part_partial_is_expected_boundary()@L27; test_missing_citations_with_proof_context_needs_repair()@L40; _source_manifest(tmp_path)@L56; test_build_and_check_manifest(tmp_path)@L84
- Tiff imports: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import build_self_rag_critic_manifest, check_self_rag_critic_manifest, critique_answer_record

### `tests/unit/test_trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Score: `211`
- Categories: `engram, graph_vector, page, safety, self_rag, server, webui`
- Functions: _bridge(tmp_path)@L12; _smoke(tmp_path)@L54; test_overlay_text_contains_boundaries()@L67; test_build_overlay_records_maps_question()@L74; test_build_manifest_passes(tmp_path)@L83; test_check_manifest(tmp_path)@L102; test_missing_bridge_record_is_unsafe(tmp_path)@L122
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import build_answer_runner_prompt_overlay_smoke_manifest, build_overlay_records, build_overlay_text, check_answer_runner_prompt_overlay_smoke_manifest

### `tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20_script_imports.py`
- Score: `209`
- Categories: `self_rag, server, table_visual_ocr`
- Functions: test_live_self_rag_crag_evaluator_v20_scripts_importable()@L7

### `tests/unit/test_trace_net_engineering_engram_crag_repair_v1.py`
- Score: `208`
- Categories: `crag, engram, page, safety, self_rag, server`
- Functions: _write(path, data)@L12; _answer_smoke(tmp_path)@L17; _critic(tmp_path, repair)@L27; test_critic_recommends_repair()@L38; test_build_crag_no_repairs_passes(tmp_path)@L44; test_repair_candidate_fails_when_attempts_not_allowed(tmp_path)@L61; test_artifact_repair_allowed(tmp_path)@L75; test_check_crag(tmp_path)@L90
- Tiff imports: from tiff.trace_net_engineering_engram_crag_repair_v1 import build_artifact_repair_answer, build_crag_repair_manifest, check_crag_repair_manifest, critic_recommends_repair

### `tests/unit/test_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Score: `203`
- Categories: `context_pack, engram, page, safety, server, webui`
- Functions: _write_json(path, data)@L12; _fixtures(tmp_path)@L18; test_build_prompt_contains_overlay_boundary(tmp_path)@L75; test_grade_catches_unsupported_claim()@L90; test_artifact_build_passes(tmp_path)@L96; test_check_artifact(tmp_path)@L119; test_missing_overlay_fails(tmp_path)@L145
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import build_answer_runner_overlay_llm_smoke, build_overlay_llm_prompt, check_answer_runner_overlay_llm_smoke, grade_h25_answer

### `tests/unit/test_trace_net_page_context_pack_v3.py`
- Score: `198`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`
- Functions: sample_inputs()@L8; test_extract_query_entities_page_and_part()@L43; test_build_page_context_pack_selects_requested_pages()@L50; test_exact_part_lookup_adds_proof_first_context()@L66; test_visual_is_guidance_only_not_proof()@L82; test_reasoning_work_order_allows_synthesis_but_blocks_overclaiming()@L97; test_quality_gate_passes_safe_pack()@L113; test_resolves_numeric_page_from_embedded_source_page_id_without_page_number()@L128; test_nested_manifest_records_are_discovered()@L144; test_unresolved_requested_page_gets_safe_placeholder_not_empty_pack()@L160; test_route_manifest_source_locator_and_route_priority_are_attached()@L173; test_unproven_table_record_becomes_route_guidance_not_proof()@L193; test_graph_citation_map_can_add_source_file_guidance()@L215; test_quality_gate_can_require_guidance_and_source_locators()@L234; test_numeric_page_label_does_not_override_source_page_number()@L257; test_label_qualified_lookup_can_still_find_numeric_page_label()@L285
- Tiff imports: from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, check_page_context_pack_v3_quality, extract_query_entities; from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3; from tiff.trace_net_page_context_pack_v3 import build_index

### `tests/unit/test_trace_net_e2e_live_llm_final_gate_v23.py`
- Score: `195`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: prompt_report()@L9; draft_report()@L107; thresholds()@L117; test_v23_repairs_v2_summary_and_nearby_context_issues()@L136; test_v23_writes_report_files(tmp_path)@L152; test_v23_markdown_mentions_repaired_drafts()@L162
- Tiff imports: from tiff.trace_net_e2e_live_llm_final_gate_v23 import build_report, render_markdown, write_report_files

### `tests/unit/test_trace_net_openwebui_page_context_bridge_v1.py`
- Score: `186`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: FakeResp@L292 methods=['__enter__', '__exit__', 'read']
- Functions: sample_pack()@L26; test_extract_page_numbers_requires_page_cue_and_avoids_part_numbers()@L102; test_should_use_page_context()@L112; test_latest_user_question_reads_last_user_message()@L118; test_render_page_context_binder_contains_reasoning_and_safety()@L128; test_enrich_openai_messages_inserts_binder_after_system()@L138; test_count_pack_records()@L151; test_quality_checker_accepts_safe_preflight_manifest()@L158; test_quality_checker_rejects_missing_binder()@L174; test_artifact_paths_reports_missing_paths(tmp_path)@L188; test_context_bridge_fallback_detects_simulated_off_topic_response()@L194; test_context_bridge_fallback_accepts_page_aligned_real_response()@L216; test_render_page_context_fallback_answer_uses_requested_pages_and_limits()@L238; test_script_wrappers_bootstrap_repo_root_for_direct_execution()@L247; test_normalize_ollama_openai_base_url_adds_v1()@L275; test_ollama_native_api_base_url_removes_v1()@L283; test_call_native_ollama_uses_api_chat_with_think_disabled(monkeypatch)@L289; test_render_native_page_answer_messages_requires_sections_and_pages()@L330
- Routes: http://127.0.0.1:11434/api/chat@L322, http://127.0.0.1:11434/v1/chat/completions@L278, http://127.0.0.1:11434/v1/chat/completions@L286
- Tiff imports: from tiff.trace_net_openwebui_page_context_bridge_v1 import PageContextArtifactPaths, PageContextBridgeHandler, PageContextBridgeServer, count_pack_records, enrich_openai_messages, extract_page_numbers, latest_user_question, render_page_context_binder, render_page_context_fallback_answer, should_use_context_bridge_fallback, should_use_page_context; from tiff.trace_net_openwebui_page_context_bridge_v1 import build_native_failure_fallback_response, build_native_page_context_response, call_native_ollama_openai_chat, normalize_ollama_openai_base_url, ollama_native_api_base_url, render_native_page_answer_messages; tiff.trace_net_openwebui_page_context_bridge_v1

### `tests/unit/test_trace_net_engineering_engram_qdrant_adapter_v1.py`
- Score: `177`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _vector_loader(tmp_path)@L14; test_normalize_records_enforces_guidance_boundary(tmp_path)@L51; test_local_search_returns_ranked_results(tmp_path)@L60; test_build_qdrant_adapter_dry_run_passes(tmp_path)@L68; test_check_qdrant_adapter(tmp_path)@L88
- Tiff imports: from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import build_qdrant_adapter_manifest, check_qdrant_adapter_manifest, local_search, normalize_qdrant_records

### `tests/unit/test_trace_net_engineering_engram_unified_runtime_gate_v1.py`
- Score: `177`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _write(path, data)@L11; _fixtures(tmp_path)@L17; test_build_unified_runtime_gate_passes(tmp_path)@L80; test_check_unified_runtime_gate_passes(tmp_path)@L104; test_answer_permission_fails_when_required(tmp_path)@L119; test_runtime_records_include_proof_boundary(tmp_path)@L133
- Tiff imports: from tiff.trace_net_engineering_engram_unified_runtime_gate_v1 import build_unified_runtime_gate, check_unified_runtime_gate

### `tests/unit/test_trace_net_engineering_engram_vector_retriever_v1.py`
- Score: `177`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _record(atom_id, layer, text, dim)@L15; _loader(tmp_path)@L36; test_retrieve_for_query_ranks_relevant_layer()@L56; test_build_manifest_passes_with_all_layers(tmp_path)@L68; test_check_manifest_passes(tmp_path)@L88; test_answer_permission_is_failure(tmp_path)@L114
- Tiff imports: from tiff.trace_net_engineering_engram_vector_retriever_v1 import REQUIRED_LAYERS, build_vector_retriever_manifest, check_vector_retriever_manifest, hashing_vector, retrieve_for_query

### `tests/unit/test_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Score: `171`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr`
- Functions: _write_json(path, data)@L13; test_apply_relationship_gate_repairs_graph_as_proof()@L18; test_apply_relationship_gate_preserves_safe_metadata_answer()@L32; test_chat_completion_response_exposes_relationship_gate_trace()@L47; test_build_and_check_report_with_tiny_artifacts(tmp_path)@L59
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import MODEL_ID, apply_relationship_final_gate, make_chat_completion_response, build_report, check_report

### `tests/unit/test_trace_net_engineering_engram_postgres_feedback_ledger_v1.py`
- Score: `169`
- Categories: `crag, engram, feedback, page, safety, self_rag, server, table_visual_ocr`
- Functions: _write(path, data)@L13; _fixtures(tmp_path)@L18; test_schema_has_tables()@L47; test_build_feedback_ledger_manifest(tmp_path)@L53; test_check_feedback_ledger_manifest(tmp_path)@L76; test_live_postgres_write_is_gated_and_counts_as_write_attempt(tmp_path)@L91
- Tiff imports: from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import build_feedback_ledger_manifest, check_feedback_ledger_manifest, SCHEMA_SQL

### `tests/unit/test_trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py`
- Score: `167`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Classes: Result@L150 methods=[]
- Functions: _bridge_payload(status)@L15; test_merge_bridge_trace_adds_e2e_visible_signals(tmp_path)@L44; test_answer_question_runs_bridge_before_existing_answer(monkeypatch, tmp_path)@L65; test_bridge_failure_blocks_answer_when_required(monkeypatch, tmp_path)@L101; test_bridge_failure_record_is_safe()@L127; test_run_bridge_preflight_uses_cli_fallback_when_in_process_bridge_raises(monkeypatch, tmp_path)@L138; test_ensure_bridge_stage_dirs_creates_all_nested_stage_outputs(tmp_path)@L172; test_run_bridge_preflight_precreates_stage_dirs_before_in_process_call(monkeypatch, tmp_path)@L186; test_stage_writer_parent_dir_patch_makes_blueprint_jsonl_safe(tmp_path)@L213; fake_bridge(question, config, output_dir)@L68; fake_answer_question_v13()@L72; fake_bridge(question, config, output_dir)@L102; fake_answer_question_v13()@L105; boom()@L141; fake_run(cmd, text, capture_output)@L144; fake_bridge()@L191
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1 import LLMConfig; from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import BridgeConfig, _ensure_bridge_stage_dirs, _patch_stage_writer_parent_dirs_for_in_process_bridge, answer_question_with_bridge_v1, bridge_failure_record, merge_bridge_trace; tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1; from tiff import trace_net_engineering_context_pack_blueprint_v1

### `tests/unit/test_trace_net_e2e_crag_retrieval_corrector_v10.py`
- Score: `164`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Classes: Args@L99 methods=[]; Args@L178 methods=[]
- Functions: sample_ready_critic()@L16; sample_weak_critic()@L43; test_build_crag_report_no_retry_ready()@L76; test_build_crag_report_retry_ready_for_intent_mismatch()@L87; test_quality_pass_for_ready_report()@L97; test_build_and_check_scripts(tmp_path)@L117; test_weak_report_quality_can_require_corrective_action()@L176
- Tiff imports: from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import NO_RETRY_STATUS, RETRY_READY_STATUS, build_crag_corrector_report, evaluate_quality

### `tests/unit/test_trace_net_engineering_context_self_rag_check_v1.py`
- Score: `164`
- Categories: `context_pack, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Functions: _write(path, payload)@L11; _context_pack_payload()@L15; test_self_rag_marks_ready_and_crag_retry(tmp_path)@L97; test_quality_checker_passes(tmp_path)@L119
- Tiff imports: from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check, check_engineering_context_self_rag_check_quality

### `tests/unit/test_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Score: `163`
- Categories: `crag, final_gate, graph_vector, page, server, webui`
- Functions: sample_v23(path)@L17; test_v24_build_endpoint_state_and_quality(tmp_path)@L42; test_v24_match_and_chat_completion(tmp_path)@L55; test_v24_health_models_and_write_files(tmp_path)@L69
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import MODEL_ID, attach_quality, build_endpoint_state, chat_completion_response, evaluate_quality, health_response, match_final_answer, openai_models_response, write_endpoint_files

### `tests/unit/test_trace_net_engineering_engram_memory_layers_v1.py`
- Score: `161`
- Categories: `crag, engram, page, safety, self_rag, server, table_visual_ocr`
- Functions: test_infer_memory_layer_examples()@L15; test_build_memory_layer_manifest_covers_all_layers(tmp_path)@L23; test_validate_rejects_non_guidance_non_working_atom()@L44; test_check_memory_layer_manifest_writes_quality_check(tmp_path)@L56
- Tiff imports: from tiff.trace_net_engineering_engram_memory_layers_v1 import MEMORY_LAYERS, build_memory_layer_manifest, check_memory_layer_manifest, infer_memory_layer, validate_layered_manifest

### `tests/unit/test_trace_net_engineering_webui_answer_server_v1_3_bridge_v1_visual_context.py`
- Score: `159`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _visual_bridge_payload()@L12; test_bridge_cli_command_passes_webui_visual_context_bridge_path(tmp_path)@L66; test_bridge_status_payload_exposes_visual_context_trace()@L80; test_manifest_quality_requires_visual_context_bridge_when_requested(tmp_path)@L95; test_manifest_quality_fails_when_visual_context_missing(tmp_path)@L132
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import BridgeConfig, _bridge_cli_command, _bridge_status_payload, check_manifest_bridge_v1

### `tests/unit/test_trace_net_e2e_self_rag_context_critic_v9.py`
- Score: `156`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: sample_pack(field_name, intent)@L16; test_critique_context_pack_ready()@L73; test_critique_context_pack_detects_intent_mismatch_for_crag()@L81; test_critique_context_pack_detects_unsafe_guidance_for_human_review()@L88; test_build_report_quality_pass(tmp_path)@L95; test_write_report_files(tmp_path)@L113
- Tiff imports: from tiff.trace_net_e2e_self_rag_context_critic_v9 import CRITIC_NEEDS_CRAG_RETRY, CRITIC_NEEDS_HUMAN_REVIEW, CRITIC_READY, build_self_rag_context_critic, critique_context_pack, write_report_files

### `tests/unit/test_trace_net_engineering_context_crag_retry_plan_v1.py`
- Score: `156`
- Categories: `context_pack, page, planner, safety, self_rag, server, table_visual_ocr`
- Functions: _write(path, payload)@L11; _self_rag_payload()@L15; test_build_crag_retry_plan_dedupes_unknown_routes(tmp_path)@L66; test_quality_checker_passes_with_unknown_route_limit(tmp_path)@L89
- Tiff imports: from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan, check_engineering_context_crag_retry_plan_quality

### `tests/unit/test_trace_net_engineering_engram_prompt_retrieval_injector_v1.py`
- Score: `153`
- Categories: `engram, graph_vector, page, safety, self_rag, server`
- Functions: _item(atom_id, layer, score, proof_role, answer_permission)@L14; test_select_prompt_atoms_filters_unsafe_and_caps()@L32; test_prompt_guidance_block_has_not_proof_boundary()@L44; test_build_and_check_prompt_injector_manifest(tmp_path)@L59; test_check_fails_for_missing_not_proof_banner(tmp_path)@L95
- Tiff imports: from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_guidance_block, build_prompt_retrieval_injector_manifest, check_prompt_retrieval_injector_manifest, select_prompt_atoms

### `tests/unit/test_trace_net_engineering_engram_vector_loader_v1.py`
- Score: `153`
- Categories: `engram, graph_vector, page, safety, server, table_visual_ocr`
- Functions: _sample_memory_layers(tmp_path)@L14; test_deterministic_hash_vector_is_stable_and_normalized()@L35; test_build_vector_loader_manifest_creates_qdrant_ready_records(tmp_path)@L44; test_check_vector_loader_manifest_passes_safe_manifest(tmp_path)@L67; test_check_vector_loader_manifest_fails_unsafe_payload(tmp_path)@L91
- Tiff imports: from tiff.trace_net_engineering_engram_vector_loader_v1 import REQUIRED_MEMORY_LAYERS, build_vector_loader_manifest, check_vector_loader_manifest, deterministic_hash_vector

### `tests/unit/test_trace_net_engineering_webui_answer_server_v1_3_bridge_v1_quality.py`
- Score: `151`
- Categories: `crag, graph_vector, page, safety, self_rag, server, webui`
- Functions: _write_report(path)@L7; test_check_manifest_bridge_quality_passes(tmp_path)@L29; test_check_manifest_fails_when_self_rag_missing(tmp_path)@L50; test_check_manifest_fails_when_crag_not_evaluated(tmp_path)@L60; test_check_manifest_fails_on_write_attempt(tmp_path)@L70
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import check_manifest_bridge_v1

### `tests/unit/test_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24_script_imports.py`
- Score: `147`
- Categories: `final_gate, server, table_visual_ocr, webui`
- Functions: test_v24_scripts_importable()@L5

### `tests/unit/test_trace_net_engineering_engram_prompt_injector_reliability_v1.py`
- Score: `145`
- Categories: `context_pack, engram, page, server, table_visual_ocr`
- Functions: _context_pack()@L9; test_engram_prompt_block_is_compact_behavior_memory_not_proof()@L44; test_minimal_retry_prompt_excludes_engram_block_and_preserves_citations()@L60; test_fallback_pipeline_answer_is_non_empty_and_citation_backed()@L72; test_fallback_unknown_has_no_unrelated_citations()@L94
- Tiff imports: from tiff.trace_net_engineering_llm_answer_smoke_v1 import _fallback_answer_from_context, _minimal_retry_prompt, build_engram_prompt_block, evaluate_llm_answer

### `tests/unit/test_trace_net_engineering_engram_prompt_injector_v1.py`
- Score: `145`
- Categories: `context_pack, engram, page, server, table_visual_ocr`
- Functions: _engram_core()@L13; _context_pack()@L43; _runner()@L72; test_select_engram_atoms_prioritizes_interchangeability_policy()@L80; test_build_engram_prompt_block_marks_memory_as_not_proof()@L92; test_build_llm_prompt_injects_engram_without_replacing_proof_context()@L99; test_safe_reasoning_trace_records_selected_engram_ids(tmp_path)@L115; test_load_engram_core_rejects_failed_manifest(tmp_path)@L143
- Tiff imports: from tiff.trace_net_engineering_llm_answer_smoke_v1 import build_engram_prompt_block, build_llm_prompt, select_engram_atoms, _build_reasoning_trace, _load_engram_core

### `tests/unit/test_trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py`
- Score: `145`
- Categories: `engram, page, safety, self_rag, server`
- Functions: _prompt_smoke(tmp_path)@L12; test_detect_unsupported_claims_respects_negation()@L42; test_build_prompt_contains_boundary()@L47; test_build_artifact_mode_passes(tmp_path)@L59; test_check_artifact(tmp_path)@L79
- Tiff imports: from tiff.trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1 import build_llm_prompt, build_prompt_retrieval_llm_smoke, check_prompt_retrieval_llm_smoke, detect_unsupported_claims

### `tests/unit/test_trace_net_engineering_engram_prompt_retrieval_smoke_v1.py`
- Score: `145`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: _sample_prompt_injector()@L12; test_build_records_preserves_boundaries()@L49; test_manifest_passes_quality(tmp_path)@L58; test_checker_fails_disallowed_role(tmp_path)@L75; test_prompt_compaction_keeps_budget(tmp_path)@L94
- Tiff imports: from tiff.trace_net_engineering_engram_prompt_retrieval_smoke_v1 import build_integration_records, build_prompt_retrieval_smoke_manifest, check_prompt_retrieval_smoke_manifest

### `tests/unit/test_trace_net_engineering_answer_runner_v1.py`
- Score: `143`
- Categories: `context_pack, page, safety, server, table_visual_ocr, webui`
- Functions: _write(path, data)@L10; _index(tmp_path)@L16; _image_pack(tmp_path)@L48; _ocr_pack(tmp_path)@L72; test_runner_chains_planner_context_pack_and_composer(tmp_path)@L92; test_check_runner_passes(tmp_path)@L118; test_runner_fails_when_proof_artifacts_missing(tmp_path)@L142; test_runner_preserves_safety_contract(tmp_path)@L159
- Tiff imports: from tiff.trace_net_engineering_answer_runner_v1 import build_engineering_answer_runner, check_engineering_answer_runner

### `tests/unit/test_trace_net_engineering_webui_answer_server_v1.py`
- Score: `143`
- Categories: `final_gate, page, safety, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L6; _make_artifacts(tmp_path)@L10; test_clean_trace_text_removes_debug_tokens()@L20; test_non_matching_part_number_uses_artifact_search_not_gated_lookup(tmp_path)@L26; test_manifest_quality_requires_retry_empty_response(tmp_path)@L35
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1 import LLMConfig, _clean_trace_text, answer_question, build_engineering_webui_answer_manifest, check_engineering_webui_answer_server_quality

### `tests/unit/test_trace_net_dynamic_final_gate_execution_v1.py`
- Score: `141`
- Categories: `feedback, final_gate, graph_vector, page, safety, server, table_visual_ocr`
- Functions: _group()@L11; test_evaluate_group_approves_cited_answer_support()@L33; test_evaluate_group_blocks_retrieval_only_without_authority()@L44; test_build_dynamic_final_gate_execution_approves_safe_claim(tmp_path)@L55; test_build_dynamic_final_gate_execution_blocks_unsafe_group(tmp_path)@L77; test_final_artifact_query_is_reused_when_exact_match(tmp_path)@L93; test_quality_report_fails_on_uncited_final_claim()@L113
- Tiff imports: from tiff.trace_net_dynamic_final_gate_execution_v1 import build_dynamic_final_gate_execution, evaluate_group_for_dynamic_claim, quality_report, write_json

### `tests/unit/test_trace_net_e2e_dynamic_context_pack_v8.py`
- Score: `141`
- Categories: `context_pack, crag, graph_vector, page, safety, server, table_visual_ocr`
- Functions: sample_ranker()@L14; test_normalize_text_repairs_known_spacing()@L63; test_build_context_pack_separates_evidence_guidance_and_rules()@L67; test_write_report_files(tmp_path)@L106; test_quality_fails_when_missing_evidence()@L115
- Tiff imports: from tiff.trace_net_e2e_dynamic_context_pack_v8 import QualityThresholds, build_context_pack_report, normalize_text, write_report_files

### `tests/unit/test_trace_net_e2e_final_gate_smoke_v1.py`
- Score: `141`
- Categories: `context_pack, final_gate, graph_vector, page, safety, self_rag, server`
- Functions: _source(tmp_path)@L9; test_build_final_gate_smoke_pass(tmp_path)@L73; test_audit_only_when_insufficient(tmp_path)@L99; test_quality_fails_on_answer_permission()@L130; test_fallback_page_citation(tmp_path)@L158
- Tiff imports: from tiff.trace_net_e2e_final_gate_smoke_v1 import build_final_gate_smoke, evaluate_quality

### `tests/unit/test_trace_net_engineering_context_pack_blueprint_v1.py`
- Score: `141`
- Categories: `context_pack, graph_vector, page, planner, safety, server, table_visual_ocr`
- Functions: _write(path, payload)@L11; _planner_payload()@L15; test_build_context_pack_blueprint(tmp_path)@L51; test_quality_checker_passes(tmp_path)@L70
- Tiff imports: from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint, check_engineering_context_pack_blueprint_quality

### `tests/unit/test_trace_net_engineering_context_pack_blueprint_v1_force_writer_dirs.py`
- Score: `141`
- Categories: `context_pack, graph_vector, page, planner, server, table_visual_ocr, webui`
- Functions: _planner_payload()@L8; test_writer_helpers_directly_create_parent_dirs(tmp_path)@L43; test_runtime_write_json_contains_parent_mkdir_guard()@L56; test_real_blueprint_build_writes_into_clean_webui_sample_path(tmp_path)@L62
- Tiff imports: from tiff import trace_net_engineering_context_pack_blueprint_v1

### `tests/unit/test_trace_net_engineering_context_pack_builder_v1.py`
- Score: `141`
- Categories: `context_pack, page, planner, safety, self_rag, server, table_visual_ocr`
- Functions: _write(path, payload)@L11; _blueprint_payload()@L15; test_build_context_pack_with_missing_optional_image_artifact(tmp_path)@L44; test_quality_checker_allows_missing_optional_by_default(tmp_path)@L66; test_quality_checker_can_fail_too_many_missing_optional(tmp_path)@L94
- Tiff imports: from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder, check_engineering_context_pack_builder_quality

### `tests/unit/test_trace_net_engineering_draft_final_gate_v1.py`
- Score: `141`
- Categories: `final_gate, graph_vector, page, planner, safety, server, table_visual_ocr`
- Functions: _write(path, payload)@L11; _runner_payload(tmp_path, draft_text)@L16; test_final_gate_allows_negated_do_not_claim_boundary(tmp_path)@L46; test_final_gate_blocks_asserted_risky_claim(tmp_path)@L76; test_quality_checker_passes_for_negated_manual_review_ready(tmp_path)@L99
- Tiff imports: from tiff.trace_net_engineering_draft_final_gate_v1 import build_engineering_draft_final_gate, check_engineering_draft_final_gate_quality

### `tests/unit/test_trace_net_engineering_context_self_rag_check_v1_quality.py`
- Score: `140`
- Categories: `context_pack, page, safety, self_rag, server`
- Functions: test_quality_flags_answer_permission(tmp_path)@L7; test_quality_flags_llm_calls(tmp_path)@L31
- Tiff imports: from tiff.trace_net_engineering_context_self_rag_check_v1 import check_engineering_context_self_rag_check_quality

### `tests/unit/test_trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py`
- Score: `139`
- Categories: `crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _write_json(path, data)@L12; _fixtures(tmp_path)@L18; test_v33_always_calls_llm_in_simulate_mode(tmp_path)@L63; test_v33_v2_summary_count_package_has_metadata(tmp_path)@L81; test_v33_relationship_question_is_guidance_only(tmp_path)@L99; test_v33_final_gate_repairs_unsafe_draft(tmp_path)@L117; test_v33_build_report_quality(tmp_path)@L132; test_v33_compact_prompt_telemetry_and_budget(tmp_path)@L159; test_v33_missing_normal_intents_are_packaged_and_answered(tmp_path)@L183; test_v33_build_report_counts_normal_intents(tmp_path)@L212; test_v33_self_rag_and_crag_telemetry_present(tmp_path)@L241; test_v33_page_profile_combines_source_truth_and_v2_guidance(tmp_path)@L260; test_v33_build_report_counts_self_rag_and_crag(tmp_path)@L280
- Tiff imports: from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v33 import TraceNetGemmaAnswerWriterV33, build_report

### `tests/unit/test_trace_net_e2e_live_llm_draft_adapter_v22.py`
- Score: `139`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server`
- Functions: sample_prompt_contract_report(count)@L14; thresholds()@L64; test_v22_simulated_drafts_ready_for_final_gate()@L81; test_v22_quality_fails_on_llm_call_errors_threshold()@L92; test_v22_ollama_call_can_be_monkeypatched(monkeypatch)@L103; test_v22_writes_report_files(tmp_path)@L119; test_v22_markdown_mentions_final_gate()@L129; fake_call()@L106
- Tiff imports: from tiff.trace_net_e2e_live_llm_draft_adapter_v22 import LlmConfig, build_report, render_markdown, write_report_files; tiff.trace_net_e2e_live_llm_draft_adapter_v22

### `tests/unit/test_trace_net_e2e_live_llm_final_gate_v23_script_imports.py`
- Score: `139`
- Categories: `final_gate, server, table_visual_ocr`
- Functions: test_v23_scripts_importable()@L7

### `tests/unit/test_trace_net_e2e_live_llm_prompt_contract_v21.py`
- Score: `139`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: sample_context_pack_report(count)@L9; sample_evaluator_report(count)@L49; thresholds()@L64; test_v21_builds_prompt_contracts_ready_for_llm()@L85; test_v21_blocks_graph_proof_authority_violation()@L97; test_v21_missing_evidence_needs_repair()@L106; test_v21_writes_report_files(tmp_path)@L114; test_v21_markdown_mentions_contract()@L125; test_v21_1_maps_v20_self_rag_crag_records_and_includes_status()@L132; test_v21_1_deduplicates_repeated_source_truth_evidence()@L170; test_v21_1_separates_exact_table_text_from_nearby_ocr_context()@L201; test_v21_2_does_not_promote_tiny_ocr_fragments_to_direct_evidence()@L234; test_v21_2_hygiene_counts_preserve_precollapsed_occurrence_count()@L268
- Tiff imports: from tiff.trace_net_e2e_live_llm_prompt_contract_v21 import build_report, render_markdown, write_report_files

### `tests/unit/test_trace_net_e2e_live_relationship_final_gated_endpoint_v31_script_imports.py`
- Score: `139`
- Categories: `final_gate, server, table_visual_ocr`
- Functions: test_v31_scripts_importable()@L5

### `tests/unit/test_trace_net_e2e_llm_assisted_query_planner_v17.py`
- Score: `138`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`
- Functions: test_detects_core_query_intents()@L6; test_build_plan_uses_v2_summaries_and_leiden_as_guidance_only()@L17; test_relationship_plan_has_graph_expansion_but_no_graph_proof()@L40; test_invalid_tunnel_is_rejected()@L51; test_report_quality_passes_with_sample_artifacts(tmp_path)@L71; test_scalability_contract_prevents_raw_5tb_scans()@L97
- Tiff imports: from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import detect_query_intent; from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_query_plan; from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import validate_query_plan; from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, build_report, evaluate_quality, write_report_files

### `tests/unit/test_trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.py`
- Score: `137`
- Categories: `engram, page, safety, server`
- Functions: _write(path, data)@L10; _fixtures(tmp_path)@L15; test_build_gate_passes(tmp_path)@L66; test_check_gate_passes(tmp_path)@L87; test_missing_boundary_fails(tmp_path)@L110; test_overlay_map_requires_explicit_flag(tmp_path)@L126
- Tiff imports: from tiff.trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1 import build_overlay_integration_gate, check_overlay_integration_gate

### `tests/unit/test_trace_net_engineering_webui_answer_server_v1_3.py`
- Score: `135`
- Categories: `crag, page, server, table_visual_ocr, webui`
- Functions: test_clean_fallback_has_no_debug_tokens()@L9; test_v13_nonmatching_part_uses_search()@L30
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1 import LLMConfig; from tiff.trace_net_engineering_webui_answer_server_v1_3 import build_clean_search_fallback, answer_question_v13

### `tests/unit/test_trace_net_answer_context_pack_v1.py`
- Score: `133`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`
- Functions: write_json(path, payload)@L9; candidate_record()@L14; page_profile_record()@L44; ask_report()@L74; hybrid_report()@L94; artifact_payload(records)@L168; write_fixture_files(tmp_path)@L172; test_build_context_pack_separates_answer_support_and_retrieval_only(tmp_path)@L184; test_answer_support_missing_citation_fails_quality(tmp_path)@L208; test_context_helper_stays_retrieval_only(tmp_path)@L229; test_same_page_answer_support_expansion_adds_safe_support_when_hits_are_route_only(tmp_path)@L258; test_same_page_answer_support_expansion_skips_unsafe_support_candidates(tmp_path)@L308; test_check_quality_reads_written_report(tmp_path)@L349; test_quality_fails_when_retrieval_only_can_answer()@L364
- Tiff imports: from tiff import trace_net_answer_context_pack_v1

### `tests/unit/test_trace_net_ask_final_gate_v1.py`
- Score: `133`
- Categories: `final_gate, graph_vector, page, safety, server, table_visual_ocr`
- Functions: write_json(path, payload)@L12; final_gate_payload()@L17; test_run_ask_final_gate_exposes_only_passed_final_gate(tmp_path)@L75; test_run_ask_final_gate_blocks_wrong_answer_mode(tmp_path)@L99; test_query_mismatch_fails_quality(tmp_path)@L121; test_final_answer_path_leak_blocks_exposure(tmp_path)@L141; test_retrieval_only_final_claim_blocks_exposure(tmp_path)@L163; test_quality_check_accepts_written_report(tmp_path)@L186
- Tiff imports: from tiff.trace_net_ask_final_gate_v1 import check_ask_final_gate_quality, run_ask_final_gate

### `tests/unit/test_trace_net_dynamic_final_gate_execution_v1_quality.py`
- Score: `133`
- Categories: `feedback, final_gate, graph_vector, page, safety, server`
- Functions: test_quality_report_passes_clean_retrieval_only_result()@L4; test_quality_report_requires_hybrid_quality_when_requested()@L30
- Tiff imports: from tiff.trace_net_dynamic_final_gate_execution_v1 import quality_report

### `tests/unit/test_trace_net_e2e_relationship_final_gate_hardener_v30.py`
- Score: `133`
- Categories: `crag, final_gate, graph_vector, page, safety, server`
- Functions: _write_json(path, data)@L12; test_detects_graph_as_proof_violation()@L17; test_safe_guidance_answer_does_not_trigger_violation()@L29; test_detects_v2_and_nomenclature_proof_violations()@L40; test_build_report_repairs_synthetic_violations(tmp_path)@L57; test_non_relationship_metadata_records_pass_without_repair(tmp_path)@L95; test_report_fails_when_post_gate_issues_remain(tmp_path)@L129
- Tiff imports: from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import build_report, detect_relationship_gate_issues

### `tests/unit/test_trace_net_engineering_answer_context_pack_v1.py`
- Score: `133`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`
- Functions: _write(path, data)@L10; _planner(tmp_path, guidance_pages)@L16; _image_pack(tmp_path)@L35; _ocr_pack(tmp_path)@L59; test_builds_context_pack_with_guidance_separate_from_proof(tmp_path)@L79; test_figure_69_gets_visual_and_ocr_proof(tmp_path)@L105; test_fails_when_proof_context_missing(tmp_path)@L121; test_check_context_pack_passes(tmp_path)@L132; test_answer_constraints_forbid_summary_only_proof(tmp_path)@L151; _exact_part_planner(tmp_path)@L165; _exact_table_pack(tmp_path)@L184; test_exact_part_lookup_builds_exact_part_proof_context(tmp_path)@L200
- Tiff imports: from tiff.trace_net_engineering_answer_context_pack_v1 import build_engineering_answer_context_pack, check_engineering_answer_context_pack

### `tests/unit/test_trace_net_engineering_context_pack_blueprint_v1_directory_safety.py`
- Score: `133`
- Categories: `context_pack, graph_vector, page, planner, server, table_visual_ocr`
- Functions: _planner_payload()@L12; test_writer_helpers_create_parent_directories(tmp_path)@L47; test_blueprint_build_creates_clean_nested_stage_directory(tmp_path)@L60
- Tiff imports: from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint, _write_json, _write_jsonl, _write_markdown

### `tests/unit/test_trace_net_engineering_context_crag_retry_plan_v1_quality.py`
- Score: `132`
- Categories: `page, safety, self_rag, server`
- Functions: test_quality_flags_unknown_target_routes(tmp_path)@L7; test_quality_flags_retrieval_execution(tmp_path)@L32
- Tiff imports: from tiff.trace_net_engineering_context_crag_retry_plan_v1 import check_engineering_context_crag_retry_plan_quality

## Highest-signal active docs

### `docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- Score: `205`
- Categories: `context_pack, crag, graph_vector, self_rag, server`
- L9 `self_rag`: behavior. It does not call an LLM, scan raw corpus data, rebuild graph data, mutate source truth, or write to services. Primary output: - `trace_net_e2e_live_self_rag_crag_evaluator_v20.json` - `trace_net_e2e_live_self_rag_crag_evaluator_records_v20.jsonl` - `trace_net_e2e_live_self_rag_crag_evaluator_crag_plans_v20.jsonl` - `trace_net_e2e_live_self_rag_crag_evaluator_v20.md` Authority contract: - Source-truth evidence is required for final factual claims. - Graph/Leiden guidance is navigation only. - v2 summar
- L1 `self-rag`: # TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20 Builds Self-RAG and CRAG evaluation records from v19 executed-plan context packs. The module keeps source-truth evidence separate from graph/Leiden and v2 summary guidance. It treats capped or high-degree graph/entity results as usable only when the final answer preserves aggregation/cap disclosure and offers drill-down behavi
- L1 `crag`: # TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20 Builds Self-RAG and CRAG evaluation records from v19 executed-plan context packs. The module keeps source-truth evidence separate from graph/Leiden and v2 summary guidance. It treats capped or high-degree graph/entity results as usable only when the final answer preserves aggregation/cap disclosure and offers drill-down behavior. It does
- L3 `context pack`: # TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20 Builds Self-RAG and CRAG evaluation records from v19 executed-plan context packs. The module keeps source-truth evidence separate from graph/Leiden and v2 summary guidance. It treats capped or high-degree graph/entity results as usable only when the final answer preserves aggregation/cap disclosure and offers drill-down behavior. It does not call an LLM, scan raw corpus data, rebuild graph data, mutate source truth, or wri
- L5 `guidance`: ds Self-RAG and CRAG evaluation records from v19 executed-plan context packs. The module keeps source-truth evidence separate from graph/Leiden and v2 summary guidance. It treats capped or high-degree graph/entity results as usable only when the final answer preserves aggregation/cap disclosure and offers drill-down behavior. It does not call an LLM, scan raw corpus data, rebuild graph data, mutate source truth, or write to services. Primary output: - `trace_net_e2e_live_self_rag_crag_evaluator_v20.json` - `trac

### `docs/trace_net_engineering_engram_self_rag_critic_v1_README.md`
- Score: `204`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server`
- L1 `engram`: # TRACE-Net Engineering Engram Self-RAG Critic v1 H28 adds an artifact-only Self-RAG-style critic for targeted Engram overlay answer-smoke results. ## Purpose The critic reviews answer-smoke records after retrieved Engram overlays have been injected into the real answer-smoke prompt path. It checks whether the answer stayed within the source-trace boundary, used counted citation
- L22 `self_rag`: mission. - Engram and critic memories remain behavior guidance only, not proof. ## Typical build ```bash python -B scripts/build_trace_net_engineering_engram_self_rag_critic_v1.py \ --answer-smoke local_data/organization/trace_net/llm_h27e_overlay_target_q12_q16_q18_q25_q29/trace_net_engineering_llm_answer_smoke_v1.json \ --output-dir local_data/organization/trace_net/engineering_engram_self_rag_critic_v1 \ --min-records 5 \ --min-critic-pass-or-expected 5 \ --max-repair-recommended 0 \ --require-sour
- L1 `self-rag`: # TRACE-Net Engineering Engram Self-RAG Critic v1 H28 adds an artifact-only Self-RAG-style critic for targeted Engram overlay answer-smoke results. ## Purpose The critic reviews answer-smoke records after retrieved Engram overlays have been injected into the real answer-smoke prompt path. It checks whether the answer stayed within the source-trace boundary, used counted citations when
- L36 `crag`: recommended 0 \ --require-source-quality-pass \ --require-no-answer-permission \ --max-unsafe 0 \ --max-write-attempts 0 ``` ## Next step H29 can add CRAG Engram repair for records with `REVIEW` or `REPAIR_RECOMMENDED` status.
- L1 `critic`: # TRACE-Net Engineering Engram Self-RAG Critic v1 H28 adds an artifact-only Self-RAG-style critic for targeted Engram overlay answer-smoke results. ## Purpose The critic reviews answer-smoke records after retrieved Engram overlays have been injected into the real answer-smoke prompt path. It checks whether the answer stayed within the source-trace boundary, used counted citations when proof con

### `docs/trace_net_engineering_engram_crag_repair_v1_README.md`
- Score: `196`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server`
- L1 `engram`: # TRACE-Net Engineering Engram CRAG Repair v1 H29 adds an artifact-only CRAG repair loop for the Engineering Engram path. ## Purpose The module consumes H28 Self-RAG critic records and the source answer-smoke manifest. It decides whether each answer should be preserved, treated as an expected unknown/no-proof boundary, or repaired. ## Safety contract - CRAG may repair answer b
- L22 `self_rag`: pical command ```bash python -B scripts/build_trace_net_engineering_engram_crag_repair_v1.py \ --critic local_data/organization/trace_net/engineering_engram_self_rag_critic_v1/trace_net_engineering_engram_self_rag_critic_v1.json \ --answer-smoke local_data/organization/trace_net/llm_h27e_overlay_target_q12_q16_q18_q25_q29/trace_net_engineering_llm_answer_smoke_v1.json \ --output-dir local_data/organization/trace_net/engineering_engram_crag_repair_v1 \ --min-records 5 \ --min-crag-pass-or-no-repair 5 \
- L7 `self-rag`: # TRACE-Net Engineering Engram CRAG Repair v1 H29 adds an artifact-only CRAG repair loop for the Engineering Engram path. ## Purpose The module consumes H28 Self-RAG critic records and the source answer-smoke manifest. It decides whether each answer should be preserved, treated as an expected unknown/no-proof boundary, or repaired. ## Safety contract - CRAG may repair answer behavior, formatting, and citation discipline. - CRAG cannot create proof. - Engram memory and summaries remain guidance only. - No answe
- L1 `crag`: # TRACE-Net Engineering Engram CRAG Repair v1 H29 adds an artifact-only CRAG repair loop for the Engineering Engram path. ## Purpose The module consumes H28 Self-RAG critic records and the source answer-smoke manifest. It decides whether each answer should be preserved, treated as an expected unknown/no-proof boundary, or repaired. ## Safety contract - CRAG may repair answer behavior
- L7 `critic`: et Engineering Engram CRAG Repair v1 H29 adds an artifact-only CRAG repair loop for the Engineering Engram path. ## Purpose The module consumes H28 Self-RAG critic records and the source answer-smoke manifest. It decides whether each answer should be preserved, treated as an expected unknown/no-proof boundary, or repaired. ## Safety contract - CRAG may repair answer behavior, formatting, and citation discipline. - CRAG cannot create proof. - Engram memory and summaries remain guidance only. - No answer permiss

### `docs/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1_README.md`
- Score: `191`
- Categories: `context_pack, crag, engram, graph_vector, page, table_visual_ocr, webui`
- L1 `engram`: # TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1 H25 performs a targeted smoke for retrieved Engram overlays against saved engineering answer-runner prompts. It is designed to avoid another full 30-question Gemma run. The default target set is: - q12 interchangeability boundary - q16 visual/OCR route explanation - q18 pipeline recovery / safe-but-too-generic rep
- L11 `repair`: tion Gemma run. The default target set is: - q12 interchangeability boundary - q16 visual/OCR route explanation - q18 pipeline recovery / safe-but-too-generic repair - q25 unknown part / no proof context - q29 summary-only proof limit ## Safety contract - No Postgres writes - No Qdrant reads/writes - No OpenSearch writes/uploads - No source-truth mutation - No answer permission - Retrieved Engram overlays are behavior guidance only and never source proof ## Modes - `artifact`: deterministic scaffold, no LLM ca
- L12 `proof`: get set is: - q12 interchangeability boundary - q16 visual/OCR route explanation - q18 pipeline recovery / safe-but-too-generic repair - q25 unknown part / no proof context - q29 summary-only proof limit ## Safety contract - No Postgres writes - No Qdrant reads/writes - No OpenSearch writes/uploads - No source-truth mutation - No answer permission - Retrieved Engram overlays are behavior guidance only and never source proof ## Modes - `artifact`: deterministic scaffold, no LLM call - `ollama`: short targeted l
- L22 `guidance`: tgres writes - No Qdrant reads/writes - No OpenSearch writes/uploads - No source-truth mutation - No answer permission - Retrieved Engram overlays are behavior guidance only and never source proof ## Modes - `artifact`: deterministic scaffold, no LLM call - `ollama`: short targeted local Gemma smoke ## Expected usage Run tests, then build artifact mode, then run the short Ollama mode only after artifact mode passes.
- L27 `ollama`: answer permission - Retrieved Engram overlays are behavior guidance only and never source proof ## Modes - `artifact`: deterministic scaffold, no LLM call - `ollama`: short targeted local Gemma smoke ## Expected usage Run tests, then build artifact mode, then run the short Ollama mode only after artifact mode passes.

### `docs/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_README.md`
- Score: `183`
- Categories: `crag, engram, graph_vector, page, safety, webui`
- L1 `engram`: # TRACE-Net Engineering Engram Answer Runner Retrieval Bridge v1 (H23) H23 creates the artifact-only bridge between retrieved Engram prompt guidance and the real engineering answer runner. It does **not** patch the full answer runner yet and does not launch a long 30-question smoke. Instead, it produces a deterministic guidance map keyed by task type so the next patch can wire re
- L32 `repair`: this guidance map into a small targeted engineering answer-runner smoke, such as q12/q16/q18/q25/q29, before any full 30-question run. ## v1b boundary safety repair H23 v1b relaxes boundary matching so normal H20 wording such as `BEHAVIOR ONLY, NOT PROOF` and `shape answer behavior only` is treated as a valid safety boundary. The previous H23 matcher required the exact phrase `behavior guidance only`, which caused false unsafe findings even when the prompt clearly said Engram guidance is behavior-only and not pr
- L22 `proof`: runner_retrieval_bridge_v1_quality_check.json` ## Safety contract - Engram retrieval is behavior guidance only. - Manual/source claims still require current `proof_context` citations. - No live Qdrant IO is attempted. - No Postgres, Qdrant, or OpenSearch writes are attempted. - No source-truth mutation is allowed. - Engram memory cannot grant answer permission. ## Next step H24 should wire this guidance map into a small targeted engineering answer-runner smoke, such as q12/q16/q18/q25/q29, before any full 30-qu
- L3 `guidance`: # TRACE-Net Engineering Engram Answer Runner Retrieval Bridge v1 (H23) H23 creates the artifact-only bridge between retrieved Engram prompt guidance and the real engineering answer runner. It does **not** patch the full answer runner yet and does not launch a long 30-question smoke. Instead, it produces a deterministic guidance map keyed by task type so the next patch can wire retrieval-guided behavior into targeted answer-runner prompts behind an explicit flag. ## Inputs - H20 `engineering_e
- L10 `ollama`: n explicit flag. ## Inputs - H20 `engineering_engram_prompt_retrieval_injector_v1` manifest. - Optional H22 `engineering_engram_prompt_retrieval_llm_smoke_v1_ollama` manifest. ## Outputs - `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.json` - `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_records.jsonl` - `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_guidance_map.json` - `trace_net_engineering_engram_answer_runner_retrieval_bridge_v1_quality_check.json` ## S

### `docs/README_trace_net_page_context_pack_v3.md`
- Score: `170`
- Categories: `context_pack, graph_vector, page, table_visual_ocr, webui`
- L1 `context pack`: # TRACE-Net Page Context Pack v3.2 Page Context Pack v3.2 builds a source-bounded page binder for page-specific and complex TRACE-Net questions. ## Purpose The model should still reason for complex questions, but it should reason from a controlled binder: - proof/source locators first: source files, source links, OCR/source text, table evidence, exact part records - guid
- L3 `binder`: # TRACE-Net Page Context Pack v3.2 Page Context Pack v3.2 builds a source-bounded page binder for page-specific and complex TRACE-Net questions. ## Purpose The model should still reason for complex questions, but it should reason from a controlled binder: - proof/source locators first: source files, source links, OCR/source text, table evidence, exact part records - guidance records second: graph neighbors, vector hits, visual summaries, ro
- L9 `proof`: e-specific and complex TRACE-Net questions. ## Purpose The model should still reason for complex questions, but it should reason from a controlled binder: - proof/source locators first: source files, source links, OCR/source text, table evidence, exact part records - guidance records second: graph neighbors, vector hits, visual summaries, route-only candidates - explicit reasoning work order: allowed synthesis plus blocked overclaims ## v3.2 hydrator improvements v3.2 improves the v3.1 page resolver with route
- L10 `guidance`: ut it should reason from a controlled binder: - proof/source locators first: source files, source links, OCR/source text, table evidence, exact part records - guidance records second: graph neighbors, vector hits, visual summaries, route-only candidates - explicit reasoning work order: allowed synthesis plus blocked overclaims ## v3.2 hydrator improvements v3.2 improves the v3.1 page resolver with route-aware hydration: - Adds source file/source link locators from route, OCR, graph, table, exact, and visual rec
- L18 `openwebui`: urce file/source link locators from route, OCR, graph, table, exact, and visual records. - Follows linked JSONL sidecars such as `records_jsonl_path` so visual/OpenWebUI route manifests can attach real page cards. - Extracts OCR text from common OCR keys and nested cells/rows/tiles. - Adds visual guidance for image/visual pages while keeping it guidance-only. - Moves unproven table/exact records into `route_guidance` instead of counting them as proof. - Adds `route_evidence_priority` and per-page `page_reasoning_ta

### `docs/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1_README.md`
- Score: `167`
- Categories: `engram, graph_vector, page, webui`
- L1 `engram`: # TRACE-Net Engineering Engram Answer-Runner Prompt Overlay Smoke v1 H24 turns the H23 answer-runner retrieval bridge into an artifact-only prompt overlay map for a small targeted set of answer-runner questions. ## Purpose The full 30-question LLM smoke is slow. H24 creates a targeted overlay smoke so retrieved Engram guidance can be inspected before it is wired into a live answ
- L32 `proof`: Qdrant reads/writes - no OpenSearch writes/uploads - no write attempts Engram overlays are behavior guidance only. Manual/source claims still require current `proof_context` citations. ## Next step H25 should use this overlay map in a targeted LLM answer-runner overlay smoke, for example q12, q16, q18, q25, and q29.
- L7 `guidance`: a small targeted set of answer-runner questions. ## Purpose The full 30-question LLM smoke is slow. H24 creates a targeted overlay smoke so retrieved Engram guidance can be inspected before it is wired into a live answer-runner LLM path. ## Inputs - H23 answer-runner retrieval bridge manifest. - Optional existing engineering answer smoke manifest, such as H16D 30-question PASS, for question metadata. ## Outputs - `trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.json` - `trace_net_engineeri
- L28 `qdrant`: moke_v1_overlay_map.json` - quality check JSON ## Safety contract Artifact-only: - no answer permission - no source-truth mutation - no Postgres writes - no Qdrant reads/writes - no OpenSearch writes/uploads - no write attempts Engram overlays are behavior guidance only. Manual/source claims still require current `proof_context` citations. ## Next step H25 should use this overlay map in a targeted LLM answer-runner overlay smoke, for example q12, q16, q18, q25, and q29.
- L29 `opensearch`: - quality check JSON ## Safety contract Artifact-only: - no answer permission - no source-truth mutation - no Postgres writes - no Qdrant reads/writes - no OpenSearch writes/uploads - no write attempts Engram overlays are behavior guidance only. Manual/source claims still require current `proof_context` citations. ## Next step H25 should use this overlay map in a targeted LLM answer-runner overlay smoke, for example q12, q16, q18, q25, and q29.

### `docs/README_trace_net_openwebui_page_context_bridge_v1.md`
- Score: `151`
- Categories: `context_pack, final_gate, graph_vector, page, server, table_visual_ocr, webui`
- L3 `context_pack`: # TRACE-Net OpenWebUI Page Context Bridge v1 This bridge wires `page_context_pack_v3` into the current OpenWebUI/V3 answer path without replacing the existing Gemma bridge. ## Runtime shape ```text Open WebUI -> page-context proxy bridge on 8023 -> detects explicit page questions -> builds page_context_pack_v3 -> injects source-bounded binder into OpenAI chat messages -> forwards to existing V3 bridge on 8022 -> Gemma draft
- L12 `binder`: time shape ```text Open WebUI -> page-context proxy bridge on 8023 -> detects explicit page questions -> builds page_context_pack_v3 -> injects source-bounded binder into OpenAI chat messages -> forwards to existing V3 bridge on 8022 -> Gemma drafts from the binder ``` ## Why this exists TRACE-Net should not make Gemma a database. TRACE-Net builds the evidence binder. Gemma still thinks for complex questions, but it reasons inside source-trace limits. The injected binder includes: - selected page records - sou
- L28 `proof`: age records - source file/source link locators when available - route-aware evidence priority - route guidance and vector guidance - per-page reasoning tasks - proof/guidance counts - safety constraints - the global reasoning work order with `model_should_think: true` ## Safety contract - Read-only artifact access. - No source-truth mutation. - No answer permission. - No Postgres/Qdrant/OpenSearch writes. - Vector, graph, visual, summary, and route guidance are not proof unless backed by source-trace proof record
- L26 `guidance`: trace limits. The injected binder includes: - selected page records - source file/source link locators when available - route-aware evidence priority - route guidance and vector guidance - per-page reasoning tasks - proof/guidance counts - safety constraints - the global reasoning work order with `model_should_think: true` ## Safety contract - Read-only artifact access. - No source-truth mutation. - No answer permission. - No Postgres/Qdrant/OpenSearch writes. - Vector, graph, visual, summary, and route guidanc
- L107 `alignment`: .content`. TRACE-Net records the empty-content diagnostic metadata, never exposes hidden reasoning/thinking text as the answer, and still requires page/page_id alignment before passing the model response. If retry output is still empty or unaligned, the bridge returns the safe page-context fallback. ## Native Ollama `/api/chat` final-content mode For thinking models such as `gemma4:26b`, the OpenAI-compatible Ollama endpoint can spend the whole generation budget in a `reasoning` field and return empty `message.co

### `docs/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.md`
- Score: `151`
- Categories: `crag, final_gate, graph_vector, page, server, table_visual_ocr, webui`
- L9 `repair`: l gate artifact. - Serves only final-gated answers that passed source-truth checks. - Does not call Gemma at request time; v22 already generated drafts and v23 repaired/gated them. - Source-truth evidence remains the only proof authority. - Graph/Leiden and v2 summaries remain guidance only. - Nearby OCR/table context is not direct proof for the user query. - Does not scan raw 5TB source data, rebuild graph, rerun OCR, mutate source truth, or write to services. ## Endpoints - `GET /health` - `GET /v1/models` - `P
- L10 `proof`: source-truth checks. - Does not call Gemma at request time; v22 already generated drafts and v23 repaired/gated them. - Source-truth evidence remains the only proof authority. - Graph/Leiden and v2 summaries remain guidance only. - Nearby OCR/table context is not direct proof for the user query. - Does not scan raw 5TB source data, rebuild graph, rerun OCR, mutate source truth, or write to services. ## Endpoints - `GET /health` - `GET /v1/models` - `POST /v1/chat/completions` ## Open WebUI Use the Docker-facin
- L11 `guidance`: ime; v22 already generated drafts and v23 repaired/gated them. - Source-truth evidence remains the only proof authority. - Graph/Leiden and v2 summaries remain guidance only. - Nearby OCR/table context is not direct proof for the user query. - Does not scan raw 5TB source data, rebuild graph, rerun OCR, mutate source truth, or write to services. ## Endpoints - `GET /health` - `GET /v1/models` - `POST /v1/chat/completions` ## Open WebUI Use the Docker-facing base URL: ```text http://host.docker.internal:8020/v1
- L19 `chat/completions`: ot scan raw 5TB source data, rebuild graph, rerun OCR, mutate source truth, or write to services. ## Endpoints - `GET /health` - `GET /v1/models` - `POST /v1/chat/completions` ## Open WebUI Use the Docker-facing base URL: ```text http://host.docker.internal:8020/v1 ``` Model: ```text trace-net-e2e-live-final-gated-gemma-v24 ```

### `docs/trace_net_engineering_engram_memory_layers_v1_README.md`
- Score: `149`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, table_visual_ocr`
- L1 `engram`: # TRACE-Net Engineering Engram Memory Layers v1 H17 formalizes the TRACE-Net Engram as a typed engineering memory taxonomy. The goal is not to make the LLM human or to add source facts to memory. The goal is to make behavior memory explicit, inspectable, versioned, and testable. ## Memory layers | Layer | Meaning | Runtime role | | --- | --- | --- | | `working_memory` | Curren
- L14 `self-rag`: revention | | `trait_memory` | Cautious, source-trace-first, helpful-but-not-overclaiming behavior profile | Consistent engineering style | | `critic_memory` | Self-RAG/CRAG critique and repair lessons | Draft critique and repair | ## Proof boundary Engram memory is behavior guidance only. It can guide how TRACE-Net plans, phrases, critiques, and repairs answers. It cannot prove source facts, mutate source truth, or grant answer permission. Manual facts must still come from current `proof_context` citations.
- L14 `crag`: | | `trait_memory` | Cautious, source-trace-first, helpful-but-not-overclaiming behavior profile | Consistent engineering style | | `critic_memory` | Self-RAG/CRAG critique and repair lessons | Draft critique and repair | ## Proof boundary Engram memory is behavior guidance only. It can guide how TRACE-Net plans, phrases, critiques, and repairs answers. It cannot prove source facts, mutate source truth, or grant answer permission. Manual facts must still come from current `proof_context` citations. `working_
- L14 `critic`: and regression prevention | | `trait_memory` | Cautious, source-trace-first, helpful-but-not-overclaiming behavior profile | Consistent engineering style | | `critic_memory` | Self-RAG/CRAG critique and repair lessons | Draft critique and repair | ## Proof boundary Engram memory is behavior guidance only. It can guide how TRACE-Net plans, phrases, critiques, and repairs answers. It cannot prove source facts, mutate source truth, or grant answer permission. Manual facts must still come from current `proof_cont
- L14 `repair`: ` | Cautious, source-trace-first, helpful-but-not-overclaiming behavior profile | Consistent engineering style | | `critic_memory` | Self-RAG/CRAG critique and repair lessons | Draft critique and repair | ## Proof boundary Engram memory is behavior guidance only. It can guide how TRACE-Net plans, phrases, critiques, and repairs answers. It cannot prove source facts, mutate source truth, or grant answer permission. Manual facts must still come from current `proof_context` citations. `working_memory` is the onl

### `docs/trace_net_engineering_engram_core_v1_README.md`
- Score: `141`
- Categories: `crag, engram, graph_vector, page, self_rag, server, table_visual_ocr`
- L1 `engram`: # TRACE-Net Engineering Engram Core v1 H15 creates the first versioned TRACE-Net Engineering Engram: a local JSON behavior-memory pack that stores operational engineering traits, source-trace policies, route behavior rules, eval failure memories, Self-RAG critic traits, and CRAG repair traits. This stage does **not** write to Postgres, Qdrant, OpenSearch, or source-truth records.
- L3 `self-rag`: ering Engram: a local JSON behavior-memory pack that stores operational engineering traits, source-trace policies, route behavior rules, eval failure memories, Self-RAG critic traits, and CRAG repair traits. This stage does **not** write to Postgres, Qdrant, OpenSearch, or source-truth records. It only builds local JSON/CSV artifacts that later stages can inject into prompts or load into vector memory. ## Outputs - `trace_net_engineering_engram_core_v1.json` - `trace_net_engineering_engram_memory_atoms_v1.json`
- L3 `crag`: ehavior-memory pack that stores operational engineering traits, source-trace policies, route behavior rules, eval failure memories, Self-RAG critic traits, and CRAG repair traits. This stage does **not** write to Postgres, Qdrant, OpenSearch, or source-truth records. It only builds local JSON/CSV artifacts that later stages can inject into prompts or load into vector memory. ## Outputs - `trace_net_engineering_engram_core_v1.json` - `trace_net_engineering_engram_memory_atoms_v1.json` - `trace_net_engineering_eng
- L3 `critic`: ram: a local JSON behavior-memory pack that stores operational engineering traits, source-trace policies, route behavior rules, eval failure memories, Self-RAG critic traits, and CRAG repair traits. This stage does **not** write to Postgres, Qdrant, OpenSearch, or source-truth records. It only builds local JSON/CSV artifacts that later stages can inject into prompts or load into vector memory. ## Outputs - `trace_net_engineering_engram_core_v1.json` - `trace_net_engineering_engram_memory_atoms_v1.json` - `trace_
- L3 `repair`: or-memory pack that stores operational engineering traits, source-trace policies, route behavior rules, eval failure memories, Self-RAG critic traits, and CRAG repair traits. This stage does **not** write to Postgres, Qdrant, OpenSearch, or source-truth records. It only builds local JSON/CSV artifacts that later stages can inject into prompts or load into vector memory. ## Outputs - `trace_net_engineering_engram_core_v1.json` - `trace_net_engineering_engram_memory_atoms_v1.json` - `trace_net_engineering_engram_t

### `docs/trace_net_engineering_engram_qdrant_adapter_v1_README.md`
- Score: `141`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag`
- L1 `engram`: # TRACE-Net Engineering Engram Qdrant Adapter v1 H30 moves the Engineering Engram vector path from local Qdrant-ready artifacts toward live Qdrant integration while preserving TRACE-Net's safety boundary. ## Scope - Input: H18 Engineering Engram vector loader manifest. - Output: Qdrant point JSONL, local retrieval smoke records, adapter manifest, quality check. - Default mode: a
- L32 `self-rag`: icit flags: - `--enable-live-qdrant-write` - `--enable-live-qdrant-read` ## Follow-on H31 should add the Postgres feedback/memory ledger. H32 should combine Self-RAG, CRAG, Qdrant/vector, feedback, and graph/vector routing into one gated runtime manifest.
- L32 `crag`: : - `--enable-live-qdrant-write` - `--enable-live-qdrant-read` ## Follow-on H31 should add the Postgres feedback/memory ledger. H32 should combine Self-RAG, CRAG, Qdrant/vector, feedback, and graph/vector routing into one gated runtime manifest.
- L14 `proof`: ags are used. ## Safety contract Engram vectors retrieve behavior guidance only. They do not prove manual/source claims. Source claims still require current `proof_context` citations. Default counters remain zero: - `qdrant_write_attempt_count` - `qdrant_read_attempt_count` - `postgres_write_attempt_count` - `opensearch_write_attempt_count` - `source_truth_mutation_allowed_count` - `answer_permission_count` Live Qdrant IO requires explicit flags: - `--enable-live-qdrant-write` - `--enable-live-qdrant-read` #
- L14 `guidance`: ry run, no live Qdrant IO. - Optional live mode: Qdrant read/write only when explicit CLI flags are used. ## Safety contract Engram vectors retrieve behavior guidance only. They do not prove manual/source claims. Source claims still require current `proof_context` citations. Default counters remain zero: - `qdrant_write_attempt_count` - `qdrant_read_attempt_count` - `postgres_write_attempt_count` - `opensearch_write_attempt_count` - `source_truth_mutation_allowed_count` - `answer_permission_count` Live Qdrant

### `docs/trace_net_engineering_engram_unified_runtime_gate_v1_README.md`
- Score: `141`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag`
- L2 `engram`: # TRACE-Net H32 Engineering Engram Unified Runtime Gate v1 H32 is the final connection gate for the Engram architecture. It joins the artifact outputs from: - H27E real answer-smoke overlay integration - H28 Self-RAG Engram critic - H29 CRAG Engram repair gate - H30 Engram Qdrant/vector adapter - H31 Postgres feedback/memory ledger - optional graph-route guidance manifest The module
- L27 `self_rag`: et/llm_h27e_overlay_target_q12_q16_q18_q25_q29/trace_net_engineering_llm_answer_smoke_v1.json \ --critic local_data/organization/trace_net/engineering_engram_self_rag_critic_v1/trace_net_engineering_engram_self_rag_critic_v1.json \ --crag-repair local_data/organization/trace_net/engineering_engram_crag_repair_v1/trace_net_engineering_engram_crag_repair_v1.json \ --qdrant-adapter local_data/organization/trace_net/engineering_engram_qdrant_adapter_v1/trace_net_engineering_engram_qdrant_adapter_v1.json \ --fee
- L8 `self-rag`: Gate v1 H32 is the final connection gate for the Engram architecture. It joins the artifact outputs from: - H27E real answer-smoke overlay integration - H28 Self-RAG Engram critic - H29 CRAG Engram repair gate - H30 Engram Qdrant/vector adapter - H31 Postgres feedback/memory ledger - optional graph-route guidance manifest The module is intentionally artifact-first. It performs no live LLM calls, no Qdrant IO, no Postgres writes, no OpenSearch IO, no live graph traversal, and no source-truth mutation. It proves
- L9 `crag`: nnection gate for the Engram architecture. It joins the artifact outputs from: - H27E real answer-smoke overlay integration - H28 Self-RAG Engram critic - H29 CRAG Engram repair gate - H30 Engram Qdrant/vector adapter - H31 Postgres feedback/memory ledger - optional graph-route guidance manifest The module is intentionally artifact-first. It performs no live LLM calls, no Qdrant IO, no Postgres writes, no OpenSearch IO, no live graph traversal, and no source-truth mutation. It proves that the runtime chain is rea
- L8 `critic`: the final connection gate for the Engram architecture. It joins the artifact outputs from: - H27E real answer-smoke overlay integration - H28 Self-RAG Engram critic - H29 CRAG Engram repair gate - H30 Engram Qdrant/vector adapter - H31 Postgres feedback/memory ledger - optional graph-route guidance manifest The module is intentionally artifact-first. It performs no live LLM calls, no Qdrant IO, no Postgres writes, no OpenSearch IO, no live graph traversal, and no source-truth mutation. It proves that the runtime

### `docs/trace_net_e2e_crag_retrieval_corrector_v10.md`
- Score: `136`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, table_visual_ocr`
- L5 `self-rag`: # TRACE-Net E2E CRAG Retrieval Corrector v10 This module is Phase 3 of TRACE-Net context/reasoning work. It consumes the Self-RAG context critic v9 artifact and emits corrective retrieval plans for each context pack. If Self-RAG marks a context as ready, v10 records that no retry is needed and the context can proceed to the prompt contract. If Self-RAG marks a context as weak, misrouted, missing citations, missing source trace, or unsafe, v10 creates a non-mutating corrective
- L1 `crag`: # TRACE-Net E2E CRAG Retrieval Corrector v10 This module is Phase 3 of TRACE-Net context/reasoning work. It consumes the Self-RAG context critic v9 artifact and emits corrective retrieval plans for each context pack. If Self-RAG marks a context as ready, v10 records that no retry is needed and the context can proceed to the prompt contract. If Self-RAG marks a context as
- L5 `critic`: # TRACE-Net E2E CRAG Retrieval Corrector v10 This module is Phase 3 of TRACE-Net context/reasoning work. It consumes the Self-RAG context critic v9 artifact and emits corrective retrieval plans for each context pack. If Self-RAG marks a context as ready, v10 records that no retry is needed and the context can proceed to the prompt contract. If Self-RAG marks a context as weak, misrouted, missing citations, missing source trace, or unsafe, v10 creates a non-mutating corrective plan. ## Contrac
- L27 `repair`: penSearch, or other services ## Typical corrective actions - `no_retry_required` - `expand_source_truth_retrieval` - `route_and_field_correction` - `citation_repair` - `guidance_authority_repair` - `human_review_enqueue` - `generic_retrieval_retry` ## Output The build script writes: - `trace_net_e2e_crag_retrieval_corrector_v10.json` - `trace_net_e2e_crag_retrieval_corrector_plans_v10.jsonl` - `trace_net_e2e_crag_retrieval_corrector_v10.md` ## Expected current behavior For the current five passing dynamic co
- L5 `context pack`: This module is Phase 3 of TRACE-Net context/reasoning work. It consumes the Self-RAG context critic v9 artifact and emits corrective retrieval plans for each context pack. If Self-RAG marks a context as ready, v10 records that no retry is needed and the context can proceed to the prompt contract. If Self-RAG marks a context as weak, misrouted, missing citations, missing source trace, or unsafe, v10 creates a non-mutating corrective plan. ## Contract The CRAG corrector is plan-only. It does not: - call an LLM -

### `docs/trace_net_e2e_self_rag_context_critic_v9.md`
- Score: `136`
- Categories: `context_pack, crag, feedback, graph_vector, safety, self_rag, table_visual_ocr`
- L16 `self_rag`: summary, vector/profile, route, and table-route signals as guidance only. - Emits statuses for prompt readiness, CRAG retry, and human review. ## Statuses - `SELF_RAG_CONTEXT_READY`: ready for prompt contract construction. - `SELF_RAG_CONTEXT_WEAK`: usable but has warnings. - `SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY`: retrieval/context mismatch should go to CRAG correction. - `SELF_RAG_CONTEXT_NEEDS_HUMAN_REVIEW`: unsafe authority or guidance/source-truth separation issue.
- L1 `self-rag`: # TRACE-Net E2E Self-RAG Context Critic v9 This module critiques dynamic context packs before they are handed to an LLM. It checks whether each pack has citation-ready source-truth evidence, whether evidence fields match the query intent, whether graph/summary/vector/route guidance is marked as guidance-only, and whether the rules box keeps answer/source-truth authority bl
- L12 `crag`: ly source-truth/citable layer. - Treats graph, summary, vector/profile, route, and table-route signals as guidance only. - Emits statuses for prompt readiness, CRAG retry, and human review. ## Statuses - `SELF_RAG_CONTEXT_READY`: ready for prompt contract construction. - `SELF_RAG_CONTEXT_WEAK`: usable but has warnings. - `SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY`: retrieval/context mismatch should go to CRAG correction. - `SELF_RAG_CONTEXT_NEEDS_HUMAN_REVIEW`: unsafe authority or guidance/source-truth separation issue.
- L1 `critic`: # TRACE-Net E2E Self-RAG Context Critic v9 This module critiques dynamic context packs before they are handed to an LLM. It checks whether each pack has citation-ready source-truth evidence, whether evidence fields match the query intent, whether graph/summary/vector/route guidance is marked as guidance-only, and whether the rules box keeps answer/source-truth authority blocked. ## Contra
- L3 `context pack`: # TRACE-Net E2E Self-RAG Context Critic v9 This module critiques dynamic context packs before they are handed to an LLM. It checks whether each pack has citation-ready source-truth evidence, whether evidence fields match the query intent, whether graph/summary/vector/route guidance is marked as guidance-only, and whether the rules box keeps answer/source-truth authority blocked. ## Contract - Uses prebuilt v8 context packs only

### `docs/trace_net_e2e_live_llm_final_gate_v23.md`
- Score: `135`
- Categories: `context_pack, crag, final_gate, graph_vector, webui`
- L3 `repair`: # TRACE-Net E2E Live LLM Final Gate v23 Validates and repairs live Gemma/LLM drafts before WebUI final answer use. ## Purpose v22 proves that Gemma can write drafts from TRACE-Net context packs. v23 makes those drafts safe for final output by enforcing the authority contract: - direct source-truth evidence is the only proof authority; - graph/Leiden guidance is navigation only; - v2 summaries are meaning/com
- L7 `context pack`: M Final Gate v23 Validates and repairs live Gemma/LLM drafts before WebUI final answer use. ## Purpose v22 proves that Gemma can write drafts from TRACE-Net context packs. v23 makes those drafts safe for final output by enforcing the authority contract: - direct source-truth evidence is the only proof authority; - graph/Leiden guidance is navigation only; - v2 summaries are meaning/compression guidance only; - nearby source-truth context is not direct query proof; - capped/high-degree results must be disclosed;
- L9 `proof`: fts from TRACE-Net context packs. v23 makes those drafts safe for final output by enforcing the authority contract: - direct source-truth evidence is the only proof authority; - graph/Leiden guidance is navigation only; - v2 summaries are meaning/compression guidance only; - nearby source-truth context is not direct query proof; - capped/high-degree results must be disclosed; - final answers must not include non-direct citation markers. ## Repairs performed The gate can repair drafts that: - cite v2 summary gui
- L10 `guidance`: . v23 makes those drafts safe for final output by enforcing the authority contract: - direct source-truth evidence is the only proof authority; - graph/Leiden guidance is navigation only; - v2 summaries are meaning/compression guidance only; - nearby source-truth context is not direct query proof; - capped/high-degree results must be disclosed; - final answers must not include non-direct citation markers. ## Repairs performed The gate can repair drafts that: - cite v2 summary guidance as if it were proof; - ove

### `docs/trace_net_e2e_live_relationship_final_gated_endpoint_v31.md`
- Score: `135`
- Categories: `crag, final_gate, graph_vector, safety, webui`
- L16 `repair`: tual relationship claims. - The endpoint does not scan raw 5TB data, rebuild graph, mutate source truth, or write to services. - Unsafe relationship wording is repaired before user-visible output.
- L13 `guidance`: r before it leaves the endpoint. 3. WebUI receives only the final-gated answer. Safety contract: - Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only. - Direct source-truth evidence is required for factual relationship claims. - The endpoint does not scan raw 5TB data, rebuild graph, mutate source truth, or write to services. - Unsafe relationship wording is repaired before user-visible output.

### `docs/trace_net_engineering_engram_vector_retriever_v1_README.md`
- Score: `133`
- Categories: `crag, engram, graph_vector, page, safety, self_rag`
- L1 `engram`: # TRACE-Net Engineering Engram Vector Retriever v1 H19 adds an artifact-only local retriever over the H18 Engram vector-loader records. It is the dry-run retrieval step before any live Qdrant integration. ## Purpose H17 created typed Engram memory layers. H18 converted those layer-tagged atoms into Qdrant-ready vector payload records. H19 proves that those records can be retriev
- L15 `repair`: any source-truth system. ## Memory role The retrieved Engram records are behavior guidance only. They can shape answer style, route awareness, critique, and repair behavior, but they cannot prove source claims. Manual facts still require current `proof_context` citations. ## Safety contract - No Postgres writes - No Qdrant writes - No OpenSearch writes/uploads - No source-truth mutation - No answer permission - No live Qdrant reads in this artifact-only version ## Build ```bash python -B scripts/build_trace_
- L16 `proof`: nce only. They can shape answer style, route awareness, critique, and repair behavior, but they cannot prove source claims. Manual facts still require current `proof_context` citations. ## Safety contract - No Postgres writes - No Qdrant writes - No OpenSearch writes/uploads - No source-truth mutation - No answer permission - No live Qdrant reads in this artifact-only version ## Build ```bash python -B scripts/build_trace_net_engineering_engram_vector_retriever_v1.py \ --vector-loader local_data/organization/
- L14 `guidance`: be retrieved by question/task intent without contacting Qdrant or mutating any source-truth system. ## Memory role The retrieved Engram records are behavior guidance only. They can shape answer style, route awareness, critique, and repair behavior, but they cannot prove source claims. Manual facts still require current `proof_context` citations. ## Safety contract - No Postgres writes - No Qdrant writes - No OpenSearch writes/uploads - No source-truth mutation - No answer permission - No live Qdrant reads in t
- L4 `qdrant`: gram Vector Retriever v1 H19 adds an artifact-only local retriever over the H18 Engram vector-loader records. It is the dry-run retrieval step before any live Qdrant integration. ## Purpose H17 created typed Engram memory layers. H18 converted those layer-tagged atoms into Qdrant-ready vector payload records. H19 proves that those records can be retrieved by question/task intent without contacting Qdrant or mutating any source-truth system. ## Memory role The retrieved Engram records are behavior guidance only

### `docs/trace_net_engineering_engram_postgres_feedback_ledger_v1_README.md`
- Score: `125`
- Categories: `crag, engram, feedback, page, self_rag`
- L1 `engram`: # TRACE-Net Engineering Engram Postgres Feedback Ledger v1 H31 creates an artifact-first feedback ledger for TRACE-Net Engram memory. It turns answer-smoke, Self-RAG critic, CRAG repair, and optional user feedback JSONL into: - `trace_net_engineering_engram_feedback_ledger_schema_v1.sql` - `trace_net_engineering_engram_feedback_ledger_records_v1.jsonl` - `trace_net_engineering_e
- L5 `self-rag`: # TRACE-Net Engineering Engram Postgres Feedback Ledger v1 H31 creates an artifact-first feedback ledger for TRACE-Net Engram memory. It turns answer-smoke, Self-RAG critic, CRAG repair, and optional user feedback JSONL into: - `trace_net_engineering_engram_feedback_ledger_schema_v1.sql` - `trace_net_engineering_engram_feedback_ledger_records_v1.jsonl` - `trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl` - `trace_net_engineering_engram_postgres_feedback_ledger_v1.json` Safety boundary: - Fe
- L5 `crag`: neering Engram Postgres Feedback Ledger v1 H31 creates an artifact-first feedback ledger for TRACE-Net Engram memory. It turns answer-smoke, Self-RAG critic, CRAG repair, and optional user feedback JSONL into: - `trace_net_engineering_engram_feedback_ledger_schema_v1.sql` - `trace_net_engineering_engram_feedback_ledger_records_v1.jsonl` - `trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl` - `trace_net_engineering_engram_postgres_feedback_ledger_v1.json` Safety boundary: - Feedback is behavio
- L5 `critic`: Net Engineering Engram Postgres Feedback Ledger v1 H31 creates an artifact-first feedback ledger for TRACE-Net Engram memory. It turns answer-smoke, Self-RAG critic, CRAG repair, and optional user feedback JSONL into: - `trace_net_engineering_engram_feedback_ledger_schema_v1.sql` - `trace_net_engineering_engram_feedback_ledger_records_v1.jsonl` - `trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl` - `trace_net_engineering_engram_postgres_feedback_ledger_v1.json` Safety boundary: - Feedback is
- L5 `repair`: ng Engram Postgres Feedback Ledger v1 H31 creates an artifact-first feedback ledger for TRACE-Net Engram memory. It turns answer-smoke, Self-RAG critic, CRAG repair, and optional user feedback JSONL into: - `trace_net_engineering_engram_feedback_ledger_schema_v1.sql` - `trace_net_engineering_engram_feedback_ledger_records_v1.jsonl` - `trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl` - `trace_net_engineering_engram_postgres_feedback_ledger_v1.json` Safety boundary: - Feedback is behavior gui

### `docs/trace_net_engineering_engram_prompt_reliability_h16c_README.md`
- Score: `125`
- Categories: `engram, graph_vector, page, server, table_visual_ocr`
- L1 `engram`: # TRACE-Net H16C Engram Prompt Reliability H16C fixes the H16B full 30-question Engram smoke failure mode where Ollama/Gemma returned a non-empty but truncated answer. The observed q18 answer stopped mid-sentence at `which allows the system to` / `OCR-backed`, so H16B did not retry because it only retried empty responses. ## What this patch adds - `tiff/trace_net_h16c_llm
- L20 `proof`: t grant answer permission and does not mutate source truth. It does not write to Postgres, Qdrant, or OpenSearch. Engram memory remains behavior guidance only; proof still comes only from proof_context citations. ## Expected result Targeted q18 should no longer stop mid-sentence. Final full 30-question H16C smoke should reach at least 28 GOOD with q25/q26 allowed as expected unknown-case PARTIAL records, while keeping: - bad answers = 0 - unsupported claims = 0 - summary used as proof = 0 - invalid citations = 0
- L20 `guidance`: ity. It does not grant answer permission and does not mutate source truth. It does not write to Postgres, Qdrant, or OpenSearch. Engram memory remains behavior guidance only; proof still comes only from proof_context citations. ## Expected result Targeted q18 should no longer stop mid-sentence. Final full 30-question H16C smoke should reach at least 28 GOOD with q25/q26 allowed as expected unknown-case PARTIAL records, while keeping: - bad answers = 0 - unsupported claims = 0 - summary used as proof = 0 - invali
- L3 `ollama`: # TRACE-Net H16C Engram Prompt Reliability H16C fixes the H16B full 30-question Engram smoke failure mode where Ollama/Gemma returned a non-empty but truncated answer. The observed q18 answer stopped mid-sentence at `which allows the system to` / `OCR-backed`, so H16B did not retry because it only retried empty responses. ## What this patch adds - `tiff/trace_net_h16c_llm_answer_reliability_v1.py` - Detects incomplete answer shapes. - Supplies safer Ollama gener
- L20 `qdrant`: contract H16C changes only local generation reliability. It does not grant answer permission and does not mutate source truth. It does not write to Postgres, Qdrant, or OpenSearch. Engram memory remains behavior guidance only; proof still comes only from proof_context citations. ## Expected result Targeted q18 should no longer stop mid-sentence. Final full 30-question H16C smoke should reach at least 28 GOOD with q25/q26 allowed as expected unknown-case PARTIAL records, while keeping: - bad answers = 0 - unsup

### `docs/trace_net_engineering_engram_prompt_retrieval_injector_v1_README.md`
- Score: `125`
- Categories: `crag, engram, graph_vector, page, server`
- L1 `engram`: # TRACE-Net Engineering Engram Prompt Retrieval Injector v1 H20 converts H19 Engram vector retrieval results into compact prompt guidance blocks. ## Purpose H17 defines typed Engram memory layers. H18 exports those atoms as Qdrant-ready local vector records. H19 retrieves relevant atoms for a task/query. H20 packages the retrieved atoms into an LLM-ready prompt section. The pro
- L23 `repair`: writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permission ## Proof boundary Engram retrieval may shape answer behavior, style, repair patterns, and route awareness. It cannot prove manual facts. Source claims still require current TRACE-Net `proof_context` citations. ## Output - `trace_net_engineering_engram_prompt_retrieval_injector_v1.json` - `trace_net_engineering_engram_prompt_retrieval_injector_v1_prompt_bundles.jsonl` - quality-check JSON Each prompt bundle contains selecte
- L9 `proof`: vant atoms for a task/query. H20 packages the retrieved atoms into an LLM-ready prompt section. The prompt section is explicitly **behavior guidance only, not proof**. ## Safety contract H20 is artifact-only: - no Postgres writes - no Qdrant reads or writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permission ## Proof boundary Engram retrieval may shape answer behavior, style, repair patterns, and route awareness. It cannot prove manual facts. Source claims still require current TR
- L3 `guidance`: # TRACE-Net Engineering Engram Prompt Retrieval Injector v1 H20 converts H19 Engram vector retrieval results into compact prompt guidance blocks. ## Purpose H17 defines typed Engram memory layers. H18 exports those atoms as Qdrant-ready local vector records. H19 retrieves relevant atoms for a task/query. H20 packages the retrieved atoms into an LLM-ready prompt section. The prompt section is explicitly **behavior guidance only, not proof**. ## Safety contract H20 is artifact-only
- L7 `qdrant`: nverts H19 Engram vector retrieval results into compact prompt guidance blocks. ## Purpose H17 defines typed Engram memory layers. H18 exports those atoms as Qdrant-ready local vector records. H19 retrieves relevant atoms for a task/query. H20 packages the retrieved atoms into an LLM-ready prompt section. The prompt section is explicitly **behavior guidance only, not proof**. ## Safety contract H20 is artifact-only: - no Postgres writes - no Qdrant reads or writes - no OpenSearch writes/uploads - no source-tr

### `docs/trace_net_engineering_answer_runner_v1_README.md`
- Score: `123`
- Categories: `context_pack, graph_vector, planner, server, table_visual_ocr, webui`
- L6 `context pack`: RACE-Net Engineering Answer Runner v1 H5 chains the engineering-brain stages into one local command: 1. H2 engineering query planner 2. H3 engineering answer context pack 3. H4 engineering answer composer and quality gate The runner preserves the context-engineering split: - `guidance_context`: v2 summaries and planner hints only; not proof. - `proof_context`: source-trace-ready visual/OCR/table records used for claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no sou
- L11 `proof`: gineering answer composer and quality gate The runner preserves the context-engineering split: - `guidance_context`: v2 summaries and planner hints only; not proof. - `proof_context`: source-trace-ready visual/OCR/table records used for claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
- L11 `guidance`: query planner 2. H3 engineering answer context pack 3. H4 engineering answer composer and quality gate The runner preserves the context-engineering split: - `guidance_context`: v2 summaries and planner hints only; not proof. - `proof_context`: source-trace-ready visual/OCR/table records used for claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
- L14 `qdrant`: ies and planner hints only; not proof. - `proof_context`: source-trace-ready visual/OCR/table records used for claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
- L14 `opensearch`: nts only; not proof. - `proof_context`: source-trace-ready visual/OCR/table records used for claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.

### `docs/trace_net_e2e_live_query_pipeline_v15.md`
- Score: `119`
- Categories: `context_pack, crag, final_gate, graph_vector, self_rag, server, table_visual_ocr, webui`
- L10 `self-rag`: routes used by Open WebUI, but returns a richer `trace_net` payload showing the query path through: 1. dynamic retrieval 2. tunnel ranking 3. context pack 4. Self-RAG critic 5. CRAG corrector 6. LLM prompt contract 7. reasoned response draft 8. final answer gate 9. WebUI final answer The stage is intentionally conservative. It serves only final-gated answers that already passed v13. Unknown queries return an audit-only limitation saying the dynamic pipeline must execute before a final answer can be returned. Th
- L11 `crag`: n WebUI, but returns a richer `trace_net` payload showing the query path through: 1. dynamic retrieval 2. tunnel ranking 3. context pack 4. Self-RAG critic 5. CRAG corrector 6. LLM prompt contract 7. reasoned response draft 8. final answer gate 9. WebUI final answer The stage is intentionally conservative. It serves only final-gated answers that already passed v13. Unknown queries return an audit-only limitation saying the dynamic pipeline must execute before a final answer can be returned. The endpoint does not
- L10 `critic`: sed by Open WebUI, but returns a richer `trace_net` payload showing the query path through: 1. dynamic retrieval 2. tunnel ranking 3. context pack 4. Self-RAG critic 5. CRAG corrector 6. LLM prompt contract 7. reasoned response draft 8. final answer gate 9. WebUI final answer The stage is intentionally conservative. It serves only final-gated answers that already passed v13. Unknown queries return an audit-only limitation saying the dynamic pipeline must execute before a final answer can be returned. The endpoin
- L9 `context pack`: penAI-compatible routes used by Open WebUI, but returns a richer `trace_net` payload showing the query path through: 1. dynamic retrieval 2. tunnel ranking 3. context pack 4. Self-RAG critic 5. CRAG corrector 6. LLM prompt contract 7. reasoned response draft 8. final answer gate 9. WebUI final answer The stage is intentionally conservative. It serves only final-gated answers that already passed v13. Unknown queries return an audit-only limitation saying the dynamic pipeline must execute before a final answer can

### `docs/trace_net_e2e_llm_assisted_query_planner_v17.md`
- Score: `118`
- Categories: `context_pack, graph_vector, planner, safety, server, table_visual_ocr`
- L16 `context pack`: guidance only. - Source-truth evidence is required for final factual claims. - Query-time planning must not scan raw 5TB source data. - The LLM reads a compact context pack, not the whole graph or source corpus. ## Tunnel authority Source-truth/proof tunnel: - `table_exact_search_tunnel` Ranking support tunnels: - `table_hybrid_bridge_tunnel` - `qdrant_page_profile_tunnel` Guidance-only tunnels: - `page_summary_tunnel` - `graph_community_tunnel` - `graph_navigation_tunnel` - `route_metadata_tunnel` - `table_
- L20 `proof`: me planning must not scan raw 5TB source data. - The LLM reads a compact context pack, not the whole graph or source corpus. ## Tunnel authority Source-truth/proof tunnel: - `table_exact_search_tunnel` Ranking support tunnels: - `table_hybrid_bridge_tunnel` - `qdrant_page_profile_tunnel` Guidance-only tunnels: - `page_summary_tunnel` - `graph_community_tunnel` - `graph_navigation_tunnel` - `route_metadata_tunnel` - `table_route_summary_tunnel` ## Why this matters A pure hard-coded planner would be too narr
- L12 `guidance`: ies, synonyms, and graph expansion hints. - TRACE-Net validates every plan before execution. - TRACE-Net executes only allowed tunnels. - v2 page summaries are guidance only. - Leiden communities are graph/navigation guidance only. - Source-truth evidence is required for final factual claims. - Query-time planning must not scan raw 5TB source data. - The LLM reads a compact context pack, not the whole graph or source corpus. ## Tunnel authority Source-truth/proof tunnel: - `table_exact_search_tunnel` Ranking su
- L27 `qdrant`: or source corpus. ## Tunnel authority Source-truth/proof tunnel: - `table_exact_search_tunnel` Ranking support tunnels: - `table_hybrid_bridge_tunnel` - `qdrant_page_profile_tunnel` Guidance-only tunnels: - `page_summary_tunnel` - `graph_community_tunnel` - `graph_navigation_tunnel` - `route_metadata_tunnel` - `table_route_summary_tunnel` ## Why this matters A pure hard-coded planner would be too narrow. A pure LLM planner would be too unsafe. v17 establishes the middle path: LLM-assisted planning with de

### `docs/trace_net_engineering_engram_prompt_injector_reliability_v1_README.md`
- Score: `117`
- Categories: `context_pack, engram, graph_vector, table_visual_ocr`
- L1 `engram`: # TRACE-Net Engineering Engram Prompt Injector Reliability v1 H16B hardens the H16 Engram prompt injection layer. ## Why The first H16 run proved that Engram atoms were being injected, but a few local Ollama calls returned empty output on long/complex prompts. The safety counters stayed clean, but the smoke test blocked because no answer text was returned. ## What changed - En
- L12 `proof`: ms are compacted before prompt injection. - If the full prompt fails or Ollama returns no answer text, the runner retries once with a minimal prompt that keeps proof context and scaffold but removes Engram bulk. - If the retry also fails, the runner writes a conservative TRACE-Net scaffold fallback answer so the result is safe, inspectable, and non-empty. - Safe reasoning traces record retry/fallback status. - Engram memory remains behavior guidance only and is never source proof. ## Safety contract - No Postgres
- L15 `guidance`: ffold fallback answer so the result is safe, inspectable, and non-empty. - Safe reasoning traces record retry/fallback status. - Engram memory remains behavior guidance only and is never source proof. ## Safety contract - No Postgres writes. - No Qdrant writes. - No OpenSearch writes/uploads. - No source-truth mutation. - No answer permission granted. - Fallback answers still use proof_context citations when proof exists and say not source-trace-ready when it does not.
- L7 `ollama`: or Reliability v1 H16B hardens the H16 Engram prompt injection layer. ## Why The first H16 run proved that Engram atoms were being injected, but a few local Ollama calls returned empty output on long/complex prompts. The safety counters stayed clean, but the smoke test blocked because no answer text was returned. ## What changed - Engram atoms are compacted before prompt injection. - If the full prompt fails or Ollama returns no answer text, the runner retries once with a minimal prompt that keeps proof contex
- L20 `qdrant`: traces record retry/fallback status. - Engram memory remains behavior guidance only and is never source proof. ## Safety contract - No Postgres writes. - No Qdrant writes. - No OpenSearch writes/uploads. - No source-truth mutation. - No answer permission granted. - Fallback answers still use proof_context citations when proof exists and say not source-trace-ready when it does not.

### `docs/trace_net_engineering_engram_prompt_injector_v1_README.md`
- Score: `117`
- Categories: `engram, graph_vector, page, table_visual_ocr`
- L1 `engram`: # TRACE-Net Engineering Engram Prompt Injector v1 H16 extends the engineering LLM answer smoke runner so it can consume an H15 Engineering Engram Core JSON profile and inject relevant behavior memories into the prompt. The engram block is **behavior guidance only**. It is not source-truth proof, cannot be cited as evidence, does not grant answer permission, and does not mutate so
- L5 `proof`: neering Engram Core JSON profile and inject relevant behavior memories into the prompt. The engram block is **behavior guidance only**. It is not source-truth proof, cannot be cited as evidence, does not grant answer permission, and does not mutate source artifacts or databases. ## Inputs - H15 `trace_net_engineering_engram_core_v1.json` - H13/H14C LLM smoke inputs: planner/context evidence packs and optional question bank ## Outputs - Existing H13/H14C smoke manifest outputs - Prompt files with `TRACE_NET_ENG
- L5 `guidance`: oke runner so it can consume an H15 Engineering Engram Core JSON profile and inject relevant behavior memories into the prompt. The engram block is **behavior guidance only**. It is not source-truth proof, cannot be cited as evidence, does not grant answer permission, and does not mutate source artifacts or databases. ## Inputs - H15 `trace_net_engineering_engram_core_v1.json` - H13/H14C LLM smoke inputs: planner/context evidence packs and optional question bank ## Outputs - Existing H13/H14C smoke manifest ou
- L23 `qdrant`: NET_ENGINEERING_ENGRAM_MEMORY` - Safe reasoning trace fields: - `engram_atom_count` - `engram_ids` - `engram_traits` ## Safety - No writes to Postgres, Qdrant, or OpenSearch - No source-truth mutation - No answer permission - Engram memory is never proof and is never citable evidence
- L23 `opensearch`: RING_ENGRAM_MEMORY` - Safe reasoning trace fields: - `engram_atom_count` - `engram_ids` - `engram_traits` ## Safety - No writes to Postgres, Qdrant, or OpenSearch - No source-truth mutation - No answer permission - Engram memory is never proof and is never citable evidence

### `docs/trace_net_engineering_engram_prompt_reliability_h16d_README.md`
- Score: `117`
- Categories: `crag, engram, graph_vector, table_visual_ocr`
- L1 `engram`: # TRACE-Net H16D Conservative Engram Smoke Reliability Repair H16C fixed q18 in isolation but made the full 30-question smoke less stable by treating too many normal answers as incomplete and forcing retry/fallback. H16D restores the pre-H16C smoke runner from the automatic H16C backup when available, removes aggressive `_h16c_looks_incomplete_llm_answer(...)` call sites, and applies o
- L1 `repair`: # TRACE-Net H16D Conservative Engram Smoke Reliability Repair H16C fixed q18 in isolation but made the full 30-question smoke less stable by treating too many normal answers as incomplete and forcing retry/fallback. H16D restores the pre-H16C smoke runner from the automatic H16C backup when available, removes aggressive `_h16c_looks_incomplete_llm_answer(...)` call sites, and applies only conservative Ollama g
- L12 `proof`: targeted reruns. Safety contract: no DB writes, no vector/search writes, no source-truth mutation, no answer permission. Engram memory remains guidance only; proof still comes from `proof_context` citations.
- L12 `guidance`: is retained for targeted reruns. Safety contract: no DB writes, no vector/search writes, no source-truth mutation, no answer permission. Engram memory remains guidance only; proof still comes from `proof_context` citations.
- L5 `ollama`: oke runner from the automatic H16C backup when available, removes aggressive `_h16c_looks_incomplete_llm_answer(...)` call sites, and applies only conservative Ollama generation options: - `num_predict=900` - `temperature=0.1` The question-bank filter tool is retained for targeted reruns. Safety contract: no DB writes, no vector/search writes, no source-truth mutation, no answer permission. Engram memory remains guidance only; proof still comes from `proof_context` citations.

### `docs/trace_net_e2e_live_llm_prompt_contract_v21.md`
- Score: `111`
- Categories: `context_pack, crag, final_gate, graph_vector, self_rag, server, table_visual_ocr`
- L7 `self_rag`: # TRACE-Net E2E Live LLM Prompt Contract v21 Hotfix v21.1 cleans the LLM prompt contract before live LLM draft integration. ## Fixes - Maps v20 `self_rag_crag_records` into the prompt so `SELF-RAG / CRAG STATUS` is not empty. - Deduplicates source-truth evidence by page, field, and value before it reaches the LLM. - Preserves duplicate counts with `occurrence_count` and contiguous citation numbering after dedupe. - Separates direct source-truth evidence from nearby source-truth/OCR context. - Keeps g
- L7 `self-rag`: Contract v21 Hotfix v21.1 cleans the LLM prompt contract before live LLM draft integration. ## Fixes - Maps v20 `self_rag_crag_records` into the prompt so `SELF-RAG / CRAG STATUS` is not empty. - Deduplicates source-truth evidence by page, field, and value before it reaches the LLM. - Preserves duplicate counts with `occurrence_count` and contiguous citation numbering after dedupe. - Separates direct source-truth evidence from nearby source-truth/OCR context. - Keeps graph/Leiden and v2 summaries as guidance on
- L7 `crag`: # TRACE-Net E2E Live LLM Prompt Contract v21 Hotfix v21.1 cleans the LLM prompt contract before live LLM draft integration. ## Fixes - Maps v20 `self_rag_crag_records` into the prompt so `SELF-RAG / CRAG STATUS` is not empty. - Deduplicates source-truth evidence by page, field, and value before it reaches the LLM. - Preserves duplicate counts with `occurrence_count` and contiguous citation numbering after dedupe. - Separates direct source-truth evidence from nearby source-truth/OCR context. - Keeps graph/Leid
- L16 `context pack`: icit when group counts are truncated for prompt size. ## Contract This stage builds LLM-ready prompt messages but does not call an LLM. The LLM reads compact context packs, not raw 5TB corpus data or the full graph. Source-truth evidence is the only proof authority. Graph/Leiden, v2 summaries, route metadata, vector hints, nearby OCR context, and aggregation metadata are guidance/disclosure layers only. A final gate is required after any LLM draft.
- L16 `proof`: ady prompt messages but does not call an LLM. The LLM reads compact context packs, not raw 5TB corpus data or the full graph. Source-truth evidence is the only proof authority. Graph/Leiden, v2 summaries, route metadata, vector hints, nearby OCR context, and aggregation metadata are guidance/disclosure layers only. A final gate is required after any LLM draft.

### `docs/trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1_README.md`
- Score: `109`
- Categories: `engram, graph_vector, page`
- L1 `engram`: # TRACE-Net Engineering Engram Answer-Smoke Overlay Integration Gate v1 H26 is an artifact-only gate between the H25 targeted overlay LLM smoke and a future patch that wires retrieved Engram overlays into the real engineering answer-smoke builder. It validates that the targeted H24/H25 overlays are safe, question-scoped, and ready to be exposed behind an explicit CLI flag such as
- L15 `proof`: ant reads or writes. - No OpenSearch writes or uploads. - No source-truth mutation. - No answer permission. - Engram overlays are behavior guidance only, never proof. ## Why this step exists The full 30-question Gemma smoke can take hours. H26 prevents the next integration patch from using a full run as the default debug loop. The gate requires targeted question IDs first and produces a deterministic overlay map for the next explicit-flag patch.
- L15 `guidance`: gres writes. - No Qdrant reads or writes. - No OpenSearch writes or uploads. - No source-truth mutation. - No answer permission. - Engram overlays are behavior guidance only, never proof. ## Why this step exists The full 30-question Gemma smoke can take hours. H26 prevents the next integration patch from using a full run as the default debug loop. The gate requires targeted question IDs first and produces a deterministic overlay map for the next explicit-flag patch.
- L11 `qdrant`: d ready to be exposed behind an explicit CLI flag such as `--engram-answer-runner-overlay-map`. ## Safety contract - No LLM calls. - No Postgres writes. - No Qdrant reads or writes. - No OpenSearch writes or uploads. - No source-truth mutation. - No answer permission. - Engram overlays are behavior guidance only, never proof. ## Why this step exists The full 30-question Gemma smoke can take hours. H26 prevents the next integration patch from using a full run as the default debug loop. The gate requires targeted
- L12 `opensearch`: an explicit CLI flag such as `--engram-answer-runner-overlay-map`. ## Safety contract - No LLM calls. - No Postgres writes. - No Qdrant reads or writes. - No OpenSearch writes or uploads. - No source-truth mutation. - No answer permission. - Engram overlays are behavior guidance only, never proof. ## Why this step exists The full 30-question Gemma smoke can take hours. H26 prevents the next integration patch from using a full run as the default debug loop. The gate requires targeted question IDs first and produ

### `docs/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1_README.md`
- Score: `109`
- Categories: `engram, graph_vector, page`
- L1 `engram`: # TRACE-Net Engineering Engram Prompt Retrieval LLM Smoke v1 (H22) H22 performs a small targeted LLM-readiness smoke over H21 retrieved prompt guidance. It is intentionally not a 30-question engineering answer smoke. The goal is to verify that retrieved Engram memory can be placed in a prompt while preserving the proof boundary: - Engram memory is behavior guidance only. - Manua
- L5 `proof`: is intentionally not a 30-question engineering answer smoke. The goal is to verify that retrieved Engram memory can be placed in a prompt while preserving the proof boundary: - Engram memory is behavior guidance only. - Manual facts require current proof_context citations. - Engram memory cannot grant answer permission. - No Postgres/Qdrant/OpenSearch writes are attempted. - No source-truth mutation is allowed. Modes: - `artifact`: deterministic safe scaffold, no LLM call. - `ollama`: calls local Ollama with co
- L3 `guidance`: # TRACE-Net Engineering Engram Prompt Retrieval LLM Smoke v1 (H22) H22 performs a small targeted LLM-readiness smoke over H21 retrieved prompt guidance. It is intentionally not a 30-question engineering answer smoke. The goal is to verify that retrieved Engram memory can be placed in a prompt while preserving the proof boundary: - Engram memory is behavior guidance only. - Manual facts require current proof_context citations. - Engram memory cannot grant answer permission. - No Postgres/Qdrant/Op
- L16 `ollama`: No Postgres/Qdrant/OpenSearch writes are attempted. - No source-truth mutation is allowed. Modes: - `artifact`: deterministic safe scaffold, no LLM call. - `ollama`: calls local Ollama with compact H21 prompt guidance and synthetic empty proof_context to verify safe boundary behavior. This module is a bridge before a deeper prompt-retrieval integration with the engineering answer runner.
- L10 `qdrant`: Engram memory is behavior guidance only. - Manual facts require current proof_context citations. - Engram memory cannot grant answer permission. - No Postgres/Qdrant/OpenSearch writes are attempted. - No source-truth mutation is allowed. Modes: - `artifact`: deterministic safe scaffold, no LLM call. - `ollama`: calls local Ollama with compact H21 prompt guidance and synthetic empty proof_context to verify safe boundary behavior. This module is a bridge before a deeper prompt-retrieval integration with the engin

### `docs/trace_net_engineering_engram_prompt_retrieval_smoke_v1_README.md`
- Score: `109`
- Categories: `engram, graph_vector, page`
- L1 `engram`: # TRACE-Net Engineering Engram Prompt Retrieval Smoke v1 H21 validates the artifact-only integration boundary between H20 retrieved Engram prompt bundles and future LLM answering. It does not call Gemma/Ollama and does not perform live Qdrant IO. It confirms that retrieved Engram atoms can be compacted into prompt guidance blocks while preserving the core boundary: - Engram memo
- L8 `proof`: compacted into prompt guidance blocks while preserving the core boundary: - Engram memory shapes behavior only. - Manual/source claims still require current `proof_context` citations. - Engram memory cannot grant answer permission. - Engram memory cannot mutate source truth. - No Postgres, Qdrant, or OpenSearch writes are attempted. ## Inputs - `engineering_engram_prompt_retrieval_injector_v1` manifest from H20. ## Outputs - `trace_net_engineering_engram_prompt_retrieval_smoke_v1.json` - `trace_net_engineerin
- L5 `guidance`: future LLM answering. It does not call Gemma/Ollama and does not perform live Qdrant IO. It confirms that retrieved Engram atoms can be compacted into prompt guidance blocks while preserving the core boundary: - Engram memory shapes behavior only. - Manual/source claims still require current `proof_context` citations. - Engram memory cannot grant answer permission. - Engram memory cannot mutate source truth. - No Postgres, Qdrant, or OpenSearch writes are attempted. ## Inputs - `engineering_engram_prompt_retri
- L5 `ollama`: al Smoke v1 H21 validates the artifact-only integration boundary between H20 retrieved Engram prompt bundles and future LLM answering. It does not call Gemma/Ollama and does not perform live Qdrant IO. It confirms that retrieved Engram atoms can be compacted into prompt guidance blocks while preserving the core boundary: - Engram memory shapes behavior only. - Manual/source claims still require current `proof_context` citations. - Engram memory cannot grant answer permission. - Engram memory cannot mutate source
- L5 `qdrant`: tifact-only integration boundary between H20 retrieved Engram prompt bundles and future LLM answering. It does not call Gemma/Ollama and does not perform live Qdrant IO. It confirms that retrieved Engram atoms can be compacted into prompt guidance blocks while preserving the core boundary: - Engram memory shapes behavior only. - Manual/source claims still require current `proof_context` citations. - Engram memory cannot grant answer permission. - Engram memory cannot mutate source truth. - No Postgres, Qdrant, or

### `docs/trace_net_engineering_engram_vector_loader_v1_README.md`
- Score: `109`
- Categories: `engram, graph_vector, page`
- L1 `engram`: # TRACE-Net Engineering Engram Vector Loader v1 H18 converts the H17 Engineering Engram Memory Layer manifest into a local, Qdrant-ready vector payload. This is an artifact-only module. It does **not** connect to Qdrant, Postgres, OpenSearch, Ollama, or any live service. It creates deterministic local vector records so the payload shape can be tested, reviewed, committed, and lat
- L24 `proof`: vector_loader_v1_quality_check.json` ## Memory role Engram vector records are behavior-retrieval records. They are guidance only. They must not be treated as proof for manual facts. Current `proof_context` remains the only source for factual engineering claims. ## Safety contract - no Postgres writes - no Qdrant writes - no OpenSearch writes - no source-truth mutation - no answer permission - no source claims from Engram memory alone ## Why deterministic vectors? H18 uses a deterministic hashing encoder so CI
- L23 `guidance`: _v1.jsonl` - `trace_net_engineering_engram_vector_loader_v1_quality_check.json` ## Memory role Engram vector records are behavior-retrieval records. They are guidance only. They must not be treated as proof for manual facts. Current `proof_context` remains the only source for factual engineering claims. ## Safety contract - no Postgres writes - no Qdrant writes - no OpenSearch writes - no source-truth mutation - no answer permission - no source claims from Engram memory alone ## Why deterministic vectors? H18
- L7 `ollama`: ram Memory Layer manifest into a local, Qdrant-ready vector payload. This is an artifact-only module. It does **not** connect to Qdrant, Postgres, OpenSearch, Ollama, or any live service. It creates deterministic local vector records so the payload shape can be tested, reviewed, committed, and later used by a gated live loader. ## Input - `trace_net_engineering_engram_memory_layers_v1.json` ## Output - `trace_net_engineering_engram_vector_loader_v1.json` - `trace_net_engineering_engram_vector_loader_v1.jsonl`
- L4 `qdrant`: # TRACE-Net Engineering Engram Vector Loader v1 H18 converts the H17 Engineering Engram Memory Layer manifest into a local, Qdrant-ready vector payload. This is an artifact-only module. It does **not** connect to Qdrant, Postgres, OpenSearch, Ollama, or any live service. It creates deterministic local vector records so the payload shape can be tested, reviewed, committed, and later used by a gated live loader. ## Input - `trace_net_engineering_engram_memory_layers_v1.json` ##

### `docs/trace_net_e2e_relationship_final_gate_hardener_v30.md`
- Score: `105`
- Categories: `crag, final_gate, graph_vector, table_visual_ocr, webui`
- L3 `repair`: # TRACE-Net E2E Relationship Final Gate Hardener v30 This phase validates and repairs relationship/synthesis answer drafts before they can become WebUI-ready final answers. ## Contract - Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only. - Relationship/synthesis answers may use guidance for navigation, but not as proof authority. - Direct source-truth evidence is required for factual relationship claims. - The
- L8 `proof`: tract - Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only. - Relationship/synthesis answers may use guidance for navigation, but not as proof authority. - Direct source-truth evidence is required for factual relationship claims. - The gate catches claims such as “the Leiden community proves...”, “the V2 summary confirms...”, or “the nomenclature means...” when those are not backed by direct source-truth evidence. - This stage does not call an LLM, scan raw 5TB source data, rebuild the graph,
- L7 `guidance`: lationship/synthesis answer drafts before they can become WebUI-ready final answers. ## Contract - Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only. - Relationship/synthesis answers may use guidance for navigation, but not as proof authority. - Direct source-truth evidence is required for factual relationship claims. - The gate catches claims such as “the Leiden community proves...”, “the V2 summary confirms...”, or “the nomenclature means...” when those are not backed by direct source-tru
- L19 `final_gate`: ruth, or write to Postgres/Qdrant/OpenSearch. ## Inputs - `trace_net_e2e_relationship_router_hardening_v29_1.json` ## Outputs - `trace_net_e2e_relationship_final_gate_hardener_v30.json` - `trace_net_e2e_relationship_final_gate_hardener_records_v30.jsonl` - `trace_net_e2e_relationship_final_gate_hardener_v30.md`
- L11 `qdrant`: ect source-truth evidence. - This stage does not call an LLM, scan raw 5TB source data, rebuild the graph, rerun OCR, mutate source truth, or write to Postgres/Qdrant/OpenSearch. ## Inputs - `trace_net_e2e_relationship_router_hardening_v29_1.json` ## Outputs - `trace_net_e2e_relationship_final_gate_hardener_v30.json` - `trace_net_e2e_relationship_final_gate_hardener_records_v30.jsonl` - `trace_net_e2e_relationship_final_gate_hardener_v30.md`

### `docs/trace_net_engineering_answer_context_pack_v1_README.md`
- Score: `105`
- Categories: `context_pack, graph_vector, planner, server, table_visual_ocr`
- L1 `context pack`: # TRACE-Net Engineering Answer Context Pack v1 This module builds the first combined engineering context pack from an engineering query planner result. It keeps two strict buckets: - `guidance_context`: v2 summaries and planner hints. These are guidance only and cannot prove answer claims. - `proof_context`: source-trace-ready visual, OCR nomenclature, and table/OCR records that can su
- L8 `proof`: planner result. It keeps two strict buckets: - `guidance_context`: v2 summaries and planner hints. These are guidance only and cannot prove answer claims. - `proof_context`: source-trace-ready visual, OCR nomenclature, and table/OCR records that can support factual claims. Safety contract: - no Postgres writes - no Qdrant writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permission The context pack is intended for a later engineering answer composer and quality gate.
- L7 `guidance`: wer Context Pack v1 This module builds the first combined engineering context pack from an engineering query planner result. It keeps two strict buckets: - `guidance_context`: v2 summaries and planner hints. These are guidance only and cannot prove answer claims. - `proof_context`: source-trace-ready visual, OCR nomenclature, and table/OCR records that can support factual claims. Safety contract: - no Postgres writes - no Qdrant writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permi
- L13 `qdrant`: roof_context`: source-trace-ready visual, OCR nomenclature, and table/OCR records that can support factual claims. Safety contract: - no Postgres writes - no Qdrant writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permission The context pack is intended for a later engineering answer composer and quality gate.
- L14 `opensearch`: ce-trace-ready visual, OCR nomenclature, and table/OCR records that can support factual claims. Safety contract: - no Postgres writes - no Qdrant writes - no OpenSearch writes/uploads - no source-truth mutation - no answer permission The context pack is intended for a later engineering answer composer and quality gate.

### `docs/trace_net_engineering_query_planner_v1_README.md`
- Score: `102`
- Categories: `graph_vector, planner, server, table_visual_ocr`
- L11 `proof`: s such as figures, items, part numbers, and topics; - task type classification; - required and optional TRACE-Net routes; - guidance pages from v2 summaries; - proof requirements; - forbidden claims; - safety counters. V2 summaries are always marked as guidance only. They may guide route selection and answer framing, but they may not prove final factual claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission. ## H2B strict gu
- L3 `guidance`: # TRACE-Net Engineering Query Planner v1 Builds a guidance-aware route plan for broad engineering questions. This module consumes the v2 summary guidance index and produces a structured plan containing: - extracted entities such as figures, items, part numbers, and topics; - task type classification; - required and optional TRACE-Net routes; - guidance pages from v2 summaries; - proof requirements; - forb
- L17 `qdrant`: rked as guidance only. They may guide route selection and answer framing, but they may not prove final factual claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission. ## H2B strict guidance behavior For specific entity questions (figure, item/callout, exact part number, or part family), the planner no longer backfills `guidance_pages` with generic illustrated-parts-list or maintenance-manual summaries. V2 summaries are selec
- L17 `opensearch`: nly. They may guide route selection and answer framing, but they may not prove final factual claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission. ## H2B strict guidance behavior For specific entity questions (figure, item/callout, exact part number, or part family), the planner no longer backfills `guidance_pages` with generic illustrated-parts-list or maintenance-manual summaries. V2 summaries are selected only when they
- L17 `postgres`: maries are always marked as guidance only. They may guide route selection and answer framing, but they may not prove final factual claims. Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission. ## H2B strict guidance behavior For specific entity questions (figure, item/callout, exact part number, or part family), the planner no longer backfills `guidance_pages` with generic illustrated-parts-list or maintenance-manual summaries. V2

### `docs/trace_net/ACTIVE_PROJECT_MAP.md`
- Score: `97`
- Categories: `context_pack, crag, engram, feedback, graph_vector, planner, self_rag, table_visual_ocr, webui`
- L17 `engram`: isual/image route summaries as guidance only - graph/Postgres relationships as retrieval and source resolution - Qdrant semantic recall as retrieval guidance - Engram behavior memory as guidance only ## Active safety rules - No source-truth mutation. - No answer permission unless explicitly authorized. - No Postgres/Qdrant/OpenSearch writes unless explicitly live-write gated. - Engram, summaries, graph hits, vector hits, and feedback are not proof. - Only current proof_context citations prove manual/source claims
- L5 `self-rag`: # TRACE-Net Active Project Map ## Active runtime direction Open WebUI -> TRACE-Net bridge -> query planner -> read-only tools -> context pack -> Gemma4 -> Self-RAG critic -> CRAG repair -> final cited answer. Gemma is not the database. TRACE-Net builds the evidence binder. Gemma drafts from it. ## Active proof lanes - OCR/source text - table evidence - exact part lookup - visual/image route summaries as guidance only - graph/Postgres relationships as retrieval and source resolution - Qdrant semantic recall
- L5 `crag`: ve Project Map ## Active runtime direction Open WebUI -> TRACE-Net bridge -> query planner -> read-only tools -> context pack -> Gemma4 -> Self-RAG critic -> CRAG repair -> final cited answer. Gemma is not the database. TRACE-Net builds the evidence binder. Gemma drafts from it. ## Active proof lanes - OCR/source text - table evidence - exact part lookup - visual/image route summaries as guidance only - graph/Postgres relationships as retrieval and source resolution - Qdrant semantic recall as retrieval guidan
- L5 `critic`: E-Net Active Project Map ## Active runtime direction Open WebUI -> TRACE-Net bridge -> query planner -> read-only tools -> context pack -> Gemma4 -> Self-RAG critic -> CRAG repair -> final cited answer. Gemma is not the database. TRACE-Net builds the evidence binder. Gemma drafts from it. ## Active proof lanes - OCR/source text - table evidence - exact part lookup - visual/image route summaries as guidance only - graph/Postgres relationships as retrieval and source resolution - Qdrant semantic recall as retrie
- L5 `repair`: oject Map ## Active runtime direction Open WebUI -> TRACE-Net bridge -> query planner -> read-only tools -> context pack -> Gemma4 -> Self-RAG critic -> CRAG repair -> final cited answer. Gemma is not the database. TRACE-Net builds the evidence binder. Gemma drafts from it. ## Active proof lanes - OCR/source text - table evidence - exact part lookup - visual/image route summaries as guidance only - graph/Postgres relationships as retrieval and source resolution - Qdrant semantic recall as retrieval guidance -

### `docs/trace_net_e2e_context_pack_builder_v1.md`
- Score: `97`
- Categories: `context_pack, graph_vector, safety, server`
- L13 `context_pack`: ng. ## Inputs - `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime/trace_net_e2e_hybrid_retrieval_runtime_v1.json` ## Outputs - `trace_net_e2e_context_pack_builder_v1.json` - `trace_net_e2e_context_pack_builder_v1_quality.json` - `trace_net_e2e_context_packs_v1.jsonl` - `trace_net_e2e_context_items_v1.jsonl` - `trace_net_e2e_context_pack_builder_v1_inspect.md` ## Safety contract - `answer_permission=false` - `can_answer_directly=false` - `can_prove_claims=false` - `source_truth_mutation_allowed=f
- L1 `context pack`: # TRACE-Net E2E Context Pack Builder v1 This module consumes `trace_net_e2e_hybrid_retrieval_runtime_v1.json` and creates local context packs for later final-gate review. It is intentionally retrieval-only. It does not answer, prove claims, mutate source truth, or write to Postgres, Qdrant, OpenSearch, or upload anything. ## Inputs - `local_data/organization/trace_net/e
- L5 `qdrant`: al context packs for later final-gate review. It is intentionally retrieval-only. It does not answer, prove claims, mutate source truth, or write to Postgres, Qdrant, OpenSearch, or upload anything. ## Inputs - `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime/trace_net_e2e_hybrid_retrieval_runtime_v1.json` ## Outputs - `trace_net_e2e_context_pack_builder_v1.json` - `trace_net_e2e_context_pack_builder_v1_quality.json` - `trace_net_e2e_context_packs_v1.jsonl` - `trace_net_e2e_context_items_v1.json
- L5 `opensearch`: xt packs for later final-gate review. It is intentionally retrieval-only. It does not answer, prove claims, mutate source truth, or write to Postgres, Qdrant, OpenSearch, or upload anything. ## Inputs - `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime/trace_net_e2e_hybrid_retrieval_runtime_v1.json` ## Outputs - `trace_net_e2e_context_pack_builder_v1.json` - `trace_net_e2e_context_pack_builder_v1_quality.json` - `trace_net_e2e_context_packs_v1.jsonl` - `trace_net_e2e_context_items_v1.jsonl` - `tr
- L5 `postgres`: reates local context packs for later final-gate review. It is intentionally retrieval-only. It does not answer, prove claims, mutate source truth, or write to Postgres, Qdrant, OpenSearch, or upload anything. ## Inputs - `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime/trace_net_e2e_hybrid_retrieval_runtime_v1.json` ## Outputs - `trace_net_e2e_context_pack_builder_v1.json` - `trace_net_e2e_context_pack_builder_v1_quality.json` - `trace_net_e2e_context_packs_v1.jsonl` - `trace_net_e2e_context_ite

### `docs/trace_net_e2e_dynamic_context_pack_v8.md`
- Score: `97`
- Categories: `context_pack, graph_vector, self_rag, table_visual_ocr`
- L13 `self-rag`: un OCR, page classification, embeddings, page summaries, graph construction, table extraction, source ingest, or service writes. This prepares the next phase: Self-RAG context critique.
- L3 `context_pack`: # TRACE-Net E2E Dynamic Context Pack v8 `trace_net_e2e_dynamic_context_pack_v8` is the first context-engineering layer after dynamic hybrid retrieval and tunnel ranking. It consumes the v6 dynamic tunnel ranker and builds LLM-readable context packs with three explicit sections: 1. **Evidence box** — source-truth records that may be cited. 2. **Guidance box** — vector/page-profile, summary, graph, route, and table-rout
- L1 `context pack`: # TRACE-Net E2E Dynamic Context Pack v8 `trace_net_e2e_dynamic_context_pack_v8` is the first context-engineering layer after dynamic hybrid retrieval and tunnel ranking. It consumes the v6 dynamic tunnel ranker and builds LLM-readable context packs with three explicit sections: 1. **Evidence box** — source-truth records that may be cited. 2. **Guidance box** — vector/page-profil
- L8 `proof`: ource-truth records that may be cited. 2. **Guidance box** — vector/page-profile, summary, graph, route, and table-route hints that help navigation but are not proof. 3. **Rules box** — answer permissions, citation policy, uncertainty behavior, and non-mutation contract. The module does not call an LLM. It also does not rerun OCR, page classification, embeddings, page summaries, graph construction, table extraction, source ingest, or service writes. This prepares the next phase: Self-RAG context critique.
- L8 `guidance`: 6 dynamic tunnel ranker and builds LLM-readable context packs with three explicit sections: 1. **Evidence box** — source-truth records that may be cited. 2. **Guidance box** — vector/page-profile, summary, graph, route, and table-route hints that help navigation but are not proof. 3. **Rules box** — answer permissions, citation policy, uncertainty behavior, and non-mutation contract. The module does not call an LLM. It also does not rerun OCR, page classification, embeddings, page summaries, graph construction, t

### `docs/trace_net_e2e_final_gate_smoke_v1.md`
- Score: `97`
- Categories: `final_gate, graph_vector, page, self_rag`
- L13 `proof`: come audit-only responses; - no record mutates source truth; - no record writes to Postgres, Qdrant, OpenSearch, or uploads anything; - no record grants direct proof/answer authority in this smoke artifact. This proves the shape of the final response layer before the live API is wired.
- L12 `qdrant`: tion-backed **response drafts for review**; - insufficient packs become audit-only responses; - no record mutates source truth; - no record writes to Postgres, Qdrant, OpenSearch, or uploads anything; - no record grants direct proof/answer authority in this smoke artifact. This proves the shape of the final response layer before the live API is wired.
- L12 `opensearch`: ked **response drafts for review**; - insufficient packs become audit-only responses; - no record mutates source truth; - no record writes to Postgres, Qdrant, OpenSearch, or uploads anything; - no record grants direct proof/answer authority in this smoke artifact. This proves the shape of the final response layer before the live API is wired.
- L12 `postgres`: ecome citation-backed **response drafts for review**; - insufficient packs become audit-only responses; - no record mutates source truth; - no record writes to Postgres, Qdrant, OpenSearch, or uploads anything; - no record grants direct proof/answer authority in this smoke artifact. This proves the shape of the final response layer before the live API is wired.

### `docs/trace_net_e2e_executed_plan_context_pack_v19.md`
- Score: `89`
- Categories: `context_pack, graph_vector, table_visual_ocr`
- L1 `context pack`: # TRACE-Net E2E Executed Plan Context Pack v19 Builds live context packs from v18 dynamic plan execution records. The v19 contract keeps proof and guidance separate: - `SOURCE-TRUTH EVIDENCE` is the only proof authority for final claims. - Leiden/community graph records are guidance only. - v2 page summaries are guidance only. - Capped/high-degree result sets disclose total vs returne
- L5 `proof`: # TRACE-Net E2E Executed Plan Context Pack v19 Builds live context packs from v18 dynamic plan execution records. The v19 contract keeps proof and guidance separate: - `SOURCE-TRUTH EVIDENCE` is the only proof authority for final claims. - Leiden/community graph records are guidance only. - v2 page summaries are guidance only. - Capped/high-degree result sets disclose total vs returned counts and drill-down options. - The LLM reads compact context packs only, not the raw corpus or entire gra
- L5 `guidance`: # TRACE-Net E2E Executed Plan Context Pack v19 Builds live context packs from v18 dynamic plan execution records. The v19 contract keeps proof and guidance separate: - `SOURCE-TRUTH EVIDENCE` is the only proof authority for final claims. - Leiden/community graph records are guidance only. - v2 page summaries are guidance only. - Capped/high-degree result sets disclose total vs returned counts and drill-down options. - The LLM reads compact context packs only, not the raw corpus or entire graph. This

### `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.md`
- Score: `87`
- Categories: `crag, final_gate, graph_vector, self_rag`
- L10 `self_rag`: retry/fallback telemetry for every answer. - Richer page profile answers that combine source-truth page records with v2 summary guidance. - Quality gates for `self_rag_sample_count`, `crag_sample_count`, and `crag_retry_required_count`. - No new proof authority: source-truth records remain the only proof authority; graph, Leiden, v2 summaries, route metadata, and nomenclature metadata remain guidance only. ## Endpoint model `trace-net-e2e-live-gemma-answer-writer-v33` ## Key telemetry - `self_rag_status` - `se
- L3 `self-rag`: E Live Gemma Answer Writer Endpoint v33 v33 keeps the v32/v32.2 behavior where Gemma is always called through compact prompt packages, then adds deterministic Self-RAG/CRAG telemetry and a richer page-profile package. ## Adds in v33 - Self-RAG package-quality telemetry for every answer. - CRAG retry/fallback telemetry for every answer. - Richer page profile answers that combine source-truth page records with v2 summary guidance. - Quality gates for `self_rag_sample_count`, `crag_sample_count`, and `crag_retry_re
- L3 `crag`: mma Answer Writer Endpoint v33 v33 keeps the v32/v32.2 behavior where Gemma is always called through compact prompt packages, then adds deterministic Self-RAG/CRAG telemetry and a richer page-profile package. ## Adds in v33 - Self-RAG package-quality telemetry for every answer. - CRAG retry/fallback telemetry for every answer. - Richer page profile answers that combine source-truth page records with v2 summary guidance. - Quality gates for `self_rag_sample_count`, `crag_sample_count`, and `crag_retry_required_co
- L11 `proof`: source-truth page records with v2 summary guidance. - Quality gates for `self_rag_sample_count`, `crag_sample_count`, and `crag_retry_required_count`. - No new proof authority: source-truth records remain the only proof authority; graph, Leiden, v2 summaries, route metadata, and nomenclature metadata remain guidance only. ## Endpoint model `trace-net-e2e-live-gemma-answer-writer-v33` ## Key telemetry - `self_rag_status` - `self_rag_package_quality` - `self_rag_answerable_from_package` - `self_rag_direct_source_
- L9 `guidance`: emetry for every answer. - CRAG retry/fallback telemetry for every answer. - Richer page profile answers that combine source-truth page records with v2 summary guidance. - Quality gates for `self_rag_sample_count`, `crag_sample_count`, and `crag_retry_required_count`. - No new proof authority: source-truth records remain the only proof authority; graph, Leiden, v2 summaries, route metadata, and nomenclature metadata remain guidance only. ## Endpoint model `trace-net-e2e-live-gemma-answer-writer-v33` ## Key telem

### `docs/trace_net_e2e_live_llm_draft_adapter_v22.md`
- Score: `87`
- Categories: `graph_vector, server, table_visual_ocr, webui`
- L14 `proof`: wer. It is a draft that must be checked by the next final-gate stage before WebUI final-answer use. ## Authority contract - Source-truth evidence is the only proof authority. - Graph / Leiden guidance remains navigation-only. - v2 summaries remain meaning/compression guidance-only. - Aggregation and cap metadata must be disclosed when results are capped. - LLM reasoning fields are metadata only; they are not passed as answer text. - Query-time draft generation does not scan the raw 5TB corpus, rebuild graph, reru
- L15 `guidance`: ecked by the next final-gate stage before WebUI final-answer use. ## Authority contract - Source-truth evidence is the only proof authority. - Graph / Leiden guidance remains navigation-only. - v2 summaries remain meaning/compression guidance-only. - Aggregation and cap metadata must be disclosed when results are capped. - LLM reasoning fields are metadata only; they are not passed as answer text. - Query-time draft generation does not scan the raw 5TB corpus, rebuild graph, rerun OCR, mutate source truth, or wri
- L8 `ollama`: cts to an LLM draft adapter. The adapter supports two modes: - `simulate`: deterministic local draft generation for tests and offline contract validation. - `ollama`: real OpenAI-compatible Ollama call, intended for `gemma4:26b`. The output is **not** a final answer. It is a draft that must be checked by the next final-gate stage before WebUI final-answer use. ## Authority contract - Source-truth evidence is the only proof authority. - Graph / Leiden guidance remains navigation-only. - v2 summaries remain mean

### `docs/trace_net_e2e_live_orchestrator_endpoint_v25.md`
- Score: `87`
- Categories: `graph_vector, page, table_visual_ocr, webui`
- L18 `proof`: m direct source-truth evidence and final-gate rules. 8. Return a WebUI-ready OpenAI-compatible response. Safety contract: - Source-truth evidence is the only proof authority. - Graph/Leiden and v2 summaries are guidance only. - Nearby OCR/table context is not direct proof. - The endpoint reads prebuilt artifacts and does not scan raw 5TB data. - It does not rebuild the graph, rerun OCR, mutate source truth, or write to services. - If no direct evidence is found, the endpoint returns an audit-only no-claim respons
- L9 `guidance`: pipeline at request time. Flow: 1. Parse user query into a query plan. 2. Search prebuilt source-truth exact-search evidence. 3. Attach bounded Leiden/graph guidance and v2 page-summary guidance. 4. Build a compact prompt. 5. Optionally call a local LLM through Ollama. 6. Treat the LLM output as a draft only. 7. Rebuild the final answer from direct source-truth evidence and final-gate rules. 8. Return a WebUI-ready OpenAI-compatible response. Safety contract: - Source-truth evidence is the only proof authority
- L11 `ollama`: exact-search evidence. 3. Attach bounded Leiden/graph guidance and v2 page-summary guidance. 4. Build a compact prompt. 5. Optionally call a local LLM through Ollama. 6. Treat the LLM output as a draft only. 7. Rebuild the final answer from direct source-truth evidence and final-gate rules. 8. Return a WebUI-ready OpenAI-compatible response. Safety contract: - Source-truth evidence is the only proof authority. - Graph/Leiden and v2 summaries are guidance only. - Nearby OCR/table context is not direct proof. - Th

### `docs/trace_net_e2e_final_answer_gate_v13.md`
- Score: `81`
- Categories: `final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- L30 `proof`: rkers; - answer text does not mention evidence values/pages without citation markers; - graph, summary, vector, route, and table-route guidance are not used as proof; - unsupported physical part descriptions are blocked; - limitations are present when evidence is incomplete; - answer permission, direct answer authority, claim-proof authority, and source-truth mutation remain blocked. ## Contract The output is ready for WebUI endpoint integration, but still keeps: - `answer_permission=false` - `can_answer_directl
- L30 `guidance`: text contains citation markers; - answer text does not mention evidence values/pages without citation markers; - graph, summary, vector, route, and table-route guidance are not used as proof; - unsupported physical part descriptions are blocked; - limitations are present when evidence is incomplete; - answer permission, direct answer authority, claim-proof authority, and source-truth mutation remain blocked. ## Contract The output is ready for WebUI endpoint integration, but still keeps: - `answer_permission=fal
- L7 `qdrant`: claims, call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph artifacts, rerun table extraction, mutate source truth, or write to Postgres/Qdrant/OpenSearch. ## Inputs - `local_data/organization/trace_net/e2e_reasoned_response_draft/trace_net_e2e_reasoned_response_draft_v12.json` ## Outputs - `trace_net_e2e_final_answer_gate_v13.json` - `trace_net_e2e_final_answer_gate_records_v13.jsonl` - `trace_net_e2e_final_answer_gate_citations_v13.jsonl` - `trace_net_e2e_final_answer_gate_v13.md` ## C
- L7 `opensearch`: call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph artifacts, rerun table extraction, mutate source truth, or write to Postgres/Qdrant/OpenSearch. ## Inputs - `local_data/organization/trace_net/e2e_reasoned_response_draft/trace_net_e2e_reasoned_response_draft_v12.json` ## Outputs - `trace_net_e2e_final_answer_gate_v13.json` - `trace_net_e2e_final_answer_gate_records_v13.jsonl` - `trace_net_e2e_final_answer_gate_citations_v13.jsonl` - `trace_net_e2e_final_answer_gate_v13.md` ## Checks
- L7 `postgres`: factual claims, call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph artifacts, rerun table extraction, mutate source truth, or write to Postgres/Qdrant/OpenSearch. ## Inputs - `local_data/organization/trace_net/e2e_reasoned_response_draft/trace_net_e2e_reasoned_response_draft_v12.json` ## Outputs - `trace_net_e2e_final_answer_gate_v13.json` - `trace_net_e2e_final_answer_gate_records_v13.jsonl` - `trace_net_e2e_final_answer_gate_citations_v13.jsonl` - `trace_net_e2e_final_answer_gate_v13.

### `docs/trace_net_e2e_image_visual_observer_route_v34.md`
- Score: `81`
- Categories: `crag, feedback, graph_vector, self_rag, server, table_visual_ocr, webui`
- L19 `self-rag`: write to Postgres, Qdrant, or OpenSearch. ## Route shape ```text image upload / page image / crop → image quality card → LLaVA visual observer card → visual Self-RAG card → visual CRAG retry/fallback card → final-gated safe answer ``` ## Endpoint Model: ```text trace-net-e2e-image-visual-observer-llava-v34 ``` Base URL from Windows: ```text http://127.0.0.1:8029/v1 ``` Base URL from Open WebUI Docker: ```text http://host.docker.internal:8029/v1 ``` ## Open WebUI image use The endpoint accepts OpenAI-com
- L20 `crag`: ant, or OpenSearch. ## Route shape ```text image upload / page image / crop → image quality card → LLaVA visual observer card → visual Self-RAG card → visual CRAG retry/fallback card → final-gated safe answer ``` ## Endpoint Model: ```text trace-net-e2e-image-visual-observer-llava-v34 ``` Base URL from Windows: ```text http://127.0.0.1:8029/v1 ``` Base URL from Open WebUI Docker: ```text http://host.docker.internal:8029/v1 ``` ## Open WebUI image use The endpoint accepts OpenAI-compatible message content
- L8 `proof`: , scanned page images, diagrams, and callout-like visual pages. ## Contract - LLaVA observations are guidance only. - Image observations are not source-truth proof. - Source-truth confirmation is required before factual part/manual claims. - Low-confidence visual observations require human review or crop/retry. - This stage does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. ## Route shape ```text image upload / page image / crop → image quality card → LLaVA visual observer card
- L7 `guidance`: troduces the first image/visual route for uploaded images, scanned page images, diagrams, and callout-like visual pages. ## Contract - LLaVA observations are guidance only. - Image observations are not source-truth proof. - Source-truth confirmation is required before factual part/manual claims. - Low-confidence visual observations require human review or crop/retry. - This stage does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. ## Route shape ```text image upload / page image
- L46 `ollama`: en WebUI image use The endpoint accepts OpenAI-compatible message content lists with image payloads, including `image_url` data URLs. In live mode it can call Ollama LLaVA using `/api/generate` with a base64 image array. ## Safety note This route can say what it visually observes. It cannot prove what a part is, what a procedure requires, or what a manual relationship means unless another source-truth route confirms that evidence.

### `docs/trace_net_e2e_image_visual_observer_route_v34_1.md`
- Score: `81`
- Categories: `crag, feedback, graph_vector, self_rag, server, table_visual_ocr, webui`
- L20 `self-rag`: ute shape ```text image upload / page image / crop → image quality card → LLaVA visual observer card → Mermaid/JSON diagram draft card when requested → visual Self-RAG card → visual CRAG retry/fallback card → final-gated safe answer ``` ## Endpoint Model: ```text trace-net-e2e-image-diagram-draft-llava-v34-1 ``` Base URL from Windows: ```text http://127.0.0.1:8030/v1 ``` Base URL from Open WebUI Docker: ```text http://host.docker.internal:8030/v1 ``` ## Open WebUI image use The endpoint accepts OpenAI-com
- L21 `crag`: e upload / page image / crop → image quality card → LLaVA visual observer card → Mermaid/JSON diagram draft card when requested → visual Self-RAG card → visual CRAG retry/fallback card → final-gated safe answer ``` ## Endpoint Model: ```text trace-net-e2e-image-diagram-draft-llava-v34-1 ``` Base URL from Windows: ```text http://127.0.0.1:8030/v1 ``` Base URL from Open WebUI Docker: ```text http://host.docker.internal:8030/v1 ``` ## Open WebUI image use The endpoint accepts OpenAI-compatible message content
- L8 `proof`: , scanned page images, diagrams, and callout-like visual pages. ## Contract - LLaVA observations are guidance only. - Image observations are not source-truth proof. - Source-truth confirmation is required before factual part/manual claims. - Low-confidence visual observations require human review or crop/retry. - This stage does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. ## Route shape ```text image upload / page image / crop → image quality card → LLaVA visual observer card
- L7 `guidance`: v34.1 extends the image/visual route for uploaded images, scanned page images, diagrams, and callout-like visual pages. ## Contract - LLaVA observations are guidance only. - Image observations are not source-truth proof. - Source-truth confirmation is required before factual part/manual claims. - Low-confidence visual observations require human review or crop/retry. - This stage does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. ## Route shape ```text image upload / page image
- L47 `ollama`: en WebUI image use The endpoint accepts OpenAI-compatible message content lists with image payloads, including `image_url` data URLs. In live mode it can call Ollama LLaVA using `/api/generate` with a base64 image array. ## Safety note This route can say what it visually observes and can return a Mermaid/JSON diagram draft. It does not generate final technical drawings or proof-authority diagrams. It cannot prove what a part is, what a procedure requires, or what a manual relationship means unless another source

### `docs/trace_net_e2e_llm_prompt_contract_v11.md`
- Score: `81`
- Categories: `context_pack, crag, graph_vector, page, self_rag, server, table_visual_ocr`
- L8 `self-rag`: E LLM Prompt Contract v11 `trace_net_e2e_llm_prompt_contract_v11` is Phase 4 of the latter-half TRACE-Net pipeline. It consumes: - dynamic context pack v8 - Self-RAG context critic v9 - CRAG retrieval corrector v10 It emits strict LLM-ready prompt packets, but it does **not** call an LLM. ## Contract The prompt builder is non-mutating and uses prebuilt artifacts only. It does not rerun retrieval, OCR, page classification, embeddings, summaries, graph construction, table extraction, or source ingest. ## Promp
- L9 `crag`: race_net_e2e_llm_prompt_contract_v11` is Phase 4 of the latter-half TRACE-Net pipeline. It consumes: - dynamic context pack v8 - Self-RAG context critic v9 - CRAG retrieval corrector v10 It emits strict LLM-ready prompt packets, but it does **not** call an LLM. ## Contract The prompt builder is non-mutating and uses prebuilt artifacts only. It does not rerun retrieval, OCR, page classification, embeddings, summaries, graph construction, table extraction, or source ingest. ## Prompt sections Each prompt packe
- L8 `critic`: ract v11 `trace_net_e2e_llm_prompt_contract_v11` is Phase 4 of the latter-half TRACE-Net pipeline. It consumes: - dynamic context pack v8 - Self-RAG context critic v9 - CRAG retrieval corrector v10 It emits strict LLM-ready prompt packets, but it does **not** call an LLM. ## Contract The prompt builder is non-mutating and uses prebuilt artifacts only. It does not rerun retrieval, OCR, page classification, embeddings, summaries, graph construction, table extraction, or source ingest. ## Prompt sections Each
- L7 `context pack`: # TRACE-Net E2E LLM Prompt Contract v11 `trace_net_e2e_llm_prompt_contract_v11` is Phase 4 of the latter-half TRACE-Net pipeline. It consumes: - dynamic context pack v8 - Self-RAG context critic v9 - CRAG retrieval corrector v10 It emits strict LLM-ready prompt packets, but it does **not** call an LLM. ## Contract The prompt builder is non-mutating and uses prebuilt artifacts only. It does not rerun retrieval, OCR, page classification, embeddings, summaries, graph construction, table extraction, or source
- L22 `proof`: EVIDENCE` — only this section can support factual claims. 2. `GUIDANCE ONLY` — graph, summary, vector/page-profile, route, and table-route context. This is not proof. 3. `ANSWER RULES` — citation, uncertainty, and safety rules. 4. Self-RAG status — whether the context is safe and ready. 5. CRAG status — whether retry/review is needed before generation. ## Output files - `trace_net_e2e_llm_prompt_contract_v11.json` - `trace_net_e2e_llm_prompt_contract_records_v11.jsonl` - `trace_net_e2e_llm_prompt_messages_v11.jso

### `docs/trace_net_engineering_real_answer_smoke_test_v1_README.md`
- Score: `81`
- Categories: `feedback, graph_vector, page, safety, server, table_visual_ocr, webui`
- L13 `proof`: ion intent. - `PARTIAL`: runner passed but the answer needs human review or intent coverage is weak. - `BAD`: unsupported claims, invalid citations, summary-as-proof, unsafe record, or other hard violation. - `BLOCKED`: the runner could not produce a passing answer. ## Default 30-question bank 1. What does figure 69 show? 2. What does figure 75 show? 3. What does figure 91 show? 4. Compare figure 69 and figure 75. 5. Compare figure 75 and figure 91. 6. Find part number 120-50645-005 and cite the source. 7. Find p
- L5 `openwebui`: e engineering answer runner over a 30-question real-answer smoke set. It is an evaluation harness only: it does not change retrieval, evidence, LLaVA, endpoint/OpenWebUI, answer-composer logic, or source-truth artifacts. ## What it measures The harness grades each answer as: - `GOOD`: runner passed, source-trace-ready evidence is present, and the answer shape matches the question intent. - `PARTIAL`: runner passed but the answer needs human review or intent coverage is weak. - `BAD`: unsupported claims, invalid
- L52 `qdrant`: ? 29. Can v2 summaries alone prove Figure 69 part identity? 30. Give the engineering limitations for Figure 91. ## Safety contract - No Postgres writes. - No Qdrant writes. - No OpenSearch writes/uploads. - No source-truth mutation. - No answer permission. - V2 summaries may guide route planning/framing only; they are not proof.
- L53 `opensearch`: es alone prove Figure 69 part identity? 30. Give the engineering limitations for Figure 91. ## Safety contract - No Postgres writes. - No Qdrant writes. - No OpenSearch writes/uploads. - No source-truth mutation. - No answer permission. - V2 summaries may guide route planning/framing only; they are not proof.
- L51 `postgres`: r what Figure 69 shows? 29. Can v2 summaries alone prove Figure 69 part identity? 30. Give the engineering limitations for Figure 91. ## Safety contract - No Postgres writes. - No Qdrant writes. - No OpenSearch writes/uploads. - No source-truth mutation. - No answer permission. - V2 summaries may guide route planning/framing only; they are not proof.

### `docs/trace_net_e2e_live_deterministic_answer_planner_v28.md`
- Score: `79`
- Categories: `graph_vector, server, table_visual_ocr`
- L14 `proof`: int skips the LLM for deterministic source-truth answer classes and reserves Gemma for relationship/synthesis questions. Source-truth evidence remains the only proof authority; graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only. ## v28.1 polish and metadata hotfix This hotfix keeps the endpoint version at v28 but tightens demo/readiness behavior: - Polishes deterministic answer whitespace, including citation spacing and joined words such as `doesnot` and `onlyand`. -
- L14 `guidance`: lationship/synthesis questions. Source-truth evidence remains the only proof authority; graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only. ## v28.1 polish and metadata hotfix This hotfix keeps the endpoint version at v28 but tightens demo/readiness behavior: - Polishes deterministic answer whitespace, including citation spacing and joined words such as `doesnot` and `onlyand`. - Preserves strict-filter audit metadata: - `raw_candidate_match_count` - `target_uniq

### `docs/trace_net_e2e_live_dynamic_fallback_v16_1.md`
- Score: `79`
- Categories: `graph_vector, server, table_visual_ocr`

### `docs/trace_net_e2e_live_eval_latency_harness_v26.md`
- Score: `79`
- Categories: `graph_vector, page, table_visual_ocr`

### `docs/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.md`
- Score: `79`
- Categories: `final_gate, server, webui`
- L39 `guidance`: part number drill-down by field - page-scoped source-truth records - page-scoped covered part numbers - page profile package using page records plus v2 summary guidance All supported normal intents still flow through: TRACE-Net package -> Gemma answer writer -> final gate -> WebUI answer.

### `docs/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.md`
- Score: `79`
- Categories: `graph_vector, page, table_visual_ocr`
- L5 `proof`: of the v25 live orchestrator. The fast path may skip the LLM only for strict exact lookups and audit-only exact misses. Source-truth evidence remains the only proof authority. Graph/Leiden, v2 summaries, and nearby context remain guidance only. The endpoint does not scan raw 5TB data, rebuild graph artifacts, rerun OCR, mutate source truth, or write to external services.
- L5 `guidance`: strict exact lookups and audit-only exact misses. Source-truth evidence remains the only proof authority. Graph/Leiden, v2 summaries, and nearby context remain guidance only. The endpoint does not scan raw 5TB data, rebuild graph artifacts, rerun OCR, mutate source truth, or write to external services.

### `docs/trace_net_e2e_live_relationship_synthesis_planner_v29.md`
- Score: `79`
- Categories: `graph_vector, table_visual_ocr, webui`
- L7 `proof`: relationship/synthesis path for graph, Leiden, related-page, neighbor, and connection-style questions. ## Safety contract - Source-truth evidence is the only proof authority. - Graph/Leiden and v2 summaries are guidance only. - Source-truth seed evidence proves only the seed facts, not inferred relationships. - The LLM may draft relationship synthesis, but TRACE-Net rebuilds and final-gates the final answer. - No query-time raw 5TB scan, graph rebuild, OCR rerun, source-truth mutation, or service write is allowed
- L8 `guidance`: d-page, neighbor, and connection-style questions. ## Safety contract - Source-truth evidence is the only proof authority. - Graph/Leiden and v2 summaries are guidance only. - Source-truth seed evidence proves only the seed facts, not inferred relationships. - The LLM may draft relationship synthesis, but TRACE-Net rebuilds and final-gates the final answer. - No query-time raw 5TB scan, graph rebuild, OCR rerun, source-truth mutation, or service write is allowed. ## Response modes - Existing v28 deterministic mo

### `docs/trace_net_image_route_openwebui_endpoint_v1_README.md`
- Score: `74`
- Categories: `graph_vector, page, webui`
- L1 `openwebui`: # TRACE-Net Image Route OpenWebUI Endpoint v1 This module provides a standalone OpenAI-compatible endpoint wrapper for the now-integrated `image_or_diagram` fast-chat route. It does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. It shells into `tiff/trace_net_fast_chat_runner_v1.py`, reads the resulting PASS artifact, and returns either `/v1/chat/c
- L5 `chat/completions`: ot write to Postgres, Qdrant, or OpenSearch. It shells into `tiff/trace_net_fast_chat_runner_v1.py`, reads the resulting PASS artifact, and returns either `/v1/chat/completions` or `/api/trace-net/ask` JSON. The endpoint is intentionally standalone so it can be smoke-tested before touching the existing live endpoint stack.
- L5 `qdrant`: OpenAI-compatible endpoint wrapper for the now-integrated `image_or_diagram` fast-chat route. It does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. It shells into `tiff/trace_net_fast_chat_runner_v1.py`, reads the resulting PASS artifact, and returns either `/v1/chat/completions` or `/api/trace-net/ask` JSON. The endpoint is intentionally standalone so it can be smoke-tested before touching the existing live endpoint stack.
- L5 `opensearch`: patible endpoint wrapper for the now-integrated `image_or_diagram` fast-chat route. It does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. It shells into `tiff/trace_net_fast_chat_runner_v1.py`, reads the resulting PASS artifact, and returns either `/v1/chat/completions` or `/api/trace-net/ask` JSON. The endpoint is intentionally standalone so it can be smoke-tested before touching the existing live endpoint stack.
- L5 `postgres`: standalone OpenAI-compatible endpoint wrapper for the now-integrated `image_or_diagram` fast-chat route. It does not mutate source truth and does not write to Postgres, Qdrant, or OpenSearch. It shells into `tiff/trace_net_fast_chat_runner_v1.py`, reads the resulting PASS artifact, and returns either `/v1/chat/completions` or `/api/trace-net/ask` JSON. The endpoint is intentionally standalone so it can be smoke-tested before touching the existing live endpoint stack.

### `docs/trace_net_e2e_codebase_checklist_v1.md`
- Score: `73`
- Categories: `context_pack, final_gate, page, self_rag, table_visual_ocr, webui`
- L9 `context pack`: It checks: - key E2E source modules are present - table exact/search/bridge artifacts exist and are PASS - query planning/routing, planned hybrid retrieval, context pack, sufficiency, final gate, RAG demo, API wrapper, and local endpoint artifacts exist and are PASS - authority/write counters remain zero when present - the current WebUI demo path is artifact-backed planned hybrid retrieval, not yet a fully dynamic per-query live runtime Run: ```bash python scripts/run_trace_net_e2e_codebase_checklist_v1.py \

### `docs/trace_net_e2e_evidence_sufficiency_gate_v1.md`
- Score: `73`
- Categories: `context_pack, final_gate, graph_vector, safety, self_rag, table_visual_ocr`
- L16 `context_pack`: Typical build: ```bash python scripts/build_trace_net_e2e_evidence_sufficiency_gate_v1.py \ --e2e-context-pack-builder local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json \ --output-dir local_data/organization/trace_net/e2e_evidence_sufficiency_gate \ --min-source-context-packs 5 \ --min-context-packs-with-items 5 \ --min-evidence-gate-records 5 \ --min-sufficient-context-packs 4 \ --min-final-gate-ready-packs 4 \ --min-total-evidence-items 20 \ -
- L3 `context pack`: # TRACE-Net E2E Evidence Sufficiency Gate v1 This module reviews E2E context packs and decides whether each pack is ready for final-gate review or should remain audit-only because the evidence is insufficient. It is intentionally conservative: - sufficiency means **ready for final-gate review**, not answer permission; - table/context evidence remains retrieval/ranking-only until the final gate; - no source truth is mutated;
- L10 `qdrant`: ate review**, not answer permission; - table/context evidence remains retrieval/ranking-only until the final gate; - no source truth is mutated; - no Postgres, Qdrant, OpenSearch, or upload writes occur. Typical build: ```bash python scripts/build_trace_net_e2e_evidence_sufficiency_gate_v1.py \ --e2e-context-pack-builder local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json \ --output-dir local_data/organization/trace_net/e2e_evidence_sufficiency_gate \ --min-
- L10 `opensearch`: ew**, not answer permission; - table/context evidence remains retrieval/ranking-only until the final gate; - no source truth is mutated; - no Postgres, Qdrant, OpenSearch, or upload writes occur. Typical build: ```bash python scripts/build_trace_net_e2e_evidence_sufficiency_gate_v1.py \ --e2e-context-pack-builder local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json \ --output-dir local_data/organization/trace_net/e2e_evidence_sufficiency_gate \ --min-source-c
- L10 `postgres`: or final-gate review**, not answer permission; - table/context evidence remains retrieval/ranking-only until the final gate; - no source truth is mutated; - no Postgres, Qdrant, OpenSearch, or upload writes occur. Typical build: ```bash python scripts/build_trace_net_e2e_evidence_sufficiency_gate_v1.py \ --e2e-context-pack-builder local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json \ --output-dir local_data/organization/trace_net/e2e_evidence_sufficiency_gate

### `docs/trace_net_e2e_rag_demo_report_v1.md`
- Score: `73`
- Categories: `context_pack, final_gate, graph_vector, page, self_rag, server`
- L7 `context pack`: es the current artifact-driven E2E RAG demo chain: 1. E2E query planning/routing with graph and summary tunnels 2. Planned hybrid retrieval runtime 3. Planned context pack builder 4. Planned evidence sufficiency gate 5. Planned final gate smoke The report is a local demo/status artifact. It confirms that the chain is ready for an API wrapper, but it does not grant answer authority, mutate source truth, or write runtime services. Graph and summaries are navigation tunnels: they can route and rank evidence, but th

### `docs/trace_net_e2e_webui_final_answer_endpoint_v14.md`
- Score: `73`
- Categories: `final_gate, graph_vector, page, server, table_visual_ocr, webui`
- L10 `chat/completions`: rtifact-backed and non-mutating. It reads the final answer gate report and exposes: - `GET /health` - `GET /v1/models` - `POST /api/trace-net/ask` - `POST /v1/chat/completions` It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services. Open WebUI base URL from Docker: ```text http://host.docker.internal:8017/v1 ``` Windows/Git Bash test URL: ```text http://127.0.0.1:8017/v1 ``` Model: ```text trace-net-e2e-webui-

### `docs/trace_net_engineering_exact_part_lookup_support_v1_README.md`
- Score: `73`
- Categories: `context_pack, graph_vector, page, server, table_visual_ocr, webui`
- L9 `proof`: v2 summaries as guidance only. It does not permit answer permission, source-truth mutation, or external writes. ## Main behavior - Adds `exact_part_evidence` proof-context records for requested part numbers found in trusted table/exact artifacts. - Preserves `table_ocr_proof`, `ocr_nomenclature`, and `visual_figure_link` evidence when available. - Updates the composer so exact-part questions answer in part-first language rather than figure-first language. - Keeps unsupported claims such as interchangeability, eff
- L5 `guidance`: ions can use source-trace-ready exact/table evidence, OCR-backed nomenclature, and any linked visual evidence already present. The patch keeps v2 summaries as guidance only. It does not permit answer permission, source-truth mutation, or external writes. ## Main behavior - Adds `exact_part_evidence` proof-context records for requested part numbers found in trusted table/exact artifacts. - Preserves `table_ocr_proof`, `ocr_nomenclature`, and `visual_figure_link` evidence when available. - Updates the composer so
- L32 `qdrant`: _v1.json \ --output-dir local_data/organization/trace_net/engineering_answer_runner_v1_exact_part_120_50645_005 ``` ## Safety - Postgres writes: disabled - Qdrant writes: disabled - OpenSearch writes/uploads: disabled - source-truth mutation: disabled - answer permission: false
- L33 `opensearch`: local_data/organization/trace_net/engineering_answer_runner_v1_exact_part_120_50645_005 ``` ## Safety - Postgres writes: disabled - Qdrant writes: disabled - OpenSearch writes/uploads: disabled - source-truth mutation: disabled - answer permission: false
- L31 `postgres`: t_table_exact_search_adapter_v1.json \ --output-dir local_data/organization/trace_net/engineering_answer_runner_v1_exact_part_120_50645_005 ``` ## Safety - Postgres writes: disabled - Qdrant writes: disabled - OpenSearch writes/uploads: disabled - source-truth mutation: disabled - answer permission: false

## Highest-signal archived/reference files

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- Score: `283`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/stage checklist that proves which gates were actually executed. This bridge is intentionally pre-answer and artifact-only: - it does not call Gemma - it does not replace the WebUI server yet - it does not execute database/vector/search writes - it does not mutate source truth - it does not grant answer permission
- Functions: _read_json(path)@L53; _write_json(path, payload)@L59; _write_jsonl(path, records)@L64; _as_path(value)@L71; _path_status(path)@L77; _stage_row()@L83; _safe_summary(payload)@L108; _records(payload)@L113; _stage_used_row(tool_id, label, report_path, payload, count_key)@L118; _artifact_tool_rows(context_pack_payload, input_paths)@L134; _crag_row(crag_payload, crag_path, self_rag_payload)@L175; _checklist_text(rows)@L204; _rollup_safety(stage_payloads)@L217; _import_stage_builders()@L244; build_webui_self_rag_crag_bridge()@L260; _write_markdown(path, payload)@L470; check_webui_self_rag_crag_bridge_quality()@L503; main_build(argv)@L562
- CLI args: --question, --kernel, --output-dir, --route-dispatch-handoff, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --image-visual-observer, --max-records-per-slot, --min-high-signal-capsules, --min-evidence-strength-score, --quality, --report-path, --write-json, --min-checklist-count, --min-used-tool-count, --require-query-planner-used, --require-context-pack-builder-used, --require-self-rag-used, --require-crag-evaluated, --require-no-answer-permission, --require-no-source-truth-mutation, --require-no-write-attempts, --require-tool-status
- Tiff imports: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner; from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint; from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder; from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check; from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan
- Has __main__ guard.

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- Score: `247`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L7; test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch)@L13; test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path)@L113; test_checklist_text_includes_reasons()@L121; fake_query_planner()@L19; fake_blueprint()@L28; fake_pack_builder()@L37; fake_self_rag()@L58; fake_crag()@L72
- Tiff imports: from tiff import trace_net_webui_self_rag_crag_bridge_v1

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- Score: `239`
- Categories: `context_pack, crag, graph_vector, page, planner, self_rag, server, webui`

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/README_trace_net_webui_self_rag_crag_bridge_v1.md`
- Score: `239`
- Categories: `crag, graph_vector, page, planner, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_stage_dir_fix2.md`
- Score: `231`
- Categories: `crag, graph_vector, page, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_self_rag_crag_bridge_v1_visual_context.md`
- Score: `231`
- Categories: `crag, graph_vector, page, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Score: `231`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, webui`
- Functions: test_quality_check_passes_for_required_brain_gates(tmp_path)@L7; test_quality_check_fails_when_self_rag_not_used(tmp_path)@L46; test_quality_check_supports_explicit_tool_status_requirements(tmp_path)@L80
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py`
- Score: `217`
- Categories: `page, self_rag, server, webui`
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_build
- Has __main__ guard.

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/scripts/check_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Score: `217`
- Categories: `page, self_rag, server, webui`
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_check
- Has __main__ guard.

### `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Score: `209`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: load_json(path)@L21; write_json(path, data)@L25; write_jsonl(path, rows)@L30; _as_int(value, default)@L37; _as_bool(value, default)@L52; _first_present(mapping, keys, default)@L62; _first_list(mapping, keys)@L69; _count_records(value)@L77; _nested(mapping, path, default)@L99; _extract_context_packs(report)@L108; _get_evidence_records(pack)@L170; _get_graph_guidance_records(pack)@L194; _get_summary_guidance_records(pack)@L207; _get_aggregation_box(pack)@L220; _has_answer_rules(pack)@L227; _guidance_authority_ok(pack)@L236; evaluate_pack(pack, idx)@L261; _quality_check(name, observed, op, expected)@L400
- CLI args: --min-context-packs, --min-self-rag-evaluations, --min-crag-plans, --min-ready-for-llm, --min-contexts-with-source-truth-evidence, --min-contexts-with-graph-guidance, --min-contexts-with-v2-summary-guidance, --min-contexts-with-aggregation-or-cap-disclosure, --max-retry-required-count, --max-audit-only-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --executed-plan-context-pack, --output-dir, --quality
- Has __main__ guard.

### `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_script_imports.py`
- Score: `199`
- Categories: `self_rag, server, webui`
- Functions: test_build_script_imports()@L5; test_check_script_imports()@L15

### `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/check_trace_net_e2e_live_self_rag_crag_evaluator_v20_quality.py`
- Score: `177`
- Categories: `crag, page, self_rag, server`
- Functions: main()@L14
- CLI args: --report-path, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json
- Has __main__ guard.

### `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Score: `173`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server`
- Functions: _args()@L10; sample_pack(capped)@L32; test_evaluate_pack_ready_with_cap_disclosure()@L54; test_evaluate_pack_weak_without_evidence()@L62; test_build_report_passes_quality(tmp_path)@L71; test_graph_proof_authority_violation_blocks()@L84
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import build_report, evaluate_pack

### `docs/trace_net/archive/debug_outputs/dot_tilde/docs/trace_net_e2e_live_self_rag_crag_evaluator_v20.md`
- Score: `165`
- Categories: `context_pack, crag, graph_vector, self_rag, server`

### `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/build_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Score: `159`
- Categories: `page, self_rag, server`
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main
- Has __main__ guard.

### `docs/trace_net/archive/debug_outputs/dot_tilde/tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20_script_imports.py`
- Score: `149`
- Categories: `self_rag, server, table_visual_ocr`
- Functions: test_live_self_rag_crag_evaluator_v20_scripts_importable()@L7

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_visual_context.md`
- Score: `91`
- Categories: `crag, graph_vector, page, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_final_gate_v1.md`
- Score: `73`
- Categories: `final_gate, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_json_writer_fix2.md`
- Score: `73`
- Categories: `context_pack, graph_vector, page, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1.md`
- Score: `67`
- Categories: `page, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3.md`
- Score: `67`
- Categories: `crag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_pack_v1.md`
- Score: `65`
- Categories: `context_pack, graph_vector, page, safety, server`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_pack_v1_answer_support_expansion_fix.md`
- Score: `65`
- Categories: `context_pack, graph_vector, page, safety, server`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_force_writer_dirs.md`
- Score: `65`
- Categories: `context_pack, graph_vector, page, server, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_crag_retry_plan_v1.md`
- Score: `64`
- Categories: `context_pack, crag, self_rag`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_self_rag_check_v1.md`
- Score: `64`
- Categories: `context_pack, crag, self_rag`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dynamic_final_gate_execution_v1.md`
- Score: `57`
- Categories: `feedback, final_gate, graph_vector, server`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1.md`
- Score: `57`
- Categories: `context_pack, graph_vector, planner, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_blueprint_v1_writer_fix.md`
- Score: `57`
- Categories: `context_pack, graph_vector, server, webui`

### `docs/trace_net/archive/debug_outputs/dot_tilde/scripts/fix_trace_net_engineering_eval_short_run_dirs_v1.py`
- Score: `53`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`
- Functions: _insert_import(text)@L18; _insert_helper(text)@L32; patch_text(text)@L52; apply_fix(repo_root, require_quality_pass)@L78; main()@L157
- CLI args: --repo-root, --require-quality-pass
- Has __main__ guard.

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_webui_answer_server_v1_3_bridge_v1.md`
- Score: `51`
- Categories: `server, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_e2e_tool_usage_audit_v1.md`
- Score: `49`
- Categories: `crag, final_gate, graph_vector, page, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_claims_v1.md`
- Score: `49`
- Categories: `context_pack, feedback, final_gate, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_sufficiency_critic_v1.md`
- Score: `49`
- Categories: `feedback, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_decision_recorder_v1.md`
- Score: `49`
- Categories: `crag, engram, feedback, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_queue_v1.md`
- Score: `49`
- Categories: `context_pack, crag, engram, feedback, graph_vector, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_triage_v1.md`
- Score: `49`
- Categories: `crag, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_synthetic_incident_console_v1.md`
- Score: `49`
- Categories: `feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/debug_outputs/dot_tilde/tiff/trace_net_incremental_orchestrator_v1.py`
- Score: `45`
- Categories: `graph_vector, page, safety, server, table_visual_ocr`
- Doc: TRACE-Net Incremental Orchestrator v1. This module converts a Step 24 incremental corpus manifest into a safe, read-only job plan. It does not execute OCR, extraction, embedding, Qdrant, OpenSearch, graph writeback, or Leiden jobs. It only decides which jobs would run for new/changed/removed pages.
- Functions: now_iso()@L58; stable_json(value)@L62; stable_hash(value, length)@L66; read_json(path)@L70; write_json(path, payload)@L75; write_jsonl(path, rows)@L80; get_manifest_pages(manifest)@L87; get_source_records(manifest)@L92; page_sort_key(page_id)@L100; unique_sorted(values)@L110; dirty_pages_for_stage(pages, stage)@L114; page_ids_for(pages)@L123; collect_candidate_ids(pages)@L127; build_job_for_stage(stage, job_type, job_family, runner_hint, payload_keys, pages)@L139; job_priority(stage)@L176; build_removal_jobs(manifest)@L188; build_incremental_orchestrator_plan()@L220; summarize_plan()@L330
- CLI args: --manifest, --output-dir, --require-page-count, --full-rescan-threshold, --quality, --report-path, --require-page-count, --max-unchanged-page-reprocess, --require-no-full-rescan, --allow-jobs-when-clean, --write-json
- Has __main__ guard.

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_context_pack_builder_v1.md`
- Score: `41`
- Categories: `context_pack, page`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_draft_final_gate_v1.md`
- Score: `41`
- Categories: `final_gate, graph_vector`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus_router.md`
- Score: `41`
- Categories: `context_pack, crag, feedback, graph_vector, page, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_snippet_cleaner_v1.md`
- Score: `41`
- Categories: `context_pack, feedback, final_gate, graph_vector, page, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_feedback_memory_v1.md`
- Score: `41`
- Categories: `feedback, final_gate, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_human_review_workbench_v1.md`
- Score: `41`
- Categories: `feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_it_issue_origin_test_matrix_v1.md`
- Score: `41`
- Categories: `feedback, final_gate, graph_vector, page, self_rag, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_opensearch_adapter_v1.md`
- Score: `41`
- Categories: `feedback, final_gate, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_opensearch_loader_smoke_v1.md`
- Score: `41`
- Categories: `context_pack, feedback, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_webui_visual_context_bridge_v1.md`
- Score: `41`
- Categories: `graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_engineering_query_planner_v1.md`
- Score: `38`
- Categories: `planner`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_algorithm_policy.md`
- Score: `33`
- Categories: `context_pack, crag, graph_vector, page, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_claim_critic_v1.md`
- Score: `33`
- Categories: `feedback, final_gate, graph_vector, self_rag, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_answer_context_evidence_enricher_v1.md`
- Score: `33`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_ask_api_dynamic_retrieval_v2.md`
- Score: `33`
- Categories: `feedback, final_gate, graph_vector, page, server, webui`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_citation_answer_draft_v1.md`
- Score: `33`
- Categories: `context_pack, final_gate, graph_vector, page, safety, server`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage4_policy_simulation.md`
- Score: `33`
- Categories: `context_pack, crag, graph_vector, page, safety, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_confidence_stage5_control.md`
- Score: `33`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_corrective_retrieval_planner_v1.md`
- Score: `33`
- Categories: `crag, feedback, graph_vector, page, safety, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_dublin_core_crosswalk_v1.md`
- Score: `33`
- Categories: `context_pack, feedback, graph_vector, page, server, table_visual_ocr`

### `docs/trace_net/archive/legacy_readme_folder/README/README_trace_net_evidence_consensus.md`
- Score: `33`
- Categories: `context_pack, crag, graph_vector, page, server, table_visual_ocr`

## Script → tiff import edges
- `scripts/ask_tiff_rag.py` → `from tiff.local_config import bool_from_config, int_from_config, load_local_config`
- `scripts/ask_tiff_rag.py` → `from tiff.ollama_client import DEFAULT_OLLAMA_URL`
- `scripts/ask_tiff_rag.py` → `from tiff.rag_answer import answer_question, format_source_label`
- `scripts/ask_tiff_rag.py` → `from tiff.rag_ata_answer import build_ata_section_answer, looks_like_ata_query`
- `scripts/audit_document_batch.py` → `from tiff.document_batch_audit import audit_document_batch, format_batch_audit_report, write_batch_audit_json`
- `scripts/audit_document_organization.py` → `from tiff.document_organization_audit import DEFAULT_DB_PATH, audit_document_organization, format_document_organization_audit, write_document_organization_json`
- `scripts/audit_document_organization.py` → `from tiff.local_config import load_local_config`
- `scripts/audit_incremental_readiness.py` → `from tiff.incremental_readiness import audit_incremental_readiness, format_incremental_readiness_report`
- `scripts/audit_ocr_coverage.py` → `from tiff.pipeline_manifest import refresh_manifest_ocr_coverage_summary`
- `scripts/audit_ocr_coverage.py` → `from tiff.ocr_coverage_audit import DEFAULT_DB_PATH, DEFAULT_MIN_CHARS, audit_ocr_coverage, format_ocr_coverage_audit, write_ocr_coverage_json`
- `scripts/audit_ocr_coverage.py` → `from tiff.local_config import load_local_config`
- `scripts/audit_ocr_depth.py` → `from tiff.ocr_depth_audit import OcrDepthThresholds, run_ocr_depth_audit, write_summary_json`
- `scripts/audit_page_image_recognition.py` → `from tiff.page_image_recognition import DEFAULT_CONTEXT_FILE, DEFAULT_EXPORT_DIR, DEFAULT_OUTPUT, print_report, run_page_image_recognition_audit, write_report`
- `scripts/audit_page_visual_objects.py` → `from tiff.page_visual_object_audit import DEFAULT_CONTEXT_FILE, DEFAULT_EXPORT_DIR, DEFAULT_GRAPH_SUMMARY, DEFAULT_OUTPUT, audit_page_visual_objects, write_visual_object_audit`
- `scripts/audit_public_tiff_zip.py` → `from tiff.public_tiff_zip_audit import audit_public_tiff_zip, format_public_tiff_zip_audit, write_audit_json`
- `scripts/audit_real_server_inventory.py` → `from tiff.real_server_inventory import DEFAULT_OUTPUT, InventoryOptions, audit_real_server_inventory, format_inventory_report, write_inventory_json`
- `scripts/audit_source_links.py` → `from tiff.source_link_audit import DEFAULT_DB_PATH, DEFAULT_SAMPLE_PARTS, audit_source_links, format_source_link_audit, write_source_link_audit_json`
- `scripts/audit_source_links.py` → `from tiff.local_config import load_local_config`
- `scripts/audit_source_package_traceability.py` → `from tiff.real_scale_intake import audit_source_zip_traceability, write_json_report`
- `scripts/audit_trace_net_postgres_graph.py` → `from tiff.trace_net_postgres_graph_audit import main`
- `scripts/batch_scan_tiffs_to_json.py` → `from tiff.json_report import scan_tiff_to_dict, write_scan_json`
- `scripts/batch_scan_tiffs_to_json.py` → `from tiff.sqlite_store import connect, upsert_scan_report`
- `scripts/build_graph_org_chart_site.py` → `from tiff.graph_org_chart_site import OrgChartPaths, build_and_write_org_chart_site`
- `scripts/build_part_catalog.py` → `from tiff.part_catalog import build_part_catalog`
- `scripts/build_rag_chunks.py` → `from tiff.rag_chunks import build_rag_chunks`
- `scripts/build_rag_embeddings.py` → `from tiff.ollama_client import DEFAULT_OLLAMA_URL`
- `scripts/build_rag_embeddings.py` → `from tiff.rag_retriever import build_rag_embeddings`
- `scripts/build_rescarta_mapping.py` → `from tiff.source_links import build_source_links, format_build_summary, write_source_link_report`
- `scripts/build_rescarta_mapping.py` → `from tiff.local_config import load_local_config`
- `scripts/build_rescarta_mapping.py` → `from tiff.source_links import format_report_summary`
- `scripts/build_tiff_search_index.py` → `from tiff.search_index import build_search_index`
- `scripts/build_trace_net_ai_trace_pack_v1.py` → `from tiff.trace_net_ai_trace_pack_v1 import main`
- `scripts/build_trace_net_algorithm_policy.py` → `from tiff.trace_net_algorithm_policy import main`
- `scripts/build_trace_net_anchor_aware_graph_leiden_expander_v1.py` → `from tiff.trace_net_anchor_aware_graph_leiden_expander_v1 import main_build`
- `scripts/build_trace_net_answer_claim_critic_v1.py` → `from tiff.trace_net_answer_claim_critic_v1 import main`
- `scripts/build_trace_net_answer_context_anchor_injector_v1.py` → `from tiff.trace_net_answer_context_anchor_injector_v1 import main_build`
- `scripts/build_trace_net_answer_context_engineering_pack_v1.py` → `from tiff.trace_net_answer_context_engineering_pack_v1 import main_build`
- `scripts/build_trace_net_answer_context_evidence_enricher_v1.py` → `from tiff.trace_net_answer_context_evidence_enricher_v1 import main_build`
- `scripts/build_trace_net_answer_context_exact_row_proof_v1.py` → `from tiff.trace_net_answer_context_exact_row_proof_v1 import main_build`
- `scripts/build_trace_net_answer_context_graph_leiden_expander_v1.py` → `from tiff.trace_net_answer_context_graph_leiden_expander_v1 import main_build`
- `scripts/build_trace_net_answer_context_pack_v1.py` → `from tiff.trace_net_answer_context_pack_v1 import main`
- `scripts/build_trace_net_answer_quality_gate_v1.py` → `from tiff.trace_net_answer_quality_gate_v1 import main_build`
- `scripts/build_trace_net_artifact_dependency_registry_v1.py` → `from tiff.trace_net_artifact_dependency_registry_v1 import main`
- `scripts/build_trace_net_artifact_detector_v1.py` → `from tiff.trace_net_artifact_detector_v1 import main`
- `scripts/build_trace_net_artifact_dirty_planner_v1.py` → `from tiff.trace_net_artifact_dirty_planner_v1 import main`
- `scripts/build_trace_net_ask_api_final_return_policy_hybrid_v3_v22.py` → `from tiff.trace_net_ask_api_final_return_policy_hybrid_v3_v22 import main`
- `scripts/build_trace_net_ask_api_final_return_policy_v21.py` → `from tiff.trace_net_ask_api_final_return_policy_v21 import main`
- `scripts/build_trace_net_ask_api_hybrid_v3_routing_v1.py` → `from tiff.trace_net_ask_api_hybrid_v3_routing_v1 import main`
- `scripts/build_trace_net_callout_visual_part_verifier_v1.py` → `from tiff.trace_net_callout_visual_part_verifier_v1 import main`
- `scripts/build_trace_net_category_aware_graph_ui_overlay_v1.py` → `from tiff.trace_net_category_aware_graph_ui_overlay_v1 import main`
- `scripts/build_trace_net_category_aware_leiden_overlay_v1.py` → `from tiff.trace_net_category_aware_leiden_overlay_v1 import main`
- `scripts/build_trace_net_citation_answer_draft_v1.py` → `from tiff.trace_net_citation_answer_draft_v1 import main`
- `scripts/build_trace_net_claim_evidence_entailment_v1.py` → `from tiff.trace_net_claim_evidence_entailment_v1 import main`
- `scripts/build_trace_net_community_aware_retrieval_v2.py` → `from tiff.trace_net_community_aware_retrieval_v2 import main`
- `scripts/build_trace_net_confidence_policy.py` → `from tiff.trace_net_confidence_stage3_policy import main`
- `scripts/build_trace_net_confidence_policy_control.py` → `from tiff.trace_net_confidence_stage5_control import main`
- `scripts/build_trace_net_confidence_stage5_control.py` → `from tiff.trace_net_confidence_stage5_control import main`
- `scripts/build_trace_net_context_retrieval_helpers_v1.py` → `from tiff.trace_net_context_retrieval_helper_v1 import main_build`
- `scripts/build_trace_net_corrective_retrieval_planner_v1.py` → `from tiff.trace_net_corrective_retrieval_planner_v1 import main`
- `scripts/build_trace_net_dry_run_loader_planner_v1.py` → `from tiff.trace_net_dry_run_loader_planner_v1 import main_build`
- `scripts/build_trace_net_dublin_core_crosswalk_refinement_v1.py` → `from tiff.trace_net_dublin_core_crosswalk_refinement_v1 import main`
- `scripts/build_trace_net_dublin_core_crosswalk_v1.py` → `from tiff.trace_net_dublin_core_crosswalk_v1 import main`
- `scripts/build_trace_net_dublin_core_source_package_extension_v1.py` → `from tiff.trace_net_dublin_core_source_package_extension_v1 import main`
- `scripts/build_trace_net_dynamic_final_gate_execution_v1.py` → `from tiff.trace_net_dynamic_final_gate_execution_v1 import main`
- `scripts/build_trace_net_e2e_api_wrapper_smoke_v1.py` → `from tiff.trace_net_e2e_api_wrapper_smoke_v1 import add_common_args, build_and_write, thresholds_from_args`
- `scripts/build_trace_net_e2e_calibrated_cascade_route_brain_v35_3.py` → `from tiff.trace_net_e2e_calibrated_cascade_route_brain_v35_3 import main`
- `scripts/build_trace_net_e2e_cascade_route_feature_audit_v35_2.py` → `from tiff.trace_net_e2e_cascade_route_feature_audit_v35_2 import main`
- `scripts/build_trace_net_e2e_context_pack_builder_v1.py` → `from tiff.trace_net_e2e_context_pack_builder_v1 import main`
- `scripts/build_trace_net_e2e_corrected_visual_context_builder_v35_4.py` → `from tiff.trace_net_e2e_corrected_visual_context_builder_v35_4 import main`
- `scripts/build_trace_net_e2e_crag_retrieval_corrector_v10.py` → `from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import QUALITY_PASS, add_quality_args, build_crag_corrector_report, evaluate_quality, print_quality_result, read_json, write_report_files`
- `scripts/build_trace_net_e2e_dynamic_context_pack_v8.py` → `from tiff.trace_net_e2e_dynamic_context_pack_v8 import QualityThresholds, build_context_pack_report, load_json, write_report_files`
- `scripts/build_trace_net_e2e_dynamic_plan_executor_v18.py` → `from tiff.trace_net_e2e_dynamic_plan_executor_v18 import build_report, quality_check_report, write_report_files`
- `scripts/build_trace_net_e2e_dynamic_query_endpoint_v1.py` → `from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import build_manifest`
- `scripts/build_trace_net_e2e_dynamic_query_tunnels_v3.py` → `from tiff.trace_net_e2e_dynamic_query_tunnels_v3 import DEFAULT_QUERY_PROBES, build_dynamic_query_tunnels_report, print_terminal_report, write_report_files`
- `scripts/build_trace_net_e2e_dynamic_tunnel_ranker_v6.py` → `from tiff.trace_net_e2e_dynamic_tunnel_ranker_v6 import main`
- `scripts/build_trace_net_e2e_evidence_sufficiency_gate_v1.py` → `from tiff.trace_net_e2e_evidence_sufficiency_gate_v1 import main`
- `scripts/build_trace_net_e2e_executed_plan_context_pack_v19.py` → `from tiff.trace_net_e2e_executed_plan_context_pack_v19 import add_common_quality_args, build_and_write, print_report_summary`
- `scripts/build_trace_net_e2e_final_answer_gate_v13.py` → `from tiff.trace_net_e2e_final_answer_gate_v13 import main`
- `scripts/build_trace_net_e2e_final_gate_smoke_v1.py` → `from tiff.trace_net_e2e_final_gate_smoke_v1 import main`
- `scripts/build_trace_net_e2e_hybrid_retrieval_runtime_v1.py` → `from tiff.trace_net_e2e_hybrid_retrieval_runtime_v1 import QualityThresholds, build_from_paths`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34 import build_report`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34 import evaluate_quality, _write_json`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34_1.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34_1 import build_report`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34_1.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34_1 import evaluate_quality, _write_json`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34_2.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34_2 import build_report`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34_2.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34_2 import evaluate_quality, _write_json`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34_3.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34_3 import build_report`
- `scripts/build_trace_net_e2e_image_visual_observer_route_v34_3.py` → `from tiff.trace_net_e2e_image_visual_observer_route_v34_3 import evaluate_quality, _write_json`
- `scripts/build_trace_net_e2e_live_deterministic_answer_planner_v28.py` → `from tiff.trace_net_e2e_live_deterministic_answer_planner_v28 import attach_quality, build_state, evaluate_quality, write_endpoint_files`
- `scripts/build_trace_net_e2e_live_dynamic_fallback_v16.py` → `from tiff.trace_net_e2e_live_dynamic_fallback_v16 import build_live_dynamic_fallback_manifest, read_json, write_report_files`
- `scripts/build_trace_net_e2e_live_eval_latency_harness_v26.py` → `from tiff.trace_net_e2e_live_eval_latency_harness_v26 import build_report, load_eval_queries_from_jsonl, standard_eval_queries`
- `scripts/build_trace_net_e2e_live_gemma_answer_writer_endpoint_v32.py` → `from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v32 import main_build`
- `scripts/build_trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py` → `from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v33 import main_build`
- `scripts/build_trace_net_e2e_live_llm_draft_adapter_v22.py` → `from tiff.trace_net_e2e_live_llm_draft_adapter_v22 import main_build`
- `scripts/build_trace_net_e2e_live_llm_final_gate_v23.py` → `from tiff.trace_net_e2e_live_llm_final_gate_v23 import main_build`
- `scripts/build_trace_net_e2e_live_llm_prompt_contract_v21.py` → `from tiff.trace_net_e2e_live_llm_prompt_contract_v21 import main_build`
- `scripts/build_trace_net_e2e_live_orchestrator_endpoint_v25.py` → `from tiff.trace_net_e2e_live_orchestrator_endpoint_v25 import MODEL_ID, attach_quality, build_orchestrator_state, evaluate_quality, write_endpoint_files`
- `scripts/build_trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py` → `from tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 import attach_quality, build_state, evaluate_quality, write_endpoint_files`
- `scripts/build_trace_net_e2e_live_query_pipeline_v15.py` → `from tiff.trace_net_e2e_live_query_pipeline_v15 import build_live_query_pipeline_manifest, read_json, write_report_files`
- `scripts/build_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py` → `from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import build_report`
- `scripts/build_trace_net_e2e_live_relationship_synthesis_planner_v29.py` → `from tiff.trace_net_e2e_live_relationship_synthesis_planner_v29 import attach_quality, build_state, evaluate_quality, write_endpoint_files`
- `scripts/build_trace_net_e2e_live_self_rag_crag_evaluator_v20.py` → `from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main`
- `scripts/build_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py` → `from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import MODEL_ID, attach_quality, build_endpoint_state, evaluate_quality, write_endpoint_files`
- `scripts/build_trace_net_e2e_llm_assisted_query_planner_v17.py` → `from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_report, load_json, write_report_files`
- `scripts/build_trace_net_e2e_llm_assisted_query_planner_v17.py` → `from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, DEFAULT_STATUS_READY, DEFAULT_STATUS_NEEDS_REPAIR, evaluate_quality`
- `scripts/build_trace_net_e2e_llm_prompt_contract_v11.py` → `from tiff.trace_net_e2e_llm_prompt_contract_v11 import QUALITY_PASS, add_quality_args, build_llm_prompt_contract_report, evaluate_quality, read_json, write_report_files`
- `scripts/build_trace_net_e2e_local_endpoint_v1.py` → `from tiff.trace_net_e2e_local_endpoint_v1 import build_endpoint_manifest`
- `scripts/build_trace_net_e2e_optional_tunnel_activator_v5.py` → `from tiff.trace_net_e2e_optional_tunnel_activator_v5 import build_optional_tunnel_activation_report`
- `scripts/build_trace_net_e2e_query_input_v1.py` → `from tiff.trace_net_e2e_query_input_v1 import QUALITY_PASS, QueryBuildConfig, STANDARD_DEMO_QUERIES, build_report, read_queries_from_file, write_outputs`
- `scripts/build_trace_net_e2e_query_planning_routing_v1.py` → `from tiff.trace_net_e2e_query_planning_routing_v1 import QualityThresholds, build_query_planning_routing`
- `scripts/build_trace_net_e2e_rag_demo_report_v1.py` → `from tiff.trace_net_e2e_rag_demo_report_v1 import build_e2e_rag_demo_report`
- `scripts/build_trace_net_e2e_reasoned_response_draft_v12.py` → `from tiff.trace_net_e2e_reasoned_response_draft_v12 import build_cli`
- `scripts/build_trace_net_e2e_relationship_final_gate_hardener_v30.py` → `from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import build_report`
- `scripts/build_trace_net_e2e_relationship_router_hardening_v29_1.py` → `from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import build_report`
- `scripts/build_trace_net_e2e_route_brain_image_page_audit_v35_1.py` → `from tiff.trace_net_e2e_route_brain_image_page_audit_v35_1 import main`
- `scripts/build_trace_net_e2e_route_scoped_visual_context_builder_v35.py` → `from tiff.trace_net_e2e_route_scoped_visual_context_builder_v35 import main`
- `scripts/build_trace_net_e2e_self_rag_context_critic_v9.py` → `from tiff.trace_net_e2e_self_rag_context_critic_v9 import add_common_args, build_from_args, write_report_files`
- `scripts/build_trace_net_e2e_tool_usage_audit_v1.py` → `from tiff.trace_net_e2e_tool_usage_audit_v1 import main_build`
- `scripts/build_trace_net_e2e_webui_final_answer_endpoint_v14.py` → `from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import build_endpoint_manifest, read_json, write_report_files`
- `scripts/build_trace_net_element_category_taxonomy_v1.py` → `from tiff.trace_net_element_category_taxonomy_v1 import main`
- `scripts/build_trace_net_element_graph_attachment_plan_v1.py` → `from tiff.trace_net_element_graph_attachment_plan_v1 import main`
- `scripts/build_trace_net_embedding_candidates_v1.py` → `from tiff.trace_net_embedding_candidates_v1 import main_build`
- `scripts/build_trace_net_engineering_answer_composer_v1.py` → `from tiff.trace_net_engineering_answer_composer_v1 import main`
- `scripts/build_trace_net_engineering_answer_context_pack_v1.py` → `from tiff.trace_net_engineering_answer_context_pack_v1 import main`
- `scripts/build_trace_net_engineering_answer_runner_v1.py` → `from tiff.trace_net_engineering_answer_runner_v1 import main`
- `scripts/build_trace_net_engineering_context_crag_retry_plan_v1.py` → `from tiff.trace_net_engineering_context_crag_retry_plan_v1 import main_build`
- `scripts/build_trace_net_engineering_context_draft_packet_v1.py` → `from tiff.trace_net_engineering_context_draft_packet_v1 import main_build`
- `scripts/build_trace_net_engineering_context_pack_blueprint_v1.py` → `from tiff.trace_net_engineering_context_pack_blueprint_v1 import main_build`
- `scripts/build_trace_net_engineering_context_pack_builder_v1.py` → `from tiff.trace_net_engineering_context_pack_builder_v1 import main_build`
- `scripts/build_trace_net_engineering_context_self_rag_check_v1.py` → `from tiff.trace_net_engineering_context_self_rag_check_v1 import main_build`
- `scripts/build_trace_net_engineering_draft_final_gate_v1.py` → `from tiff.trace_net_engineering_draft_final_gate_v1 import main_build`
- `scripts/build_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py` → `from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import main`
- `scripts/build_trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py` → `from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import main`
- `scripts/build_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py` → `from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import main`
- `scripts/build_trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.py` → `from tiff.trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1 import main`
- `scripts/build_trace_net_engineering_engram_core_v1.py` → `from tiff.trace_net_engineering_engram_core_v1 import main_build`
- `scripts/build_trace_net_engineering_engram_crag_repair_v1.py` → `from tiff.trace_net_engineering_engram_crag_repair_v1 import main`
- `scripts/build_trace_net_engineering_engram_memory_layers_v1.py` → `from tiff.trace_net_engineering_engram_memory_layers_v1 import build_memory_layer_manifest`
- `scripts/build_trace_net_engineering_engram_postgres_feedback_ledger_v1.py` → `from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import main`
- `scripts/build_trace_net_engineering_engram_prompt_retrieval_injector_v1.py` → `from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_retrieval_injector_manifest`
- `scripts/build_trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py` → `from tiff.trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1 import main`
- `scripts/build_trace_net_engineering_engram_prompt_retrieval_smoke_v1.py` → `from tiff.trace_net_engineering_engram_prompt_retrieval_smoke_v1 import build_prompt_retrieval_smoke_manifest`
- `scripts/build_trace_net_engineering_engram_qdrant_adapter_v1.py` → `from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import main`
- `scripts/build_trace_net_engineering_engram_self_rag_critic_v1.py` → `from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main`
- `scripts/build_trace_net_engineering_engram_unified_runtime_gate_v1.py` → `from tiff.trace_net_engineering_engram_unified_runtime_gate_v1 import main`
- `scripts/build_trace_net_engineering_engram_vector_loader_v1.py` → `from tiff.trace_net_engineering_engram_vector_loader_v1 import build_vector_loader_manifest`
- `scripts/build_trace_net_engineering_engram_vector_retriever_v1.py` → `from tiff.trace_net_engineering_engram_vector_retriever_v1 import build_vector_retriever_manifest`
- `scripts/build_trace_net_engineering_gemma_draft_adapter_v1.py` → `from tiff.trace_net_engineering_gemma_draft_adapter_v1 import main_build`
- `scripts/build_trace_net_engineering_gemma_draft_retry_prompt_v1.py` → `from tiff.trace_net_engineering_gemma_draft_retry_prompt_v1 import main_build`
- `scripts/build_trace_net_engineering_gemma_draft_runner_v1.py` → `from tiff.trace_net_engineering_gemma_draft_runner_v1 import main_build`
- `scripts/build_trace_net_engineering_intent_answer_composer_v1.py` → `from tiff.trace_net_engineering_intent_answer_composer_v1 import main`
- `scripts/build_trace_net_engineering_llm_answer_smoke_v1.py` → `from tiff.trace_net_engineering_llm_answer_smoke_v1 import main`
- `scripts/build_trace_net_engineering_query_planner_v1.py` → `from tiff.trace_net_engineering_query_planner_v1 import main`
- `scripts/build_trace_net_engineering_real_answer_smoke_review_v1.py` → `from tiff.trace_net_engineering_real_answer_smoke_review_v1 import main`
- `scripts/build_trace_net_engineering_real_answer_smoke_test_v1.py` → `from tiff.trace_net_engineering_real_answer_smoke_test_v1 import main`
- `scripts/build_trace_net_engineering_reasoning_kernel_v1.py` → `from tiff.trace_net_engineering_reasoning_kernel_v1 import main_build`
- `scripts/build_trace_net_engineering_runner_eval_set_v1.py` → `from tiff.trace_net_engineering_runner_eval_set_v1 import main`
- `scripts/build_trace_net_engineering_runner_expanded_eval_set_v1.py` → `from tiff.trace_net_engineering_runner_expanded_eval_set_v1 import main`
- `scripts/build_trace_net_engineering_semantic_answer_quality_eval_v1.py` → `from tiff.trace_net_engineering_semantic_answer_quality_eval_v1 import main_build`
- `scripts/build_trace_net_engineering_webui_answer_server_v1.py` → `from tiff.trace_net_engineering_webui_answer_server_v1 import main_build`
- `scripts/build_trace_net_engineering_webui_answer_server_v1_3.py` → `from tiff.trace_net_engineering_webui_answer_server_v1_3 import main_build`
- `scripts/build_trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py` → `from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import main_build`
- `scripts/build_trace_net_evidence_consensus.py` → `from tiff.trace_net_evidence_consensus import main`
- `scripts/build_trace_net_evidence_snippet_claims_v1.py` → `from tiff.trace_net_evidence_snippet_claims_v1 import main`
- `scripts/build_trace_net_evidence_snippet_cleaner_v1.py` → `from tiff.trace_net_evidence_snippet_cleaner_v1 import main`
- `scripts/build_trace_net_evidence_sufficiency_critic_v1.py` → `from tiff.trace_net_evidence_sufficiency_critic_v1 import main`
- `scripts/build_trace_net_fast_answer_composer_v1.py` → `from tiff.trace_net_fast_answer_composer_v1 import main_build`
- `scripts/build_trace_net_fast_chat_multi_route_quality_gate_v1.py` → `from tiff.trace_net_fast_chat_multi_route_quality_gate_v1 import main_build`
- `scripts/build_trace_net_feedback_graph.py` → `from tiff.trace_net_feedback import FeedbackPaths, TRACE_NET_DIR, build_feedback_graph`
- `scripts/build_trace_net_feedback_memory_v1.py` → `from tiff.trace_net_feedback_memory_v1 import build_main`
- `scripts/build_trace_net_figure_chart_understanding_v1.py` → `from tiff.trace_net_figure_chart_understanding_v1 import main`
- `scripts/build_trace_net_figure_item_fast_answer_composer_v1.py` → `from tiff.trace_net_figure_item_fast_answer_composer_v1 import main_build`
- `scripts/build_trace_net_final_answer_gate_v1.py` → `from tiff.trace_net_final_answer_gate_v1 import main`
- `scripts/build_trace_net_fishnet_accepted_route_manifest_v1.py` → `from tiff.trace_net_fishnet_accepted_route_manifest_v1 import main_build`
- `scripts/build_trace_net_fishnet_ocr_grid_v1.py` → `from tiff.trace_net_fishnet_ocr_grid_v1 import main_build`
- `scripts/build_trace_net_fishnet_retry_engine_v1.py` → `from tiff.trace_net_fishnet_retry_engine_v1 import main`
- `scripts/build_trace_net_fishnet_retry_refinement_v1.py` → `from tiff.trace_net_fishnet_retry_refinement_v1 import main`
- `scripts/build_trace_net_fishnet_router_hardening_policy_v1.py` → `from tiff.trace_net_fishnet_router_hardening_policy_v1 import main_build`
- `scripts/build_trace_net_fishnet_route_dispatch_handoff_v1.py` → `from tiff.trace_net_fishnet_route_dispatch_handoff_v1 import main_build`
- `scripts/build_trace_net_fishnet_route_manifest_overlay_v1.py` → `from tiff.trace_net_fishnet_route_manifest_overlay_v1 import main_build`
- `scripts/build_trace_net_fishnet_route_review_packet_v1.py` → `from tiff.trace_net_fishnet_route_review_packet_v1 import main_build`
- `scripts/build_trace_net_fishnet_route_signal_workbench_v1.py` → `from tiff.trace_net_fishnet_route_signal_workbench_v1 import main_build`
- `scripts/build_trace_net_four_route_operational_resolver_v1.py` → `from tiff.trace_net_four_route_operational_resolver_v1 import main_build`
- `scripts/build_trace_net_four_route_storage_gate_v1.py` → `from tiff.trace_net_four_route_storage_gate_v1 import main_build`
- `scripts/build_trace_net_gold_label_auto_review_seed_v1.py` → `from tiff.trace_net_gold_label_auto_review_seed_v1 import main_build`
- `scripts/build_trace_net_gold_label_decision_merge_v1.py` → `from tiff.trace_net_gold_label_decision_merge_v1 import main_build`
- `scripts/build_trace_net_gold_label_review_reduction_v1.py` → `from tiff.trace_net_gold_label_review_reduction_v1 import main_build`
- `scripts/build_trace_net_gold_label_review_workbook_v1.py` → `from tiff.trace_net_gold_label_review_workbook_v1 import main_build`
- `scripts/build_trace_net_graph_explorer.py` → `from tiff.trace_net_graph_explorer import main`
- `scripts/build_trace_net_graph_explorer_v2_nomenclature_fix.py` → `from tiff import trace_net_graph_explorer`
- `scripts/build_trace_net_graph_overlay_part_lineage_v1.py` → `from tiff.trace_net_graph_overlay_part_lineage_v1 import main`
- `scripts/build_trace_net_graph_overlay_part_property_normalizer_v1.py` → `from tiff.trace_net_graph_overlay_part_property_normalizer_v1 import main`
- `scripts/build_trace_net_graph_query_evidence_enrichment_v1.py` → `from tiff.trace_net_graph_query_evidence_enrichment_v1 import main`
- `scripts/build_trace_net_graph_query_helper_v1.py` → `from tiff.trace_net_graph_query_helper_v1 import main`
- `scripts/build_trace_net_graph_ui_community_overlay_v1.py` → `from tiff.trace_net_graph_ui_community_overlay_v1 import main`
- `scripts/build_trace_net_graph_writeback_overlay_v1.py` → `from tiff.trace_net_graph_writeback_overlay_v1 import main`
- `scripts/build_trace_net_h36_complex_task_validator_v1.py` → `from tiff.trace_net_h36_complex_task_validator_v1 import build_complex_task_validator`
- `scripts/build_trace_net_h37_diversity_evidence_planner_v1.py` → `from tiff.trace_net_h37_diversity_evidence_planner_v1 import main`
- `scripts/build_trace_net_h39a_whole_page_vision_summary_llama_chat_v1.py` → `from tiff import trace_net_h39a_whole_page_vision_summary_v1`
- `scripts/build_trace_net_h39a_whole_page_vision_summary_v1.py` → `from tiff.trace_net_h39a_whole_page_vision_summary_v1 import main`

## Test → tiff import edges
- `tests/unit/test_tiff_api_adapter_quality.py` → `from tiff.api_adapter_quality import build_api_adapter_quality_report, write_api_adapter_quality_report`
- `tests/unit/test_tiff_api_adapter_quality_compat.py` → `from tiff.api_adapter_quality import build_api_adapter_quality_report`
- `tests/unit/test_tiff_api_adapter_refactor.py` → `from tiff.api_adapter_backend import page_lookup_from_store, part_lookup_from_store, status_from_store, submit_feedback_from_store, trace_vector_payload_from_store`
- `tests/unit/test_tiff_api_adapter_services.py` → `from tiff.api_adapter_services import TiffApiServices`
- `tests/unit/test_tiff_api_adapter_services.py` → `from tiff.storage_adapters import StoreBundle`
- `tests/unit/test_tiff_api_backend.py` → `from tiff.api_backend import ApiPaths, api_status, page_lookup, part_lookup, submit_feedback, summarize_feedback`
- `tests/unit/test_tiff_api_contract_quality.py` → `from tiff.api_contract_quality import evaluate_api_contract_quality, write_api_contract_quality`
- `tests/unit/test_tiff_api_contract_tests.py` → `from tiff.api_contract_tests import DEFAULT_OUTPUT, default_contract_cases, run_api_contract_tests, write_contract_report`
- `tests/unit/test_tiff_changed_page_backend_update.py` → `from tiff.changed_page_backend import delete_page_scoped_backend_rows, read_changed_tiffs, run_changed_page_backend_update, tiff_paths_match, update_search_index_for_changed_pages`
- `tests/unit/test_tiff_changed_page_backend_update.py` → `from tiff.search_index import build_search_index`
- `tests/unit/test_tiff_changed_page_update.py` → `from tiff.changed_page_update import paths_might_refer_to_same_page, resolve_affected_pages, run_changed_page_backend_update`
- `tests/unit/test_tiff_changed_page_update.py` → `from tiff.search_index import build_search_index`
- `tests/unit/test_tiff_current_graph_org_chart_site.py` → `from tiff.graph_org_chart_site import OrgChartPaths, build_and_write_org_chart_site`
- `tests/unit/test_tiff_current_graph_setup_report.py` → `from tiff.graph_setup_report import build_current_graph_setup_report, format_current_graph_setup_report`
- `tests/unit/test_tiff_current_graph_visualization.py` → `from tiff.graph_visualization import export_graph_visualizations, format_graph_visualization_result`
- `tests/unit/test_tiff_document_batch_audit.py` → `from tiff.document_batch_audit import audit_document_batch, format_batch_audit_report, write_batch_audit_json`
- `tests/unit/test_tiff_document_classifier.py` → `from tiff.document_classifier import classify_document, classify_document_type`
- `tests/unit/test_tiff_document_classifier.py` → `from tiff.manual_metadata_parser import parse_manual_page_text`
- `tests/unit/test_tiff_document_classifier.py` → `from tiff.metadata_parser import parse_title_block_text`
- `tests/unit/test_tiff_document_graph_quality.py` → `from tiff.document_graph_quality import build_graph_quality_result`
- `tests/unit/test_tiff_document_graph_traceability.py` → `from tiff.document_graph_traceability import build_traceability_report, trace_part_to_sources, trace_page_context, trace_vector_candidate_to_graph, trace_ata_to_sources`
- `tests/unit/test_tiff_document_graph_traceability.py` → `from tiff.document_graph_traversal import GraphStore`
- `tests/unit/test_tiff_document_graph_traversal.py` → `from tiff.document_graph_traversal import build_traversal_report, context_score, render_report`
- `tests/unit/test_tiff_document_organization_audit.py` → `from tiff.document_organization_audit import audit_document_organization, format_document_organization_audit, write_document_organization_json`
- `tests/unit/test_tiff_document_organization_export.py` → `from tiff.document_organization_export import build_document_organization_export, format_document_organization_export, write_document_organization_export`
- `tests/unit/test_tiff_document_organization_graph.py` → `from tiff.document_organization_graph import build_graph_from_export, export_graph`
- `tests/unit/test_tiff_document_organization_inspector.py` → `from tiff.document_organization_inspector import inspect_export, write_inspection_json`
- `tests/unit/test_tiff_document_organization_pipeline_quality.py` → `from tiff.pipeline_manifest import format_manifest_summary, summarize_document_organization_audit_json, summarize_document_organization_export_json`
- `tests/unit/test_tiff_document_organization_pipeline_quality.py` → `from tiff.pipeline_quality import check_pipeline_manifest`
- `tests/unit/test_tiff_document_organization_pipeline_quality.py` → `from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps`
- `tests/unit/test_tiff_document_organization_query.py` → `from tiff.document_organization_query import collect_ata_entries, format_ata, format_page, load_export, query_ata, query_page, query_part, summarize_export`
- `tests/unit/test_tiff_entity_trait_graph.py` → `from tiff.entity_trait_graph import build_entity_trait_overlay, export_entity_trait_overlay`
- `tests/unit/test_tiff_entity_trait_graph_quality.py` → `from tiff.entity_trait_graph import export_entity_trait_overlay`
- `tests/unit/test_tiff_entity_trait_graph_quality.py` → `from tiff.entity_trait_graph_quality import build_entity_trait_quality_result`
- `tests/unit/test_tiff_feedback_session.py` → `from tiff.feedback_session import AnswerRun, audit_source_zip, make_feedback_entry, normalize_rating, save_feedback, summarize_feedback`
- `tests/unit/test_tiff_graph_org_chart_browser_syntax.py` → `from tiff.graph_org_chart_site import write_org_chart_site`
- `tests/unit/test_tiff_graph_org_chart_site.py` → `from tiff.graph_org_chart_site import OrgChartPaths, build_org_chart_data, write_org_chart_site`
- `tests/unit/test_tiff_graph_setup_report.py` → `from tiff.graph_setup_report import build_current_graph_setup_report, format_current_graph_setup_report, write_graph_setup_report_json`
- `tests/unit/test_tiff_graph_visualization.py` → `from tiff.graph_visualization import export_graph_visualizations, format_graph_visualization_result`
- `tests/unit/test_tiff_incremental_changed_page_backend.py` → `from tiff.incremental_pipeline import ChangeDetectionSummary, IncrementalPipelineConfig, build_commands`
- `tests/unit/test_tiff_incremental_changed_page_backend_mode.py` → `from tiff.incremental_pipeline import IncrementalPipelineConfig, build_commands`
- `tests/unit/test_tiff_incremental_changed_page_backend_mode.py` → `from tiff.incremental_state import ChangeDetectionSummary`
- `tests/unit/test_tiff_incremental_changed_page_smoke.py` → `from tiff.incremental_changed_page_smoke import ChangedPageSmokeReport, format_changed_page_smoke_report, select_smoke_source_page`
- `tests/unit/test_tiff_incremental_changed_page_smoke.py` → `from tiff.incremental_pipeline import IncrementalPipelineConfig`
- `tests/unit/test_tiff_incremental_changed_page_smoke.py` → `from tiff.incremental_changed_page_smoke import build_smoke_pipeline_config, SmokePreparedChange, SmokeSourcePage`
- `tests/unit/test_tiff_incremental_compatibility_api.py` → `from tiff.incremental_state import build_changed_tiff_list, read_changed_list`
- `tests/unit/test_tiff_incremental_compatibility_api.py` → `from tiff.incremental_pipeline import IncrementalPipelineConfig, build_incremental_commands, format_command`
- `tests/unit/test_tiff_incremental_pipeline.py` → `from tiff.incremental_pipeline import IncrementalPipelineConfig, build_incremental_commands, config_from_file, format_command, merge_config`
- `tests/unit/test_tiff_incremental_pipeline.py` → `from tiff.incremental_pipeline import run_changed_detection`
- `tests/unit/test_tiff_incremental_pipeline.py` → `from tiff.incremental_state import read_changed_list`
- `tests/unit/test_tiff_incremental_pipeline_safe_commit.py` → `from tiff.incremental_pipeline import IncrementalPipelineConfig, PipelineCommand, PipelineCommandResult, build_commands, load_pipeline_config, should_commit_state`
- `tests/unit/test_tiff_incremental_pipeline_safe_commit.py` → `from tiff.incremental_state import ChangeDetectionSummary`
- `tests/unit/test_tiff_incremental_preview_db_cleanup.py` → `from tiff.incremental_state import build_changed_tiff_list, read_changed_list`
- `tests/unit/test_tiff_incremental_readiness.py` → `from tiff.incremental_readiness import audit_incremental_readiness, format_incremental_readiness_report, preview_incremental_changes`
- `tests/unit/test_tiff_incremental_readiness.py` → `from tiff.incremental_state import IncrementalStateDB`
- `tests/unit/test_tiff_incremental_safe_commit.py` → `from tiff.incremental_state import IncrementalStateDB, write_changed_list, read_changed_list`
- `tests/unit/test_tiff_incremental_state.py` → `from tiff.incremental_state import build_changed_tiff_list, read_changed_list`
- `tests/unit/test_tiff_incremental_status_quality.py` → `from tiff.pipeline_manifest import refresh_manifest_incremental_summary, format_manifest_summary, summarize_incremental_smoke_json`
- `tests/unit/test_tiff_incremental_status_quality.py` → `from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest`
- `tests/unit/test_tiff_inventory.py` → `from tiff.inventory import build_tiff_inventory_record, inventory_directory`
- `tests/unit/test_tiff_json_report.py` → `from tiff.json_report import scan_tiff_to_dict, scan_tiff_to_json_file`
- `tests/unit/test_tiff_local_config.py` → `from tiff.local_config import bool_from_config, load_local_config, parse_simple_config_text`
- `tests/unit/test_tiff_manual_grouping.py` → `from tiff.manual_grouping import build_single_manual_group, is_page_specific_code, normalize_publication_number`
- `tests/unit/test_tiff_manual_metadata_parser.py` → `from tiff.manual_metadata_parser import parse_manual_page_text`
- `tests/unit/test_tiff_manual_page_types.py` → `from tiff.document_classifier import classify_document`
- `tests/unit/test_tiff_manual_page_types.py` → `from tiff.manual_metadata_parser import parse_manual_page_text`
- `tests/unit/test_tiff_metadata_parser.py` → `from tiff.metadata_parser import parse_title_block_text`
- `tests/unit/test_tiff_ocr_cleanup.py` → `from tiff.ocr_cleanup import clean_ocr_text, clean_part_nomenclature, rebuild_clean_part_catalog_pipeline, run_ocr_cleanup`
- `tests/unit/test_tiff_ocr_cleanup.py` → `from tiff.rag_retriever import retrieve_rag_context`
- `tests/unit/test_tiff_ocr_coverage_audit.py` → `from tiff.ocr_coverage_audit import audit_ocr_coverage, format_ocr_coverage_audit, write_ocr_coverage_json`
- `tests/unit/test_tiff_ocr_depth_audit.py` → `from tiff.ocr_depth_audit import OcrDepthThresholds, classify_ocr_text, run_ocr_depth_audit, source_records_from_page_index`
- `tests/unit/test_tiff_ocr_pilot.py` → `from tiff.ocr_pilot import run_ocr_pilot, source_pages_from_zip, source_pages_from_export`
- `tests/unit/test_tiff_ocr_pilot_progress.py` → `from tiff.ocr_pilot_progress import _format_duration`
- `tests/unit/test_tiff_ocr_pipeline_integration.py` → `from tiff.pipeline_manifest import summarize_ocr_coverage_audit_json, format_manifest_summary`
- `tests/unit/test_tiff_ocr_pipeline_integration.py` → `from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest`
- `tests/unit/test_tiff_ocr_pipeline_integration.py` → `from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps`
- `tests/unit/test_tiff_page_context_graph.py` → `from tiff.document_organization_graph import build_graph_from_export`
- `tests/unit/test_tiff_page_context_graph.py` → `from tiff.page_context import create_page_context, generate_page_contexts`
- `tests/unit/test_tiff_page_context_graph.py` → `from tiff.page_context import parse_context_response`
- `tests/unit/test_tiff_page_context_graph.py` → `from tiff.page_context import normalize_ollama_host`
- `tests/unit/test_tiff_page_context_graph.py` → `from tiff.page_context import approx_token_count, context_quality_score`
- `tests/unit/test_tiff_page_context_graph.py` → `from tiff.page_context import create_page_context`
- `tests/unit/test_tiff_page_context_inspector.py` → `from tiff.page_context_inspector import inspect_page_contexts, load_context_rows`
- `tests/unit/test_tiff_page_context_progress.py` → `from tiff.page_context import generate_page_contexts`
- `tests/unit/test_tiff_page_context_progress.py` → `from tiff.page_context_inspector import inspect_page_contexts`
- `tests/unit/test_tiff_page_context_v2.py` → `from tiff.page_context_v2 import build_fallback_card, enforce_card_schema, make_prompt, normalize_contexts, AUTHORITY`
- `tests/unit/test_tiff_page_context_v2_quality.py` → `from tiff.page_context_v2_quality import run_quality`
- `tests/unit/test_tiff_page_image_quality_parser_current_shape.py` → `from tiff.page_image_recognition_quality import build_page_image_recognition_quality`
- `tests/unit/test_tiff_page_image_recognition.py` → `from tiff.page_image_recognition import analyze_page_image, build_image_recognition_graph_overlay, load_page_image_sources, run_page_image_recognition_audit, PageImageSource`
- `tests/unit/test_tiff_page_image_recognition_quality.py` → `from tiff.page_image_recognition_quality import build_page_image_recognition_quality_report, summarize_page_image_recognition_audit`
- `tests/unit/test_tiff_page_image_role_fix.py` → `from tiff.page_image_recognition import load_page_image_sources, run_page_image_recognition_audit`
- `tests/unit/test_tiff_page_visual_object_audit.py` → `from tiff.page_visual_object_audit import audit_page_visual_objects, load_page_contexts, load_page_records`
- `tests/unit/test_tiff_page_visual_object_graph_linkage.py` → `from tiff.page_visual_object_audit import _load_graph_counts`
- `tests/unit/test_tiff_page_visual_object_quality.py` → `from tiff.page_visual_object_quality import build_page_visual_object_quality, summarize_page_visual_object_audit`
- `tests/unit/test_tiff_part_catalog.py` → `from tiff.part_catalog import build_part_catalog, clean_nomenclature, best_nomenclature_from_lines, query_part_catalog`
- `tests/unit/test_tiff_part_catalog.py` → `from tiff.search_index import build_search_index, search_db`
- `tests/unit/test_tiff_part_catalog.py` → `from tiff.search_web_ui import SearchRequest, render_page`
- `tests/unit/test_tiff_part_filters.py` → `from tiff.part_filters import is_bad_nomenclature, is_probable_real_part_number, canonicalize_nomenclature_for_comparison`
- `tests/unit/test_tiff_part_filters_v2.py` → `from tiff.part_filters import canonicalize_nomenclature_for_comparison, is_bad_nomenclature, is_probable_real_part_number`
- `tests/unit/test_tiff_part_qa.py` → `from tiff.part_qa import report_nomenclature_groups, report_part_nomenclature_conflicts, report_parts_missing_nomenclature, report_suspicious_part_ata`
- `tests/unit/test_tiff_part_qa_filtering.py` → `from tiff.part_qa import report_nomenclature_groups, report_part_nomenclature_conflicts, report_parts_missing_nomenclature`
- `tests/unit/test_tiff_part_qa_noise_suppression.py` → `from tiff.part_qa import report_nomenclature_groups, report_parts_missing_nomenclature`
- `tests/unit/test_tiff_part_qa_severity.py` → `from tiff.part_qa_severity import looks_like_ata_reference, looks_like_compound_part_reference, looks_like_plausible_part, summarize_triage, terminal_row_summary, triage_row, triage_rows`
- `tests/unit/test_tiff_part_qa_severity.py` → `from tiff.part_qa_severity import write_triage_outputs`
- `tests/unit/test_tiff_pipeline_manifest.py` → `from tiff.pipeline_manifest import build_pipeline_manifest, format_manifest_summary, summarize_eval_json, summarize_qa_json, write_pipeline_manifest`
- `tests/unit/test_tiff_pipeline_manifest.py` → `from tiff.pipeline_runner import PipelineConfig, PipelineRunResult, PipelineStep`
- `tests/unit/test_tiff_pipeline_qa_integration.py` → `from tiff.pipeline_manifest import summarize_qa_json`
- `tests/unit/test_tiff_pipeline_qa_integration.py` → `from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps`
- `tests/unit/test_tiff_pipeline_quality.py` → `from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest, check_pipeline_manifest_file, write_quality_gate_html, write_quality_gate_json`
- `tests/unit/test_tiff_pipeline_runner.py` → `from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps, config_from_file, format_command, read_simple_yaml, run_pipeline`
- `tests/unit/test_tiff_production_adapter_stubs.py` → `from tiff.production_adapters import OpenSearchKeywordSearchStore, PostgresCatalogStore, ProductionAdapterConfig, ProductionAdapterNotConfigured, QdrantVectorStore, ResCartaSourceStore, build_production_adapter_readiness, schema_artifact_paths, schema_artifacts_present, write_production_adapter_readiness`
- `tests/unit/test_tiff_production_schema.py` → `from tiff.production_schema import OPENSEARCH_INDICES, POSTGRES_TABLES, QDRANT_COLLECTIONS, opensearch_mappings, postgres_schema_sql, qdrant_collections, validate_schema_drafts, write_schema_drafts`
- `tests/unit/test_tiff_public_tiff_zip_audit.py` → `from tiff.public_tiff_zip_audit import audit_public_tiff_zip, format_public_tiff_zip_audit`
- `tests/unit/test_tiff_rag_answer.py` → `from tiff.rag_answer import answer_question, build_rag_prompt, extractive_answer`
- `tests/unit/test_tiff_rag_answer.py` → `from tiff.rag_chunks import build_rag_chunks`
- `tests/unit/test_tiff_rag_answer.py` → `from tiff.rag_retriever import retrieve_rag_context`
- `tests/unit/test_tiff_rag_ata_answer.py` → `from tiff.rag_ata_answer import build_ata_section_answer, extract_ata_code, looks_like_ata_query`
- `tests/unit/test_tiff_rag_chunks.py` → `from tiff.rag_chunks import build_rag_chunks, chunk_text_by_lines`
- `tests/unit/test_tiff_rag_embedding_schema_migration.py` → `from tiff.rag_chunks import create_rag_schema, table_exists`
- `tests/unit/test_tiff_rag_eval.py` → `from tiff.rag_eval import EvalQuestion, judge_answer, load_eval_questions, summarize_eval_records`
- `tests/unit/test_tiff_rag_eval.py` → `from tiff.rag_answer import RagAnswer`
- `tests/unit/test_tiff_rag_eval.py` → `from tiff.rag_retriever import RagSource`
- `tests/unit/test_tiff_rag_eval.py` → `from tiff.rag_eval import EvalRecord`
- `tests/unit/test_tiff_rag_eval_expanded.py` → `from tiff.rag_eval import load_eval_questions, question_from_dict`
- `tests/unit/test_tiff_rag_eval_expanded.py` → `from tiff.rag_eval_questions import EXPANDED_RAG_EVAL_QUESTIONS, summarize_question_set, write_expanded_rag_eval_questions`
- `tests/unit/test_tiff_rag_eval_manifest_refresh.py` → `from tiff.pipeline_manifest import refresh_manifest_eval_summary, summarize_eval_json`
- `tests/unit/test_tiff_rag_eval_manifest_refresh.py` → `from tiff.pipeline_runner import PipelineConfig, build_pipeline_steps`
- `tests/unit/test_tiff_rag_exact_lookup_no_hybrid_noise.py` → `from tiff.rag_retriever import retrieve_rag_context`
- `tests/unit/test_tiff_rag_hybrid_retrieval.py` → `from tiff.rag_answer import answer_question`
- `tests/unit/test_tiff_rag_hybrid_retrieval.py` → `from tiff.rag_retriever import classify_query_intent, nomenclature_match_score, retrieve_rag_context`
- `tests/unit/test_tiff_rag_hybrid_routing.py` → `from tiff.rag_chunks import build_rag_chunks`
- `tests/unit/test_tiff_rag_hybrid_routing.py` → `from tiff.rag_retriever import RagSource, retrieve_rag_context`
- `tests/unit/test_tiff_rag_hybrid_routing.py` → `from tiff.rag_router import classify_query`
- `tests/unit/test_tiff_rag_incremental_embedding_reuse.py` → `from tiff.rag_chunks import build_rag_chunks`
- `tests/unit/test_tiff_rag_incremental_embedding_reuse.py` → `from tiff.rag_retriever import build_rag_embeddings`
- `tests/unit/test_tiff_rag_model_eval.py` → `from tiff.rag_model_eval import ModelEvalQuestion, default_model_eval_questions, evaluate_text, parse_ask_tiff_rag_output, summarize_results, write_questions, load_questions, ModelEvalResult`
- `tests/unit/test_tiff_rag_nomenclature_reverse_lookup.py` → `from tiff.rag_answer import answer_question, build_structured_nomenclature_answer`
- `tests/unit/test_tiff_rag_nomenclature_reverse_lookup.py` → `from tiff.rag_retriever import retrieve_rag_context`
- `tests/unit/test_tiff_rag_retriever.py` → `from tiff.rag_chunks import build_rag_chunks`
- `tests/unit/test_tiff_rag_retriever.py` → `from tiff.rag_retriever import cosine_similarity, deserialize_embedding, retrieve_rag_context, serialize_embedding`
- `tests/unit/test_tiff_rag_reverse_lookup_balanced_sources.py` → `from tiff.rag_answer import answer_question`
- `tests/unit/test_tiff_rag_reverse_lookup_balanced_sources.py` → `from tiff.rag_retriever import retrieve_rag_context`
- `tests/unit/test_tiff_rag_source_grouping.py` → `from tiff.rag_answer import answer_question, build_structured_part_answer`
- `tests/unit/test_tiff_rag_source_grouping.py` → `from tiff.rag_retriever import retrieve_rag_context`
- `tests/unit/test_tiff_rag_source_link_integration.py` → `from tiff.rag_retriever import RagSource, enrich_sources_with_source_links, source_to_dict`
- `tests/unit/test_tiff_rag_source_link_integration.py` → `from tiff.rag_answer import make_context_block`
- `tests/unit/test_tiff_rag_source_link_integration.py` → `from tiff.pipeline_manifest import collect_sqlite_counts`
- `tests/unit/test_tiff_rag_source_link_integration.py` → `from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest`
- `tests/unit/test_tiff_rag_source_packing.py` → `from tiff.rag_answer import build_rag_prompt, pack_sources_for_llm`
- `tests/unit/test_tiff_rag_source_packing.py` → `from tiff.rag_retriever import RagSource`
- `tests/unit/test_tiff_rag_structured_part_summary.py` → `from tiff.rag_answer import build_structured_part_summary_answer`
- `tests/unit/test_tiff_rag_structured_part_summary.py` → `from tiff.rag_retriever import RagSource, RetrievalResult`
- `tests/unit/test_tiff_realistic_query_trace_quality.py` → `from tiff.document_graph_quality import GraphQualityThresholds, build_graph_quality_result`
- `tests/unit/test_tiff_realistic_query_trace_quality.py` → `from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest`
- `tests/unit/test_tiff_realistic_query_trace_quality_gate.py` → `from tiff.document_graph_quality import GraphQualityThresholds, build_graph_quality_result`
- `tests/unit/test_tiff_realistic_query_trace_tests.py` → `from tiff.realistic_query_trace_tests import CommandCheck, CommandCheckResult, RealisticTraceResult, default_realistic_trace_cases, select_cases, summarize_realistic_trace_results`
- `tests/unit/test_tiff_real_scale_intake.py` → `from tiff.real_scale_intake import audit_source_zip, audit_source_zip_traceability, build_intake_plan_report, extract_page_number_from_name`
- `tests/unit/test_tiff_real_server_inventory.py` → `from tiff.real_server_inventory import InventoryOptions, audit_real_server_inventory, format_inventory_report`
- `tests/unit/test_tiff_rescarta_deeplink.py` → `from tiff.rescarta_deeplink import DEFAULT_TEMPLATE, ResCartaTemplateError, SourceLinkRow, build_tokens, is_placeholder_url, preview_links, render_url, update_source_link_urls, validate_template`
- `tests/unit/test_tiff_search_index.py` → `from tiff.search_index import build_search_index, extract_part_mentions, normalize_part_number, search_db`
- `tests/unit/test_tiff_search_results_html.py` → `from tiff.search_index import SearchResult`
- `tests/unit/test_tiff_search_results_html.py` → `from tiff.search_results_html import path_to_file_uri, render_search_results_html, write_search_results_html`
- `tests/unit/test_tiff_search_web_ui.py` → `from tiff.search_index import SearchResult`
- `tests/unit/test_tiff_search_web_ui.py` → `from tiff.search_web_ui import SearchRequest, clamp_limit, csv_text_for_results, parse_search_request, render_page, resolve_source_path`
- `tests/unit/test_tiff_server_access_runbook.py` → `from tiff.server_access_runbook import build_server_access_runbook, render_markdown, write_runbook_files`
- `tests/unit/test_tiff_source_links.py` → `from tiff.source_links import build_source_links, enrich_sources_with_source_links, summarize_source_links, write_source_link_report`
- `tests/unit/test_tiff_source_link_audit.py` → `from tiff.source_link_audit import audit_source_links, format_source_link_audit, write_source_link_audit_json`
- `tests/unit/test_tiff_source_link_pipeline_quality.py` → `from tiff.pipeline_manifest import build_pipeline_manifest, format_manifest_summary, summarize_source_link_audit_json, summarize_ocr_coverage_audit_json`
- `tests/unit/test_tiff_source_link_pipeline_quality.py` → `from tiff.pipeline_quality import QualityGateThresholds, check_pipeline_manifest, format_quality_gate_result`
- `tests/unit/test_tiff_source_link_pipeline_quality.py` → `from tiff.pipeline_runner import PipelineConfig, PipelineRunResult, PipelineStep, build_pipeline_steps`
- `tests/unit/test_tiff_source_package_quality.py` → `from tiff.source_package_quality import SourcePackageQualityThresholds, build_source_package_quality_result, write_source_package_quality_json`
- `tests/unit/test_tiff_sqlite_scan_report.py` → `from tiff.sqlite_store import connect, get_scan_report, list_tiff_files, upsert_scan_report`
- `tests/unit/test_tiff_storage_adapters.py` → `from tiff.storage_adapters import LocalArtifactCatalogStore, LocalArtifactPaths, LocalJsonlFeedbackStore, OpenSearchKeywordStore, PostgresCatalogStore, QdrantVectorStore, adapter_readiness, build_local_store_bundle`
- `tests/unit/test_tiff_streamlit_api_client.py` → `from tiff import streamlit_api_client`
- `tests/unit/test_tiff_streamlit_trace_feedback.py` → `from tiff.streamlit_trace_feedback import answer_quality_hint, compact_text, feedback_stats, find_first_ata, find_first_page_id, find_first_part, flatten_feedback_items, infer_trace_target, payload_summary, step_body, step_title, trace_steps`
- `tests/unit/test_tiff_streamlit_ui_backend.py` → `from tiff.streamlit_ui_backend import ata_header, format_status_text, load_ui_status, page_header, page_table_rows, parse_rag_stdout, part_header, run_rag_question, search_ata, search_pages, search_parts, source_table_rows`
- `tests/unit/test_tiff_streamlit_ui_backend.py` → `from tiff.document_organization_query import load_export`
- `tests/unit/test_tiff_streamlit_ui_polish.py` → `from tiff.streamlit_ui_backend import ata_result_records, page_result_records, parse_rag_cli_stdout, part_result_records, part_source_records`
- `tests/unit/test_tiff_tesseract_output_decode.py` → `from tiff.title_block_ocr import _decode_tesseract_output`
- `tests/unit/test_tiff_title_block_ocr.py` → `from tiff.json_report import merge_metadata, scan_tiff_to_dict`
- `tests/unit/test_tiff_title_block_ocr.py` → `from tiff.metadata_parser import ParsedDrawingMetadata`
- `tests/unit/test_tiff_title_block_ocr.py` → `from tiff.title_block_ocr import preprocess_for_ocr, title_block_boxes`
- `tests/unit/test_tiff_trace_net.py` → `from tiff.trace_net import TraceNetOptions, TraceNetPaths, build_and_write_trace_net_plan, build_page_signals, plan_page_route`
- `tests/unit/test_tiff_trace_net_algorithm_policy.py` → `from tiff.trace_net_algorithm_policy import AlgorithmPolicyPaths, build_algorithm_policy, build_and_write_algorithm_policy`
- `tests/unit/test_tiff_trace_net_algorithm_policy_quality.py` → `from tiff.trace_net_algorithm_policy_quality import build_algorithm_policy_quality`
- `tests/unit/test_tiff_trace_net_answer_composer.py` → `from tiff.trace_net_answer_composer import AnswerComposerOptions, AnswerComposerPaths, compose_answer`
- `tests/unit/test_tiff_trace_net_answer_quality.py` → `from tiff.trace_net_answer_composer import AnswerComposerOptions, AnswerComposerPaths, compose_answer`
- `tests/unit/test_tiff_trace_net_answer_quality.py` → `from tiff.trace_net_answer_quality import AnswerQualityOptions, AnswerQualityPaths, check_answer_quality`
- `tests/unit/test_tiff_trace_net_ask.py` → `from tiff.trace_net_ask import AskOptions, build_stage_commands, run_trace_net_ask`
- `tests/unit/test_tiff_trace_net_ask_cli.py` → `from tiff.trace_net_ask import build_arg_parser`
- `tests/unit/test_tiff_trace_net_ask_quality.py` → `from tiff.trace_net_ask_quality import evaluate_trace_net_ask_quality`
- `tests/unit/test_tiff_trace_net_baseline.py` → `from tiff.trace_net_pre_algorithm_baseline import flatten_metrics`
- `tests/unit/test_tiff_trace_net_baseline.py` → `from tiff.trace_net_baseline_quality import run_quality`
- `tests/unit/test_tiff_trace_net_cleanup_repair.py` → `from tiff.trace_net_cleanup_repair import TraceNetCleanupRepairOptions, TraceNetCleanupRepairPaths, read_jsonl, repair_cleanup_record, run_trace_net_cleanup_repairs, write_jsonl`
- `tests/unit/test_tiff_trace_net_cleanup_repair_quality.py` → `from tiff.trace_net_cleanup_repair import TraceNetCleanupRepairOptions, TraceNetCleanupRepairPaths, build_trace_net_cleanup_repair_quality, run_trace_net_cleanup_repairs, write_jsonl`
- `tests/unit/test_tiff_trace_net_community_ablation.py` → `from tiff.trace_net_community_ablation import CommunityAblationPaths, evaluate_trace_net_community_ablation`
- `tests/unit/test_tiff_trace_net_community_ablation.py` → `tiff.trace_net_community_ablation`
- `tests/unit/test_tiff_trace_net_community_ablation_quality.py` → `from tiff.trace_net_community_ablation import CommunityAblationPaths, build_community_ablation_quality, write_community_ablation_quality`
- `tests/unit/test_tiff_trace_net_confidence_stage2.py` → `from tiff.trace_net_confidence_stage2 import ConfidenceStage2Paths, evaluate_confidence_stage2`
- `tests/unit/test_tiff_trace_net_confidence_stage2_quality.py` → `from tiff.trace_net_confidence_stage2_quality import ConfidenceStage2QualityPaths, build_confidence_stage2_quality`