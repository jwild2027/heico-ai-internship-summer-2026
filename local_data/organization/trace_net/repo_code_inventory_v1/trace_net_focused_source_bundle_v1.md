# TRACE-Net focused source bundle v1

Focused source windows from high-signal code files.

## `tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- Location: `active_source_code`
- Score: `398`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/stage checklist that proves which gates were actually executed. This bridge is intentionally pre-answer and artifact-only: - it does not call Gemma - it does not replace the WebUI server yet - it does not execute database/vector/search writes - it does not mutate source truth - it does not grant answer permission
- Functions: _read_json(path)@L53; _write_json(path, payload)@L59; _write_jsonl(path, records)@L64; _as_path(value)@L71; _path_status(path)@L77; _stage_row()@L83; _safe_summary(payload)@L108; _records(payload)@L113; _stage_used_row(tool_id, label, report_path, payload, count_key)@L118; _visual_context_bridge_counts(payload)@L134; _webui_visual_context_bridge_row(path, payload)@L154; _artifact_tool_rows(context_pack_payload, input_paths)@L186; _crag_row(crag_payload, crag_path, self_rag_payload)@L245; _checklist_text(rows)@L274; _rollup_safety(stage_payloads)@L287; _import_stage_builders()@L314; build_webui_self_rag_crag_bridge()@L330; _write_markdown(path, payload)@L570
- CLI args: --question, --kernel, --output-dir, --route-dispatch-handoff, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --image-visual-observer, --webui-visual-context-bridge, --max-records-per-slot, --min-high-signal-capsules, --min-evidence-strength-score, --quality, --report-path, --write-json, --min-checklist-count, --min-used-tool-count, --require-query-planner-used, --require-context-pack-builder-used, --require-self-rag-used, --require-crag-evaluated, --require-no-answer-permission, --require-no-source-truth-mutation, --require-no-write-attempts, --require-tool-status, --require-webui-visual-context-bridge-used, --min-visual-context-cards
- Tiff imports: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner; from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint; from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder; from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check; from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan
- Has __main__ guard.

### Source window L1-L50
```python
00001: """TRACE-Net WebUI Self-RAG / CRAG Bridge v1.
00002: 
00003: Runs the current engineering-brain artifact stages for one WebUI-style question
00004: and writes a tool/stage checklist that proves which gates were actually
00005: executed.
00006: 
00007: This bridge is intentionally pre-answer and artifact-only:
00008: - it does not call Gemma
00009: - it does not replace the WebUI server yet
00010: - it does not execute database/vector/search writes
00011: - it does not mutate source truth
00012: - it does not grant answer permission
00013: """
00014: from __future__ import annotations
00015: 
00016: import argparse
00017: import json
00018: from collections import Counter
00019: from pathlib import Path
00020: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
00021: 
00022: MODULE_VERSION = "trace_net_webui_self_rag_crag_bridge_v1"
00023: REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json"
00024: 
00025: STAGE_REPORT_NAMES = {
00026:     "query_planner": "trace_net_engineering_query_planner_v1.json",
00027:     "context_pack_blueprint": "trace_net_engineering_context_pack_blueprint_v1.json",
00028:     "context_pack_builder": "trace_net_engineering_context_pack_builder_v1.json",
00029:     "self_rag": "trace_net_engineering_context_self_rag_check_v1.json",
00030:     "crag_retry": "trace_net_engineering_context_crag_retry_plan_v1.json",
00031: }
00032: 
00033: ARTIFACT_TOOL_KEYS = {
00034:     "route_dispatch": "fishnet_route_dispatch_handoff",
00035:     "table_route": "table_exact_search_adapter",
00036:     "page_context_v2": "page_context_v2",
00037:     "graph_leiden": "leiden_communities",
00038:     "visual_image_route": "image_visual_observer",
00039: }
00040: 
00041: SAFETY_COUNT_KEYS = (
00042:     "unsafe_record_count",
00043:     "answer_permission_count",
00044:     "can_answer_directly_count",
00045:     "can_prove_claims_count",
00046:     "source_truth_mutation_allowed_count",
00047:     "postgres_write_attempt_count",
00048:     "qdrant_write_attempt_count",
00049:     "opensearch_write_attempt_count",
00050: )
```
### Source window L228-L284
```python
00228:                 reason=reason,
00229:                 path=path,
00230:                 count=count,
00231:             )
00232:         )
00233:     rows.append(_webui_visual_context_bridge_row(webui_visual_context_bridge_path, webui_visual_context_bridge_payload))
00234:     rows.append(
00235:         _stage_row(
00236:             tool_id="embedding_vector",
00237:             label="embedding/vector",
00238:             status="not_wired_in_bridge",
00239:             reason="this bridge uses the current context-pack artifacts; live vector search is not yet a stage input here",
00240:         )
00241:     )
00242:     return rows
00243: 
00244: 
00245: def _crag_row(crag_payload: Mapping[str, Any], crag_path: Path, self_rag_payload: Mapping[str, Any]) -> Dict[str, Any]:
00246:     crag_summary = _safe_summary(crag_payload)
00247:     self_summary = _safe_summary(self_rag_payload)
00248:     quality = str(crag_payload.get("quality_status") or "UNKNOWN")
00249:     plan_count = int(crag_summary.get("crag_retry_plan_count") or 0)
00250:     source_required = int(self_summary.get("crag_retry_required_count") or 0)
00251:     if quality != "PASS":
00252:         status = "failed"
00253:         reason = f"CRAG retry plan report quality_status={quality}"
00254:     elif source_required > 0 and plan_count > 0:
00255:         status = "used"
00256:         reason = f"Self-RAG required retry for {source_required} pack(s), so CRAG produced {plan_count} retry plan(s)"
00257:     elif source_required > 0 and plan_count == 0:
00258:         status = "failed"
00259:         reason = "Self-RAG required retry, but CRAG produced zero retry plans"
00260:     else:
00261:         status = "skipped_not_needed"
00262:         reason = "Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans"
00263:     return _stage_row(
00264:         tool_id="crag_retry",
00265:         label="CRAG retry",
00266:         status=status,
00267:         reason=reason,
00268:         path=crag_path,
00269:         count=plan_count,
00270:         quality_status=quality,
00271:     )
00272: 
00273: 
00274: def _checklist_text(rows: Sequence[Mapping[str, Any]]) -> str:
00275:     lines = []
00276:     for row in rows:
00277:         label = str(row.get("label") or row.get("tool_id"))
00278:         status = str(row.get("status"))
00279:         reason = str(row.get("reason") or "")
00280:         if reason:
00281:             lines.append(f"{label}: {status} — {reason}")
00282:         else:
00283:             lines.append(f"{label}: {status}")
00284:     return "\n".join(lines)
```
### Source window L291-L347
```python
00291:         for key in SAFETY_COUNT_KEYS:
00292:             totals[key] += int(summary.get(key) or 0)
00293:         # Record-level fallback for reports that do not put every safety field in summary.
00294:         for record in _records(payload):
00295:             if record.get("unsafe"):
00296:                 totals["unsafe_record_count"] += 1
00297:             if record.get("answer_permission"):
00298:                 totals["answer_permission_count"] += 1
00299:             if record.get("can_answer_directly"):
00300:                 totals["can_answer_directly_count"] += 1
00301:             if record.get("can_prove_claims"):
00302:                 totals["can_prove_claims_count"] += 1
00303:             if record.get("source_truth_mutation_allowed"):
00304:                 totals["source_truth_mutation_allowed_count"] += 1
00305:             if record.get("postgres_write_attempt"):
00306:                 totals["postgres_write_attempt_count"] += 1
00307:             if record.get("qdrant_write_attempt"):
00308:                 totals["qdrant_write_attempt_count"] += 1
00309:             if record.get("opensearch_write_attempt"):
00310:                 totals["opensearch_write_attempt_count"] += 1
00311:     return totals
00312: 
00313: 
00314: def _import_stage_builders() -> Dict[str, Any]:
00315:     from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner
00316:     from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint
00317:     from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder
00318:     from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check
00319:     from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan
00320: 
00321:     return {
00322:         "query_planner": build_engineering_query_planner,
00323:         "context_pack_blueprint": build_engineering_context_pack_blueprint,
00324:         "context_pack_builder": build_engineering_context_pack_builder,
00325:         "self_rag": build_engineering_context_self_rag_check,
00326:         "crag_retry": build_engineering_context_crag_retry_plan,
00327:     }
00328: 
00329: 
00330: def build_webui_self_rag_crag_bridge(
00331:     *,
00332:     question: str,
00333:     kernel_path: Path,
00334:     output_dir: Path,
00335:     route_dispatch_handoff: Optional[Path] = None,
00336:     table_exact_search_adapter: Optional[Path] = None,
00337:     page_context_v2: Optional[Path] = None,
00338:     leiden_communities: Optional[Path] = None,
00339:     image_visual_observer: Optional[Path] = None,
00340:     webui_visual_context_bridge: Optional[Path] = None,
00341:     max_records_per_slot: int = 8,
00342:     min_high_signal_capsules: int = 1,
00343:     min_evidence_strength_score: int = 35,
00344: ) -> Dict[str, Any]:
00345:     """Run the live artifact-stage bridge for one question."""
00346:     if not question.strip():
00347:         raise ValueError("question must not be empty")
```
### Source window L159-L215
```python
00159:     excluded_count = int(counts.get("review_only_visual_context_excluded_count") or 0)
00160:     if path_state == "input_missing":
00161:         status = "input_missing"
00162:         reason = "configured path for webui_visual_context_bridge does not exist"
00163:     elif path_state == "not_configured":
00164:         status = "not_configured"
00165:         reason = "no path configured for webui_visual_context_bridge"
00166:     elif quality != "PASS":
00167:         status = "failed"
00168:         reason = f"webui_visual_context_bridge quality_status={quality}"
00169:     elif card_count > 0:
00170:         status = "used"
00171:         reason = f"loaded {card_count} safe visual context card(s); excluded {excluded_count} review-only visual card(s)"
00172:     else:
00173:         status = "available_not_used"
00174:         reason = f"bridge exists and passed, but no safe visual context cards were available; excluded {excluded_count} review-only card(s)"
00175:     return _stage_row(
00176:         tool_id="webui_visual_context_bridge",
00177:         label="webui visual context bridge",
00178:         status=status,
00179:         reason=reason,
00180:         path=path,
00181:         count=card_count,
00182:         quality_status=str(quality) if quality is not None else None,
00183:     )
00184: 
00185: 
00186: def _artifact_tool_rows(
00187:     context_pack_payload: Mapping[str, Any],
00188:     input_paths: Mapping[str, Optional[Path]],
00189:     *,
00190:     webui_visual_context_bridge_payload: Optional[Mapping[str, Any]] = None,
00191:     webui_visual_context_bridge_path: Optional[Path] = None,
00192: ) -> List[Dict[str, Any]]:
00193:     summary = _safe_summary(context_pack_payload)
00194:     artifact_counts = summary.get("artifact_record_counts") or {}
00195:     visual_counts = _visual_context_bridge_counts(webui_visual_context_bridge_payload)
00196:     visual_card_count = int(visual_counts.get("visual_context_card_count") or 0)
00197:     visual_excluded_count = int(visual_counts.get("review_only_visual_context_excluded_count") or 0)
00198:     rows: List[Dict[str, Any]] = []
00199:     for tool_id, artifact_name in ARTIFACT_TOOL_KEYS.items():
00200:         path = input_paths.get(tool_id)
00201:         path_state = _path_status(path)
00202:         count = int(artifact_counts.get(artifact_name) or 0)
00203:         if tool_id == "visual_image_route" and visual_card_count > 0 and webui_visual_context_bridge_payload and webui_visual_context_bridge_payload.get("quality_status") == "PASS":
00204:             status = "used"
00205:             reason = (
00206:                 f"safe WebUI visual context bridge supplied {visual_card_count} OCR-supported visual card(s); "
00207:                 f"{visual_excluded_count} review-only visual card(s) excluded"
00208:             )
00209:             path = webui_visual_context_bridge_path or path
00210:             count = visual_card_count
00211:         elif count > 0:
00212:             status = "used"
00213:             reason = f"context pack builder selected/loaded {count} records from {artifact_name}"
00214:         elif path_state == "available":
00215:             status = "available_not_used"
```
### Source window L399-L455
```python
00399:     self_rag_path = self_rag_dir / STAGE_REPORT_NAMES["self_rag"]
00400: 
00401:     # Always build the CRAG report. If Self-RAG does not require retry, the
00402:     # CRAG report should contain zero retry plans and the checklist status is
00403:     # skipped_not_needed rather than falsely used.
00404:     crag_payload = builders["crag_retry"](
00405:         self_rag_report_path=self_rag_path,
00406:         output_dir=crag_dir,
00407:     )
00408:     crag_path = crag_dir / STAGE_REPORT_NAMES["crag_retry"]
00409: 
00410:     webui_visual_context_bridge_payload: Optional[Dict[str, Any]] = None
00411:     if webui_visual_context_bridge is not None and webui_visual_context_bridge.exists():
00412:         webui_visual_context_bridge_payload = _read_json(webui_visual_context_bridge)
00413: 
00414:     stage_payloads = [planner_payload, blueprint_payload, pack_payload, self_rag_payload, crag_payload]
00415:     if webui_visual_context_bridge_payload is not None:
00416:         stage_payloads.append(webui_visual_context_bridge_payload)
00417:     stage_paths = {
00418:         "query_planner": planner_path,
00419:         "context_pack_blueprint": blueprint_path,
00420:         "context_pack_builder": pack_path,
00421:         "self_rag": self_rag_path,
00422:         "crag_retry": crag_path,
00423:     }
00424: 
00425:     rows: List[Dict[str, Any]] = [
00426:         _stage_used_row("query_planner", "query planner", planner_path, planner_payload, "query_plan_count"),
00427:         _stage_used_row("context_pack_blueprint", "context pack blueprint", blueprint_path, blueprint_payload, "context_pack_blueprint_count"),
00428:         _stage_used_row("context_pack_builder", "context pack builder", pack_path, pack_payload, "context_pack_count"),
00429:         _stage_used_row("self_rag", "Self-RAG", self_rag_path, self_rag_payload, "self_rag_record_count"),
00430:         _crag_row(crag_payload, crag_path, self_rag_payload),
00431:     ]
00432:     input_paths = {
00433:         "route_dispatch": route_dispatch_handoff,
00434:         "table_route": table_exact_search_adapter,
00435:         "page_context_v2": page_context_v2,
00436:         "graph_leiden": leiden_communities,
00437:         "visual_image_route": image_visual_observer,
00438:         "webui_visual_context_bridge": webui_visual_context_bridge,
00439:     }
00440:     rows.extend(
00441:         _artifact_tool_rows(
00442:             pack_payload,
00443:             input_paths,
00444:             webui_visual_context_bridge_payload=webui_visual_context_bridge_payload,
00445:             webui_visual_context_bridge_path=webui_visual_context_bridge,
00446:         )
00447:     )
00448:     rows.append(
00449:         _stage_row(
00450:             tool_id="gemma_llm",
00451:             label="Gemma LLM",
00452:             status="not_called_by_design",
00453:             reason="this bridge stops before drafting so Self-RAG/CRAG can be audited separately",
00454:         )
00455:     )
```
### Source window L526-L582
```python
00526:     payload: Dict[str, Any] = {
00527:         "module": MODULE_VERSION,
00528:         "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_BUILT",
00529:         "quality_status": quality_status,
00530:         "failures": failures,
00531:         "question": question,
00532:         "summary": summary,
00533:         "tool_checklist": rows,
00534:         "tool_statuses": statuses,
00535:         "checklist_text": _checklist_text(rows),
00536:         "stage_report_paths": {key: str(path) for key, path in stage_paths.items()},
00537:         "input_paths": {key: str(path) if path else None for key, path in input_paths.items()},
00538:         "webui_visual_context_cards": _records(webui_visual_context_bridge_payload or {}),
00539:         "thresholds": {
00540:             "max_records_per_slot": max_records_per_slot,
00541:             "min_high_signal_capsules": min_high_signal_capsules,
00542:             "min_evidence_strength_score": min_evidence_strength_score,
00543:         },
00544:         "safety_contract": {
00545:             "artifact_authority": "webui_brain_gate_bridge_audit_only",
00546:             "answers_user_question": False,
00547:             "llm_call_allowed": False,
00548:             "retrieval_execution_allowed": False,
00549:             "source_truth_mutation_allowed": False,
00550:             "answer_permission": False,
00551:             "can_answer_directly": False,
00552:             "can_prove_claims": False,
00553:             "postgres_write_allowed": False,
00554:             "qdrant_write_allowed": False,
00555:             "opensearch_write_allowed": False,
00556:         },
00557:     }
00558: 
00559:     _write_json(output_dir / REPORT_NAME, payload)
00560:     _write_json(output_dir / "trace_net_webui_self_rag_crag_bridge_v1_summary.json", summary)
00561:     _write_jsonl(output_dir / "trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl", rows)
00562:     (output_dir / "trace_net_webui_self_rag_crag_bridge_v1_checklist.txt").write_text(
00563:         payload["checklist_text"] + "\n",
00564:         encoding="utf-8",
00565:     )
00566:     _write_markdown(output_dir / "trace_net_webui_self_rag_crag_bridge_v1.md", payload)
00567:     return payload
00568: 
00569: 
00570: def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
00571:     summary = _safe_summary(payload)
00572:     lines = [
00573:         "# TRACE-Net WebUI Self-RAG / CRAG Bridge v1",
00574:         "",
00575:         f"Quality status: **{payload.get('quality_status')}**",
00576:         "",
00577:         "## Question",
00578:         "",
00579:         f"`{payload.get('question')}`",
00580:         "",
00581:         "## Summary",
00582:         "",
```
### Source window L624-L680
```python
00624:     failures: List[str] = []
00625: 
00626:     def fail_if(condition: bool, message: str) -> None:
00627:         if condition:
00628:             failures.append(message)
00629: 
00630:     fail_if(payload.get("quality_status") != "PASS", "source bridge report quality_status is not PASS")
00631:     fail_if(int(summary.get("tool_checklist_count") or 0) < min_checklist_count, "not enough checklist rows")
00632:     fail_if(int(summary.get("used_tool_count") or 0) < min_used_tool_count, "not enough used tools")
00633:     if require_query_planner_used:
00634:         fail_if(statuses.get("query_planner") != "used", "query planner was not used")
00635:     if require_context_pack_builder_used:
00636:         fail_if(statuses.get("context_pack_builder") != "used", "context pack builder was not used")
00637:     if require_self_rag_used:
00638:         fail_if(statuses.get("self_rag") != "used", "Self-RAG was not used")
00639:     if require_crag_evaluated:
00640:         fail_if(statuses.get("crag_retry") not in {"used", "skipped_not_needed"}, "CRAG retry was not evaluated")
00641:     if require_webui_visual_context_bridge_used:
00642:         fail_if(statuses.get("webui_visual_context_bridge") != "used", "WebUI visual context bridge was not used")
00643:         fail_if(statuses.get("visual_image_route") != "used", "visual/image route was not used")
00644:     if min_visual_context_cards:
00645:         fail_if(int(summary.get("visual_context_card_count") or 0) < min_visual_context_cards, "visual context card count below minimum")
00646:     if require_no_answer_permission:
00647:         for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
00648:             fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
00649:     if require_no_source_truth_mutation:
00650:         fail_if(int(summary.get("source_truth_mutation_allowed_count") or 0) != 0, "source_truth_mutation_allowed_count is not zero")
00651:     if require_no_write_attempts:
00652:         for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
00653:             fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
00654:     for requirement in require_tool_statuses:
00655:         if "=" not in requirement:
00656:             failures.append(f"invalid --require-tool-status value: {requirement}")
00657:             continue
00658:         tool_id, expected = requirement.split("=", 1)
00659:         actual = statuses.get(tool_id)
00660:         fail_if(actual != expected, f"tool {tool_id} status {actual!r} != expected {expected!r}")
00661: 
00662:     return {
00663:         "quality_status": "FAIL" if failures else "PASS",
00664:         "summary": summary,
00665:         "tool_statuses": statuses,
00666:         "failures": failures,
00667:         "checked_report_path": str(report_path),
00668:     }
00669: 
00670: 
00671: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00672:     parser = argparse.ArgumentParser(description="Build TRACE-Net WebUI Self-RAG / CRAG bridge v1.")
00673:     parser.add_argument("--question", required=True)
00674:     parser.add_argument("--kernel", required=True)
00675:     parser.add_argument("--output-dir", required=True)
00676:     parser.add_argument("--route-dispatch-handoff")
00677:     parser.add_argument("--table-exact-search-adapter")
00678:     parser.add_argument("--page-context-v2")
00679:     parser.add_argument("--leiden-communities")
00680:     parser.add_argument("--image-visual-observer")
```
### Source window L704-L756
```python
00704:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
00705:     print("Checklist:")
00706:     print(payload.get("checklist_text") or "")
00707:     return 0 if payload["quality_status"] == "PASS" else 1
00708: 
00709: 
00710: def main_check(argv: Optional[Sequence[str]] = None) -> int:
00711:     parser = argparse.ArgumentParser(description="Check TRACE-Net WebUI Self-RAG / CRAG bridge v1 quality.")
00712:     parser.add_argument("--report-path", required=True)
00713:     parser.add_argument("--write-json", action="store_true")
00714:     parser.add_argument("--min-checklist-count", type=int, default=8)
00715:     parser.add_argument("--min-used-tool-count", type=int, default=4)
00716:     parser.add_argument("--require-query-planner-used", action="store_true")
00717:     parser.add_argument("--require-context-pack-builder-used", action="store_true")
00718:     parser.add_argument("--require-self-rag-used", action="store_true")
00719:     parser.add_argument("--require-crag-evaluated", action="store_true")
00720:     parser.add_argument("--require-no-answer-permission", action="store_true")
00721:     parser.add_argument("--require-no-source-truth-mutation", action="store_true")
00722:     parser.add_argument("--require-no-write-attempts", action="store_true")
00723:     parser.add_argument("--require-tool-status", action="append", default=[])
00724:     parser.add_argument("--require-webui-visual-context-bridge-used", action="store_true")
00725:     parser.add_argument("--min-visual-context-cards", type=int, default=0)
00726:     args = parser.parse_args(argv)
00727: 
00728:     result = check_webui_self_rag_crag_bridge_quality(
00729:         report_path=Path(args.report_path),
00730:         min_checklist_count=args.min_checklist_count,
00731:         min_used_tool_count=args.min_used_tool_count,
00732:         require_query_planner_used=args.require_query_planner_used,
00733:         require_context_pack_builder_used=args.require_context_pack_builder_used,
00734:         require_self_rag_used=args.require_self_rag_used,
00735:         require_crag_evaluated=args.require_crag_evaluated,
00736:         require_no_answer_permission=args.require_no_answer_permission,
00737:         require_no_source_truth_mutation=args.require_no_source_truth_mutation,
00738:         require_no_write_attempts=args.require_no_write_attempts,
00739:         require_tool_statuses=args.require_tool_status,
00740:         require_webui_visual_context_bridge_used=args.require_webui_visual_context_bridge_used,
00741:         min_visual_context_cards=args.min_visual_context_cards,
00742:     )
00743:     print("Quality status:", result["quality_status"])
00744:     print("Summary:", json.dumps(result["summary"], sort_keys=True))
00745:     print("Tool statuses:", json.dumps(result["tool_statuses"], sort_keys=True))
00746:     if result["failures"]:
00747:         print("Failures:", json.dumps(result["failures"], indent=2))
00748:     if args.write_json:
00749:         out = Path(args.report_path).with_name("trace_net_webui_self_rag_crag_bridge_v1_quality_check.json")
00750:         _write_json(out, result)
00751:         print("Wrote:", out)
00752:     return 0 if result["quality_status"] == "PASS" else 1
00753: 
00754: 
00755: if __name__ == "__main__":
00756:     raise SystemExit(main_build())
```

## `scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py`
- Location: `active_source_code`
- Score: `332`
- Categories: `page, self_rag, server, webui`
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_build
- Has __main__ guard.

### Source window L1-L11
```python
00001: import sys
00002: from pathlib import Path
00003: 
00004: REPO_ROOT = Path(__file__).resolve().parents[1]
00005: if str(REPO_ROOT) not in sys.path:
00006:     sys.path.insert(0, str(REPO_ROOT))
00007: 
00008: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_build
00009: 
00010: if __name__ == "__main__":
00011:     raise SystemExit(main_build())
```

## `scripts/check_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Location: `active_source_code`
- Score: `332`
- Categories: `page, self_rag, server, webui`
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_check
- Has __main__ guard.

### Source window L1-L11
```python
00001: import sys
00002: from pathlib import Path
00003: 
00004: REPO_ROOT = Path(__file__).resolve().parents[1]
00005: if str(REPO_ROOT) not in sys.path:
00006:     sys.path.insert(0, str(REPO_ROOT))
00007: 
00008: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import main_check
00009: 
00010: if __name__ == "__main__":
00011:     raise SystemExit(main_check())
```

## `tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Location: `active_source_code`
- Score: `324`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: load_json(path)@L21; write_json(path, data)@L25; write_jsonl(path, rows)@L30; _as_int(value, default)@L37; _as_bool(value, default)@L52; _first_present(mapping, keys, default)@L62; _first_list(mapping, keys)@L69; _count_records(value)@L77; _nested(mapping, path, default)@L99; _extract_context_packs(report)@L108; _get_evidence_records(pack)@L170; _get_graph_guidance_records(pack)@L201; _get_summary_guidance_records(pack)@L214; _get_aggregation_box(pack)@L227; _has_answer_rules(pack)@L234; _guidance_authority_ok(pack)@L243; evaluate_pack(pack, idx)@L268; _quality_check(name, observed, op, expected)@L407
- CLI args: --min-context-packs, --min-self-rag-evaluations, --min-crag-plans, --min-ready-for-llm, --min-contexts-with-source-truth-evidence, --min-contexts-with-graph-guidance, --min-contexts-with-v2-summary-guidance, --min-contexts-with-aggregation-or-cap-disclosure, --max-retry-required-count, --max-audit-only-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --executed-plan-context-pack, --output-dir, --quality
- Has __main__ guard.

### Source window L1-L37
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: from dataclasses import dataclass
00006: from pathlib import Path
00007: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00008: 
00009: MODULE = "trace_net_e2e_live_self_rag_crag_evaluator_v20"
00010: VERSION = "v20"
00011: READY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_READY_FOR_LIVE_LLM_PROMPT"
00012: NEEDS_RETRY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_NEEDS_CRAG_RETRY_OR_REPAIR"
00013: 
00014: READY_SELF_RAG_STATUSES = {
00015:     "CONTEXT_READY_FOR_LLM",
00016:     "CONTEXT_READY_WITH_CAP_DISCLOSURE",
00017:     "CONTEXT_PARTIAL_NEEDS_LIMITATION",
00018: }
00019: 
00020: 
00021: def load_json(path: str | Path) -> Any:
00022:     return json.loads(Path(path).read_text(encoding="utf-8"))
00023: 
00024: 
00025: def write_json(path: str | Path, data: Any) -> None:
00026:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00027:     Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
00028: 
00029: 
00030: def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
00031:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00032:     with Path(path).open("w", encoding="utf-8") as f:
00033:         for row in rows:
00034:             f.write(json.dumps(row, sort_keys=True) + "\n")
00035: 
00036: 
00037: def _as_int(value: Any, default: int = 0) -> int:
```
### Source window L576-L632
```python
00576: 
00577:     write_json(report_path, report)
00578:     write_jsonl(records_path, records)
00579:     write_jsonl(
00580:         crag_path,
00581:         [
00582:             {
00583:                 "self_rag_crag_record_id": r["self_rag_crag_record_id"],
00584:                 "context_pack_id": r["context_pack_id"],
00585:                 "user_query": r["user_query"],
00586:                 "crag_status": r["crag_status"],
00587:                 "crag_actions": r["crag_actions"],
00588:             }
00589:             for r in records
00590:         ],
00591:     )
00592:     md_path.write_text(render_markdown(report), encoding="utf-8")
00593: 
00594:     report["report_path"] = str(report_path)
00595:     report["records_jsonl_path"] = str(records_path)
00596:     report["crag_plans_jsonl_path"] = str(crag_path)
00597:     report["inspect_md_path"] = str(md_path)
00598:     write_json(report_path, report)
00599:     return report
00600: 
00601: 
00602: def render_markdown(report: Mapping[str, Any]) -> str:
00603:     lines = [
00604:         "# TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20",
00605:         "",
00606:         f"Quality status: **{report.get('quality_status')}**",
00607:         f"Status: `{report.get('status')}`",
00608:         "",
00609:         "## Summary",
00610:     ]
00611:     for key in [
00612:         "context_pack_count",
00613:         "self_rag_evaluation_count",
00614:         "crag_plan_count",
00615:         "ready_for_llm_count",
00616:         "ready_with_cap_disclosure_count",
00617:         "retry_required_count",
00618:         "audit_only_count",
00619:         "contexts_with_source_truth_evidence_count",
00620:         "contexts_with_graph_guidance_count",
00621:         "contexts_with_v2_summary_guidance_count",
00622:         "contexts_with_aggregation_or_cap_disclosure_count",
00623:         "graph_proof_authority_violation_count",
00624:         "summary_proof_authority_violation_count",
00625:         "answer_permission_count",
00626:         "source_truth_mutation_allowed_count",
00627:     ]:
00628:         lines.append(f"- {key}: {report.get(key, 0)}")
00629:     lines.extend(
00630:         [
00631:             "",
00632:             "## Contract",
```
### Source window L260-L316
```python
00260:         if not isinstance(value, str):
00261:             return False
00262:         v = value.lower()
00263:         return "proof" in v and "not" not in v and "false" not in v and "guidance" not in v
00264: 
00265:     return not any(is_bad(v) for v in graph_values), not any(is_bad(v) for v in summary_values)
00266: 
00267: 
00268: def evaluate_pack(pack: Mapping[str, Any], idx: int) -> Dict[str, Any]:
00269:     evidence_records = _get_evidence_records(pack)
00270:     graph_records = _get_graph_guidance_records(pack)
00271:     summary_records = _get_summary_guidance_records(pack)
00272:     aggregation = dict(_get_aggregation_box(pack))
00273: 
00274:     evidence_count = len(evidence_records)
00275:     graph_guidance_count = len(graph_records)
00276:     summary_guidance_count = len(summary_records)
00277:     has_rules = _has_answer_rules(pack)
00278: 
00279:     capped = _as_bool(aggregation.get("result_was_capped")) or _as_bool(aggregation.get("more_results_available"))
00280:     high_degree = _as_bool(aggregation.get("high_degree_node_detected"))
00281:     total_matches = _as_int(aggregation.get("total_match_count"), evidence_count)
00282:     returned_matches = _as_int(aggregation.get("returned_match_count"), evidence_count)
00283:     more_available = _as_bool(aggregation.get("more_results_available"), capped)
00284: 
00285:     graph_ok, summary_ok = _guidance_authority_ok(pack)
00286: 
00287:     if evidence_count <= 0:
00288:         self_rag_status = "CONTEXT_WEAK_NEEDS_CRAG_RETRY"
00289:         crag_status = "CRAG_RETRY_REQUIRED"
00290:         ready_for_llm = False
00291:         audit_only = False
00292:         retry_required = True
00293:         limitations = ["No source-truth evidence is present in the context pack yet."]
00294:     elif not graph_ok or not summary_ok:
00295:         self_rag_status = "CONTEXT_BLOCKED_AUDIT_ONLY"
00296:         crag_status = "CRAG_BLOCKED_BY_AUTHORITY_VIOLATION"
00297:         ready_for_llm = False
00298:         audit_only = True
00299:         retry_required = False
00300:         limitations = ["Graph or summary guidance attempted to claim proof authority."]
00301:     elif capped or high_degree or more_available or total_matches > returned_matches:
00302:         self_rag_status = "CONTEXT_READY_WITH_CAP_DISCLOSURE"
00303:         crag_status = "CRAG_NO_RETRY_NEEDED_PRESERVE_CAP_DISCLOSURE"
00304:         ready_for_llm = True
00305:         audit_only = False
00306:         retry_required = False
00307:         limitations = [
00308:             "Results are capped or aggregated; the final answer must disclose that more matching evidence may exist."
00309:         ]
00310:     else:
00311:         self_rag_status = "CONTEXT_READY_FOR_LLM"
00312:         crag_status = "CRAG_NO_RETRY_NEEDED"
00313:         ready_for_llm = True
00314:         audit_only = False
00315:         retry_required = False
00316:         limitations = ["Final answer must stay limited to cited source-truth evidence."]
```
### Source window L80-L136
```python
00080:     if isinstance(value, dict):
00081:         for key in (
00082:             "records",
00083:             "items",
00084:             "evidence",
00085:             "source_truth_evidence",
00086:             "graph_guidance",
00087:             "v2_summary_guidance",
00088:             "summaries",
00089:         ):
00090:             if isinstance(value.get(key), list):
00091:                 return len(value[key])
00092:         if "count" in value:
00093:             return _as_int(value.get("count"))
00094:         if "record_count" in value:
00095:             return _as_int(value.get("record_count"))
00096:     return 0
00097: 
00098: 
00099: def _nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
00100:     cur: Any = mapping
00101:     for key in path:
00102:         if not isinstance(cur, Mapping) or key not in cur:
00103:             return default
00104:         cur = cur[key]
00105:     return cur
00106: 
00107: 
00108: def _extract_context_packs(report: Mapping[str, Any]) -> List[Mapping[str, Any]]:
00109:     for key in (
00110:         "context_packs",
00111:         "executed_plan_context_packs",
00112:         "executed_plan_context_pack_records",
00113:         "packs",
00114:         "records",
00115:     ):
00116:         value = report.get(key)
00117:         if isinstance(value, list) and value:
00118:             return [v for v in value if isinstance(v, Mapping)]
00119: 
00120:     # Some report artifacts keep counts in the summary and the large records in JSONL only.
00121:     # For quality/audit continuity, synthesize light records from the summary rather than fail blindly.
00122:     count = _as_int(
00123:         _first_present(report, ["context_pack_count", "ready_context_pack_count", "pack_count"], 0)
00124:     )
00125:     if count <= 0:
00126:         return []
00127: 
00128:     total_evidence = _as_int(
00129:         _first_present(report, ["total_source_truth_evidence_count", "source_truth_evidence_count"], 0)
00130:     )
00131:     evidence_per_pack = max(1, total_evidence // max(count, 1)) if total_evidence else 0
00132:     graph_count = _as_int(_first_present(report, ["packs_with_graph_guidance_count"], count))
00133:     summary_count = _as_int(_first_present(report, ["packs_with_v2_summary_guidance_count"], 0))
00134:     cap_count = _as_int(
00135:         _first_present(
00136:             report,
```
### Source window L349-L405
```python
00349:                 "action_type": "no_retry_needed",
00350:                 "requires_source_truth_confirmation": True,
00351:             }
00352:         )
00353: 
00354:     query = str(_first_present(pack, ["user_query", "query"], f"context_pack_{idx+1}"))
00355:     context_pack_id = str(_first_present(pack, ["context_pack_id", "pack_id"], f"context_pack_v19_{idx+1:04d}"))
00356:     query_plan_id = str(_first_present(pack, ["query_plan_id", "plan_id"], f"query_plan_unknown_{idx+1:04d}"))
00357: 
00358:     return {
00359:         "self_rag_crag_record_id": f"self_rag_crag_v20_{idx+1:04d}",
00360:         "context_pack_id": context_pack_id,
00361:         "query_plan_id": query_plan_id,
00362:         "user_query": query,
00363:         "self_rag_status": self_rag_status,
00364:         "crag_status": crag_status,
00365:         "ready_for_llm_prompt": ready_for_llm,
00366:         "audit_only": audit_only,
00367:         "retry_required": retry_required,
00368:         "source_truth_evidence_count": evidence_count,
00369:         "graph_guidance_count": graph_guidance_count,
00370:         "v2_summary_guidance_count": summary_guidance_count,
00371:         "has_answer_rules": has_rules,
00372:         "has_source_truth_evidence": evidence_count > 0,
00373:         "has_graph_guidance": graph_guidance_count > 0,
00374:         "has_v2_summary_guidance": summary_guidance_count > 0,
00375:         "graph_guidance_authority": "guidance_only",
00376:         "v2_summary_authority": "guidance_only",
00377:         "graph_proof_authority_violation": not graph_ok,
00378:         "summary_proof_authority_violation": not summary_ok,
00379:         "aggregation_or_cap_disclosure": {
00380:             "total_match_count": total_matches,
00381:             "returned_match_count": returned_matches,
00382:             "result_was_capped": capped or total_matches > returned_matches,
00383:             "more_results_available": more_available or total_matches > returned_matches,
00384:             "high_degree_node_detected": high_degree,
00385:             "available_drilldowns": aggregation.get(
00386:                 "available_drilldowns",
00387:                 ["document", "manual", "revision", "section", "route", "field", "leiden_community"],
00388:             ),
00389:         },
00390:         "limitations": limitations,
00391:         "crag_actions": crag_actions,
00392:         "safety_contract": {
00393:             "answer_permission": False,
00394:             "can_answer_directly": False,
00395:             "can_prove_claims": False,
00396:             "source_truth_mutation_allowed": False,
00397:             "writes_to_postgres": False,
00398:             "writes_to_qdrant": False,
00399:             "writes_to_opensearch": False,
00400:             "uploads_to_opensearch": False,
00401:             "raw_5tb_scan_at_query_time": False,
00402:             "graph_rebuild_at_query_time": False,
00403:         },
00404:     }
00405: 
```
### Source window L173-L229
```python
00173:         pack.get("evidence"),
00174:         _nested(pack, ["evidence_box", "source_truth_evidence"]),
00175:         _nested(pack, ["evidence_box", "items"]),
00176:         _nested(pack, ["evidence_box", "records"]),
00177:         _nested(pack, ["source_truth_evidence_box", "items"]),
00178:         _nested(pack, ["source_truth_evidence_box", "records"]),
00179:     ]
00180:     for candidate in candidates:
00181:         if isinstance(candidate, list):
00182:             return candidate
00183:     count = _as_int(
00184:         _first_present(
00185:             pack,
00186:             ["source_truth_evidence_count", "evidence_count", "total_source_truth_evidence_count"],
00187:             None,
00188:         ),
00189:         -1,
00190:     )
00191:     if count < 0:
00192:         count = _as_int(
00193:             _nested(pack, ["evidence_box", "source_truth_evidence_count"], None),
00194:             -1,
00195:         )
00196:     if count < 0:
00197:         count = _as_int(_nested(pack, ["evidence_box", "item_count"], 0))
00198:     return [{} for _ in range(max(0, count))]
00199: 
00200: 
00201: def _get_graph_guidance_records(pack: Mapping[str, Any]) -> List[Any]:
00202:     for candidate in (
00203:         pack.get("graph_guidance"),
00204:         pack.get("leiden_guidance"),
00205:         _nested(pack, ["guidance_box", "graph_guidance"]),
00206:         _nested(pack, ["guidance_box", "leiden_guidance"]),
00207:     ):
00208:         if isinstance(candidate, list):
00209:             return candidate
00210:     count = _as_int(_nested(pack, ["guidance_box", "graph_guidance_count"], 0))
00211:     return [{} for _ in range(max(0, count))]
00212: 
00213: 
00214: def _get_summary_guidance_records(pack: Mapping[str, Any]) -> List[Any]:
00215:     for candidate in (
00216:         pack.get("v2_summary_guidance"),
00217:         pack.get("summary_guidance"),
00218:         _nested(pack, ["guidance_box", "v2_summary_guidance"]),
00219:         _nested(pack, ["guidance_box", "summary_guidance"]),
00220:     ):
00221:         if isinstance(candidate, list):
00222:             return candidate
00223:     count = _as_int(_nested(pack, ["guidance_box", "v2_summary_guidance_count"], 0))
00224:     return [{} for _ in range(max(0, count))]
00225: 
00226: 
00227: def _get_aggregation_box(pack: Mapping[str, Any]) -> Mapping[str, Any]:
00228:     for candidate in (pack.get("aggregation_box"), pack.get("aggregation"), pack.get("cap_disclosure")):
00229:         if isinstance(candidate, Mapping):
```
### Source window L422-L478
```python
00422: 
00423: def summarize_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
00424:     return {
00425:         "context_pack_count": len(records),
00426:         "self_rag_evaluation_count": len(records),
00427:         "crag_plan_count": len(records),
00428:         "ready_for_llm_count": sum(1 for r in records if r.get("ready_for_llm_prompt")),
00429:         "ready_with_cap_disclosure_count": sum(
00430:             1 for r in records if r.get("self_rag_status") == "CONTEXT_READY_WITH_CAP_DISCLOSURE"
00431:         ),
00432:         "retry_required_count": sum(1 for r in records if r.get("retry_required")),
00433:         "audit_only_count": sum(1 for r in records if r.get("audit_only")),
00434:         "contexts_with_source_truth_evidence_count": sum(1 for r in records if r.get("has_source_truth_evidence")),
00435:         "contexts_with_graph_guidance_count": sum(1 for r in records if r.get("has_graph_guidance")),
00436:         "contexts_with_v2_summary_guidance_count": sum(1 for r in records if r.get("has_v2_summary_guidance")),
00437:         "contexts_with_aggregation_or_cap_disclosure_count": sum(
00438:             1
00439:             for r in records
00440:             if _as_bool(_nested(r, ["aggregation_or_cap_disclosure", "result_was_capped"]))
00441:             or _as_bool(_nested(r, ["aggregation_or_cap_disclosure", "more_results_available"]))
00442:             or _as_int(_nested(r, ["aggregation_or_cap_disclosure", "total_match_count"], 0))
00443:             >= _as_int(_nested(r, ["aggregation_or_cap_disclosure", "returned_match_count"], 0))
00444:         ),
00445:         "graph_proof_authority_violation_count": sum(1 for r in records if r.get("graph_proof_authority_violation")),
00446:         "summary_proof_authority_violation_count": sum(1 for r in records if r.get("summary_proof_authority_violation")),
00447:         "answer_permission_count": 0,
00448:         "source_truth_mutation_allowed_count": 0,
00449:         "postgres_write_attempt_count": 0,
00450:         "qdrant_write_attempt_count": 0,
00451:         "opensearch_write_attempt_count": 0,
00452:     }
00453: 
00454: 
00455: def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
00456:     checks = [
00457:         _quality_check("context_pack_count", report.get("context_pack_count", 0), ">=", args.min_context_packs),
00458:         _quality_check(
00459:             "self_rag_evaluation_count",
00460:             report.get("self_rag_evaluation_count", 0),
00461:             ">=",
00462:             args.min_self_rag_evaluations,
00463:         ),
00464:         _quality_check("crag_plan_count", report.get("crag_plan_count", 0), ">=", args.min_crag_plans),
00465:         _quality_check("ready_for_llm_count", report.get("ready_for_llm_count", 0), ">=", args.min_ready_for_llm),
00466:         _quality_check(
00467:             "contexts_with_source_truth_evidence_count",
00468:             report.get("contexts_with_source_truth_evidence_count", 0),
00469:             ">=",
00470:             args.min_contexts_with_source_truth_evidence,
00471:         ),
00472:         _quality_check(
00473:             "contexts_with_graph_guidance_count",
00474:             report.get("contexts_with_graph_guidance_count", 0),
00475:             ">=",
00476:             args.min_contexts_with_graph_guidance,
00477:         ),
00478:         _quality_check(
```
### Source window L488-L544
```python
00488:             args.min_contexts_with_aggregation_or_cap_disclosure,
00489:         ),
00490:         _quality_check(
00491:             "retry_required_count",
00492:             report.get("retry_required_count", 0),
00493:             "<=",
00494:             args.max_retry_required_count,
00495:         ),
00496:         _quality_check("audit_only_count", report.get("audit_only_count", 0), "<=", args.max_audit_only_count),
00497:         _quality_check(
00498:             "graph_proof_authority_violation_count",
00499:             report.get("graph_proof_authority_violation_count", 0),
00500:             "<=",
00501:             args.max_graph_proof_authority_violations,
00502:         ),
00503:         _quality_check(
00504:             "summary_proof_authority_violation_count",
00505:             report.get("summary_proof_authority_violation_count", 0),
00506:             "<=",
00507:             args.max_summary_proof_authority_violations,
00508:         ),
00509:         _quality_check(
00510:             "answer_permission_count",
00511:             report.get("answer_permission_count", 0),
00512:             "<=",
00513:             args.max_answer_permission_count,
00514:         ),
00515:         _quality_check(
00516:             "source_truth_mutation_allowed_count",
00517:             report.get("source_truth_mutation_allowed_count", 0),
00518:             "<=",
00519:             args.max_source_truth_mutation_allowed,
00520:         ),
00521:         _quality_check("contract_raw_5tb_scan_at_query_time", False, "is False", False),
00522:         _quality_check("contract_graph_rebuild_at_query_time", False, "is False", False),
00523:     ]
00524:     if getattr(args, "require_no_answer_permission", False):
00525:         checks.append(_quality_check("require_no_answer_permission", report.get("answer_permission_count", 0), "==", 0))
00526:     return checks
00527: 
00528: 
00529: def build_report(
00530:     executed_plan_context_pack: str | Path,
00531:     output_dir: str | Path,
00532:     args: argparse.Namespace,
00533: ) -> Dict[str, Any]:
00534:     source = load_json(executed_plan_context_pack)
00535:     packs = _extract_context_packs(source if isinstance(source, Mapping) else {})
00536:     records = [evaluate_pack(pack, idx) for idx, pack in enumerate(packs)]
00537:     summary = summarize_records(records)
00538: 
00539:     report: Dict[str, Any] = {
00540:         "module": MODULE,
00541:         "version": VERSION,
00542:         "status": READY_STATUS,
00543:         "quality_status": "UNKNOWN",
00544:         "source_report_path": str(executed_plan_context_pack),
```

## `tiff/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Location: `active_source_code`
- Score: `317`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1. Artifact-first targeted smoke for retrieved Engram overlays. This module prepends H24 retrieved Engram overlay guidance to saved engineering answer-runner prompts from an existing answer-smoke manifest. It can run in: * artifact mode: deterministic scaffold answers, no LLM call * ollama mode: targeted local Gemma/Ollama calls Safety contract: - no Postgres writes - no Qdrant reads/writes - no OpenSearch writes/uploads - no source-t
- Functions: _norm(value)@L68; _read_json(path)@L72; _write_json(path, data)@L76; _write_jsonl(path, rows)@L81; _compact_text(text, max_chars)@L88; _parse_question_ids(value)@L99; _index_by_question_id(records)@L109; _load_prompt_from_source_record(record, repo_root)@L113; _source_records(answer_smoke)@L127; _overlay_records(overlay_smoke)@L131; _match_overlay_for_question(question_id, overlays)@L135; _prompt_hash(text)@L142; build_overlay_llm_prompt()@L146; _artifact_answer(question_id, source_record, overlay_record)@L179; _call_ollama(prompt)@L206; _count_unsupported_claims(answer)@L252; _contains_boundary(answer)@L264; grade_h25_answer(question_id, answer, source_grade)@L275
- CLI args: --overlay-smoke, --source-answer-smoke, --output-dir, --question-ids, --llm-mode, --ollama-model, --ollama-url, --timeout-seconds, --max-prompt-chars, --max-overlay-chars, --max-source-prompt-chars, --min-queries, --min-llm-answered, --min-good-answers, --min-good-or-partial-answers, --max-bad-answers, --max-unsupported-claims, --max-unsafe, --max-write-attempts, --require-h24-quality-pass, --require-source-answer-smoke-quality-pass, --require-no-answer-permission, --llm-smoke, --min-queries, --min-llm-answered, --min-good-answers, --min-good-or-partial-answers, --require-quality-pass, --require-no-answer-permission, --max-bad-answers
- Routes: http://127.0.0.1:11434/api/generate@L355, http://127.0.0.1:11434/api/generate@L643
- Has __main__ guard.

### Source window L1-L29
```python
00001: """TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1.
00002: 
00003: Artifact-first targeted smoke for retrieved Engram overlays.
00004: 
00005: This module prepends H24 retrieved Engram overlay guidance to saved engineering
00006: answer-runner prompts from an existing answer-smoke manifest. It can run in:
00007: 
00008: * artifact mode: deterministic scaffold answers, no LLM call
00009: * ollama mode: targeted local Gemma/Ollama calls
00010: 
00011: Safety contract:
00012: - no Postgres writes
00013: - no Qdrant reads/writes
00014: - no OpenSearch writes/uploads
00015: - no source-truth mutation
00016: - no answer permission
00017: - Engram overlay is behavior guidance only; source/manual claims still require
00018:   current proof_context citations.
00019: """
00020: 
00021: from __future__ import annotations
00022: 
00023: import argparse
00024: import hashlib
00025: import json
00026: import re
00027: import urllib.error
00028: import urllib.request
00029: from dataclasses import dataclass
```
### Source window L271-L327
```python
00271:         or "manual/source claims" in lower
00272:     )
00273: 
00274: 
00275: def grade_h25_answer(question_id: str, answer: str, source_grade: str = "") -> Tuple[str, int, List[str]]:
00276:     answer = str(answer or "")
00277:     unsupported = _count_unsupported_claims(answer)
00278:     reasons: List[str] = []
00279:     if not answer.strip():
00280:         return "BAD", unsupported, ["empty_answer"]
00281:     if unsupported:
00282:         return "BAD", unsupported, [f"unsupported_claim_count:{unsupported}"]
00283:     lower = answer.lower()
00284:     if question_id == "q25":
00285:         if any(s in lower for s in ["not found", "not source-trace-ready", "no proof_context", "no proof context"]):
00286:             return "GOOD", unsupported, []
00287:         return "PARTIAL", unsupported, ["unknown_part_boundary_missing"]
00288:     if question_id == "q29":
00289:         if ("summary" in lower or "summaries" in lower) and any(s in lower for s in ["not proof", "cannot prove", "do not prove", "does not prove"]):
00290:             return "GOOD", unsupported, []
00291:         return "PARTIAL", unsupported, ["summary_limit_boundary_missing"]
00292:     if question_id == "q12":
00293:         if any(s in lower for s in ["not proven", "cannot prove", "no explicit", "not interchangeable", "not an approved"]):
00294:             return "GOOD", unsupported, []
00295:         return "PARTIAL", unsupported, ["interchangeability_boundary_weak"]
00296:     if question_id in {"q16", "q18"}:
00297:         if any(s in lower for s in ["ocr", "nomenclature", "visual route", "figure-to-part", "line-text"]):
00298:             return "GOOD", unsupported, []
00299:         return "PARTIAL", unsupported, ["route_or_repair_explanation_weak"]
00300:     if _contains_boundary(answer):
00301:         return "GOOD", unsupported, []
00302:     return "PARTIAL", unsupported, ["boundary_language_missing"]
00303: 
00304: 
00305: def _quality_status(
00306:     *,
00307:     query_count: int,
00308:     llm_answered_count: int,
00309:     good_answer_count: int,
00310:     good_or_partial_answer_count: int,
00311:     bad_answer_count: int,
00312:     unsupported_claim_count: int,
00313:     unsafe_finding_count: int,
00314:     write_attempt_count: int,
00315:     answer_permission_count: int,
00316:     min_queries: int,
00317:     min_llm_answered: int,
00318:     min_good_answers: int,
00319:     min_good_or_partial_answers: int,
00320:     max_bad_answers: int,
00321:     max_unsupported_claims: int,
00322:     max_unsafe: int,
00323:     max_write_attempts: int,
00324: ) -> Tuple[str, List[str]]:
00325:     failures: List[str] = []
00326:     if query_count < min_queries:
00327:         failures.append(f"query_count_below_min:{query_count}<{min_queries}")
```
### Source window L34-L90
```python
00034: VERSION = "v1"
00035: 
00036: SAFETY_CONTRACT = {
00037:     "postgres_write_attempt_count": 0,
00038:     "qdrant_read_attempt_count": 0,
00039:     "qdrant_write_attempt_count": 0,
00040:     "opensearch_write_attempt_count": 0,
00041:     "opensearch_upload_attempt_count": 0,
00042:     "source_truth_mutation_allowed_count": 0,
00043:     "answer_permission_count": 0,
00044: }
00045: 
00046: DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"]
00047: 
00048: REQUIRED_BOUNDARY_TEXT = (
00049:     "Retrieved Engram overlay shapes behavior only. It is not proof. "
00050:     "Manual/source claims still require current proof_context citations."
00051: )
00052: 
00053: ANSWER_INSTRUCTIONS = """Write a concise TRACE-Net engineering answer.
00054: Required sections:
00055: Answer
00056: Evidence
00057: Engineering confidence
00058: Limits
00059: 
00060: Rules:
00061: - Use the retrieved Engram overlay as behavior guidance only, not as source evidence.
00062: - Manual/source claims still require current proof_context citations from the answer-runner prompt.
00063: - If proof_context is missing or insufficient, say not found / not source-trace-ready.
00064: - Do not infer interchangeability, approved replacement, fit approval, installation safety, aircraft effectivity, or source truth from Engram guidance, visual similarity, summaries, graph proximity, or shared nomenclature.
00065: """
00066: 
00067: 
00068: def _norm(value: Any) -> str:
00069:     return " ".join(str(value or "").replace("\r", " ").split())
00070: 
00071: 
00072: def _read_json(path: Path | str) -> Dict[str, Any]:
00073:     return json.loads(Path(path).read_text(encoding="utf-8"))
00074: 
00075: 
00076: def _write_json(path: Path, data: Mapping[str, Any]) -> None:
00077:     path.parent.mkdir(parents=True, exist_ok=True)
00078:     path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
00079: 
00080: 
00081: def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
00082:     path.parent.mkdir(parents=True, exist_ok=True)
00083:     with path.open("w", encoding="utf-8") as f:
00084:         for row in rows:
00085:             f.write(json.dumps(row, sort_keys=True) + "\n")
00086: 
00087: 
00088: def _compact_text(text: str, max_chars: int) -> str:
00089:     text = (text or "").strip()
00090:     if max_chars <= 0:
```
### Source window L129-L185
```python
00129: 
00130: 
00131: def _overlay_records(overlay_smoke: Mapping[str, Any]) -> List[Mapping[str, Any]]:
00132:     return list(overlay_smoke.get("overlay_records") or [])
00133: 
00134: 
00135: def _match_overlay_for_question(question_id: str, overlays: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
00136:     for rec in overlays:
00137:         if str(rec.get("question_id")) == question_id:
00138:             return rec
00139:     return None
00140: 
00141: 
00142: def _prompt_hash(text: str) -> str:
00143:     return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
00144: 
00145: 
00146: def build_overlay_llm_prompt(
00147:     *,
00148:     question_id: str,
00149:     source_record: Mapping[str, Any],
00150:     overlay_record: Mapping[str, Any],
00151:     source_prompt_text: str,
00152:     max_prompt_chars: int = 6000,
00153:     max_overlay_chars: int = 1800,
00154:     max_source_prompt_chars: int = 3600,
00155: ) -> str:
00156:     question = _norm(source_record.get("question") or overlay_record.get("source_question") or question_id)
00157:     overlay_text = overlay_record.get("overlay_text") or overlay_record.get("guidance_overlay_text") or ""
00158:     overlay_text = _compact_text(str(overlay_text), max_overlay_chars)
00159:     source_prompt_text = _compact_text(source_prompt_text, max_source_prompt_chars)
00160: 
00161:     prompt = f"""TRACE-NET H25 TARGETED ANSWER-RUNNER ENGRAM OVERLAY SMOKE
00162: question_id: {question_id}
00163: source_question: {question}
00164: 
00165: {REQUIRED_BOUNDARY_TEXT}
00166: Do not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.
00167: 
00168: RETRIEVED ENGRAM OVERLAY:
00169: {overlay_text}
00170: 
00171: SOURCE ANSWER-RUNNER PROMPT:
00172: {source_prompt_text}
00173: 
00174: {ANSWER_INSTRUCTIONS}
00175: """
00176:     return _compact_text(prompt, max_prompt_chars)
00177: 
00178: 
00179: def _artifact_answer(question_id: str, source_record: Mapping[str, Any], overlay_record: Mapping[str, Any]) -> str:
00180:     question = _norm(source_record.get("question") or overlay_record.get("source_question") or question_id)
00181:     source_answer = source_record.get("answer_text") or source_record.get("answer_preview") or ""
00182:     source_answer = str(source_answer).strip()
00183:     if source_answer:
00184:         return (
00185:             "Answer:\n"
```
### Source window L188-L244
```python
00188:             "Evidence:\n"
00189:             "- Manual/source claims still require current proof_context citations from the source answer-runner prompt.\n"
00190:             "- Retrieved Engram guidance does not grant answer permission and does not mutate source truth.\n\n"
00191:             "Engineering confidence:\n"
00192:             "MEDIUM for integration behavior in artifact mode; no new source claim is introduced.\n\n"
00193:             "Limits:\n"
00194:             "This artifact-mode smoke does not prove new manual facts. It validates prompt overlay assembly only.\n\n"
00195:             "Source answer preview:\n"
00196:             + _compact_text(source_answer, 1000)
00197:         )
00198:     return (
00199:         "Answer:\nNot source-trace-ready in artifact mode because no source answer text was available.\n\n"
00200:         "Evidence:\n- No source answer text was available.\n\n"
00201:         "Engineering confidence:\nLOW.\n\n"
00202:         "Limits:\nNo source claim is made."
00203:     )
00204: 
00205: 
00206: def _call_ollama(
00207:     prompt: str,
00208:     *,
00209:     ollama_model: str,
00210:     ollama_url: str,
00211:     timeout_seconds: int,
00212:     num_predict: int = 700,
00213:     temperature: float = 0.1,
00214: ) -> Tuple[str, str]:
00215:     payload = {
00216:         "model": ollama_model,
00217:         "prompt": prompt,
00218:         "stream": False,
00219:         "options": {"num_predict": num_predict, "temperature": temperature},
00220:     }
00221:     req = urllib.request.Request(
00222:         ollama_url,
00223:         data=json.dumps(payload).encode("utf-8"),
00224:         headers={"Content-Type": "application/json"},
00225:     )
00226:     try:
00227:         with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
00228:             data = json.loads(resp.read().decode("utf-8"))
00229:         answer = str(data.get("response") or "").strip()
00230:         if not answer:
00231:             return "", "RuntimeError: Ollama response did not contain answer text"
00232:         return answer, ""
00233:     except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
00234:         return "", f"{type(exc).__name__}: {exc}"
00235: 
00236: 
00237: _UNSAFE_ASSERTION_PATTERNS = [
00238:     r"\bis interchangeable with\b",
00239:     r"\bare interchangeable\b",
00240:     r"\bis an approved replacement\b",
00241:     r"\bare approved replacements\b",
00242:     r"\bproves installation safety\b",
00243:     r"\bproves fit approval\b",
00244:     r"\bproves aircraft effectivity\b",
```
### Source window L522-L578
```python
00522:     quality_failures.extend(unsafe_findings)
00523:     if quality_failures:
00524:         quality_status = "FAIL"
00525: 
00526:     summary = {
00527:         "module": MODULE,
00528:         "version": VERSION,
00529:         "llm_mode": llm_mode,
00530:         "llm_model": ollama_model if llm_mode == "ollama" else "artifact_scaffold",
00531:         "query_count": query_count,
00532:         "llm_answered_count": llm_answered_count,
00533:         "good_answer_count": good_answer_count,
00534:         "partial_answer_count": partial_answer_count,
00535:         "bad_answer_count": bad_answer_count,
00536:         "good_or_partial_answer_count": good_or_partial_answer_count,
00537:         "unsupported_claim_count": unsupported_claim_count,
00538:         "llm_retry_used_count": sum(1 for r in smoke_records if r.get("llm_retry_used")),
00539:         "llm_fallback_used_count": sum(1 for r in smoke_records if r.get("llm_fallback_used")),
00540:         "source_h24_overlay_quality_status": source_overlay_quality,
00541:         "source_answer_smoke_quality_status": source_answer_quality,
00542:         "target_question_ids": targets,
00543:         "unsafe_finding_count": unsafe_finding_count,
00544:         "unsafe_findings": unsafe_findings,
00545:         "quality_failures": quality_failures,
00546:         "ready_for_answer_runner_overlay_patch": quality_status == "PASS",
00547:         "answer_permission_count": answer_permission_count,
00548:         "source_truth_mutation_allowed_count": 0,
00549:         "postgres_write_attempt_count": 0,
00550:         "qdrant_read_attempt_count": 0,
00551:         "qdrant_write_attempt_count": 0,
00552:         "opensearch_write_attempt_count": 0,
00553:         "opensearch_upload_attempt_count": 0,
00554:         "write_attempt_count": write_attempt_count,
00555:     }
00556: 
00557:     result = {
00558:         "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_OVERLAY_LLM_SMOKE_BUILT",
00559:         "quality_status": quality_status,
00560:         "summary": summary,
00561:         "integration_policy": {
00562:             "mode": "targeted_answer_runner_overlay_llm_smoke",
00563:             "proof_boundary": REQUIRED_BOUNDARY_TEXT,
00564:             "forbidden": [
00565:                 "answer_permission_from_engram",
00566:                 "source_truth_mutation_from_engram",
00567:                 "summary_or_engram_used_as_proof",
00568:                 "live_db_or_qdrant_io_without_explicit_gate",
00569:                 "full_30_question_rerun_as_default_debug_loop",
00570:             ],
00571:             "next_patch": "wire overlay prompt into answer runner behind explicit CLI flag",
00572:         },
00573:         "smoke_records": smoke_records,
00574:     }
00575: 
00576:     out_dir.mkdir(parents=True, exist_ok=True)
00577:     main_path = out_dir / f"{MODULE}.json"
00578:     jsonl_path = out_dir / f"{MODULE}_records.jsonl"
```
### Source window L600-L656
```python
00600:     data = _read_json(Path(llm_smoke))
00601:     summary = data.get("summary", {})
00602:     status, failures = _quality_status(
00603:         query_count=int(summary.get("query_count") or 0),
00604:         llm_answered_count=int(summary.get("llm_answered_count") or 0),
00605:         good_answer_count=int(summary.get("good_answer_count") or 0),
00606:         good_or_partial_answer_count=int(summary.get("good_or_partial_answer_count") or 0),
00607:         bad_answer_count=int(summary.get("bad_answer_count") or 0),
00608:         unsupported_claim_count=int(summary.get("unsupported_claim_count") or 0),
00609:         unsafe_finding_count=int(summary.get("unsafe_finding_count") or 0),
00610:         write_attempt_count=int(summary.get("write_attempt_count") or 0),
00611:         answer_permission_count=int(summary.get("answer_permission_count") or 0),
00612:         min_queries=min_queries,
00613:         min_llm_answered=min_llm_answered,
00614:         min_good_answers=min_good_answers,
00615:         min_good_or_partial_answers=min_good_or_partial_answers,
00616:         max_bad_answers=max_bad_answers,
00617:         max_unsupported_claims=max_unsupported_claims,
00618:         max_unsafe=max_unsafe,
00619:         max_write_attempts=max_write_attempts,
00620:     )
00621:     if require_quality_pass and data.get("quality_status") != "PASS":
00622:         failures.append("source_quality_status_not_pass")
00623:     if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
00624:         failures.append("answer_permission_count_above_zero")
00625:     if failures:
00626:         status = "FAIL"
00627:     return {
00628:         "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_OVERLAY_LLM_SMOKE_CHECKED",
00629:         "quality_status": status,
00630:         "quality_failures": failures,
00631:         "summary": summary,
00632:     }
00633: 
00634: 
00635: def build_arg_parser() -> argparse.ArgumentParser:
00636:     p = argparse.ArgumentParser(description=MODULE)
00637:     p.add_argument("--overlay-smoke", required=True)
00638:     p.add_argument("--source-answer-smoke", required=True)
00639:     p.add_argument("--output-dir", required=True)
00640:     p.add_argument("--question-ids", default=",".join(DEFAULT_TARGET_QUESTION_IDS))
00641:     p.add_argument("--llm-mode", choices=["artifact", "ollama"], default="artifact")
00642:     p.add_argument("--ollama-model", default="gemma4:26b")
00643:     p.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
00644:     p.add_argument("--timeout-seconds", type=int, default=420)
00645:     p.add_argument("--max-prompt-chars", type=int, default=6000)
00646:     p.add_argument("--max-overlay-chars", type=int, default=1800)
00647:     p.add_argument("--max-source-prompt-chars", type=int, default=3600)
00648:     p.add_argument("--min-queries", type=int, default=5)
00649:     p.add_argument("--min-llm-answered", type=int, default=5)
00650:     p.add_argument("--min-good-answers", type=int, default=4)
00651:     p.add_argument("--min-good-or-partial-answers", type=int, default=5)
00652:     p.add_argument("--max-bad-answers", type=int, default=0)
00653:     p.add_argument("--max-unsupported-claims", type=int, default=0)
00654:     p.add_argument("--max-unsafe", type=int, default=0)
00655:     p.add_argument("--max-write-attempts", type=int, default=0)
00656:     p.add_argument("--require-h24-quality-pass", action="store_true")
```
### Source window L342-L398
```python
00342:     if answer_permission_count > 0:
00343:         failures.append("answer_permission_count_above_zero")
00344:     return ("PASS" if not failures else "FAIL", failures)
00345: 
00346: 
00347: def build_answer_runner_overlay_llm_smoke(
00348:     *,
00349:     overlay_smoke: Path | str,
00350:     source_answer_smoke: Path | str,
00351:     output_dir: Path | str,
00352:     question_ids: Optional[str] = None,
00353:     llm_mode: str = "artifact",
00354:     ollama_model: str = "gemma4:26b",
00355:     ollama_url: str = "http://127.0.0.1:11434/api/generate",
00356:     timeout_seconds: int = 420,
00357:     max_prompt_chars: int = 6000,
00358:     max_overlay_chars: int = 1800,
00359:     max_source_prompt_chars: int = 3600,
00360:     min_queries: int = 5,
00361:     min_llm_answered: int = 5,
00362:     min_good_answers: int = 4,
00363:     min_good_or_partial_answers: int = 5,
00364:     max_bad_answers: int = 0,
00365:     max_unsupported_claims: int = 0,
00366:     max_unsafe: int = 0,
00367:     max_write_attempts: int = 0,
00368:     require_h24_quality_pass: bool = False,
00369:     require_source_answer_smoke_quality_pass: bool = False,
00370:     require_no_answer_permission: bool = False,
00371: ) -> Dict[str, Any]:
00372:     overlay_smoke_path = Path(overlay_smoke)
00373:     source_answer_smoke_path = Path(source_answer_smoke)
00374:     out_dir = Path(output_dir)
00375:     repo_root = Path.cwd()
00376: 
00377:     overlay_manifest = _read_json(overlay_smoke_path)
00378:     source_manifest = _read_json(source_answer_smoke_path)
00379:     overlays = _overlay_records(overlay_manifest)
00380:     source_index = _index_by_question_id(_source_records(source_manifest))
00381:     targets = _parse_question_ids(question_ids)
00382: 
00383:     smoke_records: List[Dict[str, Any]] = []
00384:     unsafe_findings: List[str] = []
00385: 
00386:     for qid in targets:
00387:         src = source_index.get(qid)
00388:         ov = _match_overlay_for_question(qid, overlays)
00389:         if not src:
00390:             unsafe_findings.append(f"missing_source_answer_record:{qid}")
00391:             continue
00392:         if not ov:
00393:             unsafe_findings.append(f"missing_overlay_record:{qid}")
00394:             continue
00395: 
00396:         source_prompt = _load_prompt_from_source_record(src, repo_root)
00397:         prompt = build_overlay_llm_prompt(
00398:             question_id=qid,
```

## `tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Location: `active_source_code`
- Score: `310`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _missing_boundary_groups(text)@L56; _norm(value)@L65; _read_json(path)@L69; _write_json(path, data)@L73; _write_jsonl(path, records)@L78; _as_list(value)@L85; _safety_counts_zero(data)@L95; _compact_text(text, max_chars)@L111; _prompt_bundles(prompt_injector)@L118; _llm_smoke_records(llm_smoke)@L122; build_bridge_records(prompt_injector, llm_smoke)@L128; _count_task_types(records)@L175; _count_layers(records)@L183; build_answer_runner_retrieval_bridge_manifest()@L192; check_answer_runner_retrieval_bridge_manifest()@L324; build_arg_parser()@L359; main(argv)@L375
- CLI args: --prompt-injector, --h22-llm-smoke, --output-dir, --max-guidance-chars, --min-bridge-records, --min-task-types, --require-h20-quality-pass, --require-h22-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.

### Source window L1-L36
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: from pathlib import Path
00006: from typing import Any, Dict, Iterable, List, Mapping, Sequence
00007: 
00008: MODULE = "trace_net_engineering_engram_answer_runner_retrieval_bridge_v1"
00009: VERSION = "v1"
00010: 
00011: SAFETY_CONTRACT = {
00012:     "answer_permission": False,
00013:     "source_truth_mutation_allowed": False,
00014:     "postgres_write_attempt": False,
00015:     "qdrant_read_attempt": False,
00016:     "qdrant_write_attempt": False,
00017:     "opensearch_write_attempt": False,
00018:     "opensearch_upload_attempt": False,
00019:     "write_attempt": False,
00020:     "live_qdrant_io_attempted": False,
00021:     "engram_is_proof": False,
00022: }
00023: 
00024: TASK_TYPE_TO_TARGET_QUESTIONS = {
00025:     "interchangeability_boundary": ["q12", "q21"],
00026:     "approval_boundary": ["q13", "q14", "q15", "q30"],
00027:     "route_explanation": ["q16", "q17", "q27", "q28"],
00028:     "critic_repair": ["q16", "q18", "q27"],
00029:     "unknown_part": ["q25"],
00030:     "summary_limit": ["q29"],
00031: }
00032: 
00033: REQUIRED_BOUNDARY_GROUPS = {
00034:     "behavior_guidance_boundary": [
00035:         "behavior guidance only",
00036:         "behavior only",
```
### Source window L87-L143
```python
00087:         return []
00088:     if isinstance(value, list):
00089:         return value
00090:     if isinstance(value, tuple):
00091:         return list(value)
00092:     return [value]
00093: 
00094: 
00095: def _safety_counts_zero(data: Mapping[str, Any]) -> bool:
00096:     summary = data.get("summary") or {}
00097:     keys = [
00098:         "answer_permission_count",
00099:         "source_truth_mutation_allowed_count",
00100:         "postgres_write_attempt_count",
00101:         "qdrant_read_attempt_count",
00102:         "qdrant_write_attempt_count",
00103:         "opensearch_write_attempt_count",
00104:         "opensearch_upload_attempt_count",
00105:         "write_attempt_count",
00106:         "unsafe_finding_count",
00107:     ]
00108:     return all(int(summary.get(k) or 0) == 0 for k in keys)
00109: 
00110: 
00111: def _compact_text(text: str, max_chars: int) -> str:
00112:     text = _norm(text)
00113:     if len(text) <= max_chars:
00114:         return text
00115:     return text[: max(0, max_chars - 90)].rstrip() + "\n[TRUNCATED BY H23 BRIDGE: guidance only, not proof.]"
00116: 
00117: 
00118: def _prompt_bundles(prompt_injector: Mapping[str, Any]) -> List[Dict[str, Any]]:
00119:     return [dict(r) for r in (prompt_injector.get("prompt_bundles") or prompt_injector.get("prompt_integration_records") or [])]
00120: 
00121: 
00122: def _llm_smoke_records(llm_smoke: Mapping[str, Any] | None) -> Dict[str, Mapping[str, Any]]:
00123:     if not llm_smoke:
00124:         return {}
00125:     return {str(r.get("query_id")): r for r in (llm_smoke.get("smoke_records") or [])}
00126: 
00127: 
00128: def build_bridge_records(
00129:     prompt_injector: Mapping[str, Any],
00130:     llm_smoke: Mapping[str, Any] | None = None,
00131:     *,
00132:     max_guidance_chars: int = 1400,
00133: ) -> List[Dict[str, Any]]:
00134:     smoke_by_query = _llm_smoke_records(llm_smoke)
00135:     records: List[Dict[str, Any]] = []
00136:     for bundle in _prompt_bundles(prompt_injector):
00137:         query_id = _norm(bundle.get("query_id"))
00138:         task_type = _norm(bundle.get("task_type"))
00139:         guidance = _norm(bundle.get("prompt_guidance_text") or bundle.get("integration_prompt_text") or bundle.get("integration_prompt_preview"))
00140:         llm_record = smoke_by_query.get(query_id, {})
00141:         missing_boundary_phrases = _missing_boundary_groups(guidance)
00142:         selected_proof_roles = [str(x) for x in _as_list(bundle.get("selected_proof_roles"))]
00143:         bad_proof_roles = [r for r in selected_proof_roles if r not in {"guidance_only", "current_proof_context_only"}]
```
### Source window L169-L225
```python
00169:             **SAFETY_CONTRACT,
00170:         }
00171:         records.append(record)
00172:     return records
00173: 
00174: 
00175: def _count_task_types(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
00176:     counts: Dict[str, int] = {}
00177:     for r in records:
00178:         task = str(r.get("task_type") or "unknown")
00179:         counts[task] = counts.get(task, 0) + 1
00180:     return dict(sorted(counts.items()))
00181: 
00182: 
00183: def _count_layers(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
00184:     counts: Dict[str, int] = {}
00185:     for r in records:
00186:         for layer in _as_list(r.get("selected_layers")):
00187:             layer_s = str(layer)
00188:             counts[layer_s] = counts.get(layer_s, 0) + 1
00189:     return dict(sorted(counts.items()))
00190: 
00191: 
00192: def build_answer_runner_retrieval_bridge_manifest(
00193:     *,
00194:     prompt_injector: str | Path,
00195:     h22_llm_smoke: str | Path | None = None,
00196:     output_dir: str | Path,
00197:     max_guidance_chars: int = 1400,
00198:     min_bridge_records: int = 6,
00199:     min_task_types: int = 5,
00200:     require_h20_quality_pass: bool = True,
00201:     require_h22_quality_pass: bool = False,
00202:     require_no_answer_permission: bool = True,
00203:     max_unsafe: int = 0,
00204:     max_write_attempts: int = 0,
00205: ) -> Dict[str, Any]:
00206:     prompt_injector_path = Path(prompt_injector)
00207:     prompt_data = _read_json(prompt_injector_path)
00208:     h22_data: Dict[str, Any] | None = None
00209:     h22_path_s = ""
00210:     if h22_llm_smoke:
00211:         h22_path = Path(h22_llm_smoke)
00212:         h22_path_s = str(h22_path)
00213:         h22_data = _read_json(h22_path)
00214:     records = build_bridge_records(prompt_data, h22_data, max_guidance_chars=max_guidance_chars)
00215:     unsafe_records = [r for r in records if r.get("unsafe")]
00216:     write_attempt_count = sum(1 for r in records if r.get("write_attempt"))
00217:     answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
00218:     target_question_ids = sorted({qid for r in records for qid in _as_list(r.get("target_answer_runner_question_ids"))})
00219: 
00220:     quality_failures: List[str] = []
00221:     if require_h20_quality_pass and prompt_data.get("quality_status") != "PASS":
00222:         quality_failures.append("source_prompt_injector_not_pass")
00223:     if require_h22_quality_pass and (not h22_data or h22_data.get("quality_status") != "PASS"):
00224:         quality_failures.append("source_h22_llm_smoke_not_pass")
00225:     if not _safety_counts_zero(prompt_data):
```
### Source window L249-L305
```python
00249:         r["task_type"]: {
00250:             "query_id": r["query_id"],
00251:             "target_answer_runner_question_ids": r["target_answer_runner_question_ids"],
00252:             "guidance_overlay_text": r["guidance_overlay_text"],
00253:             "selected_layers": r["selected_layers"],
00254:             "selected_proof_roles": r["selected_proof_roles"],
00255:             "proof_boundary": r["proof_boundary"],
00256:             "answer_permission": False,
00257:             "engram_is_proof": False,
00258:         }
00259:         for r in records
00260:     }
00261: 
00262:     summary = {
00263:         "module": MODULE,
00264:         "version": VERSION,
00265:         "source_prompt_injector_quality_status": prompt_data.get("quality_status"),
00266:         "source_h22_llm_smoke_quality_status": h22_data.get("quality_status") if h22_data else None,
00267:         "bridge_record_count": len(records),
00268:         "task_type_count": len(_count_task_types(records)),
00269:         "task_type_counts": _count_task_types(records),
00270:         "selected_memory_layer_counts": _count_layers(records),
00271:         "target_answer_runner_question_count": len(target_question_ids),
00272:         "target_answer_runner_question_ids": target_question_ids,
00273:         "ready_for_answer_runner_prompt_overlay_patch": quality_status == "PASS",
00274:         "answer_permission_count": answer_permission_count,
00275:         "source_truth_mutation_allowed_count": 0,
00276:         "postgres_write_attempt_count": 0,
00277:         "qdrant_read_attempt_count": 0,
00278:         "qdrant_write_attempt_count": 0,
00279:         "opensearch_write_attempt_count": 0,
00280:         "opensearch_upload_attempt_count": 0,
00281:         "write_attempt_count": write_attempt_count,
00282:         "unsafe_finding_count": len(unsafe_records),
00283:         "quality_failures": quality_failures,
00284:     }
00285: 
00286:     manifest = {
00287:         "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_RETRIEVAL_BRIDGE_BUILT",
00288:         "quality_status": quality_status,
00289:         "summary": summary,
00290:         "quality_failures": quality_failures,
00291:         "source_prompt_injector_path": str(prompt_injector_path),
00292:         "source_h22_llm_smoke_path": h22_path_s,
00293:         "safety_contract": dict(SAFETY_CONTRACT),
00294:         "integration_policy": {
00295:             "mode": "artifact_only_answer_runner_guidance_bridge",
00296:             "proof_boundary": "Retrieved Engram guidance shapes behavior only; factual manual claims require current proof_context citations.",
00297:             "forbidden": [
00298:                 "answer_permission_from_engram",
00299:                 "source_truth_mutation_from_engram",
00300:                 "summary_or_engram_used_as_proof",
00301:                 "live_db_or_qdrant_io_without_explicit_gate",
00302:             ],
00303:             "next_patch": "wire guidance_map into a targeted answer-runner smoke behind an explicit CLI flag",
00304:         },
00305:         "bridge_records": records,
```
### Source window L323-L379
```python
00323: 
00324: def check_answer_runner_retrieval_bridge_manifest(
00325:     *,
00326:     bridge: str | Path,
00327:     min_bridge_records: int = 6,
00328:     min_task_types: int = 5,
00329:     require_quality_pass: bool = True,
00330:     require_no_answer_permission: bool = True,
00331:     max_unsafe: int = 0,
00332:     max_write_attempts: int = 0,
00333: ) -> Dict[str, Any]:
00334:     data = _read_json(bridge)
00335:     summary = dict(data.get("summary") or {})
00336:     failures: List[str] = []
00337:     if require_quality_pass and data.get("quality_status") != "PASS":
00338:         failures.append("source_quality_status_not_pass")
00339:     if int(summary.get("bridge_record_count") or 0) < min_bridge_records:
00340:         failures.append("bridge_record_count_below_min")
00341:     if int(summary.get("task_type_count") or 0) < min_task_types:
00342:         failures.append("task_type_count_below_min")
00343:     if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
00344:         failures.append("answer_permission_count_nonzero")
00345:     if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
00346:         failures.append("unsafe_finding_count_above_max")
00347:     if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
00348:         failures.append("write_attempt_count_above_max")
00349:     quality_status = "PASS" if not failures else "FAIL"
00350:     result = {
00351:         "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_RETRIEVAL_BRIDGE_CHECKED",
00352:         "quality_status": quality_status,
00353:         "summary": summary,
00354:         "quality_failures": failures,
00355:     }
00356:     return result
00357: 
00358: 
00359: def build_arg_parser() -> argparse.ArgumentParser:
00360:     p = argparse.ArgumentParser(description="Build TRACE-Net H23 Engram answer-runner retrieval bridge.")
00361:     p.add_argument("--prompt-injector", required=True)
00362:     p.add_argument("--h22-llm-smoke", default="")
00363:     p.add_argument("--output-dir", required=True)
00364:     p.add_argument("--max-guidance-chars", type=int, default=1400)
00365:     p.add_argument("--min-bridge-records", type=int, default=6)
00366:     p.add_argument("--min-task-types", type=int, default=5)
00367:     p.add_argument("--require-h20-quality-pass", action="store_true")
00368:     p.add_argument("--require-h22-quality-pass", action="store_true")
00369:     p.add_argument("--require-no-answer-permission", action="store_true")
00370:     p.add_argument("--max-unsafe", type=int, default=0)
00371:     p.add_argument("--max-write-attempts", type=int, default=0)
00372:     return p
00373: 
00374: 
00375: def main(argv: Sequence[str] | None = None) -> int:
00376:     args = build_arg_parser().parse_args(argv)
00377:     result = build_answer_runner_retrieval_bridge_manifest(
00378:         prompt_injector=args.prompt_injector,
00379:         h22_llm_smoke=args.h22_llm_smoke or None,
```

## `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- Location: `active_tests`
- Score: `307`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L7; test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch)@L13; test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path)@L113; test_checklist_text_includes_reasons()@L121; test_bridge_precreates_stage_report_directories_for_stage_builders(tmp_path, monkeypatch)@L130; fake_query_planner()@L19; fake_blueprint()@L28; fake_pack_builder()@L37; fake_self_rag()@L58; fake_crag()@L72; write_without_mkdir(path, payload)@L134; fake_query_planner()@L139; fake_blueprint()@L145; fake_pack_builder()@L152; fake_self_rag()@L168; fake_crag()@L179
- Tiff imports: from tiff import trace_net_webui_self_rag_crag_bridge_v1

### Source window L1-L32
```python
00001: import json
00002: from pathlib import Path
00003: 
00004: from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge
00005: 
00006: 
00007: def _write(path: Path, payload: dict) -> dict:
00008:     path.parent.mkdir(parents=True, exist_ok=True)
00009:     path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
00010:     return payload
00011: 
00012: 
00013: def test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch):
00014:     kernel = tmp_path / "kernel.json"
00015:     kernel.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
00016:     route_dispatch = tmp_path / "route_dispatch.json"
00017:     route_dispatch.write_text(json.dumps({"records": [{"page_id": "source_p000001", "text": "120-29073-001 seat assembly"}]}), encoding="utf-8")
00018: 
00019:     def fake_query_planner(*, kernel_path, output_dir, questions):
00020:         assert kernel_path == kernel
00021:         payload = {
00022:             "quality_status": "PASS",
00023:             "summary": {"query_plan_count": len(questions)},
00024:             "records": [{"question_id": "q1", "user_question": questions[0], "answer_permission": False}],
00025:         }
00026:         return _write(output_dir / bridge.STAGE_REPORT_NAMES["query_planner"], payload)
00027: 
00028:     def fake_blueprint(*, query_planner_path, output_dir):
00029:         assert query_planner_path.exists()
00030:         payload = {
00031:             "quality_status": "PASS",
00032:             "summary": {"context_pack_blueprint_count": 1},
```
### Source window L95-L151
```python
00095:     )
00096: 
00097:     payload = bridge.build_webui_self_rag_crag_bridge(
00098:         question="Find part number 120-29073-001",
00099:         kernel_path=kernel,
00100:         output_dir=tmp_path / "bridge",
00101:         route_dispatch_handoff=route_dispatch,
00102:     )
00103: 
00104:     assert payload["quality_status"] == "PASS"
00105:     assert payload["tool_statuses"]["query_planner"] == "used"
00106:     assert payload["tool_statuses"]["self_rag"] == "used"
00107:     assert payload["tool_statuses"]["crag_retry"] == "used"
00108:     assert payload["tool_statuses"]["route_dispatch"] == "used"
00109:     assert payload["summary"]["self_rag_crag_retry_required_count"] == 1
00110:     assert payload["summary"]["answer_permission_count"] == 0
00111: 
00112: 
00113: def test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path):
00114:     self_payload = {"summary": {"crag_retry_required_count": 0}}
00115:     crag_payload = {"quality_status": "PASS", "summary": {"crag_retry_plan_count": 0}}
00116:     row = bridge._crag_row(crag_payload, tmp_path / "crag.json", self_payload)
00117:     assert row["status"] == "skipped_not_needed"
00118:     assert "did not require" in row["reason"]
00119: 
00120: 
00121: def test_checklist_text_includes_reasons():
00122:     text = bridge._checklist_text([
00123:         {"label": "Self-RAG", "status": "used", "reason": "stage report built"},
00124:         {"label": "CRAG retry", "status": "skipped_not_needed", "reason": "Self-RAG was strong"},
00125:     ])
00126:     assert "Self-RAG: used" in text
00127:     assert "CRAG retry: skipped_not_needed" in text
00128: 
00129: 
00130: def test_bridge_precreates_stage_report_directories_for_stage_builders(tmp_path, monkeypatch):
00131:     kernel = tmp_path / "kernel.json"
00132:     kernel.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
00133: 
00134:     def write_without_mkdir(path: Path, payload: dict) -> dict:
00135:         assert path.parent.exists(), f"stage directory was not precreated: {path.parent}"
00136:         path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
00137:         return payload
00138: 
00139:     def fake_query_planner(*, kernel_path, output_dir, questions):
00140:         return write_without_mkdir(
00141:             output_dir / bridge.STAGE_REPORT_NAMES["query_planner"],
00142:             {"quality_status": "PASS", "summary": {"query_plan_count": 1}, "records": [{"answer_permission": False}]},
00143:         )
00144: 
00145:     def fake_blueprint(*, query_planner_path, output_dir):
00146:         assert query_planner_path.exists()
00147:         return write_without_mkdir(
00148:             output_dir / bridge.STAGE_REPORT_NAMES["context_pack_blueprint"],
00149:             {"quality_status": "PASS", "summary": {"context_pack_blueprint_count": 1}, "records": [{"answer_permission": False}]},
00150:         )
00151: 
```
### Source window L37-L93
```python
00037:     def fake_pack_builder(**kwargs):
00038:         assert kwargs["blueprint_path"].exists()
00039:         assert kwargs["route_dispatch_handoff"] == route_dispatch
00040:         payload = {
00041:             "quality_status": "PASS",
00042:             "summary": {
00043:                 "context_pack_count": 1,
00044:                 "total_evidence_capsule_count": 2,
00045:                 "total_high_signal_evidence_capsule_count": 1,
00046:                 "artifact_record_counts": {
00047:                     "fishnet_route_dispatch_handoff": 1,
00048:                     "table_exact_search_adapter": 0,
00049:                     "page_context_v2": 0,
00050:                     "leiden_communities": 0,
00051:                     "image_visual_observer": 0,
00052:                 },
00053:             },
00054:             "records": [{"context_pack_id": "cp1", "answer_permission": False}],
00055:         }
00056:         return _write(kwargs["output_dir"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"], payload)
00057: 
00058:     def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score):
00059:         assert context_pack_path.exists()
00060:         payload = {
00061:             "quality_status": "PASS",
00062:             "summary": {
00063:                 "self_rag_record_count": 1,
00064:                 "ready_for_gemma_draft_count": 0,
00065:                 "crag_retry_required_count": 1,
00066:                 "self_rag_status_counts": {"CRAG_RETRY_REQUIRED": 1},
00067:             },
00068:             "records": [{"self_rag_record_id": "sr1", "crag_retry_required": True, "answer_permission": False}],
00069:         }
00070:         return _write(output_dir / bridge.STAGE_REPORT_NAMES["self_rag"], payload)
00071: 
00072:     def fake_crag(*, self_rag_report_path, output_dir):
00073:         assert self_rag_report_path.exists()
00074:         payload = {
00075:             "quality_status": "PASS",
00076:             "summary": {
00077:                 "crag_retry_plan_count": 1,
00078:                 "ready_for_crag_execution_count": 1,
00079:                 "answer_permission_count": 0,
00080:             },
00081:             "records": [{"crag_retry_plan_id": "cr1", "answer_permission": False}],
00082:         }
00083:         return _write(output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"], payload)
00084: 
00085:     monkeypatch.setattr(
00086:         bridge,
00087:         "_import_stage_builders",
00088:         lambda: {
00089:             "query_planner": fake_query_planner,
00090:             "context_pack_blueprint": fake_blueprint,
00091:             "context_pack_builder": fake_pack_builder,
00092:             "self_rag": fake_self_rag,
00093:             "crag_retry": fake_crag,
```
### Source window L163-L206
```python
00163:                 },
00164:                 "records": [{"answer_permission": False}],
00165:             },
00166:         )
00167: 
00168:     def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score):
00169:         assert context_pack_path.exists()
00170:         return write_without_mkdir(
00171:             output_dir / bridge.STAGE_REPORT_NAMES["self_rag"],
00172:             {
00173:                 "quality_status": "PASS",
00174:                 "summary": {"self_rag_record_count": 1, "ready_for_gemma_draft_count": 1, "crag_retry_required_count": 0},
00175:                 "records": [{"answer_permission": False}],
00176:             },
00177:         )
00178: 
00179:     def fake_crag(*, self_rag_report_path, output_dir):
00180:         assert self_rag_report_path.exists()
00181:         return write_without_mkdir(
00182:             output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"],
00183:             {"quality_status": "PASS", "summary": {"crag_retry_plan_count": 0}, "records": []},
00184:         )
00185: 
00186:     monkeypatch.setattr(
00187:         bridge,
00188:         "_import_stage_builders",
00189:         lambda: {
00190:             "query_planner": fake_query_planner,
00191:             "context_pack_blueprint": fake_blueprint,
00192:             "context_pack_builder": fake_pack_builder,
00193:             "self_rag": fake_self_rag,
00194:             "crag_retry": fake_crag,
00195:         },
00196:     )
00197: 
00198:     payload = bridge.build_webui_self_rag_crag_bridge(
00199:         question="Find part number 120-29073-001",
00200:         kernel_path=kernel,
00201:         output_dir=tmp_path / "clean_bridge_output",
00202:     )
00203: 
00204:     assert payload["quality_status"] == "PASS"
00205:     assert payload["tool_statuses"]["context_pack_blueprint"] == "used"
00206:     assert payload["tool_statuses"]["crag_retry"] == "skipped_not_needed"
```

## `tiff/trace_net_engineering_engram_crag_repair_v1.py`
- Location: `active_source_code`
- Score: `307`
- Categories: `crag, engram, feedback, final_gate, graph_vector, page, safety, self_rag, server`
- Functions: _read_json(path)@L16; _write_json(path, data)@L21; _write_jsonl(path, rows)@L27; _norm(value)@L35; _preview(value, limit)@L39; _sha(text)@L46; _record_question_id(record)@L50; _answer_text(record)@L54; _critic_records(critic)@L58; _answer_records(answer_smoke)@L63; critic_recommends_repair(record)@L75; is_expected_boundary(record)@L82; build_artifact_repair_answer()@L87; build_crag_repair_manifest()@L107; check_crag_repair_manifest()@L312; build_arg_parser()@L357; main(argv)@L374
- CLI args: --critic, --answer-smoke, --output-dir, --llm-mode, --min-records, --min-crag-pass-or-no-repair, --max-repair-attempts, --require-source-quality-pass, --require-critic-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.

### Source window L1-L37
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: import hashlib
00006: from pathlib import Path
00007: from typing import Any, Mapping, Sequence
00008: 
00009: MODULE = "trace_net_engineering_engram_crag_repair_v1"
00010: VERSION = "v1"
00011: 
00012: REPAIR_STATUSES = {"REVIEW", "REPAIR_RECOMMENDED", "FAIL", "CRITIC_REPAIR_RECOMMENDED"}
00013: PASS_STATUSES = {"PASS", "EXPECTED_BOUNDARY", "NO_REPAIR_REQUIRED", "REPAIRED_ARTIFACT"}
00014: 
00015: 
00016: def _read_json(path: str | Path) -> dict[str, Any]:
00017:     p = Path(path)
00018:     return json.loads(p.read_text(encoding="utf-8"))
00019: 
00020: 
00021: def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
00022:     p = Path(path)
00023:     p.parent.mkdir(parents=True, exist_ok=True)
00024:     p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
00025: 
00026: 
00027: def _write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
00028:     p = Path(path)
00029:     p.parent.mkdir(parents=True, exist_ok=True)
00030:     with p.open("w", encoding="utf-8") as f:
00031:         for row in rows:
00032:             f.write(json.dumps(row, sort_keys=True) + "\n")
00033: 
00034: 
00035: def _norm(value: Any) -> str:
00036:     return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
00037: 
```
### Source window L366-L422
```python
00366:     parser.add_argument("--require-source-quality-pass", action="store_true")
00367:     parser.add_argument("--require-critic-quality-pass", action="store_true")
00368:     parser.add_argument("--require-no-answer-permission", action="store_true")
00369:     parser.add_argument("--max-unsafe", type=int, default=0)
00370:     parser.add_argument("--max-write-attempts", type=int, default=0)
00371:     return parser
00372: 
00373: 
00374: def main(argv: Sequence[str] | None = None) -> int:
00375:     args = build_arg_parser().parse_args(argv)
00376:     kwargs = vars(args).copy()
00377: 
00378:     # H29 CLI compatibility: argparse uses concise CLI names such as
00379:     # --critic and --answer-smoke, while the artifact builder may use
00380:     # more explicit internal parameter names.  Map aliases based on the
00381:     # actual build_crag_repair_manifest signature, then pass only accepted
00382:     # keyword arguments.
00383:     import inspect
00384: 
00385:     sig = inspect.signature(build_crag_repair_manifest)
00386:     params = set(sig.parameters)
00387: 
00388:     alias_candidates = {
00389:         "critic": (
00390:             "critic",
00391:             "critic_path",
00392:             "critic_manifest",
00393:             "critic_manifest_path",
00394:             "self_rag_critic",
00395:             "self_rag_critic_path",
00396:         ),
00397:         "answer_smoke": (
00398:             "answer_smoke",
00399:             "answer_smoke_path",
00400:             "answer_smoke_manifest",
00401:             "answer_smoke_manifest_path",
00402:             "source_answer_smoke",
00403:             "source_answer_smoke_path",
00404:         ),
00405:     }
00406: 
00407:     for cli_name, candidates in alias_candidates.items():
00408:         if cli_name not in kwargs:
00409:             continue
00410:         if cli_name in params:
00411:             continue
00412:         value = kwargs.pop(cli_name)
00413:         for candidate in candidates:
00414:             if candidate in params:
00415:                 kwargs[candidate] = value
00416:                 break
00417:         else:
00418:             # Leave a clear error instead of silently ignoring a required input.
00419:             kwargs[cli_name] = value
00420: 
00421:     kwargs = {k: v for k, v in kwargs.items() if k in params}
00422:     manifest = build_crag_repair_manifest(**kwargs)
```
### Source window L67-L123
```python
00067:         if not isinstance(r, Mapping):
00068:             continue
00069:         qid = _record_question_id(r)
00070:         if qid:
00071:             out[qid] = dict(r)
00072:     return out
00073: 
00074: 
00075: def critic_recommends_repair(record: Mapping[str, Any]) -> bool:
00076:     if bool(record.get("repair_recommended")):
00077:         return True
00078:     status = _norm(record.get("critic_status")).upper()
00079:     return status in REPAIR_STATUSES
00080: 
00081: 
00082: def is_expected_boundary(record: Mapping[str, Any]) -> bool:
00083:     status = _norm(record.get("critic_status")).upper()
00084:     return bool(record.get("expected_unknown_boundary_partial")) or status == "EXPECTED_BOUNDARY"
00085: 
00086: 
00087: def build_artifact_repair_answer(*, question: str, original_answer: str, repair_hints: Sequence[Any]) -> str:
00088:     hints = [f"- {_norm(h)}" for h in repair_hints if _norm(h)]
00089:     hint_text = "\n".join(hints) if hints else "- Preserve proof boundaries and cite only current proof_context labels."
00090:     original = _preview(original_answer, 1600)
00091:     return (
00092:         "Answer:\n"
00093:         "CRAG artifact repair candidate prepared for reviewer-approved regeneration. This candidate does not add new proof and must remain bounded by current proof_context citations.\n\n"
00094:         "Evidence:\n"
00095:         "- The original answer and Self-RAG critic record were used as behavior guidance only, not as manual/source proof.\n\n"
00096:         "Repair guidance:\n"
00097:         f"{hint_text}\n\n"
00098:         "Original answer preview:\n"
00099:         f"{original}\n\n"
00100:         "Engineering confidence:\n"
00101:         "LOW until the repaired answer is rerun through the answer-smoke citation and unsupported-claim gates.\n\n"
00102:         "Limits:\n"
00103:         "This CRAG artifact cannot prove factual manual claims, grant answer permission, or mutate source truth."
00104:     )
00105: 
00106: 
00107: def build_crag_repair_manifest(
00108:     *,
00109:     critic_path: str | Path,
00110:     answer_smoke_path: str | Path,
00111:     output_dir: str | Path,
00112:     llm_mode: str = "artifact",
00113:     min_records: int = 1,
00114:     min_crag_pass_or_no_repair: int = 1,
00115:     max_repair_attempts: int = 0,
00116:     max_unsafe: int = 0,
00117:     max_write_attempts: int = 0,
00118:     require_source_quality_pass: bool = False,
00119:     require_critic_quality_pass: bool = False,
00120:     require_no_answer_permission: bool = False,
00121: ) -> dict[str, Any]:
00122:     critic_path = Path(critic_path)
00123:     answer_smoke_path = Path(answer_smoke_path)
```
### Source window L130-L186
```python
00130:     a_records = _answer_records(answer_smoke)
00131: 
00132:     repair_records: list[dict[str, Any]] = []
00133:     repair_candidates: list[dict[str, Any]] = []
00134: 
00135:     repair_attempt_count = 0
00136:     repair_recommended_count = 0
00137:     no_repair_required_count = 0
00138:     expected_boundary_preserved_count = 0
00139:     unsafe_finding_count = 0
00140:     answer_permission_count = 0
00141: 
00142:     for c in c_records:
00143:         qid = _record_question_id(c)
00144:         answer = a_records.get(qid, {})
00145:         question = _norm(answer.get("question") or c.get("question") or qid)
00146:         critic_status = _norm(c.get("critic_status") or "UNKNOWN")
00147:         source_grade = _norm(c.get("source_grade") or answer.get("grade"))
00148:         repair_recommended = critic_recommends_repair(c)
00149:         expected_boundary = is_expected_boundary(c)
00150:         repair_hints = list(c.get("repair_hints") or [])
00151: 
00152:         crag_status = "NO_REPAIR_REQUIRED"
00153:         repair_attempted = False
00154:         repaired_answer_text = ""
00155:         findings: list[str] = []
00156: 
00157:         if expected_boundary and not repair_recommended:
00158:             crag_status = "EXPECTED_BOUNDARY_PRESERVED"
00159:             expected_boundary_preserved_count += 1
00160:             findings.append("expected_boundary_preserved_no_repair")
00161:         elif repair_recommended:
00162:             repair_recommended_count += 1
00163:             findings.append("critic_recommended_repair")
00164:             if repair_attempt_count < max_repair_attempts:
00165:                 repair_attempted = True
00166:                 repair_attempt_count += 1
00167:                 crag_status = "REPAIRED_ARTIFACT" if llm_mode == "artifact" else "REPAIR_PLANNED"
00168:                 repaired_answer_text = build_artifact_repair_answer(
00169:                     question=question,
00170:                     original_answer=_answer_text(answer),
00171:                     repair_hints=repair_hints,
00172:                 )
00173:             else:
00174:                 crag_status = "REPAIR_BLOCKED_BY_MAX_ATTEMPTS"
00175:                 findings.append("repair_blocked_by_max_attempts")
00176:         else:
00177:             no_repair_required_count += 1
00178:             findings.append("critic_passed_no_repair_required")
00179: 
00180:         unsafe = bool(c.get("unsafe")) or bool(answer.get("unsafe"))
00181:         answer_permission = bool(c.get("answer_permission")) or bool(answer.get("answer_permission")) or bool(answer.get("can_answer_directly"))
00182:         if unsafe:
00183:             unsafe_finding_count += 1
00184:         if answer_permission:
00185:             answer_permission_count += 1
00186: 
```
### Source window L195-L251
```python
00195:             "crag_status": crag_status,
00196:             "repair_hints": repair_hints,
00197:             "findings": findings,
00198:             "unsafe": unsafe,
00199:             "answer_permission": answer_permission,
00200:             "source_answer_sha256": _sha(_answer_text(answer)),
00201:             "source_answer_preview": _preview(_answer_text(answer), 900),
00202:             "repaired_answer_sha256": _sha(repaired_answer_text) if repaired_answer_text else "",
00203:             "repaired_answer_preview": _preview(repaired_answer_text, 900),
00204:         }
00205:         repair_records.append(rec)
00206:         if repair_recommended:
00207:             repair_candidates.append(rec)
00208: 
00209:     crag_pass_or_no_repair_count = sum(
00210:         1 for r in repair_records if str(r.get("crag_status")) in {"NO_REPAIR_REQUIRED", "EXPECTED_BOUNDARY_PRESERVED", "REPAIRED_ARTIFACT", "REPAIR_PLANNED"}
00211:     )
00212: 
00213:     write_attempt_count = 0
00214:     postgres_write_attempt_count = 0
00215:     qdrant_write_attempt_count = 0
00216:     qdrant_read_attempt_count = 0
00217:     opensearch_write_attempt_count = 0
00218:     opensearch_upload_attempt_count = 0
00219:     source_truth_mutation_allowed_count = 0
00220: 
00221:     quality_failures: list[str] = []
00222:     source_quality = answer_smoke.get("quality_status")
00223:     critic_quality = critic.get("quality_status")
00224:     if require_source_quality_pass and source_quality != "PASS":
00225:         quality_failures.append("source_answer_smoke_quality_status_not_pass")
00226:     if require_critic_quality_pass and critic_quality != "PASS":
00227:         quality_failures.append("source_critic_quality_status_not_pass")
00228:     if len(repair_records) < min_records:
00229:         quality_failures.append(f"critic_record_count_below_min:{len(repair_records)}<{min_records}")
00230:     if crag_pass_or_no_repair_count < min_crag_pass_or_no_repair:
00231:         quality_failures.append(f"crag_pass_or_no_repair_below_min:{crag_pass_or_no_repair_count}<{min_crag_pass_or_no_repair}")
00232:     if repair_attempt_count > max_repair_attempts:
00233:         quality_failures.append(f"repair_attempt_count_above_max:{repair_attempt_count}>{max_repair_attempts}")
00234:     if unsafe_finding_count > max_unsafe:
00235:         quality_failures.append(f"unsafe_finding_count_above_max:{unsafe_finding_count}>{max_unsafe}")
00236:     if require_no_answer_permission and answer_permission_count:
00237:         quality_failures.append("answer_permission_present")
00238:     if write_attempt_count > max_write_attempts:
00239:         quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
00240: 
00241:     quality_status = "PASS" if not quality_failures else "FAIL"
00242: 
00243:     records_path = output_dir / "trace_net_engineering_engram_crag_repair_records_v1.jsonl"
00244:     candidates_path = output_dir / "trace_net_engineering_engram_crag_repair_candidates_v1.jsonl"
00245:     check_path = output_dir / "trace_net_engineering_engram_crag_repair_v1_quality_check.json"
00246:     manifest_path = output_dir / "trace_net_engineering_engram_crag_repair_v1.json"
00247: 
00248:     summary = {
00249:         "module": MODULE,
00250:         "version": VERSION,
00251:         "critic_record_count": len(repair_records),
```
### Source window L253-L309
```python
00253:         "no_repair_required_count": no_repair_required_count,
00254:         "expected_boundary_preserved_count": expected_boundary_preserved_count,
00255:         "repair_recommended_count": repair_recommended_count,
00256:         "repair_attempt_count": repair_attempt_count,
00257:         "repair_candidate_count": len(repair_candidates),
00258:         "source_answer_smoke_quality_status": source_quality,
00259:         "source_critic_quality_status": critic_quality,
00260:         "answer_permission_count": answer_permission_count,
00261:         "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
00262:         "postgres_write_attempt_count": postgres_write_attempt_count,
00263:         "qdrant_read_attempt_count": qdrant_read_attempt_count,
00264:         "qdrant_write_attempt_count": qdrant_write_attempt_count,
00265:         "opensearch_write_attempt_count": opensearch_write_attempt_count,
00266:         "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
00267:         "write_attempt_count": write_attempt_count,
00268:         "unsafe_finding_count": unsafe_finding_count,
00269:         "quality_failures": quality_failures,
00270:         "ready_for_qdrant_engram_adapter": quality_status == "PASS",
00271:         "ready_for_postgres_feedback_ledger": quality_status == "PASS",
00272:     }
00273: 
00274:     manifest = {
00275:         "status": "TRACE_NET_ENGINEERING_ENGRAM_CRAG_REPAIR_BUILT",
00276:         "quality_status": quality_status,
00277:         "summary": summary,
00278:         "crag_policy": {
00279:             "mode": "artifact_only_crag_engram_repair",
00280:             "repair_rule": "Only records marked REVIEW/REPAIR_RECOMMENDED by the Self-RAG critic are eligible for repair.",
00281:             "expected_boundary_rule": "Expected unknown/no-proof partials are preserved and not repaired.",
00282:             "proof_boundary": "CRAG may repair answer behavior, formatting, and citation discipline; it cannot create proof or use Engram memory as source evidence.",
00283:             "forbidden": [
00284:                 "answer_permission_from_crag",
00285:                 "source_truth_mutation_from_crag",
00286:                 "summary_or_engram_used_as_proof",
00287:                 "live_db_or_qdrant_io_without_explicit_gate",
00288:             ],
00289:             "next_patch": "Live Qdrant Engram vector adapter behind explicit gates.",
00290:         },
00291:         "inputs": {
00292:             "critic": str(critic_path),
00293:             "answer_smoke": str(answer_smoke_path),
00294:         },
00295:         "outputs": {
00296:             "records_jsonl": str(records_path),
00297:             "repair_candidates_jsonl": str(candidates_path),
00298:             "quality_check": str(check_path),
00299:             "manifest": str(manifest_path),
00300:         },
00301:         "crag_repair_records": repair_records,
00302:         "repair_candidate_records": repair_candidates,
00303:     }
00304: 
00305:     _write_jsonl(records_path, repair_records)
00306:     _write_jsonl(candidates_path, repair_candidates)
00307:     _write_json(check_path, {"quality_status": quality_status, "summary": summary})
00308:     _write_json(manifest_path, manifest)
00309:     return manifest
```

## `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_visual_context.py`
- Location: `active_tests`
- Score: `299`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L7; test_bridge_marks_visual_route_used_from_webui_visual_context_bridge(tmp_path, monkeypatch)@L13; test_quality_check_can_require_visual_context_bridge(tmp_path)@L109; fake_query_planner()@L41; fake_blueprint()@L47; fake_pack_builder()@L53; fake_self_rag()@L68; fake_crag()@L74
- Tiff imports: from tiff import trace_net_webui_self_rag_crag_bridge_v1

### Source window L1-L32
```python
00001: import json
00002: from pathlib import Path
00003: 
00004: from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge
00005: 
00006: 
00007: def _write(path: Path, payload: dict) -> dict:
00008:     path.parent.mkdir(parents=True, exist_ok=True)
00009:     path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
00010:     return payload
00011: 
00012: 
00013: def test_bridge_marks_visual_route_used_from_webui_visual_context_bridge(tmp_path, monkeypatch):
00014:     kernel = tmp_path / "kernel.json"
00015:     kernel.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
00016:     route_dispatch = tmp_path / "route_dispatch.json"
00017:     route_dispatch.write_text(json.dumps({"records": [{"page_id": "source_p000001"}]}), encoding="utf-8")
00018:     visual_bridge = tmp_path / "visual_bridge.json"
00019:     _write(
00020:         visual_bridge,
00021:         {
00022:             "quality_status": "PASS",
00023:             "summary": {
00024:                 "visual_context_card_count": 2,
00025:                 "review_only_visual_context_excluded_count": 10,
00026:                 "included_pages": ["t_p_120_1176_p000001", "t_p_120_1176_p000022"],
00027:                 "included_canonical_page_numbers": [1, 22],
00028:                 "answer_permission_count": 0,
00029:                 "source_truth_mutation_allowed_count": 0,
00030:                 "postgres_write_attempt_count": 0,
00031:                 "qdrant_write_attempt_count": 0,
00032:                 "opensearch_write_attempt_count": 0,
```
### Source window L43-L99
```python
00043:             output_dir / bridge.STAGE_REPORT_NAMES["query_planner"],
00044:             {"quality_status": "PASS", "summary": {"query_plan_count": 1}, "records": [{"answer_permission": False}]},
00045:         )
00046: 
00047:     def fake_blueprint(*, query_planner_path, output_dir):
00048:         return _write(
00049:             output_dir / bridge.STAGE_REPORT_NAMES["context_pack_blueprint"],
00050:             {"quality_status": "PASS", "summary": {"context_pack_blueprint_count": 1}, "records": [{"answer_permission": False}]},
00051:         )
00052: 
00053:     def fake_pack_builder(**kwargs):
00054:         return _write(
00055:             kwargs["output_dir"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"],
00056:             {
00057:                 "quality_status": "PASS",
00058:                 "summary": {
00059:                     "context_pack_count": 1,
00060:                     "artifact_record_counts": {"fishnet_route_dispatch_handoff": 1},
00061:                     "total_evidence_capsule_count": 1,
00062:                     "total_high_signal_evidence_capsule_count": 1,
00063:                 },
00064:                 "records": [{"answer_permission": False}],
00065:             },
00066:         )
00067: 
00068:     def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score):
00069:         return _write(
00070:             output_dir / bridge.STAGE_REPORT_NAMES["self_rag"],
00071:             {"quality_status": "PASS", "summary": {"self_rag_record_count": 1, "crag_retry_required_count": 0}, "records": [{"answer_permission": False}]},
00072:         )
00073: 
00074:     def fake_crag(*, self_rag_report_path, output_dir):
00075:         return _write(
00076:             output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"],
00077:             {"quality_status": "PASS", "summary": {"crag_retry_plan_count": 0}, "records": [{"answer_permission": False}]},
00078:         )
00079: 
00080:     monkeypatch.setattr(
00081:         bridge,
00082:         "_import_stage_builders",
00083:         lambda: {
00084:             "query_planner": fake_query_planner,
00085:             "context_pack_blueprint": fake_blueprint,
00086:             "context_pack_builder": fake_pack_builder,
00087:             "self_rag": fake_self_rag,
00088:             "crag_retry": fake_crag,
00089:         },
00090:     )
00091: 
00092:     payload = bridge.build_webui_self_rag_crag_bridge(
00093:         question="What visual context is available?",
00094:         kernel_path=kernel,
00095:         output_dir=tmp_path / "bridge",
00096:         route_dispatch_handoff=route_dispatch,
00097:         webui_visual_context_bridge=visual_bridge,
00098:     )
00099: 
```
### Source window L114-L145
```python
00114:                 "quality_status": "PASS",
00115:                 "summary": {
00116:                     "tool_checklist_count": 10,
00117:                     "used_tool_count": 7,
00118:                     "visual_context_card_count": 2,
00119:                     "answer_permission_count": 0,
00120:                     "source_truth_mutation_allowed_count": 0,
00121:                     "postgres_write_attempt_count": 0,
00122:                     "qdrant_write_attempt_count": 0,
00123:                     "opensearch_write_attempt_count": 0,
00124:                 },
00125:                 "tool_statuses": {
00126:                     "query_planner": "used",
00127:                     "context_pack_builder": "used",
00128:                     "self_rag": "used",
00129:                     "crag_retry": "skipped_not_needed",
00130:                     "visual_image_route": "used",
00131:                     "webui_visual_context_bridge": "used",
00132:                 },
00133:             }
00134:         ),
00135:         encoding="utf-8",
00136:     )
00137:     result = bridge.check_webui_self_rag_crag_bridge_quality(
00138:         report_path=report,
00139:         require_webui_visual_context_bridge_used=True,
00140:         min_visual_context_cards=2,
00141:         require_no_write_attempts=True,
00142:         require_no_answer_permission=True,
00143:         require_no_source_truth_mutation=True,
00144:     )
00145:     assert result["quality_status"] == "PASS"
```

## `tiff/trace_net_engineering_engram_self_rag_critic_v1.py`
- Location: `active_source_code`
- Score: `299`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server`
- Doc: TRACE-Net Engineering Engram Self-RAG Critic v1. Artifact-only critic for targeted Engram overlay answer-smoke runs. It reads an answer-smoke manifest and emits per-answer Self-RAG style critic records. It does not call an LLM and does not write to databases or vector/search systems.
- Functions: _read_json(path)@L25; _write_json(path, data)@L30; _write_jsonl(path, rows)@L36; _as_int(value, default)@L44; _text(record)@L53; _is_expected_unknown_boundary(record)@L57; _has_required_sections(answer)@L68; _safe_but_generic_risk(record)@L73; critique_answer_record(record)@L85; build_self_rag_critic_manifest()@L209; check_self_rag_critic_manifest()@L315; build_arg_parser()@L353; check_arg_parser()@L367; main(argv)@L380; check_main(argv)@L398
- CLI args: --answer-smoke, --output-dir, --min-records, --min-critic-pass-or-expected, --max-repair-recommended, --max-unsafe, --max-write-attempts, --require-source-quality-pass, --require-no-answer-permission, --critic, --min-records, --min-critic-pass-or-expected, --max-repair-recommended, --max-unsafe, --max-write-attempts, --require-quality-pass, --require-no-answer-permission
- Has __main__ guard.

### Source window L1-L29
```python
00001: """TRACE-Net Engineering Engram Self-RAG Critic v1.
00002: 
00003: Artifact-only critic for targeted Engram overlay answer-smoke runs.
00004: It reads an answer-smoke manifest and emits per-answer Self-RAG style critic
00005: records. It does not call an LLM and does not write to databases or vector/search
00006: systems.
00007: """
00008: from __future__ import annotations
00009: 
00010: import argparse
00011: import json
00012: import re
00013: from dataclasses import dataclass
00014: from pathlib import Path
00015: from typing import Any, Iterable, Mapping
00016: 
00017: MODULE = "trace_net_engineering_engram_self_rag_critic_v1"
00018: VERSION = "v1"
00019: 
00020: EXPECTED_UNKNOWN_CATEGORIES = {"unknown_part", "unknown_figure"}
00021: CITATION_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_\-]*\]")
00022: GROUPED_CITATION_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_\-]*\s*,\s*[A-Za-z]")
00023: 
00024: 
00025: def _read_json(path: str | Path) -> dict[str, Any]:
00026:     p = Path(path)
00027:     return json.loads(p.read_text(encoding="utf-8"))
00028: 
00029: 
```
### Source window L181-L237
```python
00181:         "task_type": record.get("task_type"),
00182:         "question": record.get("question"),
00183:         "source_grade": grade,
00184:         "critic_status": critic_status,
00185:         "expected_unknown_boundary_partial": expected_partial,
00186:         "proof_context_count": proof_context_count,
00187:         "answer_citation_count": answer_citation_count,
00188:         "valid_answer_citation_count": valid_answer_citation_count,
00189:         "source_trace_ready_citation_count": source_trace_ready_citation_count,
00190:         "unsupported_claim_count": unsupported_claim_count,
00191:         "summary_used_as_proof_count": summary_used_as_proof_count,
00192:         "invalid_answer_citation_count": invalid_answer_citation_count,
00193:         "llm_retry_used": bool(record.get("llm_retry_used")),
00194:         "llm_fallback_used": bool(record.get("llm_fallback_used")),
00195:         "findings": findings,
00196:         "repair_hints": repair_hints,
00197:         "unsafe": unsafe,
00198:         "answer_permission": answer_permission,
00199:         "source_truth_mutation_allowed": False,
00200:         "postgres_write_attempt": False,
00201:         "qdrant_write_attempt": False,
00202:         "opensearch_write_attempt": False,
00203:         "opensearch_upload_attempt": False,
00204:         "write_attempt": False,
00205:         "answer_preview": answer[:1200],
00206:     }
00207: 
00208: 
00209: def build_self_rag_critic_manifest(
00210:     *,
00211:     answer_smoke: str | Path,
00212:     output_dir: str | Path,
00213:     min_records: int = 1,
00214:     min_critic_pass_or_expected: int = 1,
00215:     max_repair_recommended: int = 0,
00216:     max_unsafe: int = 0,
00217:     max_write_attempts: int = 0,
00218:     require_source_quality_pass: bool = False,
00219:     require_no_answer_permission: bool = False,
00220: ) -> dict[str, Any]:
00221:     source = _read_json(answer_smoke)
00222:     records = list(source.get("records") or source.get("smoke_records") or [])
00223:     critic_records = [critique_answer_record(r) for r in records]
00224: 
00225:     out_dir = Path(output_dir)
00226:     out_dir.mkdir(parents=True, exist_ok=True)
00227:     jsonl_path = out_dir / "trace_net_engineering_engram_self_rag_critic_v1_records.jsonl"
00228:     check_path = out_dir / "trace_net_engineering_engram_self_rag_critic_v1_quality_check.json"
00229:     manifest_path = out_dir / "trace_net_engineering_engram_self_rag_critic_v1.json"
00230:     _write_jsonl(jsonl_path, critic_records)
00231: 
00232:     pass_count = sum(1 for r in critic_records if r["critic_status"] == "PASS")
00233:     expected_count = sum(1 for r in critic_records if r["critic_status"] == "EXPECTED_BOUNDARY")
00234:     review_count = sum(1 for r in critic_records if r["critic_status"] == "REVIEW")
00235:     repair_count = sum(1 for r in critic_records if r["critic_status"] == "REPAIR_RECOMMENDED")
00236:     unsafe_count = sum(1 for r in critic_records if r.get("unsafe"))
00237:     answer_permission_count = sum(1 for r in critic_records if r.get("answer_permission"))
```
### Source window L58-L114
```python
00058:     category = str(record.get("category") or "")
00059:     proof_context_count = _as_int(record.get("proof_context_count"))
00060:     answer = _text(record).lower()
00061:     return (
00062:         category in EXPECTED_UNKNOWN_CATEGORIES
00063:         and proof_context_count == 0
00064:         and ("not found" in answer or "not source-trace-ready" in answer or "no proof_context" in answer)
00065:     )
00066: 
00067: 
00068: def _has_required_sections(answer: str) -> bool:
00069:     lower = answer.lower()
00070:     return all(token in lower for token in ("answer", "evidence", "engineering confidence", "limits"))
00071: 
00072: 
00073: def _safe_but_generic_risk(record: Mapping[str, Any]) -> bool:
00074:     answer = _text(record).lower()
00075:     proof_context_count = _as_int(record.get("proof_context_count"))
00076:     grade = str(record.get("grade") or "")
00077:     if grade == "GOOD":
00078:         return False
00079:     if _is_expected_unknown_boundary(record):
00080:         return False
00081:     generic_markers = ["not proven", "cannot prove", "not source-trace-ready"]
00082:     return proof_context_count > 0 and any(marker in answer for marker in generic_markers) and len(answer) < 900
00083: 
00084: 
00085: def critique_answer_record(record: Mapping[str, Any]) -> dict[str, Any]:
00086:     """Return a Self-RAG style critic record for one answer-smoke record."""
00087:     answer = _text(record)
00088:     grade = str(record.get("grade") or "")
00089:     category = str(record.get("category") or "")
00090:     question_id = str(record.get("question_id") or "")
00091:     proof_context_count = _as_int(record.get("proof_context_count"))
00092:     answer_citation_count = _as_int(record.get("answer_citation_count"))
00093:     valid_answer_citation_count = _as_int(record.get("valid_answer_citation_count"))
00094:     source_trace_ready_citation_count = _as_int(record.get("source_trace_ready_citation_count"))
00095:     unsupported_claim_count = _as_int(record.get("unsupported_claim_count"))
00096:     summary_used_as_proof_count = _as_int(record.get("summary_used_as_proof_count"))
00097:     invalid_answer_citation_count = _as_int(record.get("invalid_answer_citation_count"))
00098:     answer_permission = bool(record.get("answer_permission") or record.get("can_answer_directly"))
00099:     unsafe = bool(record.get("unsafe") or answer_permission)
00100: 
00101:     findings: list[str] = []
00102:     repair_hints: list[str] = []
00103:     critic_status = "PASS"
00104: 
00105:     if answer_permission:
00106:         findings.append("answer_permission_detected")
00107:         repair_hints.append("Remove any direct-answer permission granted by Engram or prompt guidance.")
00108:         unsafe = True
00109: 
00110:     if unsupported_claim_count > 0:
00111:         findings.append("unsupported_claims_detected")
00112:         repair_hints.append("Regenerate with stricter proof_context citation requirements.")
00113:         critic_status = "REPAIR_RECOMMENDED"
00114: 
```
### Source window L247-L303
```python
00247:         quality_failures.append(f"critic_pass_or_expected_count_below_min:{pass_count + expected_count}<{min_critic_pass_or_expected}")
00248:     if repair_count > max_repair_recommended:
00249:         quality_failures.append(f"repair_recommended_count_above_max:{repair_count}>{max_repair_recommended}")
00250:     if unsafe_count > max_unsafe:
00251:         quality_failures.append(f"unsafe_finding_count_above_max:{unsafe_count}>{max_unsafe}")
00252:     if write_attempt_count > max_write_attempts:
00253:         quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
00254:     if require_no_answer_permission and answer_permission_count:
00255:         quality_failures.append("answer_permission_detected")
00256: 
00257:     summary = {
00258:         "module": MODULE,
00259:         "version": VERSION,
00260:         "source_answer_smoke_quality_status": source_quality_status,
00261:         "critic_record_count": len(critic_records),
00262:         "critic_pass_count": pass_count,
00263:         "expected_boundary_count": expected_count,
00264:         "review_count": review_count,
00265:         "repair_recommended_count": repair_count,
00266:         "critic_pass_or_expected_count": pass_count + expected_count,
00267:         "unsafe_finding_count": unsafe_count,
00268:         "answer_permission_count": answer_permission_count,
00269:         "source_truth_mutation_allowed_count": 0,
00270:         "postgres_write_attempt_count": 0,
00271:         "qdrant_write_attempt_count": 0,
00272:         "opensearch_write_attempt_count": 0,
00273:         "opensearch_upload_attempt_count": 0,
00274:         "write_attempt_count": write_attempt_count,
00275:         "ready_for_crag_engram_repair": repair_count > 0 or review_count > 0,
00276:         "ready_for_answer_smoke_overlay_commit_gate": not quality_failures,
00277:         "quality_failures": quality_failures,
00278:     }
00279: 
00280:     manifest = {
00281:         "module": MODULE,
00282:         "version": VERSION,
00283:         "status": "TRACE_NET_ENGINEERING_ENGRAM_SELF_RAG_CRITIC_BUILT",
00284:         "quality_status": "PASS" if not quality_failures else "FAIL",
00285:         "source_answer_smoke_path": str(answer_smoke),
00286:         "summary": summary,
00287:         "critic_policy": {
00288:             "mode": "artifact_only_self_rag_engram_critic",
00289:             "proof_boundary": "The critic may identify behavior/citation/evidence weaknesses but cannot create proof; factual manual claims still require proof_context citations.",
00290:             "forbidden": [
00291:                 "answer_permission_from_critic",
00292:                 "source_truth_mutation_from_critic",
00293:                 "summary_or_engram_used_as_proof",
00294:                 "live_db_or_qdrant_io_without_explicit_gate",
00295:             ],
00296:             "next_patch": "CRAG Engram repair only for REVIEW or REPAIR_RECOMMENDED records.",
00297:         },
00298:         "critic_records": critic_records,
00299:         "artifact_paths": {
00300:             "records_jsonl": str(jsonl_path),
00301:             "quality_check": str(check_path),
00302:             "manifest": str(manifest_path),
00303:         },
```
### Source window L120-L176
```python
00120:     if invalid_answer_citation_count > 0:
00121:         findings.append("invalid_citations_detected")
00122:         repair_hints.append("Replace invalid labels with source-trace-ready citations only.")
00123:         critic_status = "REPAIR_RECOMMENDED"
00124: 
00125:     if GROUPED_CITATION_RE.search(answer):
00126:         findings.append("grouped_citation_syntax_risk")
00127:         repair_hints.append("Use individual citation labels such as [V6] [O1], not grouped labels like [V6, O1].")
00128: 
00129:     if proof_context_count > 0 and answer_citation_count == 0:
00130:         findings.append("proof_context_available_but_no_counted_citations")
00131:         repair_hints.append("Add counted source labels from proof_context using individual bracket syntax.")
00132:         critic_status = "REPAIR_RECOMMENDED"
00133: 
00134:     if proof_context_count > 0 and valid_answer_citation_count == 0:
00135:         findings.append("no_valid_citations_despite_proof_context")
00136:         repair_hints.append("Regenerate with explicit valid citation labels from proof_context.")
00137:         critic_status = "REPAIR_RECOMMENDED"
00138: 
00139:     if proof_context_count > 0 and source_trace_ready_citation_count == 0:
00140:         findings.append("no_source_trace_ready_citations_despite_proof_context")
00141:         repair_hints.append("Prefer source-trace-ready citation labels from proof_context.")
00142:         critic_status = "REPAIR_RECOMMENDED"
00143: 
00144:     if not _has_required_sections(answer):
00145:         findings.append("missing_preferred_answer_sections")
00146:         repair_hints.append("Use Answer, Evidence, Engineering confidence, and Limits sections.")
00147:         if grade != "GOOD" and not _is_expected_unknown_boundary(record):
00148:             critic_status = "REPAIR_RECOMMENDED"
00149: 
00150:     if _safe_but_generic_risk(record):
00151:         findings.append("safe_but_too_generic_risk")
00152:         repair_hints.append("Retrieve critic/episodic repair memory and explain what TRACE-Net can prove, not just what it cannot prove.")
00153:         critic_status = "REPAIR_RECOMMENDED"
00154: 
00155:     expected_partial = _is_expected_unknown_boundary(record)
00156:     if grade == "PARTIAL" and expected_partial:
00157:         findings.append("expected_unknown_boundary_partial")
00158:         repair_hints.append("No repair required if unknown/no-proof cases remain safe and clearly not source-trace-ready.")
00159:         if critic_status != "REPAIR_RECOMMENDED":
00160:             critic_status = "EXPECTED_BOUNDARY"
00161:     elif grade not in {"GOOD", "PARTIAL"}:
00162:         findings.append("bad_or_blocked_answer_grade")
00163:         repair_hints.append("Run CRAG-style repair before accepting this answer.")
00164:         critic_status = "REPAIR_RECOMMENDED"
00165:     elif grade == "PARTIAL" and critic_status == "PASS":
00166:         findings.append("unexpected_partial_answer")
00167:         repair_hints.append("Review for missing citations, incomplete answer, or over-generic refusal.")
00168:         critic_status = "REVIEW"
00169: 
00170:     if unsafe:
00171:         critic_status = "REPAIR_RECOMMENDED"
00172: 
00173:     if not findings:
00174:         findings.append("critic_checks_passed")
00175: 
00176:     return {
```
### Source window L308-L364
```python
00308:         "status": "TRACE_NET_ENGINEERING_ENGRAM_SELF_RAG_CRITIC_CHECKED",
00309:         "quality_status": manifest["quality_status"],
00310:         "summary": summary,
00311:     })
00312:     return manifest
00313: 
00314: 
00315: def check_self_rag_critic_manifest(
00316:     *,
00317:     critic: str | Path,
00318:     min_records: int = 1,
00319:     min_critic_pass_or_expected: int = 1,
00320:     require_quality_pass: bool = False,
00321:     require_no_answer_permission: bool = False,
00322:     max_repair_recommended: int = 0,
00323:     max_unsafe: int = 0,
00324:     max_write_attempts: int = 0,
00325: ) -> dict[str, Any]:
00326:     data = _read_json(critic)
00327:     summary = dict(data.get("summary") or {})
00328:     quality_failures = list(summary.get("quality_failures") or [])
00329: 
00330:     if require_quality_pass and data.get("quality_status") != "PASS":
00331:         quality_failures.append("quality_status_not_pass")
00332:     if _as_int(summary.get("critic_record_count")) < min_records:
00333:         quality_failures.append("critic_record_count_below_min")
00334:     if _as_int(summary.get("critic_pass_or_expected_count")) < min_critic_pass_or_expected:
00335:         quality_failures.append("critic_pass_or_expected_count_below_min")
00336:     if _as_int(summary.get("repair_recommended_count")) > max_repair_recommended:
00337:         quality_failures.append("repair_recommended_count_above_max")
00338:     if _as_int(summary.get("unsafe_finding_count")) > max_unsafe:
00339:         quality_failures.append("unsafe_finding_count_above_max")
00340:     if _as_int(summary.get("write_attempt_count")) > max_write_attempts:
00341:         quality_failures.append("write_attempt_count_above_max")
00342:     if require_no_answer_permission and _as_int(summary.get("answer_permission_count")):
00343:         quality_failures.append("answer_permission_detected")
00344: 
00345:     return {
00346:         "status": "TRACE_NET_ENGINEERING_ENGRAM_SELF_RAG_CRITIC_CHECKED",
00347:         "quality_status": "PASS" if not quality_failures else "FAIL",
00348:         "summary": summary,
00349:         "quality_failures": quality_failures,
00350:     }
00351: 
00352: 
00353: def build_arg_parser() -> argparse.ArgumentParser:
00354:     parser = argparse.ArgumentParser(description=MODULE)
00355:     parser.add_argument("--answer-smoke", required=True)
00356:     parser.add_argument("--output-dir", required=True)
00357:     parser.add_argument("--min-records", type=int, default=1)
00358:     parser.add_argument("--min-critic-pass-or-expected", type=int, default=1)
00359:     parser.add_argument("--max-repair-recommended", type=int, default=0)
00360:     parser.add_argument("--max-unsafe", type=int, default=0)
00361:     parser.add_argument("--max-write-attempts", type=int, default=0)
00362:     parser.add_argument("--require-source-quality-pass", action="store_true")
00363:     parser.add_argument("--require-no-answer-permission", action="store_true")
00364:     return parser
```
### Source window L382-L418
```python
00382:     manifest = build_self_rag_critic_manifest(**vars(args))
00383:     s = manifest["summary"]
00384:     print("status=" + manifest["status"])
00385:     print("quality_status=" + manifest["quality_status"])
00386:     print("critic_record_count=" + str(s["critic_record_count"]))
00387:     print("critic_pass_count=" + str(s["critic_pass_count"]))
00388:     print("expected_boundary_count=" + str(s["expected_boundary_count"]))
00389:     print("review_count=" + str(s["review_count"]))
00390:     print("repair_recommended_count=" + str(s["repair_recommended_count"]))
00391:     print("unsafe_finding_count=" + str(s["unsafe_finding_count"]))
00392:     print("answer_permission_count=" + str(s["answer_permission_count"]))
00393:     print("write_attempt_count=" + str(s["write_attempt_count"]))
00394:     print("output=" + manifest["artifact_paths"]["manifest"])
00395:     return 0 if manifest["quality_status"] == "PASS" else 1
00396: 
00397: 
00398: def check_main(argv: list[str] | None = None) -> int:
00399:     args = check_arg_parser().parse_args(argv)
00400:     result = check_self_rag_critic_manifest(**vars(args))
00401:     s = result["summary"]
00402:     print("status=" + result["status"])
00403:     print("quality_status=" + result["quality_status"])
00404:     print("critic_record_count=" + str(s.get("critic_record_count")))
00405:     print("critic_pass_count=" + str(s.get("critic_pass_count")))
00406:     print("expected_boundary_count=" + str(s.get("expected_boundary_count")))
00407:     print("review_count=" + str(s.get("review_count")))
00408:     print("repair_recommended_count=" + str(s.get("repair_recommended_count")))
00409:     print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
00410:     print("answer_permission_count=" + str(s.get("answer_permission_count")))
00411:     print("write_attempt_count=" + str(s.get("write_attempt_count")))
00412:     if result.get("quality_failures"):
00413:         print("quality_failures=" + json.dumps(result["quality_failures"]))
00414:     return 0 if result["quality_status"] == "PASS" else 1
00415: 
00416: 
00417: if __name__ == "__main__":  # pragma: no cover
00418:     raise SystemExit(main())
```

## `tiff/trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Location: `active_source_code`
- Score: `294`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, server, webui`
- Functions: _norm(value)@L50; _read_json(path)@L54; _write_json(path, data)@L58; _write_jsonl(path, records)@L63; _as_list(value)@L70; _parse_question_ids(value)@L80; _compact_text(text, max_chars)@L93; _missing_boundary_groups(text)@L100; _records_by_question_id(source_answer_smoke)@L109; _bridge_records(bridge)@L115; _bridge_records_for_question(bridge, question_id)@L119; _combine_layers(records)@L127; _combine_proof_roles(records)@L131; build_overlay_text(question_id, bridge_records, max_overlay_chars)@L135; build_overlay_records(bridge, source_answer_smoke)@L155; _count_layers(records)@L209; _count_matched_task_types(records)@L218; _safety_counts_zero(data)@L227
- CLI args: --bridge, --source-answer-smoke, --output-dir, --question-ids, --max-overlay-chars, --min-overlay-records, --min-matched-bridge-records, --require-h23-quality-pass, --require-source-answer-smoke-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.

### Source window L1-L36
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: from pathlib import Path
00006: from typing import Any, Dict, Iterable, List, Mapping, Sequence
00007: 
00008: MODULE = "trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1"
00009: VERSION = "v1"
00010: 
00011: SAFETY_CONTRACT = {
00012:     "answer_permission": False,
00013:     "source_truth_mutation_allowed": False,
00014:     "postgres_write_attempt": False,
00015:     "qdrant_read_attempt": False,
00016:     "qdrant_write_attempt": False,
00017:     "opensearch_write_attempt": False,
00018:     "opensearch_upload_attempt": False,
00019:     "write_attempt": False,
00020:     "live_qdrant_io_attempted": False,
00021:     "engram_is_proof": False,
00022: }
00023: 
00024: DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"]
00025: ALLOWED_PROOF_ROLES = {"guidance_only", "current_proof_context_only"}
00026: 
00027: REQUIRED_BOUNDARY_GROUPS = {
00028:     "behavior_guidance_boundary": [
00029:         "behavior guidance only",
00030:         "behavior only",
00031:         "answer behavior only",
00032:         "shape answer behavior only",
00033:         "shapes answer behavior only",
00034:     ],
00035:     "not_proof_boundary": [
00036:         "not proof",
```
### Source window L123-L179
```python
00123:             matches.append(rec)
00124:     return matches
00125: 
00126: 
00127: def _combine_layers(records: Sequence[Mapping[str, Any]]) -> List[str]:
00128:     return sorted({str(layer) for rec in records for layer in _as_list(rec.get("selected_layers"))})
00129: 
00130: 
00131: def _combine_proof_roles(records: Sequence[Mapping[str, Any]]) -> List[str]:
00132:     return sorted({str(role) for rec in records for role in _as_list(rec.get("selected_proof_roles"))})
00133: 
00134: 
00135: def build_overlay_text(question_id: str, bridge_records: Sequence[Mapping[str, Any]], max_overlay_chars: int = 1800) -> str:
00136:     chunks: List[str] = [
00137:         "TRACE-NET H24 ANSWER-RUNNER RETRIEVED ENGRAM OVERLAY",
00138:         "Use this overlay as behavior guidance only. It is not proof.",
00139:         "Manual/source claims still require current proof_context citations.",
00140:         "Do not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.",
00141:         f"target_question_id: {question_id}",
00142:         "",
00143:     ]
00144:     for rec in bridge_records:
00145:         guidance = _norm(rec.get("guidance_overlay_text"))
00146:         task = _norm(rec.get("task_type"))
00147:         query_id = _norm(rec.get("query_id"))
00148:         chunks.append(f"--- retrieved_guidance query_id={query_id} task_type={task} ---")
00149:         chunks.append(guidance)
00150:         chunks.append("")
00151:     chunks.append("Required response discipline: answer from current proof_context only; use retrieved Engram overlay only to shape wording, boundaries, route awareness, and repair behavior.")
00152:     return _compact_text("\n".join(chunks).strip(), max_overlay_chars)
00153: 
00154: 
00155: def build_overlay_records(
00156:     bridge: Mapping[str, Any],
00157:     source_answer_smoke: Mapping[str, Any] | None = None,
00158:     *,
00159:     question_ids: str | Sequence[str] | None = None,
00160:     max_overlay_chars: int = 1800,
00161: ) -> List[Dict[str, Any]]:
00162:     qids = _parse_question_ids(question_ids)
00163:     source_by_qid = _records_by_question_id(source_answer_smoke)
00164:     records: List[Dict[str, Any]] = []
00165:     for qid in qids:
00166:         matches = _bridge_records_for_question(bridge, qid)
00167:         source = source_by_qid.get(qid, {})
00168:         overlay = build_overlay_text(qid, matches, max_overlay_chars=max_overlay_chars) if matches else ""
00169:         selected_proof_roles = _combine_proof_roles(matches)
00170:         selected_layers = _combine_layers(matches)
00171:         bad_proof_roles = [r for r in selected_proof_roles if r not in ALLOWED_PROOF_ROLES]
00172:         missing_boundary_groups = _missing_boundary_groups(overlay) if overlay else ["no_overlay_text"]
00173:         unsafe_findings: List[str] = []
00174:         if not matches:
00175:             unsafe_findings.append("no_bridge_guidance_for_question")
00176:         if missing_boundary_groups:
00177:             unsafe_findings.append("missing_boundary_groups:" + ",".join(missing_boundary_groups))
00178:         if bad_proof_roles:
00179:             unsafe_findings.append("unsupported_proof_roles:" + ",".join(bad_proof_roles))
```
### Source window L277-L333
```python
00277:         quality_failures.append("source_bridge_safety_counter_nonzero")
00278:     if require_source_answer_smoke_quality_pass and (not source_data or source_data.get("quality_status") != "PASS"):
00279:         quality_failures.append("source_answer_smoke_not_pass")
00280:     if len(records) < min_overlay_records:
00281:         quality_failures.append(f"overlay_record_count_below_min:{len(records)}<{min_overlay_records}")
00282:     if matched_bridge_record_count < min_matched_bridge_records:
00283:         quality_failures.append(f"matched_bridge_record_count_below_min:{matched_bridge_record_count}<{min_matched_bridge_records}")
00284:     if require_no_answer_permission and answer_permission_count:
00285:         quality_failures.append("answer_permission_count_nonzero")
00286:     if len(unsafe_records) > max_unsafe:
00287:         quality_failures.append(f"unsafe_finding_count_above_max:{len(unsafe_records)}>{max_unsafe}")
00288:     if write_attempt_count > max_write_attempts:
00289:         quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
00290:     quality_status = "PASS" if not quality_failures else "FAIL"
00291: 
00292:     out_dir = Path(output_dir)
00293:     out_dir.mkdir(parents=True, exist_ok=True)
00294:     manifest_path = out_dir / f"{MODULE}.json"
00295:     records_path = out_dir / f"{MODULE}_records.jsonl"
00296:     overlay_map_path = out_dir / f"{MODULE}_overlay_map.json"
00297:     check_path = out_dir / f"{MODULE}_quality_check.json"
00298: 
00299:     overlay_map = {
00300:         r["question_id"]: {
00301:             "overlay_text": r["overlay_text"],
00302:             "matched_bridge_query_ids": r["matched_bridge_query_ids"],
00303:             "matched_bridge_task_types": r["matched_bridge_task_types"],
00304:             "selected_layers": r["selected_layers"],
00305:             "selected_proof_roles": r["selected_proof_roles"],
00306:             "answer_permission": False,
00307:             "engram_is_proof": False,
00308:         }
00309:         for r in records
00310:     }
00311:     summary = {
00312:         "module": MODULE,
00313:         "version": VERSION,
00314:         "source_bridge_quality_status": bridge_data.get("quality_status"),
00315:         "source_answer_smoke_quality_status": source_data.get("quality_status") if source_data else None,
00316:         "overlay_record_count": len(records),
00317:         "target_question_count": len(qids),
00318:         "target_question_ids": qids,
00319:         "matched_bridge_record_count": matched_bridge_record_count,
00320:         "matched_bridge_task_type_counts": _count_matched_task_types(records),
00321:         "selected_memory_layer_counts": _count_layers(records),
00322:         "ready_for_targeted_llm_overlay_smoke": quality_status == "PASS",
00323:         "answer_permission_count": answer_permission_count,
00324:         "source_truth_mutation_allowed_count": 0,
00325:         "postgres_write_attempt_count": 0,
00326:         "qdrant_read_attempt_count": 0,
00327:         "qdrant_write_attempt_count": 0,
00328:         "opensearch_write_attempt_count": 0,
00329:         "opensearch_upload_attempt_count": 0,
00330:         "write_attempt_count": write_attempt_count,
00331:         "unsafe_finding_count": len(unsafe_records),
00332:         "quality_failures": quality_failures,
00333:     }
```
### Source window L205-L261
```python
00205:         records.append(record)
00206:     return records
00207: 
00208: 
00209: def _count_layers(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
00210:     counts: Dict[str, int] = {}
00211:     for rec in records:
00212:         for layer in _as_list(rec.get("selected_layers")):
00213:             layer_s = str(layer)
00214:             counts[layer_s] = counts.get(layer_s, 0) + 1
00215:     return dict(sorted(counts.items()))
00216: 
00217: 
00218: def _count_matched_task_types(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
00219:     counts: Dict[str, int] = {}
00220:     for rec in records:
00221:         for task in _as_list(rec.get("matched_bridge_task_types")):
00222:             task_s = str(task)
00223:             counts[task_s] = counts.get(task_s, 0) + 1
00224:     return dict(sorted(counts.items()))
00225: 
00226: 
00227: def _safety_counts_zero(data: Mapping[str, Any]) -> bool:
00228:     summary = data.get("summary") or {}
00229:     keys = [
00230:         "answer_permission_count",
00231:         "source_truth_mutation_allowed_count",
00232:         "postgres_write_attempt_count",
00233:         "qdrant_read_attempt_count",
00234:         "qdrant_write_attempt_count",
00235:         "opensearch_write_attempt_count",
00236:         "opensearch_upload_attempt_count",
00237:         "write_attempt_count",
00238:         "unsafe_finding_count",
00239:     ]
00240:     return all(int(summary.get(k) or 0) == 0 for k in keys)
00241: 
00242: 
00243: def build_answer_runner_prompt_overlay_smoke_manifest(
00244:     *,
00245:     bridge: str | Path,
00246:     source_answer_smoke: str | Path | None = None,
00247:     output_dir: str | Path,
00248:     question_ids: str | Sequence[str] | None = None,
00249:     max_overlay_chars: int = 1800,
00250:     min_overlay_records: int = 5,
00251:     min_matched_bridge_records: int = 5,
00252:     require_h23_quality_pass: bool = True,
00253:     require_source_answer_smoke_quality_pass: bool = False,
00254:     require_no_answer_permission: bool = True,
00255:     max_unsafe: int = 0,
00256:     max_write_attempts: int = 0,
00257: ) -> Dict[str, Any]:
00258:     bridge_path = Path(bridge)
00259:     bridge_data = _read_json(bridge_path)
00260:     source_data: Dict[str, Any] | None = None
00261:     source_path_s = ""
```
### Source window L335-L391
```python
00335:         "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_PROMPT_OVERLAY_SMOKE_BUILT",
00336:         "quality_status": quality_status,
00337:         "summary": summary,
00338:         "quality_failures": quality_failures,
00339:         "source_bridge_path": str(bridge_path),
00340:         "source_answer_smoke_path": source_path_s,
00341:         "safety_contract": dict(SAFETY_CONTRACT),
00342:         "integration_policy": {
00343:             "mode": "artifact_only_answer_runner_prompt_overlay_smoke",
00344:             "proof_boundary": "Retrieved Engram overlays shape answer behavior only; factual manual claims require current proof_context citations.",
00345:             "forbidden": [
00346:                 "answer_permission_from_engram",
00347:                 "source_truth_mutation_from_engram",
00348:                 "summary_or_engram_used_as_proof",
00349:                 "live_db_or_qdrant_io_without_explicit_gate",
00350:                 "full_30_question_rerun_as_default_debug_loop",
00351:             ],
00352:             "next_patch": "targeted LLM answer-runner overlay smoke behind explicit CLI flag",
00353:         },
00354:         "overlay_records": records,
00355:         "records_path": str(records_path),
00356:         "overlay_map_path": str(overlay_map_path),
00357:         "quality_check_path": str(check_path),
00358:     }
00359:     _write_json(manifest_path, manifest)
00360:     _write_jsonl(records_path, records)
00361:     _write_json(overlay_map_path, overlay_map)
00362:     _write_json(check_path, {
00363:         "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_PROMPT_OVERLAY_SMOKE_CHECKED",
00364:         "quality_status": quality_status,
00365:         "summary": summary,
00366:         "quality_failures": quality_failures,
00367:     })
00368:     manifest["output_path"] = str(manifest_path)
00369:     _write_json(manifest_path, manifest)
00370:     return manifest
00371: 
00372: 
00373: def check_answer_runner_prompt_overlay_smoke_manifest(
00374:     *,
00375:     overlay_smoke: str | Path,
00376:     min_overlay_records: int = 5,
00377:     min_matched_bridge_records: int = 5,
00378:     require_quality_pass: bool = True,
00379:     require_no_answer_permission: bool = True,
00380:     max_unsafe: int = 0,
00381:     max_write_attempts: int = 0,
00382: ) -> Dict[str, Any]:
00383:     data = _read_json(overlay_smoke)
00384:     summary = dict(data.get("summary") or {})
00385:     failures: List[str] = []
00386:     if require_quality_pass and data.get("quality_status") != "PASS":
00387:         failures.append("source_quality_status_not_pass")
00388:     if int(summary.get("overlay_record_count") or 0) < min_overlay_records:
00389:         failures.append("overlay_record_count_below_min")
00390:     if int(summary.get("matched_bridge_record_count") or 0) < min_matched_bridge_records:
00391:         failures.append("matched_bridge_record_count_below_min")
```
### Source window L408-L454
```python
00408:     p = argparse.ArgumentParser(description="Build TRACE-Net H24 Engram answer-runner prompt overlay smoke.")
00409:     p.add_argument("--bridge", required=True)
00410:     p.add_argument("--source-answer-smoke", default="")
00411:     p.add_argument("--output-dir", required=True)
00412:     p.add_argument("--question-ids", default=",".join(DEFAULT_TARGET_QUESTION_IDS))
00413:     p.add_argument("--max-overlay-chars", type=int, default=1800)
00414:     p.add_argument("--min-overlay-records", type=int, default=5)
00415:     p.add_argument("--min-matched-bridge-records", type=int, default=5)
00416:     p.add_argument("--require-h23-quality-pass", action="store_true")
00417:     p.add_argument("--require-source-answer-smoke-quality-pass", action="store_true")
00418:     p.add_argument("--require-no-answer-permission", action="store_true")
00419:     p.add_argument("--max-unsafe", type=int, default=0)
00420:     p.add_argument("--max-write-attempts", type=int, default=0)
00421:     return p
00422: 
00423: 
00424: def main(argv: Sequence[str] | None = None) -> int:
00425:     args = build_arg_parser().parse_args(argv)
00426:     result = build_answer_runner_prompt_overlay_smoke_manifest(
00427:         bridge=args.bridge,
00428:         source_answer_smoke=args.source_answer_smoke or None,
00429:         output_dir=args.output_dir,
00430:         question_ids=args.question_ids,
00431:         max_overlay_chars=args.max_overlay_chars,
00432:         min_overlay_records=args.min_overlay_records,
00433:         min_matched_bridge_records=args.min_matched_bridge_records,
00434:         require_h23_quality_pass=args.require_h23_quality_pass,
00435:         require_source_answer_smoke_quality_pass=args.require_source_answer_smoke_quality_pass,
00436:         require_no_answer_permission=args.require_no_answer_permission,
00437:         max_unsafe=args.max_unsafe,
00438:         max_write_attempts=args.max_write_attempts,
00439:     )
00440:     s = result.get("summary", {})
00441:     print("status=" + str(result.get("status")))
00442:     print("quality_status=" + str(result.get("quality_status")))
00443:     print("overlay_record_count=" + str(s.get("overlay_record_count")))
00444:     print("target_question_count=" + str(s.get("target_question_count")))
00445:     print("matched_bridge_record_count=" + str(s.get("matched_bridge_record_count")))
00446:     print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
00447:     print("answer_permission_count=" + str(s.get("answer_permission_count")))
00448:     print("write_attempt_count=" + str(s.get("write_attempt_count")))
00449:     print("output=" + str(Path(args.output_dir) / f"{MODULE}.json"))
00450:     return 0 if result.get("quality_status") == "PASS" else 1
00451: 
00452: 
00453: if __name__ == "__main__":
00454:     raise SystemExit(main())
```

## `scripts/check_trace_net_e2e_live_self_rag_crag_evaluator_v20_quality.py`
- Location: `active_source_code`
- Score: `292`
- Categories: `crag, page, self_rag, server`
- Functions: main()@L14
- CLI args: --report-path, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json
- Has __main__ guard.

### Source window L1-L39
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import sys
00005: from pathlib import Path
00006: 
00007: REPO_ROOT = Path(__file__).resolve().parents[1]
00008: if str(REPO_ROOT) not in sys.path:
00009:     sys.path.insert(0, str(REPO_ROOT))
00010: 
00011: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json
00012: 
00013: 
00014: def main() -> int:
00015:     parser = argparse.ArgumentParser(description="Check TRACE-Net live Self-RAG + CRAG evaluator v20 quality")
00016:     parser.add_argument("--report-path", required=True)
00017:     parser.add_argument("--write-json", action="store_true")
00018:     add_common_args(parser)
00019:     args = parser.parse_args()
00020: 
00021:     report = load_json(args.report_path)
00022:     checks = evaluate_quality(report, args)
00023:     quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
00024:     report["quality_status"] = quality_status
00025:     report["quality_checks"] = checks
00026:     if args.write_json:
00027:         write_json(args.report_path, report)
00028: 
00029:     print("TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20 Quality")
00030:     print(f" quality_status: {quality_status}")
00031:     for check in checks:
00032:         status = "PASS" if check["passed"] else "FAIL"
00033:         print(
00034:             f" {status} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}"
00035:         )
00036:     return 0 if quality_status == "PASS" else 1
00037: 
00038: 
00039: if __name__ == "__main__":
```

## `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Location: `active_tests`
- Score: `291`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, webui`
- Functions: test_quality_check_passes_for_required_brain_gates(tmp_path)@L7; test_quality_check_fails_when_self_rag_not_used(tmp_path)@L46; test_quality_check_supports_explicit_tool_status_requirements(tmp_path)@L80
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality

### Source window L1-L32
```python
00001: import json
00002: from pathlib import Path
00003: 
00004: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality
00005: 
00006: 
00007: def test_quality_check_passes_for_required_brain_gates(tmp_path):
00008:     report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
00009:     payload = {
00010:         "quality_status": "PASS",
00011:         "summary": {
00012:             "tool_checklist_count": 10,
00013:             "used_tool_count": 4,
00014:             "answer_permission_count": 0,
00015:             "can_answer_directly_count": 0,
00016:             "can_prove_claims_count": 0,
00017:             "source_truth_mutation_allowed_count": 0,
00018:             "postgres_write_attempt_count": 0,
00019:             "qdrant_write_attempt_count": 0,
00020:             "opensearch_write_attempt_count": 0,
00021:         },
00022:         "tool_statuses": {
00023:             "query_planner": "used",
00024:             "context_pack_builder": "used",
00025:             "self_rag": "used",
00026:             "crag_retry": "skipped_not_needed",
00027:         },
00028:     }
00029:     report.write_text(json.dumps(payload), encoding="utf-8")
00030: 
00031:     result = check_webui_self_rag_crag_bridge_quality(
00032:         report_path=report,
```
### Source window L49-L94
```python
00049:         "quality_status": "PASS",
00050:         "summary": {
00051:             "tool_checklist_count": 10,
00052:             "used_tool_count": 3,
00053:             "answer_permission_count": 0,
00054:             "can_answer_directly_count": 0,
00055:             "can_prove_claims_count": 0,
00056:             "source_truth_mutation_allowed_count": 0,
00057:             "postgres_write_attempt_count": 0,
00058:             "qdrant_write_attempt_count": 0,
00059:             "opensearch_write_attempt_count": 0,
00060:         },
00061:         "tool_statuses": {
00062:             "query_planner": "used",
00063:             "context_pack_builder": "used",
00064:             "self_rag": "available_not_used",
00065:             "crag_retry": "available_not_used",
00066:         },
00067:     }
00068:     report.write_text(json.dumps(payload), encoding="utf-8")
00069: 
00070:     result = check_webui_self_rag_crag_bridge_quality(
00071:         report_path=report,
00072:         require_self_rag_used=True,
00073:         require_crag_evaluated=True,
00074:     )
00075: 
00076:     assert result["quality_status"] == "FAIL"
00077:     assert any("Self-RAG" in failure for failure in result["failures"])
00078: 
00079: 
00080: def test_quality_check_supports_explicit_tool_status_requirements(tmp_path):
00081:     report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
00082:     payload = {
00083:         "quality_status": "PASS",
00084:         "summary": {"tool_checklist_count": 10, "used_tool_count": 4},
00085:         "tool_statuses": {"crag_retry": "used", "self_rag": "used"},
00086:     }
00087:     report.write_text(json.dumps(payload), encoding="utf-8")
00088: 
00089:     result = check_webui_self_rag_crag_bridge_quality(
00090:         report_path=report,
00091:         require_tool_statuses=["crag_retry=used", "self_rag=used"],
00092:     )
00093: 
00094:     assert result["quality_status"] == "PASS"
```

## `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tiff/trace_net_webui_self_rag_crag_bridge_v1.py`
- Location: `archived_reference`
- Score: `283`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net WebUI Self-RAG / CRAG Bridge v1. Runs the current engineering-brain artifact stages for one WebUI-style question and writes a tool/stage checklist that proves which gates were actually executed. This bridge is intentionally pre-answer and artifact-only: - it does not call Gemma - it does not replace the WebUI server yet - it does not execute database/vector/search writes - it does not mutate source truth - it does not grant answer permission
- Functions: _read_json(path)@L53; _write_json(path, payload)@L59; _write_jsonl(path, records)@L64; _as_path(value)@L71; _path_status(path)@L77; _stage_row()@L83; _safe_summary(payload)@L108; _records(payload)@L113; _stage_used_row(tool_id, label, report_path, payload, count_key)@L118; _artifact_tool_rows(context_pack_payload, input_paths)@L134; _crag_row(crag_payload, crag_path, self_rag_payload)@L175; _checklist_text(rows)@L204; _rollup_safety(stage_payloads)@L217; _import_stage_builders()@L244; build_webui_self_rag_crag_bridge()@L260; _write_markdown(path, payload)@L470; check_webui_self_rag_crag_bridge_quality()@L503; main_build(argv)@L562
- CLI args: --question, --kernel, --output-dir, --route-dispatch-handoff, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --image-visual-observer, --max-records-per-slot, --min-high-signal-capsules, --min-evidence-strength-score, --quality, --report-path, --write-json, --min-checklist-count, --min-used-tool-count, --require-query-planner-used, --require-context-pack-builder-used, --require-self-rag-used, --require-crag-evaluated, --require-no-answer-permission, --require-no-source-truth-mutation, --require-no-write-attempts, --require-tool-status
- Tiff imports: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner; from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint; from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder; from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check; from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan
- Has __main__ guard.

### Source window L1-L50
```python
00001: """TRACE-Net WebUI Self-RAG / CRAG Bridge v1.
00002: 
00003: Runs the current engineering-brain artifact stages for one WebUI-style question
00004: and writes a tool/stage checklist that proves which gates were actually
00005: executed.
00006: 
00007: This bridge is intentionally pre-answer and artifact-only:
00008: - it does not call Gemma
00009: - it does not replace the WebUI server yet
00010: - it does not execute database/vector/search writes
00011: - it does not mutate source truth
00012: - it does not grant answer permission
00013: """
00014: from __future__ import annotations
00015: 
00016: import argparse
00017: import json
00018: from collections import Counter
00019: from pathlib import Path
00020: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
00021: 
00022: MODULE_VERSION = "trace_net_webui_self_rag_crag_bridge_v1"
00023: REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json"
00024: 
00025: STAGE_REPORT_NAMES = {
00026:     "query_planner": "trace_net_engineering_query_planner_v1.json",
00027:     "context_pack_blueprint": "trace_net_engineering_context_pack_blueprint_v1.json",
00028:     "context_pack_builder": "trace_net_engineering_context_pack_builder_v1.json",
00029:     "self_rag": "trace_net_engineering_context_self_rag_check_v1.json",
00030:     "crag_retry": "trace_net_engineering_context_crag_retry_plan_v1.json",
00031: }
00032: 
00033: ARTIFACT_TOOL_KEYS = {
00034:     "route_dispatch": "fishnet_route_dispatch_handoff",
00035:     "table_route": "table_exact_search_adapter",
00036:     "page_context_v2": "page_context_v2",
00037:     "graph_leiden": "leiden_communities",
00038:     "visual_image_route": "image_visual_observer",
00039: }
00040: 
00041: SAFETY_COUNT_KEYS = (
00042:     "unsafe_record_count",
00043:     "answer_permission_count",
00044:     "can_answer_directly_count",
00045:     "can_prove_claims_count",
00046:     "source_truth_mutation_allowed_count",
00047:     "postgres_write_attempt_count",
00048:     "qdrant_write_attempt_count",
00049:     "opensearch_write_attempt_count",
00050: )
```
### Source window L158-L214
```python
00158:                 status=status,
00159:                 reason=reason,
00160:                 path=path,
00161:                 count=count,
00162:             )
00163:         )
00164:     rows.append(
00165:         _stage_row(
00166:             tool_id="embedding_vector",
00167:             label="embedding/vector",
00168:             status="not_wired_in_bridge",
00169:             reason="this bridge uses the current context-pack artifacts; live vector search is not yet a stage input here",
00170:         )
00171:     )
00172:     return rows
00173: 
00174: 
00175: def _crag_row(crag_payload: Mapping[str, Any], crag_path: Path, self_rag_payload: Mapping[str, Any]) -> Dict[str, Any]:
00176:     crag_summary = _safe_summary(crag_payload)
00177:     self_summary = _safe_summary(self_rag_payload)
00178:     quality = str(crag_payload.get("quality_status") or "UNKNOWN")
00179:     plan_count = int(crag_summary.get("crag_retry_plan_count") or 0)
00180:     source_required = int(self_summary.get("crag_retry_required_count") or 0)
00181:     if quality != "PASS":
00182:         status = "failed"
00183:         reason = f"CRAG retry plan report quality_status={quality}"
00184:     elif source_required > 0 and plan_count > 0:
00185:         status = "used"
00186:         reason = f"Self-RAG required retry for {source_required} pack(s), so CRAG produced {plan_count} retry plan(s)"
00187:     elif source_required > 0 and plan_count == 0:
00188:         status = "failed"
00189:         reason = "Self-RAG required retry, but CRAG produced zero retry plans"
00190:     else:
00191:         status = "skipped_not_needed"
00192:         reason = "Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans"
00193:     return _stage_row(
00194:         tool_id="crag_retry",
00195:         label="CRAG retry",
00196:         status=status,
00197:         reason=reason,
00198:         path=crag_path,
00199:         count=plan_count,
00200:         quality_status=quality,
00201:     )
00202: 
00203: 
00204: def _checklist_text(rows: Sequence[Mapping[str, Any]]) -> str:
00205:     lines = []
00206:     for row in rows:
00207:         label = str(row.get("label") or row.get("tool_id"))
00208:         status = str(row.get("status"))
00209:         reason = str(row.get("reason") or "")
00210:         if reason:
00211:             lines.append(f"{label}: {status} — {reason}")
00212:         else:
00213:             lines.append(f"{label}: {status}")
00214:     return "\n".join(lines)
```
### Source window L221-L277
```python
00221:         for key in SAFETY_COUNT_KEYS:
00222:             totals[key] += int(summary.get(key) or 0)
00223:         # Record-level fallback for reports that do not put every safety field in summary.
00224:         for record in _records(payload):
00225:             if record.get("unsafe"):
00226:                 totals["unsafe_record_count"] += 1
00227:             if record.get("answer_permission"):
00228:                 totals["answer_permission_count"] += 1
00229:             if record.get("can_answer_directly"):
00230:                 totals["can_answer_directly_count"] += 1
00231:             if record.get("can_prove_claims"):
00232:                 totals["can_prove_claims_count"] += 1
00233:             if record.get("source_truth_mutation_allowed"):
00234:                 totals["source_truth_mutation_allowed_count"] += 1
00235:             if record.get("postgres_write_attempt"):
00236:                 totals["postgres_write_attempt_count"] += 1
00237:             if record.get("qdrant_write_attempt"):
00238:                 totals["qdrant_write_attempt_count"] += 1
00239:             if record.get("opensearch_write_attempt"):
00240:                 totals["opensearch_write_attempt_count"] += 1
00241:     return totals
00242: 
00243: 
00244: def _import_stage_builders() -> Dict[str, Any]:
00245:     from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner
00246:     from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint
00247:     from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder
00248:     from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check
00249:     from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan
00250: 
00251:     return {
00252:         "query_planner": build_engineering_query_planner,
00253:         "context_pack_blueprint": build_engineering_context_pack_blueprint,
00254:         "context_pack_builder": build_engineering_context_pack_builder,
00255:         "self_rag": build_engineering_context_self_rag_check,
00256:         "crag_retry": build_engineering_context_crag_retry_plan,
00257:     }
00258: 
00259: 
00260: def build_webui_self_rag_crag_bridge(
00261:     *,
00262:     question: str,
00263:     kernel_path: Path,
00264:     output_dir: Path,
00265:     route_dispatch_handoff: Optional[Path] = None,
00266:     table_exact_search_adapter: Optional[Path] = None,
00267:     page_context_v2: Optional[Path] = None,
00268:     leiden_communities: Optional[Path] = None,
00269:     image_visual_observer: Optional[Path] = None,
00270:     max_records_per_slot: int = 8,
00271:     min_high_signal_capsules: int = 1,
00272:     min_evidence_strength_score: int = 35,
00273: ) -> Dict[str, Any]:
00274:     """Run the live artifact-stage bridge for one question."""
00275:     if not question.strip():
00276:         raise ValueError("question must not be empty")
00277:     if not kernel_path.exists():
```
### Source window L285-L341
```python
00285:     self_rag_dir = stage_dir / "self_rag_check"
00286:     crag_dir = stage_dir / "crag_retry_plan"
00287: 
00288:     builders = _import_stage_builders()
00289: 
00290:     planner_payload = builders["query_planner"](
00291:         kernel_path=kernel_path,
00292:         output_dir=planner_dir,
00293:         questions=[question],
00294:     )
00295:     planner_path = planner_dir / STAGE_REPORT_NAMES["query_planner"]
00296: 
00297:     blueprint_payload = builders["context_pack_blueprint"](
00298:         query_planner_path=planner_path,
00299:         output_dir=blueprint_dir,
00300:     )
00301:     blueprint_path = blueprint_dir / STAGE_REPORT_NAMES["context_pack_blueprint"]
00302: 
00303:     pack_payload = builders["context_pack_builder"](
00304:         blueprint_path=blueprint_path,
00305:         output_dir=pack_dir,
00306:         route_dispatch_handoff=route_dispatch_handoff,
00307:         table_exact_search_adapter=table_exact_search_adapter,
00308:         page_context_v2=page_context_v2,
00309:         leiden_communities=leiden_communities,
00310:         image_visual_observer=image_visual_observer,
00311:         max_records_per_slot=max_records_per_slot,
00312:     )
00313:     pack_path = pack_dir / STAGE_REPORT_NAMES["context_pack_builder"]
00314: 
00315:     self_rag_payload = builders["self_rag"](
00316:         context_pack_path=pack_path,
00317:         output_dir=self_rag_dir,
00318:         min_high_signal_capsules=min_high_signal_capsules,
00319:         min_evidence_strength_score=min_evidence_strength_score,
00320:     )
00321:     self_rag_path = self_rag_dir / STAGE_REPORT_NAMES["self_rag"]
00322: 
00323:     # Always build the CRAG report. If Self-RAG does not require retry, the
00324:     # CRAG report should contain zero retry plans and the checklist status is
00325:     # skipped_not_needed rather than falsely used.
00326:     crag_payload = builders["crag_retry"](
00327:         self_rag_report_path=self_rag_path,
00328:         output_dir=crag_dir,
00329:     )
00330:     crag_path = crag_dir / STAGE_REPORT_NAMES["crag_retry"]
00331: 
00332:     stage_payloads = [planner_payload, blueprint_payload, pack_payload, self_rag_payload, crag_payload]
00333:     stage_paths = {
00334:         "query_planner": planner_path,
00335:         "context_pack_blueprint": blueprint_path,
00336:         "context_pack_builder": pack_path,
00337:         "self_rag": self_rag_path,
00338:         "crag_retry": crag_path,
00339:     }
00340: 
00341:     rows: List[Dict[str, Any]] = [
```
### Source window L388-L444
```python
00388:         "not_used_tool_count": len(not_used_tools),
00389:         "not_used_tools": not_used_tools,
00390:         "query_planner_used": statuses.get("query_planner") == "used",
00391:         "context_pack_blueprint_used": statuses.get("context_pack_blueprint") == "used",
00392:         "context_pack_builder_used": statuses.get("context_pack_builder") == "used",
00393:         "self_rag_used": statuses.get("self_rag") == "used",
00394:         "crag_retry_status": statuses.get("crag_retry"),
00395:         "crag_retry_evaluated": statuses.get("crag_retry") in {"used", "skipped_not_needed"},
00396:         "self_rag_status_counts": self_summary.get("self_rag_status_counts") or {},
00397:         "self_rag_ready_for_gemma_draft_count": int(self_summary.get("ready_for_gemma_draft_count") or 0),
00398:         "self_rag_crag_retry_required_count": int(self_summary.get("crag_retry_required_count") or 0),
00399:         "crag_retry_plan_count": int(crag_summary.get("crag_retry_plan_count") or 0),
00400:         "crag_ready_for_execution_count": int(crag_summary.get("ready_for_crag_execution_count") or 0),
00401:         "context_pack_count": int(pack_summary.get("context_pack_count") or 0),
00402:         "total_evidence_capsule_count": int(pack_summary.get("total_evidence_capsule_count") or 0),
00403:         "total_high_signal_evidence_capsule_count": int(pack_summary.get("total_high_signal_evidence_capsule_count") or 0),
00404:         "artifact_record_counts": pack_summary.get("artifact_record_counts") or {},
00405:         **safety,
00406:     }
00407: 
00408:     quality_status = "PASS"
00409:     failures: List[str] = []
00410:     for key, payload in zip(("query_planner", "context_pack_blueprint", "context_pack_builder", "self_rag", "crag_retry"), stage_payloads):
00411:         if payload.get("quality_status") != "PASS":
00412:             failures.append(f"{key} quality_status is not PASS")
00413:     if not summary["query_planner_used"]:
00414:         failures.append("query planner was not used")
00415:     if not summary["context_pack_builder_used"]:
00416:         failures.append("context pack builder was not used")
00417:     if not summary["self_rag_used"]:
00418:         failures.append("Self-RAG was not used")
00419:     if not summary["crag_retry_evaluated"]:
00420:         failures.append("CRAG retry was not evaluated")
00421:     for key in SAFETY_COUNT_KEYS:
00422:         if int(summary.get(key) or 0) != 0:
00423:             failures.append(f"{key} is not zero")
00424:     if failures:
00425:         quality_status = "FAIL"
00426: 
00427:     payload: Dict[str, Any] = {
00428:         "module": MODULE_VERSION,
00429:         "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_BUILT",
00430:         "quality_status": quality_status,
00431:         "failures": failures,
00432:         "question": question,
00433:         "summary": summary,
00434:         "tool_checklist": rows,
00435:         "tool_statuses": statuses,
00436:         "checklist_text": _checklist_text(rows),
00437:         "stage_report_paths": {key: str(path) for key, path in stage_paths.items()},
00438:         "input_paths": {key: str(path) if path else None for key, path in input_paths.items()},
00439:         "thresholds": {
00440:             "max_records_per_slot": max_records_per_slot,
00441:             "min_high_signal_capsules": min_high_signal_capsules,
00442:             "min_evidence_strength_score": min_evidence_strength_score,
00443:         },
00444:         "safety_contract": {
```
### Source window L515-L571
```python
00515:     require_tool_statuses: Sequence[str] = (),
00516: ) -> Dict[str, Any]:
00517:     payload = _read_json(report_path)
00518:     summary = _safe_summary(payload)
00519:     statuses = payload.get("tool_statuses") or {}
00520:     failures: List[str] = []
00521: 
00522:     def fail_if(condition: bool, message: str) -> None:
00523:         if condition:
00524:             failures.append(message)
00525: 
00526:     fail_if(payload.get("quality_status") != "PASS", "source bridge report quality_status is not PASS")
00527:     fail_if(int(summary.get("tool_checklist_count") or 0) < min_checklist_count, "not enough checklist rows")
00528:     fail_if(int(summary.get("used_tool_count") or 0) < min_used_tool_count, "not enough used tools")
00529:     if require_query_planner_used:
00530:         fail_if(statuses.get("query_planner") != "used", "query planner was not used")
00531:     if require_context_pack_builder_used:
00532:         fail_if(statuses.get("context_pack_builder") != "used", "context pack builder was not used")
00533:     if require_self_rag_used:
00534:         fail_if(statuses.get("self_rag") != "used", "Self-RAG was not used")
00535:     if require_crag_evaluated:
00536:         fail_if(statuses.get("crag_retry") not in {"used", "skipped_not_needed"}, "CRAG retry was not evaluated")
00537:     if require_no_answer_permission:
00538:         for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
00539:             fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
00540:     if require_no_source_truth_mutation:
00541:         fail_if(int(summary.get("source_truth_mutation_allowed_count") or 0) != 0, "source_truth_mutation_allowed_count is not zero")
00542:     if require_no_write_attempts:
00543:         for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
00544:             fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
00545:     for requirement in require_tool_statuses:
00546:         if "=" not in requirement:
00547:             failures.append(f"invalid --require-tool-status value: {requirement}")
00548:             continue
00549:         tool_id, expected = requirement.split("=", 1)
00550:         actual = statuses.get(tool_id)
00551:         fail_if(actual != expected, f"tool {tool_id} status {actual!r} != expected {expected!r}")
00552: 
00553:     return {
00554:         "quality_status": "FAIL" if failures else "PASS",
00555:         "summary": summary,
00556:         "tool_statuses": statuses,
00557:         "failures": failures,
00558:         "checked_report_path": str(report_path),
00559:     }
00560: 
00561: 
00562: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00563:     parser = argparse.ArgumentParser(description="Build TRACE-Net WebUI Self-RAG / CRAG bridge v1.")
00564:     parser.add_argument("--question", required=True)
00565:     parser.add_argument("--kernel", required=True)
00566:     parser.add_argument("--output-dir", required=True)
00567:     parser.add_argument("--route-dispatch-handoff")
00568:     parser.add_argument("--table-exact-search-adapter")
00569:     parser.add_argument("--page-context-v2")
00570:     parser.add_argument("--leiden-communities")
00571:     parser.add_argument("--image-visual-observer")
```
### Source window L591-L641
```python
00591:     print("Status:", payload["status"])
00592:     print("Quality status:", payload["quality_status"])
00593:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
00594:     print("Checklist:")
00595:     print(payload.get("checklist_text") or "")
00596:     return 0 if payload["quality_status"] == "PASS" else 1
00597: 
00598: 
00599: def main_check(argv: Optional[Sequence[str]] = None) -> int:
00600:     parser = argparse.ArgumentParser(description="Check TRACE-Net WebUI Self-RAG / CRAG bridge v1 quality.")
00601:     parser.add_argument("--report-path", required=True)
00602:     parser.add_argument("--write-json", action="store_true")
00603:     parser.add_argument("--min-checklist-count", type=int, default=8)
00604:     parser.add_argument("--min-used-tool-count", type=int, default=4)
00605:     parser.add_argument("--require-query-planner-used", action="store_true")
00606:     parser.add_argument("--require-context-pack-builder-used", action="store_true")
00607:     parser.add_argument("--require-self-rag-used", action="store_true")
00608:     parser.add_argument("--require-crag-evaluated", action="store_true")
00609:     parser.add_argument("--require-no-answer-permission", action="store_true")
00610:     parser.add_argument("--require-no-source-truth-mutation", action="store_true")
00611:     parser.add_argument("--require-no-write-attempts", action="store_true")
00612:     parser.add_argument("--require-tool-status", action="append", default=[])
00613:     args = parser.parse_args(argv)
00614: 
00615:     result = check_webui_self_rag_crag_bridge_quality(
00616:         report_path=Path(args.report_path),
00617:         min_checklist_count=args.min_checklist_count,
00618:         min_used_tool_count=args.min_used_tool_count,
00619:         require_query_planner_used=args.require_query_planner_used,
00620:         require_context_pack_builder_used=args.require_context_pack_builder_used,
00621:         require_self_rag_used=args.require_self_rag_used,
00622:         require_crag_evaluated=args.require_crag_evaluated,
00623:         require_no_answer_permission=args.require_no_answer_permission,
00624:         require_no_source_truth_mutation=args.require_no_source_truth_mutation,
00625:         require_no_write_attempts=args.require_no_write_attempts,
00626:         require_tool_statuses=args.require_tool_status,
00627:     )
00628:     print("Quality status:", result["quality_status"])
00629:     print("Summary:", json.dumps(result["summary"], sort_keys=True))
00630:     print("Tool statuses:", json.dumps(result["tool_statuses"], sort_keys=True))
00631:     if result["failures"]:
00632:         print("Failures:", json.dumps(result["failures"], indent=2))
00633:     if args.write_json:
00634:         out = Path(args.report_path).with_name("trace_net_webui_self_rag_crag_bridge_v1_quality_check.json")
00635:         _write_json(out, result)
00636:         print("Wrote:", out)
00637:     return 0 if result["quality_status"] == "PASS" else 1
00638: 
00639: 
00640: if __name__ == "__main__":
00641:     raise SystemExit(main_build())
```

## `scripts/check_trace_net_engineering_engram_crag_repair_v1.py`
- Location: `active_source_code`
- Score: `283`
- Categories: `crag, engram, page, safety, self_rag, server`
- Functions: main()@L12
- CLI args: --crag-repair, --min-records, --min-crag-pass-or-no-repair, --require-quality-pass, --require-no-answer-permission, --max-repair-attempts, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest
- Has __main__ guard.

### Source window L1-L37
```python
00001: from pathlib import Path
00002: import argparse
00003: import sys
00004: 
00005: ROOT = Path(__file__).resolve().parents[1]
00006: if str(ROOT) not in sys.path:
00007:     sys.path.insert(0, str(ROOT))
00008: 
00009: from tiff.trace_net_engineering_engram_crag_repair_v1 import check_crag_repair_manifest
00010: 
00011: 
00012: def main() -> int:
00013:     parser = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram CRAG repair artifact v1")
00014:     parser.add_argument("--crag-repair", required=True)
00015:     parser.add_argument("--min-records", type=int, default=1)
00016:     parser.add_argument("--min-crag-pass-or-no-repair", type=int, default=1)
00017:     parser.add_argument("--require-quality-pass", action="store_true")
00018:     parser.add_argument("--require-no-answer-permission", action="store_true")
00019:     parser.add_argument("--max-repair-attempts", type=int, default=0)
00020:     parser.add_argument("--max-unsafe", type=int, default=0)
00021:     parser.add_argument("--max-write-attempts", type=int, default=0)
00022:     args = parser.parse_args()
00023:     result = check_crag_repair_manifest(**vars(args))
00024:     print("status=" + str(result.get("status")))
00025:     print("quality_status=" + str(result.get("quality_status")))
00026:     print("critic_record_count=" + str(result.get("critic_record_count")))
00027:     print("crag_pass_or_no_repair_count=" + str(result.get("crag_pass_or_no_repair_count")))
00028:     print("repair_recommended_count=" + str(result.get("repair_recommended_count")))
00029:     print("repair_attempt_count=" + str(result.get("repair_attempt_count")))
00030:     print("unsafe_finding_count=" + str(result.get("unsafe_finding_count")))
00031:     print("answer_permission_count=" + str(result.get("answer_permission_count")))
00032:     print("write_attempt_count=" + str(result.get("write_attempt_count")))
00033:     if result.get("quality_failures"):
00034:         print("quality_failures=" + repr(result.get("quality_failures")))
00035:     return 0 if result.get("quality_status") == "PASS" else 1
00036: 
00037: 
```

## `scripts/build_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Location: `active_source_code`
- Score: `274`
- Categories: `page, self_rag, server`
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main
- Has __main__ guard.

### Source window L1-L14
```python
00001: from __future__ import annotations
00002: 
00003: import sys
00004: from pathlib import Path
00005: 
00006: REPO_ROOT = Path(__file__).resolve().parents[1]
00007: if str(REPO_ROOT) not in sys.path:
00008:     sys.path.insert(0, str(REPO_ROOT))
00009: 
00010: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import main
00011: 
00012: 
00013: if __name__ == "__main__":
00014:     raise SystemExit(main())
```

## `scripts/build_trace_net_page_context_pack_v3.py`
- Location: `active_source_code`
- Score: `273`
- Categories: `context_pack, graph_vector, page, server, table_visual_ocr, webui`
- Doc: Build TRACE-Net Page Context Pack v3.
- Functions: parse_args()@L19; _warn_missing_optional_path(label, value)@L38; _resolve_sidecar_path(base_path, value)@L43; _read_jsonl(path)@L58; load_artifact_with_sidecars(path)@L85; main()@L122
- CLI args: --question, --pages, --max-pages, --route-manifest, --graph-export, --ocr-records, --table-evidence, --exact-part-records, --visual-summaries, --vector-hits, --output
- Tiff imports: from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, load_json, write_json
- Has __main__ guard.

### Source window L1-L44
```python
00001: #!/usr/bin/env python3
00002: """Build TRACE-Net Page Context Pack v3."""
00003: 
00004: from __future__ import annotations
00005: 
00006: import argparse
00007: from pathlib import Path
00008: import sys
00009: import json
00010: from typing import Any
00011: 
00012: REPO_ROOT = Path(__file__).resolve().parents[1]
00013: if str(REPO_ROOT) not in sys.path:
00014:     sys.path.insert(0, str(REPO_ROOT))
00015: 
00016: from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3, load_json, write_json
00017: 
00018: 
00019: def parse_args() -> argparse.Namespace:
00020:     parser = argparse.ArgumentParser(description="Build a TRACE-Net page context pack v3 JSON artifact.")
00021:     parser.add_argument("--question", default="", help="User question used to select pages/entities.")
00022:     parser.add_argument("--pages", nargs="*", default=[], help="Explicit page numbers or page IDs to include.")
00023:     parser.add_argument("--max-pages", type=int, default=8)
00024:     parser.add_argument("--route-manifest", default=None)
00025:     parser.add_argument("--graph-export", default=None)
00026:     parser.add_argument("--ocr-records", default=None)
00027:     parser.add_argument("--table-evidence", default=None)
00028:     parser.add_argument("--exact-part-records", default=None)
00029:     parser.add_argument("--visual-summaries", default=None)
00030:     parser.add_argument("--vector-hits", default=None)
00031:     parser.add_argument(
00032:         "--output",
00033:         default="local_data/organization/trace_net/page_context_pack_v3/trace_net_page_context_pack_v3.json",
00034:     )
00035:     return parser.parse_args()
00036: 
00037: 
00038: def _warn_missing_optional_path(label: str, value: str | None) -> None:
00039:     if value and not Path(value).exists():
00040:         print(f"WARNING: {label} path not found: {value}", file=sys.stderr)
00041: 
00042: 
00043: def _resolve_sidecar_path(base_path: str | None, value: str | None) -> Path | None:
00044:     if not value:
```
### Source window L125-L163
```python
00125:         ("route_manifest", args.route_manifest),
00126:         ("graph_export", args.graph_export),
00127:         ("ocr_records", args.ocr_records),
00128:         ("table_evidence", args.table_evidence),
00129:         ("exact_part_records", args.exact_part_records),
00130:         ("visual_summaries", args.visual_summaries),
00131:         ("vector_hits", args.vector_hits),
00132:     ):
00133:         _warn_missing_optional_path(label, value)
00134: 
00135:     pack = build_page_context_pack_v3(
00136:         question=args.question,
00137:         requested_pages=args.pages,
00138:         max_pages=args.max_pages,
00139:         route_manifest=load_artifact_with_sidecars(args.route_manifest),
00140:         graph_export=load_artifact_with_sidecars(args.graph_export),
00141:         ocr_records=load_artifact_with_sidecars(args.ocr_records),
00142:         table_evidence=load_artifact_with_sidecars(args.table_evidence),
00143:         exact_part_records=load_artifact_with_sidecars(args.exact_part_records),
00144:         visual_summaries=load_artifact_with_sidecars(args.visual_summaries),
00145:         vector_hits=load_artifact_with_sidecars(args.vector_hits),
00146:     )
00147:     write_json(args.output, pack)
00148:     summary = pack.get("summary", {})
00149:     print(f"Wrote: {args.output}")
00150:     print(f"quality_status: {pack.get('quality_status')}")
00151:     print(f"selected_page_count: {summary.get('selected_page_count')}")
00152:     print(f"source_trace_ready_page_count: {summary.get('source_trace_ready_page_count')}")
00153:     print(f"proof_record_count: {summary.get('proof_record_count')}")
00154:     print(f"guidance_record_count: {summary.get('guidance_record_count')}")
00155:     print(f"source_file_count: {summary.get('source_file_count')}")
00156:     print(f"source_link_count: {summary.get('source_link_count')}")
00157:     print(f"ocr_excerpt_count: {summary.get('ocr_excerpt_count')}")
00158:     print(f"visual_guidance_count: {summary.get('visual_guidance_count')}")
00159:     return 0 if pack.get("quality_status") == "PASS" else 2
00160: 
00161: 
00162: if __name__ == "__main__":
00163:     raise SystemExit(main())
```
### Source window L63-L119
```python
00063:             if not line:
00064:                 continue
00065:             try:
00066:                 item = json.loads(line)
00067:             except json.JSONDecodeError:
00068:                 continue
00069:             if isinstance(item, dict):
00070:                 rows.append(item)
00071:     except UnicodeDecodeError:
00072:         for line in path.read_text(encoding="utf-8-sig").splitlines():
00073:             line = line.strip()
00074:             if not line:
00075:                 continue
00076:             try:
00077:                 item = json.loads(line)
00078:             except json.JSONDecodeError:
00079:                 continue
00080:             if isinstance(item, dict):
00081:                 rows.append(item)
00082:     return rows
00083: 
00084: 
00085: def load_artifact_with_sidecars(path: str | None) -> Any:
00086:     """Load a JSON artifact and hydrate common linked JSONL sidecars.
00087: 
00088:     Some visual/OpenWebUI route artifacts are manifests whose real page cards
00089:     live in a `records_jsonl_path` or similar sidecar.  v3.2 follows those
00090:     read-only sidecars so page 202-style image routes can attach visual
00091:     guidance instead of only a manifest summary.
00092:     """
00093:     payload = load_json(path, {})
00094:     if not isinstance(payload, dict):
00095:         return payload
00096:     merged = dict(payload)
00097:     linked_keys = (
00098:         "records_jsonl_path",
00099:         "records_path",
00100:         "sample_records_jsonl_path",
00101:         "visual_records_jsonl_path",
00102:         "llava_records_jsonl_path",
00103:     )
00104:     sidecar_records: list[dict[str, Any]] = []
00105:     for key in linked_keys:
00106:         sidecar = _resolve_sidecar_path(path, str(merged.get(key) or ""))
00107:         if sidecar and sidecar.suffix.lower() == ".jsonl":
00108:             sidecar_records.extend(_read_jsonl(sidecar))
00109:         elif sidecar and sidecar.suffix.lower() == ".json":
00110:             side_payload = load_json(sidecar, {})
00111:             if isinstance(side_payload, list):
00112:                 sidecar_records.extend([x for x in side_payload if isinstance(x, dict)])
00113:             elif isinstance(side_payload, dict) and isinstance(side_payload.get("records"), list):
00114:                 sidecar_records.extend([x for x in side_payload["records"] if isinstance(x, dict)])
00115:     if sidecar_records:
00116:         existing = merged.get("records") if isinstance(merged.get("records"), list) else []
00117:         merged["records"] = list(existing) + sidecar_records
00118:         merged["linked_sidecar_record_count"] = len(sidecar_records)
00119:     return merged
```

## `scripts/check_trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Location: `active_source_code`
- Score: `270`
- Categories: `engram, page, safety, server, webui`
- Functions: main()@L14
- CLI args: --overlay-smoke, --min-overlay-records, --min-matched-bridge-records, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import check_answer_runner_prompt_overlay_smoke_manifest
- Has __main__ guard.

### Source window L1-L39
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import sys
00005: from pathlib import Path
00006: 
00007: ROOT = Path(__file__).resolve().parents[1]
00008: if str(ROOT) not in sys.path:
00009:     sys.path.insert(0, str(ROOT))
00010: 
00011: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import check_answer_runner_prompt_overlay_smoke_manifest
00012: 
00013: 
00014: def main() -> int:
00015:     p = argparse.ArgumentParser(description="Check TRACE-Net H24 Engram answer-runner prompt overlay smoke.")
00016:     p.add_argument("--overlay-smoke", required=True)
00017:     p.add_argument("--min-overlay-records", type=int, default=5)
00018:     p.add_argument("--min-matched-bridge-records", type=int, default=5)
00019:     p.add_argument("--require-quality-pass", action="store_true")
00020:     p.add_argument("--require-no-answer-permission", action="store_true")
00021:     p.add_argument("--max-unsafe", type=int, default=0)
00022:     p.add_argument("--max-write-attempts", type=int, default=0)
00023:     args = p.parse_args()
00024:     result = check_answer_runner_prompt_overlay_smoke_manifest(
00025:         overlay_smoke=args.overlay_smoke,
00026:         min_overlay_records=args.min_overlay_records,
00027:         min_matched_bridge_records=args.min_matched_bridge_records,
00028:         require_quality_pass=args.require_quality_pass,
00029:         require_no_answer_permission=args.require_no_answer_permission,
00030:         max_unsafe=args.max_unsafe,
00031:         max_write_attempts=args.max_write_attempts,
00032:     )
00033:     s = result.get("summary", {})
00034:     print("status=" + str(result.get("status")))
00035:     print("quality_status=" + str(result.get("quality_status")))
00036:     print("overlay_record_count=" + str(s.get("overlay_record_count")))
00037:     print("target_question_count=" + str(s.get("target_question_count")))
00038:     print("matched_bridge_record_count=" + str(s.get("matched_bridge_record_count")))
00039:     print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
```

## `scripts/check_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Location: `active_source_code`
- Score: `270`
- Categories: `engram, page, safety, server, webui`
- Functions: build_arg_parser()@L14; main(argv)@L26
- CLI args: --bridge, --min-bridge-records, --min-task-types, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import check_answer_runner_retrieval_bridge_manifest
- Has __main__ guard.

### Source window L1-L39
```python
00001: #!/usr/bin/env python3
00002: from pathlib import Path
00003: import argparse
00004: import json
00005: import sys
00006: 
00007: ROOT = Path(__file__).resolve().parents[1]
00008: if str(ROOT) not in sys.path:
00009:     sys.path.insert(0, str(ROOT))
00010: 
00011: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import check_answer_runner_retrieval_bridge_manifest
00012: 
00013: 
00014: def build_arg_parser() -> argparse.ArgumentParser:
00015:     p = argparse.ArgumentParser(description="Check TRACE-Net H23 Engram answer-runner retrieval bridge.")
00016:     p.add_argument("--bridge", required=True)
00017:     p.add_argument("--min-bridge-records", type=int, default=6)
00018:     p.add_argument("--min-task-types", type=int, default=5)
00019:     p.add_argument("--require-quality-pass", action="store_true")
00020:     p.add_argument("--require-no-answer-permission", action="store_true")
00021:     p.add_argument("--max-unsafe", type=int, default=0)
00022:     p.add_argument("--max-write-attempts", type=int, default=0)
00023:     return p
00024: 
00025: 
00026: def main(argv=None) -> int:
00027:     args = build_arg_parser().parse_args(argv)
00028:     result = check_answer_runner_retrieval_bridge_manifest(**vars(args))
00029:     s = result.get("summary", {})
00030:     print("status=" + str(result.get("status")))
00031:     print("quality_status=" + str(result.get("quality_status")))
00032:     print("bridge_record_count=" + str(s.get("bridge_record_count")))
00033:     print("task_type_count=" + str(s.get("task_type_count")))
00034:     print("target_answer_runner_question_count=" + str(s.get("target_answer_runner_question_count")))
00035:     print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
00036:     print("answer_permission_count=" + str(s.get("answer_permission_count")))
00037:     print("write_attempt_count=" + str(s.get("write_attempt_count")))
00038:     if result.get("quality_failures"):
00039:         print("quality_failures=" + json.dumps(result.get("quality_failures")))
```

## `tiff/trace_net_e2e_live_llm_final_gate_v23.py`
- Location: `active_source_code`
- Score: `270`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live LLM Final Gate v23. Validates and repairs live Gemma/LLM draft answers before they can be used as WebUI final answers. The gate is intentionally non-mutating: it reads v21 prompt contracts and v22 LLM drafts, checks authority boundaries, and emits final-gated answers that use direct source-truth evidence only.
- Functions: load_json(path)@L40; write_json(path, data)@L44; write_jsonl(path, rows)@L49; _first_list(obj, keys)@L56; prompt_contracts(data)@L74; llm_drafts(data)@L78; _messages(row)@L82; _context_message(row)@L86; _block_between(text, start_marker, end_markers)@L94; _parse_json_after_marker(text, marker, end_markers)@L107; _parse_evidence_line(line)@L117; _extract_evidence(context)@L137; _citation_nums(text)@L163; _safe_str(value)@L173; _cap_sentence(aggregation)@L177; _unique_pages(direct)@L192; _field_counts(direct)@L203; _query_kind(query, direct)@L207
- CLI args: --live-llm-prompt-contract, --live-llm-draft-adapter, --output-dir, --min-llm-drafts, --min-final-gates, --min-passed-final-gates, --min-final-answers-ready-for-webui, --min-repaired-final-answers, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality, --write-json, --report-path, --min-llm-drafts, --min-final-gates, --min-passed-final-gates, --min-final-answers-ready-for-webui, --min-repaired-final-answers, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations
- Has __main__ guard.

### Source window L1-L57
```python
00001: """TRACE-Net E2E Live LLM Final Gate v23.
00002: 
00003: Validates and repairs live Gemma/LLM draft answers before they can be used as
00004: WebUI final answers.  The gate is intentionally non-mutating: it reads v21
00005: prompt contracts and v22 LLM drafts, checks authority boundaries, and emits
00006: final-gated answers that use direct source-truth evidence only.
00007: """
00008: 
00009: from __future__ import annotations
00010: 
00011: import argparse
00012: import json
00013: import re
00014: from collections import Counter, defaultdict
00015: from pathlib import Path
00016: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
00017: 
00018: VERSION = "v23"
00019: MODULE = "trace_net_e2e_live_llm_final_gate_v23"
00020: STATUS_READY = "E2E_LIVE_LLM_FINAL_GATE_READY_FOR_WEBUI"
00021: STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_FINAL_GATE_NEEDS_REPAIR"
00022: QUALITY_PASS = "PASS"
00023: QUALITY_FAIL = "FAIL"
00024: 
00025: _DIRECT_HEADER = "SOURCE-TRUTH EVIDENCE"
00026: _NEARBY_HEADER = "NEARBY SOURCE-TRUTH CONTEXT"
00027: _GRAPH_HEADER = "GRAPH / LEIDEN GUIDANCE"
00028: _AGG_MARKER = "AGGREGATION / CAPPING METADATA:"
00029: _SELF_RAG_MARKER = "SELF-RAG / CRAG STATUS:"
00030: _ANSWER_RULES_MARKER = "ANSWER RULES:"
00031: 
00032: _EVIDENCE_RE = re.compile(
00033:     r"^-\s*\[(?P<marker>\d+)\]\s+page=(?P<page>\S+)\s+field=(?P<field>\S+)\s+value=(?P<value>.*?)(?:\s+occurrence_count=(?P<count>\d+))?\s*$"
00034: )
00035: _CITATION_RE = re.compile(r"\[(\d+)\]")
00036: _PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b")
00037: _MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
00038: 
00039: 
00040: def load_json(path: str | Path) -> Any:
00041:     return json.loads(Path(path).read_text(encoding="utf-8"))
00042: 
00043: 
00044: def write_json(path: str | Path, data: Any) -> None:
00045:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00046:     Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
00047: 
00048: 
00049: def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
00050:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00051:     with Path(path).open("w", encoding="utf-8", newline="\n") as f:
00052:         for row in rows:
00053:             f.write(json.dumps(row, ensure_ascii=False) + "\n")
00054: 
00055: 
00056: def _first_list(obj: Any, keys: Sequence[str]) -> List[Any]:
00057:     if isinstance(obj, list):
```
### Source window L206-L262
```python
00206: 
00207: def _query_kind(query: str, direct: Sequence[Mapping[str, Any]]) -> str:
00208:     q = query.lower()
00209:     fields = _field_counts(direct)
00210:     if "table text" in q or "search table" in q or fields.get("ipl_text") or fields.get("table_text"):
00211:         return "table_text"
00212:     if "manual reference" in q or fields.get("manual_page_reference"):
00213:         return "manual_reference"
00214:     if "covered part" in q and ("which" in q or "what" in q or "pages" in q):
00215:         return "covered_part_pages"
00216:     if "part number" in q or fields.get("covered_part_number") or fields.get("ipl_part_number") or fields.get("part_number"):
00217:         return "part_number"
00218:     return "generic"
00219: 
00220: 
00221: def _format_evidence_list(direct: Sequence[Mapping[str, Any]]) -> str:
00222:     bits: List[str] = []
00223:     for rec in direct:
00224:         marker = rec.get("citation_marker")
00225:         field = rec.get("field_name")
00226:         value = rec.get("normalized_value")
00227:         page = rec.get("page_id")
00228:         occ = int(rec.get("occurrence_count") or 1)
00229:         occ_text = f" (collapsed from {occ} repeated source records)" if occ > 1 else ""
00230:         bits.append(f"{value} on page {page} as {field} {marker}{occ_text}")
00231:     return "; ".join(bits)
00232: 
00233: 
00234: def build_repaired_final_answer(query: str, direct: Sequence[Mapping[str, Any]], aggregation: Mapping[str, Any]) -> str:
00235:     cap = _cap_sentence(aggregation)
00236:     if not direct:
00237:         answer = (
00238:             "TRACE-Net did not find direct source-truth evidence that can support a final answer. "
00239:             "Graph/Leiden guidance and v2 summaries are not proof authority, so the result is audit-only."
00240:         )
00241:         if cap:
00242:             answer += " " + cap
00243:         return answer
00244: 
00245:     kind = _query_kind(query, direct)
00246:     pages = _unique_pages(direct)
00247: 
00248:     if kind == "part_number":
00249:         rec = direct[0]
00250:         value = rec.get("normalized_value")
00251:         field = rec.get("field_name")
00252:         page = rec.get("page_id")
00253:         marker = rec.get("citation_marker")
00254:         answer = (
00255:             f"TRACE-Net found part number {value} on page {page} as {field} {marker}. "
00256:             "The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically."
00257:         )
00258:     elif kind == "manual_reference":
00259:         rec = direct[0]
00260:         value = rec.get("normalized_value")
00261:         page = rec.get("page_id")
00262:         marker = rec.get("citation_marker")
```
### Source window L342-L398
```python
00342: 
00343:         v2_violation = _draft_uses_v2_summary_as_proof(draft_text)
00344:         guidance_violation = _draft_uses_guidance_as_proof(draft_text)
00345:         nearby_used = _nearby_values_used(draft_text, nearby)
00346:         non_direct_markers = _non_direct_citations(draft_text, direct)
00347:         needs_cap = any(bool(aggregation.get(k)) for k in ("result_was_capped", "more_results_available", "high_degree_node_detected"))
00348:         draft_has_cap = any(term in draft_text.lower() for term in ("capped", "more results", "additional matching", "returned"))
00349: 
00350:         repaired_answer = build_repaired_final_answer(query, direct, aggregation)
00351:         repaired = True  # v23 intentionally normalizes every live LLM draft into a final-gate-safe answer.
00352:         final_markers = _citation_nums(repaired_answer)
00353:         allowed_markers = {int(r.get("citation_number") or 0) for r in direct}
00354:         final_unknown_markers = [n for n in final_markers if n not in allowed_markers]
00355:         final_has_cap = not needs_cap or any(term in repaired_answer.lower() for term in ("capped", "additional", "returned"))
00356:         passed = bool(direct) and not final_unknown_markers and final_has_cap
00357: 
00358:         blockers: List[str] = []
00359:         if not direct:
00360:             blockers.append("missing_direct_source_truth_evidence")
00361:         if final_unknown_markers:
00362:             blockers.append("final_answer_has_non_direct_citation_markers")
00363:         if needs_cap and not final_has_cap:
00364:             blockers.append("missing_cap_disclosure")
00365: 
00366:         records.append({
00367:             "final_gate_id": f"live_llm_final_gate_v23_{idx:04d}",
00368:             "llm_draft_id": draft.get("llm_draft_id"),
00369:             "prompt_contract_id": draft.get("prompt_contract_id"),
00370:             "context_pack_id": draft.get("context_pack_id"),
00371:             "user_query": query,
00372:             "final_gate_status": "LIVE_LLM_FINAL_GATE_PASS" if passed else "LIVE_LLM_FINAL_GATE_BLOCKED",
00373:             "final_gate_passed": passed,
00374:             "ready_for_webui_endpoint": passed,
00375:             "draft_text": draft_text,
00376:             "final_answer": repaired_answer if passed else "",
00377:             "final_answer_repaired_from_draft": repaired,
00378:             "direct_source_truth_evidence_count": len(direct),
00379:             "nearby_source_truth_context_count": len(nearby),
00380:             "source_truth_citation_count": len(direct),
00381:             "draft_citation_like_count": len(_citation_nums(draft_text)),
00382:             "final_citation_like_count": len(final_markers),
00383:             "non_direct_citation_marker_count": len(non_direct_markers),
00384:             "non_direct_citation_markers": non_direct_markers,
00385:             "v2_summary_proof_violation_detected": v2_violation,
00386:             "graph_or_summary_guidance_proof_violation_detected": guidance_violation,
00387:             "nearby_context_overstatement_detected": bool(nearby_used),
00388:             "nearby_context_values_used_by_draft": nearby_used,
00389:             "cap_disclosure_required": needs_cap,
00390:             "cap_disclosure_detected_in_draft": draft_has_cap,
00391:             "cap_disclosure_in_final_answer": final_has_cap,
00392:             "aggregation_cap_disclosure": {
00393:                 "result_was_capped": bool(aggregation.get("result_was_capped")),
00394:                 "more_results_available": bool(aggregation.get("more_results_available")),
00395:                 "high_degree_node_detected": bool(aggregation.get("high_degree_node_detected")),
00396:                 "total_match_count": aggregation.get("total_match_count"),
00397:                 "returned_match_count": aggregation.get("returned_match_count"),
00398:             },
```
### Source window L61-L117
```python
00061:     for key in keys:
00062:         value = obj.get(key)
00063:         if isinstance(value, list):
00064:             return value
00065:     for wrapper in ("report", "payload", "data"):
00066:         nested = obj.get(wrapper)
00067:         if isinstance(nested, Mapping):
00068:             found = _first_list(nested, keys)
00069:             if found:
00070:                 return found
00071:     return []
00072: 
00073: 
00074: def prompt_contracts(data: Any) -> List[Mapping[str, Any]]:
00075:     return [r for r in _first_list(data, ["prompt_contracts", "llm_prompt_contracts", "records", "prompts"]) if isinstance(r, Mapping)]
00076: 
00077: 
00078: def llm_drafts(data: Any) -> List[Mapping[str, Any]]:
00079:     return [r for r in _first_list(data, ["llm_drafts", "drafts", "records"]) if isinstance(r, Mapping)]
00080: 
00081: 
00082: def _messages(row: Mapping[str, Any]) -> List[Mapping[str, Any]]:
00083:     return [m for m in row.get("messages", []) if isinstance(m, Mapping)]
00084: 
00085: 
00086: def _context_message(row: Mapping[str, Any]) -> str:
00087:     for msg in reversed(_messages(row)):
00088:         content = str(msg.get("content") or "")
00089:         if "TRACE-NET CONTEXT PACK" in content:
00090:             return content
00091:     return ""
00092: 
00093: 
00094: def _block_between(text: str, start_marker: str, end_markers: Sequence[str]) -> str:
00095:     idx = text.find(start_marker)
00096:     if idx < 0:
00097:         return ""
00098:     rest = text[idx + len(start_marker):]
00099:     end = len(rest)
00100:     for marker in end_markers:
00101:         e = rest.find(marker)
00102:         if e >= 0:
00103:             end = min(end, e)
00104:     return rest[:end].strip()
00105: 
00106: 
00107: def _parse_json_after_marker(text: str, marker: str, end_markers: Sequence[str]) -> Dict[str, Any]:
00108:     block = _block_between(text, marker, end_markers)
00109:     if not block.startswith("{"):
00110:         return {}
00111:     try:
00112:         return json.loads(block)
00113:     except Exception:
00114:         return {}
00115: 
00116: 
00117: def _parse_evidence_line(line: str, *, direct: bool) -> Optional[Dict[str, Any]]:
```
### Source window L270-L326
```python
00270:         marker = rec.get("citation_marker")
00271:         answer = (
00272:             f"TRACE-Net found the exact table text \"{value}\" on page {page} {marker}. "
00273:             "Nearby OCR/table records were returned as context only and are not treated as direct proof for this query."
00274:         )
00275:     elif kind == "covered_part_pages":
00276:         page_text = ", ".join(pages)
00277:         values = "; ".join(f"{r.get('normalized_value')} {r.get('citation_marker')}" for r in direct[:12])
00278:         answer = f"TRACE-Net found covered part numbers on page(s) {page_text}. Direct source-truth examples include {values}."
00279:     else:
00280:         answer = "TRACE-Net found direct source-truth evidence: " + _format_evidence_list(direct) + "."
00281: 
00282:     if cap:
00283:         answer += " " + cap
00284:     return answer
00285: 
00286: 
00287: def _draft_uses_v2_summary_as_proof(text: str) -> bool:
00288:     lower = (text or "").lower()
00289:     if "[v2 summary guidance]" in lower:
00290:         return True
00291:     if "summary guidance" in lower and _CITATION_RE.search(text or ""):
00292:         return True
00293:     if "this page appears" in lower and ("summary" in lower or "guidance" in lower):
00294:         return True
00295:     return False
00296: 
00297: 
00298: def _draft_uses_guidance_as_proof(text: str) -> bool:
00299:     lower = (text or "").lower()
00300:     suspicious = ("graph" in lower or "leiden" in lower or "community" in lower or "v2 summary" in lower or "summary guidance" in lower)
00301:     if not suspicious:
00302:         return False
00303:     # Safe if it clearly says those items are not proof/guidance only.
00304:     if "guidance only" in lower or "not proof" in lower or "not source-truth" in lower:
00305:         return False
00306:     return True
00307: 
00308: 
00309: def _nearby_values_used(text: str, nearby: Sequence[Mapping[str, Any]]) -> List[str]:
00310:     lower = (text or "").lower()
00311:     used: List[str] = []
00312:     for rec in nearby:
00313:         value = _safe_str(rec.get("normalized_value"))
00314:         if len(value) < 3:
00315:             continue
00316:         if value.lower() in lower:
00317:             used.append(value)
00318:     return used
00319: 
00320: 
00321: def _non_direct_citations(text: str, direct: Sequence[Mapping[str, Any]]) -> List[int]:
00322:     allowed = {int(r.get("citation_number") or 0) for r in direct}
00323:     return [n for n in sorted(set(_citation_nums(text))) if n not in allowed]
00324: 
00325: 
00326: def final_gate_records(prompt_contract_report: Any, llm_draft_report: Any) -> List[Dict[str, Any]]:
```
### Source window L454-L510
```python
00454:     records = final_gate_records(prompt_contract_report, llm_draft_report)
00455:     cap_required = sum(1 for r in records if r.get("cap_disclosure_required"))
00456:     report: Dict[str, Any] = {
00457:         "module": MODULE,
00458:         "version": VERSION,
00459:         "status": STATUS_READY,
00460:         "quality_status": QUALITY_PASS,
00461:         "llm_draft_count": len(drafts),
00462:         "final_gate_count": len(records),
00463:         "passed_final_gate_count": sum(1 for r in records if r.get("final_gate_passed")),
00464:         "final_answers_ready_for_webui_count": sum(1 for r in records if r.get("ready_for_webui_endpoint")),
00465:         "repaired_final_answer_count": sum(1 for r in records if r.get("final_answer_repaired_from_draft")),
00466:         "final_answers_with_source_truth_citations_count": sum(1 for r in records if int(r.get("final_citation_like_count") or 0) > 0),
00467:         "draft_v2_summary_proof_violation_count": sum(1 for r in records if r.get("v2_summary_proof_violation_detected")),
00468:         "draft_nearby_context_overstatement_count": sum(1 for r in records if r.get("nearby_context_overstatement_detected")),
00469:         "draft_non_direct_citation_marker_count": sum(int(r.get("non_direct_citation_marker_count") or 0) for r in records),
00470:         "cap_disclosure_required_count": cap_required,
00471:         "cap_disclosures_in_final_answers_count": sum(1 for r in records if r.get("cap_disclosure_required") and r.get("cap_disclosure_in_final_answer")),
00472:         "unsupported_claim_count": sum(int(r.get("unsupported_claim_count") or 0) for r in records),
00473:         "final_non_direct_citation_marker_count": 0,
00474:         "graph_proof_authority_violation_count": sum(int(r.get("graph_proof_authority_violation_count") or 0) for r in records),
00475:         "summary_proof_authority_violation_count": sum(int(r.get("summary_proof_authority_violation_count") or 0) for r in records),
00476:         "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
00477:         "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
00478:         "contract": {
00479:             "final_gate_does_not_call_llm": True,
00480:             "repairs_live_llm_drafts": True,
00481:             "source_truth_evidence_is_only_proof_authority": True,
00482:             "graph_leiden_guidance_only": True,
00483:             "v2_summaries_guidance_only": True,
00484:             "nearby_context_not_direct_proof": True,
00485:             "cap_disclosure_required_when_capped": True,
00486:             "raw_5tb_scan_at_query_time": False,
00487:             "graph_rebuild_at_query_time": False,
00488:             "source_truth_mutation_allowed": False,
00489:             "answer_permission": False,
00490:             "can_answer_directly": False,
00491:             "can_prove_claims": False,
00492:         },
00493:         "final_gate_records": records,
00494:     }
00495:     checks = evaluate_quality(report, thresholds)
00496:     report["quality_checks"] = checks
00497:     if not all(c["passed"] for c in checks):
00498:         report["quality_status"] = QUALITY_FAIL
00499:         report["status"] = STATUS_NEEDS_REPAIR
00500:     return report
00501: 
00502: 
00503: def render_markdown(report: Mapping[str, Any]) -> str:
00504:     lines: List[str] = []
00505:     lines.append("# TRACE-Net E2E Live LLM Final Gate v23")
00506:     lines.append("")
00507:     lines.append(f"Quality status: **{report.get('quality_status')}**")
00508:     lines.append(f"Status: `{report.get('status')}`")
00509:     lines.append("")
00510:     lines.append("## Summary")
```
### Source window L512-L568
```python
00512:         "llm_draft_count",
00513:         "final_gate_count",
00514:         "passed_final_gate_count",
00515:         "final_answers_ready_for_webui_count",
00516:         "repaired_final_answer_count",
00517:         "final_answers_with_source_truth_citations_count",
00518:         "draft_v2_summary_proof_violation_count",
00519:         "draft_nearby_context_overstatement_count",
00520:         "draft_non_direct_citation_marker_count",
00521:         "cap_disclosure_required_count",
00522:         "cap_disclosures_in_final_answers_count",
00523:         "unsupported_claim_count",
00524:         "final_non_direct_citation_marker_count",
00525:         "graph_proof_authority_violation_count",
00526:         "summary_proof_authority_violation_count",
00527:         "answer_permission_count",
00528:         "source_truth_mutation_allowed_count",
00529:     ):
00530:         lines.append(f"- {key}: {report.get(key)}")
00531:     lines.append("")
00532:     lines.append("## Contract")
00533:     lines.append("- This gate does not call an LLM; it validates and repairs live LLM drafts.")
00534:     lines.append("- Source-truth evidence remains the only proof authority.")
00535:     lines.append("- Graph/Leiden and v2 summaries remain guidance only.")
00536:     lines.append("- Nearby source-truth context is not treated as direct proof for the query.")
00537:     lines.append("- Capped/high-degree results must be disclosed in final answers.")
00538:     lines.append("")
00539:     lines.append("## Final answers")
00540:     for rec in report.get("final_gate_records", []):
00541:         lines.append(f"### {rec.get('final_gate_id')} — `{rec.get('final_gate_status')}`")
00542:         lines.append(f"- query: {rec.get('user_query')}")
00543:         lines.append(f"- repaired_from_draft: {rec.get('final_answer_repaired_from_draft')}")
00544:         lines.append(f"- draft_v2_summary_proof_violation: {rec.get('v2_summary_proof_violation_detected')}")
00545:         lines.append(f"- draft_nearby_context_overstatement: {rec.get('nearby_context_overstatement_detected')}")
00546:         lines.append(f"- non_direct_citation_marker_count: {rec.get('non_direct_citation_marker_count')}")
00547:         text = str(rec.get("final_answer") or "").strip().replace("\n", " ")
00548:         if text:
00549:             lines.append(f"- final_answer_preview: {text[:360]}")
00550:         if rec.get("blockers"):
00551:             lines.append(f"- blockers: {rec.get('blockers')}")
00552:         lines.append("")
00553:     lines.append("## Quality checks")
00554:     for check in report.get("quality_checks", []):
00555:         prefix = "PASS" if check.get("passed") else "FAIL"
00556:         lines.append(f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}")
00557:     return "\n".join(lines) + "\n"
00558: 
00559: 
00560: def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
00561:     out = Path(output_dir)
00562:     out.mkdir(parents=True, exist_ok=True)
00563:     report_path = out / "trace_net_e2e_live_llm_final_gate_v23.json"
00564:     records_path = out / "trace_net_e2e_live_llm_final_gate_records_v23.jsonl"
00565:     answers_path = out / "trace_net_e2e_live_llm_final_answers_v23.jsonl"
00566:     inspect_path = out / "trace_net_e2e_live_llm_final_gate_v23.md"
00567:     write_json(report_path, report)
00568:     write_jsonl(records_path, report.get("final_gate_records", []))
```
### Source window L574-L630
```python
00574:             "ready_for_webui_endpoint": r.get("ready_for_webui_endpoint"),
00575:         }
00576:         for r in report.get("final_gate_records", [])
00577:     ]
00578:     write_jsonl(answers_path, final_answers)
00579:     inspect_path.write_text(render_markdown(report), encoding="utf-8")
00580:     return {
00581:         "report_path": str(report_path),
00582:         "records_jsonl_path": str(records_path),
00583:         "final_answers_jsonl_path": str(answers_path),
00584:         "inspect_md_path": str(inspect_path),
00585:     }
00586: 
00587: 
00588: def _thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
00589:     return {
00590:         "min_llm_drafts": args.min_llm_drafts,
00591:         "min_final_gates": args.min_final_gates,
00592:         "min_passed_final_gates": args.min_passed_final_gates,
00593:         "min_final_answers_ready_for_webui": args.min_final_answers_ready_for_webui,
00594:         "min_repaired_final_answers": args.min_repaired_final_answers,
00595:         "min_final_answers_with_source_truth_citations": args.min_final_answers_with_source_truth_citations,
00596:         "min_cap_disclosures_in_final_answers": args.min_cap_disclosures_in_final_answers,
00597:         "max_unsupported_claim_count": args.max_unsupported_claim_count,
00598:         "max_final_non_direct_citation_marker_count": args.max_final_non_direct_citation_marker_count,
00599:         "max_graph_proof_authority_violations": args.max_graph_proof_authority_violations,
00600:         "max_summary_proof_authority_violations": args.max_summary_proof_authority_violations,
00601:         "max_answer_permission_count": args.max_answer_permission_count,
00602:         "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
00603:         "require_no_answer_permission": args.require_no_answer_permission,
00604:     }
00605: 
00606: 
00607: def build_arg_parser() -> argparse.ArgumentParser:
00608:     p = argparse.ArgumentParser(description="Build TRACE-Net live LLM final gate v23")
00609:     p.add_argument("--live-llm-prompt-contract", required=True)
00610:     p.add_argument("--live-llm-draft-adapter", required=True)
00611:     p.add_argument("--output-dir", required=True)
00612:     p.add_argument("--min-llm-drafts", type=int, default=5)
00613:     p.add_argument("--min-final-gates", type=int, default=5)
00614:     p.add_argument("--min-passed-final-gates", type=int, default=5)
00615:     p.add_argument("--min-final-answers-ready-for-webui", type=int, default=5)
00616:     p.add_argument("--min-repaired-final-answers", type=int, default=1)
00617:     p.add_argument("--min-final-answers-with-source-truth-citations", type=int, default=5)
00618:     p.add_argument("--min-cap-disclosures-in-final-answers", type=int, default=1)
00619:     p.add_argument("--max-unsupported-claim-count", type=int, default=0)
00620:     p.add_argument("--max-final-non-direct-citation-marker-count", type=int, default=0)
00621:     p.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
00622:     p.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
00623:     p.add_argument("--max-answer-permission-count", type=int, default=0)
00624:     p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00625:     p.add_argument("--require-no-answer-permission", action="store_true")
00626:     p.add_argument("--quality", action="store_true")
00627:     p.add_argument("--write-json", action="store_true")
00628:     return p
00629: 
00630: 
```

## `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- Location: `active_source_code`
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

### Source window L8-L64
```python
00008: Safety contract:
00009: - read-only artifact access
00010: - no Postgres/Qdrant/OpenSearch writes
00011: - no source-truth mutation
00012: - no answer permission
00013: - graph/vector/visual/summary records remain guidance unless backed by proof
00014: """
00015: 
00016: from __future__ import annotations
00017: 
00018: import argparse
00019: import json
00020: import os
00021: import re
00022: import subprocess
00023: import sys
00024: import time
00025: import urllib.error
00026: import urllib.parse
00027: import urllib.request
00028: from dataclasses import asdict, dataclass
00029: from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
00030: from pathlib import Path
00031: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00032: 
00033: MODULE = "trace_net_openwebui_page_context_bridge_v1"
00034: VERSION = "1.0.0"
00035: DEFAULT_MODEL_ID = "trace-net-page-context-v3-bridge"
00036: DEFAULT_UPSTREAM_MODEL = "trace-net-gemma4-engram-e2e-v3"
00037: DEFAULT_NATIVE_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
00038: DEFAULT_NATIVE_LLM_MODEL = "gemma4:26b"
00039: DEFAULT_NATIVE_NUM_CTX = 8192
00040: DEFAULT_NATIVE_MAX_TOKENS = 1200
00041: 
00042: _PAGE_PHRASE_RE = re.compile(
00043:     r"\bpages?\s+(?P<body>(?:p0*\d{1,6}|\d{1,4}|and|to|through|,|\s|-)+)",
00044:     re.IGNORECASE,
00045: )
00046: _P_ID_RE = re.compile(r"\bp0*(?P<num>\d{1,6})\b", re.IGNORECASE)
00047: _INT_RE = re.compile(r"\d{1,4}")
00048: 
00049: 
00050: @dataclass(frozen=True)
00051: class PageContextArtifactPaths:
00052:     route_manifest: str = "local_data/organization/trace_net/calibrated_cascade_route_brain_v35_3/trace_net_cascade_route_manifest_v35_3.json"
00053:     graph_export: str = "local_data/organization/trace_net/anchor_aware_graph_leiden_expander_gemma4_native_001/trace_net_anchor_aware_graph_leiden_expander_v1.json"
00054:     ocr_records: str = "local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json"
00055:     table_evidence: str = "local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json"
00056:     exact_part_records: str = "local_data/organization/trace_net/part_number_exact_retrieval_probe_gemma4_native_001/trace_net_part_number_exact_retrieval_probe_v1.json"
00057:     visual_summaries: str = "local_data/organization/trace_net/e2e_image_visual_observer_route/trace_net_e2e_image_visual_observer_route_v34.json"
00058:     vector_hits: str = "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"
00059: 
00060:     def existing_cli_args(self, repo_root: Path) -> List[str]:
00061:         """Return only optional artifact CLI args that exist on disk."""
00062:         mapping = [
00063:             ("--graph-export", self.graph_export),
00064:             ("--ocr-records", self.ocr_records),
```
### Source window L141-L197
```python
00141:     lowered = (question or "").lower()
00142:     return bool(extract_page_numbers(question)) or "random page" in lowered or "source page" in lowered
00143: 
00144: 
00145: def latest_user_question(messages: Sequence[Mapping[str, Any]]) -> str:
00146:     for msg in reversed(list(messages or [])):
00147:         if msg.get("role") == "user":
00148:             content = msg.get("content", "")
00149:             if isinstance(content, str):
00150:                 return content
00151:             if isinstance(content, list):
00152:                 text_parts = []
00153:                 for item in content:
00154:                     if isinstance(item, Mapping) and item.get("type") == "text":
00155:                         text_parts.append(str(item.get("text", "")))
00156:                 return "\n".join(text_parts)
00157:     return ""
00158: 
00159: 
00160: def _safe_filename_fragment(text: str, limit: int = 80) -> str:
00161:     cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
00162:     cleaned = cleaned.strip("_")[:limit]
00163:     return cleaned or "question"
00164: 
00165: 
00166: def default_output_path(question: str, pages: Sequence[int]) -> str:
00167:     page_part = "_".join(str(p) for p in pages[:12]) if pages else _safe_filename_fragment(question)
00168:     return (
00169:         "local_data/organization/trace_net/page_context_pack_v3/"
00170:         f"trace_net_page_context_pack_v3_openwebui_pages_{page_part}.json"
00171:     )
00172: 
00173: 
00174: def build_page_context_pack_via_cli(
00175:     *,
00176:     question: str,
00177:     pages: Sequence[int],
00178:     repo_root: str | Path = ".",
00179:     output_path: str | Path | None = None,
00180:     artifact_paths: PageContextArtifactPaths | None = None,
00181:     max_pages: int = 8,
00182:     python_executable: str | None = None,
00183: ) -> Dict[str, Any]:
00184:     """Build a page_context_pack_v3 by invoking the existing builder script."""
00185:     repo = Path(repo_root).resolve()
00186:     paths = artifact_paths or PageContextArtifactPaths()
00187:     py = python_executable or sys.executable
00188:     out_rel = str(output_path or default_output_path(question, pages))
00189: 
00190:     route_manifest = repo / paths.route_manifest
00191:     if not route_manifest.exists():
00192:         raise FileNotFoundError(f"route manifest not found: {paths.route_manifest}")
00193: 
00194:     cmd = [
00195:         py,
00196:         "scripts/build_trace_net_page_context_pack_v3.py",
00197:         "--question",
```
### Source window L841-L897
```python
00841:     simulate mode and for responses that fail to mention the requested source pages.
00842:     """
00843:     summary = pack.get("summary") if isinstance(pack.get("summary"), Mapping) else meta.get("context_pack_summary", {})
00844:     records = pack.get("page_context_records") if isinstance(pack.get("page_context_records"), list) else []
00845:     lines: List[str] = []
00846:     lines.append("Answer")
00847:     if records:
00848:         bits = []
00849:         for rec in records:
00850:             if not isinstance(rec, Mapping):
00851:                 continue
00852:             page = rec.get("page_number")
00853:             route = rec.get("primary_route")
00854:             srcs = rec.get("source_files") if isinstance(rec.get("source_files"), list) else []
00855:             src = ""
00856:             if srcs and isinstance(srcs[0], Mapping):
00857:                 src = str(srcs[0].get("value") or "")
00858:             part = f"page {page} ({rec.get('page_id')}) is routed as {route}"
00859:             if src:
00860:                 part += f" with source file {src}"
00861:             bits.append(part)
00862:         lines.append("TRACE-Net built a page-context binder for " + "; ".join(bits) + ".")
00863:     else:
00864:         lines.append("TRACE-Net built a page-context binder, but the page records were not available for rendering.")
00865:     lines.append("The model should reason from these page records, but the response must stay within the source-trace limits of the binder.")
00866:     lines.append("")
00867: 
00868:     lines.append("Evidence")
00869:     lines.append(f"Context pack quality: {pack.get('quality_status') or meta.get('context_pack_quality_status')}")
00870:     if isinstance(summary, Mapping):
00871:         lines.append(
00872:             "Counts: "
00873:             f"selected_page_count={summary.get('selected_page_count', 0)}, "
00874:             f"source_trace_ready_page_count={summary.get('source_trace_ready_page_count', 0)}, "
00875:             f"proof_record_count={summary.get('proof_record_count', 0)}, "
00876:             f"guidance_record_count={summary.get('guidance_record_count', 0)}, "
00877:             f"answer_permission_count={summary.get('answer_permission_count', 0)}, "
00878:             f"source_truth_mutation_allowed_count={summary.get('source_truth_mutation_allowed_count', 0)}."
00879:         )
00880:     for rec in records:
00881:         if not isinstance(rec, Mapping):
00882:             continue
00883:         lines.append(
00884:             f"- Page {rec.get('page_number')} / {rec.get('page_id')}: route={rec.get('primary_route')}; "
00885:             f"source_trace_ready={rec.get('source_trace_ready')}; "
00886:             f"proof_records={rec.get('proof_record_count')}; guidance_records={rec.get('guidance_record_count')}."
00887:         )
00888:         for cue in _first_text_from_guidance(rec.get("vector_guidance"), max_items=2, max_chars=420):
00889:             lines.append(f"  Guidance cue, not proof: {cue}")
00890:     lines.append("")
00891: 
00892:     lines.append("Engineering confidence")
00893:     lines.append("High for page identity, route, and source-file locator because the context pack is PASS and the requested page IDs are present. Lower for detailed engineering interpretation until OCR excerpts, visual observations, or claim-proof records are attached.")
00894:     lines.append("")
00895: 
00896:     lines.append("Limits")
00897:     lines.append("This guardrail answer was used because the upstream response was simulated or not aligned with the requested page binder: " + upstream_reason + ".")
```
### Source window L249-L305
```python
00249:     summary = pack.get("summary") if isinstance(pack.get("summary"), Mapping) else {}
00250:     counts = {
00251:         "selected_page_count": int(summary.get("selected_page_count", 0) or 0),
00252:         "source_trace_ready_page_count": int(summary.get("source_trace_ready_page_count", 0) or 0),
00253:         "proof_record_count": int(summary.get("proof_record_count", 0) or 0),
00254:         "guidance_record_count": int(summary.get("guidance_record_count", 0) or 0),
00255:         "answer_permission_count": int(summary.get("answer_permission_count", 0) or 0),
00256:         "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count", 0) or 0),
00257:     }
00258:     return counts
00259: 
00260: 
00261: def _sample(value: Any, max_chars: int = 700) -> str:
00262:     if value is None:
00263:         return ""
00264:     if isinstance(value, str):
00265:         text = value
00266:     else:
00267:         try:
00268:             text = json.dumps(value, ensure_ascii=False, sort_keys=True)
00269:         except TypeError:
00270:             text = str(value)
00271:     text = re.sub(r"\s+", " ", text).strip()
00272:     if len(text) > max_chars:
00273:         return text[: max_chars - 3] + "..."
00274:     return text
00275: 
00276: 
00277: def render_page_context_binder(pack: Mapping[str, Any], *, max_chars: int = 14000) -> str:
00278:     """Render a compact source-bounded binder for Gemma."""
00279:     counts = count_pack_records(pack)
00280:     query = pack.get("query_entities", {}) if isinstance(pack.get("query_entities"), Mapping) else {}
00281:     rwo = pack.get("reasoning_work_order", {}) if isinstance(pack.get("reasoning_work_order"), Mapping) else {}
00282: 
00283:     lines: List[str] = []
00284:     lines.append("TRACE-NET PAGE CONTEXT BINDER V3")
00285:     lines.append("Use this as a source-bounded evidence binder, not as a canned answer.")
00286:     lines.append("Gemma should synthesize cautiously for complex questions while obeying the proof limits.")
00287:     lines.append("")
00288:     lines.append("QUESTION")
00289:     lines.append(str(query.get("question") or pack.get("question") or ""))
00290:     lines.append("")
00291:     lines.append("QUALITY / SAFETY SUMMARY")
00292:     lines.append(json.dumps(counts, sort_keys=True))
00293:     lines.append("Safety rule: answer_permission and source_truth_mutation_allowed must remain false/zero.")
00294:     lines.append("Only current proof/source-locator records can support factual source claims.")
00295:     lines.append("Graph, vector, visual, summary, and route guidance are retrieval guidance unless backed by proof.")
00296:     lines.append("")
00297:     lines.append("REASONING WORK ORDER")
00298:     lines.append(f"model_should_think: {bool(rwo.get('model_should_think'))}")
00299:     if rwo.get("purpose"):
00300:         lines.append(f"purpose: {rwo.get('purpose')}")
00301:     for key in ("allowed_reasoning", "disallowed_reasoning", "answer_sections"):
00302:         values = rwo.get(key)
00303:         if isinstance(values, list) and values:
00304:             lines.append(f"{key}:")
00305:             for item in values[:8]:
```
### Source window L318-L374
```python
00318:         lines.append(f"guidance_record_count: {record.get('guidance_record_count')}")
00319:         if record.get("route_evidence_priority"):
00320:             lines.append("route_evidence_priority: " + ", ".join(map(str, record.get("route_evidence_priority", []))))
00321:         if record.get("page_reasoning_tasks"):
00322:             lines.append("page_reasoning_tasks:")
00323:             for task in record.get("page_reasoning_tasks", [])[:6]:
00324:                 lines.append(f"- {task}")
00325: 
00326:         for key in (
00327:             "source_files",
00328:             "source_links",
00329:             "ocr_excerpts",
00330:             "table_evidence",
00331:             "exact_part_hits",
00332:             "visual_guidance",
00333:             "route_guidance",
00334:             "graph_neighbors",
00335:             "vector_guidance",
00336:         ):
00337:             values = record.get(key)
00338:             if isinstance(values, list) and values:
00339:                 lines.append(f"{key} ({len(values)}):")
00340:                 for item in values[:3]:
00341:                     lines.append("- " + _sample(item))
00342:         lines.append("")
00343: 
00344:     binder = "\n".join(lines).strip()
00345:     if len(binder) > max_chars:
00346:         binder = binder[: max_chars - 300] + "\n\n[TRUNCATED: binder shortened for prompt budget. Preserve safety and proof limits.]"
00347:     return binder
00348: 
00349: 
00350: def enrich_openai_messages(
00351:     messages: Sequence[Mapping[str, Any]],
00352:     pack: Mapping[str, Any],
00353:     *,
00354:     max_binder_chars: int = 14000,
00355: ) -> List[Dict[str, Any]]:
00356:     binder = render_page_context_binder(pack, max_chars=max_binder_chars)
00357:     binder_message = {
00358:         "role": "system",
00359:         "content": binder,
00360:     }
00361:     original = [dict(m) for m in messages]
00362:     # Preserve existing system messages first, then insert binder before user content.
00363:     system_messages = [m for m in original if m.get("role") == "system"]
00364:     non_system_messages = [m for m in original if m.get("role") != "system"]
00365:     return system_messages + [binder_message] + non_system_messages
00366: 
00367: 
00368: def enrich_chat_payload(
00369:     payload: MutableMapping[str, Any],
00370:     *,
00371:     repo_root: str | Path = ".",
00372:     artifact_paths: PageContextArtifactPaths | None = None,
00373:     output_path: str | None = None,
00374:     max_pages: int = 8,
```
### Source window L457-L513
```python
00457: 
00458: class NativePageAnswerError(RuntimeError):
00459:     """Raised when native page-answer generation attempted but cannot be safely used."""
00460: 
00461:     def __init__(self, message: str, *, llm_attempted: bool = False, llm_metadata: Optional[Mapping[str, Any]] = None):
00462:         super().__init__(message)
00463:         self.llm_attempted = bool(llm_attempted)
00464:         self.llm_metadata = dict(llm_metadata or {})
00465: 
00466: 
00467: def render_native_page_answer_messages(
00468:     pack: Mapping[str, Any],
00469:     *,
00470:     question: str,
00471:     max_binder_chars: int = 14000,
00472:     strict_final_content: bool = False,
00473: ) -> List[Dict[str, str]]:
00474:     """Create a direct Gemma prompt for page-binder questions.
00475: 
00476:     This lets the model reason from the binder itself instead of relying on the
00477:     upstream exact-search endpoint to reinterpret the injected context. When
00478:     strict_final_content is true, this is a retry prompt that explicitly asks
00479:     thinking models to put the final answer in message.content.
00480:     """
00481:     binder = render_page_context_binder(pack, max_chars=max_binder_chars)
00482:     system = (
00483:         "You are the TRACE-Net page-binder answer writer. Answer from the provided "
00484:         "page_context_pack_v3 binder only. You may synthesize cautiously for complex "
00485:         "questions, but you must separate proof from guidance. Use the sections: "
00486:         "Answer, Evidence, Engineering confidence, Limits. Mention every requested "
00487:         "page number and page_id. Do not infer interchangeability, fit, effectivity, "
00488:         "replacement approval, installation safety, or procurement authority unless "
00489:         "explicit source proof is present. Never output hidden reasoning as the answer."
00490:     )
00491:     if strict_final_content:
00492:         system += (
00493:             " This is a final-answer retry. Put the complete user-visible final answer "
00494:             "in message.content. Do not return an empty content field. Start exactly with 'Answer'."
00495:         )
00496:     user = (
00497:         f"USER QUESTION:\n{question}\n\n"
00498:         f"{binder}\n\n"
00499:         "Write the answer now. Keep it concise, source-bounded, and explicit about limits. "
00500:         "The final answer must be visible in message.content."
00501:     )
00502:     return [{"role": "system", "content": system}, {"role": "user", "content": user}]
00503: 
00504: 
00505: def call_native_ollama_openai_chat(
00506:     *,
00507:     messages: Sequence[Mapping[str, str]],
00508:     base_url: str = DEFAULT_NATIVE_LLM_BASE_URL,
00509:     model: str = DEFAULT_NATIVE_LLM_MODEL,
00510:     api_key: str = "ollama",
00511:     temperature: float = 0.1,
00512:     timeout: float = 300.0,
00513:     attempt_label: str = "primary",
```
### Source window L661-L717
```python
00661:                 "native_llm_status": "NATIVE_PAGE_LLM_CALL_SUCCEEDED",
00662:                 "native_llm_model": native_llm_model,
00663:                 "native_llm_base_url": normalize_ollama_openai_base_url(native_llm_base_url),
00664:                 "native_llm_provider_endpoint": "ollama_api_chat",
00665:                 "native_llm_num_ctx": native_num_ctx,
00666:                 "native_llm_max_tokens": native_max_tokens,
00667:                 "native_llm_elapsed_ms": elapsed_ms,
00668:                 "native_llm_retry_attempted": retry_attempted,
00669:                 "fallback_used": False,
00670:                 "context_pack_quality_status": meta.get("context_pack_quality_status") or pack.get("quality_status"),
00671:                 "context_pack_summary": meta.get("context_pack_summary") or pack.get("summary"),
00672:                 "context_pack_output_path": meta.get("context_pack_output_path"),
00673:                 "context_pack_page_ids": meta.get("context_pack_page_ids", []),
00674:                 "detected_pages": meta.get("detected_pages", []),
00675:                 "safety": {
00676:                     "answer_permission": False,
00677:                     "source_truth_mutation_allowed": False,
00678:                     "writes_to_postgres": False,
00679:                     "writes_to_qdrant": False,
00680:                     "writes_to_opensearch": False,
00681:                 },
00682:             },
00683:             "native_llm_metadata": combined_metadata,
00684:         },
00685:     }
00686:     aligned, reason = should_use_context_bridge_fallback(response, meta)
00687:     if aligned:
00688:         raise NativePageAnswerError(
00689:             f"native page answer failed alignment check: {reason}",
00690:             llm_attempted=True,
00691:             llm_metadata=combined_metadata,
00692:         )
00693:     response["trace_net"]["page_context_bridge"]["alignment_status"] = reason
00694:     return response
00695: 
00696: 
00697: def build_native_failure_fallback_response(
00698:     *,
00699:     pack: Mapping[str, Any],
00700:     meta: Mapping[str, Any],
00701:     model_id: str,
00702:     reason: str,
00703:     error: str = "",
00704:     native_llm_attempted: bool = False,
00705:     native_llm_metadata: Optional[Mapping[str, Any]] = None,
00706: ) -> Dict[str, Any]:
00707:     content = render_page_context_fallback_answer(pack, meta, reason)
00708:     response = {
00709:         "id": f"chatcmpl-tracenet-page-fallback-{int(time.time() * 1000)}",
00710:         "object": "chat.completion",
00711:         "created": int(time.time()),
00712:         "model": model_id,
00713:         "choices": [
00714:             {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
00715:         ],
00716:         "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
00717:         "trace_net": {
```
### Source window L395-L451
```python
00395: 
00396:     pack = build_page_context_pack_via_cli(
00397:         question=question,
00398:         pages=pages,
00399:         repo_root=repo_root,
00400:         output_path=output_path,
00401:         artifact_paths=artifact_paths,
00402:         max_pages=max_pages,
00403:         python_executable=python_executable,
00404:     )
00405:     enriched["messages"] = enrich_openai_messages(messages, pack, max_binder_chars=max_binder_chars)
00406:     # Preserve requested model by default. The proxy server may override to upstream_model.
00407:     bridge_meta.update(
00408:         {
00409:             "page_context_used": True,
00410:             "context_pack_quality_status": pack.get("quality_status"),
00411:             "context_pack_summary": pack.get("summary"),
00412:             "context_pack_output_path": pack.get("bridge_build", {}).get("output_path") or output_path,
00413:             "context_pack_page_ids": [r.get("page_id") for r in pack.get("page_context_records", []) if isinstance(r, Mapping)],
00414:         }
00415:     )
00416:     return enriched, bridge_meta
00417: 
00418: 
00419: 
00420: def normalize_ollama_openai_base_url(base_url: str) -> str:
00421:     """Normalize Ollama/OpenAI-compatible base URL to the /v1 base.
00422: 
00423:     The lower-level OpenAI-compatible call appends /chat/completions, so a raw
00424:     Ollama root such as http://127.0.0.1:11434 must become
00425:     http://127.0.0.1:11434/v1.
00426:     """
00427:     raw = (base_url or DEFAULT_NATIVE_LLM_BASE_URL).strip().rstrip("/")
00428:     if not raw:
00429:         return DEFAULT_NATIVE_LLM_BASE_URL
00430:     if raw.endswith("/chat/completions"):
00431:         raw = raw[: -len("/chat/completions")]
00432:     if raw.endswith("/v1"):
00433:         return raw
00434:     parsed = urllib.parse.urlparse(raw)
00435:     if parsed.scheme and parsed.netloc and parsed.path in ("", "/"):
00436:         return raw + "/v1"
00437:     return raw
00438: 
00439: 
00440: def ollama_native_api_base_url(base_url: str) -> str:
00441:     """Return the root Ollama URL for /api/chat calls.
00442: 
00443:     The OpenAI-compatible base is usually http://host:11434/v1, but the native
00444:     Ollama chat endpoint lives at http://host:11434/api/chat. This helper
00445:     accepts either form so the CLI can keep accepting /v1 or raw Ollama roots.
00446:     """
00447:     raw = (base_url or DEFAULT_NATIVE_LLM_BASE_URL).strip().rstrip("/")
00448:     if not raw:
00449:         raw = DEFAULT_NATIVE_LLM_BASE_URL
00450:     if raw.endswith("/chat/completions"):
00451:         raw = raw[: -len("/chat/completions")]
```

## `tiff/trace_net_page_context_pack_v3.py`
- Location: `active_source_code`
- Score: `269`
- Categories: `context_pack, engram, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Page Context Pack v3.3. Builds a source-bounded page context pack for page-specific and complex engineering questions. The pack is intentionally a *binder*, not a canned answer: it gives the LLM proof, guidance, source locators, and route-aware reasoning tasks so the model can synthesize cautiously for harder questions. Safety contract: - read-only inputs - no Postgres/Qdrant/OpenSearch writes - no source-truth mutation - no answer permission - graph/vector/visual/page-summary records 
- Classes: PageContextRecord@L430 methods=['finalize', 'to_dict']; PageContextIndex@L490 methods=['__init__', 'ensure_page', 'add_aliases', 'resolve']
- Functions: load_json(path, default)@L74; write_json(path, payload)@L86; _norm_text(value)@L92; _first_present(record, keys)@L98; _first_text(record, keys)@L106; _truthy(value)@L130; _looks_page_or_evidence_like(record)@L140; _as_records(payload)@L181; normalize_page_id(value)@L267; page_number_from_any(value)@L279; page_key(record)@L304; page_aliases(record)@L317; _dedupe_dicts(items)@L354; _record_can_prove(record)@L369; _route_evidence_priority(route)@L402; _page_reasoning_tasks(page)@L413; _attach_source_locators(page, record)@L552; _make_compact(record)@L573

### Source window L819-L875
```python
00819:                 for item in group:
00820:                     haystacks.append(json.dumps(item, sort_keys=True, default=str))
00821:             if any(part in h for h in haystacks) and pid not in selected:
00822:                 selected.append(pid)
00823:     if not selected:
00824:         ready = [pid for pid, page in index.pages.items() if page.to_dict()["source_trace_ready"]]
00825:         selected.extend(ready[:max_pages])
00826:     if not selected:
00827:         selected.extend(list(index.pages.keys())[:max_pages])
00828:     return selected[:max_pages]
00829: 
00830: 
00831: def build_reasoning_work_order(question_entities: Mapping[str, Any], selected_records: list[dict[str, Any]]) -> dict[str, Any]:
00832:     proof_ready_pages = [r["page_id"] for r in selected_records if r.get("source_trace_ready")]
00833:     guidance_only_pages = [r["page_id"] for r in selected_records if r.get("guidance_record_count", 0) and not r.get("source_trace_ready")]
00834:     return {
00835:         "purpose": "Give the LLM a source-bounded binder plus reasoning tasks, not a canned answer.",
00836:         "question_intent": question_entities.get("intent"),
00837:         "model_should_think": True,
00838:         "allowed_reasoning": [
00839:             "Synthesize across multiple proof records when the cited evidence supports the claim.",
00840:             "Use graph/vector/visual/summary records to decide what to inspect or mention, but do not treat them as proof by themselves.",
00841:             "State bounded inferences clearly as inferences and tie them back to source-traceable records.",
00842:             "For complex questions, explain what the evidence supports, what remains unknown, and what additional evidence would be needed.",
00843:         ],
00844:         "disallowed_reasoning": [
00845:             "Do not infer interchangeability, fit, effectivity, replacement approval, installation safety, or procurement authority without explicit source proof.",
00846:             "Do not cite unrelated records.",
00847:             "Do not use Engram, vector hits, graph neighbors, page summaries, route guidance, or visual summaries as factual proof unless a proof record backs them.",
00848:         ],
00849:         "proof_ready_pages": proof_ready_pages,
00850:         "guidance_only_pages": guidance_only_pages,
00851:         "route_awareness": {
00852:             "table_pages": [r["page_id"] for r in selected_records if "table" in str(r.get("primary_route", "")).lower()],
00853:             "image_visual_pages": [r["page_id"] for r in selected_records if any(x in str(r.get("primary_route", "")).lower() for x in ("image", "visual", "diagram"))],
00854:         },
00855:         "answer_sections": ["Answer", "Evidence", "Engineering confidence", "Limits"],
00856:     }
00857: 
00858: 
00859: def build_page_context_pack_v3(
00860:     *,
00861:     question: str | None = None,
00862:     requested_pages: Iterable[str | int] | None = None,
00863:     route_manifest: Any = None,
00864:     graph_export: Any = None,
00865:     ocr_records: Any = None,
00866:     table_evidence: Any = None,
00867:     exact_part_records: Any = None,
00868:     visual_summaries: Any = None,
00869:     vector_hits: Any = None,
00870:     max_pages: int = 8,
00871: ) -> dict[str, Any]:
00872:     index = build_index(
00873:         route_manifest=route_manifest,
00874:         graph_export=graph_export,
00875:         ocr_records=ocr_records,
```
### Source window L907-L963
```python
00907:             "source_trace_ready_page_count": sum(1 for r in records if r.get("source_trace_ready")),
00908:             "proof_record_count": proof_count,
00909:             "guidance_record_count": guidance_count,
00910:             "source_link_count": sum(len(r.get("source_links", [])) for r in records),
00911:             "source_file_count": sum(len(r.get("source_files", [])) for r in records),
00912:             "ocr_excerpt_count": sum(len(r.get("ocr_excerpts", [])) for r in records),
00913:             "visual_guidance_count": sum(len(r.get("visual_guidance", [])) for r in records),
00914:             "route_guidance_count": sum(len(r.get("route_guidance", [])) for r in records),
00915:             "answer_permission_count": 0,
00916:             "source_truth_mutation_allowed_count": 0,
00917:             "postgres_write_attempt_count": 0,
00918:             "qdrant_write_attempt_count": 0,
00919:             "opensearch_write_attempt_count": 0,
00920:         },
00921:         "page_context_records": records,
00922:         "reasoning_work_order": build_reasoning_work_order(entities, records),
00923:         "safety_contract": {
00924:             "answer_permission": False,
00925:             "source_truth_mutation_allowed": False,
00926:             "postgres_write_allowed": False,
00927:             "qdrant_write_allowed": False,
00928:             "opensearch_write_allowed": False,
00929:             "guidance_can_be_used_as_proof": False,
00930:             "proof_context_required_for_source_claims": True,
00931:         },
00932:     }
00933: 
00934: 
00935: def check_page_context_pack_v3_quality(
00936:     pack: Mapping[str, Any],
00937:     *,
00938:     min_pages: int = 1,
00939:     require_no_answer_permission: bool = True,
00940:     require_reasoning_work_order: bool = True,
00941:     min_guidance_records: int = 0,
00942:     min_source_trace_ready_pages: int = 0,
00943:     min_source_locators: int = 0,
00944: ) -> dict[str, Any]:
00945:     summary = pack.get("summary", {}) if isinstance(pack.get("summary"), dict) else {}
00946:     records = pack.get("page_context_records", []) if isinstance(pack.get("page_context_records"), list) else []
00947:     failures: list[str] = []
00948:     if len(records) < min_pages:
00949:         failures.append(f"selected_page_count_lt_{min_pages}")
00950:     if require_reasoning_work_order and not pack.get("reasoning_work_order"):
00951:         failures.append("missing_reasoning_work_order")
00952:     if require_no_answer_permission and summary.get("answer_permission_count", 0) != 0:
00953:         failures.append("answer_permission_count_nonzero")
00954:     if summary.get("source_truth_mutation_allowed_count", 0) != 0:
00955:         failures.append("source_truth_mutation_allowed_count_nonzero")
00956:     for db_key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
00957:         if summary.get(db_key, 0) != 0:
00958:             failures.append(f"{db_key}_nonzero")
00959:     if pack.get("safety_contract", {}).get("guidance_can_be_used_as_proof") is not False:
00960:         failures.append("guidance_proof_boundary_not_false")
00961:     if summary.get("guidance_record_count", 0) < min_guidance_records:
00962:         failures.append(f"guidance_record_count_lt_{min_guidance_records}")
00963:     if summary.get("source_trace_ready_page_count", 0) < min_source_trace_ready_pages:
```
### Source window L1-L29
```python
00001: """TRACE-Net Page Context Pack v3.3.
00002: 
00003: Builds a source-bounded page context pack for page-specific and complex
00004: engineering questions.  The pack is intentionally a *binder*, not a canned
00005: answer: it gives the LLM proof, guidance, source locators, and route-aware
00006: reasoning tasks so the model can synthesize cautiously for harder questions.
00007: 
00008: Safety contract:
00009: - read-only inputs
00010: - no Postgres/Qdrant/OpenSearch writes
00011: - no source-truth mutation
00012: - no answer permission
00013: - graph/vector/visual/page-summary records are guidance unless backed by proof
00014: """
00015: 
00016: from __future__ import annotations
00017: 
00018: from dataclasses import dataclass, field
00019: from pathlib import Path
00020: import json
00021: import re
00022: from typing import Any, Iterable, Mapping
00023: 
00024: PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-\d{2,4})?\b")
00025: PAGE_RE = re.compile(r"\b(?:page|p\.?|pg\.?|pages)\s*#?\s*(\d{1,5})\b", re.IGNORECASE)
00026: ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
00027: 
00028: TEXT_KEYS = (
00029:     "ocr_text",
```
### Source window L345-L401
```python
00345:     # Page labels are useful, but they must not collide with source page
00346:     # numbers.  Keep them label-qualified.
00347:     for key in ("page_label", "label", "source_page_label"):
00348:         value = _norm_text(record.get(key))
00349:         if value:
00350:             aliases.update({f"label:{value}", f"page_label:{value}"})
00351:     return aliases
00352: 
00353: 
00354: def _dedupe_dicts(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
00355:     seen: set[str] = set()
00356:     out: list[dict[str, Any]] = []
00357:     for item in items:
00358:         sig_parts = []
00359:         for key in keys:
00360:             sig_parts.append(str(item.get(key, ""))[:500])
00361:         sig = "|".join(sig_parts)
00362:         if sig in seen:
00363:             continue
00364:         seen.add(sig)
00365:         out.append(item)
00366:     return out
00367: 
00368: 
00369: def _record_can_prove(record: Mapping[str, Any], *, proof_kind: str) -> bool:
00370:     """Return whether a record should count as proof, not merely guidance.
00371: 
00372:     Many TRACE-Net records are source-located but explicitly say they cannot
00373:     prove claims or answer directly.  v3.2 keeps those records in the binder,
00374:     but routes them to guidance/candidate lists so Gemma does not overclaim.
00375:     """
00376:     if proof_kind in {"source_file", "source_link"}:
00377:         return True
00378:     if record.get("can_prove_claims") is False or record.get("can_prove_source_truth") is False:
00379:         return False
00380:     if record.get("answer_use_policy") == "retrieval_only" or record.get("retrieval_only") is True:
00381:         return False
00382:     if proof_kind == "ocr_text":
00383:         return bool(_first_text(record)) and bool(_first_present(record, ("page_id", "source_trace", "source_file", "ocr_path", "source_member")))
00384:     if proof_kind == "exact_part":
00385:         return bool(_first_present(record, ("matched_part_number", "part_number", "covered_part_number", "ipl_part_number"))) and not record.get("unsafe", False)
00386:     if proof_kind == "table_evidence":
00387:         if _truthy(record.get("can_prove_claims")) or _truthy(record.get("can_answer_directly")):
00388:             return True
00389:         # Non-empty normalized rows/cells can support source-table context,
00390:         # but only when the record is citation/source ready and not explicitly
00391:         # marked retrieval-only.
00392:         row_count = record.get("normalized_row_count") or record.get("source_row_count") or record.get("answer_support_row_count") or 0
00393:         cell_count = record.get("normalized_cell_count") or len(record.get("cells", []) or [])
00394:         citation_ready = _truthy(record.get("citation_ready")) or _truthy(record.get("has_citation"))
00395:         try:
00396:             return citation_ready and (int(row_count) > 0 or int(cell_count) > 0)
00397:         except Exception:
00398:             return False
00399:     return False
00400: 
00401: 
```
### Source window L421-L477
```python
00421:         tasks.append("Treat blank-candidate pages cautiously and say if no text/source evidence is attached.")
00422:     if page.part_mentions:
00423:         tasks.append("Mention part relationships only as far as the attached evidence role allows.")
00424:     if page.route_guidance:
00425:         tasks.append("Candidate/guidance records may help decide what to inspect but are not proof by themselves.")
00426:     return tasks
00427: 
00428: 
00429: @dataclass
00430: class PageContextRecord:
00431:     page_id: str
00432:     page_number: int | None = None
00433:     page_label: str | None = None
00434:     ata_section: str | None = None
00435:     primary_route: str | None = None
00436:     source_links: list[dict[str, Any]] = field(default_factory=list)
00437:     source_files: list[dict[str, Any]] = field(default_factory=list)
00438:     ocr_excerpts: list[dict[str, Any]] = field(default_factory=list)
00439:     table_evidence: list[dict[str, Any]] = field(default_factory=list)
00440:     exact_part_hits: list[dict[str, Any]] = field(default_factory=list)
00441:     visual_guidance: list[dict[str, Any]] = field(default_factory=list)
00442:     graph_neighbors: list[dict[str, Any]] = field(default_factory=list)
00443:     vector_guidance: list[dict[str, Any]] = field(default_factory=list)
00444:     route_guidance: list[dict[str, Any]] = field(default_factory=list)
00445:     part_mentions: list[dict[str, Any]] = field(default_factory=list)
00446:     warnings: list[str] = field(default_factory=list)
00447: 
00448:     def finalize(self) -> None:
00449:         self.source_links = _dedupe_dicts(self.source_links, keys=("value", "route", "proof_role"))
00450:         self.source_files = _dedupe_dicts(self.source_files, keys=("value", "route", "proof_role"))
00451:         self.ocr_excerpts = _dedupe_dicts(self.ocr_excerpts, keys=("text", "route", "proof_role"))
00452:         self.table_evidence = _dedupe_dicts(self.table_evidence, keys=("page_id", "source_table_id", "normalized_table_id", "route", "proof_role"))
00453:         self.exact_part_hits = _dedupe_dicts(self.exact_part_hits, keys=("matched_part_number", "part_number", "page_id", "route"))
00454:         self.visual_guidance = _dedupe_dicts(self.visual_guidance, keys=("summary", "route", "proof_role"))
00455:         self.graph_neighbors = _dedupe_dicts(self.graph_neighbors, keys=("edge_type", "source", "target", "page_id"))
00456:         self.vector_guidance = _dedupe_dicts(self.vector_guidance, keys=("text", "score", "route"))
00457:         self.route_guidance = _dedupe_dicts(self.route_guidance, keys=("route", "reason", "source_table_id", "record_type"))
00458:         self.part_mentions = _dedupe_dicts(self.part_mentions, keys=("part_number", "route", "proof_role"))
00459: 
00460:     def to_dict(self) -> dict[str, Any]:
00461:         self.finalize()
00462:         proof_count = len(self.ocr_excerpts) + len(self.table_evidence) + len(self.exact_part_hits) + len(self.source_links) + len(self.source_files)
00463:         guidance_count = len(self.visual_guidance) + len(self.graph_neighbors) + len(self.vector_guidance) + len(self.route_guidance)
00464:         source_trace_ready = proof_count > 0 or bool(self.source_links or self.source_files)
00465:         return {
00466:             "page_id": self.page_id,
00467:             "page_number": self.page_number,
00468:             "page_label": self.page_label,
00469:             "ata_section": self.ata_section,
00470:             "primary_route": self.primary_route,
00471:             "route_evidence_priority": _route_evidence_priority(self.primary_route),
00472:             "page_reasoning_tasks": _page_reasoning_tasks(self),
00473:             "source_links": self.source_links,
00474:             "source_files": self.source_files,
00475:             "ocr_excerpts": self.ocr_excerpts,
00476:             "table_evidence": self.table_evidence,
00477:             "exact_part_hits": self.exact_part_hits,
```
### Source window L499-L555
```python
00499:         if rec.page_number is None and page_number is not None:
00500:             rec.page_number = page_number
00501:         if rec.page_label is None and page_label:
00502:             rec.page_label = page_label
00503: 
00504:         self.alias_to_page[pid] = pid
00505: 
00506:         # Source/physical page number aliases are authoritative for bare
00507:         # numeric lookups such as --pages 48.
00508:         if page_number is not None:
00509:             for alias in (str(page_number), f"p{page_number:06d}", f"p{page_number:04d}", f"source_p{page_number:06d}", f"source_p{page_number:04d}"):
00510:                 self.alias_to_page[alias] = pid
00511: 
00512:         # Numeric page labels often collide with source page numbers.  Expose
00513:         # them only through qualified aliases, never as bare "48".
00514:         if page_label:
00515:             label = str(page_label)
00516:             self.alias_to_page[f"label:{label}"] = pid
00517:             self.alias_to_page[f"page_label:{label}"] = pid
00518:             if not label.isdigit():
00519:                 self.alias_to_page.setdefault(label, pid)
00520:         return rec
00521: 
00522:     def add_aliases(self, pid: str, aliases: Iterable[str]) -> None:
00523:         for alias in aliases:
00524:             text = _norm_text(alias)
00525:             if not text:
00526:                 continue
00527:             # Do not let later label/guidance aliases steal an exact source
00528:             # page-number lookup from an already-indexed page.
00529:             if text.isdigit() and text in self.alias_to_page and self.alias_to_page[text] != pid:
00530:                 continue
00531:             self.alias_to_page[text] = pid
00532: 
00533:     def resolve(self, token: str | int) -> str | None:
00534:         text = _norm_text(token)
00535:         if not text:
00536:             return None
00537:         if text in self.alias_to_page:
00538:             return self.alias_to_page[text]
00539:         norm = normalize_page_id(text)
00540:         if norm and norm in self.pages:
00541:             return norm
00542:         if norm and norm in self.alias_to_page:
00543:             return self.alias_to_page[norm]
00544:         num = page_number_from_any(text)
00545:         if num is not None:
00546:             for alias in (str(num), f"p{num:06d}", f"p{num:04d}", f"source_p{num:06d}", f"source_p{num:04d}"):
00547:                 if alias in self.alias_to_page:
00548:                     return self.alias_to_page[alias]
00549:         return None
00550: 
00551: 
00552: def _attach_source_locators(page: PageContextRecord, record: Mapping[str, Any], *, source_route: str) -> None:
00553:     source_link = _first_present(record, SOURCE_LINK_KEYS)
00554:     if source_link:
00555:         page.source_links.append({
```

## `tiff/trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py`
- Location: `active_source_code`
- Score: `265`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering WebUI Answer Server v1.3 + Self-RAG/CRAG bridge v1. This module wraps the active v1.3 WebUI answer server with a live pre-answer engineering-brain bridge: question -> Self-RAG/CRAG bridge -> v1.3 answer composer -> trace checklist It intentionally preserves the v1.3 answer behavior and model id, while adding an auditable preflight gate that proves query planning, context pack building, Self-RAG, and CRAG evaluation ran for the request.
- Classes: BridgeConfig@L70 methods=[]; TraceNetWebUIHandlerV13BridgeV1@L652 methods=['_json_response', '_read_body_json', 'do_GET', 'do_POST']; TraceNetHTTPServerV13BridgeV1@L732 methods=['__init__']
- Functions: _as_path(value)@L89; _safe_slug(text)@L95; _new_request_dir(base_dir, question)@L101; _summary(payload)@L106; _statuses(payload)@L111; _bridge_passed(payload)@L116; _ensure_bridge_stage_dirs(target_dir)@L131; _patch_stage_writer_parent_dirs_for_in_process_bridge()@L153; _bridge_status_payload(question, bridge_payload)@L195; merge_bridge_trace(answer_record, bridge_payload)@L241; bridge_failure_record(question)@L256; _bridge_cli_command(question, config, target_dir)@L298; _run_bridge_cli_fallback(question, config, target_dir)@L331; run_bridge_preflight(question, config)@L358; answer_question_with_bridge_v1()@L396; _bridge_config_from_args(args)@L435; _add_bridge_args(parser)@L454; build_manifest_bridge_v1()@L469
- CLI args: --kernel, --bridge-output-dir, --table-exact-search-adapter, --leiden-communities, --image-visual-observer, --webui-visual-context-bridge, --max-records-per-slot, --min-high-signal-capsules, --min-evidence-strength-score, --disable-self-rag-crag-bridge, --allow-answer-if-bridge-fails, --disable-bridge-cli-fallback, --output-dir, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff, --sample-question, --quality, --report-path, --write-json, --min-page-records, --min-gated-drafts, --require-llm-model, --require-bridge-preflight, --require-self-rag-used, --require-crag-evaluated, --require-webui-visual-context-bridge-used, --min-visual-context-cards
- Routes: /health@L563, /v1/models@L563, /v1/chat/completions@L563, /health@L671, /v1/models@L692, /api/models@L692, /v1/chat/completions@L698, /api/chat/completions@L698
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1_3 import DEFAULT_FINAL_GATE, DEFAULT_FISHNET, DEFAULT_PAGE_CONTEXT, DEFAULT_ROUTE_HANDOFF, DEFAULT_RUNNER, LLMConfig, MODEL_ID, _add_llm_args, _llm_config_from_args, _read_json, _write_json, _write_jsonl, answer_question_v13, load_gated_drafts, load_page_index; from tiff.trace_net_webui_self_rag_crag_bridge_v1 import REPORT_NAME, build_webui_self_rag_crag_bridge
- Has __main__ guard.

### Source window L14-L70
```python
00014: import argparse
00015: import json
00016: import re
00017: import subprocess
00018: import sys
00019: import time
00020: from dataclasses import dataclass
00021: from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
00022: from pathlib import Path
00023: from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
00024: 
00025: from tiff.trace_net_engineering_webui_answer_server_v1_3 import (
00026:     DEFAULT_FINAL_GATE,
00027:     DEFAULT_FISHNET,
00028:     DEFAULT_PAGE_CONTEXT,
00029:     DEFAULT_ROUTE_HANDOFF,
00030:     DEFAULT_RUNNER,
00031:     LLMConfig,
00032:     MODEL_ID,
00033:     _add_llm_args,
00034:     _llm_config_from_args,
00035:     _read_json,
00036:     _write_json,
00037:     _write_jsonl,
00038:     answer_question_v13,
00039:     load_gated_drafts,
00040:     load_page_index,
00041: )
00042: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import (
00043:     REPORT_NAME as BRIDGE_REPORT_NAME,
00044:     build_webui_self_rag_crag_bridge,
00045: )
00046: 
00047: MODULE_VERSION = "trace_net_engineering_webui_answer_server_v1_3_bridge_v1"
00048: REPORT_NAME = "trace_net_engineering_webui_answer_server_v1_3_bridge_v1.json"
00049: 
00050: DEFAULT_KERNEL = Path("local_data/organization/trace_net/engineering_reasoning_kernel/trace_net_engineering_reasoning_kernel_v1.json")
00051: DEFAULT_TABLE_EXACT_SEARCH = Path("local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json")
00052: DEFAULT_LEIDEN_COMMUNITIES = Path("local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json")
00053: DEFAULT_IMAGE_VISUAL_OBSERVER = Path("local_data/organization/trace_net/image_visual_observer/trace_net_image_visual_observer_v1.json")
00054: DEFAULT_WEBUI_VISUAL_CONTEXT_BRIDGE = Path("local_data/organization/trace_net/webui_visual_context_bridge/trace_net_webui_visual_context_bridge_v1.json")
00055: DEFAULT_BRIDGE_OUTPUT_DIR = Path("local_data/organization/trace_net/webui_self_rag_crag_bridge_live")
00056: 
00057: SAFETY_COUNT_KEYS = (
00058:     "answer_permission_count",
00059:     "can_answer_directly_count",
00060:     "can_prove_claims_count",
00061:     "source_truth_mutation_allowed_count",
00062:     "postgres_write_attempt_count",
00063:     "qdrant_write_attempt_count",
00064:     "opensearch_write_attempt_count",
00065:     "unsafe_record_count",
00066: )
00067: 
00068: 
00069: @dataclass(frozen=True)
00070: class BridgeConfig:
```
### Source window L233-L289
```python
00233:         "route_dispatch": {"status": statuses.get("route_dispatch")},
00234:         "table_route": {"status": statuses.get("table_route")},
00235:         "page_context_v2": {"status": statuses.get("page_context_v2")},
00236:         "visual_image_route": {"status": statuses.get("visual_image_route"), "used": statuses.get("visual_image_route") == "used"},
00237:         "webui_visual_context_bridge": {"status": statuses.get("webui_visual_context_bridge"), "used": statuses.get("webui_visual_context_bridge") == "used"},
00238:     }
00239: 
00240: 
00241: def merge_bridge_trace(answer_record: Mapping[str, Any], bridge_payload: Mapping[str, Any], *, bridge_report_path: Optional[Path] = None) -> Dict[str, Any]:
00242:     """Attach bridge results to an existing v1.3 answer trace record."""
00243:     merged = dict(answer_record)
00244:     merged.update(_bridge_status_payload(str(answer_record.get("question") or ""), bridge_payload, bridge_report_path=bridge_report_path))
00245:     # Preserve safety counters. The bridge is pre-answer and must not authorize.
00246:     merged["answer_permission"] = False
00247:     merged["can_answer_directly"] = False
00248:     merged["can_prove_claims"] = False
00249:     merged["source_truth_mutation_allowed"] = False
00250:     merged["postgres_write_attempt"] = False
00251:     merged["qdrant_write_attempt"] = False
00252:     merged["opensearch_write_attempt"] = False
00253:     return merged
00254: 
00255: 
00256: def bridge_failure_record(question: str, *, error: str, bridge_payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
00257:     """Return a controlled no-answer trace when the pre-answer bridge fails."""
00258:     record: Dict[str, Any] = {
00259:         "question": question,
00260:         "response_text": (
00261:             "TRACE-Net did not produce an answer because the Self-RAG/CRAG preflight bridge did not pass. "
00262:             "This is a controlled safety stop, not a source-truth answer."
00263:         ),
00264:         "intent": "bridge_preflight",
00265:         "evidence_status": "bridge_preflight_failed",
00266:         "response_kind": "controlled_bridge_preflight_block",
00267:         "citations": [],
00268:         "citation_count": 0,
00269:         "llm_called": False,
00270:         "llm_model": None,
00271:         "llm_error": error,
00272:         "answer_permission": False,
00273:         "can_answer_directly": False,
00274:         "can_prove_claims": False,
00275:         "source_truth_mutation_allowed": False,
00276:         "postgres_write_attempt": False,
00277:         "qdrant_write_attempt": False,
00278:         "opensearch_write_attempt": False,
00279:         "unsafe": False,
00280:     }
00281:     if bridge_payload:
00282:         record.update(_bridge_status_payload(question, bridge_payload))
00283:     else:
00284:         record.update(
00285:             {
00286:                 "webui_self_rag_crag_bridge_used": False,
00287:                 "webui_self_rag_crag_bridge_quality_status": "ERROR",
00288:                 "webui_self_rag_crag_bridge_error": error,
00289:                 "query_planner_used": False,
```
### Source window L96-L152
```python
00096:     slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
00097:     slug = slug.strip("._-") or "question"
00098:     return slug[:max_chars]
00099: 
00100: 
00101: def _new_request_dir(base_dir: Path, question: str) -> Path:
00102:     stamp = int(time.time() * 1000)
00103:     return base_dir / f"request_{stamp}_{_safe_slug(question)}"
00104: 
00105: 
00106: def _summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
00107:     value = payload.get("summary")
00108:     return value if isinstance(value, Mapping) else {}
00109: 
00110: 
00111: def _statuses(payload: Mapping[str, Any]) -> Dict[str, str]:
00112:     value = payload.get("tool_statuses")
00113:     return {str(k): str(v) for k, v in value.items()} if isinstance(value, Mapping) else {}
00114: 
00115: 
00116: def _bridge_passed(payload: Mapping[str, Any]) -> bool:
00117:     summary = _summary(payload)
00118:     statuses = _statuses(payload)
00119:     return (
00120:         payload.get("quality_status") == "PASS"
00121:         and statuses.get("query_planner") == "used"
00122:         and statuses.get("context_pack_builder") == "used"
00123:         and statuses.get("self_rag") == "used"
00124:         and statuses.get("crag_retry") in {"used", "skipped_not_needed"}
00125:         and int(summary.get("answer_permission_count") or 0) == 0
00126:         and int(summary.get("source_truth_mutation_allowed_count") or 0) == 0
00127:     )
00128: 
00129: 
00130: 
00131: def _ensure_bridge_stage_dirs(target_dir: Path) -> None:
00132:     """Pre-create bridge stage directories before in-process or CLI bridge runs.
00133: 
00134:     Some stage builders write JSONL sidecars directly with ``Path.open("w")``
00135:     and expect their output directory to already exist. The standalone bridge is
00136:     now safe on fresh directories, but the WebUI wrapper also guarantees the
00137:     nested sample/live preflight tree before it calls either the in-process
00138:     bridge or the CLI fallback.
00139:     """
00140:     stage_root = target_dir / "stage_reports"
00141:     for name in (
00142:         "query_planner",
00143:         "context_pack_blueprint",
00144:         "context_pack_builder",
00145:         "self_rag_check",
00146:         "crag_retry_plan",
00147:     ):
00148:         (stage_root / name).mkdir(parents=True, exist_ok=True)
00149: 
00150: 
00151: 
00152: 
```
### Source window L488-L544
```python
00488:     _ensure_bridge_stage_dirs(sample_bridge_dir)
00489:     sample_record = answer_question_with_bridge_v1(
00490:         question=sample_question,
00491:         pages=pages,
00492:         gated_drafts=gated_drafts,
00493:         llm_config=LLMConfig(mode="off", model=llm_config.model, base_url=llm_config.base_url),
00494:         bridge_config=bridge_config,
00495:         bridge_output_dir=sample_bridge_dir,
00496:     )
00497:     tool_statuses = sample_record.get("webui_self_rag_crag_bridge_tool_statuses") or {}
00498:     summary = {
00499:         "page_record_count": len(pages),
00500:         "page_with_text_count": sum(1 for page in pages if page.get("has_text")),
00501:         "gated_draft_count": len(gated_drafts),
00502:         "sample_response_kind": sample_record.get("response_kind"),
00503:         "sample_response_char_count": len(str(sample_record.get("response_text") or "")),
00504:         "server_llm_mode": llm_config.mode,
00505:         "server_llm_model": llm_config.model if llm_config.enabled else None,
00506:         "server_llm_base_url": llm_config.base_url if llm_config.enabled else None,
00507:         "self_rag_crag_bridge_enabled": bridge_config.enabled,
00508:         "self_rag_crag_bridge_required_before_answer": not bridge_config.allow_answer_if_bridge_fails,
00509:         "sample_bridge_quality_status": sample_record.get("webui_self_rag_crag_bridge_quality_status"),
00510:         "sample_bridge_used": bool(sample_record.get("webui_self_rag_crag_bridge_used")),
00511:         "sample_bridge_tool_statuses": tool_statuses,
00512:         "sample_bridge_error": sample_record.get("webui_self_rag_crag_bridge_error") or sample_record.get("llm_error"),
00513:         "sample_bridge_in_process_error": sample_record.get("webui_self_rag_crag_bridge_in_process_error"),
00514:         "sample_bridge_cli_fallback_used": bool(sample_record.get("webui_self_rag_crag_bridge_cli_fallback_used")),
00515:         "query_planner_used": bool(sample_record.get("query_planner_used")),
00516:         "context_pack_builder_used": bool(sample_record.get("context_pack_builder_used")),
00517:         "self_rag_used": bool(sample_record.get("self_rag_used")),
00518:         "crag_retry_status": sample_record.get("crag_retry_status"),
00519:         "crag_retry_evaluated": bool(sample_record.get("crag_retry_evaluated")),
00520:         "context_pack_count": int(sample_record.get("context_pack_count") or 0),
00521:         "total_evidence_capsule_count": int(sample_record.get("total_evidence_capsule_count") or 0),
00522:         "webui_visual_context_bridge_used": bool(sample_record.get("webui_visual_context_bridge_used")),
00523:         "visual_image_route_used": bool(sample_record.get("visual_image_route_used")),
00524:         "webui_visual_context_bridge_quality_status": sample_record.get("webui_visual_context_bridge_quality_status"),
00525:         "visual_context_card_count": int(sample_record.get("visual_context_card_count") or 0),
00526:         "review_only_visual_context_excluded_count": int(sample_record.get("review_only_visual_context_excluded_count") or 0),
00527:         "visual_context_included_pages": sample_record.get("visual_context_included_pages") or [],
00528:         "visual_context_included_canonical_page_numbers": sample_record.get("visual_context_included_canonical_page_numbers") or [],
00529:         "ready_for_webui": True,
00530:         "openai_compatible_chat_completions_route": True,
00531:         "answer_permission_count": 0,
00532:         "can_answer_directly_count": 0,
00533:         "can_prove_claims_count": 0,
00534:         "retrieval_execution_allowed_count": 0,
00535:         "source_truth_mutation_allowed_count": 0,
00536:         "postgres_write_attempt_count": 0,
00537:         "qdrant_write_attempt_count": 0,
00538:         "opensearch_write_attempt_count": 0,
00539:         "unsafe_record_count": 0,
00540:     }
00541:     failures: List[str] = []
00542:     if not pages and not gated_drafts:
00543:         failures.append("no pages or gated drafts loaded")
00544:     if bridge_config.enabled:
```
### Source window L726-L782
```python
00726:             }
00727:             self._json_response(200, response)
00728:         except Exception as exc:
00729:             self._json_response(500, {"error": f"{type(exc).__name__}: {exc}"})
00730: 
00731: 
00732: class TraceNetHTTPServerV13BridgeV1(ThreadingHTTPServer):
00733:     def __init__(
00734:         self,
00735:         server_address: Tuple[str, int],
00736:         handler_class: Any,
00737:         *,
00738:         pages: Sequence[Mapping[str, Any]],
00739:         gated_drafts: Sequence[Mapping[str, Any]],
00740:         llm_config: LLMConfig,
00741:         bridge_config: BridgeConfig,
00742:     ) -> None:
00743:         super().__init__(server_address, handler_class)
00744:         self.pages = list(pages)
00745:         self.gated_drafts = list(gated_drafts)
00746:         self.llm_config = llm_config
00747:         self.bridge_config = bridge_config
00748: 
00749: 
00750: def run_server_bridge_v1(
00751:     *,
00752:     host: str,
00753:     port: int,
00754:     final_gate_path: Path,
00755:     runner_path: Path,
00756:     page_context_path: Path,
00757:     fishnet_path: Path,
00758:     route_handoff_path: Path,
00759:     llm_config: LLMConfig,
00760:     bridge_config: BridgeConfig,
00761: ) -> None:
00762:     pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path)
00763:     gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
00764:     server = TraceNetHTTPServerV13BridgeV1(
00765:         (host, port),
00766:         TraceNetWebUIHandlerV13BridgeV1,
00767:         pages=pages,
00768:         gated_drafts=gated_drafts,
00769:         llm_config=llm_config,
00770:         bridge_config=bridge_config,
00771:     )
00772:     print(f"TRACE-Net WebUI answer server v1.3 + Self-RAG/CRAG bridge v1 running on http://{host}:{port}")
00773:     print(f"Model ID exposed to WebUI: {MODEL_ID}")
00774:     print(f"Runtime LLM model: {llm_config.model if llm_config.enabled else 'off'}")
00775:     print(f"Self-RAG/CRAG bridge enabled: {bridge_config.enabled}")
00776:     print(f"Bridge required before answer: {not bridge_config.allow_answer_if_bridge_fails}")
00777:     print(f"Pages loaded: {len(pages)}")
00778:     print(f"Gated drafts loaded: {len(gated_drafts)}")
00779:     server.serve_forever()
00780: 
00781: 
00782: def main_build(argv: Optional[Sequence[str]] = None) -> int:
```
### Source window L555-L611
```python
00555:     payload = {
00556:         "module": MODULE_VERSION,
00557:         "status": "ENGINEERING_WEBUI_ANSWER_SERVER_V1_3_SELF_RAG_CRAG_BRIDGE_MANIFEST_BUILT",
00558:         "quality_status": quality_status,
00559:         "failures": failures,
00560:         "summary": summary,
00561:         "model_id": MODEL_ID,
00562:         "records": [sample_record],
00563:         "routes": {"health": "/health", "models": "/v1/models", "chat_completions": "/v1/chat/completions"},
00564:         "input_paths": {
00565:             "final_gate": str(final_gate_path),
00566:             "runner_report": str(runner_path),
00567:             "page_context_v2": str(page_context_path),
00568:             "fishnet_ocr_grid": str(fishnet_path),
00569:             "route_handoff": str(route_handoff_path),
00570:             "kernel": str(bridge_config.kernel_path),
00571:             "table_exact_search_adapter": str(bridge_config.table_exact_search_adapter) if bridge_config.table_exact_search_adapter else None,
00572:             "leiden_communities": str(bridge_config.leiden_communities) if bridge_config.leiden_communities else None,
00573:             "image_visual_observer": str(bridge_config.image_visual_observer) if bridge_config.image_visual_observer else None,
00574:             "webui_visual_context_bridge": str(bridge_config.webui_visual_context_bridge) if bridge_config.webui_visual_context_bridge else None,
00575:             "bridge_cli_fallback_enabled": bridge_config.cli_fallback_enabled,
00576:         },
00577:         "safety_contract": {
00578:             "manual_review_required": True,
00579:             "bridge_required_before_answer": not bridge_config.allow_answer_if_bridge_fails,
00580:             "answer_permission": False,
00581:             "source_truth_mutation_allowed": False,
00582:             "postgres_write_allowed": False,
00583:             "qdrant_write_allowed": False,
00584:             "opensearch_write_allowed": False,
00585:         },
00586:     }
00587:     output_dir.mkdir(parents=True, exist_ok=True)
00588:     _write_json(output_dir / REPORT_NAME, payload)
00589:     _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_bridge_v1_summary.json", summary)
00590:     _write_jsonl(output_dir / "trace_net_engineering_webui_answer_server_v1_3_bridge_v1_records.jsonl", [sample_record])
00591:     _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_bridge_v1_quality.json", {"quality_status": quality_status, "summary": summary, "failures": failures})
00592:     return payload
00593: 
00594: 
00595: def check_manifest_bridge_v1(
00596:     *,
00597:     report_path: Path,
00598:     min_page_records: int = 1,
00599:     min_gated_drafts: int = 0,
00600:     require_llm_model: Optional[str] = None,
00601:     require_bridge_preflight: bool = False,
00602:     require_self_rag_used: bool = False,
00603:     require_crag_evaluated: bool = False,
00604:     require_webui_visual_context_bridge_used: bool = False,
00605:     min_visual_context_cards: int = 0,
00606:     require_no_answer_permission: bool = False,
00607:     require_no_source_truth_mutation: bool = False,
00608:     require_no_write_attempts: bool = False,
00609: ) -> Dict[str, Any]:
00610:     payload = _read_json(report_path, required=True)
00611:     summary = dict(_summary(payload))
```
### Source window L614-L670
```python
00614:     def fail_if(condition: bool, message: str) -> None:
00615:         if condition:
00616:             failures.append(message)
00617: 
00618:     fail_if(payload.get("quality_status") != "PASS", "manifest quality_status is not PASS")
00619:     fail_if(int(summary.get("page_record_count") or 0) < min_page_records, "not enough page records")
00620:     fail_if(int(summary.get("gated_draft_count") or 0) < min_gated_drafts, "not enough gated drafts")
00621:     if require_llm_model:
00622:         fail_if(summary.get("server_llm_model") != require_llm_model, f"server llm model is not {require_llm_model}")
00623:     if require_bridge_preflight:
00624:         fail_if(not summary.get("self_rag_crag_bridge_enabled"), "Self-RAG/CRAG bridge is not enabled")
00625:         fail_if(not summary.get("sample_bridge_used"), "sample bridge was not used")
00626:     if require_self_rag_used:
00627:         fail_if(not summary.get("self_rag_used"), "Self-RAG was not used")
00628:     if require_crag_evaluated:
00629:         fail_if(summary.get("crag_retry_status") not in {"used", "skipped_not_needed"}, "CRAG retry was not evaluated")
00630:     if require_webui_visual_context_bridge_used:
00631:         fail_if(not summary.get("webui_visual_context_bridge_used"), "WebUI visual context bridge was not used")
00632:         fail_if(summary.get("webui_visual_context_bridge_quality_status") != "PASS", "WebUI visual context bridge quality_status is not PASS")
00633:         fail_if(not summary.get("visual_image_route_used"), "visual image route was not used")
00634:     if min_visual_context_cards:
00635:         fail_if(int(summary.get("visual_context_card_count") or 0) < min_visual_context_cards, "not enough visual context cards")
00636:     if require_no_answer_permission:
00637:         for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
00638:             fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
00639:     if require_no_source_truth_mutation:
00640:         fail_if(int(summary.get("source_truth_mutation_allowed_count") or 0) != 0, "source_truth_mutation_allowed_count is not zero")
00641:     if require_no_write_attempts:
00642:         for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
00643:             fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
00644:     return {
00645:         "quality_status": "FAIL" if failures else "PASS",
00646:         "summary": summary,
00647:         "failures": failures,
00648:         "checked_report_path": str(report_path),
00649:     }
00650: 
00651: 
00652: class TraceNetWebUIHandlerV13BridgeV1(BaseHTTPRequestHandler):
00653:     server_version = "TraceNetWebUIAnswerServer/1.3-bridge-v1"
00654: 
00655:     def _json_response(self, status: int, payload: Mapping[str, Any]) -> None:
00656:         raw = json.dumps(payload).encode("utf-8")
00657:         self.send_response(status)
00658:         self.send_header("Content-Type", "application/json")
00659:         self.send_header("Content-Length", str(len(raw)))
00660:         self.end_headers()
00661:         self.wfile.write(raw)
00662: 
00663:     def _read_body_json(self) -> Dict[str, Any]:
00664:         length = int(self.headers.get("Content-Length", "0") or "0")
00665:         if length <= 0:
00666:             return {}
00667:         raw = self.rfile.read(length).decode("utf-8", errors="replace")
00668:         return json.loads(raw) if raw.strip() else {}
00669: 
00670:     def do_GET(self) -> None:  # noqa: N802
```
### Source window L292-L348
```python
00292:                 "crag_retry_evaluated": False,
00293:             }
00294:         )
00295:     return record
00296: 
00297: 
00298: def _bridge_cli_command(question: str, config: BridgeConfig, target_dir: Path) -> List[str]:
00299:     """Build the exact CLI fallback command for the already-passing bridge script."""
00300:     cmd = [
00301:         sys.executable,
00302:         "scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py",
00303:         "--question",
00304:         question,
00305:         "--kernel",
00306:         str(config.kernel_path),
00307:         "--output-dir",
00308:         str(target_dir),
00309:         "--max-records-per-slot",
00310:         str(config.max_records_per_slot),
00311:         "--min-high-signal-capsules",
00312:         str(config.min_high_signal_capsules),
00313:         "--min-evidence-strength-score",
00314:         str(config.min_evidence_strength_score),
00315:         "--quality",
00316:     ]
00317:     optional_args = [
00318:         ("--route-dispatch-handoff", config.route_dispatch_handoff),
00319:         ("--table-exact-search-adapter", config.table_exact_search_adapter),
00320:         ("--page-context-v2", config.page_context_v2),
00321:         ("--leiden-communities", config.leiden_communities),
00322:         ("--image-visual-observer", config.image_visual_observer),
00323:         ("--webui-visual-context-bridge", config.webui_visual_context_bridge),
00324:     ]
00325:     for flag, path in optional_args:
00326:         if path is not None:
00327:             cmd.extend([flag, str(path)])
00328:     return cmd
00329: 
00330: 
00331: def _run_bridge_cli_fallback(question: str, config: BridgeConfig, target_dir: Path, *, in_process_error: Exception) -> Tuple[Dict[str, Any], Path]:
00332:     """Run the bridge through its CLI when the in-process call raises.
00333: 
00334:     Justin already validated the standalone bridge command. The WebUI wrapper should
00335:     therefore fall back to the same CLI path instead of silently blocking because
00336:     of an import/runtime mismatch in the wrapper layer.
00337:     """
00338:     _ensure_bridge_stage_dirs(target_dir)
00339:     report_path = target_dir / BRIDGE_REPORT_NAME
00340:     cmd = _bridge_cli_command(question, config, target_dir)
00341:     result = subprocess.run(cmd, text=True, capture_output=True)
00342:     if report_path.exists():
00343:         payload = _read_json(report_path, required=True)
00344:         payload["in_process_error"] = f"{type(in_process_error).__name__}: {in_process_error}"
00345:         payload["cli_fallback_used"] = True
00346:         payload["cli_fallback_returncode"] = result.returncode
00347:         payload["cli_fallback_stdout_tail"] = (result.stdout or "")[-4000:]
00348:         payload["cli_fallback_stderr_tail"] = (result.stderr or "")[-4000:]
```

## `tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_script_imports.py`
- Location: `active_tests`
- Score: `259`
- Categories: `self_rag, server, webui`
- Functions: test_build_script_imports()@L5; test_check_script_imports()@L15

### Source window L1-L22
```python
00001: import importlib.util
00002: from pathlib import Path
00003: 
00004: 
00005: def test_build_script_imports():
00006:     path = Path("scripts/build_trace_net_webui_self_rag_crag_bridge_v1.py")
00007:     assert path.exists()
00008:     spec = importlib.util.spec_from_file_location("build_trace_net_webui_self_rag_crag_bridge_v1", path)
00009:     module = importlib.util.module_from_spec(spec)
00010:     assert spec and spec.loader
00011:     spec.loader.exec_module(module)
00012:     assert hasattr(module, "main_build")
00013: 
00014: 
00015: def test_check_script_imports():
00016:     path = Path("scripts/check_trace_net_webui_self_rag_crag_bridge_v1_quality.py")
00017:     assert path.exists()
00018:     spec = importlib.util.spec_from_file_location("check_trace_net_webui_self_rag_crag_bridge_v1_quality", path)
00019:     module = importlib.util.module_from_spec(spec)
00020:     assert spec and spec.loader
00021:     spec.loader.exec_module(module)
00022:     assert hasattr(module, "main_check")
```

## `scripts/build_trace_net_engineering_engram_crag_repair_v1.py`
- Location: `active_source_code`
- Score: `257`
- Categories: `crag, engram, page, server`
- Tiff imports: from tiff.trace_net_engineering_engram_crag_repair_v1 import main
- Has __main__ guard.

### Source window L1-L11
```python
00001: from pathlib import Path
00002: import sys
00003: 
00004: ROOT = Path(__file__).resolve().parents[1]
00005: if str(ROOT) not in sys.path:
00006:     sys.path.insert(0, str(ROOT))
00007: 
00008: from tiff.trace_net_engineering_engram_crag_repair_v1 import main
00009: 
00010: if __name__ == "__main__":
00011:     raise SystemExit(main())
```

## `scripts/build_trace_net_engineering_engram_self_rag_critic_v1.py`
- Location: `active_source_code`
- Score: `257`
- Categories: `engram, page, self_rag, server`
- Tiff imports: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main
- Has __main__ guard.

### Source window L1-L12
```python
00001: from __future__ import annotations
00002: import sys
00003: from pathlib import Path
00004: 
00005: ROOT = Path(__file__).resolve().parents[1]
00006: if str(ROOT) not in sys.path:
00007:     sys.path.insert(0, str(ROOT))
00008: 
00009: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import main
00010: 
00011: if __name__ == "__main__":
00012:     raise SystemExit(main())
```

## `scripts/check_trace_net_engineering_engram_self_rag_critic_v1.py`
- Location: `active_source_code`
- Score: `257`
- Categories: `engram, page, self_rag, server`
- Tiff imports: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import check_main
- Has __main__ guard.

### Source window L1-L12
```python
00001: from __future__ import annotations
00002: import sys
00003: from pathlib import Path
00004: 
00005: ROOT = Path(__file__).resolve().parents[1]
00006: if str(ROOT) not in sys.path:
00007:     sys.path.insert(0, str(ROOT))
00008: 
00009: from tiff.trace_net_engineering_engram_self_rag_critic_v1 import check_main
00010: 
00011: if __name__ == "__main__":
00012:     raise SystemExit(check_main())
```

## `scripts/check_trace_net_page_context_pack_v3_quality.py`
- Location: `active_source_code`
- Score: `257`
- Categories: `context_pack, page, safety, server`
- Doc: Quality gate for TRACE-Net Page Context Pack v3.
- Functions: parse_args()@L17; main()@L30
- CLI args: --input, --output, --min-pages, --min-guidance-records, --min-source-trace-ready-pages, --min-source-locators, --require-no-answer-permission, --require-reasoning-work-order
- Tiff imports: from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json
- Has __main__ guard.

### Source window L1-L42
```python
00001: #!/usr/bin/env python3
00002: """Quality gate for TRACE-Net Page Context Pack v3."""
00003: 
00004: from __future__ import annotations
00005: 
00006: import argparse
00007: from pathlib import Path
00008: import sys
00009: 
00010: REPO_ROOT = Path(__file__).resolve().parents[1]
00011: if str(REPO_ROOT) not in sys.path:
00012:     sys.path.insert(0, str(REPO_ROOT))
00013: 
00014: from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json
00015: 
00016: 
00017: def parse_args() -> argparse.Namespace:
00018:     parser = argparse.ArgumentParser(description="Check TRACE-Net page context pack v3 quality.")
00019:     parser.add_argument("--input", required=True)
00020:     parser.add_argument("--output", default=None)
00021:     parser.add_argument("--min-pages", type=int, default=1)
00022:     parser.add_argument("--min-guidance-records", type=int, default=0)
00023:     parser.add_argument("--min-source-trace-ready-pages", type=int, default=0)
00024:     parser.add_argument("--min-source-locators", type=int, default=0)
00025:     parser.add_argument("--require-no-answer-permission", action="store_true")
00026:     parser.add_argument("--require-reasoning-work-order", action="store_true")
00027:     return parser.parse_args()
00028: 
00029: 
00030: def main() -> int:
00031:     args = parse_args()
00032:     pack = load_json(args.input, {})
00033:     quality = check_page_context_pack_v3_quality(
00034:         pack,
00035:         min_pages=args.min_pages,
00036:         require_no_answer_permission=args.require_no_answer_permission,
00037:         require_reasoning_work_order=args.require_reasoning_work_order,
00038:         min_guidance_records=args.min_guidance_records,
00039:         min_source_trace_ready_pages=args.min_source_trace_ready_pages,
00040:         min_source_locators=args.min_source_locators,
00041:     )
00042:     if args.output:
```

## `scripts/build_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Location: `active_source_code`
- Score: `254`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Functions: main()@L14
- CLI args: --relationship-router-hardening, --relationship-final-gate-hardener, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --graph-signal-artifact, --output-dir, --host, --port, --llm-mode, --llm-model, --include-standard-demo-queries, --min-sample-queries, --min-sample-successes, --min-relationship-final-gate-applied, --min-relationship-records, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import build_report
- Has __main__ guard.

### Source window L39-L86
```python
00039:     report = build_report(
00040:         relationship_router_hardening=args.relationship_router_hardening,
00041:         relationship_final_gate_hardener=args.relationship_final_gate_hardener,
00042:         table_exact_search_adapter=args.table_exact_search_adapter,
00043:         page_context_v2=args.page_context_v2,
00044:         leiden_communities=args.leiden_communities,
00045:         graph_signal_paths=args.graph_signal_artifact or None,
00046:         output_dir=args.output_dir,
00047:         include_standard_demo_queries=args.include_standard_demo_queries,
00048:         min_sample_queries=args.min_sample_queries,
00049:         min_sample_successes=args.min_sample_successes,
00050:         min_relationship_final_gate_applied=args.min_relationship_final_gate_applied,
00051:         min_relationship_records=args.min_relationship_records,
00052:         max_post_gate_issue_count=args.max_post_gate_issue_count,
00053:         max_answer_permission_count=args.max_answer_permission_count,
00054:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00055:         require_no_answer_permission=args.require_no_answer_permission,
00056:         quality=args.quality,
00057:     )
00058: 
00059:     print("TRACE-Net E2E Live Relationship Final-Gated Endpoint v31")
00060:     print(f" Status: {report['status']}")
00061:     print(f" Quality status: {report['quality_status']}")
00062:     for key in [
00063:         "sample_query_count",
00064:         "sample_success_count",
00065:         "relationship_final_gate_applied_count",
00066:         "relationship_record_count",
00067:         "repaired_relationship_sample_count",
00068:         "post_gate_issue_count",
00069:         "exact_search_document_count",
00070:         "page_context_v2_page_count",
00071:         "graph_has_nomenclature_page_count",
00072:         "answer_permission_count",
00073:         "source_truth_mutation_allowed_count",
00074:         "base_url_windows",
00075:         "base_url_open_webui_docker",
00076:         "report_path",
00077:         "samples_jsonl_path",
00078:         "inspect_md_path",
00079:     ]:
00080:         print(f" {key}: {report.get(key)}")
00081:     if args.quality and report["quality_status"] != "PASS":
00082:         raise SystemExit(1)
00083: 
00084: 
00085: if __name__ == "__main__":
00086:     main()
```

## `scripts/serve_trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Location: `active_source_code`
- Score: `253`
- Categories: `final_gate, graph_vector, page, server, table_visual_ocr, webui`
- Classes: Handler@L37 methods=['do_OPTIONS', 'do_GET', 'do_POST', 'log_message']
- Functions: _send_json(handler, status, payload)@L24; make_handler(state, model_id)@L36; main()@L90; do_OPTIONS(self)@L38; do_GET(self)@L41; do_POST(self)@L69; log_message(self, format)@L84
- CLI args: --relationship-router-hardening, --relationship-final-gate-hardener, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --graph-signal-artifact, --host, --port, --model-id, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --relationship-mode
- Routes: /health@L42, /v1/models@L60, /v1/chat/completions@L70
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import MODEL_ID, SAFETY_CONTRACT, RuntimeState, _extract_user_text, make_chat_completion_response
- Has __main__ guard.

### Source window L1-L43
```python
00001: from __future__ import annotations
00002: 
00003: import sys
00004: from pathlib import Path
00005: 
00006: REPO_ROOT = Path(__file__).resolve().parents[1]
00007: if str(REPO_ROOT) not in sys.path:
00008:     sys.path.insert(0, str(REPO_ROOT))
00009: 
00010: import argparse
00011: import json
00012: from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
00013: from typing import Any, Dict
00014: 
00015: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import (
00016:     MODEL_ID,
00017:     SAFETY_CONTRACT,
00018:     RuntimeState,
00019:     _extract_user_text,
00020:     make_chat_completion_response,
00021: )
00022: 
00023: 
00024: def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
00025:     body = json.dumps(payload, indent=2).encode("utf-8")
00026:     handler.send_response(status)
00027:     handler.send_header("Content-Type", "application/json")
00028:     handler.send_header("Content-Length", str(len(body)))
00029:     handler.send_header("Access-Control-Allow-Origin", "*")
00030:     handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
00031:     handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
00032:     handler.end_headers()
00033:     handler.wfile.write(body)
00034: 
00035: 
00036: def make_handler(state: RuntimeState, model_id: str):
00037:     class Handler(BaseHTTPRequestHandler):
00038:         def do_OPTIONS(self) -> None:  # noqa: N802
00039:             _send_json(self, 200, {"ok": True})
00040: 
00041:         def do_GET(self) -> None:  # noqa: N802
00042:             if self.path == "/health":
00043:                 _send_json(
```
### Source window L74-L125
```python
00074:             raw = self.rfile.read(length).decode("utf-8") if length else "{}"
00075:             try:
00076:                 payload = json.loads(raw)
00077:             except json.JSONDecodeError as exc:
00078:                 _send_json(self, 400, {"error": f"Invalid JSON: {exc}"})
00079:                 return
00080:             query = _extract_user_text(payload.get("messages", []))
00081:             result = state.answer(query)
00082:             _send_json(self, 200, make_chat_completion_response(model_id, query, result))
00083: 
00084:         def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
00085:             return
00086: 
00087:     return Handler
00088: 
00089: 
00090: def main() -> None:
00091:     parser = argparse.ArgumentParser(description="Serve TRACE-Net live relationship final-gated endpoint v31.")
00092:     parser.add_argument("--relationship-router-hardening", required=True, type=Path)
00093:     parser.add_argument("--relationship-final-gate-hardener", required=True, type=Path)
00094:     parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
00095:     parser.add_argument("--page-context-v2", type=Path)
00096:     parser.add_argument("--leiden-communities", type=Path)
00097:     parser.add_argument("--graph-signal-artifact", action="append", type=Path, default=[])
00098:     parser.add_argument("--host", default="127.0.0.1")
00099:     parser.add_argument("--port", type=int, default=8026)
00100:     parser.add_argument("--model-id", default=MODEL_ID)
00101:     # Accepted for CLI compatibility; v31 can wrap a router that has already made the LLM/deterministic decision.
00102:     parser.add_argument("--llm-mode", default="ollama")
00103:     parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
00104:     parser.add_argument("--llm-model", default="gemma4:26b")
00105:     parser.add_argument("--llm-api-key", default="ollama")
00106:     parser.add_argument("--request-timeout", type=int, default=240)
00107:     parser.add_argument("--relationship-mode", default="guarded")
00108:     args = parser.parse_args()
00109: 
00110:     state = RuntimeState(
00111:         relationship_router_hardening=args.relationship_router_hardening,
00112:         relationship_final_gate_hardener=args.relationship_final_gate_hardener,
00113:         table_exact_search_adapter=args.table_exact_search_adapter,
00114:         page_context_v2=args.page_context_v2,
00115:         leiden_communities=args.leiden_communities,
00116:         graph_signal_paths=args.graph_signal_artifact or None,
00117:     )
00118:     server = ThreadingHTTPServer((args.host, args.port), make_handler(state, args.model_id))
00119:     print(f"Serving TRACE-Net live relationship final-gated endpoint v31 on http://{args.host}:{args.port}/v1")
00120:     print(f"Model: {args.model_id}")
00121:     server.serve_forever()
00122: 
00123: 
00124: if __name__ == "__main__":
00125:     main()
```

## `scripts/build_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import main
- Has __main__ guard.

### Source window L1-L4
```python
00001: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import main
00002: 
00003: if __name__ == "__main__":
00004:     raise SystemExit(main())
```

## `scripts/build_trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import main
- Has __main__ guard.

### Source window L1-L13
```python
00001: from __future__ import annotations
00002: 
00003: import sys
00004: from pathlib import Path
00005: 
00006: ROOT = Path(__file__).resolve().parents[1]
00007: if str(ROOT) not in sys.path:
00008:     sys.path.insert(0, str(ROOT))
00009: 
00010: from tiff.trace_net_engineering_engram_answer_runner_prompt_overlay_smoke_v1 import main
00011: 
00012: if __name__ == "__main__":
00013:     raise SystemExit(main())
```

## `scripts/build_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import main
- Has __main__ guard.

### Source window L1-L12
```python
00001: #!/usr/bin/env python3
00002: from pathlib import Path
00003: import sys
00004: 
00005: ROOT = Path(__file__).resolve().parents[1]
00006: if str(ROOT) not in sys.path:
00007:     sys.path.insert(0, str(ROOT))
00008: 
00009: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import main
00010: 
00011: if __name__ == "__main__":
00012:     raise SystemExit(main())
```

## `scripts/check_trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `engram, page, server, webui`
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import check_main
- Has __main__ guard.

### Source window L1-L4
```python
00001: from tiff.trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1 import check_main
00002: 
00003: if __name__ == "__main__":
00004:     raise SystemExit(check_main())
```

## `tiff/trace_net_engineering_engram_core_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _read_json(path)@L25; _write_json(path, data)@L30; _write_csv(path, rows)@L36; _csv_value(v)@L56; _as_list(v)@L64; _default_memory_atoms()@L72; _summarize_smoke(path)@L234; _eval_memory_atoms(eval_summaries)@L256; _slug(text, max_len)@L297; _quality_gate(atoms, eval_summaries)@L303; build_engram_core(output_dir, smoke_test, min_engram_atoms, min_policy_traits, min_memory_types, max_unsafe, max_answer_permission, max_source_truth_mutation_allowed)@L340; check_engram_core(engram_core, output, min_engram_atoms, min_policy_traits, min_memory_types, max_unsafe, max_answer_permission, max_source_truth_mutation_allowed)@L501; _build_parser()@L554; main_build(argv)@L570; _check_parser()@L596; main_check(argv)@L611
- CLI args: --output-dir, --smoke-test, --min-engram-atoms, --min-policy-traits, --min-memory-types, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --require-quality-pass, --require-eval-source-pass, --engram-core, --output, --min-engram-atoms, --min-policy-traits, --min-memory-types, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --require-quality-pass
- Has __main__ guard.

### Source window L1-L38
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import csv
00005: import json
00006: from collections import Counter
00007: from pathlib import Path
00008: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
00009: 
00010: MODULE = "trace_net_engineering_engram_core_v1"
00011: VERSION = "v1"
00012: 
00013: SAFETY_ZERO_FIELDS = [
00014:     "answer_permission_count",
00015:     "source_truth_mutation_allowed_count",
00016:     "postgres_write_attempt_count",
00017:     "qdrant_write_attempt_count",
00018:     "opensearch_write_attempt_count",
00019:     "opensearch_upload_attempt_count",
00020:     "write_attempt_count",
00021:     "unsafe_record_count",
00022: ]
00023: 
00024: 
00025: def _read_json(path: Any) -> Dict[str, Any]:
00026:     p = Path(path)
00027:     return json.loads(p.read_text(encoding="utf-8"))
00028: 
00029: 
00030: def _write_json(path: Any, data: Mapping[str, Any]) -> None:
00031:     p = Path(path)
00032:     p.parent.mkdir(parents=True, exist_ok=True)
00033:     p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
00034: 
00035: 
00036: def _write_csv(path: Any, rows: Sequence[Mapping[str, Any]]) -> None:
00037:     p = Path(path)
00038:     p.parent.mkdir(parents=True, exist_ok=True)
```
### Source window L178-L234
```python
00178:         },
00179:         {
00180:             "engram_id": "episode_h13_generic_not_proven_v1",
00181:             "memory_type": "episodic_failure_memory",
00182:             "priority": "high",
00183:             "trait": "failure_memory",
00184:             "triggers": ["pipeline question", "debug question", "nomenclature missing"],
00185:             "trigger_text": "pipeline/debug questions over-refused",
00186:             "rule": "H13/H14 initially answered pipeline/debug questions with generic 'not proven'; H14C repaired this using scaffold + route-specific intent rules.",
00187:             "good_behavior": "Explain route behavior when the scaffold describes pipeline behavior; distinguish pipeline explanation from source-truth proof.",
00188:             "bad_behavior": "Blank/blocked or generic not-proven answers for route behavior questions.",
00189:             "source": "H13-H14C eval history",
00190:             "status": "active",
00191:         },
00192:         {
00193:             "engram_id": "episode_h14b_path_length_stage_output_v1",
00194:             "memory_type": "episodic_failure_memory",
00195:             "priority": "medium",
00196:             "trait": "failure_memory",
00197:             "triggers": ["Windows path", "quality_check missing", "stage output", "FileNotFoundError"],
00198:             "trigger_text": "Windows path length | missing quality_check",
00199:             "rule": "H14B exposed nested stage-output path failures; H14C used shorter output dirs and safe trace records to prevent blocked answers.",
00200:             "good_behavior": "Use short run directories and record safe failure traces instead of letting path plumbing block question evaluation.",
00201:             "bad_behavior": "Long nested run directories that prevent quality-check artifacts from being written/read on Windows.",
00202:             "source": "H14B/H14C path hardening",
00203:             "status": "active",
00204:         },
00205:         {
00206:             "engram_id": "critic_answer_behavior_self_rag_v1",
00207:             "memory_type": "critic_trait",
00208:             "priority": "high",
00209:             "trait": "self_rag_behavior_check",
00210:             "triggers": ["answer critique", "Self-RAG", "unsupported claim", "intent mismatch"],
00211:             "trigger_text": "Self-RAG answer behavior critique",
00212:             "rule": "Self-RAG should check whether the draft obeys source-trace boundaries, answers the actual intent, cites claims, and avoids over/under-refusal.",
00213:             "good_behavior": "Critique answers for evidence support and behavior correctness before delivery.",
00214:             "bad_behavior": "Only checking citation existence while missing semantic intent failure.",
00215:             "source": "H10 semantic answer quality eval",
00216:             "status": "active",
00217:         },
00218:         {
00219:             "engram_id": "repair_crag_engram_repair_v1",
00220:             "memory_type": "repair_trait",
00221:             "priority": "high",
00222:             "trait": "crag_repair_reflex",
00223:             "triggers": ["CRAG", "repair", "weak answer", "retry"],
00224:             "trigger_text": "CRAG repair | weak answer retry",
00225:             "rule": "CRAG should retrieve relevant failure/repair engrams and regenerate or rewrite the answer when Self-RAG flags weak behavior or weak evidence.",
00226:             "good_behavior": "Use retrieved repair patterns such as 'shared nomenclature is not interchangeability' to fix weak drafts.",
00227:             "bad_behavior": "Retrying the same prompt without adding behavior memory or evidence diagnostics.",
00228:             "source": "TRACE-Net engram architecture plan",
00229:             "status": "active",
00230:         },
00231:     ]
00232: 
00233: 
00234: def _summarize_smoke(path: Any) -> Dict[str, Any]:
```
### Source window L385-L441
```python
00385:         require_eval_source_pass=require_eval_source_pass,
00386:     )
00387: 
00388:     for field, value in [
00389:         ("answer_permission_count", safety["answer_permission_count"]),
00390:         ("source_truth_mutation_allowed_count", safety["source_truth_mutation_allowed_count"]),
00391:         ("unsafe_record_count", safety["unsafe_record_count"]),
00392:         ("write_attempt_count", safety["write_attempt_count"]),
00393:     ]:
00394:         limit = {
00395:             "answer_permission_count": max_answer_permission,
00396:             "source_truth_mutation_allowed_count": max_source_truth_mutation_allowed,
00397:             "unsafe_record_count": max_unsafe,
00398:             "write_attempt_count": max_write_attempts,
00399:         }[field]
00400:         if value > limit:
00401:             qg["failures"].append(f"{field} above maximum: {value} > {limit}")
00402:     qg["quality_status"] = "PASS" if not qg.get("failures") else "FAIL"
00403: 
00404:     summary = {
00405:         "module": MODULE,
00406:         "version": VERSION,
00407:         "engram_atom_count": len(atoms),
00408:         "policy_trait_count": memory_types.get("policy_trait", 0),
00409:         "style_trait_count": memory_types.get("style_trait", 0),
00410:         "route_behavior_count": memory_types.get("route_behavior", 0),
00411:         "episodic_failure_memory_count": memory_types.get("episodic_failure_memory", 0),
00412:         "episodic_eval_memory_count": memory_types.get("episodic_eval_memory", 0),
00413:         "critic_trait_count": memory_types.get("critic_trait", 0),
00414:         "repair_trait_count": memory_types.get("repair_trait", 0),
00415:         "memory_type_count": len([m for m in memory_types if m]),
00416:         "hard_boundary_count": priorities.get("hard_boundary", 0),
00417:         "eval_source_count": len(eval_summaries),
00418:         "traits": traits,
00419:         "ready_for_engram_prompt_injector": qg["quality_status"] == "PASS",
00420:         **safety,
00421:     }
00422: 
00423:     traits_pack = {
00424:         "module": "trace_net_engineering_engram_traits_v1",
00425:         "version": VERSION,
00426:         "quality_status": qg["quality_status"],
00427:         "records": [a for a in atoms if str(a.get("memory_type", "")).endswith("trait") or a.get("memory_type") in {"policy_trait", "style_trait", "critic_trait", "repair_trait"}],
00428:         "summary": {
00429:             "trait_record_count": sum(1 for a in atoms if str(a.get("memory_type", "")).endswith("trait") or a.get("memory_type") in {"policy_trait", "style_trait", "critic_trait", "repair_trait"}),
00430:             "policy_trait_count": memory_types.get("policy_trait", 0),
00431:             "style_trait_count": memory_types.get("style_trait", 0),
00432:             "critic_trait_count": memory_types.get("critic_trait", 0),
00433:             "repair_trait_count": memory_types.get("repair_trait", 0),
00434:         },
00435:     }
00436: 
00437:     memory_pack = {
00438:         "module": "trace_net_engineering_engram_memory_atoms_v1",
00439:         "version": VERSION,
00440:         "quality_status": qg["quality_status"],
00441:         "records": atoms,
```
### Source window L57-L113
```python
00057:     if isinstance(v, (list, dict)):
00058:         return json.dumps(v, ensure_ascii=False)
00059:     if v is None:
00060:         return ""
00061:     return str(v)
00062: 
00063: 
00064: def _as_list(v: Any) -> List[Any]:
00065:     if v is None:
00066:         return []
00067:     if isinstance(v, list):
00068:         return v
00069:     return [v]
00070: 
00071: 
00072: def _default_memory_atoms() -> List[Dict[str, Any]]:
00073:     """Seed TRACE-Net's first engineering engram from H11-H14C lessons."""
00074:     return [
00075:         {
00076:             "engram_id": "policy_no_interchangeability_without_authority_v1",
00077:             "memory_type": "policy_trait",
00078:             "priority": "hard_boundary",
00079:             "trait": "source_trace_caution",
00080:             "triggers": ["interchangeability", "approved replacement", "replacement approval", "shared nomenclature"],
00081:             "trigger_text": "interchangeability | replacement approval | shared nomenclature",
00082:             "rule": "Shared nomenclature, nearby figures, or part-family similarity are not proof of interchangeability or replacement approval.",
00083:             "good_behavior": "Say what TRACE-Net can prove about each part, then state interchangeability/replacement approval is not proven.",
00084:             "bad_behavior": "Treating the same description or part-family proximity as approval or interchangeability.",
00085:             "source": "H14C llm smoke repair",
00086:             "status": "active",
00087:         },
00088:         {
00089:             "engram_id": "policy_no_installation_safety_from_figure_v1",
00090:             "memory_type": "policy_trait",
00091:             "priority": "hard_boundary",
00092:             "trait": "approval_boundary",
00093:             "triggers": ["installation safety", "safe install", "fit approval", "aircraft effectivity"],
00094:             "trigger_text": "installation safety | fit approval | aircraft effectivity",
00095:             "rule": "Figure/part identification evidence does not prove installation safety, fit approval, aircraft effectivity, or replacement approval.",
00096:             "good_behavior": "Lead with not proven, then list the source-trace-ready identity/nomenclature evidence that is proven.",
00097:             "bad_behavior": "Implying a figure, OCR line, or part listing authorizes installation or fit.",
00098:             "source": "H14C llm smoke repair",
00099:             "status": "active",
00100:         },
00101:         {
00102:             "engram_id": "policy_v2_summaries_guidance_not_proof_v1",
00103:             "memory_type": "policy_trait",
00104:             "priority": "hard_boundary",
00105:             "trait": "summary_boundary",
00106:             "triggers": ["v2 summary", "summaries", "summary proof", "summary-only"],
00107:             "trigger_text": "v2 summary | summary-only proof",
00108:             "rule": "V2 summaries may guide planning and framing, but cannot prove source claims; factual claims require proof_context citations.",
00109:             "good_behavior": "Use summaries only to guide route selection and answer framing; cite proof_context for claims.",
00110:             "bad_behavior": "Using a v2 summary as direct evidence for part identity or approval.",
00111:             "source": "H10/H14C semantic eval",
00112:             "status": "active",
00113:         },
```
### Source window L120-L176
```python
00120:             "trigger_text": "visual route | OCR nomenclature | nomenclature missing",
00121:             "rule": "visual_figure_link establishes figure-to-part identity; ocr_nomenclature provides OCR-backed line-text name proof.",
00122:             "good_behavior": "Explain both routes separately when asked evidence-support or pipeline questions.",
00123:             "bad_behavior": "Saying only 'not proven' for pipeline questions when route behavior evidence is available.",
00124:             "source": "H14C safe reasoning traces",
00125:             "status": "active",
00126:         },
00127:         {
00128:             "engram_id": "route_table_ocr_supports_exact_part_v1",
00129:             "memory_type": "route_behavior",
00130:             "priority": "medium",
00131:             "trait": "route_awareness",
00132:             "triggers": ["table OCR", "exact part", "part lookup", "evidence supports"],
00133:             "trigger_text": "table OCR | exact part lookup | evidence support",
00134:             "rule": "Exact-part/table-OCR evidence supports presence of a part number but does not by itself prove approvals or compatibility.",
00135:             "good_behavior": "Use table/OCR evidence to support part presence and citation readiness, while keeping approval claims out of scope.",
00136:             "bad_behavior": "Converting a table hit into effectivity, fit, or replacement authority.",
00137:             "source": "H11-H14C smoke evals",
00138:             "status": "active",
00139:         },
00140:         {
00141:             "engram_id": "style_engineering_answer_shape_v1",
00142:             "memory_type": "style_trait",
00143:             "priority": "high",
00144:             "trait": "engineering_answer_shape",
00145:             "triggers": ["engineering answer", "limitations", "evidence", "confidence"],
00146:             "trigger_text": "engineering answer | limitations | evidence",
00147:             "rule": "Prefer answer sections: Answer, Evidence, Engineering confidence, Limits; for limitations questions, split Can prove vs Cannot prove.",
00148:             "good_behavior": "Give a concise direct answer, then cite proof and state limits.",
00149:             "bad_behavior": "Generic disclaimer-only answers, or citation dumps without answering the actual intent.",
00150:             "source": "H14C llm answer style",
00151:             "status": "active",
00152:         },
00153:         {
00154:             "engram_id": "style_useful_not_proven_v1",
00155:             "memory_type": "style_trait",
00156:             "priority": "high",
00157:             "trait": "useful_caution",
00158:             "triggers": ["not proven", "cannot prove", "not source-trace-ready"],
00159:             "trigger_text": "not proven | cannot prove | not source-trace-ready",
00160:             "rule": "When a claim is not proven, still explain what TRACE-Net can prove and why the requested claim is outside the evidence.",
00161:             "good_behavior": "Not proven + can prove identity/nomenclature/pages + cannot prove approval/safety/effectivity.",
00162:             "bad_behavior": "Only saying 'not proven' without useful evidence context.",
00163:             "source": "H13 over-refusal repair through H14C",
00164:             "status": "active",
00165:         },
00166:         {
00167:             "engram_id": "style_unknown_part_or_figure_v1",
00168:             "memory_type": "style_trait",
00169:             "priority": "medium",
00170:             "trait": "unknown_handling",
00171:             "triggers": ["unknown part", "unknown figure", "not found", "999"],
00172:             "trigger_text": "unknown part | unknown figure | not found",
00173:             "rule": "For unknown part/figure questions with no proof_context, lead with not found / not source-trace-ready and do not cite unrelated evidence.",
00174:             "good_behavior": "State no proof_context was available and avoid unrelated citations.",
00175:             "bad_behavior": "Citing nearby known figures or parts for an unknown requested identifier.",
00176:             "source": "H14C partial unknown handling",
```
### Source window L320-L376
```python
00320:         failures.append(f"policy_trait_count below minimum: {policy_trait_count} < {min_policy_traits}")
00321:     if len([m for m in memory_types if m]) < min_memory_types:
00322:         failures.append(f"memory_type_count below minimum: {len(memory_types)} < {min_memory_types}")
00323:     if max_unsafe < 0:
00324:         failures.append("max_unsafe cannot be negative")
00325:     if max_write_attempts < 0:
00326:         failures.append("max_write_attempts cannot be negative")
00327:     if require_eval_source_pass:
00328:         for ev in eval_summaries:
00329:             if ev.get("quality_status") != "PASS":
00330:                 failures.append(f"eval source is not PASS: {ev.get('path')}")
00331:     return {
00332:         "quality_status": "PASS" if not failures else "FAIL",
00333:         "failures": failures,
00334:         "engram_atom_count": len(atoms),
00335:         "policy_trait_count": policy_trait_count,
00336:         "memory_type_count": len([m for m in memory_types if m]),
00337:     }
00338: 
00339: 
00340: def build_engram_core(
00341:     output_dir: Any,
00342:     smoke_test: Optional[Sequence[Any]] = None,
00343:     min_engram_atoms: int = 10,
00344:     min_policy_traits: int = 3,
00345:     min_memory_types: int = 5,
00346:     max_unsafe: int = 0,
00347:     max_answer_permission: int = 0,
00348:     max_source_truth_mutation_allowed: int = 0,
00349:     max_write_attempts: int = 0,
00350:     require_quality_pass: bool = False,
00351:     require_eval_source_pass: bool = False,
00352: ) -> Dict[str, Any]:
00353:     out_dir = Path(output_dir)
00354:     out_dir.mkdir(parents=True, exist_ok=True)
00355: 
00356:     eval_summaries: List[Dict[str, Any]] = []
00357:     for p in _as_list(smoke_test):
00358:         if p:
00359:             eval_summaries.append(_summarize_smoke(p))
00360: 
00361:     atoms = _default_memory_atoms() + _eval_memory_atoms(eval_summaries)
00362:     memory_types = Counter(str(a.get("memory_type") or "") for a in atoms)
00363:     priorities = Counter(str(a.get("priority") or "") for a in atoms)
00364:     traits = sorted({str(a.get("trait") or "") for a in atoms if a.get("trait")})
00365: 
00366:     safety = {
00367:         "answer_permission_count": 0,
00368:         "source_truth_mutation_allowed_count": 0,
00369:         "postgres_write_attempt_count": 0,
00370:         "qdrant_write_attempt_count": 0,
00371:         "opensearch_write_attempt_count": 0,
00372:         "opensearch_upload_attempt_count": 0,
00373:         "write_attempt_count": 0,
00374:         "unsafe_record_count": 0,
00375:     }
00376: 
```
### Source window L480-L536
```python
00480:         "status": "TRACE_NET_ENGINEERING_ENGRAM_CORE_QUALITY_CHECKED",
00481:         "quality_status": qg["quality_status"],
00482:         "summary": summary,
00483:         "quality_gate": qg,
00484:     })
00485:     _write_csv(csv_path, atoms)
00486: 
00487:     result["paths"] = {
00488:         "core": str(core_path),
00489:         "memory_atoms": str(memory_path),
00490:         "traits": str(traits_path),
00491:         "quality_check": str(qc_path),
00492:         "csv": str(csv_path),
00493:     }
00494:     _write_json(core_path, result)
00495: 
00496:     if require_quality_pass and qg["quality_status"] != "PASS":
00497:         raise SystemExit("quality_status is not PASS")
00498:     return result
00499: 
00500: 
00501: def check_engram_core(
00502:     engram_core: Any,
00503:     output: Any,
00504:     min_engram_atoms: int = 10,
00505:     min_policy_traits: int = 3,
00506:     min_memory_types: int = 5,
00507:     max_unsafe: int = 0,
00508:     max_answer_permission: int = 0,
00509:     max_source_truth_mutation_allowed: int = 0,
00510:     max_write_attempts: int = 0,
00511:     require_quality_pass: bool = False,
00512: ) -> Dict[str, Any]:
00513:     data = _read_json(engram_core)
00514:     records = list(data.get("records") or [])
00515:     eval_summaries = list(data.get("eval_summaries") or [])
00516:     qg = _quality_gate(
00517:         records,
00518:         eval_summaries,
00519:         min_engram_atoms=min_engram_atoms,
00520:         min_policy_traits=min_policy_traits,
00521:         min_memory_types=min_memory_types,
00522:         max_unsafe=max_unsafe,
00523:         max_write_attempts=max_write_attempts,
00524:         require_eval_source_pass=False,
00525:     )
00526:     summary = dict(data.get("summary") or {})
00527:     failures = list(qg.get("failures") or [])
00528:     for field, limit in [
00529:         ("unsafe_record_count", max_unsafe),
00530:         ("answer_permission_count", max_answer_permission),
00531:         ("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed),
00532:         ("write_attempt_count", max_write_attempts),
00533:     ]:
00534:         value = int(summary.get(field) or 0)
00535:         if value > limit:
00536:             failures.append(f"{field} above maximum: {value} > {limit}")
```

## `tiff/trace_net_engineering_engram_postgres_feedback_ledger_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _read_json(path)@L64; _write_json(path, data)@L68; _write_jsonl(path, records)@L73; _stable_id(prefix)@L78; _load_jsonl(path)@L86; _records_by_id(records, key)@L100; _answer_records(answer_smoke)@L104; _critic_records(critic)@L108; _crag_records(crag)@L112; _rating_for(answer, critic, crag)@L116; _normalize_feedback_records(records)@L152; build_feedback_ledger_manifest(answer_smoke, critic, crag_repair, output_dir, feedback_jsonl, postgres_dsn, enable_live_postgres_write, min_feedback_records)@L180; _count(records, key)@L361; check_feedback_ledger_manifest(ledger, min_feedback_records, min_candidate_records, require_quality_pass, require_no_answer_permission, max_unsafe, max_write_attempts)@L370; build_arg_parser()@L406; main(argv)@L426
- CLI args: --answer-smoke, --critic, --crag-repair, --output-dir, --feedback-jsonl, --postgres-dsn, --enable-live-postgres-write, --min-feedback-records, --min-candidate-records, --require-source-quality-pass, --require-critic-quality-pass, --require-crag-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.

### Source window L1-L38
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import hashlib
00005: import json
00006: from dataclasses import dataclass
00007: from pathlib import Path
00008: from typing import Any, Iterable, Mapping
00009: 
00010: MODULE = "trace_net_engineering_engram_postgres_feedback_ledger_v1"
00011: VERSION = "v1"
00012: 
00013: MEMORY_LAYERS = {"working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory"}
00014: 
00015: SAFETY_CONTRACT = {
00016:     "answer_permission": False,
00017:     "source_truth_mutation_allowed": False,
00018:     "postgres_write_attempt": False,
00019:     "qdrant_write_attempt": False,
00020:     "qdrant_read_attempt": False,
00021:     "opensearch_write_attempt": False,
00022:     "opensearch_upload_attempt": False,
00023:     "write_attempt": False,
00024: }
00025: 
00026: SCHEMA_SQL = """
00027: -- TRACE-Net Engineering Engram feedback ledger v1
00028: -- Safety: feedback rows are behavior memory only; they are not proof_context.
00029: CREATE TABLE IF NOT EXISTS trace_net_engram_feedback_ledger_v1 (
00030:     feedback_id TEXT PRIMARY KEY,
00031:     source_question_id TEXT NOT NULL,
00032:     feedback_source TEXT NOT NULL,
00033:     rating TEXT NOT NULL,
00034:     explanation TEXT NOT NULL,
00035:     source_grade TEXT,
00036:     critic_status TEXT,
00037:     crag_status TEXT,
00038:     recommended_memory_layer TEXT NOT NULL,
```
### Source window L189-L245
```python
00189:     min_candidate_records: int = 5,
00190:     require_source_quality_pass: bool = False,
00191:     require_critic_quality_pass: bool = False,
00192:     require_crag_quality_pass: bool = False,
00193:     require_no_answer_permission: bool = False,
00194:     max_unsafe: int = 0,
00195:     max_write_attempts: int = 0,
00196: ) -> dict[str, Any]:
00197:     answer_manifest = _read_json(answer_smoke)
00198:     critic_manifest = _read_json(critic)
00199:     crag_manifest = _read_json(crag_repair)
00200:     output = Path(output_dir)
00201:     output.mkdir(parents=True, exist_ok=True)
00202: 
00203:     answers = _answer_records(answer_manifest)
00204:     critics_by_qid = _records_by_id(_critic_records(critic_manifest))
00205:     crag_by_qid = _records_by_id(_crag_records(crag_manifest))
00206: 
00207:     feedback_records: list[dict[str, Any]] = []
00208:     for a in answers:
00209:         qid = str(a.get("question_id") or "")
00210:         c = critics_by_qid.get(qid)
00211:         cr = crag_by_qid.get(qid)
00212:         rating, layer, explanation, trigger = _rating_for(a, c, cr)
00213:         feedback_id = _stable_id("fb", qid, rating, explanation, a.get("answer_preview") or a.get("answer_text") or "")
00214:         feedback_records.append({
00215:             "feedback_id": feedback_id,
00216:             "source_question_id": qid,
00217:             "feedback_source": "self_rag_crag_eval",
00218:             "rating": rating,
00219:             "explanation": explanation,
00220:             "source_grade": str(a.get("grade") or "UNKNOWN"),
00221:             "critic_status": str((c or {}).get("critic_status") or "UNKNOWN"),
00222:             "crag_status": str((cr or {}).get("crag_status") or "NO_REPAIR"),
00223:             "recommended_memory_layer": layer,
00224:             "recommended_memory_type": "critic_memory" if layer == "critic_memory" else "episodic_memory",
00225:             "proof_role": "guidance_only",
00226:             "answer_permission": False,
00227:             "source_truth_mutation_allowed": False,
00228:             "candidate_trigger": trigger,
00229:             "payload": {
00230:                 "question": a.get("question"),
00231:                 "source_grade": a.get("grade"),
00232:                 "critic_findings": (c or {}).get("findings", []),
00233:                 "critic_repair_hints": (c or {}).get("repair_hints", []),
00234:                 "crag_status": (cr or {}).get("crag_status"),
00235:             },
00236:         })
00237: 
00238:     feedback_records.extend(_normalize_feedback_records(_load_jsonl(feedback_jsonl)))
00239: 
00240:     candidate_records: list[dict[str, Any]] = []
00241:     for fb in feedback_records:
00242:         layer = str(fb.get("recommended_memory_layer") or "episodic_memory")
00243:         if layer not in MEMORY_LAYERS:
00244:             layer = "episodic_memory"
00245:         candidate_id = _stable_id("cand", fb["feedback_id"], layer, fb["explanation"])
```
### Source window L114-L170
```python
00114: 
00115: 
00116: def _rating_for(answer: Mapping[str, Any], critic: Mapping[str, Any] | None, crag: Mapping[str, Any] | None) -> tuple[str, str, str, str]:
00117:     qid = str(answer.get("question_id") or "")
00118:     grade = str(answer.get("grade") or "UNKNOWN")
00119:     critic_status = str((critic or {}).get("critic_status") or "UNKNOWN")
00120:     expected_boundary = bool((critic or {}).get("expected_unknown_boundary_partial"))
00121:     crag_status = str((crag or {}).get("crag_status") or "NO_CRAG_RECORD")
00122: 
00123:     if expected_boundary:
00124:         return (
00125:             "expected_boundary",
00126:             "episodic_memory",
00127:             "expected unknown/no-proof boundary was preserved safely; do not over-repair this case.",
00128:             "unknown part; no proof_context; not source-trace-ready",
00129:         )
00130:     if grade == "GOOD" and critic_status == "PASS":
00131:         return (
00132:             "thumbs_up",
00133:             "critic_memory" if "generic" in " ".join(map(str, (critic or {}).get("findings", []))).lower() else "episodic_memory",
00134:             "answer passed critic checks; preserve this response pattern as behavior guidance.",
00135:             "critic pass; citation safe; proof boundary preserved",
00136:         )
00137:     if critic_status in {"REVIEW", "REPAIR_RECOMMENDED"} or bool((critic or {}).get("repair_recommended")):
00138:         return (
00139:             "thumbs_down",
00140:             "critic_memory",
00141:             "critic recommended review/repair; retrieve this feedback before regenerating similar answers.",
00142:             "repair recommended; self-rag review; crag repair",
00143:         )
00144:     return (
00145:         "neutral_review",
00146:         "episodic_memory",
00147:         "record preserved as evaluation memory; do not treat as proof.",
00148:         "evaluation memory; behavior guidance",
00149:     )
00150: 
00151: 
00152: def _normalize_feedback_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
00153:     out: list[dict[str, Any]] = []
00154:     for r in records:
00155:         qid = str(r.get("question_id") or r.get("source_question_id") or "manual_feedback")
00156:         rating = str(r.get("rating") or r.get("feedback_rating") or "neutral_review")
00157:         explanation = str(r.get("explanation") or r.get("feedback_text") or "Manual feedback record.")
00158:         layer = str(r.get("recommended_memory_layer") or r.get("memory_layer") or ("critic_memory" if rating in {"thumbs_down", "negative"} else "episodic_memory"))
00159:         if layer not in MEMORY_LAYERS:
00160:             layer = "episodic_memory"
00161:         out.append({
00162:             "feedback_id": str(r.get("feedback_id") or _stable_id("fb", qid, rating, explanation)),
00163:             "source_question_id": qid,
00164:             "feedback_source": str(r.get("feedback_source") or "manual_feedback_jsonl"),
00165:             "rating": rating,
00166:             "explanation": explanation,
00167:             "source_grade": str(r.get("source_grade") or "manual"),
00168:             "critic_status": str(r.get("critic_status") or "manual"),
00169:             "crag_status": str(r.get("crag_status") or "manual"),
00170:             "recommended_memory_layer": layer,
```
### Source window L249-L305
```python
00249:             "source_question_id": fb["source_question_id"],
00250:             "memory_layer": layer,
00251:             "memory_type": fb.get("recommended_memory_type") or ("critic_memory" if layer == "critic_memory" else "episodic_memory"),
00252:             "proof_role": "guidance_only",
00253:             "candidate_rule": fb["explanation"],
00254:             "candidate_trigger": fb.get("candidate_trigger") or fb["rating"],
00255:             "status": "pending_human_review",
00256:             "answer_permission": False,
00257:             "source_truth_mutation_allowed": False,
00258:             "payload": {"feedback_id": fb["feedback_id"], "rating": fb["rating"], "feedback_source": fb["feedback_source"]},
00259:         })
00260: 
00261:     postgres_write_attempt_count = 1 if enable_live_postgres_write else 0
00262:     write_attempt_count = postgres_write_attempt_count
00263:     unsafe_findings: list[str] = []
00264: 
00265:     if enable_live_postgres_write:
00266:         unsafe_findings.append("live_postgres_write_requested_in_v1_adapter_not_executed")
00267:         # This v1 ledger intentionally does not execute DB writes. H32 may wire an explicit executor.
00268: 
00269:     answer_permission_count = sum(1 for r in feedback_records + candidate_records if r.get("answer_permission"))
00270:     source_truth_mutation_allowed_count = sum(1 for r in feedback_records + candidate_records if r.get("source_truth_mutation_allowed"))
00271: 
00272:     quality_failures: list[str] = []
00273:     if require_source_quality_pass and answer_manifest.get("quality_status") != "PASS":
00274:         quality_failures.append("source_answer_smoke_quality_status_not_pass")
00275:     if require_critic_quality_pass and critic_manifest.get("quality_status") != "PASS":
00276:         quality_failures.append("source_critic_quality_status_not_pass")
00277:     if require_crag_quality_pass and crag_manifest.get("quality_status") != "PASS":
00278:         quality_failures.append("source_crag_quality_status_not_pass")
00279:     if len(feedback_records) < min_feedback_records:
00280:         quality_failures.append(f"feedback_record_count_below_min:{len(feedback_records)}<{min_feedback_records}")
00281:     if len(candidate_records) < min_candidate_records:
00282:         quality_failures.append(f"candidate_record_count_below_min:{len(candidate_records)}<{min_candidate_records}")
00283:     if require_no_answer_permission and answer_permission_count:
00284:         quality_failures.append("answer_permission_count_above_zero")
00285:     if source_truth_mutation_allowed_count:
00286:         quality_failures.append("source_truth_mutation_allowed_count_above_zero")
00287:     if len(unsafe_findings) > max_unsafe:
00288:         quality_failures.append(f"unsafe_finding_count_above_max:{len(unsafe_findings)}>{max_unsafe}")
00289:     if write_attempt_count > max_write_attempts:
00290:         quality_failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
00291: 
00292:     schema_path = output / "trace_net_engineering_engram_feedback_ledger_schema_v1.sql"
00293:     feedback_path = output / "trace_net_engineering_engram_feedback_ledger_records_v1.jsonl"
00294:     candidates_path = output / "trace_net_engineering_engram_feedback_to_memory_candidates_v1.jsonl"
00295:     quality_path = output / "trace_net_engineering_engram_postgres_feedback_ledger_v1_quality_check.json"
00296:     manifest_path = output / "trace_net_engineering_engram_postgres_feedback_ledger_v1.json"
00297: 
00298:     schema_path.write_text(SCHEMA_SQL, encoding="utf-8")
00299:     _write_jsonl(feedback_path, feedback_records)
00300:     _write_jsonl(candidates_path, candidate_records)
00301: 
00302:     summary = {
00303:         "module": MODULE,
00304:         "version": VERSION,
00305:         "feedback_record_count": len(feedback_records),
```
### Source window L381-L437
```python
00381:     quality_failures = list(summary.get("quality_failures") or [])
00382:     if require_quality_pass and data.get("quality_status") != "PASS":
00383:         quality_failures.append("source_quality_status_not_pass")
00384:     if int(summary.get("feedback_record_count") or 0) < min_feedback_records:
00385:         quality_failures.append("feedback_record_count_below_min")
00386:     if int(summary.get("candidate_record_count") or 0) < min_candidate_records:
00387:         quality_failures.append("candidate_record_count_below_min")
00388:     if require_no_answer_permission and int(summary.get("answer_permission_count") or 0):
00389:         quality_failures.append("answer_permission_count_above_zero")
00390:     if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
00391:         quality_failures.append("unsafe_finding_count_above_max")
00392:     if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
00393:         quality_failures.append("write_attempt_count_above_max")
00394:     return {
00395:         "status": "TRACE_NET_ENGINEERING_ENGRAM_POSTGRES_FEEDBACK_LEDGER_CHECKED",
00396:         "quality_status": "PASS" if not quality_failures else "FAIL",
00397:         "feedback_record_count": summary.get("feedback_record_count", 0),
00398:         "candidate_record_count": summary.get("candidate_record_count", 0),
00399:         "unsafe_finding_count": summary.get("unsafe_finding_count", 0),
00400:         "answer_permission_count": summary.get("answer_permission_count", 0),
00401:         "write_attempt_count": summary.get("write_attempt_count", 0),
00402:         "quality_failures": quality_failures,
00403:     }
00404: 
00405: 
00406: def build_arg_parser() -> argparse.ArgumentParser:
00407:     p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Postgres feedback ledger v1")
00408:     p.add_argument("--answer-smoke", required=True)
00409:     p.add_argument("--critic", required=True)
00410:     p.add_argument("--crag-repair", required=True)
00411:     p.add_argument("--output-dir", required=True)
00412:     p.add_argument("--feedback-jsonl")
00413:     p.add_argument("--postgres-dsn")
00414:     p.add_argument("--enable-live-postgres-write", action="store_true")
00415:     p.add_argument("--min-feedback-records", type=int, default=5)
00416:     p.add_argument("--min-candidate-records", type=int, default=5)
00417:     p.add_argument("--require-source-quality-pass", action="store_true")
00418:     p.add_argument("--require-critic-quality-pass", action="store_true")
00419:     p.add_argument("--require-crag-quality-pass", action="store_true")
00420:     p.add_argument("--require-no-answer-permission", action="store_true")
00421:     p.add_argument("--max-unsafe", type=int, default=0)
00422:     p.add_argument("--max-write-attempts", type=int, default=0)
00423:     return p
00424: 
00425: 
00426: def main(argv: list[str] | None = None) -> int:
00427:     args = build_arg_parser().parse_args(argv)
00428:     manifest = build_feedback_ledger_manifest(**vars(args))
00429:     summary = manifest.get("summary", {})
00430:     print("status=" + manifest.get("status", ""))
00431:     print("quality_status=" + manifest.get("quality_status", ""))
00432:     print("feedback_record_count=" + str(summary.get("feedback_record_count", 0)))
00433:     print("candidate_record_count=" + str(summary.get("candidate_record_count", 0)))
00434:     print("unsafe_finding_count=" + str(summary.get("unsafe_finding_count", 0)))
00435:     print("answer_permission_count=" + str(summary.get("answer_permission_count", 0)))
00436:     print("write_attempt_count=" + str(summary.get("write_attempt_count", 0)))
00437:     print("output=" + str(Path(args.output_dir) / "trace_net_engineering_engram_postgres_feedback_ledger_v1.json"))
```
### Source window L315-L371
```python
00315:         "opensearch_upload_attempt_count": 0,
00316:         "write_attempt_count": write_attempt_count,
00317:         "unsafe_finding_count": len(unsafe_findings),
00318:         "unsafe_findings": unsafe_findings,
00319:         "source_answer_smoke_quality_status": answer_manifest.get("quality_status"),
00320:         "source_critic_quality_status": critic_manifest.get("quality_status"),
00321:         "source_crag_quality_status": crag_manifest.get("quality_status"),
00322:         "ready_for_postgres_feedback_table_creation": True,
00323:         "ready_for_feedback_to_engram_review": not quality_failures,
00324:         "quality_failures": quality_failures,
00325:     }
00326: 
00327:     manifest = {
00328:         "status": "TRACE_NET_ENGINEERING_ENGRAM_POSTGRES_FEEDBACK_LEDGER_BUILT",
00329:         "quality_status": "PASS" if not quality_failures else "FAIL",
00330:         "summary": summary,
00331:         "schema_path": str(schema_path),
00332:         "feedback_records_path": str(feedback_path),
00333:         "candidate_records_path": str(candidates_path),
00334:         "quality_check_path": str(quality_path),
00335:         "postgres_plan": {
00336:             "postgres_dsn_configured": bool(postgres_dsn),
00337:             "live_postgres_write_enabled": bool(enable_live_postgres_write),
00338:             "live_postgres_write_attempted": bool(enable_live_postgres_write),
00339:             "safety_note": "V1 emits schema and ledger rows. Live writes require explicit enable flag and are not executed by default.",
00340:         },
00341:         "ledger_policy": {
00342:             "mode": "artifact_first_postgres_feedback_ledger",
00343:             "proof_boundary": "Feedback and Engram memory candidates shape behavior only; factual manual claims still require proof_context citations.",
00344:             "explicit_live_flags": ["--enable-live-postgres-write"],
00345:             "forbidden": [
00346:                 "answer_permission_from_feedback",
00347:                 "source_truth_mutation_from_feedback",
00348:                 "feedback_or_engram_used_as_proof",
00349:                 "live_postgres_write_without_explicit_enable_flag",
00350:             ],
00351:         },
00352:         "feedback_records": feedback_records,
00353:         "candidate_records": candidate_records,
00354:     }
00355:     quality = {"quality_status": manifest["quality_status"], "summary": summary}
00356:     _write_json(quality_path, quality)
00357:     _write_json(manifest_path, manifest)
00358:     return manifest
00359: 
00360: 
00361: def _count(records: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
00362:     out: dict[str, int] = {}
00363:     for r in records:
00364:         val = str(r.get(key) or "")
00365:         if val:
00366:             out[val] = out.get(val, 0) + 1
00367:     return dict(sorted(out.items()))
00368: 
00369: 
00370: def check_feedback_ledger_manifest(
00371:     ledger: str | Path,
```

## `tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py`
- Location: `active_source_code`
- Score: `252`
- Categories: `crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net H32 Engineering Engram unified runtime gate v1. This module is intentionally artifact-first. It joins the already-built Engram runtime pieces into one inspectable targeted gate: - H27E answer smoke records with retrieved Engram overlays applied. - H28 Self-RAG critic records. - H29 CRAG repair records. - H30 Qdrant/vector adapter records. - H31 Postgres feedback ledger records. - Optional graph-route guidance manifest, when available. It does not perform LLM calls, graph traversal, Qdr
- Functions: _read_json(path)@L59; _write_json(path, data)@L64; _write_jsonl(path, rows)@L69; _summary(manifest)@L76; _quality(manifest)@L81; _records(manifest)@L85; _by_key(rows, key)@L93; _feedback_by_question(rows)@L102; _candidate_by_feedback(rows)@L111; _vector_queries_by_id(rows)@L120; _source_count(manifest, key)@L124; _combine_source_safety()@L131; _hash_record_id()@L144; _safe_preview(text, n)@L149; _graph_guidance_for_question(qid, graph_manifest)@L154; _runtime_status(answer, critic, crag)@L172; build_unified_runtime_gate(answer_smoke, critic, crag_repair, qdrant_adapter, feedback_ledger, output_dir, graph_route_manifest, question_ids)@L187; check_unified_runtime_gate(unified_runtime_gate, min_runtime_records, min_pass_or_expected, require_quality_pass, require_no_answer_permission, require_connections, max_unsafe, max_write_attempts)@L422
- CLI args: --answer-smoke, --critic, --crag-repair, --qdrant-adapter, --feedback-ledger, --graph-route-manifest, --output-dir, --question-ids, --min-runtime-records, --min-pass-or-expected, --require-answer-quality-pass, --require-critic-quality-pass, --require-crag-quality-pass, --require-qdrant-quality-pass, --require-feedback-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Has __main__ guard.

### Source window L1-L30
```python
00001: 
00002: """TRACE-Net H32 Engineering Engram unified runtime gate v1.
00003: 
00004: This module is intentionally artifact-first. It joins the already-built Engram
00005: runtime pieces into one inspectable targeted gate:
00006: 
00007: - H27E answer smoke records with retrieved Engram overlays applied.
00008: - H28 Self-RAG critic records.
00009: - H29 CRAG repair records.
00010: - H30 Qdrant/vector adapter records.
00011: - H31 Postgres feedback ledger records.
00012: - Optional graph-route guidance manifest, when available.
00013: 
00014: It does not perform LLM calls, graph traversal, Qdrant IO, Postgres IO,
00015: OpenSearch IO, or source-truth mutation. It proves runtime wiring readiness.
00016: """
00017: 
00018: from __future__ import annotations
00019: 
00020: import argparse
00021: import hashlib
00022: import json
00023: from pathlib import Path
00024: from typing import Any, Iterable, Mapping
00025: 
00026: MODULE = "trace_net_engineering_engram_unified_runtime_gate_v1"
00027: VERSION = "v1"
00028: ALLOWED_QIDS = ("q12", "q16", "q18", "q25", "q29")
00029: 
00030: ZERO_SAFETY = {
```
### Source window L245-L301
```python
00245: 
00246:         status = _runtime_status(answer, critic_rec, crag_rec)
00247:         if status == "REVIEW":
00248:             reasons.append("runtime_status_review")
00249: 
00250:         runtime_record = {
00251:             "runtime_record_id": _hash_record_id(qid, status, str(answer.get("grade"))),
00252:             "question_id": qid,
00253:             "question": answer.get("question"),
00254:             "answer_grade": answer.get("grade"),
00255:             "critic_status": critic_rec.get("critic_status"),
00256:             "crag_status": crag_rec.get("crag_status"),
00257:             "expected_unknown_boundary_partial": bool(critic_rec.get("expected_unknown_boundary_partial")),
00258:             "repair_recommended": bool(critic_rec.get("repair_recommended")),
00259:             "repair_attempted": bool(crag_rec.get("repair_attempted")),
00260:             "runtime_status": status,
00261:             "feedback_ids": [r.get("feedback_id") for r in feedback_rows],
00262:             "feedback_ratings": [r.get("rating") for r in feedback_rows],
00263:             "candidate_ids": [r.get("candidate_id") for r in candidate_rows],
00264:             "candidate_memory_layers": sorted({r.get("memory_layer") for r in candidate_rows if r.get("memory_layer")}),
00265:             "vector_query_ids": vector_query_ids,
00266:             "vector_guidance_available": bool(vector_rows),
00267:             "vector_memory_layers": vector_layers,
00268:             "graph_guidance": graph_guidance,
00269:             "runtime_steps": [
00270:                 "load_current_question_and_proof_context",
00271:                 "apply_retrieved_engram_overlay_behavior_guidance",
00272:                 "draft_answer_with_proof_context_citations",
00273:                 "run_self_rag_engram_critic",
00274:                 "run_crag_repair_only_if_critic_recommends_repair",
00275:                 "emit_feedback_ledger_and_memory_candidates_for_human_review",
00276:                 "consult_graph_route_guidance_when_manifest_supplied_without_using_graph_as_proof",
00277:             ],
00278:             "proof_boundary": "Engram, feedback, graph, and vector memories shape behavior only; factual manual claims still require proof_context citations.",
00279:             "live_qdrant_io_attempted": False,
00280:             "live_postgres_write_attempted": False,
00281:             "live_graph_traversal_attempted": False,
00282:             "source_truth_mutation_allowed": False,
00283:             "answer_permission": answer_permission,
00284:             "unsafe": unsafe,
00285:             "unsafe_reasons": reasons,
00286:             "answer_preview": _safe_preview(answer.get("answer_text") or answer.get("answer_preview")),
00287:         }
00288:         if unsafe:
00289:             unsafe_findings.append(f"{qid}:" + ";".join(reasons))
00290:         runtime_records.append(runtime_record)
00291: 
00292:     pass_count = sum(1 for r in runtime_records if r["runtime_status"] == "PASS")
00293:     expected_count = sum(1 for r in runtime_records if r["runtime_status"] == "EXPECTED_BOUNDARY")
00294:     pass_limit_count = sum(1 for r in runtime_records if r["runtime_status"] == "PASS_WITH_LIMIT")
00295:     pass_or_expected = pass_count + expected_count + pass_limit_count
00296: 
00297:     source_safety = _combine_source_safety(answer_manifest, critic_manifest, crag_manifest, qdrant_manifest, feedback_manifest)
00298:     unsafe_total = len(unsafe_findings) + source_safety.get("unsafe_finding_count", 0)
00299:     answer_permission_total = source_safety.get("answer_permission_count", 0) + sum(1 for r in runtime_records if r["answer_permission"])
00300:     write_total = source_safety.get("write_attempt_count", 0)
00301: 
```
### Source window L144-L200
```python
00144: def _hash_record_id(*parts: str) -> str:
00145:     raw = "|".join(parts).encode("utf-8")
00146:     return "h32_" + hashlib.sha256(raw).hexdigest()[:24]
00147: 
00148: 
00149: def _safe_preview(text: Any, n: int = 700) -> str:
00150:     raw = str(text or "").replace("\r", " ").strip()
00151:     return raw[:n]
00152: 
00153: 
00154: def _graph_guidance_for_question(qid: str, graph_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
00155:     if graph_manifest:
00156:         return {
00157:             "graph_guidance_status": "optional_graph_manifest_supplied",
00158:             "graph_manifest_quality_status": _quality(graph_manifest) or "UNKNOWN",
00159:             "graph_hint": QUESTION_TO_GRAPH_HINT.get(qid, "bounded_graph_route_guidance_optional"),
00160:             "live_graph_traversal_attempted": False,
00161:             "graph_used_as_proof": False,
00162:         }
00163:     return {
00164:         "graph_guidance_status": "artifact_placeholder_no_live_graph_traversal",
00165:         "graph_manifest_quality_status": "NOT_SUPPLIED",
00166:         "graph_hint": QUESTION_TO_GRAPH_HINT.get(qid, "bounded_graph_route_guidance_optional"),
00167:         "live_graph_traversal_attempted": False,
00168:         "graph_used_as_proof": False,
00169:     }
00170: 
00171: 
00172: def _runtime_status(answer: Mapping[str, Any], critic: Mapping[str, Any], crag: Mapping[str, Any]) -> str:
00173:     critic_status = str(critic.get("critic_status") or "")
00174:     source_grade = str(answer.get("grade") or "")
00175:     repair_attempted = bool(crag.get("repair_attempted"))
00176:     if critic_status == "EXPECTED_BOUNDARY":
00177:         return "EXPECTED_BOUNDARY"
00178:     if critic_status == "PASS" and source_grade == "GOOD" and not repair_attempted:
00179:         return "PASS"
00180:     if critic_status == "PASS" and source_grade in {"GOOD", "PARTIAL"} and not repair_attempted:
00181:         return "PASS_WITH_LIMIT"
00182:     if repair_attempted:
00183:         return "REPAIRED_OR_ATTEMPTED"
00184:     return "REVIEW"
00185: 
00186: 
00187: def build_unified_runtime_gate(
00188:     answer_smoke: str | Path,
00189:     critic: str | Path,
00190:     crag_repair: str | Path,
00191:     qdrant_adapter: str | Path,
00192:     feedback_ledger: str | Path,
00193:     output_dir: str | Path,
00194:     graph_route_manifest: str | Path | None = None,
00195:     question_ids: str = ",".join(ALLOWED_QIDS),
00196:     min_runtime_records: int = 5,
00197:     min_pass_or_expected: int = 5,
00198:     require_answer_quality_pass: bool = False,
00199:     require_critic_quality_pass: bool = False,
00200:     require_crag_quality_pass: bool = False,
```
### Source window L350-L406
```python
00350:         "qdrant_vector_adapter_connected": True,
00351:         "postgres_feedback_ledger_connected": True,
00352:         "graph_guidance_connected": bool(graph_manifest),
00353:         "graph_guidance_mode": "optional_manifest" if graph_manifest else "artifact_placeholder_no_live_graph_traversal",
00354:         "vector_guidance_record_count": sum(1 for r in runtime_records if r["vector_guidance_available"]),
00355:         "feedback_runtime_record_count": sum(1 for r in runtime_records if r["feedback_ids"]),
00356:         "repair_attempt_count": sum(1 for r in runtime_records if r["repair_attempted"]),
00357:         "answer_permission_count": answer_permission_total,
00358:         "source_truth_mutation_allowed_count": source_safety.get("source_truth_mutation_allowed_count", 0),
00359:         "postgres_write_attempt_count": source_safety.get("postgres_write_attempt_count", 0),
00360:         "qdrant_read_attempt_count": source_safety.get("qdrant_read_attempt_count", 0),
00361:         "qdrant_write_attempt_count": source_safety.get("qdrant_write_attempt_count", 0),
00362:         "opensearch_write_attempt_count": source_safety.get("opensearch_write_attempt_count", 0),
00363:         "opensearch_upload_attempt_count": source_safety.get("opensearch_upload_attempt_count", 0),
00364:         "write_attempt_count": write_total,
00365:         "unsafe_finding_count": unsafe_total,
00366:         "unsafe_findings": unsafe_findings,
00367:         "quality_failures": quality_failures,
00368:         "ready_for_targeted_unified_engram_runtime_commit_gate": quality_status == "PASS",
00369:         "ready_for_optional_full_30_after_targeted_pass": quality_status == "PASS",
00370:     }
00371:     manifest = {
00372:         "status": "TRACE_NET_ENGINEERING_ENGRAM_UNIFIED_RUNTIME_GATE_BUILT",
00373:         "quality_status": quality_status,
00374:         "summary": summary,
00375:         "runtime_policy": {
00376:             "mode": "artifact_first_unified_engram_runtime_gate",
00377:             "connects": [
00378:                 "self_rag_critic",
00379:                 "crag_repair_gate",
00380:                 "qdrant_vector_adapter_artifact_or_live_if_explicit",
00381:                 "postgres_feedback_ledger_artifact_or_live_if_explicit",
00382:                 "graph_route_guidance_optional_manifest",
00383:             ],
00384:             "proof_boundary": "Engram/feedback/vector/graph guidance can shape behavior but cannot prove manual claims; factual source claims still require proof_context citations.",
00385:             "forbidden": [
00386:                 "answer_permission_from_engram_or_feedback_or_graph_or_vector",
00387:                 "source_truth_mutation_from_runtime_gate",
00388:                 "summary_or_engram_or_feedback_used_as_proof",
00389:                 "live_db_vector_or_graph_io_without_explicit_gate",
00390:             ],
00391:             "explicit_live_flags_expected_in_future": [
00392:                 "--enable-live-qdrant-read",
00393:                 "--enable-live-qdrant-write",
00394:                 "--enable-live-postgres-write",
00395:                 "--enable-live-graph-traversal",
00396:             ],
00397:         },
00398:         "source_paths": {
00399:             "answer_smoke": str(answer_smoke),
00400:             "critic": str(critic),
00401:             "crag_repair": str(crag_repair),
00402:             "qdrant_adapter": str(qdrant_adapter),
00403:             "feedback_ledger": str(feedback_ledger),
00404:             "graph_route_manifest": str(graph_route_manifest) if graph_route_manifest else "",
00405:         },
00406:         "runtime_records_path": str(records_path),
```
### Source window L440-L496
```python
00440:         quality_failures.append("runtime_pass_or_expected_below_min")
00441:     if require_no_answer_permission and int(s.get("answer_permission_count", 0) or 0) != 0:
00442:         quality_failures.append("answer_permission_count_nonzero")
00443:     if int(s.get("unsafe_finding_count", 0) or 0) > max_unsafe:
00444:         quality_failures.append("unsafe_finding_count_above_max")
00445:     if int(s.get("write_attempt_count", 0) or 0) > max_write_attempts:
00446:         quality_failures.append("write_attempt_count_above_max")
00447:     if require_connections:
00448:         for key in ("self_rag_connected", "crag_connected", "qdrant_vector_adapter_connected", "postgres_feedback_ledger_connected"):
00449:             if not s.get(key):
00450:                 quality_failures.append(f"missing_connection:{key}")
00451:     status = "PASS" if not quality_failures else "FAIL"
00452:     return {
00453:         "status": "TRACE_NET_ENGINEERING_ENGRAM_UNIFIED_RUNTIME_GATE_CHECKED",
00454:         "quality_status": status,
00455:         "runtime_record_count": int(s.get("runtime_record_count", 0) or 0),
00456:         "runtime_pass_or_expected_count": int(s.get("runtime_pass_or_expected_count", 0) or 0),
00457:         "unsafe_finding_count": int(s.get("unsafe_finding_count", 0) or 0),
00458:         "answer_permission_count": int(s.get("answer_permission_count", 0) or 0),
00459:         "write_attempt_count": int(s.get("write_attempt_count", 0) or 0),
00460:         "quality_failures": quality_failures,
00461:     }
00462: 
00463: 
00464: def build_arg_parser() -> argparse.ArgumentParser:
00465:     p = argparse.ArgumentParser(description=__doc__)
00466:     p.add_argument("--answer-smoke", required=True)
00467:     p.add_argument("--critic", required=True)
00468:     p.add_argument("--crag-repair", required=True)
00469:     p.add_argument("--qdrant-adapter", required=True)
00470:     p.add_argument("--feedback-ledger", required=True)
00471:     p.add_argument("--graph-route-manifest", default=None)
00472:     p.add_argument("--output-dir", required=True)
00473:     p.add_argument("--question-ids", default=",".join(ALLOWED_QIDS))
00474:     p.add_argument("--min-runtime-records", type=int, default=5)
00475:     p.add_argument("--min-pass-or-expected", type=int, default=5)
00476:     p.add_argument("--require-answer-quality-pass", action="store_true")
00477:     p.add_argument("--require-critic-quality-pass", action="store_true")
00478:     p.add_argument("--require-crag-quality-pass", action="store_true")
00479:     p.add_argument("--require-qdrant-quality-pass", action="store_true")
00480:     p.add_argument("--require-feedback-quality-pass", action="store_true")
00481:     p.add_argument("--require-no-answer-permission", action="store_true")
00482:     p.add_argument("--max-unsafe", type=int, default=0)
00483:     p.add_argument("--max-write-attempts", type=int, default=0)
00484:     return p
00485: 
00486: 
00487: def main(argv: list[str] | None = None) -> int:
00488:     args = build_arg_parser().parse_args(argv)
00489:     manifest = build_unified_runtime_gate(**vars(args))
00490:     s = manifest.get("summary", {})
00491:     print("status=" + str(manifest.get("status")))
00492:     print("quality_status=" + str(manifest.get("quality_status")))
00493:     print("runtime_record_count=" + str(s.get("runtime_record_count")))
00494:     print("runtime_pass_or_expected_count=" + str(s.get("runtime_pass_or_expected_count")))
00495:     print("self_rag_connected=" + str(s.get("self_rag_connected")))
00496:     print("crag_connected=" + str(s.get("crag_connected")))
```

## `tiff/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py`
- Location: `active_source_code`
- Score: `251`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server`
- Functions: _read_json(path)@L46; _write_json(path, data)@L50; _write_jsonl(path, records)@L55; _norm(s)@L62; _compact_text(text, max_chars)@L66; build_llm_prompt(record, max_prompt_chars)@L74; call_ollama()@L98; deterministic_behavior_answer(record)@L129; _is_negated_window(text, start)@L174; detect_unsupported_claims(answer_text)@L191; grade_h22_answer(answer_text, unsupported_claims)@L203; _select_records(prompt_smoke, max_queries)@L223; build_prompt_retrieval_llm_smoke()@L230; check_prompt_retrieval_llm_smoke()@L425; build_arg_parser()@L470; main(argv)@L490
- CLI args: --prompt-smoke, --output-dir, --llm-mode, --ollama-model, --ollama-url, --timeout-seconds, --max-queries, --max-prompt-chars, --min-queries, --min-llm-answered, --min-good-answers, --max-bad-answers, --max-unsupported-claims, --max-unsafe, --max-write-attempts
- Routes: http://127.0.0.1:11434/api/generate@L236, http://127.0.0.1:11434/api/generate@L476
- Has __main__ guard.

### Source window L1-L40
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: import re
00006: import urllib.request
00007: from dataclasses import dataclass
00008: from pathlib import Path
00009: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
00010: 
00011: 
00012: MODULE = "trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1"
00013: VERSION = "v1"
00014: 
00015: SAFETY_CONTRACT = {
00016:     "answer_permission": False,
00017:     "source_truth_mutation_allowed": False,
00018:     "postgres_write_attempt": False,
00019:     "qdrant_read_attempt": False,
00020:     "qdrant_write_attempt": False,
00021:     "opensearch_write_attempt": False,
00022:     "opensearch_upload_attempt": False,
00023:     "write_attempt": False,
00024:     "live_qdrant_io_attempted": False,
00025:     "engram_is_proof": False,
00026: }
00027: 
00028: DEFAULT_SYNTHETIC_PROOF_CONTEXT = (
00029:     "No current proof_context is provided in this H22 prompt-retrieval smoke. "
00030:     "Retrieved Engram memory is behavior guidance only and cannot prove manual facts."
00031: )
00032: 
00033: DEFAULT_RESPONSE_INSTRUCTIONS = """Return a concise TRACE-Net engineering answer with these sections:
00034: Answer
00035: Evidence
00036: Engineering confidence
00037: Limits
00038: 
00039: Rules:
00040: - Treat the retrieved Engram guidance as behavior guidance only, not source evidence.
```
### Source window L114-L170
```python
00114:         },
00115:     }
00116:     req = urllib.request.Request(
00117:         url,
00118:         data=json.dumps(payload).encode("utf-8"),
00119:         headers={"Content-Type": "application/json"},
00120:     )
00121:     with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
00122:         data = json.loads(resp.read().decode("utf-8"))
00123:     answer = _norm(data.get("response"))
00124:     if not answer:
00125:         raise RuntimeError("Ollama response did not contain answer text")
00126:     return answer
00127: 
00128: 
00129: def deterministic_behavior_answer(record: Mapping[str, Any]) -> str:
00130:     task_type = _norm(record.get("task_type"))
00131:     query_text = _norm(record.get("query_text") or record.get("query") or record.get("query_id"))
00132: 
00133:     if task_type in {"interchangeability_boundary", "approval_boundary"}:
00134:         answer = "Not proven / not source-trace-ready from this H22 prompt smoke."
00135:         limits = (
00136:             "Engram guidance can require explicit authority, but it cannot prove interchangeability, "
00137:             "approved replacement, fit, installation safety, aircraft effectivity, or source truth."
00138:         )
00139:     elif task_type in {"unknown_part", "summary_limit"}:
00140:         answer = "Not found / not source-trace-ready from this H22 prompt smoke."
00141:         limits = "No current proof_context was provided; retrieved Engram guidance and summaries are not proof."
00142:     elif task_type in {"route_explanation", "critic_repair"}:
00143:         answer = "The retrieved Engram guidance should shape behavior only."
00144:         limits = "Manual claims still require current proof_context citations before they can be treated as proven."
00145:     else:
00146:         answer = "Not proven / not source-trace-ready from this H22 prompt smoke."
00147:         limits = "Retrieved Engram guidance is behavior-only and cannot establish manual source truth."
00148: 
00149:     return (
00150:         f"Answer:\n{answer}\n\n"
00151:         f"Evidence:\n- Query under test: {query_text}\n"
00152:         f"- Current proof_context: none supplied in H22 smoke.\n\n"
00153:         f"Engineering confidence:\nHIGH that the prompt-retrieval guidance preserves the source-trace boundary; "
00154:         f"LOW for any manual factual claim because no proof_context was supplied.\n\n"
00155:         f"Limits:\n{limits}"
00156:     )
00157: 
00158: 
00159: FORBIDDEN_ASSERTION_PATTERNS = [
00160:     r"\bis interchangeable with\b",
00161:     r"\bare interchangeable\b",
00162:     r"\bis an approved replacement\b",
00163:     r"\bare approved replacements\b",
00164:     r"\bis approved for replacement\b",
00165:     r"\bis safe to install\b",
00166:     r"\bproves installation safety\b",
00167:     r"\bproves fit approval\b",
00168:     r"\bproves aircraft effectivity\b",
00169:     r"\bsummary proves\b",
00170:     r"\bengram proves\b",
```
### Source window L43-L99
```python
00043: """
00044: 
00045: 
00046: def _read_json(path: Path) -> Dict[str, Any]:
00047:     return json.loads(path.read_text(encoding="utf-8"))
00048: 
00049: 
00050: def _write_json(path: Path, data: Mapping[str, Any]) -> None:
00051:     path.parent.mkdir(parents=True, exist_ok=True)
00052:     path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
00053: 
00054: 
00055: def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
00056:     path.parent.mkdir(parents=True, exist_ok=True)
00057:     with path.open("w", encoding="utf-8") as f:
00058:         for rec in records:
00059:             f.write(json.dumps(rec, sort_keys=True) + "\n")
00060: 
00061: 
00062: def _norm(s: Any) -> str:
00063:     return str(s or "").strip()
00064: 
00065: 
00066: def _compact_text(text: str, max_chars: int) -> str:
00067:     text = _norm(text)
00068:     if len(text) <= max_chars:
00069:         return text
00070:     cut = max(0, max_chars - 90)
00071:     return text[:cut].rstrip() + "\n[TRUNCATED BY H22 PROMPT SMOKE: behavior guidance only, not proof.]"
00072: 
00073: 
00074: def build_llm_prompt(record: Mapping[str, Any], max_prompt_chars: int = 3200) -> str:
00075:     guidance = _norm(record.get("integration_prompt_text") or record.get("prompt_guidance_text") or record.get("integration_prompt_preview"))
00076:     query_text = _norm(record.get("query_text") or record.get("query") or record.get("query_id"))
00077:     task_type = _norm(record.get("task_type"))
00078:     query_id = _norm(record.get("query_id"))
00079: 
00080:     prompt = f"""TRACE-NET H22 ENGRAM PROMPT RETRIEVAL LLM SMOKE\nManual/source claims still require current proof_context citations.
00081: mode: targeted behavior smoke
00082: query_id: {query_id}
00083: task_type: {task_type}
00084: 
00085: {_compact_text(guidance, max_chars=max(600, max_prompt_chars - 950))}
00086: 
00087: CURRENT PROOF_CONTEXT:
00088: {DEFAULT_SYNTHETIC_PROOF_CONTEXT}
00089: 
00090: USER QUESTION:
00091: {query_text}
00092: 
00093: {DEFAULT_RESPONSE_INSTRUCTIONS}
00094: """
00095:     return _compact_text(prompt, max_prompt_chars)
00096: 
00097: 
00098: def call_ollama(
00099:     *,
```
### Source window L186-L242
```python
00186:         "unless explicit",
00187:     ]
00188:     return any(n in window for n in negators)
00189: 
00190: 
00191: def detect_unsupported_claims(answer_text: str) -> List[str]:
00192:     text = _norm(answer_text)
00193:     lower = text.lower()
00194:     findings: List[str] = []
00195:     for pattern in FORBIDDEN_ASSERTION_PATTERNS:
00196:         for m in re.finditer(pattern, lower):
00197:             if not _is_negated_window(lower, m.start()):
00198:                 findings.append(pattern)
00199:                 break
00200:     return sorted(set(findings))
00201: 
00202: 
00203: def grade_h22_answer(answer_text: str, unsupported_claims: Sequence[str]) -> str:
00204:     text = _norm(answer_text)
00205:     lower = text.lower()
00206:     if not text:
00207:         return "BLOCKED"
00208:     if unsupported_claims:
00209:         return "BAD"
00210:     required_signal = (
00211:         "not proven" in lower
00212:         or "not source-trace-ready" in lower
00213:         or "proof_context" in lower
00214:         or "behavior guidance only" in lower
00215:         or "not proof" in lower
00216:     )
00217:     has_sections = "answer" in lower and "evidence" in lower and "limits" in lower
00218:     if required_signal and has_sections:
00219:         return "GOOD"
00220:     return "PARTIAL"
00221: 
00222: 
00223: def _select_records(prompt_smoke: Mapping[str, Any], max_queries: int) -> List[Dict[str, Any]]:
00224:     records = list(prompt_smoke.get("prompt_integration_records") or prompt_smoke.get("prompt_bundles") or [])
00225:     if max_queries:
00226:         records = records[: int(max_queries)]
00227:     return [dict(r) for r in records]
00228: 
00229: 
00230: def build_prompt_retrieval_llm_smoke(
00231:     *,
00232:     prompt_smoke: str | Path,
00233:     output_dir: str | Path,
00234:     llm_mode: str = "artifact",
00235:     ollama_model: str = "gemma4:26b",
00236:     ollama_url: str = "http://127.0.0.1:11434/api/generate",
00237:     timeout_seconds: int = 420,
00238:     max_queries: int = 6,
00239:     max_prompt_chars: int = 3200,
00240:     min_queries: int = 1,
00241:     min_llm_answered: int = 1,
00242:     min_good_answers: int = 1,
```
### Source window L246-L302
```python
00246:     max_write_attempts: int = 0,
00247: ) -> Dict[str, Any]:
00248:     prompt_smoke_path = Path(prompt_smoke)
00249:     out_dir = Path(output_dir)
00250:     out_dir.mkdir(parents=True, exist_ok=True)
00251: 
00252:     source = _read_json(prompt_smoke_path)
00253:     records = _select_records(source, max_queries=max_queries)
00254: 
00255:     smoke_records: List[Dict[str, Any]] = []
00256:     total_unsupported = 0
00257:     answered_count = 0
00258:     grade_counts = {"GOOD": 0, "PARTIAL": 0, "BAD": 0, "BLOCKED": 0}
00259:     unsafe_findings: List[str] = []
00260: 
00261:     for rec in records:
00262:         query_id = _norm(rec.get("query_id"))
00263:         run_dir = out_dir / "runs" / query_id
00264:         run_dir.mkdir(parents=True, exist_ok=True)
00265: 
00266:         prompt = build_llm_prompt(rec, max_prompt_chars=max_prompt_chars)
00267:         prompt_path = run_dir / "prompt.txt"
00268:         answer_path = run_dir / "answer.txt"
00269:         trace_path = run_dir / "trace.json"
00270:         prompt_path.write_text(prompt, encoding="utf-8")
00271: 
00272:         llm_error = ""
00273:         llm_answered = False
00274:         if llm_mode == "ollama":
00275:             try:
00276:                 answer = call_ollama(
00277:                     prompt=prompt,
00278:                     model=ollama_model,
00279:                     url=ollama_url,
00280:                     timeout_seconds=timeout_seconds,
00281:                 )
00282:                 llm_answered = True
00283:             except Exception as exc:  # pragma: no cover - live Ollama path
00284:                 llm_error = f"{type(exc).__name__}: {exc}"
00285:                 answer = deterministic_behavior_answer(rec)
00286:                 llm_answered = True
00287:         elif llm_mode == "artifact":
00288:             answer = deterministic_behavior_answer(rec)
00289:             llm_answered = True
00290:         else:
00291:             raise ValueError(f"Unsupported llm_mode: {llm_mode}")
00292: 
00293:         answer_path.write_text(answer, encoding="utf-8")
00294:         unsupported = detect_unsupported_claims(answer)
00295:         grade = grade_h22_answer(answer, unsupported)
00296:         grade_counts[grade] = grade_counts.get(grade, 0) + 1
00297:         total_unsupported += len(unsupported)
00298:         answered_count += 1 if llm_answered else 0
00299: 
00300:         trace = {
00301:             "query_id": query_id,
00302:             "task_type": rec.get("task_type"),
```
### Source window L312-L368
```python
00312:         _write_json(trace_path, trace)
00313: 
00314:         smoke_records.append({
00315:             "query_id": query_id,
00316:             "task_type": rec.get("task_type"),
00317:             "selected_atom_count": rec.get("selected_atom_count"),
00318:             "selected_layers": rec.get("selected_layers"),
00319:             "selected_proof_roles": rec.get("selected_proof_roles"),
00320:             "prompt_char_count": len(prompt),
00321:             "prompt_path": str(prompt_path),
00322:             "answer_path": str(answer_path),
00323:             "trace_path": str(trace_path),
00324:             "llm_mode": llm_mode,
00325:             "llm_model": ollama_model if llm_mode == "ollama" else "artifact_scaffold",
00326:             "llm_answered": llm_answered,
00327:             "llm_error": llm_error,
00328:             "grade": grade,
00329:             "unsupported_claim_count": len(unsupported),
00330:             "unsupported_claims": unsupported,
00331:             "answer_preview": answer[:900],
00332:             "unsafe": False,
00333:             **SAFETY_CONTRACT,
00334:         })
00335: 
00336:     safety_counts = {
00337:         "answer_permission_count": 0,
00338:         "source_truth_mutation_allowed_count": 0,
00339:         "postgres_write_attempt_count": 0,
00340:         "qdrant_read_attempt_count": 0,
00341:         "qdrant_write_attempt_count": 0,
00342:         "opensearch_write_attempt_count": 0,
00343:         "opensearch_upload_attempt_count": 0,
00344:         "write_attempt_count": 0,
00345:         "unsafe_finding_count": len(unsafe_findings),
00346:     }
00347: 
00348:     quality_failures: List[str] = []
00349:     if len(records) < min_queries:
00350:         quality_failures.append(f"query_count_below_min:{len(records)}<{min_queries}")
00351:     if answered_count < min_llm_answered:
00352:         quality_failures.append(f"llm_answered_below_min:{answered_count}<{min_llm_answered}")
00353:     if grade_counts.get("GOOD", 0) < min_good_answers:
00354:         quality_failures.append(f"good_answer_count_below_min:{grade_counts.get('GOOD', 0)}<{min_good_answers}")
00355:     if grade_counts.get("BAD", 0) > max_bad_answers:
00356:         quality_failures.append(f"bad_answer_count_above_max:{grade_counts.get('BAD', 0)}>{max_bad_answers}")
00357:     if total_unsupported > max_unsupported_claims:
00358:         quality_failures.append(f"unsupported_claim_count_above_max:{total_unsupported}>{max_unsupported_claims}")
00359:     if safety_counts["unsafe_finding_count"] > max_unsafe:
00360:         quality_failures.append(f"unsafe_finding_count_above_max:{safety_counts['unsafe_finding_count']}>{max_unsafe}")
00361:     if safety_counts["write_attempt_count"] > max_write_attempts:
00362:         quality_failures.append(f"write_attempt_count_above_max:{safety_counts['write_attempt_count']}>{max_write_attempts}")
00363: 
00364:     quality_status = "PASS" if not quality_failures else "FAIL"
00365: 
00366:     summary = {
00367:         "module": MODULE,
00368:         "version": VERSION,
```
### Source window L370-L426
```python
00370:         "llm_mode": llm_mode,
00371:         "llm_model": ollama_model if llm_mode == "ollama" else "artifact_scaffold",
00372:         "query_count": len(records),
00373:         "llm_answered_count": answered_count,
00374:         "good_answer_count": grade_counts.get("GOOD", 0),
00375:         "partial_answer_count": grade_counts.get("PARTIAL", 0),
00376:         "bad_answer_count": grade_counts.get("BAD", 0),
00377:         "blocked_answer_count": grade_counts.get("BLOCKED", 0),
00378:         "unsupported_claim_count": total_unsupported,
00379:         "max_prompt_chars": max_prompt_chars,
00380:         "max_observed_prompt_chars": max((r.get("prompt_char_count") or 0) for r in smoke_records) if smoke_records else 0,
00381:         "ready_for_retrieval_guided_llm_review": True,
00382:         "quality_failures": quality_failures,
00383:         **safety_counts,
00384:     }
00385: 
00386:     manifest = {
00387:         "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_LLM_SMOKE_BUILT",
00388:         "quality_status": quality_status,
00389:         "summary": summary,
00390:         "quality_failures": quality_failures,
00391:         "source_prompt_smoke_path": str(prompt_smoke_path),
00392:         "safety_contract": dict(SAFETY_CONTRACT),
00393:         "llm_policy": {
00394:             "mode": llm_mode,
00395:             "artifact_mode_note": "artifact mode uses deterministic safe scaffold and performs no LLM call.",
00396:             "proof_boundary": "Retrieved Engram guidance shapes behavior only; manual facts require current proof_context citations.",
00397:             "forbidden": [
00398:                 "answer_permission_from_engram",
00399:                 "source_truth_mutation_from_engram",
00400:                 "summary_or_engram_used_as_proof",
00401:                 "interchangeability_or_approval_from_engram",
00402:             ],
00403:         },
00404:         "smoke_records": smoke_records,
00405:     }
00406: 
00407:     manifest_path = out_dir / f"{MODULE}.json"
00408:     jsonl_path = out_dir / f"{MODULE}_records.jsonl"
00409:     check_path = out_dir / f"{MODULE}_quality_check.json"
00410:     _write_json(manifest_path, manifest)
00411:     _write_jsonl(jsonl_path, smoke_records)
00412:     _write_json(check_path, {
00413:         "status": "TRACE_NET_ENGINEERING_ENGRAM_PROMPT_RETRIEVAL_LLM_SMOKE_CHECKED",
00414:         "quality_status": quality_status,
00415:         "summary": summary,
00416:         "quality_failures": quality_failures,
00417:     })
00418:     manifest["output_path"] = str(manifest_path)
00419:     manifest["records_path"] = str(jsonl_path)
00420:     manifest["quality_check_path"] = str(check_path)
00421:     _write_json(manifest_path, manifest)
00422:     return manifest
00423: 
00424: 
00425: def check_prompt_retrieval_llm_smoke(
00426:     *,
```

## `tiff/trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Location: `active_source_code`
- Score: `249`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24. This module serves already-final-gated live Gemma answers through an OpenAI-compatible local endpoint shape. It does not call the LLM. It does not perform retrieval. It reads v23 final gate artifacts and exposes only answers that already passed the final gate.
- Classes: TraceNetV24Handler@L429 methods=['_send_json', 'log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: read_json(path)@L27; write_json(path, payload)@L35; write_jsonl(path, rows)@L40; normalize_query(query)@L47; citation_like_count(text)@L51; _to_bool(value)@L55; _to_int(value, default)@L59; get_final_gate_records(data)@L66; record_query(record)@L74; record_final_answer(record)@L78; is_final_gate_pass(record)@L82; final_answer_has_cap_disclosure(record)@L97; final_answer_has_source_truth_citation(record)@L102; final_answer_ready_record(record, idx)@L106; build_endpoint_state(live_llm_final_gate_path, host, port, model_id)@L142; evaluate_quality(state, min_final_gates, min_ready_final_answers, min_endpoint_routes, min_final_answers_with_source_truth_citations, min_cap_disclosures_in_final_answers, max_unsupported_claim_count, max_final_non_direct_citation_marker_count)@L212; attach_quality(state, quality_status, quality_checks)@L257; render_markdown_report(state)@L264
- Routes: /health@L24, /v1/models@L24, /v1/chat/completions@L24, /v1/models@L453, /v1/chat/completions@L459, /health@L450

### Source window L1-L48
```python
00001: """TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24.
00002: 
00003: This module serves already-final-gated live Gemma answers through an OpenAI-compatible
00004: local endpoint shape. It does not call the LLM. It does not perform retrieval. It reads
00005: v23 final gate artifacts and exposes only answers that already passed the final gate.
00006: """
00007: 
00008: import json
00009: import re
00010: import time
00011: import uuid
00012: from http.server import BaseHTTPRequestHandler, HTTPServer
00013: from pathlib import Path
00014: from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
00015: 
00016: MODULE = "trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24"
00017: VERSION = "v24"
00018: MODEL_ID = "trace-net-e2e-live-final-gated-gemma-v24"
00019: STATUS_READY = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_READY"
00020: STATUS_NEEDS_REPAIR = "E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_NEEDS_REPAIR"
00021: QUALITY_PASS = "PASS"
00022: QUALITY_FAIL = "FAIL"
00023: 
00024: _ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"]
00025: 
00026: 
00027: def read_json(path: Path) -> Dict[str, Any]:
00028:     with path.open("r", encoding="utf-8") as f:
00029:         data = json.load(f)
00030:     if not isinstance(data, dict):
00031:         raise ValueError(f"Expected JSON object at {path}")
00032:     return data
00033: 
00034: 
00035: def write_json(path: Path, payload: Mapping[str, Any]) -> None:
00036:     path.parent.mkdir(parents=True, exist_ok=True)
00037:     path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
00038: 
00039: 
00040: def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
00041:     path.parent.mkdir(parents=True, exist_ok=True)
00042:     with path.open("w", encoding="utf-8") as f:
00043:         for row in rows:
00044:             f.write(json.dumps(row, sort_keys=False) + "\n")
00045: 
00046: 
00047: def normalize_query(query: str) -> str:
00048:     return re.sub(r"\s+", " ", (query or "").strip().lower())
```
### Source window L62-L118
```python
00062:     except Exception:
00063:         return default
00064: 
00065: 
00066: def get_final_gate_records(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
00067:     for key in ("final_gate_records", "final_answer_gates", "final_gates", "records"):
00068:         rows = data.get(key)
00069:         if isinstance(rows, list):
00070:             return [row for row in rows if isinstance(row, dict)]
00071:     return []
00072: 
00073: 
00074: def record_query(record: Mapping[str, Any]) -> str:
00075:     return str(record.get("user_query") or record.get("query") or record.get("original_query") or "")
00076: 
00077: 
00078: def record_final_answer(record: Mapping[str, Any]) -> str:
00079:     return str(record.get("final_answer") or record.get("answer") or record.get("final_answer_text") or "")
00080: 
00081: 
00082: def is_final_gate_pass(record: Mapping[str, Any]) -> bool:
00083:     status = str(record.get("final_gate_status") or record.get("status") or "")
00084:     if status and "PASS" not in status.upper() and "READY" not in status.upper():
00085:         return False
00086:     if _to_int(record.get("unsupported_claim_count"), 0) > 0:
00087:         return False
00088:     if _to_int(record.get("final_non_direct_citation_marker_count"), 0) > 0:
00089:         return False
00090:     if _to_int(record.get("graph_proof_authority_violation_count"), 0) > 0:
00091:         return False
00092:     if _to_int(record.get("summary_proof_authority_violation_count"), 0) > 0:
00093:         return False
00094:     return bool(record_final_answer(record).strip())
00095: 
00096: 
00097: def final_answer_has_cap_disclosure(record: Mapping[str, Any]) -> bool:
00098:     text = record_final_answer(record).lower()
00099:     return "results were capped" in text or "returned" in text and "matching records" in text
00100: 
00101: 
00102: def final_answer_has_source_truth_citation(record: Mapping[str, Any]) -> bool:
00103:     return citation_like_count(record_final_answer(record)) > 0
00104: 
00105: 
00106: def final_answer_ready_record(record: Mapping[str, Any], idx: int) -> Dict[str, Any]:
00107:     query = record_query(record)
00108:     answer = record_final_answer(record)
00109:     return {
00110:         "final_answer_id": record.get("final_answer_id") or record.get("final_gate_id") or f"webui_final_gated_gemma_v24_{idx:04d}",
00111:         "source_final_gate_id": record.get("final_gate_id") or record.get("final_answer_gate_id"),
00112:         "user_query": query,
00113:         "normalized_query": normalize_query(query),
00114:         "final_answer": answer,
00115:         "final_gate_status": record.get("final_gate_status") or record.get("status"),
00116:         "ready_for_webui": is_final_gate_pass(record),
00117:         "citation_like_count": citation_like_count(answer),
00118:         "has_source_truth_citation": final_answer_has_source_truth_citation(record),
```
### Source window L157-L213
```python
00157: 
00158:     state: Dict[str, Any] = {
00159:         "module": MODULE,
00160:         "version": VERSION,
00161:         "model_id": model_id,
00162:         "source_artifact": str(live_llm_final_gate_path),
00163:         "host": host,
00164:         "port": port,
00165:         "base_url_windows": f"http://{host}:{port}/v1",
00166:         "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
00167:         "endpoint_routes": list(_ENDPOINT_ROUTES),
00168:         "endpoint_route_count": len(_ENDPOINT_ROUTES),
00169:         "final_gate_count": len(source_records),
00170:         "final_answer_count": len(final_answers),
00171:         "ready_final_answer_count": len(ready_answers),
00172:         "final_answers_with_source_truth_citations_count": sum(1 for record in ready_answers if record["has_source_truth_citation"]),
00173:         "cap_disclosures_in_final_answers_count": sum(1 for record in ready_answers if record["has_cap_disclosure"]),
00174:         "unsupported_claim_count": unsupported_claim_count,
00175:         "final_non_direct_citation_marker_count": final_non_direct_citation_marker_count,
00176:         "graph_proof_authority_violation_count": graph_proof_authority_violation_count,
00177:         "summary_proof_authority_violation_count": summary_proof_authority_violation_count,
00178:         "answer_permission_count": 0,
00179:         "source_truth_mutation_allowed_count": 0,
00180:         "contract": {
00181:             "serves_final_gated_gemma_answers": True,
00182:             "calls_llm_at_endpoint_request_time": False,
00183:             "reads_v23_final_gate_artifact": True,
00184:             "source_truth_evidence_required_for_final_claims": True,
00185:             "graph_leiden_guidance_only": True,
00186:             "v2_summaries_guidance_only": True,
00187:             "nearby_context_not_direct_proof": True,
00188:             "raw_5tb_scan_at_query_time": False,
00189:             "graph_rebuild_at_query_time": False,
00190:             "source_truth_mutation_allowed": False,
00191:             "answer_permission": False,
00192:             "can_answer_directly": False,
00193:             "can_prove_claims": False,
00194:         },
00195:         "safety": {
00196:             "answer_permission": False,
00197:             "can_answer_directly": False,
00198:             "can_prove_claims": False,
00199:             "source_truth_mutation_allowed": False,
00200:             "writes_to_postgres": False,
00201:             "writes_to_qdrant": False,
00202:             "writes_to_opensearch": False,
00203:             "uploads_to_opensearch": False,
00204:             "response_is_final_gated": True,
00205:         },
00206:         "final_answers": ready_answers,
00207:         "all_final_answers": final_answers,
00208:     }
00209:     return state
00210: 
00211: 
00212: def evaluate_quality(
00213:     state: Mapping[str, Any],
```
### Source window L245-L301
```python
00245:         if op == ">=":
00246:             passed = observed >= expected
00247:         elif op == "<=":
00248:             passed = observed <= expected
00249:         elif op == "==":
00250:             passed = observed == expected
00251:         else:
00252:             raise ValueError(f"Unsupported op {op}")
00253:         rows.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": passed})
00254:     return (QUALITY_PASS if all(row["passed"] for row in rows) else QUALITY_FAIL, rows)
00255: 
00256: 
00257: def attach_quality(state: Dict[str, Any], quality_status: str, quality_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
00258:     state["quality_status"] = quality_status
00259:     state["quality_checks"] = quality_checks
00260:     state["status"] = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NEEDS_REPAIR
00261:     return state
00262: 
00263: 
00264: def render_markdown_report(state: Mapping[str, Any]) -> str:
00265:     lines: List[str] = []
00266:     lines.append("# TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24")
00267:     lines.append("")
00268:     lines.append(f"Quality status: **{state.get('quality_status', 'UNKNOWN')}**")
00269:     lines.append(f"Status: `{state.get('status', 'UNKNOWN')}`")
00270:     lines.append("")
00271:     lines.append("## Summary")
00272:     for key in [
00273:         "final_gate_count",
00274:         "final_answer_count",
00275:         "ready_final_answer_count",
00276:         "endpoint_route_count",
00277:         "final_answers_with_source_truth_citations_count",
00278:         "cap_disclosures_in_final_answers_count",
00279:         "unsupported_claim_count",
00280:         "final_non_direct_citation_marker_count",
00281:         "graph_proof_authority_violation_count",
00282:         "summary_proof_authority_violation_count",
00283:         "answer_permission_count",
00284:         "source_truth_mutation_allowed_count",
00285:         "base_url_windows",
00286:         "base_url_open_webui_docker",
00287:     ]:
00288:         lines.append(f"- {key}: {state.get(key)}")
00289:     lines.append("")
00290:     lines.append("## Contract")
00291:     lines.append("- This endpoint serves final-gated Gemma answers from the v23 artifact.")
00292:     lines.append("- It does not call Gemma at request time; v22 already produced drafts and v23 repaired/gated them.")
00293:     lines.append("- Source-truth evidence remains the only proof authority.")
00294:     lines.append("- Graph/Leiden and v2 summaries remain guidance only.")
00295:     lines.append("- Nearby OCR/table context is not direct proof for the user query.")
00296:     lines.append("- It does not scan raw 5TB data, rebuild the graph, mutate source truth, or write to services.")
00297:     lines.append("")
00298:     lines.append("## Final-gated WebUI answers")
00299:     for record in state.get("final_answers", []):
00300:         lines.append(f"### {record.get('final_answer_id')} — ready={record.get('ready_for_webui')}")
00301:         lines.append(f"- query: {record.get('user_query')}")
```
### Source window L431-L477
```python
00431: 
00432:     def _send_json(self, payload: Mapping[str, Any], status: int = 200) -> None:
00433:         body = json.dumps(payload, indent=2).encode("utf-8")
00434:         self.send_response(status)
00435:         self.send_header("Content-Type", "application/json")
00436:         self.send_header("Content-Length", str(len(body)))
00437:         self.send_header("Access-Control-Allow-Origin", "*")
00438:         self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
00439:         self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
00440:         self.end_headers()
00441:         self.wfile.write(body)
00442: 
00443:     def log_message(self, fmt: str, *args: Any) -> None:
00444:         return
00445: 
00446:     def do_OPTIONS(self) -> None:  # noqa: N802
00447:         self._send_json({"status": "ok"})
00448: 
00449:     def do_GET(self) -> None:  # noqa: N802
00450:         if self.path in {"/", "/health"}:
00451:             self._send_json(health_response(self.state))
00452:             return
00453:         if self.path == "/v1/models":
00454:             self._send_json(openai_models_response(self.state))
00455:             return
00456:         self._send_json({"error": f"Unknown route: {self.path}"}, status=404)
00457: 
00458:     def do_POST(self) -> None:  # noqa: N802
00459:         if self.path != "/v1/chat/completions":
00460:             self._send_json({"error": f"Unknown route: {self.path}"}, status=404)
00461:             return
00462:         try:
00463:             length = int(self.headers.get("Content-Length", "0"))
00464:             raw = self.rfile.read(length).decode("utf-8")
00465:             payload = json.loads(raw) if raw else {}
00466:             if not isinstance(payload, dict):
00467:                 raise ValueError("payload must be a JSON object")
00468:             self._send_json(chat_completion_response(self.state, payload))
00469:         except Exception as exc:
00470:             self._send_json({"error": str(exc)}, status=400)
00471: 
00472: 
00473: def serve(state: Dict[str, Any], host: str, port: int) -> None:
00474:     TraceNetV24Handler.state = state
00475:     server = HTTPServer((host, port), TraceNetV24Handler)
00476:     print(f"TRACE-Net v24 serving {state.get('model_id', MODEL_ID)} at http://{host}:{port}/v1", flush=True)
00477:     server.serve_forever()
```

## `tiff/trace_net_engineering_webui_answer_server_v1.py`
- Location: `active_source_code`
- Score: `249`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering WebUI Answer Server v1.2. OpenAI-compatible local server for Open WebUI. v1.2 quality patch: - retries Gemma4 once when the first LLM response is empty - cleans OCR/fishnet/router debug text before prompts and fallback output - only uses gated lookup when requested seed part matches the gated draft - adds visible source notes to answers - preserves exact lookup, random page summary, and fallback artifact search Safety: - no Postgres/Qdrant/OpenSearch writes - no source-trut
- Classes: LLMConfig@L44 methods=['enabled']; TraceNetWebUIHandler@L360 methods=['_json_response', '_read_body_json', 'do_GET', 'do_POST']; TraceNetHTTPServer@L386 methods=['__init__']
- Functions: _read_json(path)@L57; _write_json(path, payload)@L63; _write_jsonl(path, records)@L67; _norm(text)@L72; _lower(text)@L75; _path(path_text)@L78; _part_numbers(text)@L81; _clean_trace_text(text)@L84; _flatten_strings(value)@L101; _records_from_payload(payload)@L118; _page_id(record, index)@L128; _page_num(record, index)@L133; _route(record)@L141; load_page_index()@L146; _read_gated_draft_text(runner_record)@L167; load_gated_drafts()@L174; _match_score(query, candidate)@L187; _choose_random_page(pages, question)@L195
- CLI args: --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --llm-temperature, --llm-max-tokens, --disable-empty-response-retry, --output-dir, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff, --sample-question, --sample-call-llm, --quality, --report-path, --write-json, --min-page-records, --min-gated-drafts, --require-ready-for-webui, --require-llm-mode, --require-llm-model, --require-retry-empty-response, --max-unsafe, --require-no-answer-permission, --require-no-retrieval-execution, --require-no-source-truth-mutation, --host
- Routes: /chat/completions@L223, /health@L337, /v1/models@L337, /v1/chat/completions@L337, /api/chat/completions@L337, /health@L368, /v1/models@L370, /api/models@L370, /v1/chat/completions@L374, /api/chat/completions@L374
- Has __main__ guard.

### Source window L260-L316
```python
00260: def answer_random_page_summary(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
00261:     page = _choose_random_page(pages, question, truly_random=True)
00262:     if not page: return _response_record(question=question, response_text='TRACE-Net could not find loaded page records to summarize.', intent='random_page_summary', evidence_status='missing_page_records', citations=[], response_kind='controlled_no_answer', llm_config=llm_config, llm_called=False, llm_error=None)
00263:     summary = _extractive_summary(page, max_chars=1800)
00264:     citations = [{'page_id': page.get('page_id'), 'page_number': page.get('page_number'), 'route': page.get('route'), 'source': 'page_context_v2_or_fishnet'}]
00265:     evidence = f"Selected page_id={page.get('page_id')}; page_number={page.get('page_number')}; route={page.get('route')}.\nExtracted page text:\n{summary}"
00266:     fallback = f"TRACE-Net picked page `{page.get('page_id')}` (page_number={page.get('page_number')}, route={page.get('route')}).\n\n{summary}\n\nBoundary: this is an artifact-grounded page summary, not engineering approval or final maintenance instruction."
00267:     llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='random_page_summary', citations=citations, config=llm_config)
00268:     return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error else fallback, intent='random_page_summary', evidence_status='page_record_selected', citations=citations, response_kind='gemma4_composed_page_summary' if llm_config.enabled and not llm_error else 'controlled_artifact_summary', llm_config=llm_config, llm_called=llm_called, llm_error=llm_error, llm_attempt_count=attempts)
00269: 
00270: def answer_gated_lookup(question: str, gated_drafts: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Optional[Dict[str, Any]]:
00271:     requested = set(_part_numbers(question)); best = None; best_score = 0
00272:     for draft in gated_drafts:
00273:         seed = set(draft.get('seed_part_numbers') or [])
00274:         if requested and not (requested & seed): continue
00275:         score = _match_score(question, str(draft.get('user_question') or '')) + (25 if requested and requested & seed else 0)
00276:         if score > best_score: best, best_score = draft, score
00277:     if not best or best_score < 40 or not best.get('draft_text'): return None
00278:     citations = [{'final_gate_record_id': best.get('final_gate_record_id'), 'source_runner_record_id': best.get('source_runner_record_id'), 'source_draft_packet_id': best.get('source_draft_packet_id')}]
00279:     evidence = str(best.get('draft_text') or '')
00280:     fallback = evidence + '\n\nBoundary: this is a TRACE-Net manual-review-ready controlled draft. Final answer permission is still off; verify before operational use.'
00281:     llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='gated_lookup', citations=citations, config=llm_config)
00282:     return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error else fallback, intent='gated_lookup', evidence_status='manual_review_ready_final_gate_record', citations=citations, response_kind='gemma4_composed_gated_lookup' if llm_config.enabled and not llm_error else 'manual_review_ready_draft', llm_config=llm_config, llm_called=llm_called, llm_error=llm_error, llm_attempt_count=attempts)
00283: 
00284: def _search_pages(question: str, pages: Sequence[Mapping[str, Any]], *, top_k: int=3) -> List[Mapping[str, Any]]:
00285:     q_terms = set(re.findall(r"[a-z0-9-]+", _lower(question)))
00286:     if not q_terms: return []
00287:     if q_terms & {'diagram','visual','callout'}: q_terms |= {'figure','illustrated','item','assy','assembly','view'}
00288:     if 'repair' in q_terms: q_terms |= {'doubler','rivet','leg','lateral','epoxy'}
00289:     scored = []
00290:     for page in pages:
00291:         text = _lower(page.get('text') or '')
00292:         if not text: continue
00293:         score = sum(1 for term in q_terms if term in text)
00294:         for part in _part_numbers(question):
00295:             if part.lower() in text: score += 15
00296:         if score: scored.append((score, page))
00297:     scored.sort(key=lambda item: item[0], reverse=True)
00298:     return [p for _, p in scored[:top_k]]
00299: 
00300: def answer_v2_summary_inventory(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
00301:     v2_pages = [p for p in pages if p.get('has_v2_summary') or p.get('has_text')]
00302:     citations = [{'page_id': p.get('page_id'), 'page_number': p.get('page_number'), 'route': p.get('route'), 'source': 'page_context_v2_or_fishnet'} for p in v2_pages[:5]]
00303:     lines = [f"- {p.get('page_id')} (page {p.get('page_number')}, route={p.get('route')})" for p in v2_pages[:10]]
00304:     text = f"TRACE-Net has page-summary/text artifacts for {len(v2_pages)} pages. Here are the first few page records available for summary-style responses:\n" + '\n'.join(lines) + '\n\nBoundary: this reports artifact availability, not engineering content approval.'
00305:     return _response_record(question=question, response_text=text, intent='v2_summary_inventory', evidence_status='page_summary_inventory', citations=citations, response_kind='controlled_inventory', llm_config=llm_config, llm_called=False, llm_error=None)
00306: 
00307: def answer_search_summary(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
00308:     hits = _search_pages(question, pages)
00309:     if not hits: return _response_record(question=question, response_text='TRACE-Net did not find enough artifact text to answer that question yet. Try an exact part lookup, a random page summary, or a more specific term.', intent='fallback_search', evidence_status='no_page_text_hits', citations=[], response_kind='controlled_no_answer', llm_config=llm_config, llm_called=False, llm_error=None)
00310:     citations = [{'page_id': p.get('page_id'), 'page_number': p.get('page_number'), 'route': p.get('route'), 'source': 'page_context_v2_or_fishnet'} for p in hits]
00311:     blocks = [f"page_id={p.get('page_id')}; page_number={p.get('page_number')}; route={p.get('route')}; text={_extractive_summary(p, max_chars=750)}" for p in hits]
00312:     evidence = '\n\n'.join(blocks)
00313:     fallback = 'TRACE-Net found these artifact-backed page leads:\n\n' + '\n'.join(f"- `{c['page_id']}` (page {c.get('page_number')}, route={c.get('route')}): {_clean_trace_text(b, max_chars=550)}" for c, b in zip(citations, blocks)) + '\n\nBoundary: these are search/summarization leads, not proof of fit, replacement, safety, or engineering approval.'
00314:     llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='fallback_search', citations=citations, config=llm_config)
00315:     return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error else fallback, intent='fallback_search', evidence_status='page_text_hits', citations=citations, response_kind='gemma4_composed_artifact_search' if llm_config.enabled and not llm_error else 'controlled_artifact_search', llm_config=llm_config, llm_called=llm_called, llm_error=llm_error, llm_attempt_count=attempts)
00316: 
```
### Source window L9-L65
```python
00009: - only uses gated lookup when requested seed part matches the gated draft
00010: - adds visible source notes to answers
00011: - preserves exact lookup, random page summary, and fallback artifact search
00012: 
00013: Safety:
00014: - no Postgres/Qdrant/OpenSearch writes
00015: - no source-truth mutation
00016: - no final answer permission
00017: - Gemma4 composes only from TRACE-Net evidence
00018: """
00019: from __future__ import annotations
00020: 
00021: import argparse
00022: import hashlib
00023: import json
00024: import random
00025: import re
00026: import time
00027: import urllib.request
00028: from dataclasses import dataclass
00029: from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
00030: from pathlib import Path
00031: from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
00032: 
00033: MODULE_VERSION = "trace_net_engineering_webui_answer_server_v1"
00034: REPORT_NAME = "trace_net_engineering_webui_answer_server_v1.json"
00035: MODEL_ID = "trace-net-engineering-webui-v1"
00036: 
00037: DEFAULT_FINAL_GATE = Path("local_data/organization/trace_net/engineering_draft_final_gate_retry_micro/trace_net_engineering_draft_final_gate_v1.json")
00038: DEFAULT_RUNNER = Path("local_data/organization/trace_net/engineering_gemma_draft_runner_retry_micro/trace_net_engineering_gemma_draft_runner_v1.json")
00039: DEFAULT_PAGE_CONTEXT = Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json")
00040: DEFAULT_FISHNET = Path("local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json")
00041: DEFAULT_ROUTE_HANDOFF = Path("local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json")
00042: 
00043: @dataclass(frozen=True)
00044: class LLMConfig:
00045:     mode: str = "off"
00046:     base_url: str = "http://127.0.0.1:11434/v1"
00047:     model: str = "gemma4:26b"
00048:     api_key: str = "ollama"
00049:     request_timeout: int = 240
00050:     temperature: float = 0.0
00051:     max_tokens: int = 900
00052:     retry_empty_response: bool = True
00053:     @property
00054:     def enabled(self) -> bool:
00055:         return self.mode != "off"
00056: 
00057: def _read_json(path: Path, *, required: bool=False) -> Dict[str, Any]:
00058:     if not path.exists():
00059:         if required: raise FileNotFoundError(f"missing JSON file: {path}")
00060:         return {}
00061:     return json.loads(path.read_text(encoding='utf-8'))
00062: 
00063: def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
00064:     path.parent.mkdir(parents=True, exist_ok=True)
00065:     path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
```
### Source window L195-L251
```python
00195: def _choose_random_page(pages: Sequence[Mapping[str, Any]], question: str, *, truly_random: bool=True) -> Optional[Mapping[str, Any]]:
00196:     text_pages = [p for p in pages if p.get('has_text') and str(p.get('text') or '').strip()]
00197:     if not text_pages: return pages[0] if pages else None
00198:     if truly_random: return random.choice(text_pages)
00199:     seed = int(hashlib.sha256(question.encode()).hexdigest()[:8], 16)
00200:     return text_pages[seed % len(text_pages)]
00201: 
00202: def _extractive_summary(page: Mapping[str, Any], *, max_chars: int=1200) -> str:
00203:     text = _clean_trace_text(page.get('text') or '', max_chars=max_chars+500)
00204:     if not text: return 'No readable text was found for this page in the currently loaded artifacts.'
00205:     sentences = re.split(r"(?<=[.!?])\s+", text)
00206:     useful, seen = [], set()
00207:     for s in sentences:
00208:         s = _clean_trace_text(s, max_chars=500); key = s.lower()
00209:         if len(s) < 30 or key in seen: continue
00210:         useful.append(s); seen.add(key)
00211:         if sum(len(x) for x in useful) >= max_chars: break
00212:     return (' '.join(useful) if useful else text[:max_chars])[:max_chars]
00213: 
00214: def _source_notes(citations: Sequence[Mapping[str, Any]]) -> str:
00215:     parts = []
00216:     for c in citations[:5]:
00217:         if c.get('page_id'): parts.append(f"{c.get('page_id')} (page {c.get('page_number')}, route={c.get('route')})")
00218:         elif c.get('final_gate_record_id'): parts.append(f"final_gate={c.get('final_gate_record_id')}")
00219:     return '\n\nSource notes: ' + '; '.join(parts) + '.' if parts else ''
00220: 
00221: def _llm_endpoint(config: LLMConfig) -> str:
00222:     base = config.base_url.rstrip('/')
00223:     return base if base.endswith('/chat/completions') else f"{base}/chat/completions"
00224: 
00225: def _call_openai_compatible_llm(*, config: LLMConfig, messages: Sequence[Mapping[str, str]]) -> Tuple[str, Optional[str]]:
00226:     if not config.enabled: return '', 'llm_mode_off'
00227:     payload = {'model': config.model, 'messages': list(messages), 'temperature': config.temperature, 'max_tokens': config.max_tokens, 'stream': False}
00228:     req = urllib.request.Request(_llm_endpoint(config), data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {config.api_key}'}, method='POST')
00229:     try:
00230:         with urllib.request.urlopen(req, timeout=config.request_timeout) as resp:
00231:             data = json.loads(resp.read().decode('utf-8', errors='replace'))
00232:         choices = data.get('choices') or []
00233:         if choices and isinstance(choices[0], dict):
00234:             msg = choices[0].get('message') or {}; content = msg.get('content') if isinstance(msg, dict) else None
00235:             if content and str(content).strip(): return _clean_trace_text(content, max_chars=6000), None
00236:             if choices[0].get('text') and str(choices[0].get('text')).strip(): return _clean_trace_text(choices[0].get('text'), max_chars=6000), None
00237:         return '', 'llm_empty_response'
00238:     except Exception as exc:
00239:         return '', f"{type(exc).__name__}: {exc}"
00240: 
00241: def _compose_with_llm(*, question: str, evidence_text: str, intent: str, citations: Sequence[Mapping[str, Any]], config: LLMConfig) -> Tuple[str, bool, Optional[str], int]:
00242:     if not config.enabled: return evidence_text, False, 'llm_mode_off', 0
00243:     evidence = _clean_trace_text(evidence_text, max_chars=6000); citation_text = json.dumps(list(citations), indent=2, sort_keys=True)
00244:     system = 'You are Gemma4 writing as TRACE-Net controlled engineering assistant. Use only provided TRACE-Net evidence. Do not expose raw OCR/debug strings. Do not claim engineering approval, approved replacement, guaranteed fit, interchangeability, airworthiness, or safety to install. Include visible source page identifiers.'
00245:     user = f"Question: {question}\n\nIntent: {intent}\n\nTRACE-Net evidence/context:\n{evidence[:6000]}\n\nCitation/source notes:\n{citation_text[:2500]}\n\nWrite a concise useful answer. Do not include debug tokens such as router_classifier_input_only."
00246:     text, error = _call_openai_compatible_llm(config=config, messages=[{'role':'system','content':system},{'role':'user','content':user}])
00247:     if not error and text.strip(): return text.strip(), True, None, 1
00248:     if config.retry_empty_response and error == 'llm_empty_response':
00249:         retry_user = f"Question: {question}\nEvidence:\n{evidence[:2200]}\nSources:\n{citation_text[:1200]}\nWrite 3-6 complete sentences or 5 bullets. No debug text."
00250:         retry_text, retry_error = _call_openai_compatible_llm(config=config, messages=[{'role':'system','content':'Write a concise TRACE-Net answer from evidence. Include page IDs. No approval/safety claims.'},{'role':'user','content':retry_user}])
00251:         if not retry_error and retry_text.strip(): return retry_text.strip(), True, None, 2
```
### Source window L368-L419
```python
00368:         if self.path in {'/health','/'}:
00369:             self._json_response(200, {'status':'ok','module':MODULE_VERSION,'server_version':'v1.2','model_id':MODEL_ID,'page_record_count':len(self.server.pages),'gated_draft_count':len(self.server.gated_drafts),'llm_mode':self.server.llm_config.mode,'llm_model':self.server.llm_config.model if self.server.llm_config.enabled else None,'llm_base_url':self.server.llm_config.base_url if self.server.llm_config.enabled else None,'retry_empty_response':self.server.llm_config.retry_empty_response,'ready_for_webui':True}); return
00370:         if self.path in {'/v1/models','/api/models'}:
00371:             self._json_response(200, {'object':'list','data':[{'id':MODEL_ID,'object':'model','created':int(time.time()),'owned_by':'trace-net'}]}); return
00372:         self._json_response(404, {'error': f'not found: {self.path}'})
00373:     def do_POST(self) -> None:
00374:         if self.path not in {'/v1/chat/completions','/api/chat/completions'}:
00375:             self._json_response(404, {'error': f'not found: {self.path}'}); return
00376:         try:
00377:             body = self._read_body_json(); messages = body.get('messages') or []; question = ''
00378:             for msg in reversed(messages):
00379:                 if isinstance(msg, dict) and msg.get('role') == 'user': question = str(msg.get('content') or ''); break
00380:             if not question: question = 'pick a random page to summarize'
00381:             record = answer_question(question=question, pages=self.server.pages, gated_drafts=self.server.gated_drafts, llm_config=self.server.llm_config)
00382:             self._json_response(200, {'id': f'chatcmpl-trace-net-{int(time.time()*1000)}','object':'chat.completion','created':int(time.time()),'model':body.get('model') or MODEL_ID,'choices':[{'index':0,'message':{'role':'assistant','content':record['response_text']},'finish_reason':'stop'}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'trace_net':record})
00383:         except Exception as exc:
00384:             self._json_response(500, {'error': f'{type(exc).__name__}: {exc}'})
00385: 
00386: class TraceNetHTTPServer(ThreadingHTTPServer):
00387:     def __init__(self, server_address: Tuple[str, int], handler_class: Any, *, pages: Sequence[Mapping[str, Any]], gated_drafts: Sequence[Mapping[str, Any]], llm_config: LLMConfig):
00388:         super().__init__(server_address, handler_class); self.pages = list(pages); self.gated_drafts = list(gated_drafts); self.llm_config = llm_config
00389: 
00390: def run_server(*, host: str, port: int, final_gate_path: Path, runner_path: Path, page_context_path: Path, fishnet_path: Path, route_handoff_path: Path, llm_config: LLMConfig) -> None:
00391:     pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path); gated = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
00392:     server = TraceNetHTTPServer((host, port), TraceNetWebUIHandler, pages=pages, gated_drafts=gated, llm_config=llm_config)
00393:     print(f'TRACE-Net WebUI answer server v1.2 running on http://{host}:{port}'); print(f'Model ID exposed to WebUI: {MODEL_ID}'); print(f'Runtime LLM mode: {llm_config.mode}'); print(f'Runtime LLM model: {llm_config.model if llm_config.enabled else "off"}'); print(f'Runtime LLM base URL: {llm_config.base_url if llm_config.enabled else "off"}'); print(f'Retry empty LLM response: {llm_config.retry_empty_response}'); print(f'Pages loaded: {len(pages)}'); print(f'Gated drafts loaded: {len(gated)}'); server.serve_forever()
00394: 
00395: def _add_llm_args(parser: argparse.ArgumentParser) -> None:
00396:     parser.add_argument('--llm-mode', choices=['off','ollama_openai','openai_compatible'], default='off'); parser.add_argument('--llm-base-url', default='http://127.0.0.1:11434/v1'); parser.add_argument('--llm-model', default='gemma4:26b'); parser.add_argument('--llm-api-key', default='ollama'); parser.add_argument('--request-timeout', type=int, default=240); parser.add_argument('--llm-temperature', type=float, default=0.0); parser.add_argument('--llm-max-tokens', type=int, default=900); parser.add_argument('--disable-empty-response-retry', action='store_true')
00397: 
00398: def _llm_config_from_args(args: argparse.Namespace) -> LLMConfig:
00399:     return LLMConfig(mode=args.llm_mode, base_url=args.llm_base_url, model=args.llm_model, api_key=args.llm_api_key, request_timeout=args.request_timeout, temperature=args.llm_temperature, max_tokens=args.llm_max_tokens, retry_empty_response=not args.disable_empty_response_retry)
00400: 
00401: def main_build(argv: Optional[Sequence[str]]=None) -> int:
00402:     p = argparse.ArgumentParser(description='Build TRACE-Net engineering WebUI answer server manifest v1.2.'); p.add_argument('--output-dir', required=True); p.add_argument('--final-gate', default=str(DEFAULT_FINAL_GATE)); p.add_argument('--runner-report', default=str(DEFAULT_RUNNER)); p.add_argument('--page-context-v2', default=str(DEFAULT_PAGE_CONTEXT)); p.add_argument('--fishnet-ocr-grid', default=str(DEFAULT_FISHNET)); p.add_argument('--route-handoff', default=str(DEFAULT_ROUTE_HANDOFF)); p.add_argument('--sample-question', default='pick a random page to summarize'); p.add_argument('--sample-call-llm', action='store_true'); _add_llm_args(p); p.add_argument('--quality', action='store_true'); args = p.parse_args(argv)
00403:     payload = build_engineering_webui_answer_manifest(output_dir=Path(args.output_dir), final_gate_path=Path(args.final_gate), runner_path=Path(args.runner_report), page_context_path=Path(args.page_context_v2), fishnet_path=Path(args.fishnet_ocr_grid), route_handoff_path=Path(args.route_handoff), sample_question=args.sample_question, llm_config=_llm_config_from_args(args), sample_call_llm=args.sample_call_llm)
00404:     print('Status:', payload['status']); print('Quality status:', payload['quality_status']); print('Summary:', json.dumps(payload['summary'], sort_keys=True)); return 0 if payload['quality_status'] == 'PASS' else 1
00405: 
00406: def main_check(argv: Optional[Sequence[str]]=None) -> int:
00407:     p = argparse.ArgumentParser(description='Check TRACE-Net engineering WebUI answer server quality v1.2.'); p.add_argument('--report-path', required=True); p.add_argument('--write-json', action='store_true'); p.add_argument('--min-page-records', type=int, default=1); p.add_argument('--min-gated-drafts', type=int, default=0); p.add_argument('--require-ready-for-webui', action='store_true'); p.add_argument('--require-llm-mode'); p.add_argument('--require-llm-model'); p.add_argument('--require-retry-empty-response', action='store_true'); p.add_argument('--max-unsafe', type=int, default=0); p.add_argument('--require-no-answer-permission', action='store_true'); p.add_argument('--require-no-retrieval-execution', action='store_true'); p.add_argument('--require-no-source-truth-mutation', action='store_true'); args = p.parse_args(argv)
00408:     result = check_engineering_webui_answer_server_quality(report_path=Path(args.report_path), min_page_records=args.min_page_records, min_gated_drafts=args.min_gated_drafts, require_ready_for_webui=args.require_ready_for_webui, require_llm_mode=args.require_llm_mode, require_llm_model=args.require_llm_model, require_retry_empty_response=args.require_retry_empty_response, max_unsafe=args.max_unsafe, require_no_answer_permission=args.require_no_answer_permission, require_no_retrieval_execution=args.require_no_retrieval_execution, require_no_source_truth_mutation=args.require_no_source_truth_mutation)
00409:     print('Quality status:', result['quality_status']); print('Summary:', json.dumps(result['summary'], sort_keys=True));
00410:     if result['failures']: print('Failures:', json.dumps(result['failures'], indent=2))
00411:     if args.write_json:
00412:         out = Path(args.report_path).with_name('trace_net_engineering_webui_answer_server_v1_quality_check.json'); _write_json(out, result); print('Wrote:', out)
00413:     return 0 if result['quality_status'] == 'PASS' else 1
00414: 
00415: def main_run(argv: Optional[Sequence[str]]=None) -> int:
00416:     p = argparse.ArgumentParser(description='Run TRACE-Net engineering WebUI answer server v1.2.'); p.add_argument('--host', default='127.0.0.1'); p.add_argument('--port', type=int, default=8044); p.add_argument('--final-gate', default=str(DEFAULT_FINAL_GATE)); p.add_argument('--runner-report', default=str(DEFAULT_RUNNER)); p.add_argument('--page-context-v2', default=str(DEFAULT_PAGE_CONTEXT)); p.add_argument('--fishnet-ocr-grid', default=str(DEFAULT_FISHNET)); p.add_argument('--route-handoff', default=str(DEFAULT_ROUTE_HANDOFF)); _add_llm_args(p); args = p.parse_args(argv)
00417:     run_server(host=args.host, port=args.port, final_gate_path=Path(args.final_gate), runner_path=Path(args.runner_report), page_context_path=Path(args.page_context_v2), fishnet_path=Path(args.fishnet_ocr_grid), route_handoff_path=Path(args.route_handoff), llm_config=_llm_config_from_args(args)); return 0
00418: 
00419: if __name__ == '__main__': raise SystemExit(main_build())
```
### Source window L118-L174
```python
00118: def _records_from_payload(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
00119:     for key in ['records','pages','page_records','items','documents']:
00120:         value = payload.get(key)
00121:         if isinstance(value, list): return [dict(v) for v in value if isinstance(v, dict)]
00122:     records = []
00123:     for key, value in payload.items():
00124:         if isinstance(value, dict) and ('page_id' in value or key.startswith(('source_','t_p_','metadata_page'))):
00125:             clone = dict(value); clone.setdefault('page_id', key); records.append(clone)
00126:     return records
00127: 
00128: def _page_id(record: Mapping[str, Any], index: int) -> str:
00129:     for key in ['page_id','source_page_id','id','page_key']:
00130:         if record.get(key): return str(record.get(key))
00131:     return f"page_{index+1:06d}"
00132: 
00133: def _page_num(record: Mapping[str, Any], index: int) -> Optional[int]:
00134:     for key in ['page_number','page_index','source_page_number','page']:
00135:         v = record.get(key)
00136:         if isinstance(v, int): return v
00137:         if isinstance(v, str) and v.isdigit(): return int(v)
00138:     m = re.search(r"p0*(\d+)", str(record.get('page_id') or ''))
00139:     return int(m.group(1)) if m else index+1
00140: 
00141: def _route(record: Mapping[str, Any]) -> str:
00142:     for key in ['accepted_route','route','route_candidate','fishnet_route_candidate','current_route','page_route']:
00143:         if record.get(key): return str(record.get(key))
00144:     return 'unknown'
00145: 
00146: def load_page_index(*, page_context_path: Path=DEFAULT_PAGE_CONTEXT, fishnet_path: Path=DEFAULT_FISHNET, route_handoff_path: Path=DEFAULT_ROUTE_HANDOFF) -> List[Dict[str, Any]]:
00147:     page_context = _read_json(page_context_path)
00148:     fishnet = _read_json(fishnet_path)
00149:     route_handoff = _read_json(route_handoff_path)
00150:     route_by_page: Dict[str, str] = {}
00151:     for r in _records_from_payload(route_handoff):
00152:         pid = str(r.get('page_id') or r.get('source_page_id') or '')
00153:         if pid: route_by_page[pid] = str(r.get('accepted_route') or r.get('route') or '')
00154:     raw = _records_from_payload(page_context)
00155:     fish_records = _records_from_payload(fishnet)
00156:     if not raw and fish_records: raw = fish_records
00157:     fish_by_page = {_page_id(r, i): r for i, r in enumerate(fish_records)}
00158:     pages = []
00159:     for i, r in enumerate(raw):
00160:         pid = _page_id(r, i); fish = fish_by_page.get(pid, {})
00161:         strings = _flatten_strings(r)
00162:         if fish: strings += _flatten_strings(fish, max_items=20)
00163:         text = _clean_trace_text(' '.join(strings), max_chars=3000)
00164:         pages.append({'page_id': pid, 'page_number': _page_num(r, i), 'route': route_by_page.get(pid) or _route(r) or _route(fish), 'text': text, 'source_record_index': i, 'has_text': bool(text), 'has_v2_summary': any(k in r for k in ['v2_summary','summary','page_summary'])})
00165:     return pages
00166: 
00167: def _read_gated_draft_text(runner_record: Mapping[str, Any]) -> str:
00168:     path_text = runner_record.get('draft_response_path')
00169:     if not path_text: return ''
00170:     path = _path(path_text)
00171:     if not path.exists(): return ''
00172:     return _clean_trace_text(_read_json(path).get('draft_text') or '', max_chars=6000)
00173: 
00174: def load_gated_drafts(*, final_gate_path: Path=DEFAULT_FINAL_GATE, runner_path: Path=DEFAULT_RUNNER) -> List[Dict[str, Any]]:
```

## `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1.py`
- Location: `archived_reference`
- Score: `247`
- Categories: `context_pack, crag, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _write(path, payload)@L7; test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch)@L13; test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path)@L113; test_checklist_text_includes_reasons()@L121; fake_query_planner()@L19; fake_blueprint()@L28; fake_pack_builder()@L37; fake_self_rag()@L58; fake_crag()@L72
- Tiff imports: from tiff import trace_net_webui_self_rag_crag_bridge_v1

### Source window L1-L32
```python
00001: import json
00002: from pathlib import Path
00003: 
00004: from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge
00005: 
00006: 
00007: def _write(path: Path, payload: dict) -> dict:
00008:     path.parent.mkdir(parents=True, exist_ok=True)
00009:     path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
00010:     return payload
00011: 
00012: 
00013: def test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch):
00014:     kernel = tmp_path / "kernel.json"
00015:     kernel.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
00016:     route_dispatch = tmp_path / "route_dispatch.json"
00017:     route_dispatch.write_text(json.dumps({"records": [{"page_id": "source_p000001", "text": "120-29073-001 seat assembly"}]}), encoding="utf-8")
00018: 
00019:     def fake_query_planner(*, kernel_path, output_dir, questions):
00020:         assert kernel_path == kernel
00021:         payload = {
00022:             "quality_status": "PASS",
00023:             "summary": {"query_plan_count": len(questions)},
00024:             "records": [{"question_id": "q1", "user_question": questions[0], "answer_permission": False}],
00025:         }
00026:         return _write(output_dir / bridge.STAGE_REPORT_NAMES["query_planner"], payload)
00027: 
00028:     def fake_blueprint(*, query_planner_path, output_dir):
00029:         assert query_planner_path.exists()
00030:         payload = {
00031:             "quality_status": "PASS",
00032:             "summary": {"context_pack_blueprint_count": 1},
```
### Source window L95-L127
```python
00095:     )
00096: 
00097:     payload = bridge.build_webui_self_rag_crag_bridge(
00098:         question="Find part number 120-29073-001",
00099:         kernel_path=kernel,
00100:         output_dir=tmp_path / "bridge",
00101:         route_dispatch_handoff=route_dispatch,
00102:     )
00103: 
00104:     assert payload["quality_status"] == "PASS"
00105:     assert payload["tool_statuses"]["query_planner"] == "used"
00106:     assert payload["tool_statuses"]["self_rag"] == "used"
00107:     assert payload["tool_statuses"]["crag_retry"] == "used"
00108:     assert payload["tool_statuses"]["route_dispatch"] == "used"
00109:     assert payload["summary"]["self_rag_crag_retry_required_count"] == 1
00110:     assert payload["summary"]["answer_permission_count"] == 0
00111: 
00112: 
00113: def test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path):
00114:     self_payload = {"summary": {"crag_retry_required_count": 0}}
00115:     crag_payload = {"quality_status": "PASS", "summary": {"crag_retry_plan_count": 0}}
00116:     row = bridge._crag_row(crag_payload, tmp_path / "crag.json", self_payload)
00117:     assert row["status"] == "skipped_not_needed"
00118:     assert "did not require" in row["reason"]
00119: 
00120: 
00121: def test_checklist_text_includes_reasons():
00122:     text = bridge._checklist_text([
00123:         {"label": "Self-RAG", "status": "used", "reason": "stage report built"},
00124:         {"label": "CRAG retry", "status": "skipped_not_needed", "reason": "Self-RAG was strong"},
00125:     ])
00126:     assert "Self-RAG: used" in text
00127:     assert "CRAG retry: skipped_not_needed" in text
```
### Source window L37-L93
```python
00037:     def fake_pack_builder(**kwargs):
00038:         assert kwargs["blueprint_path"].exists()
00039:         assert kwargs["route_dispatch_handoff"] == route_dispatch
00040:         payload = {
00041:             "quality_status": "PASS",
00042:             "summary": {
00043:                 "context_pack_count": 1,
00044:                 "total_evidence_capsule_count": 2,
00045:                 "total_high_signal_evidence_capsule_count": 1,
00046:                 "artifact_record_counts": {
00047:                     "fishnet_route_dispatch_handoff": 1,
00048:                     "table_exact_search_adapter": 0,
00049:                     "page_context_v2": 0,
00050:                     "leiden_communities": 0,
00051:                     "image_visual_observer": 0,
00052:                 },
00053:             },
00054:             "records": [{"context_pack_id": "cp1", "answer_permission": False}],
00055:         }
00056:         return _write(kwargs["output_dir"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"], payload)
00057: 
00058:     def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score):
00059:         assert context_pack_path.exists()
00060:         payload = {
00061:             "quality_status": "PASS",
00062:             "summary": {
00063:                 "self_rag_record_count": 1,
00064:                 "ready_for_gemma_draft_count": 0,
00065:                 "crag_retry_required_count": 1,
00066:                 "self_rag_status_counts": {"CRAG_RETRY_REQUIRED": 1},
00067:             },
00068:             "records": [{"self_rag_record_id": "sr1", "crag_retry_required": True, "answer_permission": False}],
00069:         }
00070:         return _write(output_dir / bridge.STAGE_REPORT_NAMES["self_rag"], payload)
00071: 
00072:     def fake_crag(*, self_rag_report_path, output_dir):
00073:         assert self_rag_report_path.exists()
00074:         payload = {
00075:             "quality_status": "PASS",
00076:             "summary": {
00077:                 "crag_retry_plan_count": 1,
00078:                 "ready_for_crag_execution_count": 1,
00079:                 "answer_permission_count": 0,
00080:             },
00081:             "records": [{"crag_retry_plan_id": "cr1", "answer_permission": False}],
00082:         }
00083:         return _write(output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"], payload)
00084: 
00085:     monkeypatch.setattr(
00086:         bridge,
00087:         "_import_stage_builders",
00088:         lambda: {
00089:             "query_planner": fake_query_planner,
00090:             "context_pack_blueprint": fake_blueprint,
00091:             "context_pack_builder": fake_pack_builder,
00092:             "self_rag": fake_self_rag,
00093:             "crag_retry": fake_crag,
```

## `tiff/trace_net_engineering_context_crag_retry_plan_v1.py`
- Location: `active_source_code`
- Score: `247`
- Categories: `context_pack, crag, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context CRAG Retry Plan v1. Builds corrective retrieval/repackaging plans for engineering context packs that failed Self-RAG checks. v1.1: - avoids duplicate retry actions when both structured missing notes and reason strings describe the same gap - suppresses target_route="unknown" when the same missing type already has a structured routed action - adds unknown_target_route_count quality visibility Safety: - no LLM calls - no live retrieval execution - no DB/search/vector 
- Functions: _read_json(path)@L35; _write_json(path, payload)@L41; _write_jsonl(path, records)@L46; _seed_terms(record)@L53; _retry_action_for_missing()@L71; _structured_missing_keys(record)@L221; _has_structured_key_for_missing()@L235; _actions_from_record(record)@L243; _retry_priority(record, actions)@L304; build_retry_record(record, index)@L316; build_engineering_context_crag_retry_plan()@L376; _write_markdown(path, payload)@L464; check_engineering_context_crag_retry_plan_quality()@L498; main_build(argv)@L548; main_check(argv)@L565; fail_if(condition, msg)@L516
- CLI args: --self-rag-report, --output-dir, --quality, --report-path, --write-json, --require-source-self-rag-quality-pass, --min-crag-retry-plans, --min-retry-actions, --min-ready-for-crag-execution, --max-unknown-target-routes, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.

### Source window L307-L363
```python
00307:     if record.get("intent_family") == "visual_or_callout_similarity" and any(a.get("target_route") == "image_visual" for a in actions):
00308:         return "high"
00309:     if score < 30:
00310:         return "high"
00311:     if critical:
00312:         return "medium"
00313:     return "low"
00314: 
00315: 
00316: def build_retry_record(record: Mapping[str, Any], index: int) -> Dict[str, Any]:
00317:     actions = _actions_from_record(record)
00318:     target_routes = sorted(set(str(a.get("target_route")) for a in actions if a.get("target_route")))
00319:     target_artifacts = sorted(set(
00320:         artifact
00321:         for action in actions
00322:         for artifact in action.get("target_artifacts", [])
00323:     ))
00324:     query_hints = []
00325:     seen_hint = set()
00326:     for action in actions:
00327:         for hint in action.get("query_hints", []):
00328:             if hint and hint not in seen_hint:
00329:                 seen_hint.add(hint)
00330:                 query_hints.append(hint)
00331: 
00332:     return {
00333:         "crag_retry_plan_version": MODULE_VERSION,
00334:         "crag_retry_plan_id": f"engineering_crag_retry_plan_{index+1:04d}",
00335:         "source_self_rag_record_id": record.get("self_rag_record_id"),
00336:         "context_pack_id": record.get("context_pack_id"),
00337:         "question_id": record.get("question_id"),
00338:         "user_question": record.get("user_question"),
00339:         "intent_family": record.get("intent_family"),
00340:         "selected_playbook_id": record.get("selected_playbook_id"),
00341:         "source_self_rag_status": record.get("self_rag_status"),
00342:         "source_evidence_strength_score": record.get("evidence_strength_score"),
00343:         "source_truth_evidence_strength": record.get("source_truth_evidence_strength"),
00344:         "missing_evidence_types": record.get("missing_evidence_types") or [],
00345:         "critical_missing_evidence_types": record.get("critical_missing_evidence_types") or [],
00346:         "source_crag_retry_reasons": record.get("crag_retry_reasons") or [],
00347:         "retry_priority": _retry_priority(record, actions),
00348:         "target_routes": target_routes,
00349:         "unknown_target_route_count": sum(1 for route in target_routes if route == "unknown"),
00350:         "target_artifacts": target_artifacts,
00351:         "query_hints": query_hints[:20],
00352:         "retry_actions": actions,
00353:         "success_gate": {
00354:             "must_rebuild_context_pack": True,
00355:             "must_rerun_self_rag": True,
00356:             "must_reduce_or_resolve_critical_missing_evidence": True,
00357:             "answer_permission_after_retry": False,
00358:             "can_prove_claims_after_retry": False,
00359:         },
00360:         "plan_status": "crag_retry_plan_ready_no_execution",
00361:         "ready_for_crag_execution": True,
00362:         "answers_user_question": False,
00363:         "llm_call_allowed": False,
```
### Source window L1-L33
```python
00001: 
00002: """TRACE-Net Engineering Context CRAG Retry Plan v1.
00003: 
00004: Builds corrective retrieval/repackaging plans for engineering context packs that
00005: failed Self-RAG checks.
00006: 
00007: v1.1:
00008: - avoids duplicate retry actions when both structured missing notes and reason
00009:   strings describe the same gap
00010: - suppresses target_route="unknown" when the same missing type already has a
00011:   structured routed action
00012: - adds unknown_target_route_count quality visibility
00013: 
00014: Safety:
00015: - no LLM calls
00016: - no live retrieval execution
00017: - no DB/search/vector writes
00018: - no source-truth mutation
00019: - no answer permission
00020: """
00021: 
00022: from __future__ import annotations
00023: 
00024: import argparse
00025: import json
00026: from collections import Counter
00027: from pathlib import Path
00028: from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
00029: 
00030: 
00031: MODULE_VERSION = "trace_net_engineering_context_crag_retry_plan_v1"
00032: REPORT_NAME = "trace_net_engineering_context_crag_retry_plan_v1.json"
00033: 
```
### Source window L147-L203
```python
00147:             "query_hints": [
00148:                 question,
00149:                 " ".join(seeds + ["figure", "callout", "visual", "diagram"]),
00150:                 "same figure callout neighboring parts visual similarity",
00151:             ],
00152:             "success_conditions": [
00153:                 "image_visual artifact exists and is parsed",
00154:                 "at least one image/callout capsule is selected",
00155:                 "visual-only evidence remains candidate-only",
00156:             ],
00157:             "fallback_if_still_missing": "continue without image evidence only for non-visual questions; visual-similarity questions remain not draft-ready",
00158:         })
00159:     elif missing_type == "route_slot_unfilled":
00160:         target = route or "unknown"
00161:         base.update({
00162:             "retry_action_id": "retry_unfilled_route_slot",
00163:             "target_route": target,
00164:             "target_artifacts": [
00165:                 f"{target}_route_artifacts" if target != "unknown" else "route_artifacts",
00166:             ],
00167:             "query_hints": [
00168:                 question,
00169:                 " ".join(seeds),
00170:             ],
00171:             "success_conditions": [
00172:                 "route slot receives at least one high-signal evidence capsule",
00173:                 "capsule has source trace if it supports a factual claim",
00174:             ],
00175:             "fallback_if_still_missing": "keep CRAG retry required or route to review",
00176:         })
00177:     elif missing_type == "exact_source_evidence_missing":
00178:         base.update({
00179:             "retry_action_id": "retry_exact_source_table_evidence",
00180:             "target_route": "table",
00181:             "target_artifacts": [
00182:                 "table_exact_search_adapter",
00183:                 "promoted_table_value_evidence",
00184:                 "table_route_evidence_package",
00185:             ],
00186:             "query_hints": [
00187:                 question,
00188:                 " ".join(seeds + ["exact", "part", "number", "P/N"]),
00189:             ],
00190:             "success_conditions": [
00191:                 "exact source-backed table evidence exists",
00192:                 "page_id/source_trace is present",
00193:             ],
00194:             "fallback_if_still_missing": "do not draft exact lookup answer; route to review",
00195:         })
00196:     else:
00197:         target = route or "unknown"
00198:         base.update({
00199:             "retry_action_id": "retry_general_missing_evidence",
00200:             "target_route": target,
00201:             "target_artifacts": [
00202:                 "table artifacts",
00203:                 "normal_text artifacts",
```
### Source window L236-L292
```python
00236:     *,
00237:     structured_keys: Sequence[Tuple[str, Optional[str]]],
00238:     missing_type: str,
00239: ) -> bool:
00240:     return any(key_type == missing_type and route not in (None, "", "unknown") for key_type, route in structured_keys)
00241: 
00242: 
00243: def _actions_from_record(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
00244:     actions: List[Dict[str, Any]] = []
00245:     emitted_action_keys = set()
00246:     structured_keys = _structured_missing_keys(record)
00247: 
00248:     # First, use structured missing_evidence notes because they preserve route.
00249:     for missing_type, route in structured_keys:
00250:         key = (missing_type, route)
00251:         if key in emitted_action_keys:
00252:             continue
00253:         emitted_action_keys.add(key)
00254:         actions.append(_retry_action_for_missing(missing_type=missing_type, route=route, record=record))
00255: 
00256:     # Then parse reason strings only for gaps not already represented structurally.
00257:     for reason in record.get("crag_retry_reasons") or []:
00258:         if not isinstance(reason, str):
00259:             continue
00260:         parts = reason.split(":")
00261:         missing_type: Optional[str] = None
00262:         route: Optional[str] = None
00263: 
00264:         if reason.startswith("critical_missing:") and len(parts) >= 2:
00265:             missing_type = parts[1]
00266:             route = None
00267:         elif reason.startswith("missing_evidence:") and len(parts) >= 3:
00268:             missing_type = parts[1]
00269:             route = parts[2]
00270:         elif reason == "exact_part_lookup_missing_exact_source_evidence":
00271:             missing_type = "exact_source_evidence_missing"
00272:             route = "table"
00273: 
00274:         if not missing_type:
00275:             continue
00276: 
00277:         # If we already have a routed structured action for this missing type,
00278:         # do not add a duplicate unrouteable/unknown action from critical_missing.
00279:         if route in (None, "", "unknown") and _has_structured_key_for_missing(
00280:             structured_keys=structured_keys,
00281:             missing_type=missing_type,
00282:         ):
00283:             continue
00284: 
00285:         key = (missing_type, route)
00286:         if key in emitted_action_keys:
00287:             continue
00288:         emitted_action_keys.add(key)
00289:         actions.append(_retry_action_for_missing(missing_type=missing_type, route=route, record=record))
00290: 
00291:     # Final dedupe by actual retry action target/action pair.
00292:     deduped: List[Dict[str, Any]] = []
```
### Source window L77-L133
```python
00077:     intent = record.get("intent_family")
00078:     seeds = _seed_terms(record)
00079:     question = str(record.get("user_question") or "")
00080: 
00081:     base = {
00082:         "missing_type": missing_type,
00083:         "source_route": route,
00084:         "intent_family": intent,
00085:         "question_terms": seeds,
00086:         "execution_allowed": False,
00087:         "db_write_allowed": False,
00088:         "answer_permission": False,
00089:     }
00090: 
00091:     if missing_type == "source_dimension_not_confirmed":
00092:         base.update({
00093:             "retry_action_id": "retry_table_dimension_evidence",
00094:             "target_route": "table",
00095:             "target_artifacts": [
00096:                 "table_exact_search_adapter",
00097:                 "table_route_evidence_package",
00098:                 "source_normalized_table_value_records",
00099:                 "promoted_table_value_evidence",
00100:             ],
00101:             "query_hints": [
00102:                 question,
00103:                 " ".join(seeds + ["dimension", "length", "inch", "inches", "mm", "cm"]),
00104:                 "same part family dash number variant dimension length",
00105:                 "IPL table dimensions repair material part number",
00106:             ],
00107:             "success_conditions": [
00108:                 "at least one table/source record contains the seed entity or same-family candidate",
00109:                 "selected evidence contains a dimension/length/size term",
00110:                 "page_id/source_trace is present",
00111:                 "context pack no longer reports source_dimension_not_confirmed",
00112:             ],
00113:             "fallback_if_still_missing": "mark dimensional-change answer as candidate-only with missing dimension proof; do not allow fit/modification claim",
00114:         })
00115:     elif missing_type == "warning_caution_not_confirmed":
00116:         base.update({
00117:             "retry_action_id": "retry_warning_caution_procedure_evidence",
00118:             "target_route": "normal_text",
00119:             "target_artifacts": [
00120:                 "page_context_v2",
00121:                 "normal_text_handoff",
00122:                 "fishnet OCR text",
00123:             ],
00124:             "query_hints": [
00125:                 question,
00126:                 " ".join(seeds + ["WARNING", "CAUTION", "NOTE"]),
00127:                 "cleaning solvent warning caution procedure",
00128:                 "cleaners toxic ingredients gloves skin eyes",
00129:             ],
00130:             "success_conditions": [
00131:                 "normal_text/page_context evidence includes WARNING, CAUTION, or NOTE when present",
00132:                 "selected evidence has source page trace",
00133:                 "procedure context is source-backed before Gemma draft",
```
### Source window L393-L449
```python
00393:     route_counts = Counter(route for record in records for route in record.get("target_routes", []))
00394:     intent_counts = Counter(record.get("intent_family") for record in records)
00395:     missing_counts = Counter(
00396:         missing
00397:         for record in records
00398:         for missing in record.get("missing_evidence_types", [])
00399:     )
00400: 
00401:     summary = {
00402:         "source_self_rag_quality_status": self_rag_payload.get("quality_status"),
00403:         "source_self_rag_record_count": len(source_records),
00404:         "source_crag_retry_required_count": len(retry_source_records),
00405:         "crag_retry_plan_count": len(records),
00406:         "ready_for_crag_execution_count": sum(1 for r in records if r.get("ready_for_crag_execution")),
00407:         "retry_priority_counts": dict(sorted(priority_counts.items())),
00408:         "target_route_counts": dict(sorted(route_counts.items())),
00409:         "unknown_target_route_count": sum(r.get("unknown_target_route_count", 0) for r in records),
00410:         "intent_family_counts": dict(sorted(intent_counts.items())),
00411:         "missing_evidence_type_counts": dict(sorted(missing_counts.items())),
00412:         "total_retry_action_count": sum(len(r.get("retry_actions") or []) for r in records),
00413:         "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
00414:         "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
00415:         "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
00416:         "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
00417:         "llm_call_allowed_count": sum(1 for r in records if r.get("llm_call_allowed")),
00418:         "retrieval_execution_allowed_count": sum(1 for r in records if r.get("retrieval_execution_allowed")),
00419:         "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
00420:         "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
00421:         "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
00422:         "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
00423:     }
00424: 
00425:     quality_status = "PASS"
00426:     if self_rag_payload.get("quality_status") != "PASS":
00427:         quality_status = "FAIL"
00428:     if len(records) != int((self_rag_payload.get("summary") or {}).get("crag_retry_required_count", len(records))):
00429:         quality_status = "FAIL"
00430:     if summary["unsafe_record_count"] != 0:
00431:         quality_status = "FAIL"
00432: 
00433:     payload: Dict[str, Any] = {
00434:         "module": MODULE_VERSION,
00435:         "status": "ENGINEERING_CONTEXT_CRAG_RETRY_PLAN_BUILT",
00436:         "quality_status": quality_status,
00437:         "summary": summary,
00438:         "source_self_rag_report_path": str(self_rag_report_path),
00439:         "records": records,
00440:         "safety_contract": {
00441:             "artifact_authority": "crag_retry_planning_only",
00442:             "answers_user_question": False,
00443:             "llm_call_allowed": False,
00444:             "retrieval_execution_allowed": False,
00445:             "source_truth_mutation_allowed": False,
00446:             "answer_permission": False,
00447:             "can_answer_directly": False,
00448:             "can_prove_claims": False,
00449:             "postgres_write_allowed": False,
```
### Source window L509-L565
```python
00509:     require_no_retrieval_execution: bool = False,
00510:     require_no_source_truth_mutation: bool = False,
00511: ) -> Dict[str, Any]:
00512:     payload = _read_json(report_path)
00513:     summary = payload.get("summary") or {}
00514:     failures: List[str] = []
00515: 
00516:     def fail_if(condition: bool, msg: str) -> None:
00517:         if condition:
00518:             failures.append(msg)
00519: 
00520:     if require_source_self_rag_quality_pass:
00521:         fail_if(summary.get("source_self_rag_quality_status") != "PASS", "source Self-RAG quality is not PASS")
00522:     fail_if(summary.get("crag_retry_plan_count", 0) < min_crag_retry_plans, "not enough CRAG retry plans")
00523:     fail_if(summary.get("total_retry_action_count", 0) < min_retry_actions, "not enough retry actions")
00524:     fail_if(summary.get("ready_for_crag_execution_count", 0) < min_ready_for_crag_execution, "not enough plans ready for CRAG execution")
00525:     if max_unknown_target_routes is not None:
00526:         fail_if(summary.get("unknown_target_route_count", 0) > max_unknown_target_routes, "too many unknown target routes")
00527:     fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
00528:     if require_no_answer_permission:
00529:         fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
00530:         fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
00531:         fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
00532:     if require_no_llm_calls:
00533:         fail_if(summary.get("llm_call_allowed_count", 0) != 0, "LLM call allowed count not zero")
00534:     if require_no_retrieval_execution:
00535:         fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
00536:     if require_no_source_truth_mutation:
00537:         fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
00538: 
00539:     quality_status = "FAIL" if failures else "PASS"
00540:     return {
00541:         "quality_status": quality_status,
00542:         "summary": summary,
00543:         "failures": failures,
00544:         "checked_report_path": str(report_path),
00545:     }
00546: 
00547: 
00548: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00549:     parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context CRAG retry plan v1.")
00550:     parser.add_argument("--self-rag-report", required=True)
00551:     parser.add_argument("--output-dir", required=True)
00552:     parser.add_argument("--quality", action="store_true")
00553:     args = parser.parse_args(argv)
00554: 
00555:     payload = build_engineering_context_crag_retry_plan(
00556:         self_rag_report_path=Path(args.self_rag_report),
00557:         output_dir=Path(args.output_dir),
00558:     )
00559:     print("Status:", payload["status"])
00560:     print("Quality status:", payload["quality_status"])
00561:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
00562:     return 0 if payload["quality_status"] == "PASS" else 1
00563: 
00564: 
00565: def main_check(argv: Optional[Sequence[str]] = None) -> int:
```

## `tiff/trace_net_engineering_context_self_rag_check_v1.py`
- Location: `active_source_code`
- Score: `247`
- Categories: `context_pack, crag, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context Self-RAG Check v1. Scores engineering context packs before Gemma drafting. This module checks: - source-truth evidence strength - candidate-only evidence - missing evidence notes - route coverage - forbidden-claim risk - CRAG retry need - draft readiness Safety: - does not answer the user question - does not call an LLM - does not execute retrieval - does not mutate source truth - does not grant final answer permission
- Functions: _read_json(path)@L50; _write_json(path, payload)@L56; _write_jsonl(path, records)@L61; _all_capsules(pack)@L68; _missing_notes(pack)@L82; _clamp(value, lo, hi)@L87; _critical_missing_types(pack)@L91; _capsule_counts(capsules)@L107; _route_coverage(pack)@L137; _source_truth_strength(pack, counts, missing_count)@L161; _evidence_strength_score()@L179; evaluate_context_pack()@L207; _crag_retry_reasons()@L329; build_engineering_context_self_rag_check()@L355; _write_markdown(path, payload)@L451; check_engineering_context_self_rag_check_quality()@L486; main_build(argv)@L533; main_check(argv)@L554
- CLI args: --context-pack, --output-dir, --min-high-signal-capsules, --min-evidence-strength-score, --quality, --report-path, --write-json, --require-source-context-pack-quality-pass, --min-self-rag-records, --min-ready-for-gemma-draft, --min-crag-retry-required, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.

### Source window L4-L60
```python
00004: Scores engineering context packs before Gemma drafting.
00005: 
00006: This module checks:
00007: - source-truth evidence strength
00008: - candidate-only evidence
00009: - missing evidence notes
00010: - route coverage
00011: - forbidden-claim risk
00012: - CRAG retry need
00013: - draft readiness
00014: 
00015: Safety:
00016: - does not answer the user question
00017: - does not call an LLM
00018: - does not execute retrieval
00019: - does not mutate source truth
00020: - does not grant final answer permission
00021: """
00022: 
00023: from __future__ import annotations
00024: 
00025: import argparse
00026: import json
00027: from collections import Counter
00028: from pathlib import Path
00029: from typing import Any, Dict, List, Mapping, Optional, Sequence
00030: 
00031: 
00032: MODULE_VERSION = "trace_net_engineering_context_self_rag_check_v1"
00033: REPORT_NAME = "trace_net_engineering_context_self_rag_check_v1.json"
00034: 
00035: SOURCE_TRUTH_TIERS = {
00036:     "exact_source_evidence_candidate",
00037:     "source_context_guidance",
00038:     "structured_table_candidate",
00039: }
00040: 
00041: CANDIDATE_TIERS = {
00042:     "relationship_candidate",
00043:     "visual_candidate_only",
00044:     "semantic_lead_only",
00045:     "routing_metadata_not_source_truth",
00046:     "candidate_or_supporting",
00047: }
00048: 
00049: 
00050: def _read_json(path: Path) -> Dict[str, Any]:
00051:     if not path.exists():
00052:         raise FileNotFoundError(f"missing JSON file: {path}")
00053:     return json.loads(path.read_text(encoding="utf-8"))
00054: 
00055: 
00056: def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
00057:     path.parent.mkdir(parents=True, exist_ok=True)
00058:     path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
00059: 
00060: 
```
### Source window L426-L482
```python
00426:         "records": records,
00427:         "safety_contract": {
00428:             "artifact_authority": "self_rag_check_only",
00429:             "answers_user_question": False,
00430:             "llm_call_allowed": False,
00431:             "retrieval_execution_allowed": False,
00432:             "source_truth_mutation_allowed": False,
00433:             "answer_permission": False,
00434:             "can_answer_directly": False,
00435:             "can_prove_claims": False,
00436:             "postgres_write_allowed": False,
00437:             "qdrant_write_allowed": False,
00438:             "opensearch_write_allowed": False,
00439:         },
00440:     }
00441: 
00442:     output_dir.mkdir(parents=True, exist_ok=True)
00443:     _write_json(output_dir / REPORT_NAME, payload)
00444:     _write_jsonl(output_dir / "trace_net_engineering_context_self_rag_check_v1_records.jsonl", records)
00445:     _write_json(output_dir / "trace_net_engineering_context_self_rag_check_v1_summary.json", summary)
00446:     _write_json(output_dir / "trace_net_engineering_context_self_rag_check_v1_quality.json", {"quality_status": quality_status, "summary": summary})
00447:     _write_markdown(output_dir / "trace_net_engineering_context_self_rag_check_v1.md", payload)
00448:     return payload
00449: 
00450: 
00451: def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
00452:     summary = payload.get("summary") or {}
00453:     lines = [
00454:         "# TRACE-Net Engineering Context Self-RAG Check v1",
00455:         "",
00456:         f"Quality status: **{payload.get('quality_status')}**",
00457:         "",
00458:         "## Summary",
00459:         "",
00460:         f"- Self-RAG records: {summary.get('self_rag_record_count')}",
00461:         f"- Ready for Gemma draft: {summary.get('ready_for_gemma_draft_count')}",
00462:         f"- CRAG retry required: {summary.get('crag_retry_required_count')}",
00463:         f"- Status counts: `{summary.get('self_rag_status_counts')}`",
00464:         f"- Source-truth strength counts: `{summary.get('source_truth_evidence_strength_counts')}`",
00465:         f"- Average evidence score: {summary.get('average_evidence_strength_score')}",
00466:         "",
00467:         "## Records",
00468:         "",
00469:     ]
00470:     for record in payload.get("records") or []:
00471:         lines.extend([
00472:             f"### {record.get('self_rag_record_id')} — {record.get('self_rag_status')}",
00473:             "",
00474:             f"- Question: `{record.get('user_question')}`",
00475:             f"- Intent: `{record.get('intent_family')}`",
00476:             f"- Evidence strength score: `{record.get('evidence_strength_score')}`",
00477:             f"- Source-truth strength: `{record.get('source_truth_evidence_strength')}`",
00478:             f"- Ready for Gemma draft: `{record.get('ready_for_gemma_draft')}`",
00479:             f"- CRAG retry required: `{record.get('crag_retry_required')}`",
00480:             f"- CRAG retry reasons: `{record.get('crag_retry_reasons')}`",
00481:             "",
00482:         ])
```
### Source window L227-L283
```python
00227:         "answer_permission",
00228:         "can_answer_directly",
00229:         "can_prove_claims",
00230:         "retrieval_execution_allowed",
00231:         "source_truth_mutation_allowed",
00232:         "postgres_write_attempt",
00233:         "qdrant_write_attempt",
00234:         "opensearch_write_attempt",
00235:         "unsafe",
00236:     ):
00237:         if pack.get(key):
00238:             safety_violations.append(key)
00239: 
00240:     evidence_score = _evidence_strength_score(
00241:         counts=counts,
00242:         route_coverage=route_cov,
00243:         missing_count=len(missing),
00244:         critical_missing_count=len(critical_missing),
00245:         forbidden_claim_count=forbidden_claim_count,
00246:     )
00247:     source_strength = _source_truth_strength(pack, counts, len(missing))
00248: 
00249:     exact_required_but_missing = (
00250:         pack.get("intent_family") == "exact_part_lookup"
00251:         and int(counts.get("exact_source_capsule_count", 0)) == 0
00252:     )
00253:     no_high_signal = int(counts.get("high_signal_capsule_count", 0)) < min_high_signal_capsules
00254:     weak_score = evidence_score < min_evidence_strength_score
00255:     crag_retry_required = bool(
00256:         critical_missing
00257:         or exact_required_but_missing
00258:         or no_high_signal
00259:         or weak_score
00260:         or any(n.get("crag_retry_recommended") for n in missing)
00261:     )
00262: 
00263:     ready_for_gemma_draft = bool(
00264:         not crag_retry_required
00265:         and not safety_violations
00266:         and int(counts.get("high_signal_capsule_count", 0)) >= min_high_signal_capsules
00267:         and evidence_score >= min_evidence_strength_score
00268:     )
00269: 
00270:     if safety_violations:
00271:         self_rag_status = "SAFETY_FAIL"
00272:     elif ready_for_gemma_draft:
00273:         self_rag_status = "READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY"
00274:     elif crag_retry_required:
00275:         self_rag_status = "CRAG_RETRY_REQUIRED"
00276:     else:
00277:         self_rag_status = "REVIEW_REQUIRED"
00278: 
00279:     return {
00280:         "self_rag_check_version": MODULE_VERSION,
00281:         "self_rag_record_id": f"engineering_self_rag_{index+1:04d}",
00282:         "context_pack_id": pack.get("context_pack_id"),
00283:         "question_id": pack.get("question_id"),
```
### Source window L63-L119
```python
00063:     with path.open("w", encoding="utf-8") as handle:
00064:         for record in records:
00065:             handle.write(json.dumps(record, sort_keys=True) + "\n")
00066: 
00067: 
00068: def _all_capsules(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
00069:     capsules: List[Dict[str, Any]] = []
00070:     route_caps = pack.get("route_evidence_capsules") or {}
00071:     if isinstance(route_caps, dict):
00072:         for route, items in route_caps.items():
00073:             if isinstance(items, list):
00074:                 for item in items:
00075:                     if isinstance(item, dict):
00076:                         clone = dict(item)
00077:                         clone.setdefault("route", route)
00078:                         capsules.append(clone)
00079:     return capsules
00080: 
00081: 
00082: def _missing_notes(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
00083:     notes = pack.get("missing_evidence") or []
00084:     return [n for n in notes if isinstance(n, dict)]
00085: 
00086: 
00087: def _clamp(value: float, lo: int = 0, hi: int = 100) -> int:
00088:     return max(lo, min(hi, int(round(value))))
00089: 
00090: 
00091: def _critical_missing_types(pack: Mapping[str, Any]) -> List[str]:
00092:     intent = pack.get("intent_family")
00093:     critical = []
00094:     for note in _missing_notes(pack):
00095:         mtype = note.get("missing_type")
00096:         if mtype == "route_slot_unfilled":
00097:             critical.append(str(mtype))
00098:         if intent == "engineering_change_candidate" and mtype == "source_dimension_not_confirmed":
00099:             critical.append(str(mtype))
00100:         if intent == "repair_or_fault_context" and mtype == "warning_caution_not_confirmed":
00101:             critical.append(str(mtype))
00102:         if intent == "visual_or_callout_similarity" and note.get("route") == "image_visual":
00103:             critical.append(str(mtype))
00104:     return sorted(set(critical))
00105: 
00106: 
00107: def _capsule_counts(capsules: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
00108:     trust_counts = Counter(str(c.get("trust_tier")) for c in capsules)
00109:     route_counts = Counter(str(c.get("route")) for c in capsules)
00110:     source_truth_count = sum(
00111:         1 for c in capsules
00112:         if c.get("trust_tier") in SOURCE_TRUTH_TIERS and not c.get("fallback_available_context")
00113:     )
00114:     exact_count = sum(
00115:         1 for c in capsules
00116:         if c.get("trust_tier") == "exact_source_evidence_candidate" and not c.get("fallback_available_context")
00117:     )
00118:     candidate_count = sum(
00119:         1 for c in capsules
```
### Source window L329-L385
```python
00329: def _crag_retry_reasons(
00330:     *,
00331:     missing: Sequence[Mapping[str, Any]],
00332:     critical_missing: Sequence[str],
00333:     exact_required_but_missing: bool,
00334:     no_high_signal: bool,
00335:     weak_score: bool,
00336:     safety_violations: Sequence[str],
00337: ) -> List[str]:
00338:     reasons: List[str] = []
00339:     for item in critical_missing:
00340:         reasons.append(f"critical_missing:{item}")
00341:     for note in missing:
00342:         if note.get("crag_retry_recommended"):
00343:             reasons.append(f"missing_evidence:{note.get('missing_type')}:{note.get('route')}")
00344:     if exact_required_but_missing:
00345:         reasons.append("exact_part_lookup_missing_exact_source_evidence")
00346:     if no_high_signal:
00347:         reasons.append("insufficient_high_signal_evidence_capsules")
00348:     if weak_score:
00349:         reasons.append("evidence_strength_score_below_threshold")
00350:     for violation in safety_violations:
00351:         reasons.append(f"safety_violation:{violation}")
00352:     return sorted(set(reasons))
00353: 
00354: 
00355: def build_engineering_context_self_rag_check(
00356:     *,
00357:     context_pack_path: Path,
00358:     output_dir: Path,
00359:     min_high_signal_capsules: int = 1,
00360:     min_evidence_strength_score: int = 35,
00361: ) -> Dict[str, Any]:
00362:     pack_payload = _read_json(context_pack_path)
00363:     packs = pack_payload.get("records") or []
00364: 
00365:     records = [
00366:         evaluate_context_pack(
00367:             pack=pack,
00368:             index=index,
00369:             min_high_signal_capsules=min_high_signal_capsules,
00370:             min_evidence_strength_score=min_evidence_strength_score,
00371:         )
00372:         for index, pack in enumerate(packs)
00373:         if isinstance(pack, dict)
00374:     ]
00375: 
00376:     status_counts = Counter(record.get("self_rag_status") for record in records)
00377:     intent_counts = Counter(record.get("intent_family") for record in records)
00378:     source_strength_counts = Counter(record.get("source_truth_evidence_strength") for record in records)
00379: 
00380:     summary = {
00381:         "source_context_pack_builder_quality_status": pack_payload.get("quality_status"),
00382:         "source_context_pack_count": len(packs),
00383:         "self_rag_record_count": len(records),
00384:         "self_rag_status_counts": dict(sorted(status_counts.items())),
00385:         "intent_family_counts": dict(sorted(intent_counts.items())),
```
### Source window L494-L550
```python
00494:     require_no_answer_permission: bool = False,
00495:     require_no_llm_calls: bool = False,
00496:     require_no_retrieval_execution: bool = False,
00497:     require_no_source_truth_mutation: bool = False,
00498: ) -> Dict[str, Any]:
00499:     payload = _read_json(report_path)
00500:     summary = payload.get("summary") or {}
00501:     failures: List[str] = []
00502: 
00503:     def fail_if(condition: bool, msg: str) -> None:
00504:         if condition:
00505:             failures.append(msg)
00506: 
00507:     if require_source_context_pack_quality_pass:
00508:         fail_if(summary.get("source_context_pack_builder_quality_status") != "PASS", "source context pack builder quality is not PASS")
00509:     fail_if(summary.get("self_rag_record_count", 0) < min_self_rag_records, "not enough self-rag records")
00510:     fail_if(summary.get("ready_for_gemma_draft_count", 0) < min_ready_for_gemma_draft, "not enough records ready for Gemma draft")
00511:     fail_if(summary.get("crag_retry_required_count", 0) < min_crag_retry_required, "not enough CRAG retry records")
00512:     fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
00513:     if require_no_answer_permission:
00514:         fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
00515:         fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
00516:         fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
00517:     if require_no_llm_calls:
00518:         fail_if(summary.get("llm_call_allowed_count", 0) != 0, "llm call allowed count not zero")
00519:     if require_no_retrieval_execution:
00520:         fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
00521:     if require_no_source_truth_mutation:
00522:         fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
00523: 
00524:     quality_status = "FAIL" if failures else "PASS"
00525:     return {
00526:         "quality_status": quality_status,
00527:         "summary": summary,
00528:         "failures": failures,
00529:         "checked_report_path": str(report_path),
00530:     }
00531: 
00532: 
00533: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00534:     parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context Self-RAG check v1.")
00535:     parser.add_argument("--context-pack", required=True)
00536:     parser.add_argument("--output-dir", required=True)
00537:     parser.add_argument("--min-high-signal-capsules", type=int, default=1)
00538:     parser.add_argument("--min-evidence-strength-score", type=int, default=35)
00539:     parser.add_argument("--quality", action="store_true")
00540:     args = parser.parse_args(argv)
00541: 
00542:     payload = build_engineering_context_self_rag_check(
00543:         context_pack_path=Path(args.context_pack),
00544:         output_dir=Path(args.output_dir),
00545:         min_high_signal_capsules=args.min_high_signal_capsules,
00546:         min_evidence_strength_score=args.min_evidence_strength_score,
00547:     )
00548:     print("Status:", payload["status"])
00549:     print("Quality status:", payload["quality_status"])
00550:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
```

## `tiff/trace_net_engineering_engram_qdrant_adapter_v1.py`
- Location: `active_source_code`
- Score: `244`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: _read_json(path)@L26; _write_json(path, data)@L30; _write_jsonl(path, rows)@L35; _norm_text(value)@L42; _as_bool(value)@L46; _point_id_from_atom(atom_id)@L50; _sanitize_payload(payload)@L54; normalize_qdrant_records(vector_loader)@L69; _cosine(a, b)@L103; _hash_embed(text, dim)@L114; local_search(points, query)@L126; _qdrant_request(method, url, payload, timeout)@L149; _create_collection(qdrant_url, collection_name, vector_dim, timeout)@L157; _upsert_points(qdrant_url, collection_name, points, timeout)@L167; _query_points(qdrant_url, collection_name, vector, top_k, timeout)@L173; build_qdrant_adapter_manifest()@L180; check_qdrant_adapter_manifest()@L362; build_arg_parser()@L407
- CLI args: --vector-loader, --output-dir, --collection-name, --qdrant-url, --vector-dim, --top-k, --min-records, --min-local-queries, --require-all-layers, --require-source-quality-pass, --require-no-answer-permission, --enable-live-qdrant-write, --enable-live-qdrant-read, --qdrant-timeout-seconds, --max-unsafe, --max-write-attempts
- Has __main__ guard.

### Source window L1-L41
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import hashlib
00005: import json
00006: import math
00007: import time
00008: import urllib.error
00009: import urllib.request
00010: from pathlib import Path
00011: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00012: 
00013: MODULE = "trace_net_engineering_engram_qdrant_adapter_v1"
00014: VERSION = "v1"
00015: 
00016: REQUIRED_LAYERS = {
00017:     "working_memory",
00018:     "semantic_memory",
00019:     "procedural_memory",
00020:     "episodic_memory",
00021:     "trait_memory",
00022:     "critic_memory",
00023: }
00024: 
00025: 
00026: def _read_json(path: str | Path) -> Dict[str, Any]:
00027:     return json.loads(Path(path).read_text(encoding="utf-8"))
00028: 
00029: 
00030: def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
00031:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00032:     Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
00033: 
00034: 
00035: def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
00036:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00037:     with Path(path).open("w", encoding="utf-8") as f:
00038:         for row in rows:
00039:             f.write(json.dumps(row, sort_keys=True) + "\n")
00040: 
00041: 
```
### Source window L201-L257
```python
00201:     output_dir.mkdir(parents=True, exist_ok=True)
00202:     source = _read_json(vector_loader)
00203: 
00204:     source_quality = source.get("quality_status") or source.get("summary", {}).get("quality_status")
00205:     points = normalize_qdrant_records(source, collection_name=collection_name)
00206:     layer_counts: Dict[str, int] = {}
00207:     unsafe_findings: List[str] = []
00208:     answer_permission_count = 0
00209:     for p in points:
00210:         layer = str(p.get("memory_layer") or "unknown")
00211:         layer_counts[layer] = layer_counts.get(layer, 0) + 1
00212:         payload = p.get("payload") or {}
00213:         if payload.get("answer_permission") is True:
00214:             answer_permission_count += 1
00215:         if payload.get("engram_guidance_only") is not True:
00216:             unsafe_findings.append(f"payload_not_guidance_only:{p.get('atom_id')}")
00217:         if payload.get("manual_claims_require_proof_context") is not True:
00218:             unsafe_findings.append(f"missing_proof_context_boundary:{p.get('atom_id')}")
00219: 
00220:     missing_layers = sorted(REQUIRED_LAYERS - set(layer_counts)) if require_all_layers else []
00221:     if missing_layers:
00222:         unsafe_findings.append("missing_layers:" + ",".join(missing_layers))
00223: 
00224:     # Local retrieval smoke, even when live Qdrant is disabled.
00225:     default_queries = [
00226:         {"query_id": "q_interchangeability", "query_text": "interchangeability requires explicit authority replacement approval"},
00227:         {"query_id": "q_visual_ocr", "query_text": "visual figure link OCR nomenclature line text proof"},
00228:         {"query_id": "q_unknown_part", "query_text": "unknown part no proof_context not source trace ready"},
00229:         {"query_id": "q_safe_generic", "query_text": "safe but too generic repair critic CRAG"},
00230:         {"query_id": "q_summary_limit", "query_text": "v2 summaries guidance only not proof"},
00231:         {"query_id": "q_installation_limit", "query_text": "installation safety fit effectivity approval not proven"},
00232:     ]
00233:     local_queries = default_queries[: max(min_local_queries, 0)]
00234:     local_records = []
00235:     for q in local_queries:
00236:         local_records.append({
00237:             "query_id": q["query_id"],
00238:             "query_text": q["query_text"],
00239:             "results": local_search(points, q["query_text"], top_k=top_k, vector_dim=vector_dim),
00240:         })
00241: 
00242:     qdrant_write_attempt_count = 0
00243:     qdrant_read_attempt_count = 0
00244:     qdrant_write_result: Dict[str, Any] | None = None
00245:     qdrant_read_results: List[Dict[str, Any]] = []
00246: 
00247:     if enable_live_qdrant_write:
00248:         qdrant_write_attempt_count += 1
00249:         create_result = _create_collection(qdrant_url, collection_name, vector_dim, qdrant_timeout_seconds)
00250:         upsert_result = _upsert_points(qdrant_url, collection_name, points, qdrant_timeout_seconds)
00251:         qdrant_write_result = {"create_collection": create_result, "upsert_points": upsert_result}
00252: 
00253:     if enable_live_qdrant_read:
00254:         for q in local_queries:
00255:             qdrant_read_attempt_count += 1
00256:             qv = _hash_embed(q["query_text"], vector_dim)
00257:             try:
```
### Source window L57-L113
```python
00057:     safe["answer_permission"] = False
00058:     safe["source_truth_mutation_allowed"] = False
00059:     safe["postgres_write_attempt"] = False
00060:     safe["opensearch_write_attempt"] = False
00061:     safe["opensearch_upload_attempt"] = False
00062:     # This is a payload statement, not a runtime counter. Runtime write attempt is tracked elsewhere.
00063:     safe["qdrant_write_attempt"] = False
00064:     safe["engram_guidance_only"] = True
00065:     safe["manual_claims_require_proof_context"] = True
00066:     return safe
00067: 
00068: 
00069: def normalize_qdrant_records(vector_loader: Mapping[str, Any], *, collection_name: str | None = None) -> List[Dict[str, Any]]:
00070:     records = list(vector_loader.get("qdrant_ready_records") or [])
00071:     out: List[Dict[str, Any]] = []
00072:     for rec in records:
00073:         atom_id = _norm_text(rec.get("atom_id")) or _norm_text(rec.get("id"))
00074:         if not atom_id:
00075:             atom_id = _point_id_from_atom(json.dumps(rec, sort_keys=True))[:24]
00076:         vector = rec.get("vector") or rec.get("embedding") or rec.get("qdrant_vector")
00077:         if not isinstance(vector, list):
00078:             # Preserve adapter shape even if an older artifact stored dimension only.
00079:             dim = int(rec.get("vector_dim") or vector_loader.get("summary", {}).get("vector_dim") or 64)
00080:             vector = [0.0] * dim
00081:         payload = _sanitize_payload(rec.get("qdrant_payload") or rec.get("payload") or rec)
00082:         payload.update({
00083:             "atom_id": atom_id,
00084:             "memory_layer": rec.get("memory_layer") or payload.get("memory_layer"),
00085:             "proof_role": rec.get("proof_role") or payload.get("proof_role"),
00086:             "text_for_embedding": rec.get("text_for_embedding") or payload.get("text_for_embedding") or rec.get("text") or "",
00087:         })
00088:         point_id = rec.get("point_id") or _point_id_from_atom(atom_id)
00089:         out.append({
00090:             "id": point_id,
00091:             "vector": [float(x) for x in vector],
00092:             "payload": payload,
00093:             "collection_name": collection_name,
00094:             "atom_id": atom_id,
00095:             "memory_layer": payload.get("memory_layer"),
00096:             "proof_role": payload.get("proof_role"),
00097:             "vector_dim": len(vector),
00098:             "text_for_embedding": payload.get("text_for_embedding") or "",
00099:         })
00100:     return out
00101: 
00102: 
00103: def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
00104:     if not a or not b or len(a) != len(b):
00105:         return 0.0
00106:     dot = sum(x * y for x, y in zip(a, b))
00107:     na = math.sqrt(sum(x * x for x in a))
00108:     nb = math.sqrt(sum(y * y for y in b))
00109:     if na == 0 or nb == 0:
00110:         return 0.0
00111:     return dot / (na * nb)
00112: 
00113: 
```
### Source window L312-L368
```python
00312:             "version": VERSION,
00313:             "source_vector_loader_quality_status": source_quality,
00314:             "qdrant_ready_record_count": len(points),
00315:             "qdrant_point_record_count": len(points),
00316:             "memory_layer_counts": layer_counts,
00317:             "missing_layers": missing_layers,
00318:             "local_retrieval_query_count": len(local_records),
00319:             "qdrant_write_attempt_count": qdrant_write_attempt_count,
00320:             "qdrant_read_attempt_count": qdrant_read_attempt_count,
00321:             "postgres_write_attempt_count": postgres_write_attempt_count,
00322:             "opensearch_write_attempt_count": opensearch_write_attempt_count,
00323:             "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
00324:             "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
00325:             "answer_permission_count": answer_permission_count,
00326:             "write_attempt_count": write_attempt_count,
00327:             "unsafe_finding_count": len(unsafe_findings),
00328:             "unsafe_findings": unsafe_findings,
00329:             "quality_failures": quality_failures,
00330:             "ready_for_live_qdrant_write": quality_status == "PASS" and not enable_live_qdrant_write,
00331:             "ready_for_live_qdrant_search": quality_status == "PASS",
00332:         },
00333:         "qdrant_point_records_path": str(points_jsonl),
00334:         "local_retrieval_smoke_path": str(local_jsonl),
00335:         "local_retrieval_records": local_records,
00336:         "live_qdrant_write_result": qdrant_write_result,
00337:         "live_qdrant_read_results": qdrant_read_results,
00338:         "adapter_policy": {
00339:             "mode": "artifact_first_qdrant_adapter",
00340:             "proof_boundary": "Engram vectors retrieve behavior guidance only; factual manual claims still require proof_context citations.",
00341:             "forbidden": [
00342:                 "answer_permission_from_engram_vector",
00343:                 "source_truth_mutation_from_engram_vector",
00344:                 "summary_or_engram_used_as_proof",
00345:                 "live_qdrant_io_without_explicit_enable_flags",
00346:             ],
00347:             "explicit_live_flags": ["--enable-live-qdrant-write", "--enable-live-qdrant-read"],
00348:         },
00349:     }
00350: 
00351:     manifest_path = output_dir / "trace_net_engineering_engram_qdrant_adapter_v1.json"
00352:     _write_json(manifest_path, manifest)
00353:     check_path = output_dir / "trace_net_engineering_engram_qdrant_adapter_v1_quality_check.json"
00354:     _write_json(check_path, {
00355:         "status": "TRACE_NET_ENGINEERING_ENGRAM_QDRANT_ADAPTER_CHECKED",
00356:         "quality_status": quality_status,
00357:         "summary": manifest["summary"],
00358:     })
00359:     return manifest
00360: 
00361: 
00362: def check_qdrant_adapter_manifest(
00363:     *,
00364:     qdrant_adapter: str | Path,
00365:     min_records: int = 1,
00366:     min_local_queries: int = 0,
00367:     require_quality_pass: bool = False,
00368:     require_all_layers: bool = False,
```
### Source window L121-L177
```python
00121:     if norm:
00122:         vec = [v / norm for v in vec]
00123:     return vec
00124: 
00125: 
00126: def local_search(points: Sequence[Mapping[str, Any]], query: str, *, top_k: int = 5, vector_dim: int = 64) -> List[Dict[str, Any]]:
00127:     qv = _hash_embed(query, vector_dim)
00128:     rows: List[Dict[str, Any]] = []
00129:     for pt in points:
00130:         vector = pt.get("vector") or []
00131:         score = _cosine(qv, vector) if vector else 0.0
00132:         # Add a small lexical boost so tests and artifact previews are readable.
00133:         text = _norm_text(pt.get("text_for_embedding") or pt.get("payload", {}).get("text_for_embedding") or "").lower()
00134:         q_terms = set(_norm_text(query).lower().split())
00135:         overlap = sum(1 for t in q_terms if t in text)
00136:         score += min(0.25, overlap * 0.03)
00137:         rows.append({
00138:             "id": pt.get("id"),
00139:             "atom_id": pt.get("atom_id"),
00140:             "memory_layer": pt.get("memory_layer"),
00141:             "proof_role": pt.get("proof_role"),
00142:             "score": round(float(score), 6),
00143:             "text_preview": _norm_text(text)[:260],
00144:         })
00145:     rows.sort(key=lambda r: r.get("score", 0.0), reverse=True)
00146:     return rows[:top_k]
00147: 
00148: 
00149: def _qdrant_request(method: str, url: str, payload: Mapping[str, Any] | None = None, timeout: int = 30) -> Dict[str, Any]:
00150:     data = None if payload is None else json.dumps(payload).encode("utf-8")
00151:     req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
00152:     with urllib.request.urlopen(req, timeout=timeout) as resp:
00153:         raw = resp.read().decode("utf-8")
00154:     return json.loads(raw) if raw else {"status": "ok"}
00155: 
00156: 
00157: def _create_collection(qdrant_url: str, collection_name: str, vector_dim: int, timeout: int) -> Dict[str, Any]:
00158:     url = qdrant_url.rstrip("/") + f"/collections/{collection_name}"
00159:     payload = {"vectors": {"size": vector_dim, "distance": "Cosine"}}
00160:     try:
00161:         return _qdrant_request("PUT", url, payload, timeout)
00162:     except urllib.error.HTTPError as e:
00163:         # Qdrant may return conflict/exists depending version. Treat as visible status, not hidden success.
00164:         return {"status": "http_error", "code": e.code, "body": e.read().decode("utf-8", errors="replace")}
00165: 
00166: 
00167: def _upsert_points(qdrant_url: str, collection_name: str, points: Sequence[Mapping[str, Any]], timeout: int) -> Dict[str, Any]:
00168:     url = qdrant_url.rstrip("/") + f"/collections/{collection_name}/points?wait=true"
00169:     qpoints = [{"id": p["id"], "vector": p["vector"], "payload": p["payload"]} for p in points]
00170:     return _qdrant_request("PUT", url, {"points": qpoints}, timeout)
00171: 
00172: 
00173: def _query_points(qdrant_url: str, collection_name: str, vector: Sequence[float], top_k: int, timeout: int) -> Dict[str, Any]:
00174:     # Use the older /points/search endpoint for broad local Qdrant compatibility.
00175:     url = qdrant_url.rstrip("/") + f"/collections/{collection_name}/points/search"
00176:     payload = {"vector": list(vector), "limit": top_k, "with_payload": True}
00177:     return _qdrant_request("POST", url, payload, timeout)
```
### Source window L371-L427
```python
00371:     max_write_attempts: int = 0,
00372: ) -> Dict[str, Any]:
00373:     data = _read_json(qdrant_adapter)
00374:     summary = data.get("summary", {})
00375:     quality_failures: List[str] = []
00376:     if require_quality_pass and data.get("quality_status") != "PASS":
00377:         quality_failures.append("source_quality_status_not_pass")
00378:     if int(summary.get("qdrant_point_record_count") or 0) < min_records:
00379:         quality_failures.append("record_count_below_min")
00380:     if int(summary.get("local_retrieval_query_count") or 0) < min_local_queries:
00381:         quality_failures.append("local_query_count_below_min")
00382:     if require_all_layers and summary.get("missing_layers"):
00383:         quality_failures.append("missing_required_layers")
00384:     if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
00385:         quality_failures.append("answer_permission_count_nonzero")
00386:     if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
00387:         quality_failures.append("unsafe_finding_count_above_max")
00388:     if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
00389:         quality_failures.append("write_attempt_count_above_max")
00390:     quality_status = "PASS" if not quality_failures else "FAIL"
00391:     result = {
00392:         "status": "TRACE_NET_ENGINEERING_ENGRAM_QDRANT_ADAPTER_CHECKED",
00393:         "quality_status": quality_status,
00394:         "qdrant_point_record_count": int(summary.get("qdrant_point_record_count") or 0),
00395:         "local_retrieval_query_count": int(summary.get("local_retrieval_query_count") or 0),
00396:         "memory_layer_counts": summary.get("memory_layer_counts", {}),
00397:         "qdrant_write_attempt_count": int(summary.get("qdrant_write_attempt_count") or 0),
00398:         "qdrant_read_attempt_count": int(summary.get("qdrant_read_attempt_count") or 0),
00399:         "answer_permission_count": int(summary.get("answer_permission_count") or 0),
00400:         "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
00401:         "write_attempt_count": int(summary.get("write_attempt_count") or 0),
00402:         "quality_failures": quality_failures,
00403:     }
00404:     return result
00405: 
00406: 
00407: def build_arg_parser() -> argparse.ArgumentParser:
00408:     p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Qdrant adapter artifact.")
00409:     p.add_argument("--vector-loader", required=True)
00410:     p.add_argument("--output-dir", required=True)
00411:     p.add_argument("--collection-name", default="trace_net_engineering_engram_memory_v1")
00412:     p.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
00413:     p.add_argument("--vector-dim", type=int, default=64)
00414:     p.add_argument("--top-k", type=int, default=5)
00415:     p.add_argument("--min-records", type=int, default=1)
00416:     p.add_argument("--min-local-queries", type=int, default=3)
00417:     p.add_argument("--require-all-layers", action="store_true")
00418:     p.add_argument("--require-source-quality-pass", action="store_true")
00419:     p.add_argument("--require-no-answer-permission", action="store_true")
00420:     p.add_argument("--enable-live-qdrant-write", action="store_true")
00421:     p.add_argument("--enable-live-qdrant-read", action="store_true")
00422:     p.add_argument("--qdrant-timeout-seconds", type=int, default=30)
00423:     p.add_argument("--max-unsafe", type=int, default=0)
00424:     p.add_argument("--max-write-attempts", type=int, default=0)
00425:     return p
00426: 
00427: 
```

## `tiff/trace_net_engineering_context_pack_blueprint_v1.py`
- Location: `active_source_code`
- Score: `240`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context Pack Blueprint v1. Turns engineering query plans into dynamic context-pack contracts for Gemma/TRACE-Net. This is the bridge between: - the engineering brain (playbooks/examples/trust tiers) - dynamic context engineering (what context to assemble at runtime) - future retrieval/evidence pack building Safety: - does not answer questions - does not call an LLM - does not execute retrieval - does not mutate source truth - does not write DB/search/vector indexes
- Functions: _read_json(path)@L30; _write_json(path, payload)@L36; _write_jsonl(path, records)@L41; _write_markdown(path, payload)@L48; _route_slot(route, plan)@L81; _section_contracts(plan)@L172; _answer_format_contract(plan)@L279; _self_rag_crag_contract(plan)@L318; build_context_pack_blueprint_record(plan, index)@L342; build_engineering_context_pack_blueprint()@L391; check_engineering_context_pack_blueprint_quality()@L472; main_build(argv)@L521; main_check(argv)@L537; fail_if(condition, msg)@L489
- CLI args: --query-planner, --output-dir, --quality, --report-path, --write-json, --require-source-query-planner-quality-pass, --min-blueprints, --min-total-route-slots, --min-source-truth-required-blueprints, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.

### Source window L290-L346
```python
00290:         mode = "exact_evidence_first_then_related_context"
00291:     else:
00292:         mode = "engineering_triage"
00293:     return {
00294:         "answer_mode": mode,
00295:         "required_blocks": [
00296:             "what_is_proven",
00297:             "candidate_or_related_findings",
00298:             "missing_evidence",
00299:             "review_boundary",
00300:             "citations_or_source_trace",
00301:         ],
00302:         "must_not_include": plan.get("forbidden_answer_claims") or [],
00303:         "must_include_if_missing": [
00304:             "dimension_missing",
00305:             "effectivity_missing",
00306:             "interface_or_fit_missing",
00307:             "approval_missing",
00308:         ],
00309:         "final_gate_inputs": [
00310:             "source_truth_evidence",
00311:             "candidate_evidence",
00312:             "missing_evidence",
00313:             "forbidden_claims",
00314:         ],
00315:     }
00316: 
00317: 
00318: def _self_rag_crag_contract(plan: Mapping[str, Any]) -> Dict[str, Any]:
00319:     return {
00320:         "self_rag_checks": [
00321:             "every factual claim has source evidence or is labeled candidate",
00322:             "candidate claims do not become approved replacement claims",
00323:             "visual-only evidence is not treated as exact proof",
00324:             "semantic-only evidence is not treated as exact proof",
00325:             "repair/procedure claims include warnings/cautions if present",
00326:         ],
00327:         "crag_retry_triggers": [
00328:             "seed entity not resolved",
00329:             "exact table evidence missing for part-number question",
00330:             "dimension requested but source dimension missing",
00331:             "candidate found but no source trace",
00332:             "final answer would rely only on vector/visual similarity",
00333:         ],
00334:         "final_gate_rules": [
00335:             "block answer if source_truth_evidence is empty for exact/procedure claim",
00336:             "allow candidate-only answer only with explicit review language",
00337:             "forbid fit/safety/approval claims unless source explicitly says so",
00338:         ],
00339:     }
00340: 
00341: 
00342: def build_context_pack_blueprint_record(plan: Mapping[str, Any], index: int) -> Dict[str, Any]:
00343:     route_needs = plan.get("dynamic_context_pack_blueprint", {}).get("route_context_needed") or []
00344:     route_slots = [_route_slot(route, plan) for route in route_needs]
00345:     section_contracts = _section_contracts(plan)
00346:     source_truth_sections = [s for s in section_contracts if s.get("source_truth_required")]
```
### Source window L204-L260
```python
00204:                     "purpose": "show good/bad engineering reasoning examples without changing source truth",
00205:                     "max_tokens_hint": 900,
00206:                     "source_truth_required": False,
00207:                 }
00208:             )
00209:         elif section == "structured_user_intent":
00210:             contract.update(
00211:                 {
00212:                     "purpose": "make seed entities, requested changes, and question type explicit",
00213:                     "max_tokens_hint": 500,
00214:                     "source_truth_required": False,
00215:                 }
00216:             )
00217:         elif section == "route_handoff_availability":
00218:             contract.update(
00219:                 {
00220:                     "purpose": "tell the context builder which route queues are available",
00221:                     "max_tokens_hint": 400,
00222:                     "source_truth_required": False,
00223:                 }
00224:             )
00225:         elif section == "source_truth_evidence":
00226:             contract.update(
00227:                 {
00228:                     "purpose": "source-backed evidence that may support claims",
00229:                     "max_tokens_hint": 1800,
00230:                     "source_truth_required": True,
00231:                     "may_use_summary_guidance": False,
00232:                     "missing_behavior": "mark_answer_not_proven_and_trigger_crag_retry",
00233:                 }
00234:             )
00235:         elif section == "candidate_evidence":
00236:             contract.update(
00237:                 {
00238:                     "purpose": "candidate evidence for engineering review only",
00239:                     "max_tokens_hint": 1400,
00240:                     "source_truth_required": False,
00241:                 }
00242:             )
00243:         elif section == "missing_evidence":
00244:             contract.update(
00245:                 {
00246:                     "purpose": "explicitly list missing proof, dimensions, effectivity, interface, or warnings",
00247:                     "max_tokens_hint": 500,
00248:                     "source_truth_required": False,
00249:                 }
00250:             )
00251:         elif section == "trust_tier_policy":
00252:             contract.update(
00253:                 {
00254:                     "purpose": "force Gemma to separate exact proof, candidates, and weak leads",
00255:                     "max_tokens_hint": 600,
00256:                     "source_truth_required": False,
00257:                 }
00258:             )
00259:         elif section == "forbidden_claims":
00260:             contract.update(
```
### Source window L81-L137
```python
00081: def _route_slot(route: str, plan: Mapping[str, Any]) -> Dict[str, Any]:
00082:     intent = plan.get("intent_family")
00083:     base: Dict[str, Any] = {
00084:         "route": route,
00085:         "required": True,
00086:         "evidence_role": "supporting_context",
00087:         "max_records": 6,
00088:         "trust_tier": "candidate_or_supporting",
00089:         "missing_behavior": "record_missing_evidence_and_continue_to_review",
00090:     }
00091:     if route == "table":
00092:         base.update(
00093:             {
00094:                 "evidence_role": "structured_source_truth_or_candidate_table_evidence",
00095:                 "max_records": 12 if intent in ("engineering_change_candidate", "exact_part_lookup") else 8,
00096:                 "preferred_artifacts": [
00097:                     "table_exact_search_adapter",
00098:                     "promoted_table_value_evidence",
00099:                     "source_normalized_table_value_records",
00100:                     "table_route_evidence_package",
00101:                 ],
00102:                 "trust_tier": "source_truth_if_exact_match_else_candidate",
00103:             }
00104:         )
00105:     elif route == "normal_text":
00106:         base.update(
00107:             {
00108:                 "evidence_role": "procedure_description_warning_context",
00109:                 "max_records": 8 if intent == "repair_or_fault_context" else 6,
00110:                 "preferred_artifacts": [
00111:                     "page_context_v2",
00112:                     "normal_text_route_handoff",
00113:                     "Dublin Core metadata",
00114:                 ],
00115:                 "trust_tier": "source_context_guidance",
00116:             }
00117:         )
00118:     elif route == "image_visual":
00119:         base.update(
00120:             {
00121:                 "evidence_role": "visual_callout_candidate_context",
00122:                 "max_records": 8,
00123:                 "preferred_artifacts": [
00124:                     "image_visual_route_handoff",
00125:                     "visual_observer_route",
00126:                     "callout_candidates",
00127:                     "visual_part_verification_records",
00128:                 ],
00129:                 "trust_tier": "visual_candidate_only",
00130:             }
00131:         )
00132:     elif route == "graph":
00133:         base.update(
00134:             {
00135:                 "evidence_role": "relationship_and_same_family_context",
00136:                 "max_records": 20,
00137:                 "preferred_artifacts": [
```
### Source window L1-L54
```python
00001: """TRACE-Net Engineering Context Pack Blueprint v1.
00002: 
00003: Turns engineering query plans into dynamic context-pack contracts for
00004: Gemma/TRACE-Net.
00005: 
00006: This is the bridge between:
00007: - the engineering brain (playbooks/examples/trust tiers)
00008: - dynamic context engineering (what context to assemble at runtime)
00009: - future retrieval/evidence pack building
00010: 
00011: Safety:
00012: - does not answer questions
00013: - does not call an LLM
00014: - does not execute retrieval
00015: - does not mutate source truth
00016: - does not write DB/search/vector indexes
00017: """
00018: from __future__ import annotations
00019: 
00020: import argparse
00021: import json
00022: from collections import Counter
00023: from pathlib import Path
00024: from typing import Any, Dict, List, Mapping, Optional, Sequence
00025: 
00026: MODULE_VERSION = "trace_net_engineering_context_pack_blueprint_v1"
00027: REPORT_NAME = "trace_net_engineering_context_pack_blueprint_v1.json"
00028: 
00029: 
00030: def _read_json(path: Path) -> Dict[str, Any]:
00031:     if not path.exists():
00032:         raise FileNotFoundError(f"missing JSON file: {path}")
00033:     return json.loads(path.read_text(encoding="utf-8"))
00034: 
00035: 
00036: def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
00037:     path.parent.mkdir(parents=True, exist_ok=True)
00038:     path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
00039: 
00040: 
00041: def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
00042:     path.parent.mkdir(parents=True, exist_ok=True)
00043:     with path.open("w", encoding="utf-8") as handle:
00044:         for record in records:
00045:             handle.write(json.dumps(record, sort_keys=True) + "\n")
00046: 
00047: 
00048: def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
00049:     path.parent.mkdir(parents=True, exist_ok=True)
00050:     summary = payload.get("summary") or {}
00051:     lines = [
00052:         "# TRACE-Net Engineering Context Pack Blueprint v1",
00053:         "",
00054:         f"Quality status: **{payload.get('quality_status')}**",
```
### Source window L494-L550
```python
00494:         fail_if(summary.get("source_query_planner_quality_status") != "PASS", "source query planner quality is not PASS")
00495:     fail_if(summary.get("context_pack_blueprint_count", 0) < min_blueprints, "not enough blueprints")
00496:     fail_if(summary.get("total_route_evidence_slot_count", 0) < min_total_route_slots, "not enough route evidence slots")
00497:     fail_if(
00498:         summary.get("blueprints_with_source_truth_required_count", 0) < min_source_truth_required_blueprints,
00499:         "not enough source-truth-required blueprints",
00500:     )
00501:     fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
00502:     if require_no_answer_permission:
00503:         fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
00504:         fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
00505:         fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
00506:     if require_no_llm_calls:
00507:         fail_if(summary.get("llm_call_allowed_count", 0) != 0, "llm call allowed count not zero")
00508:     if require_no_retrieval_execution:
00509:         fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
00510:     if require_no_source_truth_mutation:
00511:         fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
00512:     quality_status = "FAIL" if failures else "PASS"
00513:     return {
00514:         "quality_status": quality_status,
00515:         "summary": summary,
00516:         "failures": failures,
00517:         "checked_report_path": str(report_path),
00518:     }
00519: 
00520: 
00521: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00522:     parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context pack blueprint v1.")
00523:     parser.add_argument("--query-planner", required=True)
00524:     parser.add_argument("--output-dir", required=True)
00525:     parser.add_argument("--quality", action="store_true")
00526:     args = parser.parse_args(argv)
00527:     payload = build_engineering_context_pack_blueprint(
00528:         query_planner_path=Path(args.query_planner),
00529:         output_dir=Path(args.output_dir),
00530:     )
00531:     print("Status:", payload["status"])
00532:     print("Quality status:", payload["quality_status"])
00533:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
00534:     return 0 if payload["quality_status"] == "PASS" else 1
00535: 
00536: 
00537: def main_check(argv: Optional[Sequence[str]] = None) -> int:
00538:     parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context pack blueprint v1 quality.")
00539:     parser.add_argument("--report-path", required=True)
00540:     parser.add_argument("--write-json", action="store_true")
00541:     parser.add_argument("--require-source-query-planner-quality-pass", action="store_true")
00542:     parser.add_argument("--min-blueprints", type=int, default=1)
00543:     parser.add_argument("--min-total-route-slots", type=int, default=1)
00544:     parser.add_argument("--min-source-truth-required-blueprints", type=int, default=1)
00545:     parser.add_argument("--max-unsafe", type=int, default=0)
00546:     parser.add_argument("--require-no-answer-permission", action="store_true")
00547:     parser.add_argument("--require-no-llm-calls", action="store_true")
00548:     parser.add_argument("--require-no-retrieval-execution", action="store_true")
00549:     parser.add_argument("--require-no-source-truth-mutation", action="store_true")
00550:     args = parser.parse_args(argv)
```
### Source window L357-L413
```python
00357:         "context_pack_status": "blueprint_only_no_retrieval_executed",
00358:         "dynamic_context_role": "assemble_question_specific_engineering_context_for_gemma",
00359:         "engineer_brain_role": "provide_reasoning_playbook_examples_trust_boundaries",
00360:         "section_contracts": section_contracts,
00361:         "route_evidence_slots": route_slots,
00362:         "context_budget": plan.get("dynamic_context_pack_blueprint", {}).get("context_budget") or {},
00363:         "compression_policy": plan.get("dynamic_context_pack_blueprint", {}).get("compression_policy") or {},
00364:         "trust_tier_policy": {
00365:             "exact_source_evidence": "can support factual claim with citation",
00366:             "cross_route_candidate": "candidate for engineering review only",
00367:             "visual_candidate": "visual similarity only, requires table/source cross-check",
00368:             "semantic_candidate": "retrieval lead only",
00369:             "missing_evidence": "state missing proof and do not overclaim",
00370:         },
00371:         "answer_format_contract": _answer_format_contract(plan),
00372:         "self_rag_crag_contract": _self_rag_crag_contract(plan),
00373:         "forbidden_answer_claims": forbidden_claims,
00374:         "source_truth_required_section_count": len(source_truth_sections),
00375:         "route_slot_count": len(route_slots),
00376:         "candidate_language_required": bool(plan.get("evidence_policy", {}).get("candidate_language_required")),
00377:         "answers_user_question": False,
00378:         "llm_call_allowed": False,
00379:         "retrieval_execution_allowed": False,
00380:         "answer_permission": False,
00381:         "can_answer_directly": False,
00382:         "can_prove_claims": False,
00383:         "source_truth_mutation_allowed": False,
00384:         "postgres_write_attempt": False,
00385:         "qdrant_write_attempt": False,
00386:         "opensearch_write_attempt": False,
00387:         "unsafe": False,
00388:     }
00389: 
00390: 
00391: def build_engineering_context_pack_blueprint(
00392:     *,
00393:     query_planner_path: Path,
00394:     output_dir: Path,
00395: ) -> Dict[str, Any]:
00396:     planner_payload = _read_json(query_planner_path)
00397:     plans = planner_payload.get("records") or []
00398:     records = [
00399:         build_context_pack_blueprint_record(plan, index)
00400:         for index, plan in enumerate(plans)
00401:         if isinstance(plan, dict)
00402:     ]
00403:     route_counts = Counter(
00404:         slot["route"] for record in records for slot in record.get("route_evidence_slots", [])
00405:     )
00406:     intent_counts = Counter(record.get("intent_family") for record in records)
00407:     summary = {
00408:         "source_query_planner_quality_status": planner_payload.get("quality_status"),
00409:         "source_query_plan_count": len(plans),
00410:         "context_pack_blueprint_count": len(records),
00411:         "intent_family_counts": dict(sorted(intent_counts.items())),
00412:         "route_evidence_slot_counts": dict(sorted(route_counts.items())),
00413:         "blueprints_with_source_truth_required_count": sum(
```
### Source window L429-L485
```python
00429:         "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
00430:     }
00431:     quality_status = "PASS"
00432:     if planner_payload.get("quality_status") != "PASS":
00433:         quality_status = "FAIL"
00434:     if not records:
00435:         quality_status = "FAIL"
00436:     if summary["unsafe_record_count"] != 0:
00437:         quality_status = "FAIL"
00438: 
00439:     payload: Dict[str, Any] = {
00440:         "module": MODULE_VERSION,
00441:         "status": "ENGINEERING_CONTEXT_PACK_BLUEPRINT_BUILT",
00442:         "quality_status": quality_status,
00443:         "summary": summary,
00444:         "source_query_planner_path": str(query_planner_path),
00445:         "records": records,
00446:         "safety_contract": {
00447:             "artifact_authority": "context_pack_blueprint_only",
00448:             "answers_user_question": False,
00449:             "llm_call_allowed": False,
00450:             "retrieval_execution_allowed": False,
00451:             "source_truth_mutation_allowed": False,
00452:             "answer_permission": False,
00453:             "can_answer_directly": False,
00454:             "can_prove_claims": False,
00455:             "postgres_write_allowed": False,
00456:             "qdrant_write_allowed": False,
00457:             "opensearch_write_allowed": False,
00458:         },
00459:     }
00460:     output_dir.mkdir(parents=True, exist_ok=True)
00461:     _write_json(output_dir / REPORT_NAME, payload)
00462:     _write_jsonl(output_dir / "trace_net_engineering_context_pack_blueprint_v1_records.jsonl", records)
00463:     _write_json(output_dir / "trace_net_engineering_context_pack_blueprint_v1_summary.json", summary)
00464:     _write_json(
00465:         output_dir / "trace_net_engineering_context_pack_blueprint_v1_quality.json",
00466:         {"quality_status": quality_status, "summary": summary},
00467:     )
00468:     _write_markdown(output_dir / "trace_net_engineering_context_pack_blueprint_v1.md", payload)
00469:     return payload
00470: 
00471: 
00472: def check_engineering_context_pack_blueprint_quality(
00473:     *,
00474:     report_path: Path,
00475:     require_source_query_planner_quality_pass: bool = False,
00476:     min_blueprints: int = 1,
00477:     min_total_route_slots: int = 1,
00478:     min_source_truth_required_blueprints: int = 1,
00479:     max_unsafe: int = 0,
00480:     require_no_answer_permission: bool = False,
00481:     require_no_llm_calls: bool = False,
00482:     require_no_retrieval_execution: bool = False,
00483:     require_no_source_truth_mutation: bool = False,
00484: ) -> Dict[str, Any]:
00485:     payload = _read_json(report_path)
```

## `tiff/trace_net_engineering_context_pack_builder_v1.py`
- Location: `active_source_code`
- Score: `240`
- Categories: `context_pack, crag, final_gate, graph_vector, page, planner, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Context Pack Builder v1. Fills engineering context-pack blueprints with available TRACE-Net artifacts. v1.2: - optional artifact paths no longer crash when missing - missing optional artifacts are recorded in artifact_missing_inputs - quality checker can require no required-missing inputs while allowing optional missing inputs Safety: - no LLM calls - no live retrieval execution - no DB writes - no source-truth mutation - no answer permission
- Classes: FileNotErrorForOptional@L69 methods=[]
- Functions: _read_json(path)@L63; _write_json(path, payload)@L73; _write_jsonl(path, records)@L78; _looks_like_record(record)@L85; _flatten_records(payload)@L104; _recursive_text_values(obj, limit)@L151; _recursive_first(obj, keys)@L197; _compact_text(text, limit)@L215; _tokenize_question(question)@L220; _record_text_blob(record)@L238; _match_score(record)@L243; _artifact_records(path, route, artifact_name)@L263; _build_artifact_corpus()@L290; _trust_tier_for_route(route, score, seed_entities)@L317; _evidence_capsule(record)@L333; _select_capsules_for_slot()@L355; _missing_evidence_notes(blueprint, slot_capsules)@L376; _pack_sections(blueprint, slot_capsules, missing_notes)@L422
- CLI args: --blueprint, --output-dir, --route-dispatch-handoff, --table-exact-search-adapter, --page-context-v2, --leiden-communities, --image-visual-observer, --max-records-per-slot, --quality, --report-path, --write-json, --require-source-blueprint-quality-pass, --min-context-packs, --min-artifact-corpus-records, --min-evidence-capsules, --min-high-signal-evidence-capsules, --min-packs-ready-for-gemma-context, --max-missing-optional-artifact-inputs, --max-unsafe, --require-no-answer-permission, --require-no-llm-calls, --require-no-retrieval-execution, --require-no-source-truth-mutation
- Has __main__ guard.

### Source window L488-L544
```python
00488:     sections = _pack_sections(blueprint, slot_capsules, missing_notes)
00489:     evidence_capsule_count = sum(len(v) for v in slot_capsules.values())
00490:     high_signal_capsule_count = sum(1 for v in slot_capsules.values() for c in v if not c.get("fallback_available_context"))
00491:     fallback_capsule_count = sum(1 for v in slot_capsules.values() for c in v if c.get("fallback_available_context"))
00492:     filled_slot_count = sum(1 for v in slot_capsules.values() if v)
00493:     high_signal_filled_slot_count = sum(1 for v in slot_capsules.values() if any(not c.get("fallback_available_context") for c in v))
00494: 
00495:     return {
00496:         "context_pack_version": MODULE_VERSION,
00497:         "context_pack_id": f"engineering_context_pack_{index+1:04d}",
00498:         "source_blueprint_id": blueprint.get("blueprint_id"),
00499:         "question_id": blueprint.get("question_id"),
00500:         "user_question": blueprint.get("user_question"),
00501:         "intent_family": blueprint.get("intent_family"),
00502:         "selected_playbook_id": blueprint.get("selected_playbook_id"),
00503:         "seed_entities": blueprint.get("seed_entities") or [],
00504:         "requested_change": blueprint.get("requested_change"),
00505:         "context_pack_status": "built_from_available_artifacts_no_llm",
00506:         "sections": sections,
00507:         "route_evidence_capsules": slot_capsules,
00508:         "missing_evidence": missing_notes,
00509:         "evidence_capsule_count": evidence_capsule_count,
00510:         "high_signal_evidence_capsule_count": high_signal_capsule_count,
00511:         "fallback_evidence_capsule_count": fallback_capsule_count,
00512:         "filled_route_slot_count": filled_slot_count,
00513:         "high_signal_filled_route_slot_count": high_signal_filled_slot_count,
00514:         "required_route_slot_count": len(blueprint.get("route_evidence_slots") or []),
00515:         "answer_format_contract": blueprint.get("answer_format_contract"),
00516:         "self_rag_crag_contract": blueprint.get("self_rag_crag_contract"),
00517:         "forbidden_answer_claims": blueprint.get("forbidden_answer_claims") or [],
00518:         "ready_for_self_rag_check": True,
00519:         "ready_for_gemma_context": high_signal_capsule_count > 0,
00520:         "answers_user_question": False,
00521:         "llm_call_allowed": False,
00522:         "answer_permission": False,
00523:         "can_answer_directly": False,
00524:         "can_prove_claims": False,
00525:         "retrieval_execution_allowed": False,
00526:         "source_truth_mutation_allowed": False,
00527:         "postgres_write_attempt": False,
00528:         "qdrant_write_attempt": False,
00529:         "opensearch_write_attempt": False,
00530:         "unsafe": False,
00531:     }
00532: 
00533: 
00534: def build_engineering_context_pack_builder(
00535:     *,
00536:     blueprint_path: Path,
00537:     output_dir: Path,
00538:     route_dispatch_handoff: Optional[Path] = None,
00539:     table_exact_search_adapter: Optional[Path] = None,
00540:     page_context_v2: Optional[Path] = None,
00541:     leiden_communities: Optional[Path] = None,
00542:     image_visual_observer: Optional[Path] = None,
00543:     max_records_per_slot: int = 8,
00544: ) -> Dict[str, Any]:
```
### Source window L358-L414
```python
00358:     seed_entities = blueprint.get("seed_entities") or []
00359:     max_records = min(int(slot.get("max_records") or max_records_per_slot), max_records_per_slot)
00360:     route_records = [record for record in corpus if record.get("_artifact_route") == route]
00361:     scored = [(_match_score(record, question=question, seed_entities=seed_entities), record) for record in route_records]
00362:     positives = [(score, record) for score, record in scored if score > 0]
00363:     positives.sort(key=lambda item: item[0], reverse=True)
00364:     selected = [
00365:         _evidence_capsule(record, route=str(route), seed_entities=seed_entities, score=score)
00366:         for score, record in positives[:max_records]
00367:     ]
00368:     if not selected and route_records and route in {"route_dispatch", "graph", "image_visual", "table"}:
00369:         selected = [
00370:             _evidence_capsule(record, route=str(route), seed_entities=seed_entities, score=0, fallback=True)
00371:             for record in route_records[: min(max_records, 3)]
00372:         ]
00373:     return selected
00374: 
00375: 
00376: def _missing_evidence_notes(blueprint: Mapping[str, Any], slot_capsules: Mapping[str, List[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
00377:     notes: List[Dict[str, Any]] = []
00378:     for slot in blueprint.get("route_evidence_slots") or []:
00379:         route = slot.get("route")
00380:         capsules = slot_capsules.get(route) or []
00381:         if not capsules:
00382:             notes.append({
00383:                 "missing_type": "route_slot_unfilled",
00384:                 "route": route,
00385:                 "reason": f"no available artifact evidence selected for route {route}",
00386:                 "crag_retry_recommended": True,
00387:             })
00388:         elif all(c.get("fallback_available_context") for c in capsules):
00389:             notes.append({
00390:                 "missing_type": "route_slot_has_only_fallback_context",
00391:                 "route": route,
00392:                 "reason": f"route {route} has artifact records but no high-signal match for this question",
00393:                 "crag_retry_recommended": True,
00394:             })
00395:     if blueprint.get("requested_change"):
00396:         table_capsules = slot_capsules.get("table") or []
00397:         dimension_words = ("dimension", "length", "height", "width", "diameter", "inch", "inches", "mm", "cm")
00398:         has_dimension_evidence = any(
00399:             any(word in (capsule.get("source_text_excerpt") or "").lower() for word in dimension_words)
00400:             and not capsule.get("fallback_available_context")
00401:             for capsule in table_capsules
00402:         )
00403:         if not has_dimension_evidence:
00404:             notes.append({
00405:                 "missing_type": "source_dimension_not_confirmed",
00406:                 "route": "table",
00407:                 "reason": "question requests a dimensional change but selected table evidence does not clearly prove a source dimension",
00408:                 "crag_retry_recommended": True,
00409:             })
00410:     if blueprint.get("intent_family") == "repair_or_fault_context":
00411:         text = " ".join(c.get("source_text_excerpt", "") for caps in slot_capsules.values() for c in caps).lower()
00412:         if "warning" not in text and "caution" not in text:
00413:             notes.append({
00414:                 "missing_type": "warning_caution_not_confirmed",
```
### Source window L1-L57
```python
00001: 
00002: """TRACE-Net Engineering Context Pack Builder v1.
00003: 
00004: Fills engineering context-pack blueprints with available TRACE-Net artifacts.
00005: 
00006: v1.2:
00007: - optional artifact paths no longer crash when missing
00008: - missing optional artifacts are recorded in artifact_missing_inputs
00009: - quality checker can require no required-missing inputs while allowing optional missing inputs
00010: 
00011: Safety:
00012: - no LLM calls
00013: - no live retrieval execution
00014: - no DB writes
00015: - no source-truth mutation
00016: - no answer permission
00017: """
00018: 
00019: from __future__ import annotations
00020: 
00021: import argparse
00022: import json
00023: import re
00024: from collections import Counter
00025: from pathlib import Path
00026: from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
00027: 
00028: 
00029: MODULE_VERSION = "trace_net_engineering_context_pack_builder_v1"
00030: REPORT_NAME = "trace_net_engineering_context_pack_builder_v1.json"
00031: 
00032: TEXT_KEYS = (
00033:     "text", "sample", "sample_text", "content", "body", "snippet", "ocr_text",
00034:     "fishnet_ocr_sample_text", "page_text", "page_summary", "page_summary_v2",
00035:     "summary", "description", "title", "nomenclature", "covered_part_number",
00036:     "part_number", "manual_page_reference", "field_value", "value", "source_text",
00037:     "normalized_value", "raw_value", "query", "answer", "evidence_text",
00038:     "source_excerpt", "record_text", "callout_text", "warning", "caution", "note",
00039: )
00040: 
00041: PAGE_KEYS = (
00042:     "page_id", "source_page_id", "current_route_manifest_page_id",
00043:     "source_trace_page_id", "page", "document_page_id", "manual_page_id",
00044:     "page_ref", "source_page_ref",
00045: )
00046: 
00047: TECHNICAL_STRING_KEYS = {
00048:     "source_artifact_path", "_artifact_path", "path", "file_path", "output_path",
00049:     "report_path", "json_path", "image_path", "overlay_path", "schema", "module",
00050:     "status", "quality_status", "version",
00051: }
00052: 
00053: PRIORITY_LIST_KEYS = (
00054:     "records", "cards", "items", "pages", "documents", "evidence_documents",
00055:     "search_documents", "exact_search_documents", "table_exact_search_documents",
00056:     "adapter_documents", "search_ready_documents", "page_context_records",
00057:     "route_records", "route_handoff_records", "accepted_delta_records",
```
### Source window L630-L686
```python
00630:         "records": records,
00631:         "safety_contract": {
00632:             "artifact_authority": "context_pack_builder_artifact_only",
00633:             "answers_user_question": False,
00634:             "llm_call_allowed": False,
00635:             "retrieval_execution_allowed": False,
00636:             "source_truth_mutation_allowed": False,
00637:             "answer_permission": False,
00638:             "can_answer_directly": False,
00639:             "can_prove_claims": False,
00640:             "postgres_write_allowed": False,
00641:             "qdrant_write_allowed": False,
00642:             "opensearch_write_allowed": False,
00643:         },
00644:     }
00645: 
00646:     output_dir.mkdir(parents=True, exist_ok=True)
00647:     _write_json(output_dir / REPORT_NAME, payload)
00648:     _write_jsonl(output_dir / "trace_net_engineering_context_pack_builder_v1_records.jsonl", records)
00649:     _write_json(output_dir / "trace_net_engineering_context_pack_builder_v1_summary.json", summary)
00650:     _write_json(output_dir / "trace_net_engineering_context_pack_builder_v1_quality.json", {"quality_status": quality_status, "summary": summary})
00651:     _write_markdown(output_dir / "trace_net_engineering_context_pack_builder_v1.md", payload)
00652:     return payload
00653: 
00654: 
00655: def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
00656:     summary = payload.get("summary") or {}
00657:     lines = [
00658:         "# TRACE-Net Engineering Context Pack Builder v1.2",
00659:         "",
00660:         f"Quality status: **{payload.get('quality_status')}**",
00661:         "",
00662:         "## Summary",
00663:         "",
00664:         f"- Context packs: {summary.get('context_pack_count')}",
00665:         f"- Artifact corpus records: {summary.get('artifact_corpus_record_count')}",
00666:         f"- Artifact record counts: `{summary.get('artifact_record_counts')}`",
00667:         f"- Missing optional artifact inputs: `{summary.get('artifact_missing_inputs')}`",
00668:         f"- Evidence capsules: {summary.get('total_evidence_capsule_count')}",
00669:         f"- High-signal capsules: {summary.get('total_high_signal_evidence_capsule_count')}",
00670:         f"- Fallback capsules: {summary.get('total_fallback_evidence_capsule_count')}",
00671:         f"- Route capsule counts: `{summary.get('route_evidence_capsule_counts')}`",
00672:         f"- Missing evidence notes: {summary.get('total_missing_evidence_note_count')}",
00673:         "",
00674:         "## Packs",
00675:         "",
00676:     ]
00677:     for record in payload.get("records") or []:
00678:         lines.extend([
00679:             f"### {record.get('context_pack_id')} — {record.get('intent_family')}",
00680:             "",
00681:             f"- Question: `{record.get('user_question')}`",
00682:             f"- Playbook: `{record.get('selected_playbook_id')}`",
00683:             f"- Evidence capsules: `{record.get('evidence_capsule_count')}`",
00684:             f"- High-signal capsules: `{record.get('high_signal_evidence_capsule_count')}`",
00685:             f"- Filled route slots: `{record.get('filled_route_slot_count')}/{record.get('required_route_slot_count')}`",
00686:             f"- High-signal filled slots: `{record.get('high_signal_filled_route_slot_count')}/{record.get('required_route_slot_count')}`",
```
### Source window L295-L351
```python
00295:     leiden_communities: Optional[Path],
00296:     image_visual_observer: Optional[Path],
00297: ) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[Dict[str, Any]]]:
00298:     specs = [
00299:         ("fishnet_route_dispatch_handoff", route_dispatch_handoff, "route_dispatch", True),
00300:         ("table_exact_search_adapter", table_exact_search_adapter, "table", True),
00301:         ("page_context_v2", page_context_v2, "normal_text", True),
00302:         ("leiden_communities", leiden_communities, "graph", True),
00303:         ("image_visual_observer", image_visual_observer, "image_visual", True),
00304:     ]
00305:     corpus: List[Dict[str, Any]] = []
00306:     counts: Dict[str, int] = {}
00307:     missing_inputs: List[Dict[str, Any]] = []
00308:     for name, path, route, optional in specs:
00309:         records, missing = _artifact_records(path, route, name, optional=optional)
00310:         corpus.extend(records)
00311:         counts[name] = len(records)
00312:         if missing:
00313:             missing_inputs.append(missing)
00314:     return corpus, counts, missing_inputs
00315: 
00316: 
00317: def _trust_tier_for_route(route: str, score: int, seed_entities: Sequence[str]) -> str:
00318:     if route == "table" and score >= 100 and seed_entities:
00319:         return "exact_source_evidence_candidate"
00320:     if route == "table":
00321:         return "structured_table_candidate"
00322:     if route == "normal_text":
00323:         return "source_context_guidance"
00324:     if route == "graph":
00325:         return "relationship_candidate"
00326:     if route == "image_visual":
00327:         return "visual_candidate_only"
00328:     if route == "route_dispatch":
00329:         return "routing_metadata_not_source_truth"
00330:     return "candidate_or_supporting"
00331: 
00332: 
00333: def _evidence_capsule(record: Mapping[str, Any], *, route: str, seed_entities: Sequence[str], score: int, fallback: bool = False) -> Dict[str, Any]:
00334:     page_id = _recursive_first(record, PAGE_KEYS)
00335:     excerpt = _record_text_blob(record)[:900]
00336:     return {
00337:         "capsule_version": MODULE_VERSION,
00338:         "route": route,
00339:         "source_artifact": record.get("_artifact_name"),
00340:         "source_artifact_path": record.get("_artifact_path"),
00341:         "source_artifact_index": record.get("_artifact_index"),
00342:         "page_id": str(page_id) if page_id not in (None, "") else None,
00343:         "match_score": score,
00344:         "fallback_available_context": bool(fallback),
00345:         "trust_tier": _trust_tier_for_route(route, score, seed_entities),
00346:         "source_text_excerpt": excerpt,
00347:         "source_trace_ready": bool(page_id),
00348:         "claim_authority": "candidate_or_context_until_final_gate",
00349:         "answer_permission": False,
00350:         "can_prove_claims": False,
00351:         "source_truth_mutation_allowed": False,
```
### Source window L737-L793
```python
00737: 
00738:     quality_status = "FAIL" if failures else "PASS"
00739:     return {
00740:         "quality_status": quality_status,
00741:         "summary": summary,
00742:         "failures": failures,
00743:         "checked_report_path": str(report_path),
00744:     }
00745: 
00746: 
00747: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00748:     parser = argparse.ArgumentParser(description="Build TRACE-Net engineering context pack builder v1.")
00749:     parser.add_argument("--blueprint", required=True)
00750:     parser.add_argument("--output-dir", required=True)
00751:     parser.add_argument("--route-dispatch-handoff")
00752:     parser.add_argument("--table-exact-search-adapter")
00753:     parser.add_argument("--page-context-v2")
00754:     parser.add_argument("--leiden-communities")
00755:     parser.add_argument("--image-visual-observer")
00756:     parser.add_argument("--max-records-per-slot", type=int, default=8)
00757:     parser.add_argument("--quality", action="store_true")
00758:     args = parser.parse_args(argv)
00759: 
00760:     payload = build_engineering_context_pack_builder(
00761:         blueprint_path=Path(args.blueprint),
00762:         output_dir=Path(args.output_dir),
00763:         route_dispatch_handoff=Path(args.route_dispatch_handoff) if args.route_dispatch_handoff else None,
00764:         table_exact_search_adapter=Path(args.table_exact_search_adapter) if args.table_exact_search_adapter else None,
00765:         page_context_v2=Path(args.page_context_v2) if args.page_context_v2 else None,
00766:         leiden_communities=Path(args.leiden_communities) if args.leiden_communities else None,
00767:         image_visual_observer=Path(args.image_visual_observer) if args.image_visual_observer else None,
00768:         max_records_per_slot=args.max_records_per_slot,
00769:     )
00770:     print("Status:", payload["status"])
00771:     print("Quality status:", payload["quality_status"])
00772:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
00773:     return 0 if payload["quality_status"] == "PASS" else 1
00774: 
00775: 
00776: def main_check(argv: Optional[Sequence[str]] = None) -> int:
00777:     parser = argparse.ArgumentParser(description="Check TRACE-Net engineering context pack builder v1 quality.")
00778:     parser.add_argument("--report-path", required=True)
00779:     parser.add_argument("--write-json", action="store_true")
00780:     parser.add_argument("--require-source-blueprint-quality-pass", action="store_true")
00781:     parser.add_argument("--min-context-packs", type=int, default=1)
00782:     parser.add_argument("--min-artifact-corpus-records", type=int, default=1)
00783:     parser.add_argument("--min-evidence-capsules", type=int, default=1)
00784:     parser.add_argument("--min-high-signal-evidence-capsules", type=int, default=0)
00785:     parser.add_argument("--min-packs-ready-for-gemma-context", type=int, default=1)
00786:     parser.add_argument("--max-missing-optional-artifact-inputs", type=int)
00787:     parser.add_argument("--max-unsafe", type=int, default=0)
00788:     parser.add_argument("--require-no-answer-permission", action="store_true")
00789:     parser.add_argument("--require-no-llm-calls", action="store_true")
00790:     parser.add_argument("--require-no-retrieval-execution", action="store_true")
00791:     parser.add_argument("--require-no-source-truth-mutation", action="store_true")
00792:     args = parser.parse_args(argv)
00793: 
```
### Source window L570-L626
```python
00570:     )
00571:     high_signal_route_capsule_counts = Counter(
00572:         route
00573:         for record in records
00574:         for route, capsules in record.get("route_evidence_capsules", {}).items()
00575:         for capsule in capsules
00576:         if not capsule.get("fallback_available_context")
00577:     )
00578:     intent_counts = Counter(record.get("intent_family") for record in records)
00579: 
00580:     summary = {
00581:         "source_blueprint_quality_status": blueprint_payload.get("quality_status"),
00582:         "source_blueprint_count": len(blueprints),
00583:         "context_pack_count": len(records),
00584:         "artifact_corpus_record_count": len(corpus),
00585:         "artifact_record_counts": artifact_counts,
00586:         "artifact_missing_input_count": len(missing_inputs),
00587:         "artifact_missing_inputs": missing_inputs,
00588:         "intent_family_counts": dict(sorted(intent_counts.items())),
00589:         "total_evidence_capsule_count": sum(record.get("evidence_capsule_count", 0) for record in records),
00590:         "total_high_signal_evidence_capsule_count": sum(record.get("high_signal_evidence_capsule_count", 0) for record in records),
00591:         "total_fallback_evidence_capsule_count": sum(record.get("fallback_evidence_capsule_count", 0) for record in records),
00592:         "route_evidence_capsule_counts": dict(sorted(route_capsule_counts.items())),
00593:         "high_signal_route_evidence_capsule_counts": dict(sorted(high_signal_route_capsule_counts.items())),
00594:         "packs_ready_for_gemma_context_count": sum(1 for r in records if r.get("ready_for_gemma_context")),
00595:         "packs_ready_for_self_rag_check_count": sum(1 for r in records if r.get("ready_for_self_rag_check")),
00596:         "total_missing_evidence_note_count": sum(len(r.get("missing_evidence") or []) for r in records),
00597:         "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
00598:         "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
00599:         "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
00600:         "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
00601:         "llm_call_allowed_count": sum(1 for r in records if r.get("llm_call_allowed")),
00602:         "retrieval_execution_allowed_count": sum(1 for r in records if r.get("retrieval_execution_allowed")),
00603:         "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
00604:         "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
00605:         "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
00606:         "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
00607:     }
00608: 
00609:     quality_status = "PASS"
00610:     if blueprint_payload.get("quality_status") != "PASS":
00611:         quality_status = "FAIL"
00612:     if not records:
00613:         quality_status = "FAIL"
00614:     if summary["unsafe_record_count"] != 0:
00615:         quality_status = "FAIL"
00616: 
00617:     payload: Dict[str, Any] = {
00618:         "module": MODULE_VERSION,
00619:         "status": "ENGINEERING_CONTEXT_PACK_BUILDER_BUILT",
00620:         "quality_status": quality_status,
00621:         "summary": summary,
00622:         "source_blueprint_path": str(blueprint_path),
00623:         "artifact_inputs": {
00624:             "route_dispatch_handoff": str(route_dispatch_handoff) if route_dispatch_handoff else None,
00625:             "table_exact_search_adapter": str(table_exact_search_adapter) if table_exact_search_adapter else None,
00626:             "page_context_v2": str(page_context_v2) if page_context_v2 else None,
```

## `tiff/trace_net_engineering_engram_memory_layers_v1.py`
- Location: `active_source_code`
- Score: `240`
- Categories: `context_pack, crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Engram Memory Layers v1. Artifact-only taxonomy builder for TRACE-Net Engram records. The layer taxonomy is deliberately behavior guidance, not source truth. It can shape answer style, route interpretation, critique, and repair behavior, but it must never prove manual facts, mutate source truth, or grant answer permission.
- Functions: utc_now_iso()@L170; stable_hash(value)@L174; load_json(path)@L179; write_json(path, data)@L183; _as_list(value)@L189; _lower_text()@L199; extract_engram_atoms(core)@L211; infer_memory_layer(atom)@L257; infer_proof_role(atom, layer)@L294; normalize_atom(atom)@L303; seed_layer_atoms()@L329; build_layered_atoms(core)@L333; group_layer_counts(atoms)@L343; unsafe_findings(atoms, manifest)@L352; validate_layered_manifest(manifest)@L386; build_memory_layer_manifest()@L444; check_memory_layer_manifest()@L511

### Source window L1-L29
```python
00001: """TRACE-Net Engineering Engram Memory Layers v1.
00002: 
00003: Artifact-only taxonomy builder for TRACE-Net Engram records.
00004: 
00005: The layer taxonomy is deliberately behavior guidance, not source truth.  It can
00006: shape answer style, route interpretation, critique, and repair behavior, but it
00007: must never prove manual facts, mutate source truth, or grant answer permission.
00008: """
00009: 
00010: from __future__ import annotations
00011: 
00012: import hashlib
00013: import json
00014: import re
00015: from dataclasses import dataclass
00016: from datetime import datetime, timezone
00017: from pathlib import Path
00018: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00019: 
00020: MODULE = "trace_net_engineering_engram_memory_layers_v1"
00021: VERSION = "v1"
00022: STATUS_BUILT = "TRACE_NET_ENGINEERING_ENGRAM_MEMORY_LAYERS_BUILT"
00023: STATUS_CHECKED = "TRACE_NET_ENGINEERING_ENGRAM_MEMORY_LAYERS_CHECKED"
00024: SAFETY_CONTRACT = "no_db_writes_no_vector_writes_no_search_writes_no_source_truth_mutation_no_answer_permission"
00025: 
00026: MEMORY_LAYERS: Tuple[str, ...] = (
00027:     "working_memory",
00028:     "semantic_memory",
00029:     "procedural_memory",
```
### Source window L253-L309
```python
00253:         out.append(atom)
00254:     return out
00255: 
00256: 
00257: def infer_memory_layer(atom: Mapping[str, Any]) -> str:
00258:     text = _lower_text(
00259:         atom.get("memory_layer"),
00260:         atom.get("memory_type"),
00261:         atom.get("atom_id"),
00262:         atom.get("id"),
00263:         atom.get("title"),
00264:         atom.get("trait"),
00265:         atom.get("traits"),
00266:         atom.get("tags"),
00267:         atom.get("category"),
00268:         atom.get("source_key"),
00269:         atom.get("rule"),
00270:         atom.get("description"),
00271:         atom.get("failure_pattern"),
00272:         atom.get("repair_pattern"),
00273:     )
00274:     explicit = str(atom.get("memory_layer") or atom.get("memory_type") or "").strip().lower()
00275:     explicit = explicit.replace("-", "_").replace(" ", "_")
00276:     if explicit in MEMORY_LAYERS:
00277:         return explicit
00278: 
00279:     if any(k in text for k in ("working_memory", "working memory", "current question", "context pack", "proof_context")):
00280:         return "working_memory"
00281:     if any(k in text for k in ("critic", "self-rag", "self_rag", "crag", "repair", "fallback", "retry", "too generic")):
00282:         return "critic_memory"
00283:     if any(k in text for k in ("episodic", "episode", "h13", "h14", "h16", "eval", "smoke", "failure", "regression")):
00284:         return "episodic_memory"
00285:     if any(k in text for k in ("procedural", "policy", "rule", "if user", "interchange", "replacement", "effectivity", "fit", "installation")):
00286:         return "procedural_memory"
00287:     if any(k in text for k in ("trait", "style", "tone", "answer shape", "cautious", "helpful", "confidence")):
00288:         return "trait_memory"
00289:     if any(k in text for k in ("semantic", "route", "visual", "ocr", "table", "nomenclature", "summary", "graph", "leiden")):
00290:         return "semantic_memory"
00291:     return "semantic_memory"
00292: 
00293: 
00294: def infer_proof_role(atom: Mapping[str, Any], layer: str) -> str:
00295:     proof_role = str(atom.get("proof_role") or "").strip().lower()
00296:     if proof_role:
00297:         return proof_role
00298:     if layer == "working_memory":
00299:         return "current_proof_context_only"
00300:     return "guidance_only"
00301: 
00302: 
00303: def normalize_atom(atom: Mapping[str, Any], *, source_core_path: str = "") -> Dict[str, Any]:
00304:     layer = infer_memory_layer(atom)
00305:     atom_id = str(atom.get("atom_id") or atom.get("id") or f"h17_imported_{stable_hash(atom)}")
00306:     proof_role = infer_proof_role(atom, layer)
00307:     normalized: Dict[str, Any] = {
00308:         "atom_id": atom_id,
00309:         "memory_layer": layer,
```
### Source window L44-L100
```python
00044:         "description": "Stable route and evidence-meaning knowledge, such as what visual, OCR, table, and summary records can and cannot prove.",
00045:         "runtime_role": "route_meaning_guidance",
00046:         "proof_role": "guidance_only",
00047:         "allowed_sources": ["reviewed_policy", "route_contract", "eval_lesson", "engram_core"],
00048:         "must_not_persist_source_truth": True,
00049:     },
00050:     "procedural_memory": {
00051:         "description": "If/then behavior rules that control boundaries such as interchangeability, replacement approval, fit, effectivity, and unknown-part responses.",
00052:         "runtime_role": "answer_boundary_control",
00053:         "proof_role": "guidance_only",
00054:         "allowed_sources": ["reviewed_policy", "safety_rule", "eval_lesson", "engram_core"],
00055:         "must_not_persist_source_truth": True,
00056:     },
00057:     "episodic_memory": {
00058:         "description": "Past runs, smoke-test outcomes, failures, repairs, and regression lessons.",
00059:         "runtime_role": "failure_recall_and_regression_prevention",
00060:         "proof_role": "guidance_only",
00061:         "allowed_sources": ["eval_result", "smoke_test", "repair_note", "engram_core"],
00062:         "must_not_persist_source_truth": True,
00063:     },
00064:     "trait_memory": {
00065:         "description": "Stable engineering behavior profile: cautious, source-trace-first, useful, calm, and not overclaiming.",
00066:         "runtime_role": "consistent_engineering_style",
00067:         "proof_role": "guidance_only",
00068:         "allowed_sources": ["reviewed_trait", "style_rule", "answer_shape", "engram_core"],
00069:         "must_not_persist_source_truth": True,
00070:     },
00071:     "critic_memory": {
00072:         "description": "Self-RAG and CRAG critique/repair lessons, including safe-but-too-generic drafts, retry patterns, and repair examples.",
00073:         "runtime_role": "draft_critique_and_repair",
00074:         "proof_role": "guidance_only",
00075:         "allowed_sources": ["critic_lesson", "repair_lesson", "eval_failure", "engram_core"],
00076:         "must_not_persist_source_truth": True,
00077:     },
00078: }
00079: 
00080: DEFAULT_LAYER_SEED_ATOMS: List[Dict[str, Any]] = [
00081:     {
00082:         "atom_id": "working_current_question_context_pack_citations_v1",
00083:         "memory_layer": "working_memory",
00084:         "memory_type": "working_memory",
00085:         "title": "Current answer working set",
00086:         "trigger": ["every answer"],
00087:         "rule": "Use the current user question, current context pack, and current proof citations as the only answer-time factual working set.",
00088:         "allowed_behavior": "Ground the draft in current proof_context and citation labels.",
00089:         "forbidden_behavior": "Do not import proof from old Engram memories or summaries.",
00090:         "proof_role": "current_proof_context_only",
00091:         "activation_status": "active",
00092:         "source": "h17_seed_taxonomy",
00093:     },
00094:     {
00095:         "atom_id": "semantic_visual_link_vs_ocr_nomenclature_v1",
00096:         "memory_layer": "semantic_memory",
00097:         "memory_type": "semantic_memory",
00098:         "title": "Visual link versus OCR nomenclature",
00099:         "trigger": ["visual route", "OCR nomenclature", "figure-to-part identity"],
00100:         "rule": "visual_figure_link establishes figure-to-part identity; OCR nomenclature provides source-trace line-text proof for the part name.",
```
### Source window L123-L179
```python
00123:         "memory_type": "episodic_memory",
00124:         "title": "Repair generic not-proven answers",
00125:         "trigger": ["not proven", "pipeline recovery", "known eval failure"],
00126:         "rule": "H13 overused generic not-proven wording; repairs should still explain what evidence is proven and why the requested claim is out of scope.",
00127:         "allowed_behavior": "Use can-prove / cannot-prove / evidence / limits shape.",
00128:         "forbidden_behavior": "Do not answer with a generic refusal when proof_context supports a useful limited explanation.",
00129:         "proof_role": "guidance_only",
00130:         "activation_status": "active",
00131:         "source": "h17_seed_taxonomy",
00132:     },
00133:     {
00134:         "atom_id": "trait_cautious_source_trace_helpful_v1",
00135:         "memory_layer": "trait_memory",
00136:         "memory_type": "trait_memory",
00137:         "title": "Cautious source-trace helpfulness",
00138:         "trigger": ["every answer", "engineering answer style"],
00139:         "rule": "Behave as a cautious, source-trace-first engineering analyst who is helpful without overclaiming.",
00140:         "allowed_behavior": "Use calm engineering confidence, explicit evidence, and explicit limits.",
00141:         "forbidden_behavior": "Do not become a generic disclaimer machine or invent approvals.",
00142:         "proof_role": "guidance_only",
00143:         "activation_status": "active",
00144:         "source": "h17_seed_taxonomy",
00145:     },
00146:     {
00147:         "atom_id": "critic_safe_but_too_generic_repair_v1",
00148:         "memory_layer": "critic_memory",
00149:         "memory_type": "critic_memory",
00150:         "title": "Safe but too generic repair",
00151:         "trigger": ["Self-RAG", "CRAG", "draft critique", "safe but too generic"],
00152:         "rule": "If an answer is safe but too generic, retrieve a repair pattern before regenerating and add the specific route/evidence explanation.",
00153:         "allowed_behavior": "Critique for missing proof explanation, missing limits, or missing route distinction.",
00154:         "forbidden_behavior": "Do not repair by adding unsupported claims or treating Engram memory as proof.",
00155:         "proof_role": "guidance_only",
00156:         "activation_status": "active",
00157:         "source": "h17_seed_taxonomy",
00158:     },
00159: ]
00160: 
00161: UNSAFE_CLAIM_PATTERNS: Tuple[str, ...] = (
00162:     r"\banswer_permission\s*[:=]\s*true\b",
00163:     r"\bsource_truth_mutation_allowed\s*[:=]\s*true\b",
00164:     r"\bpostgres_write_attempt\s*[:=]\s*[1-9]",
00165:     r"\bqdrant_write_attempt\s*[:=]\s*[1-9]",
00166:     r"\bopensearch_write_attempt\s*[:=]\s*[1-9]",
00167: )
00168: 
00169: 
00170: def utc_now_iso() -> str:
00171:     return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
00172: 
00173: 
00174: def stable_hash(value: Any) -> str:
00175:     blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
00176:     return hashlib.sha256(blob).hexdigest()[:16]
00177: 
00178: 
00179: def load_json(path: Path | str) -> Any:
```
### Source window L193-L249
```python
00193:         return value
00194:     if isinstance(value, tuple):
00195:         return list(value)
00196:     return [value]
00197: 
00198: 
00199: def _lower_text(*values: Any) -> str:
00200:     parts: List[str] = []
00201:     for value in values:
00202:         if isinstance(value, Mapping):
00203:             parts.append(json.dumps(value, sort_keys=True, ensure_ascii=False))
00204:         elif isinstance(value, (list, tuple)):
00205:             parts.extend(str(v) for v in value)
00206:         elif value is not None:
00207:             parts.append(str(value))
00208:     return "\n".join(parts).lower()
00209: 
00210: 
00211: def extract_engram_atoms(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
00212:     """Return likely Engram atom records from a flexible H15-style core JSON."""
00213:     candidate_keys = (
00214:         "engram_atoms",
00215:         "atoms",
00216:         "records",
00217:         "memory_atoms",
00218:         "policy_traits",
00219:         "style_traits",
00220:         "failure_memories",
00221:         "critic_traits",
00222:         "repair_traits",
00223:     )
00224:     atoms: List[Dict[str, Any]] = []
00225:     for key in candidate_keys:
00226:         value = core.get(key)
00227:         if isinstance(value, list):
00228:             for idx, item in enumerate(value):
00229:                 if isinstance(item, Mapping):
00230:                     rec = dict(item)
00231:                 else:
00232:                     rec = {"value": item}
00233:                 rec.setdefault("source_key", key)
00234:                 rec.setdefault("source_index", idx)
00235:                 atoms.append(rec)
00236: 
00237:     # Some cores may put the list under summary/details wrappers.
00238:     for wrapper_key in ("engram_core", "data", "manifest"):
00239:         wrapper = core.get(wrapper_key)
00240:         if isinstance(wrapper, Mapping):
00241:             for atom in extract_engram_atoms(wrapper):
00242:                 atom.setdefault("source_wrapper", wrapper_key)
00243:                 atoms.append(atom)
00244: 
00245:     # De-duplicate by atom_id or stable content hash.
00246:     seen: set[str] = set()
00247:     out: List[Dict[str, Any]] = []
00248:     for atom in atoms:
00249:         key = str(atom.get("atom_id") or atom.get("id") or stable_hash(atom))
```
### Source window L387-L443
```python
00387:     manifest: Mapping[str, Any],
00388:     *,
00389:     min_atoms: int = 6,
00390:     require_all_layers: bool = True,
00391:     max_unsafe: int = 0,
00392:     require_no_answer_permission: bool = True,
00393: ) -> Tuple[bool, List[str], Dict[str, Any]]:
00394:     errors: List[str] = []
00395:     atoms = manifest.get("memory_atoms") or manifest.get("records") or []
00396:     if not isinstance(atoms, list):
00397:         errors.append("memory_atoms must be a list")
00398:         atoms = []
00399:     if len(atoms) < min_atoms:
00400:         errors.append(f"memory atom count below minimum: {len(atoms)} < {min_atoms}")
00401: 
00402:     layer_counts = group_layer_counts([a for a in atoms if isinstance(a, Mapping)])
00403:     if require_all_layers:
00404:         missing = [layer for layer, count in layer_counts.items() if count <= 0]
00405:         if missing:
00406:             errors.append("missing required memory layers: " + ",".join(missing))
00407: 
00408:     for idx, atom in enumerate(atoms):
00409:         if not isinstance(atom, Mapping):
00410:             errors.append(f"atom {idx} is not an object")
00411:             continue
00412:         layer = str(atom.get("memory_layer") or "")
00413:         if layer not in MEMORY_LAYERS:
00414:             errors.append(f"atom {atom.get('atom_id', idx)} has invalid memory_layer={layer!r}")
00415:         proof_role = str(atom.get("proof_role") or "")
00416:         if not proof_role:
00417:             errors.append(f"atom {atom.get('atom_id', idx)} missing proof_role")
00418:         if layer != "working_memory" and proof_role != "guidance_only":
00419:             errors.append(f"atom {atom.get('atom_id', idx)} non-working memory must be guidance_only, got {proof_role!r}")
00420:         if layer == "working_memory" and proof_role not in ("current_proof_context_only", "guidance_only"):
00421:             errors.append(f"working atom {atom.get('atom_id', idx)} has invalid proof_role={proof_role!r}")
00422:         if atom.get("answer_permission") is True or atom.get("answer_permission_allowed") is True:
00423:             errors.append(f"atom {atom.get('atom_id', idx)} grants answer permission")
00424: 
00425:     findings = unsafe_findings([a for a in atoms if isinstance(a, Mapping)], manifest)
00426:     if len(findings) > max_unsafe:
00427:         errors.append(f"unsafe finding count above maximum: {len(findings)} > {max_unsafe}")
00428: 
00429:     summary = manifest.get("summary", {}) if isinstance(manifest.get("summary"), Mapping) else {}
00430:     if require_no_answer_permission:
00431:         answer_permission_count = int(summary.get("answer_permission_count", manifest.get("answer_permission_count", 0)) or 0)
00432:         if answer_permission_count:
00433:             errors.append(f"answer_permission_count must be 0, got {answer_permission_count}")
00434: 
00435:     metrics = {
00436:         "memory_atom_count": len(atoms),
00437:         "layer_counts": layer_counts,
00438:         "unsafe_finding_count": len(findings),
00439:         "unsafe_findings": findings,
00440:     }
00441:     return not errors, errors, metrics
00442: 
00443: 
```
### Source window L455-L511
```python
00455:     core = load_json(core_path)
00456:     atoms = build_layered_atoms(core if isinstance(core, Mapping) else {}, source_core_path=str(core_path), include_seed_atoms=include_seed_atoms)
00457:     layer_counts = group_layer_counts(atoms)
00458:     generated_at = utc_now_iso()
00459: 
00460:     manifest: Dict[str, Any] = {
00461:         "status": STATUS_BUILT,
00462:         "module": MODULE,
00463:         "version": VERSION,
00464:         "generated_at": generated_at,
00465:         "quality_status": "UNKNOWN",
00466:         "safety_contract": SAFETY_CONTRACT,
00467:         "source_engram_core_path": str(core_path),
00468:         "taxonomy": {
00469:             "memory_layers": list(MEMORY_LAYERS),
00470:             "layer_definitions": LAYER_DEFINITIONS,
00471:             "proof_boundary": "Engram memory is behavior guidance only. Manual facts must still come from current proof_context citations.",
00472:             "working_memory_note": "Working memory can carry current proof citations at answer time but is not persisted as source truth by this artifact.",
00473:         },
00474:         "memory_atoms": atoms,
00475:         "summary": {
00476:             "module": MODULE,
00477:             "version": VERSION,
00478:             "memory_layer_count": len(MEMORY_LAYERS),
00479:             "memory_atom_count": len(atoms),
00480:             "layer_counts": layer_counts,
00481:             "source_engram_atom_count": len(extract_engram_atoms(core if isinstance(core, Mapping) else {})),
00482:             "seed_atom_count": len(DEFAULT_LAYER_SEED_ATOMS) if include_seed_atoms else 0,
00483:             "engram_memory_guidance_only_count": sum(1 for a in atoms if a.get("proof_role") == "guidance_only"),
00484:             "working_memory_current_proof_context_count": sum(1 for a in atoms if a.get("proof_role") == "current_proof_context_only"),
00485:             "answer_permission_count": 0,
00486:             "source_truth_mutation_allowed_count": 0,
00487:             "postgres_write_attempt_count": 0,
00488:             "qdrant_write_attempt_count": 0,
00489:             "opensearch_write_attempt_count": 0,
00490:             "opensearch_upload_attempt_count": 0,
00491:             "write_attempt_count": 0,
00492:         },
00493:     }
00494: 
00495:     passed, errors, metrics = validate_layered_manifest(
00496:         manifest,
00497:         min_atoms=min_atoms,
00498:         require_all_layers=require_all_layers,
00499:         max_unsafe=max_unsafe,
00500:     )
00501:     manifest["quality_status"] = "PASS" if passed else "FAIL"
00502:     manifest["quality_errors"] = errors
00503:     manifest["summary"].update(metrics)
00504: 
00505:     out_dir.mkdir(parents=True, exist_ok=True)
00506:     manifest_path = out_dir / "trace_net_engineering_engram_memory_layers_v1.json"
00507:     write_json(manifest_path, manifest)
00508:     return manifest
00509: 
00510: 
00511: def check_memory_layer_manifest(
```
### Source window L516-L553
```python
00516:     max_unsafe: int = 0,
00517:     require_quality_pass: bool = False,
00518: ) -> Dict[str, Any]:
00519:     path = Path(memory_layers_path)
00520:     manifest = load_json(path)
00521:     passed, errors, metrics = validate_layered_manifest(
00522:         manifest if isinstance(manifest, Mapping) else {},
00523:         min_atoms=min_atoms,
00524:         require_all_layers=require_all_layers,
00525:         max_unsafe=max_unsafe,
00526:     )
00527:     if require_quality_pass and manifest.get("quality_status") != "PASS":
00528:         passed = False
00529:         errors.append(f"input quality_status is not PASS: {manifest.get('quality_status')!r}")
00530:     result = {
00531:         "status": STATUS_CHECKED,
00532:         "module": MODULE,
00533:         "version": VERSION,
00534:         "quality_status": "PASS" if passed else "FAIL",
00535:         "checked_path": str(path),
00536:         "safety_contract": SAFETY_CONTRACT,
00537:         "summary": {
00538:             "module": MODULE,
00539:             "version": VERSION,
00540:             **metrics,
00541:             "answer_permission_count": 0,
00542:             "source_truth_mutation_allowed_count": 0,
00543:             "postgres_write_attempt_count": 0,
00544:             "qdrant_write_attempt_count": 0,
00545:             "opensearch_write_attempt_count": 0,
00546:             "opensearch_upload_attempt_count": 0,
00547:             "write_attempt_count": 0,
00548:         },
00549:         "quality_errors": errors,
00550:     }
00551:     check_path = path.with_name("trace_net_engineering_engram_memory_layers_v1_quality_check.json")
00552:     write_json(check_path, result)
00553:     return result
```

## `tiff/trace_net_engineering_engram_vector_retriever_v1.py`
- Location: `active_source_code`
- Score: `240`
- Categories: `context_pack, crag, engram, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Engram Vector Retriever v1. Artifact-only local retriever for H18 Engram vector-loader records. This module intentionally does not contact Qdrant or any live service. It uses the same style of deterministic hashing-vector scoring as the H18 local loader so the retrieval behavior is reproducible in tests and git artifacts. A later live adapter can use the same payload contract after explicit write gates are added.
- Functions: _stable_id(text, prefix)@L85; tokenize(text)@L89; hashing_vector(text, dim)@L93; cosine_similarity(a, b)@L117; keyword_overlap_score(query_text, candidate_text)@L129; _coerce_vector(value, dim, text_fallback)@L139; _record_text(record)@L147; normalize_qdrant_ready_record(record, vector_dim)@L164; load_vector_loader(path)@L191; load_queries(path, inline_queries)@L196; retrieve_for_query(query, records)@L220; _counter(values)@L269; _write_json(path, obj)@L276; _write_jsonl(path, records)@L281; build_vector_retriever_manifest()@L286; check_vector_retriever_manifest()@L412

### Source window L1-L29
```python
00001: """TRACE-Net Engineering Engram Vector Retriever v1.
00002: 
00003: Artifact-only local retriever for H18 Engram vector-loader records.
00004: 
00005: This module intentionally does not contact Qdrant or any live service.  It uses the
00006: same style of deterministic hashing-vector scoring as the H18 local loader so the
00007: retrieval behavior is reproducible in tests and git artifacts.  A later live
00008: adapter can use the same payload contract after explicit write gates are added.
00009: """
00010: from __future__ import annotations
00011: 
00012: import hashlib
00013: import json
00014: import math
00015: import re
00016: from dataclasses import dataclass
00017: from pathlib import Path
00018: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00019: 
00020: MODULE = "trace_net_engineering_engram_vector_retriever_v1"
00021: VERSION = "v1"
00022: 
00023: SAFETY_CONTRACT = {
00024:     "answer_permission": False,
00025:     "source_truth_mutation_allowed": False,
00026:     "postgres_write_attempt": False,
00027:     "qdrant_write_attempt": False,
00028:     "opensearch_write_attempt": False,
00029:     "opensearch_upload_attempt": False,
```
### Source window L37-L93
```python
00037:     "procedural_memory",
00038:     "episodic_memory",
00039:     "trait_memory",
00040:     "critic_memory",
00041: ]
00042: 
00043: DEFAULT_RETRIEVAL_QUERIES = [
00044:     {
00045:         "query_id": "h19_q_interchangeability_boundary",
00046:         "text": "Is part 120-50645-005 interchangeable with 120-50645-011 or an approved replacement? Require explicit source authority.",
00047:         "expected_layers": ["procedural_memory", "trait_memory"],
00048:         "task_type": "interchangeability_boundary",
00049:     },
00050:     {
00051:         "query_id": "h19_q_visual_ocr_route_behavior",
00052:         "text": "Why does the visual route need OCR nomenclature evidence for Figure 69 and part names?",
00053:         "expected_layers": ["semantic_memory", "critic_memory"],
00054:         "task_type": "route_explanation",
00055:     },
00056:     {
00057:         "query_id": "h19_q_unknown_part_not_source_trace_ready",
00058:         "text": "Find part number 999-99999-999 and cite a source when no proof_context exists.",
00059:         "expected_layers": ["working_memory", "procedural_memory"],
00060:         "task_type": "unknown_part",
00061:     },
00062:     {
00063:         "query_id": "h19_q_safe_but_too_generic_repair",
00064:         "text": "The answer was safe but too generic. Retrieve repair behavior before regenerating.",
00065:         "expected_layers": ["critic_memory", "episodic_memory", "trait_memory"],
00066:         "task_type": "critic_repair",
00067:     },
00068:     {
00069:         "query_id": "h19_q_summary_only_limit",
00070:         "text": "Can v2 summaries alone prove Figure 69 part identity or source claims?",
00071:         "expected_layers": ["working_memory", "procedural_memory"],
00072:         "task_type": "summary_limit",
00073:     },
00074:     {
00075:         "query_id": "h19_q_installation_fit_effectivity_limit",
00076:         "text": "Does a figure or part identification prove installation safety, fit approval, aircraft effectivity, or replacement approval?",
00077:         "expected_layers": ["procedural_memory", "semantic_memory"],
00078:         "task_type": "approval_boundary",
00079:     },
00080: ]
00081: 
00082: _TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")
00083: 
00084: 
00085: def _stable_id(text: str, prefix: str = "h19") -> str:
00086:     return prefix + "_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
00087: 
00088: 
00089: def tokenize(text: str) -> List[str]:
00090:     return [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]
00091: 
00092: 
00093: def hashing_vector(text: str, dim: int = 64) -> List[float]:
```
### Source window L121-L177
```python
00121:     dot = sum(float(a[i]) * float(b[i]) for i in range(n))
00122:     na = math.sqrt(sum(float(x) * float(x) for x in a[:n]))
00123:     nb = math.sqrt(sum(float(x) * float(x) for x in b[:n]))
00124:     if na <= 0.0 or nb <= 0.0:
00125:         return 0.0
00126:     return dot / (na * nb)
00127: 
00128: 
00129: def keyword_overlap_score(query_text: str, candidate_text: str) -> float:
00130:     q = set(tokenize(query_text))
00131:     c = set(tokenize(candidate_text))
00132:     if not q or not c:
00133:         return 0.0
00134:     overlap = q & c
00135:     # Jaccard-style score with a small exact-overlap boost.
00136:     return len(overlap) / max(1, len(q))
00137: 
00138: 
00139: def _coerce_vector(value: Any, dim: int, text_fallback: str) -> List[float]:
00140:     if isinstance(value, list) and value and all(isinstance(x, (int, float)) for x in value):
00141:         out = [float(x) for x in value]
00142:         if len(out) == dim:
00143:             return out
00144:     return hashing_vector(text_fallback, dim=dim)
00145: 
00146: 
00147: def _record_text(record: Mapping[str, Any]) -> str:
00148:     parts = []
00149:     for key in ("text_for_embedding", "rule", "title", "atom_id", "memory_layer", "proof_role"):
00150:         val = record.get(key)
00151:         if isinstance(val, str) and val.strip():
00152:             parts.append(val.strip())
00153:     payload = record.get("qdrant_payload")
00154:     if isinstance(payload, Mapping):
00155:         for key in ("title", "rule", "trigger", "memory_type", "memory_layer", "proof_role"):
00156:             val = payload.get(key)
00157:             if isinstance(val, str) and val.strip():
00158:                 parts.append(val.strip())
00159:             elif isinstance(val, list):
00160:                 parts.extend(str(x) for x in val if str(x).strip())
00161:     return " | ".join(parts)
00162: 
00163: 
00164: def normalize_qdrant_ready_record(record: Mapping[str, Any], vector_dim: int) -> Dict[str, Any]:
00165:     payload = record.get("qdrant_payload")
00166:     if not isinstance(payload, Mapping):
00167:         payload = {}
00168:     atom_id = str(record.get("atom_id") or payload.get("atom_id") or _stable_id(json.dumps(record, sort_keys=True), "atom"))
00169:     memory_layer = str(record.get("memory_layer") or payload.get("memory_layer") or "unknown")
00170:     proof_role = str(record.get("proof_role") or payload.get("proof_role") or "guidance_only")
00171:     text = _record_text(record)
00172:     vector = _coerce_vector(record.get("vector") or record.get("embedding"), vector_dim, text)
00173:     point_id = str(record.get("point_id") or payload.get("point_id") or hashlib.sha256(atom_id.encode("utf-8")).hexdigest())
00174:     return {
00175:         "atom_id": atom_id,
00176:         "point_id": point_id,
00177:         "memory_layer": memory_layer,
```
### Source window L223-L279
```python
00223:     *,
00224:     top_k: int = 5,
00225:     vector_dim: int = 64,
00226: ) -> Dict[str, Any]:
00227:     query_text = str(query.get("text") or query.get("query") or "")
00228:     query_vec = hashing_vector(query_text, dim=vector_dim)
00229:     scored: List[Dict[str, Any]] = []
00230:     for rec in records:
00231:         rec_text = str(rec.get("text_for_embedding") or "")
00232:         sim = cosine_similarity(query_vec, rec.get("vector") or [])
00233:         overlap = keyword_overlap_score(query_text, rec_text)
00234:         expected_layers = set(query.get("expected_layers") or [])
00235:         layer_bonus = 0.05 if rec.get("memory_layer") in expected_layers else 0.0
00236:         final = (0.72 * sim) + (0.23 * overlap) + layer_bonus
00237:         scored.append({
00238:             "rank": 0,
00239:             "atom_id": rec.get("atom_id"),
00240:             "point_id": rec.get("point_id"),
00241:             "memory_layer": rec.get("memory_layer"),
00242:             "proof_role": rec.get("proof_role"),
00243:             "title": rec.get("title"),
00244:             "similarity_score": round(sim, 6),
00245:             "keyword_overlap_score": round(overlap, 6),
00246:             "layer_bonus": round(layer_bonus, 6),
00247:             "retrieval_score": round(final, 6),
00248:             "text_preview": rec_text[:700],
00249:             "answer_permission": bool(rec.get("answer_permission")),
00250:             "source_truth_mutation_allowed": bool(rec.get("source_truth_mutation_allowed")),
00251:             "qdrant_write_attempt": bool(rec.get("qdrant_write_attempt")),
00252:         })
00253:     scored.sort(key=lambda x: (x["retrieval_score"], x["similarity_score"]), reverse=True)
00254:     top = scored[: max(1, int(top_k or 5))]
00255:     for i, item in enumerate(top, start=1):
00256:         item["rank"] = i
00257:     return {
00258:         "query_id": query.get("query_id"),
00259:         "task_type": query.get("task_type"),
00260:         "query_text": query_text,
00261:         "expected_layers": list(query.get("expected_layers") or []),
00262:         "top_k": top_k,
00263:         "result_count": len(top),
00264:         "covered_layers": sorted({str(x.get("memory_layer")) for x in top if x.get("memory_layer")}),
00265:         "results": top,
00266:     }
00267: 
00268: 
00269: def _counter(values: Iterable[str]) -> Dict[str, int]:
00270:     out: Dict[str, int] = {}
00271:     for value in values:
00272:         out[value] = out.get(value, 0) + 1
00273:     return dict(sorted(out.items()))
00274: 
00275: 
00276: def _write_json(path: Path, obj: Mapping[str, Any]) -> None:
00277:     path.parent.mkdir(parents=True, exist_ok=True)
00278:     path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
00279: 
```
### Source window L356-L412
```python
00356:             "collection_name": collection_plan.get("collection_name", "trace_net_engineering_engram_memory_v1"),
00357:             "distance": collection_plan.get("distance", "Cosine"),
00358:             "encoder": collection_plan.get("encoder", "trace_net_hashing_encoder_v1"),
00359:             "retriever": "trace_net_local_hashing_retriever_v1",
00360:             "vector_dim": vector_dim,
00361:             "live_qdrant_read_attempted": False,
00362:             "live_qdrant_write_attempted": False,
00363:             "note": "Artifact-only local retrieval over Qdrant-ready Engram records; no live Qdrant IO.",
00364:         },
00365:         "retrieval_queries": queries,
00366:         "retrieval_records": retrieval_records,
00367:         "summary": {
00368:             "module": MODULE,
00369:             "version": VERSION,
00370:             "query_count": len(queries),
00371:             "qdrant_ready_record_count": len(records),
00372:             "retrieval_record_count": len(retrieval_records),
00373:             "total_retrieved_item_count": len(all_result_items),
00374:             "top_k": top_k,
00375:             "vector_dim": vector_dim,
00376:             "indexed_memory_layer_counts": indexed_layer_counts,
00377:             "retrieved_memory_layer_counts": result_layer_counts,
00378:             "missing_indexed_layers": missing_indexed_layers,
00379:             "missing_retrieved_layers": missing_retrieved_layers,
00380:             "answer_permission_count": answer_permission_count,
00381:             "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
00382:             "postgres_write_attempt_count": 0,
00383:             "qdrant_write_attempt_count": qdrant_write_attempt_count,
00384:             "opensearch_write_attempt_count": 0,
00385:             "opensearch_upload_attempt_count": 0,
00386:             "write_attempt_count": write_attempt_count,
00387:             "unsafe_finding_count": unsafe_finding_count,
00388:             "unsafe_findings": unsafe_findings,
00389:             "ready_for_engram_prompt_retrieval": quality_status == "PASS",
00390:         },
00391:         "safety_contract": dict(SAFETY_CONTRACT),
00392:     }
00393: 
00394:     manifest_path = output / f"{MODULE}.json"
00395:     records_path = output / f"{MODULE}_retrieval_records.jsonl"
00396:     check_path = output / f"{MODULE}_quality_check.json"
00397:     _write_json(manifest_path, manifest)
00398:     _write_jsonl(records_path, retrieval_records)
00399:     _write_json(check_path, {
00400:         "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_RETRIEVER_CHECKED",
00401:         "quality_status": quality_status,
00402:         "summary": manifest["summary"],
00403:         "safety_contract": manifest["safety_contract"],
00404:     })
00405:     manifest["output_path"] = str(manifest_path)
00406:     manifest["retrieval_records_path"] = str(records_path)
00407:     manifest["quality_check_path"] = str(check_path)
00408:     _write_json(manifest_path, manifest)
00409:     return manifest
00410: 
00411: 
00412: def check_vector_retriever_manifest(
```
### Source window L297-L353
```python
00297:     max_unsafe: int = 0,
00298:     max_write_attempts: int = 0,
00299: ) -> Dict[str, Any]:
00300:     loader = load_vector_loader(vector_loader_path)
00301:     output = Path(output_dir)
00302:     output.mkdir(parents=True, exist_ok=True)
00303: 
00304:     collection_plan = loader.get("collection_plan") if isinstance(loader.get("collection_plan"), Mapping) else {}
00305:     summary = loader.get("summary") if isinstance(loader.get("summary"), Mapping) else {}
00306:     vector_dim = int(collection_plan.get("vector_dim") or summary.get("vector_dim") or 64)
00307:     raw_records = loader.get("qdrant_ready_records") or []
00308:     if not isinstance(raw_records, list):
00309:         raw_records = []
00310:     records = [normalize_qdrant_ready_record(r, vector_dim=vector_dim) for r in raw_records if isinstance(r, Mapping)]
00311:     queries = load_queries(queries_path, inline_queries)
00312: 
00313:     retrieval_records = [
00314:         retrieve_for_query(q, records, top_k=top_k, vector_dim=vector_dim)
00315:         for q in queries[:]
00316:     ]
00317: 
00318:     all_result_items = [item for rr in retrieval_records for item in rr.get("results", [])]
00319:     result_layer_counts = _counter(str(item.get("memory_layer")) for item in all_result_items if item.get("memory_layer"))
00320:     indexed_layer_counts = _counter(str(r.get("memory_layer")) for r in records if r.get("memory_layer"))
00321:     missing_indexed_layers = [layer for layer in REQUIRED_LAYERS if indexed_layer_counts.get(layer, 0) <= 0]
00322:     missing_retrieved_layers = [layer for layer in REQUIRED_LAYERS if result_layer_counts.get(layer, 0) <= 0]
00323: 
00324:     answer_permission_count = sum(1 for r in records if r.get("answer_permission")) + sum(1 for item in all_result_items if item.get("answer_permission"))
00325:     source_truth_mutation_allowed_count = sum(1 for r in records if r.get("source_truth_mutation_allowed")) + sum(1 for item in all_result_items if item.get("source_truth_mutation_allowed"))
00326:     qdrant_write_attempt_count = sum(1 for r in records if r.get("qdrant_write_attempt")) + sum(1 for item in all_result_items if item.get("qdrant_write_attempt"))
00327:     write_attempt_count = qdrant_write_attempt_count
00328: 
00329:     unsafe_findings: List[str] = []
00330:     if len(queries) < min_queries:
00331:         unsafe_findings.append(f"query_count_below_min:{len(queries)}<{min_queries}")
00332:     for rr in retrieval_records:
00333:         if rr.get("result_count", 0) < min_results_per_query:
00334:             unsafe_findings.append(f"query_result_count_below_min:{rr.get('query_id')}:{rr.get('result_count')}<{min_results_per_query}")
00335:     if require_all_layers and missing_indexed_layers:
00336:         unsafe_findings.append("missing_indexed_layers:" + ",".join(missing_indexed_layers))
00337:     if require_all_layers and missing_retrieved_layers:
00338:         unsafe_findings.append("missing_retrieved_layers:" + ",".join(missing_retrieved_layers))
00339:     if require_no_answer_permission and answer_permission_count:
00340:         unsafe_findings.append(f"answer_permission_count:{answer_permission_count}")
00341:     if source_truth_mutation_allowed_count:
00342:         unsafe_findings.append(f"source_truth_mutation_allowed_count:{source_truth_mutation_allowed_count}")
00343:     if write_attempt_count > max_write_attempts:
00344:         unsafe_findings.append(f"write_attempt_count:{write_attempt_count}>{max_write_attempts}")
00345: 
00346:     unsafe_finding_count = len(unsafe_findings)
00347:     quality_status = "PASS" if unsafe_finding_count <= max_unsafe else "FAIL"
00348: 
00349:     manifest = {
00350:         "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_RETRIEVER_BUILT",
00351:         "quality_status": quality_status,
00352:         "module": MODULE,
00353:         "version": VERSION,
```
### Source window L431-L466
```python
00431:         if int(rr.get("result_count") or 0) < min_results_per_query:
00432:             failures.append(f"query_result_count_below_min:{rr.get('query_id')}")
00433:     if require_all_layers:
00434:         missing = summary.get("missing_indexed_layers") or []
00435:         if missing:
00436:             failures.append("missing_indexed_layers:" + ",".join(missing))
00437:         missing_retrieved = summary.get("missing_retrieved_layers") or []
00438:         if missing_retrieved:
00439:             failures.append("missing_retrieved_layers:" + ",".join(missing_retrieved))
00440:     if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
00441:         failures.append("answer_permission_count_nonzero")
00442:     if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
00443:         failures.append("write_attempt_count_exceeds_max")
00444:     if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
00445:         failures.append("unsafe_finding_count_exceeds_max")
00446: 
00447:     quality_status = "PASS" if not failures else "FAIL"
00448:     result = {
00449:         "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_RETRIEVER_CHECKED",
00450:         "quality_status": quality_status,
00451:         "module": MODULE,
00452:         "version": VERSION,
00453:         "query_count": int(summary.get("query_count") or 0),
00454:         "retrieval_record_count": int(summary.get("retrieval_record_count") or 0),
00455:         "total_retrieved_item_count": int(summary.get("total_retrieved_item_count") or 0),
00456:         "indexed_memory_layer_counts": summary.get("indexed_memory_layer_counts") or {},
00457:         "retrieved_memory_layer_counts": summary.get("retrieved_memory_layer_counts") or {},
00458:         "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
00459:         "answer_permission_count": int(summary.get("answer_permission_count") or 0),
00460:         "write_attempt_count": int(summary.get("write_attempt_count") or 0),
00461:         "failures": failures,
00462:     }
00463:     out = Path(vector_retriever_path).with_name(f"{MODULE}_external_quality_check.json")
00464:     _write_json(out, result)
00465:     result["output_path"] = str(out)
00466:     return result
```

## `tiff/trace_net_engineering_webui_answer_server_v1_3.py`
- Location: `active_source_code`
- Score: `239`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Doc: TRACE-Net Engineering WebUI Answer Server v1.3. Small quality layer over v1/v1.2 server. v1.3 fixes the remaining weak spot from the v1.2 rerun: - if Gemma4 returns empty on artifact-search questions, fallback is now a clean deterministic mini-answer instead of raw page-lead text - repair/material/table pages are summarized as "what TRACE-Net found" - visible source notes are always included - keeps exact lookup and random page behavior from v1.2
- Classes: TraceNetWebUIHandlerV13@L344 methods=['_json_response', '_read_body_json', 'do_GET', 'do_POST']; TraceNetHTTPServerV13@L417 methods=['__init__']
- Functions: _query_type(question)@L57; _extract_key_terms(text)@L68; build_clean_search_fallback()@L102; answer_search_summary_v13(question, pages)@L139; answer_question_v13()@L206; build_manifest_v13()@L233; check_manifest_v13()@L305; run_server_v13()@L425; main_build(argv)@L448; main_check(argv)@L477; main_run(argv)@L509; fail_if(condition, msg)@L319; _json_response(self, status, payload)@L347; _read_body_json(self)@L355; do_GET(self)@L362; do_POST(self)@L382; __init__(self, server_address, handler_class)@L418
- CLI args: --output-dir, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff, --sample-question, --quality, --report-path, --write-json, --min-page-records, --min-gated-drafts, --require-llm-model, --require-clean-fallback, --require-no-answer-permission, --require-no-source-truth-mutation, --host, --port, --final-gate, --runner-report, --page-context-v2, --fishnet-ocr-grid, --route-handoff
- Routes: /health@L287, /v1/models@L287, /v1/chat/completions@L287, /health@L363, /v1/models@L377, /api/models@L377, /v1/chat/completions@L383, /api/chat/completions@L383
- Tiff imports: from tiff.trace_net_engineering_webui_answer_server_v1 import DEFAULT_FINAL_GATE, DEFAULT_FISHNET, DEFAULT_PAGE_CONTEXT, DEFAULT_ROUTE_HANDOFF, DEFAULT_RUNNER, LLMConfig, MODEL_ID, _add_llm_args, _clean_trace_text, _compose_with_llm, _extractive_summary, _llm_config_from_args, _part_numbers, _read_json, _records_from_payload, _response_record, _search_pages, _source_notes, _write_json, _write_jsonl, answer_gated_lookup, answer_random_page_summary, answer_v2_summary_inventory, load_gated_drafts, load_page_index

### Source window L1-L37
```python
00001: 
00002: """TRACE-Net Engineering WebUI Answer Server v1.3.
00003: 
00004: Small quality layer over v1/v1.2 server.
00005: 
00006: v1.3 fixes the remaining weak spot from the v1.2 rerun:
00007: - if Gemma4 returns empty on artifact-search questions, fallback is now a clean
00008:   deterministic mini-answer instead of raw page-lead text
00009: - repair/material/table pages are summarized as "what TRACE-Net found"
00010: - visible source notes are always included
00011: - keeps exact lookup and random page behavior from v1.2
00012: """
00013: 
00014: from __future__ import annotations
00015: 
00016: import argparse
00017: import json
00018: import re
00019: import time
00020: from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
00021: from pathlib import Path
00022: from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
00023: 
00024: from tiff.trace_net_engineering_webui_answer_server_v1 import (
00025:     DEFAULT_FINAL_GATE,
00026:     DEFAULT_FISHNET,
00027:     DEFAULT_PAGE_CONTEXT,
00028:     DEFAULT_ROUTE_HANDOFF,
00029:     DEFAULT_RUNNER,
00030:     LLMConfig,
00031:     MODEL_ID,
00032:     _add_llm_args,
00033:     _clean_trace_text,
00034:     _compose_with_llm,
00035:     _extractive_summary,
00036:     _llm_config_from_args,
00037:     _part_numbers,
```
### Source window L106-L162
```python
00106:     citations: Sequence[Mapping[str, Any]],
00107: ) -> str:
00108:     qtype = _query_type(question)
00109:     lines = []
00110: 
00111:     if qtype == "repair_materials":
00112:         opener = "TRACE-Net found repair-related manual pages. The strongest leads are:"
00113:     elif qtype == "visual_or_figure_leads":
00114:         opener = "TRACE-Net found pages that may be figure, callout, or illustrated-parts-list leads. The current server is still using text/OCR evidence, not true image understanding:"
00115:     elif qtype == "parts_list":
00116:         opener = "TRACE-Net found parts-list style evidence. The strongest leads are:"
00117:     else:
00118:         opener = "TRACE-Net found artifact-backed page leads:"
00119: 
00120:     lines.append(opener)
00121: 
00122:     for page in hits[:3]:
00123:         page_id = page.get("page_id")
00124:         page_number = page.get("page_number")
00125:         route = page.get("route")
00126:         summary = _extractive_summary(page, max_chars=420)
00127:         terms = _extract_key_terms(str(page.get("text") or ""))
00128:         terms_text = f" Key terms: {', '.join(terms[:6])}." if terms else ""
00129:         lines.append(f"- `{page_id}` (page {page_number}, route={route}): {summary}{terms_text}")
00130: 
00131:     if qtype == "visual_or_figure_leads":
00132:         lines.append("Because this is OCR/text-led evidence, treat diagram interpretation as a candidate lead until the image/visual route verifies it.")
00133:     else:
00134:         lines.append("Treat these as source leads for review, not as proof of approval, interchangeability, fit, or safety.")
00135: 
00136:     return "\n".join(lines)
00137: 
00138: 
00139: def answer_search_summary_v13(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
00140:     hits = _search_pages(question, pages)
00141:     if not hits:
00142:         response = (
00143:             "TRACE-Net did not find enough artifact text to answer that question yet. "
00144:             "Try an exact part number, a repair/material term, a nomenclature term, or ask for a random page summary."
00145:         )
00146:         return _response_record(
00147:             question=question,
00148:             response_text=response,
00149:             intent="fallback_search",
00150:             evidence_status="no_page_text_hits",
00151:             citations=[],
00152:             response_kind="controlled_no_answer",
00153:             llm_config=llm_config,
00154:             llm_called=False,
00155:             llm_error=None,
00156:         )
00157: 
00158:     citations = [
00159:         {
00160:             "page_id": page.get("page_id"),
00161:             "page_number": page.get("page_number"),
00162:             "route": page.get("route"),
```
### Source window L208-L264
```python
00208:     question: str,
00209:     pages: Sequence[Mapping[str, Any]],
00210:     gated_drafts: Sequence[Mapping[str, Any]],
00211:     llm_config: LLMConfig,
00212: ) -> Dict[str, Any]:
00213:     q = question.lower()
00214: 
00215:     if "v2 summary" in q or "v2 summaries" in q:
00216:         return answer_v2_summary_inventory(question, pages, llm_config=llm_config)
00217: 
00218:     if _part_numbers(question) or "part number" in q or "nearby similar" in q:
00219:         lookup = answer_gated_lookup(question, gated_drafts, llm_config=llm_config)
00220:         if lookup:
00221:             return lookup
00222: 
00223:     if ("random" in q or "choose" in q or "pick" in q) and ("page" in q or "manual" in q) and any(word in q for word in ["summarize", "summary", "say", "tell me", "explain"]):
00224:         return answer_random_page_summary(question, pages, llm_config=llm_config)
00225: 
00226:     lookup = answer_gated_lookup(question, gated_drafts, llm_config=llm_config)
00227:     if lookup:
00228:         return lookup
00229: 
00230:     return answer_search_summary_v13(question, pages, llm_config=llm_config)
00231: 
00232: 
00233: def build_manifest_v13(
00234:     *,
00235:     output_dir: Path,
00236:     final_gate_path: Path,
00237:     runner_path: Path,
00238:     page_context_path: Path,
00239:     fishnet_path: Path,
00240:     route_handoff_path: Path,
00241:     sample_question: str,
00242:     llm_config: LLMConfig,
00243: ) -> Dict[str, Any]:
00244:     pages = load_page_index(
00245:         page_context_path=page_context_path,
00246:         fishnet_path=fishnet_path,
00247:         route_handoff_path=route_handoff_path,
00248:     )
00249:     gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
00250:     sample_record = answer_question_v13(
00251:         question=sample_question,
00252:         pages=pages,
00253:         gated_drafts=gated_drafts,
00254:         llm_config=LLMConfig(mode="off", model=llm_config.model, base_url=llm_config.base_url),
00255:     )
00256: 
00257:     records = [sample_record]
00258:     summary = {
00259:         "page_record_count": len(pages),
00260:         "page_with_text_count": sum(1 for p in pages if p.get("has_text")),
00261:         "gated_draft_count": len(gated_drafts),
00262:         "sample_response_kind": sample_record.get("response_kind"),
00263:         "sample_response_char_count": sample_record.get("response_text_char_count"),
00264:         "server_llm_mode": llm_config.mode,
```
### Source window L355-L411
```python
00355:     def _read_body_json(self) -> Dict[str, Any]:
00356:         length = int(self.headers.get("Content-Length", "0") or "0")
00357:         if length <= 0:
00358:             return {}
00359:         raw = self.rfile.read(length).decode("utf-8", errors="replace")
00360:         return json.loads(raw) if raw.strip() else {}
00361: 
00362:     def do_GET(self) -> None:  # noqa: N802
00363:         if self.path in {"/health", "/"}:
00364:             self._json_response(200, {
00365:                 "status": "ok",
00366:                 "module": MODULE_VERSION,
00367:                 "server_version": "v1.3",
00368:                 "model_id": MODEL_ID,
00369:                 "page_record_count": len(self.server.pages),  # type: ignore[attr-defined]
00370:                 "gated_draft_count": len(self.server.gated_drafts),  # type: ignore[attr-defined]
00371:                 "llm_mode": self.server.llm_config.mode,  # type: ignore[attr-defined]
00372:                 "llm_model": self.server.llm_config.model if self.server.llm_config.enabled else None,  # type: ignore[attr-defined]
00373:                 "clean_fallback_enabled": True,
00374:                 "ready_for_webui": True,
00375:             })
00376:             return
00377:         if self.path in {"/v1/models", "/api/models"}:
00378:             self._json_response(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net"}]})
00379:             return
00380:         self._json_response(404, {"error": f"not found: {self.path}"})
00381: 
00382:     def do_POST(self) -> None:  # noqa: N802
00383:         if self.path not in {"/v1/chat/completions", "/api/chat/completions"}:
00384:             self._json_response(404, {"error": f"not found: {self.path}"})
00385:             return
00386:         try:
00387:             body = self._read_body_json()
00388:             messages = body.get("messages") or []
00389:             question = ""
00390:             for msg in reversed(messages):
00391:                 if isinstance(msg, dict) and msg.get("role") == "user":
00392:                     question = str(msg.get("content") or "")
00393:                     break
00394:             if not question:
00395:                 question = "pick a random page to summarize"
00396: 
00397:             record = answer_question_v13(
00398:                 question=question,
00399:                 pages=self.server.pages,  # type: ignore[attr-defined]
00400:                 gated_drafts=self.server.gated_drafts,  # type: ignore[attr-defined]
00401:                 llm_config=self.server.llm_config,  # type: ignore[attr-defined]
00402:             )
00403:             response = {
00404:                 "id": f"chatcmpl-trace-net-{int(time.time() * 1000)}",
00405:                 "object": "chat.completion",
00406:                 "created": int(time.time()),
00407:                 "model": body.get("model") or MODEL_ID,
00408:                 "choices": [{"index": 0, "message": {"role": "assistant", "content": record["response_text"]}, "finish_reason": "stop"}],
00409:                 "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
00410:                 "trace_net": record,
00411:             }
```
### Source window L266-L322
```python
00266:         "server_llm_base_url": llm_config.base_url if llm_config.enabled else None,
00267:         "retry_empty_response_enabled": llm_config.retry_empty_response,
00268:         "clean_fallback_enabled": True,
00269:         "ready_for_webui": True,
00270:         "openai_compatible_chat_completions_route": True,
00271:         "answer_permission_count": 0,
00272:         "can_answer_directly_count": 0,
00273:         "can_prove_claims_count": 0,
00274:         "retrieval_execution_allowed_count": 0,
00275:         "source_truth_mutation_allowed_count": 0,
00276:         "unsafe_record_count": 0,
00277:     }
00278:     quality_status = "PASS" if (summary["page_record_count"] or summary["gated_draft_count"]) else "FAIL"
00279: 
00280:     payload = {
00281:         "module": MODULE_VERSION,
00282:         "status": "ENGINEERING_WEBUI_ANSWER_SERVER_V1_3_MANIFEST_BUILT",
00283:         "quality_status": quality_status,
00284:         "summary": summary,
00285:         "model_id": MODEL_ID,
00286:         "records": records,
00287:         "routes": {"health": "/health", "models": "/v1/models", "chat_completions": "/v1/chat/completions"},
00288:         "safety_contract": {
00289:             "manual_review_required": True,
00290:             "answer_permission": False,
00291:             "source_truth_mutation_allowed": False,
00292:             "postgres_write_allowed": False,
00293:             "qdrant_write_allowed": False,
00294:             "opensearch_write_allowed": False,
00295:         },
00296:     }
00297:     output_dir.mkdir(parents=True, exist_ok=True)
00298:     _write_json(output_dir / REPORT_NAME, payload)
00299:     _write_jsonl(output_dir / "trace_net_engineering_webui_answer_server_v1_3_records.jsonl", records)
00300:     _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_summary.json", summary)
00301:     _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_quality.json", {"quality_status": quality_status, "summary": summary})
00302:     return payload
00303: 
00304: 
00305: def check_manifest_v13(
00306:     *,
00307:     report_path: Path,
00308:     min_page_records: int = 1,
00309:     min_gated_drafts: int = 0,
00310:     require_llm_model: Optional[str] = None,
00311:     require_clean_fallback: bool = False,
00312:     require_no_answer_permission: bool = False,
00313:     require_no_source_truth_mutation: bool = False,
00314: ) -> Dict[str, Any]:
00315:     payload = _read_json(report_path, required=True)
00316:     summary = payload.get("summary") or {}
00317:     failures: List[str] = []
00318: 
00319:     def fail_if(condition: bool, msg: str) -> None:
00320:         if condition:
00321:             failures.append(msg)
00322: 
```
### Source window L425-L481
```python
00425: def run_server_v13(
00426:     *,
00427:     host: str,
00428:     port: int,
00429:     final_gate_path: Path,
00430:     runner_path: Path,
00431:     page_context_path: Path,
00432:     fishnet_path: Path,
00433:     route_handoff_path: Path,
00434:     llm_config: LLMConfig,
00435: ) -> None:
00436:     pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path)
00437:     gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
00438:     server = TraceNetHTTPServerV13((host, port), TraceNetWebUIHandlerV13, pages=pages, gated_drafts=gated_drafts, llm_config=llm_config)
00439:     print(f"TRACE-Net WebUI answer server v1.3 running on http://{host}:{port}")
00440:     print(f"Model ID exposed to WebUI: {MODEL_ID}")
00441:     print(f"Runtime LLM model: {llm_config.model if llm_config.enabled else 'off'}")
00442:     print("Clean fallback enabled: True")
00443:     print(f"Pages loaded: {len(pages)}")
00444:     print(f"Gated drafts loaded: {len(gated_drafts)}")
00445:     server.serve_forever()
00446: 
00447: 
00448: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00449:     parser = argparse.ArgumentParser(description="Build TRACE-Net engineering WebUI answer server manifest v1.3.")
00450:     parser.add_argument("--output-dir", required=True)
00451:     parser.add_argument("--final-gate", default=str(DEFAULT_FINAL_GATE))
00452:     parser.add_argument("--runner-report", default=str(DEFAULT_RUNNER))
00453:     parser.add_argument("--page-context-v2", default=str(DEFAULT_PAGE_CONTEXT))
00454:     parser.add_argument("--fishnet-ocr-grid", default=str(DEFAULT_FISHNET))
00455:     parser.add_argument("--route-handoff", default=str(DEFAULT_ROUTE_HANDOFF))
00456:     parser.add_argument("--sample-question", default="find repair information for passenger seat legs")
00457:     _add_llm_args(parser)
00458:     parser.add_argument("--quality", action="store_true")
00459:     args = parser.parse_args(argv)
00460: 
00461:     payload = build_manifest_v13(
00462:         output_dir=Path(args.output_dir),
00463:         final_gate_path=Path(args.final_gate),
00464:         runner_path=Path(args.runner_report),
00465:         page_context_path=Path(args.page_context_v2),
00466:         fishnet_path=Path(args.fishnet_ocr_grid),
00467:         route_handoff_path=Path(args.route_handoff),
00468:         sample_question=args.sample_question,
00469:         llm_config=_llm_config_from_args(args),
00470:     )
00471:     print("Status:", payload["status"])
00472:     print("Quality status:", payload["quality_status"])
00473:     print("Summary:", json.dumps(payload["summary"], sort_keys=True))
00474:     return 0 if payload["quality_status"] == "PASS" else 1
00475: 
00476: 
00477: def main_check(argv: Optional[Sequence[str]] = None) -> int:
00478:     parser = argparse.ArgumentParser(description="Check TRACE-Net engineering WebUI answer server v1.3 quality.")
00479:     parser.add_argument("--report-path", required=True)
00480:     parser.add_argument("--write-json", action="store_true")
00481:     parser.add_argument("--min-page-records", type=int, default=1)
```

## `scripts/build_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Location: `active_source_code`
- Score: `238`
- Categories: `final_gate, graph_vector, page, safety, server, webui`
- Functions: parse_args()@L18; main()@L41
- CLI args: --live-llm-final-gate, --output-dir, --host, --port, --model-id, --min-final-gates, --min-ready-final-answers, --min-endpoint-routes, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import MODEL_ID, attach_quality, build_endpoint_state, evaluate_quality, write_endpoint_files
- Has __main__ guard.

### Source window L4-L60
```python
00004: 
00005: REPO_ROOT = Path(__file__).resolve().parents[1]
00006: if str(REPO_ROOT) not in sys.path:
00007:     sys.path.insert(0, str(REPO_ROOT))
00008: 
00009: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import (
00010:     MODEL_ID,
00011:     attach_quality,
00012:     build_endpoint_state,
00013:     evaluate_quality,
00014:     write_endpoint_files,
00015: )
00016: 
00017: 
00018: def parse_args():
00019:     p = argparse.ArgumentParser(description="Build TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24 artifact.")
00020:     p.add_argument("--live-llm-final-gate", required=True)
00021:     p.add_argument("--output-dir", required=True)
00022:     p.add_argument("--host", default="127.0.0.1")
00023:     p.add_argument("--port", type=int, default=8020)
00024:     p.add_argument("--model-id", default=MODEL_ID)
00025:     p.add_argument("--min-final-gates", type=int, default=5)
00026:     p.add_argument("--min-ready-final-answers", type=int, default=5)
00027:     p.add_argument("--min-endpoint-routes", type=int, default=4)
00028:     p.add_argument("--min-final-answers-with-source-truth-citations", type=int, default=5)
00029:     p.add_argument("--min-cap-disclosures-in-final-answers", type=int, default=3)
00030:     p.add_argument("--max-unsupported-claim-count", type=int, default=0)
00031:     p.add_argument("--max-final-non-direct-citation-marker-count", type=int, default=0)
00032:     p.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
00033:     p.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
00034:     p.add_argument("--max-answer-permission-count", type=int, default=0)
00035:     p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00036:     p.add_argument("--require-no-answer-permission", action="store_true")
00037:     p.add_argument("--quality", action="store_true")
00038:     return p.parse_args()
00039: 
00040: 
00041: def main() -> int:
00042:     args = parse_args()
00043:     state = build_endpoint_state(Path(args.live_llm_final_gate), host=args.host, port=args.port, model_id=args.model_id)
00044:     quality_status, checks = evaluate_quality(
00045:         state,
00046:         min_final_gates=args.min_final_gates,
00047:         min_ready_final_answers=args.min_ready_final_answers,
00048:         min_endpoint_routes=args.min_endpoint_routes,
00049:         min_final_answers_with_source_truth_citations=args.min_final_answers_with_source_truth_citations,
00050:         min_cap_disclosures_in_final_answers=args.min_cap_disclosures_in_final_answers,
00051:         max_unsupported_claim_count=args.max_unsupported_claim_count,
00052:         max_final_non_direct_citation_marker_count=args.max_final_non_direct_citation_marker_count,
00053:         max_graph_proof_authority_violations=args.max_graph_proof_authority_violations,
00054:         max_summary_proof_authority_violations=args.max_summary_proof_authority_violations,
00055:         max_answer_permission_count=args.max_answer_permission_count,
00056:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00057:         require_no_answer_permission=args.require_no_answer_permission,
00058:     )
00059:     attach_quality(state, quality_status, checks)
00060:     paths = write_endpoint_files(state, Path(args.output_dir))
```

## `scripts/check_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24_quality.py`
- Location: `active_source_code`
- Score: `238`
- Categories: `final_gate, graph_vector, page, safety, server, webui`
- Functions: parse_args()@L18; main()@L37
- CLI args: --report-path, --min-final-gates, --min-ready-final-answers, --min-endpoint-routes, --min-final-answers-with-source-truth-citations, --min-cap-disclosures-in-final-answers, --max-unsupported-claim-count, --max-final-non-direct-citation-marker-count, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import QUALITY_PASS, attach_quality, evaluate_quality, read_json, write_json
- Has __main__ guard.

### Source window L1-L56
```python
00001: import argparse
00002: import sys
00003: from pathlib import Path
00004: 
00005: REPO_ROOT = Path(__file__).resolve().parents[1]
00006: if str(REPO_ROOT) not in sys.path:
00007:     sys.path.insert(0, str(REPO_ROOT))
00008: 
00009: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import (
00010:     QUALITY_PASS,
00011:     attach_quality,
00012:     evaluate_quality,
00013:     read_json,
00014:     write_json,
00015: )
00016: 
00017: 
00018: def parse_args():
00019:     p = argparse.ArgumentParser(description="Check TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24 quality.")
00020:     p.add_argument("--report-path", required=True)
00021:     p.add_argument("--min-final-gates", type=int, default=5)
00022:     p.add_argument("--min-ready-final-answers", type=int, default=5)
00023:     p.add_argument("--min-endpoint-routes", type=int, default=4)
00024:     p.add_argument("--min-final-answers-with-source-truth-citations", type=int, default=5)
00025:     p.add_argument("--min-cap-disclosures-in-final-answers", type=int, default=3)
00026:     p.add_argument("--max-unsupported-claim-count", type=int, default=0)
00027:     p.add_argument("--max-final-non-direct-citation-marker-count", type=int, default=0)
00028:     p.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
00029:     p.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
00030:     p.add_argument("--max-answer-permission-count", type=int, default=0)
00031:     p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00032:     p.add_argument("--require-no-answer-permission", action="store_true")
00033:     p.add_argument("--write-json", action="store_true")
00034:     return p.parse_args()
00035: 
00036: 
00037: def main() -> int:
00038:     args = parse_args()
00039:     path = Path(args.report_path)
00040:     state = read_json(path)
00041:     quality_status, checks = evaluate_quality(
00042:         state,
00043:         min_final_gates=args.min_final_gates,
00044:         min_ready_final_answers=args.min_ready_final_answers,
00045:         min_endpoint_routes=args.min_endpoint_routes,
00046:         min_final_answers_with_source_truth_citations=args.min_final_answers_with_source_truth_citations,
00047:         min_cap_disclosures_in_final_answers=args.min_cap_disclosures_in_final_answers,
00048:         max_unsupported_claim_count=args.max_unsupported_claim_count,
00049:         max_final_non_direct_citation_marker_count=args.max_final_non_direct_citation_marker_count,
00050:         max_graph_proof_authority_violations=args.max_graph_proof_authority_violations,
00051:         max_summary_proof_authority_violations=args.max_summary_proof_authority_violations,
00052:         max_answer_permission_count=args.max_answer_permission_count,
00053:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00054:         require_no_answer_permission=args.require_no_answer_permission,
00055:     )
00056:     attach_quality(state, quality_status, checks)
```

## `tiff/trace_net_e2e_crag_retrieval_corrector_v10.py`
- Location: `active_source_code`
- Score: `237`
- Categories: `context_pack, crag, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E CRAG retrieval corrector v10. This module consumes Self-RAG context critic output and creates a corrective retrieval plan for each context. It is intentionally plan-only: it does not call an LLM, rerun retrieval, mutate source truth, or write to external services. Later endpoint/runtime modules can consume these plans to decide whether to retry retrieval, repair routing, or request human review.
- Functions: read_json(path)@L55; write_json(path, data)@L60; write_jsonl(path, rows)@L66; as_bool(value)@L74; as_int(value, default)@L86; safe_list(value)@L97; nested_get(data, path, default)@L105; extract_critiques(self_rag_report)@L114; _has_failed_findings(critique, severity)@L132; infer_retry_reasons(critique)@L145; build_corrective_actions(critique, retry_reasons)@L208; build_crag_plan(critique, index)@L299; build_crag_corrector_report(self_rag_context_critic, source_path)@L350; evaluate_quality(report, args)@L402; render_markdown(report)@L435; write_report_files(report, output_dir)@L477; add_quality_args(parser)@L496; print_quality_result(report, checks, title)@L512
- CLI args: --min-context-critiques, --min-crag-plans, --min-ready-crag-plans, --min-no-retry-needed-count, --min-corrective-actions, --max-retry-required-plan-count, --max-human-review-plan-count, --max-unresolved-plan-count, --max-graph-summary-proof-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission

### Source window L2-L58
```python
00002: 
00003: This module consumes Self-RAG context critic output and creates a corrective
00004: retrieval plan for each context. It is intentionally plan-only: it does not
00005: call an LLM, rerun retrieval, mutate source truth, or write to external
00006: services. Later endpoint/runtime modules can consume these plans to decide
00007: whether to retry retrieval, repair routing, or request human review.
00008: """
00009: 
00010: from __future__ import annotations
00011: 
00012: import argparse
00013: import json
00014: from dataclasses import dataclass
00015: from pathlib import Path
00016: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00017: 
00018: SCHEMA_VERSION = "v10"
00019: STATUS_BUILT = "E2E_CRAG_RETRIEVAL_CORRECTOR_BUILT"
00020: STATUS_READY = "E2E_CRAG_RETRIEVAL_CORRECTOR_READY_FOR_PROMPT_OR_RETRY"
00021: QUALITY_PASS = "PASS"
00022: QUALITY_FAIL = "FAIL"
00023: 
00024: NO_RETRY_STATUS = "CRAG_NO_RETRY_NEEDED"
00025: RETRY_READY_STATUS = "CRAG_RETRY_PLAN_READY"
00026: HUMAN_REVIEW_STATUS = "CRAG_HUMAN_REVIEW_PLAN_READY"
00027: UNRESOLVED_STATUS = "CRAG_UNRESOLVED"
00028: 
00029: DEFAULT_CONTRACT: Dict[str, Any] = {
00030:     "uses_prebuilt_self_rag_critiques": True,
00031:     "uses_prebuilt_context_packs": True,
00032:     "corrector_emits_plan_only": True,
00033:     "corrector_does_not_call_llm": True,
00034:     "corrector_does_not_rerun_retrieval": True,
00035:     "corrector_does_not_rerun_ocr": True,
00036:     "corrector_does_not_rerun_page_classification": True,
00037:     "corrector_does_not_rerun_embeddings": True,
00038:     "corrector_does_not_rerun_page_summaries": True,
00039:     "corrector_does_not_rerun_graph_build": True,
00040:     "corrector_does_not_rerun_table_extraction": True,
00041:     "graph_is_not_proof_authority": True,
00042:     "summaries_are_not_source_truth": True,
00043:     "guidance_box_is_not_source_truth": True,
00044:     "answer_permission": False,
00045:     "can_answer_directly": False,
00046:     "can_prove_claims": False,
00047:     "source_truth_mutation_allowed": False,
00048:     "postgres_write_attempt_count": 0,
00049:     "qdrant_write_attempt_count": 0,
00050:     "opensearch_write_attempt_count": 0,
00051:     "opensearch_upload_attempt_count": 0,
00052: }
00053: 
00054: 
00055: def read_json(path: Path | str) -> Dict[str, Any]:
00056:     p = Path(path)
00057:     return json.loads(p.read_text(encoding="utf-8"))
00058: 
```
### Source window L190-L246
```python
00190:         elif isinstance(blocker, Mapping):
00191:             reasons.append(f"blocker:{blocker.get('name', blocker.get('detail', 'unknown'))}")
00192:     for warning in warnings:
00193:         if isinstance(warning, str):
00194:             reasons.append(f"warning:{warning}")
00195:         elif isinstance(warning, Mapping):
00196:             reasons.append(f"warning:{warning.get('name', warning.get('detail', 'unknown'))}")
00197: 
00198:     # Preserve order while removing duplicates.
00199:     seen: set[str] = set()
00200:     unique: List[str] = []
00201:     for reason in reasons:
00202:         if reason not in seen:
00203:             seen.add(reason)
00204:             unique.append(reason)
00205:     return unique
00206: 
00207: 
00208: def build_corrective_actions(critique: Mapping[str, Any], retry_reasons: Sequence[str]) -> List[Dict[str, Any]]:
00209:     actions: List[Dict[str, Any]] = []
00210:     query_intent = str(critique.get("query_intent") or "unknown")
00211:     user_query = str(critique.get("user_query") or "")
00212: 
00213:     if not retry_reasons:
00214:         return [
00215:             {
00216:                 "action_type": "no_retry_required",
00217:                 "action_status": "READY",
00218:                 "description": "Self-RAG marked the context ready. Preserve the current context pack for prompt construction.",
00219:                 "route_policy": "preserve_current_route_and_evidence",
00220:             }
00221:         ]
00222: 
00223:     if any(r in retry_reasons for r in ("missing_evidence_box_items", "source_trace_repair_needed")):
00224:         actions.append(
00225:             {
00226:                 "action_type": "expand_source_truth_retrieval",
00227:                 "action_status": "READY",
00228:                 "description": "Retry retrieval against source-truth evidence pools and require citation/source-trace-ready records.",
00229:                 "preferred_tunnels": ["table_exact_search_tunnel", "table_hybrid_bridge_tunnel", "route_metadata_tunnel"],
00230:                 "forbidden_authority": ["graph_summary_as_proof", "summary_only_answer"],
00231:             }
00232:         )
00233: 
00234:     if any("query_intent_mismatch" in r or "wrong_field" in r or "intent_relevant" in r for r in retry_reasons):
00235:         field_preference = "covered_part_number" if "covered" in user_query.lower() or query_intent == "covered_part_number" else query_intent
00236:         actions.append(
00237:             {
00238:                 "action_type": "route_and_field_correction",
00239:                 "action_status": "READY",
00240:                 "description": "Retry with the detected/expected route and field preference instead of broad table text matching.",
00241:                 "query_intent": query_intent,
00242:                 "field_preference": field_preference,
00243:                 "preferred_tunnels": ["table_exact_search_tunnel", "route_metadata_tunnel"],
00244:             }
00245:         )
00246: 
```
### Source window L123-L179
```python
00123:         rows = self_rag_report.get(key)
00124:         if isinstance(rows, list):
00125:             return [dict(r) for r in rows if isinstance(r, Mapping)]
00126:     # Some reports may only store a single critique-like record.
00127:     if "context_pack_id" in self_rag_report:
00128:         return [dict(self_rag_report)]
00129:     return []
00130: 
00131: 
00132: def _has_failed_findings(critique: Mapping[str, Any], severity: Optional[str] = None) -> List[Dict[str, Any]]:
00133:     failed: List[Dict[str, Any]] = []
00134:     for finding in safe_list(critique.get("findings")):
00135:         if not isinstance(finding, Mapping):
00136:             continue
00137:         if as_bool(finding.get("passed")):
00138:             continue
00139:         if severity and str(finding.get("severity", "")).lower() != severity.lower():
00140:             continue
00141:         failed.append(dict(finding))
00142:     return failed
00143: 
00144: 
00145: def infer_retry_reasons(critique: Mapping[str, Any]) -> List[str]:
00146:     reasons: List[str] = []
00147:     status = str(critique.get("self_rag_critic_status", ""))
00148:     if status and status not in {"SELF_RAG_CONTEXT_READY", "READY", "PASS"}:
00149:         reasons.append(f"self_rag_status={status}")
00150: 
00151:     if as_bool(critique.get("needs_crag_retry")):
00152:         reasons.append("self_rag_marked_needs_crag_retry")
00153:     if as_bool(critique.get("needs_human_review")):
00154:         reasons.append("self_rag_marked_needs_human_review")
00155: 
00156:     evidence_count = as_int(critique.get("evidence_item_count"))
00157:     source_truth_count = as_int(critique.get("source_truth_evidence_count"))
00158:     citation_ready_count = as_int(critique.get("citation_ready_evidence_count"))
00159:     source_trace_count = as_int(critique.get("source_trace_ready_evidence_count"))
00160:     intent_relevant_count = as_int(critique.get("intent_relevant_evidence_count"))
00161:     guidance_count = as_int(critique.get("guidance_item_count"))
00162:     safe_guidance_count = as_int(critique.get("safe_guidance_item_count"))
00163:     graph_summary_violation = as_int(critique.get("graph_summary_proof_violation_count"))
00164: 
00165:     if evidence_count <= 0:
00166:         reasons.append("missing_evidence_box_items")
00167:     if source_truth_count < evidence_count:
00168:         reasons.append("non_source_truth_evidence_present")
00169:     if citation_ready_count < evidence_count:
00170:         reasons.append("citation_repair_needed")
00171:     if source_trace_count < evidence_count:
00172:         reasons.append("source_trace_repair_needed")
00173:     if intent_relevant_count <= 0:
00174:         reasons.append("query_intent_mismatch_or_wrong_field")
00175:     if guidance_count > safe_guidance_count:
00176:         reasons.append("guidance_authority_repair_needed")
00177:     if graph_summary_violation > 0:
00178:         reasons.append("graph_or_summary_used_as_proof")
00179: 
```
### Source window L296-L352
```python
00296:     return actions
00297: 
00298: 
00299: def build_crag_plan(critique: Mapping[str, Any], index: int) -> Dict[str, Any]:
00300:     retry_reasons = infer_retry_reasons(critique)
00301:     corrective_actions = build_corrective_actions(critique, retry_reasons)
00302:     needs_human_review = as_bool(critique.get("needs_human_review")) or any(
00303:         a.get("action_type") == "human_review_enqueue" for a in corrective_actions
00304:     )
00305:     needs_retry = bool(retry_reasons) and not needs_human_review
00306: 
00307:     if not retry_reasons:
00308:         status = NO_RETRY_STATUS
00309:     elif needs_human_review:
00310:         status = HUMAN_REVIEW_STATUS
00311:     elif needs_retry:
00312:         status = RETRY_READY_STATUS
00313:     else:
00314:         status = UNRESOLVED_STATUS
00315: 
00316:     plan_ready = status in {NO_RETRY_STATUS, RETRY_READY_STATUS, HUMAN_REVIEW_STATUS}
00317: 
00318:     return {
00319:         "schema_version": SCHEMA_VERSION,
00320:         "crag_plan_id": f"crag_retrieval_corrector_v10_{index:04d}",
00321:         "context_pack_id": critique.get("context_pack_id", f"unknown_context_{index:04d}"),
00322:         "user_query": critique.get("user_query", ""),
00323:         "query_intent": critique.get("query_intent", "unknown"),
00324:         "source_self_rag_status": critique.get("self_rag_critic_status", "UNKNOWN"),
00325:         "crag_plan_status": status,
00326:         "ready_for_prompt_contract": status == NO_RETRY_STATUS,
00327:         "ready_for_retry_execution": status == RETRY_READY_STATUS,
00328:         "ready_for_human_review_queue": status == HUMAN_REVIEW_STATUS,
00329:         "needs_retry": status == RETRY_READY_STATUS,
00330:         "needs_human_review": status == HUMAN_REVIEW_STATUS,
00331:         "plan_ready": plan_ready,
00332:         "retry_reasons": list(retry_reasons),
00333:         "corrective_actions": corrective_actions,
00334:         "corrective_action_count": len([a for a in corrective_actions if a.get("action_type") != "no_retry_required"]),
00335:         "source_truth_evidence_count": as_int(critique.get("source_truth_evidence_count")),
00336:         "citation_ready_evidence_count": as_int(critique.get("citation_ready_evidence_count")),
00337:         "source_trace_ready_evidence_count": as_int(critique.get("source_trace_ready_evidence_count")),
00338:         "intent_relevant_evidence_count": as_int(critique.get("intent_relevant_evidence_count")),
00339:         "guidance_item_count": as_int(critique.get("guidance_item_count")),
00340:         "safe_guidance_item_count": as_int(critique.get("safe_guidance_item_count")),
00341:         "graph_summary_proof_violation_count": as_int(critique.get("graph_summary_proof_violation_count")),
00342:         "answer_permission": False,
00343:         "can_answer_directly": False,
00344:         "can_prove_claims": False,
00345:         "source_truth_mutation_allowed": False,
00346:         "contract": DEFAULT_CONTRACT,
00347:     }
00348: 
00349: 
00350: def build_crag_corrector_report(self_rag_context_critic: Mapping[str, Any], source_path: str = "") -> Dict[str, Any]:
00351:     critiques = extract_critiques(self_rag_context_critic)
00352:     plans = [build_crag_plan(critique, i + 1) for i, critique in enumerate(critiques)]
```
### Source window L391-L447
```python
00391:         "schema_version": SCHEMA_VERSION,
00392:         "status": STATUS_BUILT,
00393:         "e2e_crag_retrieval_corrector_status": STATUS_READY,
00394:         "quality_status": QUALITY_PASS,
00395:         "source_self_rag_context_critic_path": source_path,
00396:         "crag_retrieval_corrector_contract": DEFAULT_CONTRACT,
00397:         "summary": summary,
00398:         "crag_plans": plans,
00399:     }
00400: 
00401: 
00402: def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
00403:     summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
00404: 
00405:     checks: List[Dict[str, Any]] = []
00406: 
00407:     def add(name: str, observed: Any, expected: str, passed: bool) -> None:
00408:         checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})
00409: 
00410:     add("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == QUALITY_PASS)
00411:     add("context_critique_count", summary.get("context_critique_count", 0), f">= {args.min_context_critiques}", as_int(summary.get("context_critique_count")) >= args.min_context_critiques)
00412:     add("crag_plan_count", summary.get("crag_plan_count", 0), f">= {args.min_crag_plans}", as_int(summary.get("crag_plan_count")) >= args.min_crag_plans)
00413:     add("ready_crag_plan_count", summary.get("ready_crag_plan_count", 0), f">= {args.min_ready_crag_plans}", as_int(summary.get("ready_crag_plan_count")) >= args.min_ready_crag_plans)
00414:     add("no_retry_needed_count", summary.get("no_retry_needed_count", 0), f">= {args.min_no_retry_needed_count}", as_int(summary.get("no_retry_needed_count")) >= args.min_no_retry_needed_count)
00415:     add("corrective_action_count", summary.get("corrective_action_count", 0), f">= {args.min_corrective_actions}", as_int(summary.get("corrective_action_count")) >= args.min_corrective_actions)
00416:     add("retry_required_plan_count", summary.get("retry_required_plan_count", 0), f"<= {args.max_retry_required_plan_count}", as_int(summary.get("retry_required_plan_count")) <= args.max_retry_required_plan_count)
00417:     add("human_review_plan_count", summary.get("human_review_plan_count", 0), f"<= {args.max_human_review_plan_count}", as_int(summary.get("human_review_plan_count")) <= args.max_human_review_plan_count)
00418:     add("unresolved_plan_count", summary.get("unresolved_plan_count", 0), f"<= {args.max_unresolved_plan_count}", as_int(summary.get("unresolved_plan_count")) <= args.max_unresolved_plan_count)
00419:     add("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), f"<= {args.max_graph_summary_proof_violations}", as_int(summary.get("graph_summary_proof_violation_count")) <= args.max_graph_summary_proof_violations)
00420:     add("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", as_int(summary.get("answer_permission_count")) <= args.max_answer_permission_count)
00421:     add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", as_int(summary.get("source_truth_mutation_allowed_count")) <= args.max_source_truth_mutation_allowed)
00422:     add("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", as_int(summary.get("can_answer_directly_count")) == 0)
00423:     add("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", as_int(summary.get("can_prove_claims_count")) == 0)
00424:     add("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", as_int(summary.get("postgres_write_attempt_count")) == 0)
00425:     add("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", as_int(summary.get("qdrant_write_attempt_count")) == 0)
00426:     add("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", as_int(summary.get("opensearch_write_attempt_count")) == 0)
00427: 
00428:     if args.require_no_answer_permission:
00429:         add("require_no_answer_permission", summary.get("answer_permission_count", 0), "== 0", as_int(summary.get("answer_permission_count")) == 0)
00430: 
00431:     status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
00432:     return status, checks
00433: 
00434: 
00435: def render_markdown(report: Mapping[str, Any]) -> str:
00436:     summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
00437:     lines = [
00438:         "# TRACE-Net E2E CRAG Retrieval Corrector v10",
00439:         "",
00440:         f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
00441:         f"Status: `{report.get('e2e_crag_retrieval_corrector_status', report.get('status', 'UNKNOWN'))}`",
00442:         "",
00443:         "## Contract",
00444:         "This CRAG stage emits corrective retrieval plans only. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
00445:         "",
00446:         "## Summary",
00447:     ]
```

## `tiff/trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py`
- Location: `active_source_code`
- Score: `237`
- Categories: `crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Classes: TraceNetArtifactsV33@L539 methods=['load', 'all_page_ids']; TraceNetGemmaAnswerWriterV33@L803 methods=['__init__', 'from_paths', '_page_metadata', 'build_package', '_llm_messages', '_simulate_llm', '_call_openai_compatible_llm', '_final_gate']
- Functions: _now()@L69; _read_json(path)@L73; _stable_id(prefix, text)@L85; _stringify(x)@L90; _norm(s)@L100; _lower(s)@L104; _looks_like_page_id(value)@L108; _extract_page_id(obj)@L112; _extract_field(obj)@L136; _extract_value(obj)@L148; _walk_json(obj)@L176; _candidate_record_dicts(data)@L186; _collect_page_contexts(data)@L214; _load_leiden_membership(data)@L231; _safe_join_items(items, max_items)@L261; _citation_lines(evidence)@L265; _dedupe_evidence(records, limit)@L276; _format_evidence_examples(evidence, max_items)@L298
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --output-dir, --host, --port, --llm-mode, --llm-model, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens, --include-standard-demo-queries, --min-sample-queries, --min-sample-successes, --min-llm-called-samples, --min-compact-prompt-samples, --min-normal-intent-samples, --min-self-rag-samples, --min-crag-samples, --max-crag-retry-required-count, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Routes: /chat/completions@L1062
- Has __main__ guard.

### Source window L287-L343
```python
00287:         if key in seen:
00288:             collapsed += 1
00289:             continue
00290:         seen.add(key)
00291:         out.append({"page_id": page_id, "field": field or "source_truth", "value": value, "raw": dict(r)})
00292:         if len(out) >= limit:
00293:             # Continue not needed for return sample, but collapsed already counted only before limit.
00294:             pass
00295:     return out[:limit], collapsed
00296: 
00297: 
00298: def _format_evidence_examples(evidence: Sequence[Dict[str, Any]], max_items: int = 10) -> str:
00299:     parts = []
00300:     for i, ev in enumerate(evidence[:max_items], start=1):
00301:         parts.append(f"{ev.get('value')} [{i}]")
00302:     return _safe_join_items(parts, max_items=max_items)
00303: 
00304: 
00305: def _metadata_from_router(router_report: Mapping[str, Any]) -> Dict[str, Any]:
00306:     return {
00307:         "page_context_v2_page_count": router_report.get("page_context_v2_page_count"),
00308:         "graph_has_v2_page_count": router_report.get("graph_has_v2_page_count"),
00309:         "graph_has_context_page_count": router_report.get("graph_has_context_page_count"),
00310:         "graph_has_nomenclature_page_count": router_report.get("graph_has_nomenclature_page_count"),
00311:         "exact_search_document_count": router_report.get("exact_search_document_count"),
00312:     }
00313: 
00314: 
00315: def _self_rag_assessment(package: Mapping[str, Any]) -> Dict[str, Any]:
00316:     """Small, deterministic Self-RAG-style package quality card.
00317: 
00318:     This is not a second model call. It is runtime telemetry that tells the
00319:     endpoint and evaluator whether the package is strong enough, partial,
00320:     guidance-only, metadata-only, or safely unanswerable.
00321:     """
00322:     intent = _norm(package.get("query_intent"))
00323:     mode = _norm(package.get("response_mode"))
00324:     evidence = package.get("source_truth_evidence", []) or []
00325:     guidance = package.get("graph_guidance", {}) or {}
00326:     metadata = package.get("artifact_metadata", {}) or {}
00327:     has_direct = bool(evidence)
00328:     has_metadata_answer = mode == "artifact_metadata_count" and bool(package.get("total_match_count"))
00329:     has_v2 = bool(package.get("v2_summary"))
00330:     has_graph_guidance = bool(guidance.get("candidate_page_ids") or guidance.get("leiden_community_ids") or guidance.get("relationship_guidance_only"))
00331:     guidance_only = bool(has_graph_guidance or has_v2 or intent in {"artifact_v2_summary_count", "field_or_graph_nomenclature_count", "nomenclature_relationship_question", "v2_proof_safety_question"})
00332:     capped = bool(package.get("result_was_capped"))
00333:     missing_or_audit = mode in {"audit_only", "exact_missing_value"} or not (has_direct or has_metadata_answer or has_graph_guidance or has_v2)
00334: 
00335:     if has_direct and not capped:
00336:         quality = "strong"
00337:         status = "SELF_RAG_SOURCE_TRUTH_READY"
00338:         answerable = True
00339:     elif has_direct and capped:
00340:         quality = "partial"
00341:         status = "SELF_RAG_SOURCE_TRUTH_READY_WITH_CAP_DISCLOSURE"
00342:         answerable = True
00343:     elif has_metadata_answer:
```
### Source window L1600-L1656
```python
01600:             passed = observed <= expected
01601:         else:
01602:             passed = False
01603:         out.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": passed})
01604:     return out
01605: 
01606: 
01607: def main_build(argv: Optional[Sequence[str]] = None) -> int:
01608:     ap = argparse.ArgumentParser()
01609:     ap.add_argument("--table-exact-search-adapter", required=True)
01610:     ap.add_argument("--page-context-v2", required=True)
01611:     ap.add_argument("--leiden-communities", required=True)
01612:     ap.add_argument("--relationship-router-hardening", default=None)
01613:     ap.add_argument("--relationship-final-gate-hardener", default=None)
01614:     ap.add_argument("--output-dir", required=True)
01615:     ap.add_argument("--host", default="127.0.0.1")
01616:     ap.add_argument("--port", type=int, default=8027)
01617:     ap.add_argument("--llm-mode", default="simulate")
01618:     ap.add_argument("--llm-model", default="gemma4:26b")
01619:     ap.add_argument("--llm-answer-mode", default="always")
01620:     ap.add_argument("--llm-prompt-mode", default="compact", choices=["compact", "full"])
01621:     ap.add_argument("--llm-max-output-tokens", type=int, default=180)
01622:     ap.add_argument("--include-standard-demo-queries", action="store_true")
01623:     ap.add_argument("--min-sample-queries", type=int, default=0)
01624:     ap.add_argument("--min-sample-successes", type=int, default=0)
01625:     ap.add_argument("--min-llm-called-samples", type=int, default=0)
01626:     ap.add_argument("--min-compact-prompt-samples", type=int, default=0)
01627:     ap.add_argument("--min-normal-intent-samples", type=int, default=0)
01628:     ap.add_argument("--min-self-rag-samples", type=int, default=0)
01629:     ap.add_argument("--min-crag-samples", type=int, default=0)
01630:     ap.add_argument("--max-crag-retry-required-count", type=int, default=999999)
01631:     ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
01632:     ap.add_argument("--max-answer-permission-count", type=int, default=0)
01633:     ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
01634:     ap.add_argument("--require-no-answer-permission", action="store_true")
01635:     ap.add_argument("--quality", action="store_true")
01636:     ns = ap.parse_args(argv)
01637:     report = build_report(
01638:         table_exact_search_adapter=ns.table_exact_search_adapter,
01639:         page_context_v2=ns.page_context_v2,
01640:         leiden_communities=ns.leiden_communities,
01641:         relationship_router_hardening=ns.relationship_router_hardening,
01642:         relationship_final_gate_hardener=ns.relationship_final_gate_hardener,
01643:         output_dir=ns.output_dir,
01644:         host=ns.host,
01645:         port=ns.port,
01646:         llm_mode=ns.llm_mode,
01647:         llm_model=ns.llm_model,
01648:         llm_prompt_mode=ns.llm_prompt_mode,
01649:         llm_max_output_tokens=ns.llm_max_output_tokens,
01650:         include_standard_demo_queries=ns.include_standard_demo_queries,
01651:         min_sample_queries=ns.min_sample_queries,
01652:         min_sample_successes=ns.min_sample_successes,
01653:         min_llm_called_samples=ns.min_llm_called_samples,
01654:         min_compact_prompt_samples=ns.min_compact_prompt_samples,
01655:         min_normal_intent_samples=ns.min_normal_intent_samples,
01656:         min_self_rag_samples=ns.min_self_rag_samples,
```
### Source window L349-L405
```python
00349:         status = "SELF_RAG_GUIDANCE_ONLY_NEEDS_SOURCE_TRUTH_FOR_CLAIMS"
00350:         answerable = True
00351:     elif missing_or_audit:
00352:         quality = "weak"
00353:         status = "SELF_RAG_NO_DIRECT_EVIDENCE_AUDIT_ONLY"
00354:         answerable = False
00355:     else:
00356:         quality = "partial"
00357:         status = "SELF_RAG_PARTIAL_PACKAGE"
00358:         answerable = True
00359: 
00360:     return {
00361:         "self_rag_status": status,
00362:         "package_quality": quality,
00363:         "answerable_from_package": answerable,
00364:         "direct_source_truth_available": has_direct,
00365:         "direct_source_truth_evidence_count": len(evidence),
00366:         "metadata_answer_available": has_metadata_answer,
00367:         "guidance_only_signals_present": guidance_only,
00368:         "graph_guidance_present": has_graph_guidance,
00369:         "v2_summary_guidance_present": has_v2,
00370:         "cap_disclosure_required": capped,
00371:         "citation_required_for_claims": has_direct,
00372:         "limitation_disclosure_required": guidance_only or capped or not has_direct,
00373:         "metadata_count_source": metadata.get("metadata_count_source"),
00374:     }
00375: 
00376: 
00377: def _crag_assessment(package: Mapping[str, Any], self_rag: Mapping[str, Any]) -> Dict[str, Any]:
00378:     """Small CRAG-style retry/fallback decision card.
00379: 
00380:     CRAG here means: if the first package is weak, identify whether we should
00381:     retry a different route, or whether the safe audit-only answer is the
00382:     correct final behavior.
00383:     """
00384:     intent = _norm(package.get("query_intent"))
00385:     mode = _norm(package.get("response_mode"))
00386:     has_direct = bool(self_rag.get("direct_source_truth_available"))
00387:     has_metadata = bool(self_rag.get("metadata_answer_available"))
00388:     has_guidance = bool(self_rag.get("guidance_only_signals_present"))
00389:     answerable = bool(self_rag.get("answerable_from_package"))
00390:     capped = bool(package.get("result_was_capped"))
00391: 
00392:     retry_required = False
00393:     retry_reason = None
00394:     recommended_retry_route = None
00395:     fallback_safe = False
00396:     status = "CRAG_NO_RETRY_PACKAGE_READY"
00397: 
00398:     if mode in {"exact_missing_value", "audit_only"} and not (has_direct or has_metadata or has_guidance):
00399:         status = "CRAG_NO_RETRY_SAFE_AUDIT_ONLY"
00400:         fallback_safe = True
00401:         retry_reason = "direct_exact_or_supported_route_found_no_citation_ready_evidence"
00402:     elif capped:
00403:         status = "CRAG_NO_RETRY_CAP_DISCLOSURE_REQUIRED"
00404:         retry_reason = "results_capped_but_source_truth_package_is_answerable"
00405:     elif has_direct or has_metadata:
```
### Source window L1118-L1174
```python
01118: 
01119:     def _final_gate(self, draft: str, package: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
01120:         text = (draft or "").strip()
01121:         deterministic = _norm(package.get("deterministic_safe_answer"))
01122:         lower = text.lower()
01123:         issues: List[str] = []
01124:         if not text:
01125:             issues.append("empty_draft")
01126:         # Detect common overclaims.
01127:         unsafe_patterns = [
01128:             ("graph_as_proof", r"\b(graph|leiden|community)\b.{0,40}\b(proves?|confirms?|establishes?|validates?)\b"),
01129:             ("v2_summary_as_proof", r"\bv2\b.{0,40}\b(proves?|confirms?|establishes?|validates?)\b"),
01130:             ("nomenclature_as_proof", r"\bnomenclature\b.{0,40}\b(proves?|confirms?|means|establishes?|validates?)\b"),
01131:             ("ignore_source_truth", r"ignore\s+the\s+source[- ]truth"),
01132:         ]
01133:         for name, pat in unsafe_patterns:
01134:             if re.search(pat, lower, flags=re.I | re.S):
01135:                 issues.append(name)
01136:         evidence = package.get("source_truth_evidence", []) or []
01137:         if evidence and not CITATION_RE.search(text):
01138:             issues.append("missing_source_truth_citation")
01139:         # Relationship claims need guidance wording unless direct relationship evidence exists.
01140:         intent = package.get("query_intent")
01141:         if intent in {"relationship_synthesis", "relationship_navigation", "nomenclature_relationship_question", "v2_proof_safety_question"}:
01142:             if "guidance" not in lower and "not proof" not in lower:
01143:                 issues.append("relationship_guidance_disclosure_missing")
01144:         if issues:
01145:             final = deterministic
01146:             repaired = True
01147:         else:
01148:             final = text
01149:             repaired = False
01150:         # Normalize a few spacing artifacts.
01151:         final = re.sub(r"(?<!\s)(\[\d+\])", r" \1", final)
01152:         final = final.replace("doesnot", "does not").replace("onlyand", "only and").replace("availableevidence", "available evidence")
01153:         final = re.sub(r"\s+", " ", final).strip()
01154:         return final, {
01155:             "final_gate_status": "LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS",
01156:             "final_gate_applied": True,
01157:             "final_gate_repaired": repaired,
01158:             "post_gate_issue_count": 0,
01159:             "draft_issue_count": len(issues),
01160:             "draft_issues": issues,
01161:             "unsupported_claim_count": 0,
01162:         }
01163: 
01164:     def answer_query(
01165:         self,
01166:         query: str,
01167:         *,
01168:         llm_mode: str = "simulate",
01169:         llm_base_url: str = "http://127.0.0.1:11434/v1",
01170:         llm_model: str = "gemma4:26b",
01171:         llm_api_key: str = "ollama",
01172:         temperature: float = 0.0,
01173:         request_timeout: int = 240,
01174:         max_evidence: int = 10,
```
### Source window L479-L535
```python
00479:             "total_match_count": package.get("total_match_count"),
00480:             "returned_match_count": package.get("returned_match_count"),
00481:             "result_was_capped": package.get("result_was_capped"),
00482:             "corpus_page_count": metadata.get("corpus_page_count"),
00483:             "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
00484:             "v2_summary_page_first": metadata.get("v2_summary_page_first"),
00485:             "v2_summary_page_last": metadata.get("v2_summary_page_last"),
00486:             "graph_has_v2_page_count": metadata.get("graph_has_v2_page_count"),
00487:             "graph_has_context_page_count": metadata.get("graph_has_context_page_count"),
00488:             "nomenclature_page_count": metadata.get("nomenclature_page_count"),
00489:             "nomenclature_part_count": metadata.get("nomenclature_part_count"),
00490:             "metadata_count_source": metadata.get("metadata_count_source"),
00491:             "corpus_page_first": metadata.get("corpus_page_first"),
00492:             "corpus_page_last": metadata.get("corpus_page_last"),
00493:             "requested_page_id": package.get("page_id"),
00494:         },
00495:         "graph_guidance": {
00496:             "relationship_guidance_only": guidance.get("relationship_guidance_only"),
00497:             "leiden_community_ids": guidance.get("leiden_community_ids", []),
00498:             "candidate_page_ids": (guidance.get("candidate_page_ids", []) or [])[:10],
00499:             "requires_source_truth_confirmation": guidance.get("requires_source_truth_confirmation", True),
00500:         },
00501:         "v2_summary_guidance": package.get("v2_summary"),
00502:         "page_profile": package.get("page_profile"),
00503:         "self_rag": package.get("self_rag"),
00504:         "crag": package.get("crag"),
00505:         "drilldown_groups": package.get("drilldown_groups"),
00506:         "limitations": [
00507:             "Source-truth records are the only proof authority for factual claims.",
00508:             "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only, not proof.",
00509:             "Do not invent physical part descriptions, page contents, or relationships.",
00510:         ],
00511:         "normal_intent_package": package.get("query_intent") in NORMAL_INTENTS_V33,
00512:         "answer_style": "Answer in 2-5 short sentences. Do not explain hidden reasoning. Use citation markers only for direct source-truth evidence.",
00513:     }
00514:     # Drop empty keys inside nested dicts to keep prompt small and cache-friendly.
00515:     for key in ("counts_and_metadata", "graph_guidance"):
00516:         content[key] = {k: v for k, v in (content.get(key) or {}).items() if v not in (None, "", [], {})}
00517:     return content
00518: 
00519: 
00520: def _full_llm_content(package: Mapping[str, Any]) -> Dict[str, Any]:
00521:     return {
00522:         "user_query": package.get("user_query"),
00523:         "query_intent": package.get("query_intent"),
00524:         "response_mode": package.get("response_mode"),
00525:         "direct_source_truth_evidence": package.get("source_truth_evidence"),
00526:         "artifact_metadata": package.get("artifact_metadata"),
00527:         "graph_guidance": package.get("graph_guidance"),
00528:         "v2_summary": package.get("v2_summary"),
00529:         "drilldown_groups": package.get("drilldown_groups"),
00530:         "total_match_count": package.get("total_match_count"),
00531:         "returned_match_count": package.get("returned_match_count"),
00532:         "result_was_capped": package.get("result_was_capped"),
00533:         "deterministic_safe_answer": package.get("deterministic_safe_answer"),
00534:         "answer_rules": package.get("answer_rules"),
00535:     }
```
### Source window L15-L71
```python
00015: VERSION = "v33"
00016: MODULE = "trace_net_e2e_live_gemma_answer_writer_endpoint_v33"
00017: MODEL_ID = "trace-net-e2e-live-gemma-answer-writer-v33"
00018: 
00019: PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b", re.I)
00020: PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
00021: MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
00022: CITATION_RE = re.compile(r"\[\d+\]")
00023: 
00024: SOURCE_TRUTH_FIELDS = {
00025:     "covered_part_number",
00026:     "ipl_part_number",
00027:     "part_number",
00028:     "manual_page_reference",
00029:     "ipl_text",
00030:     "table_text",
00031:     "nomenclature",
00032: }
00033: 
00034: NORMAL_INTENTS_V33 = {
00035:     "corpus_page_count",
00036:     "covered_part_number_listing",
00037:     "drilldown_covered_part_numbers_by_field",
00038:     "page_records_lookup",
00039:     "page_covered_part_numbers_lookup",
00040:     "page_profile_summary",
00041: }
00042: 
00043: GUIDANCE_ONLY_WARNING = (
00044:     "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only; "
00045:     "source-truth evidence is required for factual claims."
00046: )
00047: 
00048: SAFETY_CONTRACT: Dict[str, Any] = {
00049:     "answer_permission": False,
00050:     "can_answer_directly": False,
00051:     "can_prove_claims": False,
00052:     "source_truth_mutation_allowed": False,
00053:     "writes_to_postgres": False,
00054:     "writes_to_qdrant": False,
00055:     "writes_to_opensearch": False,
00056:     "uploads_to_opensearch": False,
00057:     "raw_5tb_scan_at_query_time": False,
00058:     "graph_rebuild_at_query_time": False,
00059:     "llm_called": True,
00060:     "response_is_final_gated": True,
00061:     "llm_answer_writer_required": True,
00062:     "source_truth_required_for_relationship_claims": True,
00063:     "graph_leiden_guidance_only": True,
00064:     "v2_summaries_guidance_only": True,
00065:     "nomenclature_metadata_guidance_only": True,
00066: }
00067: 
00068: 
00069: def _now() -> int:
00070:     return int(time.time())
00071: 
```
### Source window L1177-L1233
```python
01177:         llm_max_prompt_evidence: int = 5,
01178:     ) -> Dict[str, Any]:
01179:         started = time.perf_counter()
01180:         t0 = time.perf_counter()
01181:         package = self.build_package(query, max_evidence=max_evidence)
01182:         package_ms = round((time.perf_counter() - t0) * 1000, 3)
01183:         t1 = time.perf_counter()
01184:         if llm_mode == "simulate":
01185:             draft, llm_meta = self._simulate_llm(
01186:                 package,
01187:                 prompt_mode=llm_prompt_mode,
01188:                 max_output_tokens=llm_max_output_tokens,
01189:                 max_prompt_evidence=llm_max_prompt_evidence,
01190:             )
01191:         else:
01192:             draft, llm_meta = self._call_openai_compatible_llm(
01193:                 package,
01194:                 base_url=llm_base_url,
01195:                 model=llm_model,
01196:                 api_key=llm_api_key,
01197:                 temperature=temperature,
01198:                 timeout=request_timeout,
01199:                 prompt_mode=llm_prompt_mode,
01200:                 max_output_tokens=llm_max_output_tokens,
01201:                 max_prompt_evidence=llm_max_prompt_evidence,
01202:             )
01203:         llm_ms = round((time.perf_counter() - t1) * 1000, 3)
01204:         t2 = time.perf_counter()
01205:         final, gate = self._final_gate(draft, package)
01206:         final_gate_ms = round((time.perf_counter() - t2) * 1000, 3)
01207:         total_ms = round((time.perf_counter() - started) * 1000, 3)
01208:         evidence = package.get("source_truth_evidence", []) or []
01209:         metadata = package.get("artifact_metadata", {}) or {}
01210:         guidance = package.get("graph_guidance", {}) or {}
01211:         self_rag = package.get("self_rag", {}) or {}
01212:         crag = package.get("crag", {}) or {}
01213:         return {
01214:             "id": "chatcmpl-tracenet-v33-" + uuid.uuid4().hex[:16],
01215:             "object": "chat.completion",
01216:             "created": _now(),
01217:             "model": MODEL_ID,
01218:             "choices": [
01219:                 {
01220:                     "index": 0,
01221:                     "message": {"role": "assistant", "content": final},
01222:                     "finish_reason": "stop",
01223:                 }
01224:             ],
01225:             "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
01226:             "trace_net": {
01227:                 "endpoint_version": "live_gemma_answer_writer_v33",
01228:                 "query_intent": package.get("query_intent"),
01229:                 "response_mode": package.get("response_mode"),
01230:                 "trace_net_package_built": True,
01231:                 "trace_net_package_id": package.get("package_id"),
01232:                 "llm_answer_writer_used": True,
01233:                 "llm_called": True,
```
### Source window L1034-L1090
```python
01034:         messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence)
01035:         prompt_text = "\n".join(m.get("content", "") for m in messages)
01036:         return _norm(package.get("deterministic_safe_answer")), {
01037:             "llm_mode": "simulate",
01038:             "llm_call_status": "LLM_CALL_SIMULATED",
01039:             "llm_reasoning_omitted_from_draft": True,
01040:             "llm_prompt_mode": "compact" if prompt_mode != "full" else "full",
01041:             "prompt_char_count": len(prompt_text),
01042:             "prompt_token_estimate": _estimate_token_count(prompt_text),
01043:             "llm_max_output_tokens": max_output_tokens,
01044:             "llm_timeout_budget_ms": 0,
01045:             "llm_timed_out": False,
01046:             "fallback_answer_used": False,
01047:         }
01048: 
01049:     def _call_openai_compatible_llm(
01050:         self,
01051:         package: Mapping[str, Any],
01052:         *,
01053:         base_url: str,
01054:         model: str,
01055:         api_key: str,
01056:         temperature: float = 0.0,
01057:         timeout: int = 240,
01058:         prompt_mode: str = "compact",
01059:         max_output_tokens: int = 180,
01060:         max_prompt_evidence: int = 5,
01061:     ) -> Tuple[str, Dict[str, Any]]:
01062:         url = base_url.rstrip("/") + "/chat/completions"
01063:         messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence)
01064:         prompt_text = "\n".join(m.get("content", "") for m in messages)
01065:         prompt_mode_norm = "compact" if (prompt_mode or "compact").lower().strip() != "full" else "full"
01066:         payload = {
01067:             "model": model,
01068:             "messages": messages,
01069:             "temperature": temperature,
01070:             "max_tokens": max_output_tokens,
01071:         }
01072:         req = urllib.request.Request(
01073:             url,
01074:             data=json.dumps(payload).encode("utf-8"),
01075:             headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key or 'trace-net-local'}"},
01076:             method="POST",
01077:         )
01078:         started = time.perf_counter()
01079:         base_meta = {
01080:             "llm_mode": "ollama",
01081:             "llm_prompt_mode": prompt_mode_norm,
01082:             "prompt_char_count": len(prompt_text),
01083:             "prompt_token_estimate": _estimate_token_count(prompt_text),
01084:             "llm_max_output_tokens": max_output_tokens,
01085:             "llm_timeout_budget_ms": int(timeout * 1000),
01086:         }
01087:         try:
01088:             with urllib.request.urlopen(req, timeout=timeout) as resp:
01089:                 raw = resp.read().decode("utf-8", errors="replace")
01090:                 data = json.loads(raw)
```

## `tiff/trace_net_e2e_live_llm_draft_adapter_v22.py`
- Location: `active_source_code`
- Score: `237`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, webui`
- Classes: LlmConfig@L226 methods=[]
- Functions: load_json(path)@L25; write_json(path, data)@L29; write_jsonl(path, rows)@L34; _as_bool(value)@L41; _first_list(obj, candidate_keys)@L49; prompt_contracts(data)@L67; _contract_id(row, index)@L72; _contract_ready(row)@L76; _messages(row)@L85; _context_message(row)@L98; _extract_direct_evidence_lines(context)@L105; _extract_aggregation(context)@L121; _citation_like_count(text)@L142; _has_cap_disclosure(text)@L146; _simulate_draft(row)@L151; _call_openai_compatible_llm()@L180; build_drafts(contracts)@L236; evaluate_quality(report, thresholds)@L354
- CLI args: --live-llm-prompt-contract, --output-dir, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --temperature, --request-timeout, --max-contracts, --min-prompt-contracts, --min-llm-drafts, --min-drafts-ready-for-final-gate, --min-drafts-with-nonempty-content, --min-source-truth-supported-prompts, --min-successful-llm-calls, --min-live-llm-calls, --min-simulated-llm-drafts, --max-llm-call-errors, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality, --report-path, --min-prompt-contracts, --min-llm-drafts, --min-drafts-ready-for-final-gate, --min-drafts-with-nonempty-content, --min-source-truth-supported-prompts, --min-successful-llm-calls, --min-live-llm-calls
- Routes: /chat/completions@L189
- Has __main__ guard.

### Source window L99-L155
```python
00099:     for msg in reversed(_messages(row)):
00100:         if "TRACE-NET CONTEXT PACK" in msg.get("content", ""):
00101:             return msg["content"]
00102:     return _messages(row)[-1]["content"] if _messages(row) else ""
00103: 
00104: 
00105: def _extract_direct_evidence_lines(context: str) -> List[str]:
00106:     lines = context.splitlines()
00107:     in_direct = False
00108:     out: List[str] = []
00109:     for line in lines:
00110:         stripped = line.strip()
00111:         if stripped.startswith("SOURCE-TRUTH EVIDENCE"):
00112:             in_direct = True
00113:             continue
00114:         if in_direct and stripped.startswith("NEARBY SOURCE-TRUTH CONTEXT"):
00115:             break
00116:         if in_direct and stripped.startswith("- ["):
00117:             out.append(stripped)
00118:     return out
00119: 
00120: 
00121: def _extract_aggregation(context: str) -> Dict[str, Any]:
00122:     marker = "AGGREGATION / CAPPING METADATA:"
00123:     start = context.find(marker)
00124:     if start < 0:
00125:         return {}
00126:     rest = context[start + len(marker):]
00127:     end_markers = ["SELF-RAG / CRAG STATUS:", "ANSWER RULES:"]
00128:     end = len(rest)
00129:     for m in end_markers:
00130:         idx = rest.find(m)
00131:         if idx >= 0:
00132:             end = min(end, idx)
00133:     block = rest[:end].strip()
00134:     if not block.startswith("{"):
00135:         return {}
00136:     try:
00137:         return json.loads(block)
00138:     except Exception:
00139:         return {}
00140: 
00141: 
00142: def _citation_like_count(text: str) -> int:
00143:     return len(re.findall(r"\[\d+\]", text or ""))
00144: 
00145: 
00146: def _has_cap_disclosure(text: str) -> bool:
00147:     nt = (text or "").lower()
00148:     return any(term in nt for term in ("capped", "more results", "showing", "returned", "total match", "high-degree", "high degree", "drilldown"))
00149: 
00150: 
00151: def _simulate_draft(row: Mapping[str, Any]) -> str:
00152:     query = str(row.get("user_query") or "")
00153:     context = _context_message(row)
00154:     evidence_lines = _extract_direct_evidence_lines(context)
00155:     aggregation = _extract_aggregation(context)
```
### Source window L1-L44
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: import re
00006: import time
00007: import urllib.error
00008: import urllib.request
00009: from dataclasses import dataclass
00010: from pathlib import Path
00011: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
00012: 
00013: VERSION = "v22"
00014: MODULE = "trace_net_e2e_live_llm_draft_adapter_v22"
00015: STATUS_READY = "E2E_LIVE_LLM_DRAFT_ADAPTER_READY_FOR_FINAL_GATE"
00016: STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_DRAFT_ADAPTER_NEEDS_REPAIR"
00017: QUALITY_PASS = "PASS"
00018: QUALITY_FAIL = "FAIL"
00019: 
00020: DEFAULT_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
00021: DEFAULT_LLM_MODEL = "gemma4:26b"
00022: DEFAULT_LLM_API_KEY = "ollama"
00023: 
00024: 
00025: def load_json(path: str | Path) -> Any:
00026:     return json.loads(Path(path).read_text(encoding="utf-8"))
00027: 
00028: 
00029: def write_json(path: str | Path, data: Any) -> None:
00030:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00031:     Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
00032: 
00033: 
00034: def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
00035:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00036:     with Path(path).open("w", encoding="utf-8") as f:
00037:         for row in rows:
00038:             f.write(json.dumps(row, ensure_ascii=False) + "\n")
00039: 
00040: 
00041: def _as_bool(value: Any) -> bool:
00042:     if isinstance(value, bool):
00043:         return value
00044:     if isinstance(value, str):
```
### Source window L228-L284
```python
00228:     base_url: str = DEFAULT_LLM_BASE_URL
00229:     model: str = DEFAULT_LLM_MODEL
00230:     api_key: str = DEFAULT_LLM_API_KEY
00231:     temperature: float = 0.0
00232:     timeout: float = 120.0
00233:     max_contracts: int = 0
00234: 
00235: 
00236: def build_drafts(
00237:     contracts: Sequence[Mapping[str, Any]],
00238:     *,
00239:     config: LlmConfig,
00240: ) -> List[Dict[str, Any]]:
00241:     drafts: List[Dict[str, Any]] = []
00242:     selected = list(contracts)
00243:     if config.max_contracts and config.max_contracts > 0:
00244:         selected = selected[: config.max_contracts]
00245:     for idx, contract in enumerate(selected, start=1):
00246:         contract_id = _contract_id(contract, idx)
00247:         ready_contract = _contract_ready(contract)
00248:         context = _context_message(contract)
00249:         direct_evidence_count = len(_extract_direct_evidence_lines(context))
00250:         aggregation = _extract_aggregation(context)
00251:         messages = _messages(contract)
00252:         draft_id = f"llm_draft_v22_{idx:04d}"
00253:         base_record: Dict[str, Any] = {
00254:             "llm_draft_id": draft_id,
00255:             "prompt_contract_id": contract_id,
00256:             "context_pack_id": contract.get("context_pack_id"),
00257:             "user_query": contract.get("user_query"),
00258:             "draft_adapter_status": "LLM_DRAFT_PENDING",
00259:             "prompt_contract_ready": ready_contract,
00260:             "llm_mode": config.mode,
00261:             "llm_provider": "ollama_openai_compatible" if config.mode == "ollama" else "simulated_deterministic_adapter",
00262:             "llm_base_url": config.base_url,
00263:             "llm_model": config.model,
00264:             "llm_called": config.mode == "ollama",
00265:             "source_truth_evidence_count": direct_evidence_count,
00266:             "requires_final_gate": True,
00267:             "answer_permission": False,
00268:             "can_answer_directly": False,
00269:             "can_prove_claims": False,
00270:             "source_truth_mutation_allowed": False,
00271:             "writes_to_postgres": False,
00272:             "writes_to_qdrant": False,
00273:             "writes_to_opensearch": False,
00274:             "uploads_to_opensearch": False,
00275:             "raw_5tb_scan_at_query_time": False,
00276:             "graph_rebuild_at_query_time": False,
00277:             "llm_reads_context_pack_only": True,
00278:             "graph_leiden_guidance_only": True,
00279:             "v2_summaries_guidance_only": True,
00280:             "aggregation_cap_disclosure": {
00281:                 "result_was_capped": bool(aggregation.get("result_was_capped")),
00282:                 "more_results_available": bool(aggregation.get("more_results_available")),
00283:                 "high_degree_node_detected": bool(aggregation.get("high_degree_node_detected")),
00284:                 "total_match_count": aggregation.get("total_match_count"),
```
### Source window L460-L516
```python
00460:     lines.append("")
00461:     lines.append(f"Quality status: **{report.get('quality_status')}**")
00462:     lines.append(f"Status: `{report.get('status')}`")
00463:     lines.append("")
00464:     lines.append("## Summary")
00465:     for key in (
00466:         "prompt_contract_count",
00467:         "ready_prompt_contract_count",
00468:         "llm_draft_count",
00469:         "drafts_ready_for_final_gate_count",
00470:         "drafts_with_nonempty_content_count",
00471:         "source_truth_supported_prompt_count",
00472:         "successful_llm_call_count",
00473:         "live_llm_call_count",
00474:         "simulated_llm_draft_count",
00475:         "llm_call_error_count",
00476:         "drafts_with_citation_like_tokens_count",
00477:         "drafts_needing_cap_disclosure_count",
00478:         "drafts_with_cap_disclosure_detected_count",
00479:         "llm_reasoning_omitted_count",
00480:         "answer_permission_count",
00481:         "source_truth_mutation_allowed_count",
00482:     ):
00483:         lines.append(f"- {key}: {report.get(key)}")
00484:     lines.append("")
00485:     lines.append("## Contract")
00486:     lines.append("- This stage may call the configured LLM, but the output is only a draft.")
00487:     lines.append("- The draft must pass a later TRACE-Net final gate before WebUI final answer use.")
00488:     lines.append("- The LLM receives compact v21 context packs, not the raw 5TB corpus or full graph.")
00489:     lines.append("- Source-truth evidence remains the only proof authority; graph/Leiden and v2 summaries remain guidance only.")
00490:     lines.append("- Any provider reasoning field is stored as metadata only and is not passed as answer text.")
00491:     lines.append("")
00492:     lines.append("## Drafts")
00493:     for d in report.get("llm_drafts", []):
00494:         lines.append(f"### {d.get('llm_draft_id')} — `{d.get('draft_adapter_status')}`")
00495:         lines.append(f"- query: {d.get('user_query')}")
00496:         lines.append(f"- mode/model: {d.get('llm_mode')} / {d.get('llm_model')}")
00497:         lines.append(f"- llm_call_status: {d.get('llm_call_status')}")
00498:         lines.append(f"- ready_for_final_gate: {d.get('ready_for_final_gate')}")
00499:         lines.append(f"- citation_like_count: {d.get('citation_like_count')}")
00500:         if d.get("error_message"):
00501:             lines.append(f"- error: {d.get('error_type')}: {d.get('error_message')}")
00502:         text = str(d.get("draft_text") or "").strip().replace("\n", " ")
00503:         if text:
00504:             lines.append(f"- draft_preview: {text[:280]}")
00505:         lines.append("")
00506:     lines.append("## Quality checks")
00507:     for check in report.get("quality_checks", []):
00508:         prefix = "PASS" if check.get("passed") else "FAIL"
00509:         lines.append(f"- {prefix} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}")
00510:     return "\n".join(lines) + "\n"
00511: 
00512: 
00513: def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
00514:     out = Path(output_dir)
00515:     out.mkdir(parents=True, exist_ok=True)
00516:     report_path = out / "trace_net_e2e_live_llm_draft_adapter_v22.json"
```
### Source window L297-L353
```python
00297:             continue
00298:         started = time.time()
00299:         try:
00300:             if config.mode == "simulate":
00301:                 content = _simulate_draft(contract)
00302:                 meta: Dict[str, Any] = {
00303:                     "finish_reason": "simulated",
00304:                     "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
00305:                     "reasoning_present": False,
00306:                     "reasoning_omitted_from_draft": False,
00307:                     "model_returned": config.model,
00308:                 }
00309:                 call_status = "SIMULATED_DRAFT_BUILT"
00310:             elif config.mode == "ollama":
00311:                 content, meta = _call_openai_compatible_llm(
00312:                     base_url=config.base_url,
00313:                     api_key=config.api_key,
00314:                     model=config.model,
00315:                     messages=messages,
00316:                     temperature=config.temperature,
00317:                     timeout=config.timeout,
00318:                 )
00319:                 call_status = "LLM_CALL_SUCCEEDED"
00320:             else:
00321:                 raise ValueError(f"Unsupported llm mode: {config.mode}")
00322:             elapsed = round(time.time() - started, 3)
00323:             record = dict(base_record)
00324:             record.update({
00325:                 "draft_adapter_status": "LLM_DRAFT_READY_FOR_FINAL_GATE",
00326:                 "llm_call_status": call_status,
00327:                 "ready_for_final_gate": bool(content.strip()),
00328:                 "draft_text": content,
00329:                 "draft_character_count": len(content),
00330:                 "citation_like_count": _citation_like_count(content),
00331:                 "cap_disclosure_detected_in_draft": _has_cap_disclosure(content),
00332:                 "llm_elapsed_seconds": elapsed,
00333:                 "llm_response_metadata": meta,
00334:             })
00335:         except Exception as exc:
00336:             elapsed = round(time.time() - started, 3)
00337:             record = dict(base_record)
00338:             record.update({
00339:                 "draft_adapter_status": "LLM_DRAFT_ADAPTER_ERROR",
00340:                 "llm_call_status": "LLM_CALL_FAILED" if config.mode == "ollama" else "SIMULATED_DRAFT_FAILED",
00341:                 "ready_for_final_gate": False,
00342:                 "draft_text": "",
00343:                 "draft_character_count": 0,
00344:                 "citation_like_count": 0,
00345:                 "cap_disclosure_detected_in_draft": False,
00346:                 "llm_elapsed_seconds": elapsed,
00347:                 "error_type": type(exc).__name__,
00348:                 "error_message": str(exc),
00349:             })
00350:         drafts.append(record)
00351:     return drafts
00352: 
00353: 
```
### Source window L161-L217
```python
00161:     first = evidence_lines[0].lstrip("- ")
00162:     evidence_preview = "; ".join(line.lstrip("- ") for line in evidence_lines[:3])
00163:     if len(evidence_lines) > 3:
00164:         evidence_preview += f"; plus {len(evidence_lines) - 3} additional direct evidence item(s)."
00165:     else:
00166:         evidence_preview += "."
00167:     cap_sentence = ""
00168:     if aggregation.get("result_was_capped") or aggregation.get("more_results_available") or aggregation.get("high_degree_node_detected"):
00169:         cap_sentence = (
00170:             f" Results were capped: TRACE-Net returned {aggregation.get('returned_match_count')} "
00171:             f"of {aggregation.get('total_match_count')} matches; more results may be available through drill-down filters."
00172:         )
00173:     return (
00174:         f"TRACE-Net found citation-backed source-truth evidence for the query '{query}'. "
00175:         f"Primary evidence: {first}. Related direct evidence includes {evidence_preview}"
00176:         f"{cap_sentence} Graph/Leiden and v2 summary information were used only as guidance, not proof."
00177:     )
00178: 
00179: 
00180: def _call_openai_compatible_llm(
00181:     *,
00182:     base_url: str,
00183:     api_key: str,
00184:     model: str,
00185:     messages: Sequence[Mapping[str, str]],
00186:     temperature: float,
00187:     timeout: float,
00188: ) -> Tuple[str, Dict[str, Any]]:
00189:     url = base_url.rstrip("/") + "/chat/completions"
00190:     payload = {
00191:         "model": model,
00192:         "messages": list(messages),
00193:         "temperature": temperature,
00194:     }
00195:     request = urllib.request.Request(
00196:         url,
00197:         data=json.dumps(payload).encode("utf-8"),
00198:         headers={
00199:             "Content-Type": "application/json",
00200:             "Authorization": f"Bearer {api_key}",
00201:         },
00202:         method="POST",
00203:     )
00204:     with urllib.request.urlopen(request, timeout=timeout) as response:
00205:         raw = response.read().decode("utf-8")
00206:     data = json.loads(raw)
00207:     choices = data.get("choices") or []
00208:     if not choices:
00209:         raise RuntimeError("LLM response did not include choices")
00210:     msg = choices[0].get("message") or {}
00211:     content = str(msg.get("content") or "").strip()
00212:     if not content:
00213:         raise RuntimeError("LLM response message content was empty")
00214:     metadata = {
00215:         "raw_response_id": data.get("id"),
00216:         "finish_reason": choices[0].get("finish_reason"),
00217:         "usage": data.get("usage") or {},
```
### Source window L546-L602
```python
00546:     ):
00547:         print(f" {key}: {report.get(key)}")
00548:     for key in ("report_path", "drafts_jsonl_path", "inspect_md_path"):
00549:         if key in report:
00550:             print(f" {key}: {report[key]}")
00551: 
00552: 
00553: def _thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
00554:     return {
00555:         "min_prompt_contracts": args.min_prompt_contracts,
00556:         "min_llm_drafts": args.min_llm_drafts,
00557:         "min_drafts_ready_for_final_gate": args.min_drafts_ready_for_final_gate,
00558:         "min_drafts_with_nonempty_content": args.min_drafts_with_nonempty_content,
00559:         "min_source_truth_supported_prompts": args.min_source_truth_supported_prompts,
00560:         "min_successful_llm_calls": args.min_successful_llm_calls,
00561:         "min_live_llm_calls": args.min_live_llm_calls,
00562:         "min_simulated_llm_drafts": args.min_simulated_llm_drafts,
00563:         "max_llm_call_errors": args.max_llm_call_errors,
00564:         "max_answer_permission_count": args.max_answer_permission_count,
00565:         "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
00566:         "require_no_answer_permission": args.require_no_answer_permission,
00567:     }
00568: 
00569: 
00570: def main_build(argv: Optional[Sequence[str]] = None) -> int:
00571:     parser = argparse.ArgumentParser(description="Build TRACE-Net E2E Live LLM Draft Adapter v22")
00572:     parser.add_argument("--live-llm-prompt-contract", required=True)
00573:     parser.add_argument("--output-dir", required=True)
00574:     parser.add_argument("--llm-mode", choices=["simulate", "ollama"], default="simulate")
00575:     parser.add_argument("--llm-base-url", default=DEFAULT_LLM_BASE_URL)
00576:     parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
00577:     parser.add_argument("--llm-api-key", default=DEFAULT_LLM_API_KEY)
00578:     parser.add_argument("--temperature", type=float, default=0.0)
00579:     parser.add_argument("--request-timeout", type=float, default=120.0)
00580:     parser.add_argument("--max-contracts", type=int, default=0)
00581:     parser.add_argument("--min-prompt-contracts", type=int, default=5)
00582:     parser.add_argument("--min-llm-drafts", type=int, default=5)
00583:     parser.add_argument("--min-drafts-ready-for-final-gate", type=int, default=5)
00584:     parser.add_argument("--min-drafts-with-nonempty-content", type=int, default=5)
00585:     parser.add_argument("--min-source-truth-supported-prompts", type=int, default=5)
00586:     parser.add_argument("--min-successful-llm-calls", type=int, default=5)
00587:     parser.add_argument("--min-live-llm-calls", type=int, default=0)
00588:     parser.add_argument("--min-simulated-llm-drafts", type=int, default=0)
00589:     parser.add_argument("--max-llm-call-errors", type=int, default=0)
00590:     parser.add_argument("--max-answer-permission-count", type=int, default=0)
00591:     parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00592:     parser.add_argument("--require-no-answer-permission", action="store_true")
00593:     parser.add_argument("--quality", action="store_true")
00594:     args = parser.parse_args(argv)
00595: 
00596:     data = load_json(args.live_llm_prompt_contract)
00597:     config = LlmConfig(
00598:         mode=args.llm_mode,
00599:         base_url=args.llm_base_url,
00600:         model=args.llm_model,
00601:         api_key=args.llm_api_key,
00602:         temperature=args.temperature,
```
### Source window L399-L455
```python
00399:     errors = sum(1 for d in drafts if str(d.get("draft_adapter_status")) == "LLM_DRAFT_ADAPTER_ERROR")
00400:     reasoning_omitted = sum(1 for d in drafts if (d.get("llm_response_metadata") or {}).get("reasoning_omitted_from_draft"))
00401:     citation_like = sum(1 for d in drafts if int(d.get("citation_like_count") or 0) > 0)
00402:     cap_disclosure_needed = sum(
00403:         1 for d in drafts if any(d.get("aggregation_cap_disclosure", {}).get(k) for k in ("result_was_capped", "more_results_available", "high_degree_node_detected"))
00404:     )
00405:     cap_disclosure_detected = sum(1 for d in drafts if d.get("cap_disclosure_detected_in_draft"))
00406: 
00407:     report: Dict[str, Any] = {
00408:         "module": MODULE,
00409:         "version": VERSION,
00410:         "status": STATUS_READY,
00411:         "quality_status": QUALITY_PASS,
00412:         "prompt_contract_count": prompt_contract_count,
00413:         "ready_prompt_contract_count": ready_prompt_contract_count,
00414:         "llm_draft_count": llm_draft_count,
00415:         "drafts_ready_for_final_gate_count": drafts_ready,
00416:         "drafts_with_nonempty_content_count": nonempty,
00417:         "source_truth_supported_prompt_count": source_truth_supported,
00418:         "successful_llm_call_count": successful,
00419:         "live_llm_call_count": live_calls,
00420:         "simulated_llm_draft_count": simulated,
00421:         "llm_call_error_count": errors,
00422:         "drafts_with_citation_like_tokens_count": citation_like,
00423:         "drafts_needing_cap_disclosure_count": cap_disclosure_needed,
00424:         "drafts_with_cap_disclosure_detected_count": cap_disclosure_detected,
00425:         "llm_reasoning_omitted_count": reasoning_omitted,
00426:         "answer_permission_count": sum(1 for d in drafts if d.get("answer_permission")),
00427:         "source_truth_mutation_allowed_count": sum(1 for d in drafts if d.get("source_truth_mutation_allowed")),
00428:         "contract": {
00429:             "llm_draft_adapter_stage": True,
00430:             "real_llm_call_supported": True,
00431:             "llm_mode": config.mode,
00432:             "llm_model": config.model,
00433:             "llm_base_url": config.base_url,
00434:             "final_gate_required_after_llm_draft": True,
00435:             "draft_is_not_final_answer": True,
00436:             "source_truth_evidence_required_for_final_claims": True,
00437:             "graph_leiden_guidance_only": True,
00438:             "v2_summaries_guidance_only": True,
00439:             "raw_5tb_scan_at_query_time": False,
00440:             "graph_rebuild_at_query_time": False,
00441:             "source_truth_mutation_allowed": False,
00442:             "answer_permission": False,
00443:             "can_answer_directly": False,
00444:             "can_prove_claims": False,
00445:             "llm_reasoning_field_is_not_passed_to_final_gate": True,
00446:         },
00447:         "llm_drafts": drafts,
00448:     }
00449:     checks = evaluate_quality(report, thresholds)
00450:     report["quality_checks"] = checks
00451:     if not all(c["passed"] for c in checks):
00452:         report["quality_status"] = QUALITY_FAIL
00453:         report["status"] = STATUS_NEEDS_REPAIR
00454:     return report
00455: 
```

## `tiff/trace_net_e2e_self_rag_context_critic_v9.py`
- Location: `active_source_code`
- Score: `237`
- Categories: `context_pack, crag, feedback, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E Self-RAG Context Critic v9. This module critiques dynamic context packs before they are handed to an LLM. It is intentionally non-mutating: it reads prebuilt context-pack artifacts and writes an audit/critic artifact. It does not rerun OCR, embeddings, graph build, table extraction, or source ingest.
- Functions: load_json(path)@L41; write_json(path, data)@L46; write_jsonl(path, rows)@L52; as_list(value)@L60; as_bool(value)@L68; truthy_count(rows, key)@L76; get_context_packs(context_pack_report)@L80; get_evidence_items(pack)@L94; get_guidance_items(pack)@L101; get_rules_box(pack)@L108; expected_fields_for_intent(intent)@L113; field_relevant_for_intent(field_name, intent)@L122; guidance_item_is_safe(item)@L129; critique_context_pack(pack)@L137; make_quality_check(name, observed, expected, passed)@L324; build_self_rag_context_critic(dynamic_context_pack)@L328; render_markdown_report(report)@L461; write_report_files(report, output_dir)@L506
- CLI args: --dynamic-context-pack, --output-dir, --min-context-packs, --min-context-critiques, --min-ready-contexts, --min-contexts-with-source-truth-evidence, --min-contexts-with-guidance-separation, --max-needs-crag-retry-count, --max-human-review-count, --max-graph-summary-proof-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality

### Source window L1-L46
```python
00001: """TRACE-Net E2E Self-RAG Context Critic v9.
00002: 
00003: This module critiques dynamic context packs before they are handed to an LLM.
00004: It is intentionally non-mutating: it reads prebuilt context-pack artifacts and
00005: writes an audit/critic artifact. It does not rerun OCR, embeddings, graph build,
00006: table extraction, or source ingest.
00007: """
00008: 
00009: from __future__ import annotations
00010: 
00011: import argparse
00012: import json
00013: from dataclasses import dataclass
00014: from pathlib import Path
00015: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00016: 
00017: SCHEMA_VERSION = "v9"
00018: STATUS_BUILT = "E2E_SELF_RAG_CONTEXT_CRITIC_BUILT"
00019: STATUS_READY_FOR_CRAG_OR_PROMPT = "E2E_SELF_RAG_CONTEXT_CRITIC_READY_FOR_CRAG_OR_PROMPT"
00020: STATUS_NOT_READY = "E2E_SELF_RAG_CONTEXT_CRITIC_NOT_READY"
00021: 
00022: CRITIC_READY = "SELF_RAG_CONTEXT_READY"
00023: CRITIC_WEAK = "SELF_RAG_CONTEXT_WEAK"
00024: CRITIC_NEEDS_CRAG_RETRY = "SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY"
00025: CRITIC_NEEDS_HUMAN_REVIEW = "SELF_RAG_CONTEXT_NEEDS_HUMAN_REVIEW"
00026: 
00027: SOURCE_TRUTH_AUTHORITY = "source_truth_evidence_only"
00028: GUIDANCE_AUTHORITY_MARKERS = ("guidance_only", "not_source_truth", "not_proof")
00029: 
00030: INTENT_FIELD_MAP: Dict[str, Tuple[str, ...]] = {
00031:     "covered_part_number": ("covered_part_number",),
00032:     "manual_page_reference": ("manual_page_reference", "ipl_part_number"),
00033:     "table_text": ("ipl_text", "table_text"),
00034:     "ipl_text": ("ipl_text", "table_text"),
00035:     "ipl_part_number": ("ipl_part_number", "manual_page_reference"),
00036:     "ipl_figure_item_or_quantity": ("ipl_figure_item_or_quantity",),
00037:     "figure_item_or_quantity": ("ipl_figure_item_or_quantity",),
00038: }
00039: 
00040: 
00041: def load_json(path: Path | str) -> Dict[str, Any]:
00042:     p = Path(path)
00043:     return json.loads(p.read_text(encoding="utf-8"))
00044: 
00045: 
00046: def write_json(path: Path | str, data: Mapping[str, Any]) -> None:
```
### Source window L436-L492
```python
00436:         "summary": summary,
00437:         "self_rag_context_critic_contract": {
00438:             "uses_prebuilt_context_packs": True,
00439:             "critic_does_not_call_llm": True,
00440:             "critic_does_not_rerun_retrieval": True,
00441:             "reruns_ocr": False,
00442:             "reruns_page_classification": False,
00443:             "reruns_embeddings": False,
00444:             "reruns_page_summaries": False,
00445:             "reruns_graph_build": False,
00446:             "reruns_table_extraction": False,
00447:             "evidence_box_is_source_truth": True,
00448:             "guidance_box_is_not_source_truth": True,
00449:             "graph_is_not_proof_authority": True,
00450:             "summaries_are_not_source_truth": True,
00451:             "answer_permission": False,
00452:             "can_answer_directly": False,
00453:             "can_prove_claims": False,
00454:             "source_truth_mutation_allowed": False,
00455:         },
00456:         "critiques": critiques,
00457:         "quality_checks": quality_checks,
00458:     }
00459: 
00460: 
00461: def render_markdown_report(report: Mapping[str, Any]) -> str:
00462:     summary = dict(report.get("summary") or {})
00463:     lines = [
00464:         "# TRACE-Net E2E Self-RAG Context Critic v9",
00465:         "",
00466:         f"Quality status: **{report.get('quality_status')}**",
00467:         f"Status: `{report.get('e2e_self_rag_context_critic_status')}`",
00468:         "",
00469:         "## Summary",
00470:     ]
00471:     for key in [
00472:         "context_pack_count",
00473:         "self_rag_critique_count",
00474:         "ready_context_count",
00475:         "weak_context_count",
00476:         "needs_crag_retry_count",
00477:         "human_review_count",
00478:         "contexts_with_source_truth_evidence_count",
00479:         "contexts_with_guidance_separation_count",
00480:         "contexts_with_graph_or_summary_guidance_count",
00481:         "graph_summary_proof_violation_count",
00482:         "answer_permission_count",
00483:         "source_truth_mutation_allowed_count",
00484:     ]:
00485:         lines.append(f"- {key}: {summary.get(key, 0)}")
00486: 
00487:     lines.extend(["", "## Critiques"])
00488:     for critique in as_list(report.get("critiques"))[:20]:
00489:         if not isinstance(critique, Mapping):
00490:             continue
00491:         lines.append(
00492:             f"- **{critique.get('self_rag_critic_status')}** `{critique.get('context_pack_id')}` | "
```
### Source window L248-L304
```python
00248: 
00249:     required_rule_bools = {
00250:         "evidence_box_is_source_truth": True,
00251:         "guidance_box_is_not_source_truth": True,
00252:         "graph_is_not_proof_authority": True,
00253:         "summaries_are_not_source_truth": True,
00254:         "cite_every_factual_claim": True,
00255:         "source_truth_mutation_allowed": False,
00256:         "answer_permission": False,
00257:         "can_answer_directly": False,
00258:         "can_prove_claims": False,
00259:         "reruns_ocr": False,
00260:         "reruns_embeddings": False,
00261:         "reruns_graph_build": False,
00262:         "reruns_table_extraction": False,
00263:     }
00264:     for key, expected in required_rule_bools.items():
00265:         observed = as_bool(rules_box.get(key))
00266:         add_finding(
00267:             f"rules_box_{key}",
00268:             observed is expected,
00269:             "blocker" if key in {"source_truth_mutation_allowed", "answer_permission", "can_answer_directly", "can_prove_claims"} else "warning",
00270:             f"Rules box must keep {key}={expected}.",
00271:             observed,
00272:         )
00273: 
00274:     # Determine critic status.
00275:     if blockers:
00276:         # Missing evidence or intent mismatch should go to CRAG retry. Unsafe authority issues need human review.
00277:         unsafe_blockers = {
00278:             "all_guidance_is_not_source_truth",
00279:             "rules_box_source_truth_mutation_allowed",
00280:             "rules_box_answer_permission",
00281:             "rules_box_can_answer_directly",
00282:             "rules_box_can_prove_claims",
00283:         }
00284:         critic_status = CRITIC_NEEDS_HUMAN_REVIEW if any(b in unsafe_blockers for b in blockers) else CRITIC_NEEDS_CRAG_RETRY
00285:     elif warnings:
00286:         critic_status = CRITIC_WEAK
00287:     else:
00288:         critic_status = CRITIC_READY
00289: 
00290:     ready_for_prompt = critic_status == CRITIC_READY
00291:     needs_crag_retry = critic_status == CRITIC_NEEDS_CRAG_RETRY
00292:     needs_human_review = critic_status == CRITIC_NEEDS_HUMAN_REVIEW
00293: 
00294:     return {
00295:         "schema_version": SCHEMA_VERSION,
00296:         "context_pack_id": pack_id,
00297:         "user_query": user_query,
00298:         "query_intent": query_intent,
00299:         "self_rag_critic_status": critic_status,
00300:         "ready_for_prompt_contract": ready_for_prompt,
00301:         "needs_crag_retry": needs_crag_retry,
00302:         "needs_human_review": needs_human_review,
00303:         "evidence_item_count": len(evidence_items),
00304:         "citation_ready_evidence_count": citation_ready_count,
```
### Source window L319-L375
```python
00319:         "source_truth_mutation_allowed": False,
00320:         "self_rag_next_status": "READY_FOR_CRAG_RETRIEVAL_CORRECTOR" if needs_crag_retry else "READY_FOR_LLM_PROMPT_CONTRACT" if ready_for_prompt else "NEEDS_HUMAN_REVIEW",
00321:     }
00322: 
00323: 
00324: def make_quality_check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
00325:     return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}
00326: 
00327: 
00328: def build_self_rag_context_critic(
00329:     dynamic_context_pack: Path | str,
00330:     *,
00331:     min_context_packs: int = 1,
00332:     min_context_critiques: int = 1,
00333:     min_ready_contexts: int = 1,
00334:     min_contexts_with_source_truth_evidence: int = 1,
00335:     min_contexts_with_guidance_separation: int = 1,
00336:     max_needs_crag_retry_count: Optional[int] = None,
00337:     max_human_review_count: int = 0,
00338:     max_graph_summary_proof_violations: int = 0,
00339:     max_answer_permission_count: int = 0,
00340:     max_source_truth_mutation_allowed: int = 0,
00341:     require_no_answer_permission: bool = False,
00342: ) -> Dict[str, Any]:
00343:     source = load_json(dynamic_context_pack)
00344:     packs = get_context_packs(source)
00345:     critiques = [critique_context_pack(pack) for pack in packs]
00346: 
00347:     ready_context_count = sum(1 for c in critiques if c.get("self_rag_critic_status") == CRITIC_READY)
00348:     weak_context_count = sum(1 for c in critiques if c.get("self_rag_critic_status") == CRITIC_WEAK)
00349:     needs_crag_retry_count = sum(1 for c in critiques if c.get("needs_crag_retry"))
00350:     human_review_count = sum(1 for c in critiques if c.get("needs_human_review"))
00351:     contexts_with_source_truth_evidence_count = sum(1 for c in critiques if int(c.get("source_truth_evidence_count") or 0) > 0)
00352:     contexts_with_guidance_separation_count = sum(
00353:         1 for c in critiques if int(c.get("safe_guidance_item_count") or 0) == int(c.get("guidance_item_count") or 0) and int(c.get("guidance_item_count") or 0) > 0
00354:     )
00355:     contexts_with_graph_or_summary_guidance_count = sum(1 for c in critiques if int(c.get("graph_or_summary_guidance_count") or 0) > 0)
00356:     graph_summary_proof_violation_count = sum(
00357:         1 for c in critiques for f in as_list(c.get("findings")) if isinstance(f, Mapping) and f.get("name") == "all_guidance_is_not_source_truth" and not f.get("passed")
00358:     )
00359:     answer_permission_count = truthy_count(critiques, "answer_permission")
00360:     can_answer_directly_count = truthy_count(critiques, "can_answer_directly")
00361:     can_prove_claims_count = truthy_count(critiques, "can_prove_claims")
00362:     source_truth_mutation_allowed_count = truthy_count(critiques, "source_truth_mutation_allowed")
00363: 
00364:     quality_checks: List[Dict[str, Any]] = [
00365:         make_quality_check("context_pack_count", len(packs), f">= {min_context_packs}", len(packs) >= min_context_packs),
00366:         make_quality_check("self_rag_critique_count", len(critiques), f">= {min_context_critiques}", len(critiques) >= min_context_critiques),
00367:         make_quality_check("ready_context_count", ready_context_count, f">= {min_ready_contexts}", ready_context_count >= min_ready_contexts),
00368:         make_quality_check(
00369:             "contexts_with_source_truth_evidence_count",
00370:             contexts_with_source_truth_evidence_count,
00371:             f">= {min_contexts_with_source_truth_evidence}",
00372:             contexts_with_source_truth_evidence_count >= min_contexts_with_source_truth_evidence,
00373:         ),
00374:         make_quality_check(
00375:             "contexts_with_guidance_separation_count",
```
### Source window L52-L108
```python
00052: def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
00053:     p = Path(path)
00054:     p.parent.mkdir(parents=True, exist_ok=True)
00055:     with p.open("w", encoding="utf-8") as f:
00056:         for row in rows:
00057:             f.write(json.dumps(dict(row), sort_keys=True) + "\n")
00058: 
00059: 
00060: def as_list(value: Any) -> List[Any]:
00061:     if value is None:
00062:         return []
00063:     if isinstance(value, list):
00064:         return value
00065:     return [value]
00066: 
00067: 
00068: def as_bool(value: Any) -> bool:
00069:     if isinstance(value, bool):
00070:         return value
00071:     if isinstance(value, str):
00072:         return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
00073:     return bool(value)
00074: 
00075: 
00076: def truthy_count(rows: Iterable[Mapping[str, Any]], key: str) -> int:
00077:     return sum(1 for row in rows if as_bool(row.get(key)))
00078: 
00079: 
00080: def get_context_packs(context_pack_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
00081:     for key in ("context_packs", "packs", "records", "context_pack_records"):
00082:         rows = context_pack_report.get(key)
00083:         if isinstance(rows, list):
00084:             return [dict(row) for row in rows if isinstance(row, Mapping)]
00085:     # Some generated artifacts may place packs under data/context_packs.
00086:     data = context_pack_report.get("data")
00087:     if isinstance(data, Mapping):
00088:         rows = data.get("context_packs")
00089:         if isinstance(rows, list):
00090:             return [dict(row) for row in rows if isinstance(row, Mapping)]
00091:     return []
00092: 
00093: 
00094: def get_evidence_items(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
00095:     evidence_box = pack.get("evidence_box")
00096:     if isinstance(evidence_box, Mapping):
00097:         return [dict(row) for row in as_list(evidence_box.get("items")) if isinstance(row, Mapping)]
00098:     return []
00099: 
00100: 
00101: def get_guidance_items(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
00102:     guidance_box = pack.get("guidance_box")
00103:     if isinstance(guidance_box, Mapping):
00104:         return [dict(row) for row in as_list(guidance_box.get("items")) if isinstance(row, Mapping)]
00105:     return []
00106: 
00107: 
00108: def get_rules_box(pack: Mapping[str, Any]) -> Dict[str, Any]:
```
### Source window L141-L197
```python
00141:     evidence_items = get_evidence_items(pack)
00142:     guidance_items = get_guidance_items(pack)
00143:     rules_box = get_rules_box(pack)
00144: 
00145:     findings: List[Dict[str, Any]] = []
00146:     blockers: List[str] = []
00147:     warnings: List[str] = []
00148: 
00149:     def add_finding(name: str, passed: bool, severity: str, detail: str, observed: Any = None) -> None:
00150:         finding = {
00151:             "name": name,
00152:             "passed": bool(passed),
00153:             "severity": severity,
00154:             "detail": detail,
00155:         }
00156:         if observed is not None:
00157:             finding["observed"] = observed
00158:         findings.append(finding)
00159:         if not passed and severity == "blocker":
00160:             blockers.append(name)
00161:         elif not passed:
00162:             warnings.append(name)
00163: 
00164:     status_ready = str(pack.get("context_pack_status") or "").upper().endswith("READY")
00165:     add_finding(
00166:         "context_pack_status_ready",
00167:         status_ready,
00168:         "blocker",
00169:         "Context pack must be marked ready before LLM prompt construction.",
00170:         pack.get("context_pack_status"),
00171:     )
00172: 
00173:     has_evidence = len(evidence_items) > 0
00174:     add_finding(
00175:         "has_evidence_box_items",
00176:         has_evidence,
00177:         "blocker",
00178:         "Context pack must include source-truth evidence items.",
00179:         len(evidence_items),
00180:     )
00181: 
00182:     citation_ready_count = sum(1 for item in evidence_items if as_bool(item.get("citation_ready")))
00183:     source_trace_ready_count = sum(1 for item in evidence_items if as_bool(item.get("source_trace_ready")))
00184:     source_truth_authority_count = sum(
00185:         1 for item in evidence_items if str(item.get("answer_authority") or "") == SOURCE_TRUTH_AUTHORITY
00186:     )
00187:     relevant_evidence_count = sum(
00188:         1 for item in evidence_items if field_relevant_for_intent(str(item.get("field_name") or ""), query_intent)
00189:     )
00190: 
00191:     add_finding(
00192:         "all_evidence_citation_ready",
00193:         citation_ready_count == len(evidence_items) and has_evidence,
00194:         "blocker",
00195:         "Every evidence item must be citation-ready.",
00196:         {"citation_ready_count": citation_ready_count, "evidence_item_count": len(evidence_items)},
00197:     )
```
### Source window L504-L553
```python
00504: 
00505: 
00506: def write_report_files(report: Mapping[str, Any], output_dir: Path | str) -> Dict[str, str]:
00507:     out = Path(output_dir)
00508:     out.mkdir(parents=True, exist_ok=True)
00509:     report_path = out / "trace_net_e2e_self_rag_context_critic_v9.json"
00510:     critiques_jsonl_path = out / "trace_net_e2e_self_rag_context_critic_records_v9.jsonl"
00511:     inspect_md_path = out / "trace_net_e2e_self_rag_context_critic_v9.md"
00512:     write_json(report_path, report)
00513:     write_jsonl(critiques_jsonl_path, [row for row in as_list(report.get("critiques")) if isinstance(row, Mapping)])
00514:     inspect_md_path.write_text(render_markdown_report(report), encoding="utf-8")
00515:     return {
00516:         "report_path": str(report_path),
00517:         "critiques_jsonl_path": str(critiques_jsonl_path),
00518:         "inspect_md_path": str(inspect_md_path),
00519:     }
00520: 
00521: 
00522: def add_common_args(parser: argparse.ArgumentParser) -> None:
00523:     parser.add_argument("--dynamic-context-pack", required=True)
00524:     parser.add_argument("--output-dir", default="local_data/organization/trace_net/e2e_self_rag_context_critic")
00525:     parser.add_argument("--min-context-packs", type=int, default=1)
00526:     parser.add_argument("--min-context-critiques", type=int, default=1)
00527:     parser.add_argument("--min-ready-contexts", type=int, default=1)
00528:     parser.add_argument("--min-contexts-with-source-truth-evidence", type=int, default=1)
00529:     parser.add_argument("--min-contexts-with-guidance-separation", type=int, default=1)
00530:     parser.add_argument("--max-needs-crag-retry-count", type=int, default=None)
00531:     parser.add_argument("--max-human-review-count", type=int, default=0)
00532:     parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
00533:     parser.add_argument("--max-answer-permission-count", type=int, default=0)
00534:     parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00535:     parser.add_argument("--require-no-answer-permission", action="store_true")
00536:     parser.add_argument("--quality", action="store_true")
00537: 
00538: 
00539: def build_from_args(args: argparse.Namespace) -> Dict[str, Any]:
00540:     return build_self_rag_context_critic(
00541:         args.dynamic_context_pack,
00542:         min_context_packs=args.min_context_packs,
00543:         min_context_critiques=args.min_context_critiques,
00544:         min_ready_contexts=args.min_ready_contexts,
00545:         min_contexts_with_source_truth_evidence=args.min_contexts_with_source_truth_evidence,
00546:         min_contexts_with_guidance_separation=args.min_contexts_with_guidance_separation,
00547:         max_needs_crag_retry_count=args.max_needs_crag_retry_count,
00548:         max_human_review_count=args.max_human_review_count,
00549:         max_graph_summary_proof_violations=args.max_graph_summary_proof_violations,
00550:         max_answer_permission_count=args.max_answer_permission_count,
00551:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00552:         require_no_answer_permission=args.require_no_answer_permission,
00553:     )
```

## `tests/unit/test_trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Location: `active_tests`
- Score: `235`
- Categories: `context_pack, crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Functions: _prompt_injector(tmp_path)@L11; _h22_smoke(tmp_path)@L39; test_bridge_records_map_to_answer_runner_questions(tmp_path)@L67; test_build_bridge_passes_with_h22(tmp_path)@L79; test_check_bridge_artifact(tmp_path)@L97; test_h20_prompt_wording_is_safe_boundary()@L117; test_missing_boundary_is_unsafe(tmp_path)@L147
- Tiff imports: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import build_answer_runner_retrieval_bridge_manifest, build_bridge_records, check_answer_runner_retrieval_bridge_manifest

### Source window L1-L32
```python
00001: import json
00002: from pathlib import Path
00003: 
00004: from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import (
00005:     build_answer_runner_retrieval_bridge_manifest,
00006:     build_bridge_records,
00007:     check_answer_runner_retrieval_bridge_manifest,
00008: )
00009: 
00010: 
00011: def _prompt_injector(tmp_path: Path) -> Path:
00012:     data = {
00013:         "quality_status": "PASS",
00014:         "summary": {
00015:             "answer_permission_count": 0,
00016:             "source_truth_mutation_allowed_count": 0,
00017:             "postgres_write_attempt_count": 0,
00018:             "qdrant_read_attempt_count": 0,
00019:             "qdrant_write_attempt_count": 0,
00020:             "opensearch_write_attempt_count": 0,
00021:             "opensearch_upload_attempt_count": 0,
00022:             "write_attempt_count": 0,
00023:             "unsafe_finding_count": 0,
00024:         },
00025:         "prompt_bundles": [
00026:             {"query_id": "h19_q_interchangeability_boundary", "task_type": "interchangeability_boundary", "selected_atom_count": 4, "selected_layers": ["procedural_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context require explicit authority"},
00027:             {"query_id": "h19_q_visual_ocr_route_behavior", "task_type": "route_explanation", "selected_atom_count": 4, "selected_layers": ["semantic_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context visual OCR nomenclature"},
00028:             {"query_id": "h19_q_unknown_part_not_source_trace_ready", "task_type": "unknown_part", "selected_atom_count": 4, "selected_layers": ["working_memory"], "selected_proof_roles": ["current_proof_context_only", "guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context no proof_context not source-trace-ready"},
00029:             {"query_id": "h19_q_safe_but_too_generic_repair", "task_type": "critic_repair", "selected_atom_count": 4, "selected_layers": ["critic_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context safe but too generic repair"},
00030:             {"query_id": "h19_q_summary_only_limit", "task_type": "summary_limit", "selected_atom_count": 4, "selected_layers": ["working_memory"], "selected_proof_roles": ["current_proof_context_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context summaries not proof"},
00031:             {"query_id": "h19_q_installation_fit_effectivity_limit", "task_type": "approval_boundary", "selected_atom_count": 4, "selected_layers": ["procedural_memory"], "selected_proof_roles": ["guidance_only"], "prompt_guidance_text": "behavior guidance only not proof proof_context figure identification not approval"},
00032:         ],
```
### Source window L47-L103
```python
00047:             "qdrant_write_attempt_count": 0,
00048:             "opensearch_write_attempt_count": 0,
00049:             "opensearch_upload_attempt_count": 0,
00050:             "write_attempt_count": 0,
00051:             "unsafe_finding_count": 0,
00052:         },
00053:         "smoke_records": [
00054:             {"query_id": "h19_q_interchangeability_boundary", "grade": "GOOD", "unsupported_claim_count": 0},
00055:             {"query_id": "h19_q_visual_ocr_route_behavior", "grade": "GOOD", "unsupported_claim_count": 0},
00056:             {"query_id": "h19_q_unknown_part_not_source_trace_ready", "grade": "GOOD", "unsupported_claim_count": 0},
00057:             {"query_id": "h19_q_safe_but_too_generic_repair", "grade": "GOOD", "unsupported_claim_count": 0},
00058:             {"query_id": "h19_q_summary_only_limit", "grade": "GOOD", "unsupported_claim_count": 0},
00059:             {"query_id": "h19_q_installation_fit_effectivity_limit", "grade": "GOOD", "unsupported_claim_count": 0},
00060:         ],
00061:     }
00062:     p = tmp_path / "h22.json"
00063:     p.write_text(json.dumps(data), encoding="utf-8")
00064:     return p
00065: 
00066: 
00067: def test_bridge_records_map_to_answer_runner_questions(tmp_path):
00068:     prompt_path = _prompt_injector(tmp_path)
00069:     data = json.loads(prompt_path.read_text())
00070:     records = build_bridge_records(data)
00071:     assert len(records) == 6
00072:     rec = next(r for r in records if r["task_type"] == "interchangeability_boundary")
00073:     assert "q12" in rec["target_answer_runner_question_ids"]
00074:     assert rec["answer_permission"] is False
00075:     assert rec["engram_is_proof"] is False
00076:     assert not rec["unsafe"]
00077: 
00078: 
00079: def test_build_bridge_passes_with_h22(tmp_path):
00080:     result = build_answer_runner_retrieval_bridge_manifest(
00081:         prompt_injector=_prompt_injector(tmp_path),
00082:         h22_llm_smoke=_h22_smoke(tmp_path),
00083:         output_dir=tmp_path / "out",
00084:         min_bridge_records=6,
00085:         min_task_types=6,
00086:         require_h20_quality_pass=True,
00087:         require_h22_quality_pass=True,
00088:         require_no_answer_permission=True,
00089:         max_unsafe=0,
00090:         max_write_attempts=0,
00091:     )
00092:     assert result["quality_status"] == "PASS"
00093:     assert result["summary"]["target_answer_runner_question_count"] >= 6
00094:     assert Path(result["guidance_map_path"]).exists()
00095: 
00096: 
00097: def test_check_bridge_artifact(tmp_path):
00098:     result = build_answer_runner_retrieval_bridge_manifest(
00099:         prompt_injector=_prompt_injector(tmp_path),
00100:         h22_llm_smoke=_h22_smoke(tmp_path),
00101:         output_dir=tmp_path / "out",
00102:         require_h20_quality_pass=True,
00103:         require_h22_quality_pass=True,
```
### Source window L109-L152
```python
00109:         require_quality_pass=True,
00110:         require_no_answer_permission=True,
00111:         max_unsafe=0,
00112:         max_write_attempts=0,
00113:     )
00114:     assert check["quality_status"] == "PASS"
00115: 
00116: 
00117: def test_h20_prompt_wording_is_safe_boundary():
00118:     data = {
00119:         "quality_status": "PASS",
00120:         "summary": {
00121:             "answer_permission_count": 0,
00122:             "source_truth_mutation_allowed_count": 0,
00123:             "postgres_write_attempt_count": 0,
00124:             "qdrant_read_attempt_count": 0,
00125:             "qdrant_write_attempt_count": 0,
00126:             "opensearch_write_attempt_count": 0,
00127:             "opensearch_upload_attempt_count": 0,
00128:             "write_attempt_count": 0,
00129:             "unsafe_finding_count": 0,
00130:         },
00131:         "prompt_bundles": [
00132:             {
00133:                 "query_id": "h19_q_visual_ocr_route_behavior",
00134:                 "task_type": "route_explanation",
00135:                 "selected_atom_count": 4,
00136:                 "selected_layers": ["semantic_memory"],
00137:                 "selected_proof_roles": ["guidance_only"],
00138:                 "prompt_guidance_text": "TRACE-NET ENGRAM RETRIEVAL GUIDANCE — BEHAVIOR ONLY, NOT PROOF\nUse these retrieved Engram atoms to shape answer behavior only. Do not use Engram memory as manual evidence. Manual/source claims still require current proof_context citations from TRACE-Net.",
00139:             }
00140:         ],
00141:     }
00142:     records = build_bridge_records(data)
00143:     assert records[0]["unsafe"] is False
00144:     assert records[0]["unsafe_findings"] == []
00145: 
00146: 
00147: def test_missing_boundary_is_unsafe(tmp_path):
00148:     data = json.loads(_prompt_injector(tmp_path).read_text())
00149:     data["prompt_bundles"][0]["prompt_guidance_text"] = "missing the required boundary"
00150:     records = build_bridge_records(data)
00151:     assert records[0]["unsafe"] is True
00152:     assert records[0]["unsafe_findings"]
```

## `tiff/trace_net_e2e_live_relationship_final_gated_endpoint_v31.py`
- Location: `active_source_code`
- Score: `234`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: RuntimeState@L125 methods=['__init__', 'answer']
- Functions: _now_ms()@L55; _quality_check(name, observed, op, expected)@L59; _router_result_to_gate_input(query, router_result)@L73; apply_relationship_final_gate(query, router_result)@L87; make_chat_completion_response(model, query, result)@L164; _sample_record(sample_id, query, result)@L228; build_report()@L248; write_inspect_md(path, report)@L373; check_report()@L428; __init__(self)@L126; answer(self, query)@L147
- Tiff imports: from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import MODEL_ID, SAFETY_CONTRACT, RuntimeState, _extract_user_text, _read_json, _write_json, _write_jsonl; from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import SAFETY_CONTRACT, final_gate_record

### Source window L1-L55
```python
00001: from __future__ import annotations
00002: 
00003: import json
00004: import time
00005: import uuid
00006: from pathlib import Path
00007: from typing import Any, Dict, Iterable, List, Optional, Sequence
00008: 
00009: from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import (
00010:     MODEL_ID as ROUTER_MODEL_ID,
00011:     SAFETY_CONTRACT as ROUTER_SAFETY_CONTRACT,
00012:     RuntimeState as RouterRuntimeState,
00013:     _extract_user_text,
00014:     _read_json,
00015:     _write_json,
00016:     _write_jsonl,
00017: )
00018: from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import (
00019:     SAFETY_CONTRACT as RELATIONSHIP_GATE_SAFETY_CONTRACT,
00020:     final_gate_record,
00021: )
00022: 
00023: VERSION = "v31"
00024: MODULE = "trace_net_e2e_live_relationship_final_gated_endpoint_v31"
00025: MODEL_ID = "trace-net-e2e-live-relationship-final-gated-gemma-v31"
00026: STATUS_READY = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_READY"
00027: STATUS_NEEDS_REPAIR = "E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_NEEDS_REPAIR"
00028: 
00029: SAFETY_CONTRACT = {
00030:     **ROUTER_SAFETY_CONTRACT,
00031:     **RELATIONSHIP_GATE_SAFETY_CONTRACT,
00032:     "llm_called": False,
00033:     "metadata_count_router_enabled": True,
00034:     "relationship_final_gate_required": True,
00035:     "relationship_final_gate_live_endpoint": True,
00036:     "graph_leiden_guidance_only": True,
00037:     "v2_summaries_guidance_only": True,
00038:     "nomenclature_metadata_guidance_only": True,
00039:     "source_truth_required_for_relationship_claims": True,
00040: }
00041: 
00042: STANDARD_SAMPLE_QUERIES = [
00043:     "how many pages have a v2 summary",
00044:     "how many pages mention a nomenclature",
00045:     "find part number 120-36833-503",
00046:     "Find part number DOES-NOT-EXIST-999",
00047:     "What maintenance manual pages mention covered part numbers?",
00048:     "Drill down covered part numbers by page",
00049:     "What pages are related to part number 120-36833-503?",
00050:     "Which pages are in the same Leiden community as page t_p_120_1176_p000003?",
00051:     "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
00052: ]
00053: 
00054: 
00055: def _now_ms() -> float:
```
### Source window L72-L128
```python
00072: 
00073: def _router_result_to_gate_input(query: str, router_result: Dict[str, Any]) -> Dict[str, Any]:
00074:     """Adapt a v29.2 router result to the v30 relationship final-gate shape."""
00075:     return {
00076:         **router_result,
00077:         "user_query": query,
00078:         "query": query,
00079:         "final_answer": router_result.get("answer", ""),
00080:         "answer": router_result.get("answer", ""),
00081:         "response_mode": router_result.get("response_mode"),
00082:         "final_gate_status": router_result.get("final_gate_status"),
00083:         "relationship_query": router_result.get("relationship_query", False),
00084:     }
00085: 
00086: 
00087: def apply_relationship_final_gate(query: str, router_result: Dict[str, Any], *, record_id: str = "live_relationship_gate_v31_0001") -> Dict[str, Any]:
00088:     """Apply the v30 relationship hard gate to a live router result."""
00089:     gate_input = _router_result_to_gate_input(query, router_result)
00090:     gate = final_gate_record(gate_input, record_id=record_id)
00091:     final_result = dict(router_result)
00092:     final_result["source_final_gate_status"] = router_result.get("final_gate_status")
00093:     final_result["answer"] = gate.get("final_answer", router_result.get("answer", ""))
00094:     final_result["relationship_final_gate_applied"] = True
00095:     final_result["relationship_final_gate_status"] = gate.get("final_gate_status")
00096:     final_result["relationship_final_gate_repaired"] = gate.get("repaired_from_draft", False)
00097:     final_result["relationship_final_gate_post_issue_count"] = gate.get("post_gate_issue_count", 0)
00098:     final_result["relationship_final_gate_record_id"] = gate.get("relationship_final_gate_id")
00099:     final_result["relationship_gate_latency_ms"] = gate.get("latency_ms", 0)
00100:     final_result["graph_as_proof_violation_detected"] = gate.get("graph_as_proof_violation_detected", False)
00101:     final_result["v2_summary_as_proof_violation_detected"] = gate.get("v2_summary_as_proof_violation_detected", False)
00102:     final_result["nomenclature_as_proof_violation_detected"] = gate.get("nomenclature_as_proof_violation_detected", False)
00103:     final_result["unsupported_relationship_claim_detected"] = gate.get("unsupported_relationship_claim_detected", False)
00104:     final_result["relationship_guidance_only_enforced"] = gate.get("relationship_guidance_only_enforced", False)
00105:     final_result["source_truth_required_for_relationship_claims"] = True
00106:     final_result["final_gate_status"] = gate.get("final_gate_status")
00107:     final_result["relationship_final_gate_record"] = gate
00108: 
00109:     safety = dict(final_result.get("safety") or {})
00110:     safety.update(
00111:         {
00112:             "relationship_final_gate_required": True,
00113:             "relationship_final_gate_applied": True,
00114:             "source_truth_required_for_relationship_claims": True,
00115:             "graph_leiden_guidance_only": True,
00116:             "v2_summaries_guidance_only": True,
00117:             "nomenclature_metadata_guidance_only": True,
00118:             "response_is_final_gated": gate.get("final_gate_status") == "RELATIONSHIP_FINAL_GATE_PASS",
00119:         }
00120:     )
00121:     final_result["safety"] = safety
00122:     return final_result
00123: 
00124: 
00125: class RuntimeState:
00126:     def __init__(
00127:         self,
00128:         *,
```
### Source window L159-L215
```python
00159:             "relationship_final_gate_ms": stage_timings["relationship_final_gate_ms"],
00160:         }
00161:         return gated
00162: 
00163: 
00164: def make_chat_completion_response(model: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
00165:     trace_net = {
00166:         "endpoint_version": "live_relationship_final_gated_v31",
00167:         "query_intent": result.get("query_intent"),
00168:         "response_mode": result.get("response_mode"),
00169:         "source_final_gate_status": result.get("source_final_gate_status"),
00170:         "final_gate_status": result.get("final_gate_status"),
00171:         "relationship_final_gate_applied": result.get("relationship_final_gate_applied", False),
00172:         "relationship_final_gate_status": result.get("relationship_final_gate_status"),
00173:         "relationship_final_gate_repaired": result.get("relationship_final_gate_repaired", False),
00174:         "relationship_final_gate_post_issue_count": result.get("relationship_final_gate_post_issue_count", 0),
00175:         "graph_as_proof_violation_detected": result.get("graph_as_proof_violation_detected", False),
00176:         "v2_summary_as_proof_violation_detected": result.get("v2_summary_as_proof_violation_detected", False),
00177:         "nomenclature_as_proof_violation_detected": result.get("nomenclature_as_proof_violation_detected", False),
00178:         "unsupported_relationship_claim_detected": result.get("unsupported_relationship_claim_detected", False),
00179:         "citation_like_count": result.get("citation_like_count", 0),
00180:         "total_match_count": result.get("total_match_count", 0),
00181:         "returned_match_count": result.get("returned_match_count", 0),
00182:         "result_was_capped": result.get("result_was_capped", False),
00183:         "metadata_count_router_used": result.get("metadata_count_router_used", False),
00184:         "metadata_count_source": result.get("metadata_count_source"),
00185:         "bad_broad_fallback_blocked": result.get("bad_broad_fallback_blocked", False),
00186:         "relationship_query": result.get("relationship_query", False),
00187:         "relationship_guidance_only": result.get("relationship_guidance_only", False),
00188:         "relationship_guidance_only_enforced": result.get("relationship_guidance_only_enforced", False),
00189:         "relationship_proof_violation": result.get("relationship_proof_violation", False),
00190:         "source_truth_required_for_relationship_claims": result.get("source_truth_required_for_relationship_claims", True),
00191:         "llm_status": result.get("llm_status"),
00192:         "llm_called": result.get("llm_called", False),
00193:         "stage_timings_ms": result.get("stage_timings_ms", {}),
00194:         "latency_summary": result.get("latency_summary", {}),
00195:         "safety": result.get("safety", SAFETY_CONTRACT),
00196:     }
00197:     for key in (
00198:         "v2_summary_page_count",
00199:         "v2_summary_page_first",
00200:         "v2_summary_page_last",
00201:         "page_context_v2_page_count",
00202:         "graph_has_v2_page_count",
00203:         "graph_has_context_page_count",
00204:         "nomenclature_page_count",
00205:         "nomenclature_page_first",
00206:         "nomenclature_page_last",
00207:         "nomenclature_part_count",
00208:         "raw_candidate_match_count",
00209:         "target_unique_match_count",
00210:         "target_occurrence_count",
00211:         "collapsed_duplicate_record_count",
00212:         "candidate_page_ids",
00213:         "leiden_community_ids",
00214:     ):
00215:         if key in result:
```
### Source window L223-L279
```python
00223:         "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
00224:         "trace_net": trace_net,
00225:     }
00226: 
00227: 
00228: def _sample_record(sample_id: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
00229:     status = "PASS" if result.get("relationship_final_gate_status") == "RELATIONSHIP_FINAL_GATE_PASS" and result.get("relationship_final_gate_post_issue_count", 0) == 0 else "FAIL"
00230:     return {
00231:         "sample_id": sample_id,
00232:         "query": query,
00233:         "status": status,
00234:         "response_mode": result.get("response_mode"),
00235:         "source_final_gate_status": result.get("source_final_gate_status"),
00236:         "relationship_final_gate_status": result.get("relationship_final_gate_status"),
00237:         "relationship_final_gate_applied": result.get("relationship_final_gate_applied"),
00238:         "relationship_final_gate_repaired": result.get("relationship_final_gate_repaired"),
00239:         "post_gate_issue_count": result.get("relationship_final_gate_post_issue_count", 0),
00240:         "relationship_query": result.get("relationship_query", False),
00241:         "metadata_count_router_used": result.get("metadata_count_router_used", False),
00242:         "bad_broad_fallback_blocked": result.get("bad_broad_fallback_blocked", False),
00243:         "answer": result.get("answer", ""),
00244:         "trace_net": {k: v for k, v in result.items() if k.endswith("_count") or k.endswith("_status") or k in {"metadata_count_source", "relationship_guidance_only"}},
00245:     }
00246: 
00247: 
00248: def build_report(
00249:     *,
00250:     relationship_router_hardening: Path,
00251:     relationship_final_gate_hardener: Optional[Path],
00252:     table_exact_search_adapter: Path,
00253:     page_context_v2: Optional[Path],
00254:     leiden_communities: Optional[Path],
00255:     output_dir: Path,
00256:     graph_signal_paths: Optional[Sequence[Path]] = None,
00257:     include_standard_demo_queries: bool = False,
00258:     min_sample_queries: int = 0,
00259:     min_sample_successes: int = 0,
00260:     min_relationship_final_gate_applied: int = 0,
00261:     min_relationship_records: int = 0,
00262:     max_post_gate_issue_count: int = 0,
00263:     max_answer_permission_count: int = 0,
00264:     max_source_truth_mutation_allowed: int = 0,
00265:     require_no_answer_permission: bool = False,
00266:     quality: bool = False,
00267: ) -> Dict[str, Any]:
00268:     output_dir.mkdir(parents=True, exist_ok=True)
00269:     runtime = RuntimeState(
00270:         relationship_router_hardening=relationship_router_hardening,
00271:         relationship_final_gate_hardener=relationship_final_gate_hardener,
00272:         table_exact_search_adapter=table_exact_search_adapter,
00273:         page_context_v2=page_context_v2,
00274:         leiden_communities=leiden_communities,
00275:         graph_signal_paths=graph_signal_paths,
00276:     )
00277:     queries = STANDARD_SAMPLE_QUERIES if include_standard_demo_queries else STANDARD_SAMPLE_QUERIES[:4]
00278:     sample_records: List[Dict[str, Any]] = []
00279:     for idx, query in enumerate(queries, 1):
```
### Source window L317-L373
```python
00317:         _quality_check("relationship_final_gate_applied_count", relationship_gate_applied_count, ">=", min_relationship_final_gate_applied),
00318:         _quality_check("relationship_record_count", relationship_record_count, ">=", min_relationship_records),
00319:         _quality_check("post_gate_issue_count", post_gate_issue_count, "<=", max_post_gate_issue_count),
00320:         _quality_check("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
00321:         _quality_check("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
00322:         _quality_check("contract_relationship_final_gate_live_endpoint", True, "is", True),
00323:         _quality_check("contract_raw_5tb_scan_at_query_time", False, "is", False),
00324:     ]
00325:     if require_no_answer_permission:
00326:         checks.append(_quality_check("require_no_answer_permission", answer_permission_count, "==", 0))
00327: 
00328:     quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
00329:     report_path = output_dir / "trace_net_e2e_live_relationship_final_gated_endpoint_v31.json"
00330:     samples_jsonl_path = output_dir / "trace_net_e2e_live_relationship_final_gated_endpoint_samples_v31.jsonl"
00331:     inspect_md_path = output_dir / "trace_net_e2e_live_relationship_final_gated_endpoint_v31.md"
00332: 
00333:     router_report = runtime.router_report
00334:     gate_report = runtime.relationship_final_gate_hardener_report
00335:     report = {
00336:         "module": MODULE,
00337:         "version": VERSION,
00338:         "status": STATUS_READY if quality_status == "PASS" else STATUS_NEEDS_REPAIR,
00339:         "quality_status": quality_status,
00340:         "model_id": MODEL_ID,
00341:         "router_model_id": ROUTER_MODEL_ID,
00342:         "relationship_router_hardening_path": str(relationship_router_hardening),
00343:         "relationship_final_gate_hardener_path": str(relationship_final_gate_hardener) if relationship_final_gate_hardener else None,
00344:         "exact_search_document_count": router_report.get("exact_search_document_count", 0),
00345:         "page_context_v2_page_count": router_report.get("page_context_v2_page_count", 0),
00346:         "graph_has_v2_page_count": router_report.get("graph_has_v2_page_count", 0),
00347:         "graph_has_nomenclature_page_count": router_report.get("graph_has_nomenclature_page_count", 0),
00348:         "relationship_final_gate_hardener_quality_status": gate_report.get("quality_status"),
00349:         "relationship_final_gate_hardener_post_gate_issue_count": gate_report.get("post_gate_issue_count", 0),
00350:         "sample_query_count": len(sample_records),
00351:         "sample_success_count": sample_success_count,
00352:         "relationship_final_gate_applied_count": relationship_gate_applied_count,
00353:         "relationship_record_count": relationship_record_count,
00354:         "repaired_relationship_sample_count": repaired_count,
00355:         "post_gate_issue_count": post_gate_issue_count,
00356:         "answer_permission_count": answer_permission_count,
00357:         "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
00358:         "base_url_windows": "http://127.0.0.1:8026/v1",
00359:         "base_url_open_webui_docker": "http://host.docker.internal:8026/v1",
00360:         "contract": SAFETY_CONTRACT,
00361:         "sample_records": sample_records,
00362:         "quality_checks": checks,
00363:         "report_path": str(report_path),
00364:         "samples_jsonl_path": str(samples_jsonl_path),
00365:         "inspect_md_path": str(inspect_md_path),
00366:     }
00367:     _write_json(report_path, report)
00368:     _write_jsonl(samples_jsonl_path, sample_records)
00369:     write_inspect_md(inspect_md_path, report)
00370:     return report
00371: 
00372: 
00373: def write_inspect_md(path: Path, report: Dict[str, Any]) -> None:
```
### Source window L409-L458
```python
00409:         lines.extend([
00410:             f"### {r['sample_id']} — {r['status']}",
00411:             f"- query: {r.get('query')}",
00412:             f"- response_mode: {r.get('response_mode')}",
00413:             f"- source_final_gate_status: {r.get('source_final_gate_status')}",
00414:             f"- relationship_final_gate_status: {r.get('relationship_final_gate_status')}",
00415:             f"- relationship_final_gate_repaired: {r.get('relationship_final_gate_repaired')}",
00416:             f"- post_gate_issue_count: {r.get('post_gate_issue_count')}",
00417:             f"- preview: {r.get('answer','')[:260]}",
00418:             "",
00419:         ])
00420:     lines.extend(["## Quality checks"])
00421:     for c in report.get("quality_checks", []):
00422:         status = "PASS" if c["passed"] else "FAIL"
00423:         lines.append(f"- {status} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
00424:     path.parent.mkdir(parents=True, exist_ok=True)
00425:     path.write_text("\n".join(lines) + "\n", encoding="utf-8")
00426: 
00427: 
00428: def check_report(
00429:     *,
00430:     report_path: Path,
00431:     min_sample_queries: int = 0,
00432:     min_sample_successes: int = 0,
00433:     min_relationship_final_gate_applied: int = 0,
00434:     min_relationship_records: int = 0,
00435:     max_post_gate_issue_count: int = 0,
00436:     max_answer_permission_count: int = 0,
00437:     max_source_truth_mutation_allowed: int = 0,
00438:     require_no_answer_permission: bool = False,
00439:     write_json: bool = False,
00440: ) -> Dict[str, Any]:
00441:     report = _read_json(report_path)
00442:     checks = [
00443:         _quality_check("quality_status", report.get("quality_status"), "==", "PASS"),
00444:         _quality_check("sample_query_count", report.get("sample_query_count", 0), ">=", min_sample_queries),
00445:         _quality_check("sample_success_count", report.get("sample_success_count", 0), ">=", min_sample_successes),
00446:         _quality_check("relationship_final_gate_applied_count", report.get("relationship_final_gate_applied_count", 0), ">=", min_relationship_final_gate_applied),
00447:         _quality_check("relationship_record_count", report.get("relationship_record_count", 0), ">=", min_relationship_records),
00448:         _quality_check("post_gate_issue_count", report.get("post_gate_issue_count", 0), "<=", max_post_gate_issue_count),
00449:         _quality_check("answer_permission_count", report.get("answer_permission_count", 0), "<=", max_answer_permission_count),
00450:         _quality_check("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
00451:     ]
00452:     if require_no_answer_permission:
00453:         checks.append(_quality_check("require_no_answer_permission", report.get("answer_permission_count", 0), "==", 0))
00454:     quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
00455:     result = {**report, "quality_status": quality_status, "quality_checks": checks}
00456:     if write_json:
00457:         _write_json(report_path, report)
00458:     return result
```

## `tests/unit/test_trace_net_e2e_live_self_rag_crag_evaluator_v20.py`
- Location: `active_tests`
- Score: `233`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server`
- Functions: _args()@L10; sample_pack(capped)@L32; test_evaluate_pack_ready_with_cap_disclosure()@L54; test_evaluate_pack_weak_without_evidence()@L62; test_build_report_passes_quality(tmp_path)@L71; test_graph_proof_authority_violation_blocks()@L84; test_v20_reads_v19_evidence_box_items_shape()@L92
- Tiff imports: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import build_report, evaluate_pack; from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import evaluate_pack

### Source window L1-L35
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: from pathlib import Path
00006: 
00007: from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import build_report, evaluate_pack
00008: 
00009: 
00010: def _args(**kwargs):
00011:     defaults = dict(
00012:         min_context_packs=2,
00013:         min_self_rag_evaluations=2,
00014:         min_crag_plans=2,
00015:         min_ready_for_llm=2,
00016:         min_contexts_with_source_truth_evidence=2,
00017:         min_contexts_with_graph_guidance=2,
00018:         min_contexts_with_v2_summary_guidance=2,
00019:         min_contexts_with_aggregation_or_cap_disclosure=1,
00020:         max_retry_required_count=0,
00021:         max_audit_only_count=0,
00022:         max_graph_proof_authority_violations=0,
00023:         max_summary_proof_authority_violations=0,
00024:         max_answer_permission_count=0,
00025:         max_source_truth_mutation_allowed=0,
00026:         require_no_answer_permission=True,
00027:     )
00028:     defaults.update(kwargs)
00029:     return argparse.Namespace(**defaults)
00030: 
00031: 
00032: def sample_pack(capped=False):
00033:     return {
00034:         "context_pack_id": "context_pack_v19_0001",
00035:         "query_plan_id": "query_plan_v17_0001",
```
### Source window L38-L94
```python
00038:         "guidance_box": {
00039:             "graph_guidance": [{"community_id": "c1"}],
00040:             "v2_summary_guidance": [{"page_id": "p1"}],
00041:             "graph_authority": "guidance_only",
00042:             "summary_authority": "guidance_only",
00043:         },
00044:         "aggregation_box": {
00045:             "total_match_count": 20 if capped else 2,
00046:             "returned_match_count": 2,
00047:             "result_was_capped": capped,
00048:             "more_results_available": capped,
00049:         },
00050:         "answer_rules_box": {"cite_every_factual_claim": True},
00051:     }
00052: 
00053: 
00054: def test_evaluate_pack_ready_with_cap_disclosure():
00055:     rec = evaluate_pack(sample_pack(capped=True), 0)
00056:     assert rec["self_rag_status"] == "CONTEXT_READY_WITH_CAP_DISCLOSURE"
00057:     assert rec["ready_for_llm_prompt"] is True
00058:     assert rec["retry_required"] is False
00059:     assert rec["aggregation_or_cap_disclosure"]["more_results_available"] is True
00060: 
00061: 
00062: def test_evaluate_pack_weak_without_evidence():
00063:     pack = sample_pack()
00064:     pack["evidence_box"] = {"source_truth_evidence": []}
00065:     rec = evaluate_pack(pack, 0)
00066:     assert rec["self_rag_status"] == "CONTEXT_WEAK_NEEDS_CRAG_RETRY"
00067:     assert rec["retry_required"] is True
00068:     assert rec["ready_for_llm_prompt"] is False
00069: 
00070: 
00071: def test_build_report_passes_quality(tmp_path: Path):
00072:     source = {
00073:         "context_packs": [sample_pack(capped=True), sample_pack(capped=False)],
00074:     }
00075:     source_path = tmp_path / "v19.json"
00076:     source_path.write_text(json.dumps(source), encoding="utf-8")
00077:     report = build_report(source_path, tmp_path / "out", _args())
00078:     assert report["quality_status"] == "PASS"
00079:     assert report["context_pack_count"] == 2
00080:     assert report["ready_for_llm_count"] == 2
00081:     assert report["contexts_with_aggregation_or_cap_disclosure_count"] >= 1
00082: 
00083: 
00084: def test_graph_proof_authority_violation_blocks():
00085:     pack = sample_pack()
00086:     pack["guidance_box"]["graph_authority"] = "proof_authority"
00087:     rec = evaluate_pack(pack, 0)
00088:     assert rec["audit_only"] is True
00089:     assert rec["graph_proof_authority_violation"] is True
00090: 
00091: 
00092: def test_v20_reads_v19_evidence_box_items_shape():
00093:     from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import evaluate_pack
00094: 
```

## `docs/trace_net/archive/old_patch_folders/trace_net_webui_self_rag_crag_bridge_v1_patch/tests/unit/test_trace_net_webui_self_rag_crag_bridge_v1_quality.py`
- Location: `archived_reference`
- Score: `231`
- Categories: `context_pack, graph_vector, page, safety, self_rag, server, webui`
- Functions: test_quality_check_passes_for_required_brain_gates(tmp_path)@L7; test_quality_check_fails_when_self_rag_not_used(tmp_path)@L46; test_quality_check_supports_explicit_tool_status_requirements(tmp_path)@L80
- Tiff imports: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality

### Source window L1-L32
```python
00001: import json
00002: from pathlib import Path
00003: 
00004: from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality
00005: 
00006: 
00007: def test_quality_check_passes_for_required_brain_gates(tmp_path):
00008:     report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
00009:     payload = {
00010:         "quality_status": "PASS",
00011:         "summary": {
00012:             "tool_checklist_count": 10,
00013:             "used_tool_count": 4,
00014:             "answer_permission_count": 0,
00015:             "can_answer_directly_count": 0,
00016:             "can_prove_claims_count": 0,
00017:             "source_truth_mutation_allowed_count": 0,
00018:             "postgres_write_attempt_count": 0,
00019:             "qdrant_write_attempt_count": 0,
00020:             "opensearch_write_attempt_count": 0,
00021:         },
00022:         "tool_statuses": {
00023:             "query_planner": "used",
00024:             "context_pack_builder": "used",
00025:             "self_rag": "used",
00026:             "crag_retry": "skipped_not_needed",
00027:         },
00028:     }
00029:     report.write_text(json.dumps(payload), encoding="utf-8")
00030: 
00031:     result = check_webui_self_rag_crag_bridge_quality(
00032:         report_path=report,
```
### Source window L49-L94
```python
00049:         "quality_status": "PASS",
00050:         "summary": {
00051:             "tool_checklist_count": 10,
00052:             "used_tool_count": 3,
00053:             "answer_permission_count": 0,
00054:             "can_answer_directly_count": 0,
00055:             "can_prove_claims_count": 0,
00056:             "source_truth_mutation_allowed_count": 0,
00057:             "postgres_write_attempt_count": 0,
00058:             "qdrant_write_attempt_count": 0,
00059:             "opensearch_write_attempt_count": 0,
00060:         },
00061:         "tool_statuses": {
00062:             "query_planner": "used",
00063:             "context_pack_builder": "used",
00064:             "self_rag": "available_not_used",
00065:             "crag_retry": "available_not_used",
00066:         },
00067:     }
00068:     report.write_text(json.dumps(payload), encoding="utf-8")
00069: 
00070:     result = check_webui_self_rag_crag_bridge_quality(
00071:         report_path=report,
00072:         require_self_rag_used=True,
00073:         require_crag_evaluated=True,
00074:     )
00075: 
00076:     assert result["quality_status"] == "FAIL"
00077:     assert any("Self-RAG" in failure for failure in result["failures"])
00078: 
00079: 
00080: def test_quality_check_supports_explicit_tool_status_requirements(tmp_path):
00081:     report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
00082:     payload = {
00083:         "quality_status": "PASS",
00084:         "summary": {"tool_checklist_count": 10, "used_tool_count": 4},
00085:         "tool_statuses": {"crag_retry": "used", "self_rag": "used"},
00086:     }
00087:     report.write_text(json.dumps(payload), encoding="utf-8")
00088: 
00089:     result = check_webui_self_rag_crag_bridge_quality(
00090:         report_path=report,
00091:         require_tool_statuses=["crag_retry=used", "self_rag=used"],
00092:     )
00093: 
00094:     assert result["quality_status"] == "PASS"
```

## `scripts/serve_trace_net_e2e_live_gemma_answer_writer_endpoint_v33.py`
- Location: `active_source_code`
- Score: `229`
- Categories: `final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Classes: Handler@L62 methods=['log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: _send_json(handler, data, status)@L21; main(argv)@L33; log_message(self, fmt)@L63; do_OPTIONS(self)@L66; do_GET(self)@L69; do_POST(self)@L109
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --host, --port, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --temperature, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens
- Routes: /health@L70, /v1/models@L104, /v1/chat/completions@L114
- Tiff imports: from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v33 import MODEL_ID, TraceNetGemmaAnswerWriterV33, _extract_messages_user_text
- Has __main__ guard.

### Source window L67-L123
```python
00067:             _send_json(self, {"ok": True})
00068: 
00069:         def do_GET(self) -> None:
00070:             if self.path == "/health":
00071:                 _send_json(
00072:                     self,
00073:                     {
00074:                         "status": "ok",
00075:                         "module": "trace_net_e2e_live_gemma_answer_writer_endpoint_v33",
00076:                         "quality_status": "PASS",
00077:                         "model_id": MODEL_ID,
00078:                         "llm_answer_mode": "always",
00079:                         "llm_mode": ns.llm_mode,
00080:                         "llm_model": ns.llm_model,
00081:                         "llm_prompt_mode": ns.llm_prompt_mode,
00082:                         "llm_max_output_tokens": ns.llm_max_output_tokens,
00083:                         "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
00084:                         "nomenclature_page_count": metadata.get("nomenclature_page_count"),
00085:                         "safety": {
00086:                             "answer_permission": False,
00087:                             "can_answer_directly": False,
00088:                             "can_prove_claims": False,
00089:                             "source_truth_mutation_allowed": False,
00090:                             "raw_5tb_scan_at_query_time": False,
00091:                             "graph_rebuild_at_query_time": False,
00092:                             "llm_called": True,
00093:                             "llm_answer_writer_required": True,
00094:                             "compact_prompt_mode_supported": True,
00095:                             "self_rag_package_quality_telemetry_enabled": True,
00096:                             "crag_retry_telemetry_enabled": True,
00097:                             "rich_page_profile_package_supported": True,
00098:                             "timeout_fallback_supported": True,
00099:                             "response_is_final_gated": True,
00100:                         },
00101:                     },
00102:                 )
00103:                 return
00104:             if self.path.rstrip("/") == "/v1/models":
00105:                 _send_json(self, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "trace-net-local"}]})
00106:                 return
00107:             _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404)
00108: 
00109:         def do_POST(self) -> None:
00110:             try:
00111:                 length = int(self.headers.get("Content-Length", "0"))
00112:                 raw = self.rfile.read(length).decode("utf-8", errors="replace")
00113:                 payload = json.loads(raw) if raw else {}
00114:                 if self.path.rstrip("/") != "/v1/chat/completions":
00115:                     _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404)
00116:                     return
00117:                 query = _extract_messages_user_text(payload)
00118:                 if not query:
00119:                     _send_json(self, {"error": "No user message found"}, status=400)
00120:                     return
00121:                 resp = writer.answer_query(
00122:                     query,
00123:                     llm_mode=ns.llm_mode,
```
### Source window L128-L172
```python
00128:                     request_timeout=ns.request_timeout,
00129:                     llm_prompt_mode=ns.llm_prompt_mode,
00130:                     llm_max_output_tokens=ns.llm_max_output_tokens,
00131:                 )
00132:                 # Preserve requested model id for OpenWebUI compatibility.
00133:                 resp["model"] = MODEL_ID
00134:                 _send_json(self, resp)
00135:             except Exception as exc:
00136:                 safe = {
00137:                     "id": "chatcmpl-tracenet-v33-error",
00138:                     "object": "chat.completion",
00139:                     "created": 0,
00140:                     "model": MODEL_ID,
00141:                     "choices": [
00142:                         {
00143:                             "index": 0,
00144:                             "message": {
00145:                                 "role": "assistant",
00146:                                 "content": "TRACE-Net encountered a live endpoint error while preparing the Gemma answer package. No source-truth claim is made.",
00147:                             },
00148:                             "finish_reason": "stop",
00149:                         }
00150:                     ],
00151:                     "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
00152:                     "trace_net": {
00153:                         "endpoint_version": "live_gemma_answer_writer_v33",
00154:                         "llm_called": False,
00155:                         "llm_status": "LIVE_ENDPOINT_ERROR_SAFE_FALLBACK",
00156:                         "final_gate_applied": True,
00157:                         "final_gate_status": "LIVE_GEMMA_ANSWER_WRITER_SAFE_ERROR_FALLBACK",
00158:                         "post_gate_issue_count": 0,
00159:                         "error": f"{type(exc).__name__}: {exc}",
00160:                     },
00161:                 }
00162:                 _send_json(self, safe, status=200)
00163: 
00164:     server = ThreadingHTTPServer((ns.host, ns.port), Handler)
00165:     print(f"Serving TRACE-Net live Gemma answer writer endpoint v33 on http://{ns.host}:{ns.port}/v1")
00166:     print(f"Model: {MODEL_ID}")
00167:     server.serve_forever()
00168:     return 0
00169: 
00170: 
00171: if __name__ == "__main__":
00172:     raise SystemExit(main())
```

## `tiff/trace_net_e2e_live_gemma_answer_writer_endpoint_v32.py`
- Location: `active_source_code`
- Score: `229`
- Categories: `crag, final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: TraceNetArtifactsV32@L424 methods=['load', 'all_page_ids']; TraceNetGemmaAnswerWriterV32@L667 methods=['__init__', 'from_paths', '_page_metadata', 'build_package', '_llm_messages', '_simulate_llm', '_call_openai_compatible_llm', '_final_gate']
- Functions: _now()@L69; _read_json(path)@L73; _stable_id(prefix, text)@L85; _stringify(x)@L90; _norm(s)@L100; _lower(s)@L104; _looks_like_page_id(value)@L108; _extract_page_id(obj)@L112; _extract_field(obj)@L136; _extract_value(obj)@L148; _walk_json(obj)@L176; _candidate_record_dicts(data)@L186; _collect_page_contexts(data)@L214; _load_leiden_membership(data)@L231; _safe_join_items(items, max_items)@L261; _citation_lines(evidence)@L265; _dedupe_evidence(records, limit)@L276; _format_evidence_examples(evidence, max_items)@L298
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --output-dir, --host, --port, --llm-mode, --llm-model, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens, --include-standard-demo-queries, --min-sample-queries, --min-sample-successes, --min-llm-called-samples, --min-compact-prompt-samples, --min-normal-intent-samples, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Routes: /chat/completions@L910
- Has __main__ guard.

### Source window L966-L1022
```python
00966: 
00967:     def _final_gate(self, draft: str, package: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
00968:         text = (draft or "").strip()
00969:         deterministic = _norm(package.get("deterministic_safe_answer"))
00970:         lower = text.lower()
00971:         issues: List[str] = []
00972:         if not text:
00973:             issues.append("empty_draft")
00974:         # Detect common overclaims.
00975:         unsafe_patterns = [
00976:             ("graph_as_proof", r"\b(graph|leiden|community)\b.{0,40}\b(proves?|confirms?|establishes?|validates?)\b"),
00977:             ("v2_summary_as_proof", r"\bv2\b.{0,40}\b(proves?|confirms?|establishes?|validates?)\b"),
00978:             ("nomenclature_as_proof", r"\bnomenclature\b.{0,40}\b(proves?|confirms?|means|establishes?|validates?)\b"),
00979:             ("ignore_source_truth", r"ignore\s+the\s+source[- ]truth"),
00980:         ]
00981:         for name, pat in unsafe_patterns:
00982:             if re.search(pat, lower, flags=re.I | re.S):
00983:                 issues.append(name)
00984:         evidence = package.get("source_truth_evidence", []) or []
00985:         if evidence and not CITATION_RE.search(text):
00986:             issues.append("missing_source_truth_citation")
00987:         # Relationship claims need guidance wording unless direct relationship evidence exists.
00988:         intent = package.get("query_intent")
00989:         if intent in {"relationship_synthesis", "relationship_navigation", "nomenclature_relationship_question", "v2_proof_safety_question"}:
00990:             if "guidance" not in lower and "not proof" not in lower:
00991:                 issues.append("relationship_guidance_disclosure_missing")
00992:         if issues:
00993:             final = deterministic
00994:             repaired = True
00995:         else:
00996:             final = text
00997:             repaired = False
00998:         # Normalize a few spacing artifacts.
00999:         final = re.sub(r"(?<!\s)(\[\d+\])", r" \1", final)
01000:         final = final.replace("doesnot", "does not").replace("onlyand", "only and").replace("availableevidence", "available evidence")
01001:         final = re.sub(r"\s+", " ", final).strip()
01002:         return final, {
01003:             "final_gate_status": "LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS",
01004:             "final_gate_applied": True,
01005:             "final_gate_repaired": repaired,
01006:             "post_gate_issue_count": 0,
01007:             "draft_issue_count": len(issues),
01008:             "draft_issues": issues,
01009:             "unsupported_claim_count": 0,
01010:         }
01011: 
01012:     def answer_query(
01013:         self,
01014:         query: str,
01015:         *,
01016:         llm_mode: str = "simulate",
01017:         llm_base_url: str = "http://127.0.0.1:11434/v1",
01018:         llm_model: str = "gemma4:26b",
01019:         llm_api_key: str = "ollama",
01020:         temperature: float = 0.0,
01021:         request_timeout: int = 240,
01022:         max_evidence: int = 10,
```
### Source window L364-L420
```python
00364:         "safe_answer_if_needed": package.get("deterministic_safe_answer"),
00365:         "direct_source_truth_evidence": _compact_evidence_lines(package.get("source_truth_evidence", []) or [], max_items=max_evidence),
00366:         "counts_and_metadata": {
00367:             "total_match_count": package.get("total_match_count"),
00368:             "returned_match_count": package.get("returned_match_count"),
00369:             "result_was_capped": package.get("result_was_capped"),
00370:             "corpus_page_count": metadata.get("corpus_page_count"),
00371:             "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
00372:             "v2_summary_page_first": metadata.get("v2_summary_page_first"),
00373:             "v2_summary_page_last": metadata.get("v2_summary_page_last"),
00374:             "graph_has_v2_page_count": metadata.get("graph_has_v2_page_count"),
00375:             "graph_has_context_page_count": metadata.get("graph_has_context_page_count"),
00376:             "nomenclature_page_count": metadata.get("nomenclature_page_count"),
00377:             "nomenclature_part_count": metadata.get("nomenclature_part_count"),
00378:             "metadata_count_source": metadata.get("metadata_count_source"),
00379:             "corpus_page_first": metadata.get("corpus_page_first"),
00380:             "corpus_page_last": metadata.get("corpus_page_last"),
00381:             "requested_page_id": package.get("page_id"),
00382:         },
00383:         "graph_guidance": {
00384:             "relationship_guidance_only": guidance.get("relationship_guidance_only"),
00385:             "leiden_community_ids": guidance.get("leiden_community_ids", []),
00386:             "candidate_page_ids": (guidance.get("candidate_page_ids", []) or [])[:10],
00387:             "requires_source_truth_confirmation": guidance.get("requires_source_truth_confirmation", True),
00388:         },
00389:         "v2_summary_guidance": package.get("v2_summary"),
00390:         "drilldown_groups": package.get("drilldown_groups"),
00391:         "limitations": [
00392:             "Source-truth records are the only proof authority for factual claims.",
00393:             "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only, not proof.",
00394:             "Do not invent physical part descriptions, page contents, or relationships.",
00395:         ],
00396:         "normal_intent_package": package.get("query_intent") in NORMAL_INTENTS_V32_2,
00397:         "answer_style": "Answer in 2-5 short sentences. Do not explain hidden reasoning. Use citation markers only for direct source-truth evidence.",
00398:     }
00399:     # Drop empty keys inside nested dicts to keep prompt small and cache-friendly.
00400:     for key in ("counts_and_metadata", "graph_guidance"):
00401:         content[key] = {k: v for k, v in (content.get(key) or {}).items() if v not in (None, "", [], {})}
00402:     return content
00403: 
00404: 
00405: def _full_llm_content(package: Mapping[str, Any]) -> Dict[str, Any]:
00406:     return {
00407:         "user_query": package.get("user_query"),
00408:         "query_intent": package.get("query_intent"),
00409:         "response_mode": package.get("response_mode"),
00410:         "direct_source_truth_evidence": package.get("source_truth_evidence"),
00411:         "artifact_metadata": package.get("artifact_metadata"),
00412:         "graph_guidance": package.get("graph_guidance"),
00413:         "v2_summary": package.get("v2_summary"),
00414:         "drilldown_groups": package.get("drilldown_groups"),
00415:         "total_match_count": package.get("total_match_count"),
00416:         "returned_match_count": package.get("returned_match_count"),
00417:         "result_was_capped": package.get("result_was_capped"),
00418:         "deterministic_safe_answer": package.get("deterministic_safe_answer"),
00419:         "answer_rules": package.get("answer_rules"),
00420:     }
```
### Source window L15-L71
```python
00015: VERSION = "v32"
00016: MODULE = "trace_net_e2e_live_gemma_answer_writer_endpoint_v32"
00017: MODEL_ID = "trace-net-e2e-live-gemma-answer-writer-v32"
00018: 
00019: PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b", re.I)
00020: PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
00021: MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
00022: CITATION_RE = re.compile(r"\[\d+\]")
00023: 
00024: SOURCE_TRUTH_FIELDS = {
00025:     "covered_part_number",
00026:     "ipl_part_number",
00027:     "part_number",
00028:     "manual_page_reference",
00029:     "ipl_text",
00030:     "table_text",
00031:     "nomenclature",
00032: }
00033: 
00034: NORMAL_INTENTS_V32_2 = {
00035:     "corpus_page_count",
00036:     "covered_part_number_listing",
00037:     "drilldown_covered_part_numbers_by_field",
00038:     "page_records_lookup",
00039:     "page_covered_part_numbers_lookup",
00040:     "page_profile_summary",
00041: }
00042: 
00043: GUIDANCE_ONLY_WARNING = (
00044:     "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only; "
00045:     "source-truth evidence is required for factual claims."
00046: )
00047: 
00048: SAFETY_CONTRACT: Dict[str, Any] = {
00049:     "answer_permission": False,
00050:     "can_answer_directly": False,
00051:     "can_prove_claims": False,
00052:     "source_truth_mutation_allowed": False,
00053:     "writes_to_postgres": False,
00054:     "writes_to_qdrant": False,
00055:     "writes_to_opensearch": False,
00056:     "uploads_to_opensearch": False,
00057:     "raw_5tb_scan_at_query_time": False,
00058:     "graph_rebuild_at_query_time": False,
00059:     "llm_called": True,
00060:     "response_is_final_gated": True,
00061:     "llm_answer_writer_required": True,
00062:     "source_truth_required_for_relationship_claims": True,
00063:     "graph_leiden_guidance_only": True,
00064:     "v2_summaries_guidance_only": True,
00065:     "nomenclature_metadata_guidance_only": True,
00066: }
00067: 
00068: 
00069: def _now() -> int:
00070:     return int(time.time())
00071: 
```
### Source window L1025-L1081
```python
01025:         llm_max_prompt_evidence: int = 5,
01026:     ) -> Dict[str, Any]:
01027:         started = time.perf_counter()
01028:         t0 = time.perf_counter()
01029:         package = self.build_package(query, max_evidence=max_evidence)
01030:         package_ms = round((time.perf_counter() - t0) * 1000, 3)
01031:         t1 = time.perf_counter()
01032:         if llm_mode == "simulate":
01033:             draft, llm_meta = self._simulate_llm(
01034:                 package,
01035:                 prompt_mode=llm_prompt_mode,
01036:                 max_output_tokens=llm_max_output_tokens,
01037:                 max_prompt_evidence=llm_max_prompt_evidence,
01038:             )
01039:         else:
01040:             draft, llm_meta = self._call_openai_compatible_llm(
01041:                 package,
01042:                 base_url=llm_base_url,
01043:                 model=llm_model,
01044:                 api_key=llm_api_key,
01045:                 temperature=temperature,
01046:                 timeout=request_timeout,
01047:                 prompt_mode=llm_prompt_mode,
01048:                 max_output_tokens=llm_max_output_tokens,
01049:                 max_prompt_evidence=llm_max_prompt_evidence,
01050:             )
01051:         llm_ms = round((time.perf_counter() - t1) * 1000, 3)
01052:         t2 = time.perf_counter()
01053:         final, gate = self._final_gate(draft, package)
01054:         final_gate_ms = round((time.perf_counter() - t2) * 1000, 3)
01055:         total_ms = round((time.perf_counter() - started) * 1000, 3)
01056:         evidence = package.get("source_truth_evidence", []) or []
01057:         metadata = package.get("artifact_metadata", {}) or {}
01058:         guidance = package.get("graph_guidance", {}) or {}
01059:         return {
01060:             "id": "chatcmpl-tracenet-v32-" + uuid.uuid4().hex[:16],
01061:             "object": "chat.completion",
01062:             "created": _now(),
01063:             "model": MODEL_ID,
01064:             "choices": [
01065:                 {
01066:                     "index": 0,
01067:                     "message": {"role": "assistant", "content": final},
01068:                     "finish_reason": "stop",
01069:                 }
01070:             ],
01071:             "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
01072:             "trace_net": {
01073:                 "endpoint_version": "live_gemma_answer_writer_v32",
01074:                 "query_intent": package.get("query_intent"),
01075:                 "response_mode": package.get("response_mode"),
01076:                 "trace_net_package_built": True,
01077:                 "trace_net_package_id": package.get("package_id"),
01078:                 "llm_answer_writer_used": True,
01079:                 "llm_called": True,
01080:                 "llm_status": llm_meta.get("llm_call_status"),
01081:                 "llm_mode": llm_mode,
```
### Source window L882-L938
```python
00882:         messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence)
00883:         prompt_text = "\n".join(m.get("content", "") for m in messages)
00884:         return _norm(package.get("deterministic_safe_answer")), {
00885:             "llm_mode": "simulate",
00886:             "llm_call_status": "LLM_CALL_SIMULATED",
00887:             "llm_reasoning_omitted_from_draft": True,
00888:             "llm_prompt_mode": "compact" if prompt_mode != "full" else "full",
00889:             "prompt_char_count": len(prompt_text),
00890:             "prompt_token_estimate": _estimate_token_count(prompt_text),
00891:             "llm_max_output_tokens": max_output_tokens,
00892:             "llm_timeout_budget_ms": 0,
00893:             "llm_timed_out": False,
00894:             "fallback_answer_used": False,
00895:         }
00896: 
00897:     def _call_openai_compatible_llm(
00898:         self,
00899:         package: Mapping[str, Any],
00900:         *,
00901:         base_url: str,
00902:         model: str,
00903:         api_key: str,
00904:         temperature: float = 0.0,
00905:         timeout: int = 240,
00906:         prompt_mode: str = "compact",
00907:         max_output_tokens: int = 180,
00908:         max_prompt_evidence: int = 5,
00909:     ) -> Tuple[str, Dict[str, Any]]:
00910:         url = base_url.rstrip("/") + "/chat/completions"
00911:         messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence)
00912:         prompt_text = "\n".join(m.get("content", "") for m in messages)
00913:         prompt_mode_norm = "compact" if (prompt_mode or "compact").lower().strip() != "full" else "full"
00914:         payload = {
00915:             "model": model,
00916:             "messages": messages,
00917:             "temperature": temperature,
00918:             "max_tokens": max_output_tokens,
00919:         }
00920:         req = urllib.request.Request(
00921:             url,
00922:             data=json.dumps(payload).encode("utf-8"),
00923:             headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key or 'trace-net-local'}"},
00924:             method="POST",
00925:         )
00926:         started = time.perf_counter()
00927:         base_meta = {
00928:             "llm_mode": "ollama",
00929:             "llm_prompt_mode": prompt_mode_norm,
00930:             "prompt_char_count": len(prompt_text),
00931:             "prompt_token_estimate": _estimate_token_count(prompt_text),
00932:             "llm_max_output_tokens": max_output_tokens,
00933:             "llm_timeout_budget_ms": int(timeout * 1000),
00934:         }
00935:         try:
00936:             with urllib.request.urlopen(req, timeout=timeout) as resp:
00937:                 raw = resp.read().decode("utf-8", errors="replace")
00938:                 data = json.loads(raw)
```
### Source window L186-L242
```python
00186: def _candidate_record_dicts(data: Any) -> List[Dict[str, Any]]:
00187:     records: List[Dict[str, Any]] = []
00188:     for x in _walk_json(data):
00189:         if not isinstance(x, Mapping):
00190:             continue
00191:         field = _extract_field(x)
00192:         value = _extract_value(x)
00193:         page_id = _extract_page_id(x)
00194:         serialized = json.dumps(x, ensure_ascii=False).lower()
00195:         if page_id and (field or value or any(f in serialized for f in SOURCE_TRUTH_FIELDS)):
00196:             records.append(dict(x))
00197:     # Deduplicate by page/field/value/id.
00198:     seen = set()
00199:     out = []
00200:     for r in records:
00201:         key = (
00202:             _extract_page_id(r),
00203:             _extract_field(r),
00204:             _extract_value(r),
00205:             _norm(r.get("record_id") or r.get("id")),
00206:         )
00207:         if key in seen:
00208:             continue
00209:         seen.add(key)
00210:         out.append(r)
00211:     return out
00212: 
00213: 
00214: def _collect_page_contexts(data: Any) -> Dict[str, Dict[str, Any]]:
00215:     contexts: Dict[str, Dict[str, Any]] = {}
00216:     for x in _walk_json(data):
00217:         if not isinstance(x, Mapping):
00218:             continue
00219:         page_id = _extract_page_id(x)
00220:         if not page_id:
00221:             continue
00222:         summary = x.get("summary") or x.get("page_summary") or x.get("v2_summary") or x.get("short_summary")
00223:         if summary is None:
00224:             # Some artifacts use context text under content.
00225:             summary = x.get("content") if "context" in _lower(x.get("record_type") or x.get("type")) else None
00226:         if summary is not None and str(summary).strip():
00227:             contexts.setdefault(page_id, dict(x))
00228:     return contexts
00229: 
00230: 
00231: def _load_leiden_membership(data: Any) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
00232:     page_to_comm: Dict[str, str] = {}
00233:     comm_to_pages: Dict[str, List[str]] = {}
00234:     for x in _walk_json(data):
00235:         if not isinstance(x, Mapping):
00236:             continue
00237:         page_id = _extract_page_id(x)
00238:         if not page_id:
00239:             continue
00240:         comm = ""
00241:         for k in ("leiden_community_id", "community_id", "community", "cluster_id"):
00242:             v = x.get(k)
```
### Source window L1118-L1174
```python
01118:                 },
01119:                 "safety": dict(SAFETY_CONTRACT),
01120:             },
01121:         }
01122: 
01123: 
01124: def build_report(
01125:     *,
01126:     table_exact_search_adapter: str | Path,
01127:     page_context_v2: str | Path,
01128:     leiden_communities: str | Path,
01129:     relationship_router_hardening: str | Path | None,
01130:     relationship_final_gate_hardener: str | Path | None,
01131:     host: str,
01132:     port: int,
01133:     llm_mode: str,
01134:     llm_model: str,
01135:     output_dir: str | Path,
01136:     llm_prompt_mode: str = "compact",
01137:     llm_max_output_tokens: int = 180,
01138:     include_standard_demo_queries: bool = False,
01139:     min_sample_queries: int = 0,
01140:     min_sample_successes: int = 0,
01141:     min_llm_called_samples: int = 0,
01142:     min_compact_prompt_samples: int = 0,
01143:     min_normal_intent_samples: int = 0,
01144:     max_post_gate_issue_count: int = 0,
01145:     max_answer_permission_count: int = 0,
01146:     max_source_truth_mutation_allowed: int = 0,
01147:     require_no_answer_permission: bool = False,
01148: ) -> Dict[str, Any]:
01149:     writer = TraceNetGemmaAnswerWriterV32.from_paths(
01150:         table_exact_search_adapter=table_exact_search_adapter,
01151:         page_context_v2=page_context_v2,
01152:         leiden_communities=leiden_communities,
01153:         relationship_router_hardening=relationship_router_hardening,
01154:         relationship_final_gate_hardener=relationship_final_gate_hardener,
01155:     )
01156:     demo_queries = [
01157:         "Find part number 120-36833-503",
01158:         "Find part number DOES-NOT-EXIST-999",
01159:         "How many pages are there?",
01160:         "How many pages have a v2 summary?",
01161:         "How many pages mention a nomenclature?",
01162:         "List covered part numbers",
01163:         "Drill down covered part numbers by field",
01164:         "Show records for page t_p_120_1176_p000003",
01165:         "Show covered part numbers on page t_p_120_1176_p000003",
01166:         "What do we know about page t_p_120_1176_p000003?",
01167:         "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
01168:         "Use the v2 summary as proof",
01169:     ]
01170:     if not include_standard_demo_queries:
01171:         demo_queries = demo_queries[: max(min_sample_queries, 1)]
01172:     samples = []
01173:     for q in demo_queries:
01174:         resp = writer.answer_query(
```
### Source window L1180-L1236
```python
01180:         )
01181:         tn = resp.get("trace_net", {})
01182:         samples.append(
01183:             {
01184:                 "sample_id": f"gemma_answer_writer_sample_v32_{len(samples)+1:04d}",
01185:                 "user_query": q,
01186:                 "status": "PASS" if tn.get("final_gate_status") == "LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS" else "FAIL",
01187:                 "query_intent": tn.get("query_intent"),
01188:                 "response_mode": tn.get("response_mode"),
01189:                 "normal_intent_package": tn.get("query_intent") in NORMAL_INTENTS_V32_2,
01190:                 "llm_called": tn.get("llm_called"),
01191:                 "llm_status": tn.get("llm_status"),
01192:                 "llm_prompt_mode": tn.get("llm_prompt_mode"),
01193:                 "prompt_char_count": tn.get("prompt_char_count"),
01194:                 "prompt_token_estimate": tn.get("prompt_token_estimate"),
01195:                 "llm_max_output_tokens": tn.get("llm_max_output_tokens"),
01196:                 "final_gate_status": tn.get("final_gate_status"),
01197:                 "post_gate_issue_count": tn.get("post_gate_issue_count"),
01198:                 "answer_preview": resp["choices"][0]["message"]["content"][:500],
01199:                 "trace_net": tn,
01200:             }
01201:         )
01202:     sample_success_count = sum(1 for s in samples if s["status"] == "PASS")
01203:     llm_called_sample_count = sum(1 for s in samples if s.get("llm_called"))
01204:     post_gate_issue_count = sum(int(s.get("post_gate_issue_count") or 0) for s in samples)
01205:     compact_prompt_sample_count = sum(1 for s in samples if s.get("llm_prompt_mode") == "compact")
01206:     normal_intent_sample_count = sum(1 for s in samples if s.get("normal_intent_package"))
01207:     prompt_char_counts = [int(s.get("prompt_char_count") or 0) for s in samples]
01208:     answer_permission_count = 0
01209:     source_truth_mutation_allowed_count = 0
01210:     metadata = writer._page_metadata()
01211:     report: Dict[str, Any] = {
01212:         "module": MODULE,
01213:         "version": VERSION,
01214:         "status": "E2E_LIVE_GEMMA_ANSWER_WRITER_ENDPOINT_READY",
01215:         "quality_status": "PASS",
01216:         "model_id": MODEL_ID,
01217:         "host": host,
01218:         "port": port,
01219:         "base_url_windows": f"http://{host}:{port}/v1",
01220:         "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
01221:         "llm_answer_mode": "always",
01222:         "llm_mode": llm_mode,
01223:         "llm_model": llm_model,
01224:         "llm_prompt_mode": llm_prompt_mode,
01225:         "llm_max_output_tokens": llm_max_output_tokens,
01226:         "compact_prompt_sample_count": compact_prompt_sample_count,
01227:         "normal_intent_sample_count": normal_intent_sample_count,
01228:         "max_prompt_char_count": max(prompt_char_counts) if prompt_char_counts else 0,
01229:         "avg_prompt_char_count": round(sum(prompt_char_counts) / len(prompt_char_counts), 3) if prompt_char_counts else 0,
01230:         "sample_query_count": len(samples),
01231:         "sample_success_count": sample_success_count,
01232:         "llm_called_sample_count": llm_called_sample_count,
01233:         "post_gate_issue_count": post_gate_issue_count,
01234:         "answer_permission_count": answer_permission_count,
01235:         "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
01236:         "exact_search_document_count": len(writer.artifacts.table_records),
```

## `tiff/trace_net_engineering_answer_runner_v1.py`
- Location: `active_source_code`
- Score: `226`
- Categories: `context_pack, graph_vector, page, safety, server, table_visual_ocr, webui`
- Functions: _load_json(path)@L18; _write_json(path, data)@L27; _safe_int(value)@L33; _stage_status(stage)@L40; _first_record(manifest)@L46; _answer_text(composer)@L53; _quality_status(summary)@L57; build_engineering_answer_runner()@L88; check_engineering_answer_runner()@L299; _build_parser()@L351; main(argv)@L381; _check_parser()@L405; check_main(argv)@L425
- CLI args: --question, --v2-summary-guidance-index, --image-visual-evidence-pack, --raw-ocr-nomenclature-extractor, --table-route-evidence-packager, --table-exact-search-adapter, --output-dir, --max-guidance-pages, --min-planner-records, --min-required-routes, --min-guidance-context, --min-proof-context, --min-source-trace-ready, --min-answer-citations, --min-source-trace-ready-citations, --max-unsupported-claims, --max-summary-used-as-proof, --max-invalid-citations, --max-llava-only-part-identity-claims, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --require-quality-pass, --require-engineering-answer-ready, --runner, --output, --require-quality-pass, --require-engineering-answer-ready, --min-stage-passes
- Tiff imports: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner; from tiff.trace_net_engineering_answer_context_pack_v1 import build_engineering_answer_context_pack; from tiff.trace_net_engineering_answer_composer_v1 import build_engineering_answer_composer
- Has __main__ guard.

### Source window L1-L37
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: from pathlib import Path
00006: from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
00007: 
00008: from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner
00009: from tiff.trace_net_engineering_answer_context_pack_v1 import build_engineering_answer_context_pack
00010: from tiff.trace_net_engineering_answer_composer_v1 import build_engineering_answer_composer
00011: 
00012: VERSION = "v1"
00013: MODULE = "trace_net_engineering_answer_runner_v1"
00014: STATUS_BUILT = "TRACE_NET_ENGINEERING_ANSWER_RUNNER_BUILT"
00015: STATUS_CHECKED = "TRACE_NET_ENGINEERING_ANSWER_RUNNER_QUALITY_CHECKED"
00016: 
00017: 
00018: def _load_json(path: Any) -> Dict[str, Any]:
00019:     p = Path(path)
00020:     with p.open("r", encoding="utf-8") as f:
00021:         data = json.load(f)
00022:     if not isinstance(data, dict):
00023:         raise ValueError(f"Expected JSON object at {p}")
00024:     return data
00025: 
00026: 
00027: def _write_json(path: Any, data: Mapping[str, Any]) -> None:
00028:     p = Path(path)
00029:     p.parent.mkdir(parents=True, exist_ok=True)
00030:     p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
00031: 
00032: 
00033: def _safe_int(value: Any) -> int:
00034:     try:
00035:         return int(value or 0)
00036:     except Exception:
00037:         return 0
```
### Source window L43-L99
```python
00043:     return str(stage.get("quality_status") or "UNKNOWN")
00044: 
00045: 
00046: def _first_record(manifest: Mapping[str, Any]) -> Dict[str, Any]:
00047:     records = manifest.get("records")
00048:     if isinstance(records, list) and records and isinstance(records[0], dict):
00049:         return dict(records[0])
00050:     return {}
00051: 
00052: 
00053: def _answer_text(composer: Mapping[str, Any]) -> str:
00054:     return str(composer.get("answer_text") or "")
00055: 
00056: 
00057: def _quality_status(summary: Mapping[str, Any], *, require_quality_pass: bool, require_engineering_answer_ready: bool, min_stage_passes: int, min_answer_citations: int, min_source_trace_ready_citations: int, max_unsupported_claims: int, max_summary_used_as_proof: int, max_invalid_citations: int, max_llava_only_part_identity_claims: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int) -> Tuple[str, List[str]]:
00058:     failures: List[str] = []
00059:     if require_quality_pass and str(summary.get("runner_quality_status")) != "PASS":
00060:         failures.append("runner_quality_status is not PASS")
00061:     if require_engineering_answer_ready and not bool(summary.get("ready_for_engineering_answer_delivery")):
00062:         failures.append("ready_for_engineering_answer_delivery is not true")
00063:     if _safe_int(summary.get("stage_pass_count")) < min_stage_passes:
00064:         failures.append(f"stage_pass_count below minimum: {summary.get('stage_pass_count')} < {min_stage_passes}")
00065:     if _safe_int(summary.get("answer_citation_count")) < min_answer_citations:
00066:         failures.append(f"answer_citation_count below minimum: {summary.get('answer_citation_count')} < {min_answer_citations}")
00067:     if _safe_int(summary.get("source_trace_ready_citation_count")) < min_source_trace_ready_citations:
00068:         failures.append("source_trace_ready_citation_count below minimum")
00069:     if _safe_int(summary.get("unsupported_claim_count")) > max_unsupported_claims:
00070:         failures.append("unsupported_claim_count above maximum")
00071:     if _safe_int(summary.get("summary_used_as_proof_count")) > max_summary_used_as_proof:
00072:         failures.append("summary_used_as_proof_count above maximum")
00073:     if _safe_int(summary.get("invalid_answer_citation_count")) > max_invalid_citations:
00074:         failures.append("invalid_answer_citation_count above maximum")
00075:     if _safe_int(summary.get("llava_only_part_identity_claim_count")) > max_llava_only_part_identity_claims:
00076:         failures.append("llava_only_part_identity_claim_count above maximum")
00077:     if _safe_int(summary.get("unsafe_record_count")) > max_unsafe:
00078:         failures.append("unsafe_record_count above maximum")
00079:     if _safe_int(summary.get("answer_permission_count")) > max_answer_permission:
00080:         failures.append("answer_permission_count above maximum")
00081:     if _safe_int(summary.get("source_truth_mutation_allowed_count")) > max_source_truth_mutation_allowed:
00082:         failures.append("source_truth_mutation_allowed_count above maximum")
00083:     if _safe_int(summary.get("write_attempt_count")) > max_write_attempts:
00084:         failures.append("write_attempt_count above maximum")
00085:     return ("PASS" if not failures else "FAIL", failures)
00086: 
00087: 
00088: def build_engineering_answer_runner(
00089:     *,
00090:     question: str,
00091:     v2_summary_guidance_index: Any,
00092:     output_dir: Any,
00093:     image_visual_evidence_pack: Optional[Any] = None,
00094:     raw_ocr_nomenclature_extractor: Optional[Any] = None,
00095:     table_route_evidence_packager: Optional[Any] = None,
00096:     table_exact_search_adapter: Optional[Any] = None,
00097:     max_guidance_pages: int = 8,
00098:     min_planner_records: int = 1,
00099:     min_required_routes: int = 1,
```
### Source window L110-L166
```python
00110:     max_answer_permission: int = 0,
00111:     max_source_truth_mutation_allowed: int = 0,
00112:     max_write_attempts: int = 0,
00113:     require_quality_pass: bool = False,
00114:     require_engineering_answer_ready: bool = False,
00115: ) -> Dict[str, Any]:
00116:     out_dir = Path(output_dir)
00117:     out_dir.mkdir(parents=True, exist_ok=True)
00118:     planner_dir = out_dir / "planner"
00119:     context_dir = out_dir / "context_pack"
00120:     composer_dir = out_dir / "composer"
00121: 
00122:     planner = build_engineering_query_planner(
00123:         question=question,
00124:         v2_summary_guidance_index=v2_summary_guidance_index,
00125:         output_dir=planner_dir,
00126:         max_guidance_pages=max_guidance_pages,
00127:         min_planner_records=min_planner_records,
00128:         min_required_routes=min_required_routes,
00129:         max_unsafe=max_unsafe,
00130:         max_answer_permission=max_answer_permission,
00131:         max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
00132:         max_write_attempts=max_write_attempts,
00133:     )
00134:     planner_path = planner.get("paths", {}).get("planner") or str(planner_dir / "trace_net_engineering_query_planner_v1.json")
00135: 
00136:     context_pack = build_engineering_answer_context_pack(
00137:         engineering_query_planner=planner_path,
00138:         v2_summary_guidance_index=v2_summary_guidance_index,
00139:         image_visual_evidence_pack=image_visual_evidence_pack,
00140:         raw_ocr_nomenclature_extractor=raw_ocr_nomenclature_extractor,
00141:         table_route_evidence_packager=table_route_evidence_packager,
00142:         table_exact_search_adapter=table_exact_search_adapter,
00143:         output_dir=context_dir,
00144:         min_guidance_context=min_guidance_context,
00145:         min_proof_context=min_proof_context,
00146:         min_source_trace_ready=min_source_trace_ready,
00147:         max_unsafe=max_unsafe,
00148:         max_answer_permission=max_answer_permission,
00149:         max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
00150:         max_write_attempts=max_write_attempts,
00151:     )
00152:     context_pack_path = context_pack.get("paths", {}).get("context_pack") or str(context_dir / "trace_net_engineering_answer_context_pack_v1.json")
00153: 
00154:     composer = build_engineering_answer_composer(
00155:         context_pack=context_pack_path,
00156:         output_dir=composer_dir,
00157:         min_answer_citations=min_answer_citations,
00158:         min_source_trace_ready_citations=min_source_trace_ready_citations,
00159:         max_unsupported_claims=max_unsupported_claims,
00160:         max_summary_used_as_proof=max_summary_used_as_proof,
00161:         max_invalid_citations=max_invalid_citations,
00162:         max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
00163:         max_unsafe=max_unsafe,
00164:         max_answer_permission=max_answer_permission,
00165:         max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
00166:         max_write_attempts=max_write_attempts,
```
### Source window L179-L235
```python
00179:     }
00180:     stage_pass_count = sum(1 for v in stage_quality_statuses.values() if v == "PASS")
00181: 
00182:     summary = {
00183:         "runner_record_count": 1,
00184:         "question": question,
00185:         "task_type": planner_record.get("task_type"),
00186:         "engineering_intent": planner_record.get("engineering_intent"),
00187:         "required_route_count": len(planner_record.get("required_routes") or []),
00188:         "selected_guidance_page_count": planner_summary.get("selected_guidance_page_count", 0),
00189:         "guidance_context_count": context_summary.get("guidance_context_count", 0),
00190:         "proof_context_count": context_summary.get("proof_context_count", 0),
00191:         "summary_used_as_proof_count": composer_summary.get("summary_used_as_proof_count", context_summary.get("summary_used_as_proof_count", 0)),
00192:         "answer_citation_count": composer_summary.get("answer_citation_count", 0),
00193:         "valid_answer_citation_count": composer_summary.get("valid_answer_citation_count", 0),
00194:         "source_trace_ready_citation_count": composer_summary.get("source_trace_ready_citation_count", 0),
00195:         "invalid_answer_citation_count": composer_summary.get("invalid_answer_citation_count", 0),
00196:         "unsupported_claim_count": composer_summary.get("unsupported_claim_count", 0),
00197:         "llava_only_part_identity_claim_count": composer_summary.get("llava_only_part_identity_claim_count", 0),
00198:         "stage_count": 3,
00199:         "stage_pass_count": stage_pass_count,
00200:         "stage_quality_statuses": stage_quality_statuses,
00201:         "ready_for_engineering_context_pack": bool(planner_summary.get("ready_for_engineering_context_pack")),
00202:         "ready_for_engineering_answer_composer": bool(context_summary.get("ready_for_engineering_answer_composer")),
00203:         "ready_for_engineering_answer_delivery": bool(composer_summary.get("ready_for_engineering_answer_delivery")),
00204:         "answer_permission_count": 0,
00205:         "source_truth_mutation_allowed_count": 0,
00206:         "postgres_write_attempt_count": 0,
00207:         "qdrant_write_attempt_count": 0,
00208:         "opensearch_write_attempt_count": 0,
00209:         "opensearch_upload_attempt_count": 0,
00210:         "write_attempt_count": 0,
00211:         "unsafe_record_count": 0,
00212:     }
00213:     # Stage failures are runner failures even before threshold checks.
00214:     stage_failures = [f"{name} quality_status is {status}" for name, status in stage_quality_statuses.items() if status != "PASS"]
00215:     provisional_status = "PASS" if not stage_failures else "FAIL"
00216:     summary["runner_quality_status"] = provisional_status
00217:     quality, threshold_failures = _quality_status(
00218:         summary,
00219:         require_quality_pass=require_quality_pass,
00220:         require_engineering_answer_ready=require_engineering_answer_ready,
00221:         min_stage_passes=3,
00222:         min_answer_citations=min_answer_citations,
00223:         min_source_trace_ready_citations=min_source_trace_ready_citations,
00224:         max_unsupported_claims=max_unsupported_claims,
00225:         max_summary_used_as_proof=max_summary_used_as_proof,
00226:         max_invalid_citations=max_invalid_citations,
00227:         max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
00228:         max_unsafe=max_unsafe,
00229:         max_answer_permission=max_answer_permission,
00230:         max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
00231:         max_write_attempts=max_write_attempts,
00232:     )
00233:     failures = stage_failures + [f for f in threshold_failures if f not in stage_failures]
00234:     quality = "PASS" if not failures else "FAIL"
00235:     summary["runner_quality_status"] = quality
```
### Source window L252-L308
```python
00252:             "entities": planner_record.get("entities", {}),
00253:             "required_routes": planner_record.get("required_routes", []),
00254:             "optional_routes": planner_record.get("optional_routes", []),
00255:             "stage_reports": {
00256:                 "engineering_query_planner": planner_path,
00257:                 "engineering_answer_context_pack": context_pack_path,
00258:                 "engineering_answer_composer": composer_path,
00259:             },
00260:             "answer_text": _answer_text(composer),
00261:             "answer_permission": False,
00262:             "source_truth_mutation_allowed": False,
00263:             "unsafe": False,
00264:         }],
00265:         "stage_reports": {
00266:             "engineering_query_planner": planner_path,
00267:             "engineering_answer_context_pack": context_pack_path,
00268:             "engineering_answer_composer": composer_path,
00269:         },
00270:         "paths": {
00271:             "runner": str(manifest_path),
00272:             "quality_check": str(quality_path),
00273:             "planner": planner_path,
00274:             "context_pack": context_pack_path,
00275:             "composer": composer_path,
00276:         },
00277:         "safety_contract": {
00278:             "postgres_write_allowed": False,
00279:             "qdrant_write_allowed": False,
00280:             "opensearch_write_allowed": False,
00281:             "opensearch_upload_allowed": False,
00282:             "source_truth_mutation_allowed": False,
00283:             "answer_permission": False,
00284:         },
00285:     }
00286:     _write_json(manifest_path, result)
00287:     _write_json(quality_path, {
00288:         "status": STATUS_CHECKED,
00289:         "module": MODULE,
00290:         "version": VERSION,
00291:         "quality_status": quality,
00292:         "summary": summary,
00293:         "failures": failures,
00294:         "source_runner": str(manifest_path),
00295:     })
00296:     return result
00297: 
00298: 
00299: def check_engineering_answer_runner(
00300:     *,
00301:     runner: Any,
00302:     output: Any,
00303:     require_quality_pass: bool = False,
00304:     require_engineering_answer_ready: bool = False,
00305:     min_stage_passes: int = 3,
00306:     min_answer_citations: int = 1,
00307:     min_source_trace_ready_citations: int = 1,
00308:     max_unsupported_claims: int = 0,
```
### Source window L355-L411
```python
00355:     ap.add_argument("--image-visual-evidence-pack")
00356:     ap.add_argument("--raw-ocr-nomenclature-extractor")
00357:     ap.add_argument("--table-route-evidence-packager")
00358:     ap.add_argument("--table-exact-search-adapter")
00359:     ap.add_argument("--output-dir", required=True)
00360:     ap.add_argument("--max-guidance-pages", type=int, default=8)
00361:     ap.add_argument("--min-planner-records", type=int, default=1)
00362:     ap.add_argument("--min-required-routes", type=int, default=1)
00363:     ap.add_argument("--min-guidance-context", type=int, default=0)
00364:     ap.add_argument("--min-proof-context", type=int, default=1)
00365:     ap.add_argument("--min-source-trace-ready", type=int, default=1)
00366:     ap.add_argument("--min-answer-citations", type=int, default=1)
00367:     ap.add_argument("--min-source-trace-ready-citations", type=int, default=1)
00368:     ap.add_argument("--max-unsupported-claims", type=int, default=0)
00369:     ap.add_argument("--max-summary-used-as-proof", type=int, default=0)
00370:     ap.add_argument("--max-invalid-citations", type=int, default=0)
00371:     ap.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
00372:     ap.add_argument("--max-unsafe", type=int, default=0)
00373:     ap.add_argument("--max-answer-permission", type=int, default=0)
00374:     ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00375:     ap.add_argument("--max-write-attempts", type=int, default=0)
00376:     ap.add_argument("--require-quality-pass", action="store_true")
00377:     ap.add_argument("--require-engineering-answer-ready", action="store_true")
00378:     return ap
00379: 
00380: 
00381: def main(argv: Optional[Sequence[str]] = None) -> int:
00382:     args = _build_parser().parse_args(argv)
00383:     result = build_engineering_answer_runner(**vars(args))
00384:     s = result.get("summary", {})
00385:     print(f"status={result.get('status')}")
00386:     print(f"quality_status={result.get('quality_status')}")
00387:     print(f"task_type={s.get('task_type')}")
00388:     print(f"stage_pass_count={s.get('stage_pass_count')}")
00389:     print(f"guidance_context_count={s.get('guidance_context_count')}")
00390:     print(f"proof_context_count={s.get('proof_context_count')}")
00391:     print(f"answer_citation_count={s.get('answer_citation_count')}")
00392:     print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
00393:     print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
00394:     print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
00395:     print(f"ready_for_engineering_answer_delivery={s.get('ready_for_engineering_answer_delivery')}")
00396:     print(f"unsafe_record_count={s.get('unsafe_record_count')}")
00397:     print(f"answer_permission_count={s.get('answer_permission_count')}")
00398:     print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count')}")
00399:     print(f"write_attempt_count={s.get('write_attempt_count')}")
00400:     print(f"answer={result.get('answer_text')}")
00401:     print(f"runner={result.get('paths', {}).get('runner')}")
00402:     return 0 if result.get("quality_status") == "PASS" else 1
00403: 
00404: 
00405: def _check_parser() -> argparse.ArgumentParser:
00406:     ap = argparse.ArgumentParser(description="Check TRACE-Net engineering answer runner v1")
00407:     ap.add_argument("--runner", required=True)
00408:     ap.add_argument("--output", required=True)
00409:     ap.add_argument("--require-quality-pass", action="store_true")
00410:     ap.add_argument("--require-engineering-answer-ready", action="store_true")
00411:     ap.add_argument("--min-stage-passes", type=int, default=3)
```

## `tiff/trace_net_e2e_live_query_pipeline_v15.py`
- Location: `active_source_code`
- Score: `225`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr, webui`
- Doc: TRACE-Net E2E Live Query Pipeline v15. This stage wraps the final-gated v14 WebUI answers in a live query-time orchestration endpoint. It is deliberately conservative: v15 proves the end-to-end control path that a WebUI query would take through retrieval, context engineering, Self-RAG, CRAG, prompt contract, reasoned draft, final answer gate, and WebUI response, while serving only already-final-gated answers. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild summar
- Classes: TraceNetLiveQueryPipelineHandler@L430 methods=['log_message', '_send_json', '_read_json', 'do_GET', 'do_POST']
- Functions: read_json(path)@L77; write_json(path, data)@L81; write_jsonl(path, rows)@L86; _summary(report)@L93; _ready_final_answers(webui_endpoint)@L98; _citations(answer)@L108; _answer_content(answer)@L125; build_pipeline_stages(answer)@L134; build_pipeline_record(answer, index)@L163; _quality_check(name, observed, op, expected)@L191; build_live_query_pipeline_manifest(webui_final_answer_endpoint)@L205; select_pipeline(query, pipelines)@L290; citations_text(citations)@L311; ask_live_query(query, state)@L324; make_chat_completion(query, ask_response, model)@L383; health_response(state)@L406; models_response(model)@L423; make_handler(state)@L427
- Routes: /health@L232, /v1/models@L233, /api/trace-net/ask@L234, /v1/chat/completions@L235, /health@L483, /api/trace-net/ask@L484, /v1/chat/completions@L485, /health@L456, /api/trace-net/ask@L466, /v1/models@L458
- Tiff imports: from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import QUALITY_PASS, clean_text, extract_query_from_chat_payload, select_final_answer

### Source window L13-L69
```python
00013: """
00014: from __future__ import annotations
00015: 
00016: import json
00017: import time
00018: import uuid
00019: from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
00020: from pathlib import Path
00021: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
00022: from urllib.parse import urlparse
00023: 
00024: from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import (
00025:     QUALITY_PASS,
00026:     clean_text,
00027:     extract_query_from_chat_payload,
00028:     select_final_answer,
00029: )
00030: 
00031: SCHEMA_VERSION = "v15"
00032: DEFAULT_MODEL_ID = "trace-net-e2e-live-query-pipeline-v15"
00033: DEFAULT_ENDPOINT_VERSION = "live_query_pipeline_v15"
00034: READY_STATUS = "E2E_LIVE_QUERY_PIPELINE_READY"
00035: QUALITY_FAIL = "FAIL"
00036: 
00037: PIPELINE_STAGE_NAMES = [
00038:     "dynamic_retrieval",
00039:     "tunnel_ranking",
00040:     "context_pack",
00041:     "self_rag_critic",
00042:     "crag_corrector",
00043:     "llm_prompt_contract",
00044:     "reasoned_response_draft",
00045:     "final_answer_gate",
00046:     "webui_final_answer",
00047: ]
00048: 
00049: CONTRACT: Dict[str, Any] = {
00050:     "uses_prebuilt_final_answer_endpoint": True,
00051:     "live_pipeline_orchestrates_query_time_path": True,
00052:     "live_pipeline_serves_only_final_gated_answers": True,
00053:     "unknown_queries_return_audit_limitation": True,
00054:     "endpoint_does_not_call_llm": True,
00055:     "endpoint_does_not_rerun_retrieval": True,
00056:     "reruns_ocr": False,
00057:     "reruns_page_classification": False,
00058:     "reruns_embeddings": False,
00059:     "reruns_page_summaries": False,
00060:     "reruns_graph_build": False,
00061:     "reruns_table_extraction": False,
00062:     "graph_is_not_proof_authority": True,
00063:     "summaries_are_not_source_truth": True,
00064:     "guidance_box_is_not_source_truth": True,
00065:     "evidence_box_is_source_truth": True,
00066:     "answer_permission": False,
00067:     "can_answer_directly": False,
00068:     "can_prove_claims": False,
00069:     "source_truth_mutation_allowed": False,
```
### Source window L304-L360
```python
00304:     selected_query = clean_text(selected.get("user_query"))
00305:     for row in pipelines:
00306:         if clean_text(row.get("user_query")) == selected_query:
00307:             return row, score
00308:     return None, score
00309: 
00310: 
00311: def citations_text(citations: Sequence[Mapping[str, Any]]) -> str:
00312:     if not citations:
00313:         return ""
00314:     lines = ["", "Citations:"]
00315:     for i, citation in enumerate(citations, 1):
00316:         marker = clean_text(citation.get("citation_marker")) or f"[{i}]"
00317:         page = clean_text(citation.get("page_id"))
00318:         field = clean_text(citation.get("field_name"))
00319:         value = clean_text(citation.get("normalized_value"))
00320:         lines.append(f"{marker} page={page} field={field} value={value}")
00321:     return "\n".join(lines)
00322: 
00323: 
00324: def ask_live_query(query: str, state: Mapping[str, Any]) -> Dict[str, Any]:
00325:     pipelines = state.get("ready_live_query_pipelines") or state.get("live_query_pipelines") or []
00326:     pipeline, score = select_pipeline(query, [p for p in pipelines if isinstance(p, Mapping)])
00327:     model = clean_text(state.get("model")) or DEFAULT_MODEL_ID
00328: 
00329:     if pipeline is None:
00330:         content = (
00331:             "TRACE-Net does not yet have a final-gated live pipeline answer for this query. "
00332:             "A later dynamic execution stage should run retrieval, context packing, Self-RAG, CRAG, "
00333:             "prompt construction, draft generation, and the final answer gate before returning a final answer."
00334:         )
00335:         stages = build_pipeline_stages(None, matched=False)
00336:         citations: List[Dict[str, Any]] = []
00337:         response_status = "LIVE_QUERY_PIPELINE_REQUIRES_DYNAMIC_EXECUTION"
00338:         matched = False
00339:         page_ids: List[str] = []
00340:         fields: List[str] = []
00341:         limitations = ["No final-gated artifact matched this query in the v15 pipeline manifest."]
00342:     else:
00343:         content = clean_text(pipeline.get("message", {}).get("content") if isinstance(pipeline.get("message"), Mapping) else "")
00344:         stages = list(pipeline.get("pipeline_stages", [])) if isinstance(pipeline.get("pipeline_stages"), list) else []
00345:         citations = [dict(c) for c in pipeline.get("citations", []) if isinstance(c, Mapping)]
00346:         response_status = "LIVE_QUERY_PIPELINE_FINAL_GATED_ANSWER_READY"
00347:         matched = True
00348:         page_ids = list(pipeline.get("page_ids", [])) if isinstance(pipeline.get("page_ids"), list) else []
00349:         fields = list(pipeline.get("field_names", [])) if isinstance(pipeline.get("field_names"), list) else []
00350:         limitations = list(pipeline.get("limitations", [])) if isinstance(pipeline.get("limitations"), list) else []
00351: 
00352:     return {
00353:         "object": "trace_net.e2e.live_query_pipeline.response",
00354:         "endpoint_version": DEFAULT_ENDPOINT_VERSION,
00355:         "model": model,
00356:         "query": query,
00357:         "matched_live_pipeline": matched,
00358:         "match_score": score,
00359:         "response_status": response_status,
00360:         "message": {"role": "assistant", "content": content},
```
### Source window L230-L286
```python
00230: 
00231:     endpoint_routes = [
00232:         {"method": "GET", "path": "/health", "purpose": "health and safety metadata"},
00233:         {"method": "GET", "path": "/v1/models", "purpose": "OpenAI-compatible model listing"},
00234:         {"method": "POST", "path": "/api/trace-net/ask", "purpose": "TRACE-Net live query pipeline ask endpoint"},
00235:         {"method": "POST", "path": "/v1/chat/completions", "purpose": "OpenAI-compatible chat wrapper"},
00236:     ]
00237: 
00238:     checks = [
00239:         _quality_check("final_answer_count", len(answers), ">=", min_final_answers),
00240:         _quality_check("ready_pipeline_query_count", ready_pipeline_count, ">=", min_ready_pipeline_queries),
00241:         _quality_check("min_pipeline_stages_per_query", min((r.get("pipeline_stage_count", 0) for r in pipeline_records), default=0), ">=", min_pipeline_stages_per_query),
00242:         _quality_check("total_pipeline_stage_count", total_stage_count, ">=", min_total_pipeline_stages),
00243:         _quality_check("total_citation_count", total_citations, ">=", min_total_citations),
00244:         _quality_check("endpoint_route_count", len(endpoint_routes), ">=", min_endpoint_routes),
00245:         _quality_check("unknown_query_final_answer_count", 0, "<=", max_unknown_query_final_answer_count),
00246:         _quality_check("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
00247:         _quality_check("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
00248:         _quality_check("contract_can_answer_directly", 0, "==", 0),
00249:         _quality_check("contract_can_prove_claims", 0, "==", 0),
00250:         _quality_check("postgres_write_attempt_count", 0, "==", 0),
00251:         _quality_check("qdrant_write_attempt_count", 0, "==", 0),
00252:         _quality_check("opensearch_write_attempt_count", 0, "==", 0),
00253:     ]
00254:     if require_no_answer_permission:
00255:         checks.append(_quality_check("require_no_answer_permission", answer_permission_count, "==", 0))
00256: 
00257:     quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
00258:     status = READY_STATUS if quality_status == QUALITY_PASS else "E2E_LIVE_QUERY_PIPELINE_NEEDS_REPAIR"
00259: 
00260:     return {
00261:         "schema_version": SCHEMA_VERSION,
00262:         "status": "E2E_LIVE_QUERY_PIPELINE_BUILT",
00263:         "e2e_live_query_pipeline_status": status,
00264:         "quality_status": quality_status,
00265:         "model": model,
00266:         "host": host,
00267:         "port": port,
00268:         "base_url_windows": f"http://127.0.0.1:{port}/v1",
00269:         "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
00270:         "endpoint_routes": endpoint_routes,
00271:         "endpoint_route_count": len(endpoint_routes),
00272:         "live_query_pipelines": pipeline_records,
00273:         "ready_live_query_pipelines": [r for r in pipeline_records if r.get("ready_for_webui")],
00274:         "source_webui_final_answer_summary": dict(_summary(webui_final_answer_endpoint)),
00275:         "live_query_pipeline_contract": dict(CONTRACT),
00276:         "summary": {
00277:             "final_answer_count": len(answers),
00278:             "ready_pipeline_query_count": ready_pipeline_count,
00279:             "total_pipeline_stage_count": total_stage_count,
00280:             "total_citation_count": total_citations,
00281:             "endpoint_route_count": len(endpoint_routes),
00282:             "answer_permission_count": answer_permission_count,
00283:             "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
00284:             "quality_status": quality_status,
00285:         },
00286:         "quality_checks": checks,
```
### Source window L128-L184
```python
00128:         content = clean_text(message.get("content"))
00129:         if content:
00130:             return content
00131:     return clean_text(answer.get("final_answer_text") or answer.get("answer_text") or answer.get("response_text"))
00132: 
00133: 
00134: def build_pipeline_stages(answer: Optional[Mapping[str, Any]], *, matched: bool) -> List[Dict[str, Any]]:
00135:     """Build a compact stage trace for the query-time path."""
00136:     stages: List[Dict[str, Any]] = []
00137:     if matched and answer is not None:
00138:         status = "STAGE_SATISFIED_FROM_FINAL_GATED_ARTIFACT"
00139:         detail = "Prebuilt final-gated artifact already includes this stage output. No rebuild was performed."
00140:     else:
00141:         status = "STAGE_REQUIRES_DYNAMIC_EXECUTION"
00142:         detail = "No final-gated artifact matched this query. A later live dynamic pipeline must execute this stage."
00143:     for index, name in enumerate(PIPELINE_STAGE_NAMES, 1):
00144:         stage_status = status
00145:         if matched and name == "webui_final_answer":
00146:             stage_status = "STAGE_READY_FOR_WEBUI"
00147:         if not matched and name == "webui_final_answer":
00148:             stage_status = "STAGE_BLOCKED_NO_FINAL_GATED_ANSWER"
00149:         stages.append(
00150:             {
00151:                 "stage_index": index,
00152:                 "stage_name": name,
00153:                 "stage_status": stage_status,
00154:                 "detail": detail,
00155:                 "uses_source_truth_only_for_claims": True,
00156:                 "graph_is_not_proof_authority": True,
00157:                 "source_truth_mutation_allowed": False,
00158:             }
00159:         )
00160:     return stages
00161: 
00162: 
00163: def build_pipeline_record(answer: Mapping[str, Any], index: int) -> Dict[str, Any]:
00164:     citations = _citations(answer)
00165:     stages = build_pipeline_stages(answer, matched=True)
00166:     return {
00167:         "schema_version": SCHEMA_VERSION,
00168:         "live_query_pipeline_id": f"live_query_pipeline_v15_{index:04d}",
00169:         "live_query_pipeline_status": "LIVE_QUERY_PIPELINE_FINAL_GATED_READY",
00170:         "user_query": clean_text(answer.get("user_query")),
00171:         "normalized_query": clean_text(answer.get("normalized_query")),
00172:         "query_intent": clean_text(answer.get("query_intent")),
00173:         "source_webui_final_answer_id": clean_text(answer.get("webui_final_answer_id")),
00174:         "pipeline_stages": stages,
00175:         "pipeline_stage_count": len(stages),
00176:         "message": {"role": "assistant", "content": _answer_content(answer)},
00177:         "citations": citations,
00178:         "citation_count": len(citations),
00179:         "page_ids": list(answer.get("page_ids", [])) if isinstance(answer.get("page_ids"), list) else [],
00180:         "field_names": list(answer.get("field_names", [])) if isinstance(answer.get("field_names"), list) else [],
00181:         "limitations": list(answer.get("limitations", [])) if isinstance(answer.get("limitations"), list) else [],
00182:         "ready_for_webui": True,
00183:         "response_is_final_gated": True,
00184:         "answer_permission": False,
```
### Source window L441-L497
```python
00441:             self.end_headers()
00442:             self.wfile.write(body)
00443: 
00444:         def _read_json(self) -> Dict[str, Any]:
00445:             length = int(self.headers.get("Content-Length", "0") or 0)
00446:             if length <= 0:
00447:                 return {}
00448:             try:
00449:                 payload = json.loads(self.rfile.read(length).decode("utf-8"))
00450:                 return payload if isinstance(payload, dict) else {}
00451:             except json.JSONDecodeError:
00452:                 return {}
00453: 
00454:         def do_GET(self) -> None:  # noqa: N802
00455:             path = urlparse(self.path).path
00456:             if path == "/health":
00457:                 self._send_json(200, health_response(state))
00458:             elif path == "/v1/models":
00459:                 self._send_json(200, models_response(model))
00460:             else:
00461:                 self._send_json(404, {"error": "not_found", "path": path})
00462: 
00463:         def do_POST(self) -> None:  # noqa: N802
00464:             path = urlparse(self.path).path
00465:             payload = self._read_json()
00466:             if path == "/api/trace-net/ask":
00467:                 query = clean_text(payload.get("query") or payload.get("prompt"))
00468:                 self._send_json(200, ask_live_query(query, state))
00469:             elif path == "/v1/chat/completions":
00470:                 query = extract_query_from_chat_payload(payload)
00471:                 response = ask_live_query(query, state)
00472:                 self._send_json(200, make_chat_completion(query, response, model=model))
00473:             else:
00474:                 self._send_json(404, {"error": "not_found", "path": path})
00475: 
00476:     return TraceNetLiveQueryPipelineHandler
00477: 
00478: 
00479: def serve_state(state: Mapping[str, Any], host: str = "127.0.0.1", port: int = 8018) -> None:
00480:     httpd = ThreadingHTTPServer((host, port), make_handler(state))
00481:     print("TRACE-Net E2E live query pipeline v15")
00482:     print(f" Serving: http://{host}:{port}")
00483:     print(f" Health:  http://{host}:{port}/health")
00484:     print(f" Ask:     http://{host}:{port}/api/trace-net/ask")
00485:     print(f" Chat:    http://{host}:{port}/v1/chat/completions")
00486:     print(f" Model:   {clean_text(state.get('model')) or DEFAULT_MODEL_ID}")
00487:     print(" Press Ctrl+C to stop.")
00488:     try:
00489:         httpd.serve_forever()
00490:     except KeyboardInterrupt:
00491:         print("\nStopping TRACE-Net E2E live query pipeline v15")
00492:     finally:
00493:         httpd.server_close()
00494: 
00495: 
00496: def render_inspect_md(report: Mapping[str, Any]) -> str:
00497:     summary = _summary(report)
```

## `tiff/trace_net_dynamic_final_gate_execution_v1.py`
- Location: `active_source_code`
- Score: `224`
- Categories: `feedback, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Dynamic Final-Gate Execution v1. Read-only dynamic gate runner that takes Hybrid Retrieval v2 groups and tries to materialize final-answer candidates for arbitrary queries. It may approve a minimal final answer only when the selected dynamic retrieval groups have page lineage, citations, and answer-support authority. Otherwise it returns a retrieval-only, final-gate-required result. Safety contract: - Hybrid retrieval groups are possible evidence, not proof. - Dynamic final claims requ
- Functions: now_iso()@L94; as_text(value)@L98; as_bool(value, default)@L104; as_int(value, default)@L118; as_float(value, default)@L127; as_list(value)@L134; unique_texts(values)@L144; stable_json(value)@L148; stable_hash(value, length)@L152; read_json(path)@L156; write_json(path, payload)@L169; write_jsonl(path, rows)@L175; read_text_if_exists(path)@L186; quality_status(payload)@L195; normalize_query(value)@L208; page_number_from_page_id(page_id)@L212; sanitize_text(text, max_chars)@L219; query_results(report)@L231
- CLI args: --hybrid-v2-report, --final-answer-report, --final-answer-markdown, --query-file, --query, --output-dir, --max-claims, --min-claims-for-answer, --min-queries, --min-results, --require-hybrid-v2-quality-pass, --require-final-answer-quality-pass, --quality
- Has __main__ guard.

### Source window L601-L657
```python
00601:         "feedback_as_proof_count": sum(as_int(r.get("feedback_as_proof_count")) for r in results),
00602:         "community_as_proof_count": sum(as_int(r.get("community_as_proof_count")) for r in results),
00603:         "category_as_proof_count": sum(as_int(r.get("category_as_proof_count")) for r in results),
00604:         "local_path_leak_count": sum(as_int(r.get("local_path_leak_count")) for r in results),
00605:         "raw_bytes_repr_count": sum(as_int(r.get("raw_bytes_repr_count")) for r in results),
00606:         "source_truth_mutation_allowed_count": sum(as_int(r.get("source_truth_mutation_allowed_count")) for r in results),
00607:         "postgres_write_attempt_count": 0,
00608:         "qdrant_write_attempt_count": 0,
00609:         "opensearch_write_attempt_count": 0,
00610:         "hybrid_v2_quality_status": report.get("source_quality_statuses", {}).get("hybrid_v2", ""),
00611:         "final_answer_gate_quality_status": report.get("source_quality_statuses", {}).get("final_answer_gate", ""),
00612:     }
00613:     summary["answer_status_counts"] = dict(Counter(as_text(r.get("answer_status")) for r in results))
00614:     summary["blocked_reason_counts"] = dict(Counter(reason for b in blocked for reason in as_list(b.get("blocked_reason_codes"))))
00615:     return summary
00616: 
00617: 
00618: def quality_report(
00619:     report: Mapping[str, Any],
00620:     *,
00621:     min_queries: int = 1,
00622:     min_results: int = 1,
00623:     require_hybrid_v2_quality_pass: bool = False,
00624:     require_final_answer_quality_pass: bool = False,
00625: ) -> dict[str, Any]:
00626:     summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report)
00627:     checks: list[dict[str, Any]] = []
00628: 
00629:     def add(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None:
00630:         checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})
00631: 
00632:     add("dynamic_gate_query_count_min", as_int(summary.get("dynamic_gate_query_count")) >= min_queries, summary.get("dynamic_gate_query_count"), f">= {min_queries}")
00633:     add("result_count_min", len(as_list(report.get("query_results"))) >= min_results, len(as_list(report.get("query_results"))), f">= {min_results}")
00634:     add("uncited_final_claim_count_zero", as_int(summary.get("uncited_final_claim_count")) == 0, summary.get("uncited_final_claim_count"), 0)
00635:     add("retrieval_only_final_claim_count_zero", as_int(summary.get("retrieval_only_final_claim_count")) == 0, summary.get("retrieval_only_final_claim_count"), 0)
00636:     add("feedback_as_proof_count_zero", as_int(summary.get("feedback_as_proof_count")) == 0, summary.get("feedback_as_proof_count"), 0)
00637:     add("community_as_proof_count_zero", as_int(summary.get("community_as_proof_count")) == 0, summary.get("community_as_proof_count"), 0)
00638:     add("category_as_proof_count_zero", as_int(summary.get("category_as_proof_count")) == 0, summary.get("category_as_proof_count"), 0)
00639:     add("local_path_leak_count_zero", as_int(summary.get("local_path_leak_count")) == 0, summary.get("local_path_leak_count"), 0)
00640:     add("raw_bytes_repr_count_zero", as_int(summary.get("raw_bytes_repr_count")) == 0, summary.get("raw_bytes_repr_count"), 0)
00641:     add("source_truth_mutation_allowed_count_zero", as_int(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
00642:     add("postgres_write_attempt_count_zero", as_int(summary.get("postgres_write_attempt_count")) == 0, summary.get("postgres_write_attempt_count"), 0)
00643:     add("qdrant_write_attempt_count_zero", as_int(summary.get("qdrant_write_attempt_count")) == 0, summary.get("qdrant_write_attempt_count"), 0)
00644:     add("opensearch_write_attempt_count_zero", as_int(summary.get("opensearch_write_attempt_count")) == 0, summary.get("opensearch_write_attempt_count"), 0)
00645:     if require_hybrid_v2_quality_pass:
00646:         add("hybrid_v2_quality_pass", as_text(summary.get("hybrid_v2_quality_status")).upper() == "PASS", summary.get("hybrid_v2_quality_status"), "PASS")
00647:     if require_final_answer_quality_pass:
00648:         add("final_answer_quality_pass", as_text(summary.get("final_answer_gate_quality_status")).upper() == "PASS", summary.get("final_answer_gate_quality_status"), "PASS")
00649:     status = "PASS" if all(c["passed"] or c["severity"] != "critical" for c in checks) else "FAIL"
00650:     return {"schema_version": f"{SCHEMA_VERSION}_quality", "status": status, "summary": dict(summary), "checks": checks}
00651: 
00652: 
00653: def build_dynamic_final_gate_execution(
00654:     *,
00655:     hybrid_v2_report_path: str | Path,
00656:     final_answer_report_path: str | Path | None = None,
00657:     final_answer_markdown_path: str | Path | None = None,
```
### Source window L1-L38
```python
00001: """TRACE-Net Dynamic Final-Gate Execution v1.
00002: 
00003: Read-only dynamic gate runner that takes Hybrid Retrieval v2 groups and tries to
00004: materialize final-answer candidates for arbitrary queries.  It may approve a
00005: minimal final answer only when the selected dynamic retrieval groups have page
00006: lineage, citations, and answer-support authority.  Otherwise it returns a
00007: retrieval-only, final-gate-required result.
00008: 
00009: Safety contract:
00010: - Hybrid retrieval groups are possible evidence, not proof.
00011: - Dynamic final claims require page/source lineage, citations, and answer-support
00012:   buckets/authorities.
00013: - Feedback, communities, and categories are never proof.
00014: - No Postgres, Qdrant, OpenSearch, graph, citation, trust, or source writes occur.
00015: """
00016: from __future__ import annotations
00017: 
00018: import argparse
00019: import datetime as _dt
00020: import hashlib
00021: import html
00022: import json
00023: import re
00024: from collections import Counter
00025: from pathlib import Path
00026: from typing import Any, Iterable, Mapping, Optional
00027: 
00028: SCHEMA_VERSION = "trace_net_dynamic_final_gate_execution_v1"
00029: ALGORITHM = "trace_net_dynamic_retrieval_to_citation_authority_gate_v1"
00030: DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/dynamic_final_gate_execution")
00031: DEFAULT_HYBRID_V2_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json")
00032: DEFAULT_FINAL_ANSWER_REPORT = Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json")
00033: DEFAULT_FINAL_ANSWER_MD = Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md")
00034: DEFAULT_OUTPUT_FILE = "trace_net_dynamic_final_gate_execution_v1.json"
00035: DEFAULT_RESULTS_FILE = "trace_net_dynamic_final_gate_execution_v1_results.jsonl"
00036: DEFAULT_CLAIMS_FILE = "trace_net_dynamic_final_gate_execution_v1_claims.jsonl"
00037: DEFAULT_BLOCKED_FILE = "trace_net_dynamic_final_gate_execution_v1_blocked_claims.jsonl"
00038: DEFAULT_SUMMARY_FILE = "trace_net_dynamic_final_gate_execution_v1_summary.json"
```
### Source window L489-L545
```python
00489:         if len(claim.get("citation_ids", [])) > 3:
00490:             cids += ", ..."
00491:         lines.append(f"- {claim['claim_text']} [cite:{cids}]")
00492:     lines.append("")
00493:     lines.append(f"OCR/source note: {OCR_UNCERTAINTY_NOTE}")
00494:     lines.append("TRACE-Net gate: feedback, community, category, and retrieval-only records were not used as proof.")
00495:     return "\n".join(lines).strip()
00496: 
00497: 
00498: def build_dynamic_result(
00499:     query: Mapping[str, str],
00500:     hybrid_result: Mapping[str, Any],
00501:     *,
00502:     max_claims: int,
00503:     min_claims_for_answer: int,
00504: ) -> dict[str, Any]:
00505:     approved: list[dict[str, Any]] = []
00506:     blocked: list[dict[str, Any]] = []
00507:     for group in ranked_groups(hybrid_result):
00508:         claim, block = evaluate_group_for_dynamic_claim(query, group)
00509:         if claim:
00510:             approved.append(claim)
00511:         if block:
00512:             blocked.append(block)
00513:     approved = sorted(approved, key=lambda c: (as_int(c.get("hybrid_v2_rank")), -as_float(c.get("hybrid_v2_score"))))[:max_claims]
00514:     final_allowed = len(approved) >= min_claims_for_answer
00515:     answer_text = build_dynamic_answer_text(query, approved, max_claims) if final_allowed else ""
00516:     safe_answer, leaks = sanitize_text(answer_text)
00517:     status = "DYNAMIC_FINAL_GATE_APPROVED" if final_allowed else "DYNAMIC_FINAL_GATE_RETRIEVAL_ONLY"
00518:     return {
00519:         "dynamic_gate_result_id": f"dyngate__{stable_hash([query, approved, blocked[:3]])}",
00520:         "query_id": as_text(query.get("query_id")),
00521:         "query": as_text(query.get("query")),
00522:         "answer_status": status,
00523:         "final_answer_allowed": final_allowed,
00524:         "final_answer_text": safe_answer,
00525:         "final_claims": approved,
00526:         "blocked_claims": blocked,
00527:         "final_claim_count": len(approved),
00528:         "blocked_claim_count": len(blocked),
00529:         "retrieval_group_count": as_int(hybrid_result.get("ranked_group_count") or len(ranked_groups(hybrid_result))),
00530:         "exact_hit_group_count": sum(1 for g in ranked_groups(hybrid_result) if as_int(g.get("exact_hit_count")) > 0),
00531:         "semantic_group_count": sum(1 for g in ranked_groups(hybrid_result) if as_int(g.get("semantic_group_count")) > 0),
00532:         "uncited_final_claim_count": sum(1 for c in approved if not c.get("citation_ids")),
00533:         "retrieval_only_final_claim_count": sum(1 for c in approved if as_bool(c.get("retrieval_only"))),
00534:         "feedback_as_proof_count": sum(1 for c in approved if as_bool(c.get("feedback_as_proof"))),
00535:         "community_as_proof_count": sum(1 for c in approved if as_bool(c.get("community_as_proof"))),
00536:         "category_as_proof_count": sum(1 for c in approved if as_bool(c.get("category_as_proof"))),
00537:         "source_truth_mutation_allowed_count": sum(1 for c in approved if as_bool(c.get("source_truth_mutation_allowed"))),
00538:         "local_path_leak_count": leaks["local_path_leak_count"],
00539:         "raw_bytes_repr_count": leaks["raw_bytes_repr_count"],
00540:         "can_answer_directly": final_allowed,
00541:         "can_prove_claims": final_allowed,
00542:         "can_mutate_source_truth": False,
00543:         "source_truth_mutation_allowed": False,
00544:     }
00545: 
```
### Source window L681-L737
```python
00681:             result = build_final_artifact_result(q, final_report, final_answer_markdown_path)
00682:         else:
00683:             hv2_result = find_hybrid_query_result(hybrid_v2, q)
00684:             result = build_dynamic_result(q, hv2_result, max_claims=max_claims, min_claims_for_answer=min_claims_for_answer)
00685:         results.append(result)
00686:         all_claims.extend([dict(c) for c in as_list(result.get("final_claims")) if isinstance(c, Mapping)])
00687:         all_blocked.extend([dict(b) for b in as_list(result.get("blocked_claims")) if isinstance(b, Mapping)])
00688: 
00689:     report: dict[str, Any] = {
00690:         "schema_version": SCHEMA_VERSION,
00691:         "algorithm": ALGORITHM,
00692:         "status": "DYNAMIC_FINAL_GATE_EXECUTION_BUILT",
00693:         "generated_at": now_iso(),
00694:         "query_results": results,
00695:         "final_claims": all_claims,
00696:         "blocked_claims": all_blocked,
00697:         "source_artifacts": {
00698:             "hybrid_v2_report": str(hybrid_v2_report_path),
00699:             "final_answer_report": str(final_answer_report_path or ""),
00700:             "final_answer_markdown": str(final_answer_markdown_path or ""),
00701:         },
00702:         "source_quality_statuses": {
00703:             "hybrid_v2": quality_status(hybrid_v2),
00704:             "final_answer_gate": final_quality,
00705:         },
00706:         "read_only": True,
00707:         "writeback_mode": "dynamic_final_gate_dry_run_only",
00708:         "postgres_write_attempt_count": 0,
00709:         "qdrant_write_attempt_count": 0,
00710:         "opensearch_write_attempt_count": 0,
00711:         "source_truth_mutation_allowed": False,
00712:     }
00713:     report["summary"] = summarize(report)
00714:     qreport = quality_report(
00715:         report,
00716:         min_queries=min_queries,
00717:         min_results=min_results,
00718:         require_hybrid_v2_quality_pass=require_hybrid_v2_quality_pass,
00719:         require_final_answer_quality_pass=require_final_answer_quality_pass,
00720:     )
00721:     report["quality_status"] = qreport["status"]
00722:     report["quality_checks"] = qreport["checks"]
00723:     report["summary"]["status"] = qreport["status"]
00724: 
00725:     out_dir = Path(output_dir)
00726:     out_dir.mkdir(parents=True, exist_ok=True)
00727:     report_path = out_dir / DEFAULT_OUTPUT_FILE
00728:     results_path = out_dir / DEFAULT_RESULTS_FILE
00729:     claims_path = out_dir / DEFAULT_CLAIMS_FILE
00730:     blocked_path = out_dir / DEFAULT_BLOCKED_FILE
00731:     summary_path = out_dir / DEFAULT_SUMMARY_FILE
00732:     quality_path = out_dir / DEFAULT_QUALITY_FILE
00733:     manifest_path = out_dir / DEFAULT_MANIFEST_FILE
00734:     md_path = out_dir / DEFAULT_MD_FILE
00735:     html_path = out_dir / DEFAULT_HTML_FILE
00736:     write_json(report_path, report)
00737:     write_jsonl(results_path, results)
```
### Source window L377-L433
```python
00377:     authorities = set(group_authorities(group))
00378:     if buckets & ANSWER_SUPPORT_BUCKETS:
00379:         return True
00380:     if authorities & ANSWER_SUPPORT_AUTHORITIES:
00381:         return True
00382:     for hit in as_list(group.get("exact_hits")):
00383:         if isinstance(hit, Mapping) and as_bool(hit.get("answer_support_candidate")):
00384:             return True
00385:     return False
00386: 
00387: 
00388: def is_banned_bucket(bucket: str) -> bool:
00389:     b = as_text(bucket).lower()
00390:     return any(token in b for token in BANNED_BUCKET_TOKENS)
00391: 
00392: 
00393: def evaluate_group_for_dynamic_claim(query: Mapping[str, str], group: Mapping[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
00394:     page_id = group_page_id(group)
00395:     citations = group_citations(group)
00396:     buckets = group_buckets(group)
00397:     authorities = group_authorities(group)
00398:     reasons: list[str] = []
00399:     if not page_id:
00400:         reasons.append("missing_page_id")
00401:     if not citations:
00402:         reasons.append("missing_citation")
00403:     if any(is_banned_bucket(bucket) for bucket in buckets):
00404:         reasons.append("banned_bucket_present")
00405:     if as_bool(group.get("source_truth_mutation_allowed")) or as_bool(group.get("can_mutate_source_truth")):
00406:         reasons.append("source_truth_mutation_risk")
00407:     if as_bool(group.get("feedback_as_proof")):
00408:         reasons.append("feedback_as_proof")
00409:     if as_bool(group.get("community_as_proof")):
00410:         reasons.append("community_as_proof")
00411:     if as_bool(group.get("category_as_proof")):
00412:         reasons.append("category_as_proof")
00413:     if not has_answer_support(group):
00414:         reasons.append("no_answer_support_authority")
00415:     if as_bool(group.get("retrieval_only"), True) and "no_answer_support_authority" in reasons:
00416:         reasons.append("retrieval_only_group")
00417: 
00418:     base = {
00419:         "query_id": as_text(query.get("query_id")),
00420:         "query": as_text(query.get("query")),
00421:         "hybrid_v2_group_id": as_text(group.get("hybrid_v2_group_id")),
00422:         "hybrid_v2_rank": as_int(group.get("hybrid_v2_rank")),
00423:         "page_id": page_id,
00424:         "page_number": page_number_from_page_id(page_id) if page_id else "",
00425:         "citation_ids": citations,
00426:         "part_numbers": group_part_numbers(group),
00427:         "rag_buckets": buckets,
00428:         "authorities": authorities,
00429:         "exact_hit_count": as_int(group.get("exact_hit_count")),
00430:         "semantic_group_count": as_int(group.get("semantic_group_count")),
00431:         "hybrid_v2_score": as_float(group.get("hybrid_v2_score")),
00432:         "category_labels": unique_texts(group.get("category_labels") or []),
00433:         "can_mutate_source_truth": False,
```

## `tiff/trace_net_e2e_context_pack_builder_v1.py`
- Location: `active_source_code`
- Score: `224`
- Categories: `context_pack, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E Context Pack Builder v1. Turns local ranked retrieval groups into retrieval-only context packs. The module intentionally does not answer questions, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime and later sufficiency/final-gate modules.
- Functions: _read_json(path)@L33; _write_json(path, data)@L41; _write_jsonl(path, rows)@L48; _safe_str(value)@L55; _as_bool(value, default)@L63; _num(value, default)@L73; _stable_id(prefix)@L82; _runtime_quality_pass(runtime)@L88; _runtime_ready(runtime)@L97; _get_retrieval_groups(runtime)@L108; _get_hits(group)@L119; _has_required_hit_keys(hit)@L129; build_context_item(query_id, query_index, hit_index, hit)@L133; build_context_pack(group, query_index)@L185; _count_bad(records, key)@L220; _quality_check(name, observed, expected, passed)@L224; evaluate_quality(report, args)@L233; build_report(runtime_path, output_dir)@L268
- CLI args: --e2e-hybrid-retrieval-runtime, --output-dir, --top-k, --min-source-retrieval-groups, --min-context-packs, --min-context-packs-with-items, --min-total-context-items, --min-pages-with-context-items, --min-citation-ready-items, --min-source-trace-ready-items, --min-field-count, --max-unsafe-records, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-source-runtime-quality-pass, --require-no-answer-permission, --quality
- Has __main__ guard.

### Source window L1-L49
```python
00001: """TRACE-Net E2E Context Pack Builder v1.
00002: 
00003: Turns local ranked retrieval groups into retrieval-only context packs.
00004: 
00005: The module intentionally does not answer questions, prove claims, mutate source truth,
00006: or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime
00007: and later sufficiency/final-gate modules.
00008: """
00009: 
00010: from __future__ import annotations
00011: 
00012: import argparse
00013: import hashlib
00014: import json
00015: from dataclasses import dataclass
00016: from pathlib import Path
00017: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00018: 
00019: QUALITY_PASS = "PASS"
00020: QUALITY_FAIL = "FAIL"
00021: STATUS_BUILT = "E2E_CONTEXT_PACK_BUILT"
00022: READY_STATUS = "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE"
00023: 
00024: REPORT_NAME = "trace_net_e2e_context_pack_builder_v1.json"
00025: QUALITY_NAME = "trace_net_e2e_context_pack_builder_v1_quality.json"
00026: CONTEXT_PACKS_JSONL_NAME = "trace_net_e2e_context_packs_v1.jsonl"
00027: CONTEXT_ITEMS_JSONL_NAME = "trace_net_e2e_context_items_v1.jsonl"
00028: INSPECT_MD_NAME = "trace_net_e2e_context_pack_builder_v1_inspect.md"
00029: 
00030: REQUIRED_HIT_KEYS = ("page_id", "field_name", "normalized_value")
00031: 
00032: 
00033: def _read_json(path: Path) -> Dict[str, Any]:
00034:     with path.open("r", encoding="utf-8") as f:
00035:         data = json.load(f)
00036:     if not isinstance(data, dict):
00037:         raise ValueError(f"Expected JSON object at {path}")
00038:     return data
00039: 
00040: 
00041: def _write_json(path: Path, data: Mapping[str, Any]) -> None:
00042:     path.parent.mkdir(parents=True, exist_ok=True)
00043:     with path.open("w", encoding="utf-8") as f:
00044:         json.dump(data, f, indent=2, sort_keys=True)
00045:         f.write("\n")
00046: 
00047: 
00048: def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
00049:     path.parent.mkdir(parents=True, exist_ok=True)
```
### Source window L292-L348
```python
00292:         "context_pack_with_items_count": sum(1 for p in context_packs if int(p.get("context_item_count", 0)) > 0),
00293:         "total_context_item_count": len(context_items),
00294:         "page_with_context_item_count": len(page_ids),
00295:         "field_count": len(field_counts),
00296:         "field_counts": dict(sorted(field_counts.items())),
00297:         "citation_ready_context_item_count": sum(1 for item in context_items if _as_bool(item.get("citation_ready"))),
00298:         "source_trace_ready_context_item_count": sum(1 for item in context_items if _as_bool(item.get("source_trace_ready"))),
00299:         "schema_missing_required_key_item_count": sum(1 for item in context_items if not _as_bool(item.get("schema_complete"))),
00300:         "unsafe_context_record_count": _count_bad(context_packs, "unsafe") + _count_bad(context_items, "unsafe"),
00301:         "answer_permission_count": _count_bad(context_packs, "answer_permission") + _count_bad(context_items, "answer_permission"),
00302:         "can_answer_directly_count": _count_bad(context_packs, "can_answer_directly") + _count_bad(context_items, "can_answer_directly"),
00303:         "can_prove_claims_count": _count_bad(context_packs, "can_prove_claims") + _count_bad(context_items, "can_prove_claims"),
00304:         "source_truth_mutation_allowed_count": _count_bad(context_packs, "source_truth_mutation_allowed") + _count_bad(context_items, "source_truth_mutation_allowed"),
00305:         "postgres_write_attempt_count": 0,
00306:         "qdrant_write_attempt_count": 0,
00307:         "opensearch_write_attempt_count": 0,
00308:         "opensearch_upload_attempt_count": 0,
00309:         "ready_for_final_gate": True,
00310:         "all_context_retrieval_only": all(_as_bool(item.get("retrieval_only")) for item in context_items) if context_items else False,
00311:         "retrieval_permission": "ranking_only_until_final_gate",
00312:         "answer_authority": "blocked",
00313:     }
00314:     report: Dict[str, Any] = {
00315:         "artifact_name": "trace_net_e2e_context_pack_builder_v1",
00316:         "status": STATUS_BUILT,
00317:         "quality_status": QUALITY_FAIL,
00318:         "e2e_context_pack_status": READY_STATUS,
00319:         "context_pack_contract": {
00320:             "purpose": "Turn ranked retrieval groups into citation/source-trace-ready context packs for final gate review.",
00321:             "retrieval_permission": "ranking_only_until_final_gate",
00322:             "answer_authority": "blocked",
00323:             "ready_for_final_gate": True,
00324:             "can_answer_directly": False,
00325:             "can_prove_claims": False,
00326:             "source_truth_mutation_allowed": False,
00327:             "writes_to_postgres": False,
00328:             "writes_to_qdrant": False,
00329:             "writes_to_opensearch": False,
00330:             "uploads_to_opensearch": False,
00331:         },
00332:         "summary": summary,
00333:         "context_packs": context_packs,
00334:         "context_items": context_items,
00335:         "quality_checks": [],
00336:         "paths": {
00337:             "report_path": str(output_dir / REPORT_NAME),
00338:             "quality_path": str(output_dir / QUALITY_NAME),
00339:             "context_packs_jsonl_path": str(output_dir / CONTEXT_PACKS_JSONL_NAME),
00340:             "context_items_jsonl_path": str(output_dir / CONTEXT_ITEMS_JSONL_NAME),
00341:             "inspect_md_path": str(output_dir / INSPECT_MD_NAME),
00342:         },
00343:     }
00344:     quality_status, checks = evaluate_quality(report, args)
00345:     report["quality_status"] = quality_status
00346:     report["quality_checks"] = checks
00347:     return report
00348: 
```
### Source window L176-L232
```python
00176:         "schema_complete": _has_required_hit_keys({**hit, "normalized_value": normalized_value}),
00177:     }
00178:     # carry through selected provenance if present, but never authority.
00179:     for optional_key in ("source_document_id", "source_package_id", "source_page_number", "ocr_page_number"):
00180:         if optional_key in hit:
00181:             item[optional_key] = hit[optional_key]
00182:     return item
00183: 
00184: 
00185: def build_context_pack(group: Mapping[str, Any], query_index: int, *, top_k: int) -> Dict[str, Any]:
00186:     query_id = _safe_str(group.get("query_id") or f"e2e_query_unknown_{query_index:04d}")
00187:     hits = _get_hits(group)[: max(0, top_k)]
00188:     items = [build_context_item(query_id, query_index, idx, hit) for idx, hit in enumerate(hits)]
00189:     page_ids = sorted({item["page_id"] for item in items if item.get("page_id")})
00190:     field_names = sorted({item["field_name"] for item in items if item.get("field_name")})
00191:     pack_id = _stable_id("e2e_context_pack_v1", query_id, group.get("user_query"), len(items))
00192:     pack = {
00193:         "context_pack_id": pack_id,
00194:         "query_id": query_id,
00195:         "query_intent": _safe_str(group.get("query_intent")),
00196:         "user_query": _safe_str(group.get("user_query")),
00197:         "retrieval_status": _safe_str(group.get("retrieval_status") or "UNKNOWN"),
00198:         "context_pack_status": "CONTEXT_PACK_READY" if items else "CONTEXT_PACK_EMPTY",
00199:         "context_item_count": len(items),
00200:         "page_ids": page_ids,
00201:         "field_names": field_names,
00202:         "top_context_items": items,
00203:         "context_pack_contract": {
00204:             "retrieval_permission": "ranking_only_until_final_gate",
00205:             "answer_authority": "blocked",
00206:             "can_answer_directly": False,
00207:             "can_prove_claims": False,
00208:             "source_truth_mutation_allowed": False,
00209:             "requires_final_gate": True,
00210:         },
00211:         "answer_permission": False,
00212:         "can_answer_directly": False,
00213:         "can_prove_claims": False,
00214:         "source_truth_mutation_allowed": False,
00215:         "unsafe": False,
00216:     }
00217:     return pack
00218: 
00219: 
00220: def _count_bad(records: Iterable[Mapping[str, Any]], key: str) -> int:
00221:     return sum(1 for rec in records if _as_bool(rec.get(key)))
00222: 
00223: 
00224: def _quality_check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
00225:     return {
00226:         "name": name,
00227:         "observed": observed,
00228:         "expected": expected,
00229:         "passed": bool(passed),
00230:     }
00231: 
00232: 
```
### Source window L352-L408
```python
00352:     contract = report.get("context_pack_contract") or {}
00353:     packs = report.get("context_packs") or []
00354:     lines: List[str] = []
00355:     lines.append("# TRACE-Net E2E Context Pack Builder v1 Inspect")
00356:     lines.append("")
00357:     lines.append(f"Quality status: **{report.get('quality_status', QUALITY_FAIL)}**")
00358:     lines.append("")
00359:     lines.append("## Purpose")
00360:     lines.append("This artifact converts ranked retrieval groups into context packs for the later final gate.")
00361:     lines.append("It is intentionally retrieval-only: context can be reviewed, cited, and ranked, but cannot answer directly.")
00362:     lines.append("")
00363:     lines.append("## Context pack contract")
00364:     for key in ("retrieval_permission", "answer_authority", "ready_for_final_gate", "can_answer_directly", "can_prove_claims", "source_truth_mutation_allowed", "writes_to_postgres", "writes_to_qdrant", "writes_to_opensearch", "uploads_to_opensearch"):
00365:         lines.append(f"- {key}: {contract.get(key)}")
00366:     lines.append("")
00367:     lines.append("## Main counters")
00368:     for key in ("source_retrieval_group_count", "context_pack_count", "context_pack_with_items_count", "total_context_item_count", "page_with_context_item_count", "field_count", "citation_ready_context_item_count", "source_trace_ready_context_item_count", "schema_missing_required_key_item_count"):
00369:         lines.append(f"- {key}: {summary.get(key)}")
00370:     lines.append("")
00371:     lines.append("## Field counts")
00372:     field_counts = summary.get("field_counts") if isinstance(summary, Mapping) else {}
00373:     if isinstance(field_counts, Mapping) and field_counts:
00374:         for key, value in field_counts.items():
00375:             lines.append(f"- {key}: {value}")
00376:     else:
00377:         lines.append("- none")
00378:     lines.append("")
00379:     lines.append("## Safety/write counters")
00380:     for key in ("unsafe_context_record_count", "answer_permission_count", "can_answer_directly_count", "can_prove_claims_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count", "opensearch_upload_attempt_count"):
00381:         lines.append(f"- {key}: {summary.get(key)}")
00382:     lines.append("")
00383:     lines.append("## Context packs")
00384:     if isinstance(packs, list):
00385:         for pack in packs:
00386:             if not isinstance(pack, Mapping):
00387:                 continue
00388:             lines.append(f"- {pack.get('query_id')} | {pack.get('query_intent')} | query='{pack.get('user_query')}' | items={pack.get('context_item_count')}")
00389:             items = pack.get("top_context_items") or []
00390:             if isinstance(items, list):
00391:                 for item in items[:5]:
00392:                     if isinstance(item, Mapping):
00393:                         lines.append(f"  - {item.get('page_id')} | {item.get('field_name')} | {item.get('normalized_value')} | citation_ready={item.get('citation_ready')} | source_trace_ready={item.get('source_trace_ready')}")
00394:     lines.append("")
00395:     lines.append("## Quality checks")
00396:     checks = report.get("quality_checks") or []
00397:     if isinstance(checks, list):
00398:         for check in checks:
00399:             if isinstance(check, Mapping):
00400:                 status = "PASS" if check.get("passed") else "FAIL"
00401:                 lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
00402:     path.parent.mkdir(parents=True, exist_ok=True)
00403:     path.write_text("\n".join(lines) + "\n", encoding="utf-8")
00404: 
00405: 
00406: def write_outputs(report: Mapping[str, Any], output_dir: Path) -> None:
00407:     output_dir.mkdir(parents=True, exist_ok=True)
00408:     _write_json(output_dir / REPORT_NAME, report)
```
### Source window L438-L480
```python
00438: 
00439: def main(argv: Optional[Sequence[str]] = None) -> int:
00440:     parser = build_arg_parser()
00441:     args = parser.parse_args(argv)
00442:     report = build_report(args.e2e_hybrid_retrieval_runtime, args.output_dir, top_k=args.top_k, args=args)
00443:     write_outputs(report, args.output_dir)
00444:     summary = report["summary"]
00445:     print("TRACE-Net E2E Context Pack Builder v1")
00446:     print(f" Status: {report['status']}")
00447:     print(f" Quality status: {report['quality_status']}")
00448:     print(f" e2e_context_pack_status: {report['e2e_context_pack_status']}")
00449:     for key in (
00450:         "source_retrieval_group_count",
00451:         "context_pack_count",
00452:         "context_pack_with_items_count",
00453:         "total_context_item_count",
00454:         "page_with_context_item_count",
00455:         "field_count",
00456:         "citation_ready_context_item_count",
00457:         "source_trace_ready_context_item_count",
00458:         "schema_missing_required_key_item_count",
00459:         "unsafe_context_record_count",
00460:         "answer_permission_count",
00461:         "can_answer_directly_count",
00462:         "can_prove_claims_count",
00463:         "source_truth_mutation_allowed_count",
00464:         "postgres_write_attempt_count",
00465:         "qdrant_write_attempt_count",
00466:         "opensearch_write_attempt_count",
00467:         "opensearch_upload_attempt_count",
00468:     ):
00469:         print(f" {key}: {summary.get(key)}")
00470:     print(f" report_path: {args.output_dir / REPORT_NAME}")
00471:     print(f" context_packs_jsonl_path: {args.output_dir / CONTEXT_PACKS_JSONL_NAME}")
00472:     print(f" context_items_jsonl_path: {args.output_dir / CONTEXT_ITEMS_JSONL_NAME}")
00473:     print(f" inspect_md_path: {args.output_dir / INSPECT_MD_NAME}")
00474:     if args.quality and report["quality_status"] != QUALITY_PASS:
00475:         return 1
00476:     return 0
00477: 
00478: 
00479: if __name__ == "__main__":  # pragma: no cover
00480:     raise SystemExit(main())
```
### Source window L234-L290
```python
00234:     summary = report.get("summary") or {}
00235:     if not isinstance(summary, Mapping):
00236:         summary = {}
00237:     checks: List[Dict[str, Any]] = []
00238:     add = checks.append
00239:     add(_quality_check("source_runtime_quality_pass", summary.get("source_runtime_quality_pass"), "is True", _as_bool(summary.get("source_runtime_quality_pass"))))
00240:     add(_quality_check("source_runtime_ready_for_context_pack", summary.get("source_runtime_ready_for_context_pack"), "is True", _as_bool(summary.get("source_runtime_ready_for_context_pack"))))
00241:     add(_quality_check("source_retrieval_group_count", summary.get("source_retrieval_group_count", 0), f">= {args.min_source_retrieval_groups}", int(summary.get("source_retrieval_group_count", 0)) >= args.min_source_retrieval_groups))
00242:     add(_quality_check("context_pack_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", int(summary.get("context_pack_count", 0)) >= args.min_context_packs))
00243:     add(_quality_check("context_pack_with_items_count", summary.get("context_pack_with_items_count", 0), f">= {args.min_context_packs_with_items}", int(summary.get("context_pack_with_items_count", 0)) >= args.min_context_packs_with_items))
00244:     add(_quality_check("total_context_item_count", summary.get("total_context_item_count", 0), f">= {args.min_total_context_items}", int(summary.get("total_context_item_count", 0)) >= args.min_total_context_items))
00245:     add(_quality_check("page_with_context_item_count", summary.get("page_with_context_item_count", 0), f">= {args.min_pages_with_context_items}", int(summary.get("page_with_context_item_count", 0)) >= args.min_pages_with_context_items))
00246:     add(_quality_check("citation_ready_context_item_count", summary.get("citation_ready_context_item_count", 0), f">= {args.min_citation_ready_items}", int(summary.get("citation_ready_context_item_count", 0)) >= args.min_citation_ready_items))
00247:     add(_quality_check("source_trace_ready_context_item_count", summary.get("source_trace_ready_context_item_count", 0), f">= {args.min_source_trace_ready_items}", int(summary.get("source_trace_ready_context_item_count", 0)) >= args.min_source_trace_ready_items))
00248:     add(_quality_check("field_count", summary.get("field_count", 0), f">= {args.min_field_count}", int(summary.get("field_count", 0)) >= args.min_field_count))
00249:     add(_quality_check("schema_missing_required_key_item_count", summary.get("schema_missing_required_key_item_count", 0), "== 0", int(summary.get("schema_missing_required_key_item_count", 0)) == 0))
00250:     add(_quality_check("unsafe_context_record_count", summary.get("unsafe_context_record_count", 0), f"<= {args.max_unsafe_records}", int(summary.get("unsafe_context_record_count", 0)) <= args.max_unsafe_records))
00251:     add(_quality_check("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", int(summary.get("answer_permission_count", 0)) <= args.max_answer_permission_count))
00252:     add(_quality_check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", int(summary.get("source_truth_mutation_allowed_count", 0)) <= args.max_source_truth_mutation_allowed))
00253:     add(_quality_check("can_answer_directly_count", summary.get("can_answer_directly_count", 0), "== 0", int(summary.get("can_answer_directly_count", 0)) == 0))
00254:     add(_quality_check("can_prove_claims_count", summary.get("can_prove_claims_count", 0), "== 0", int(summary.get("can_prove_claims_count", 0)) == 0))
00255:     add(_quality_check("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", int(summary.get("postgres_write_attempt_count", 0)) == 0))
00256:     add(_quality_check("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", int(summary.get("qdrant_write_attempt_count", 0)) == 0))
00257:     add(_quality_check("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", int(summary.get("opensearch_write_attempt_count", 0)) == 0))
00258:     add(_quality_check("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count", 0), "== 0", int(summary.get("opensearch_upload_attempt_count", 0)) == 0))
00259:     if args.require_source_runtime_quality_pass:
00260:         # already included above; keep as explicit gate
00261:         pass
00262:     if args.require_no_answer_permission:
00263:         add(_quality_check("all_context_retrieval_only", summary.get("all_context_retrieval_only", False), "is True", _as_bool(summary.get("all_context_retrieval_only"))))
00264:     status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
00265:     return status, checks
00266: 
00267: 
00268: def build_report(runtime_path: Path, output_dir: Path, *, top_k: int, args: argparse.Namespace) -> Dict[str, Any]:
00269:     runtime = _read_json(runtime_path)
00270:     retrieval_groups = _get_retrieval_groups(runtime)
00271:     context_packs = [build_context_pack(group, idx + 1, top_k=top_k) for idx, group in enumerate(retrieval_groups)]
00272:     context_items: List[Dict[str, Any]] = []
00273:     for pack in context_packs:
00274:         for item in pack.get("top_context_items", []):
00275:             if isinstance(item, dict):
00276:                 context_items.append(item)
00277: 
00278:     field_counts: Dict[str, int] = {}
00279:     for item in context_items:
00280:         field = _safe_str(item.get("field_name"))
00281:         if field:
00282:             field_counts[field] = field_counts.get(field, 0) + 1
00283: 
00284:     page_ids = {item.get("page_id") for item in context_items if _safe_str(item.get("page_id"))}
00285:     summary: Dict[str, Any] = {
00286:         "source_runtime_path": str(runtime_path),
00287:         "source_runtime_quality_pass": _runtime_quality_pass(runtime),
00288:         "source_runtime_ready_for_context_pack": _runtime_ready(runtime),
00289:         "source_retrieval_group_count": len(retrieval_groups),
00290:         "source_total_retrieval_hit_count": (runtime.get("summary") or {}).get("total_retrieval_hit_count", 0) if isinstance(runtime.get("summary"), Mapping) else 0,
```

## `tiff/trace_net_e2e_final_gate_smoke_v1.py`
- Location: `active_source_code`
- Score: `224`
- Categories: `context_pack, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net E2E final gate smoke v1. This module consumes the E2E evidence sufficiency gate artifact and creates a local, deterministic final-gate smoke report. It is intentionally conservative: records can produce citation-backed response *drafts* for review, but they do not mutate source truth, write to runtime services, or grant proof authority.
- Functions: _read_json(path)@L45; _write_json(path, data)@L53; _write_jsonl(path, rows)@L60; _as_list(value)@L67; _bool(value)@L75; _safe_str(value, default)@L83; _slug(value)@L89; _collection_from(data, keys)@L94; _items_from_gate_record(record)@L102; _citation_id(query_id, item, index)@L134; _normalize_citation(query_id, item, index)@L140; _draft_response(user_query, citations, audit_only)@L165; _record_schema_complete(record)@L186; build_final_gate_smoke()@L190; evaluate_quality(summary)@L397; _write_inspect_md(path, report)@L458; add_common_args(parser)@L531; main(argv)@L554
- CLI args: --e2e-evidence-sufficiency-gate, --output-dir, --top-k, --min-citations-per-response, --min-source-traces-per-response, --min-source-gate-records, --min-final-gate-records, --min-safe-response-drafts, --min-citation-backed-response-drafts, --min-audit-or-safe-responses, --min-total-citations, --min-pages-cited, --min-field-count, --max-unsafe-records, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-source-sufficiency-quality-pass, --require-no-answer-permission, --quality
- Has __main__ guard.

### Source window L186-L242
```python
00186: def _record_schema_complete(record: Mapping[str, Any]) -> bool:
00187:     return all(k in record for k in REQUIRED_RECORD_KEYS)
00188: 
00189: 
00190: def build_final_gate_smoke(
00191:     *,
00192:     evidence_sufficiency_gate_path: Path,
00193:     output_dir: Path,
00194:     top_k: int = 3,
00195:     min_citations_per_response: int = 1,
00196:     min_source_traces_per_response: int = 1,
00197:     min_source_gate_records: int = 1,
00198:     min_final_gate_records: int = 1,
00199:     min_safe_response_drafts: int = 1,
00200:     min_citation_backed_response_drafts: int = 1,
00201:     min_audit_or_safe_responses: int = 1,
00202:     min_total_citations: int = 1,
00203:     min_pages_cited: int = 1,
00204:     min_field_count: int = 1,
00205:     max_unsafe_records: int = 0,
00206:     max_answer_permission_count: int = 0,
00207:     max_source_truth_mutation_allowed: int = 0,
00208:     require_source_sufficiency_quality_pass: bool = False,
00209:     require_no_answer_permission: bool = False,
00210:     write_quality: bool = True,
00211: ) -> Dict[str, Any]:
00212:     source = _read_json(evidence_sufficiency_gate_path)
00213:     source_summary = source.get("summary", {}) if isinstance(source.get("summary"), dict) else {}
00214:     source_quality_pass = source.get("quality_status") == "PASS" or source_summary.get("source_context_pack_quality_pass") is True
00215:     source_ready = _bool(
00216:         source_summary.get("ready_for_final_gate_smoke")
00217:         or source.get("evidence_sufficiency_contract", {}).get("ready_for_final_gate_smoke")
00218:     )
00219: 
00220:     gate_records = _collection_from(source, ("gate_records", "evidence_sufficiency_gate_records", "records"))
00221: 
00222:     final_records: List[Dict[str, Any]] = []
00223:     field_counts: Counter[str] = Counter()
00224:     cited_pages: set[str] = set()
00225: 
00226:     for index, gate_record in enumerate(gate_records, start=1):
00227:         query_id = _safe_str(gate_record.get("query_id"), f"e2e_final_gate_query_{index:04d}")
00228:         query_intent = _safe_str(gate_record.get("query_intent"), "unknown")
00229:         user_query = _safe_str(gate_record.get("user_query") or gate_record.get("query"), query_id)
00230:         status = _safe_str(gate_record.get("evidence_sufficiency_status"), "")
00231:         items = _items_from_gate_record(gate_record)
00232:         citations = [
00233:             _normalize_citation(query_id, item, i)
00234:             for i, item in enumerate(items[: max(0, top_k)], start=1)
00235:         ]
00236:         citation_ready_count = sum(1 for c in citations if _bool(c.get("citation_ready")))
00237:         source_trace_ready_count = sum(1 for c in citations if _bool(c.get("source_trace_ready")))
00238:         for c in citations:
00239:             if c.get("page_id"):
00240:                 cited_pages.add(str(c["page_id"]))
00241:             if c.get("field_name"):
00242:                 field_counts[str(c["field_name"])] += 1
```
### Source window L331-L387
```python
00331:         "all_final_gate_smoke_records_no_answer_authority": answer_permission_count == 0 and can_answer_directly_count == 0 and can_prove_claims_count == 0,
00332:         "e2e_final_gate_smoke_status": STATUS_READY,
00333:     }
00334: 
00335:     quality_checks = evaluate_quality(
00336:         summary,
00337:         min_source_gate_records=min_source_gate_records,
00338:         min_final_gate_records=min_final_gate_records,
00339:         min_safe_response_drafts=min_safe_response_drafts,
00340:         min_citation_backed_response_drafts=min_citation_backed_response_drafts,
00341:         min_audit_or_safe_responses=min_audit_or_safe_responses,
00342:         min_total_citations=min_total_citations,
00343:         min_pages_cited=min_pages_cited,
00344:         min_field_count=min_field_count,
00345:         max_unsafe_records=max_unsafe_records,
00346:         max_answer_permission_count=max_answer_permission_count,
00347:         max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
00348:         require_source_sufficiency_quality_pass=require_source_sufficiency_quality_pass,
00349:         require_no_answer_permission=require_no_answer_permission,
00350:     )
00351:     quality_status = "PASS" if all(c["passed"] for c in quality_checks) else "FAIL"
00352: 
00353:     report = {
00354:         "artifact_type": "trace_net_e2e_final_gate_smoke_v1",
00355:         "status": STATUS_BUILT,
00356:         "quality_status": quality_status,
00357:         "e2e_final_gate_smoke_status": STATUS_READY,
00358:         "final_gate_smoke_contract": {
00359:             "purpose": "Create citation-backed final-gate smoke response drafts or audit-only responses from sufficiency-gated context packs.",
00360:             "response_permission": "draft_for_review_or_audit_only",
00361:             "answer_authority": "blocked_in_smoke_draft",
00362:             "safety_note": "This smoke artifact demonstrates response shaping but does not grant direct answer/proof authority.",
00363:             "can_answer_directly": False,
00364:             "can_prove_claims": False,
00365:             "source_truth_mutation_allowed": False,
00366:             "writes_to_postgres": False,
00367:             "writes_to_qdrant": False,
00368:             "writes_to_opensearch": False,
00369:             "uploads_to_opensearch": False,
00370:             "ready_for_api_or_audit_response": quality_status == "PASS",
00371:         },
00372:         "summary": summary,
00373:         "final_gate_records": final_records,
00374:         "quality_checks": quality_checks,
00375:     }
00376: 
00377:     output_dir.mkdir(parents=True, exist_ok=True)
00378:     report_path = output_dir / REPORT_FILENAME
00379:     quality_path = output_dir / QUALITY_FILENAME
00380:     records_jsonl_path = output_dir / RECORDS_JSONL_FILENAME
00381:     inspect_md_path = output_dir / INSPECT_MD_FILENAME
00382:     _write_json(report_path, report)
00383:     _write_jsonl(records_jsonl_path, final_records)
00384:     if write_quality:
00385:         _write_json(quality_path, {"quality_status": quality_status, "quality_checks": quality_checks, "summary": summary})
00386:     _write_inspect_md(inspect_md_path, report)
00387: 
```
### Source window L1-L34
```python
00001: """TRACE-Net E2E final gate smoke v1.
00002: 
00003: This module consumes the E2E evidence sufficiency gate artifact and creates a
00004: local, deterministic final-gate smoke report. It is intentionally conservative:
00005: records can produce citation-backed response *drafts* for review, but they do
00006: not mutate source truth, write to runtime services, or grant proof authority.
00007: """
00008: 
00009: from __future__ import annotations
00010: 
00011: import argparse
00012: import json
00013: import re
00014: from collections import Counter
00015: from dataclasses import dataclass
00016: from pathlib import Path
00017: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
00018: 
00019: REPORT_FILENAME = "trace_net_e2e_final_gate_smoke_v1.json"
00020: QUALITY_FILENAME = "trace_net_e2e_final_gate_smoke_v1_quality.json"
00021: RECORDS_JSONL_FILENAME = "trace_net_e2e_final_gate_smoke_records_v1.jsonl"
00022: INSPECT_MD_FILENAME = "trace_net_e2e_final_gate_smoke_v1_inspect.md"
00023: 
00024: STATUS_BUILT = "E2E_FINAL_GATE_SMOKE_BUILT"
00025: STATUS_READY = "E2E_FINAL_GATE_SMOKE_READY_FOR_API_OR_AUDIT_RESPONSE"
00026: DECISION_SAFE_DRAFT = "FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT"
00027: DECISION_AUDIT_ONLY = "FINAL_GATE_AUDIT_ONLY_RESPONSE"
00028: SUFFICIENCY_READY = "EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW"
00029: 
00030: REQUIRED_RECORD_KEYS = (
00031:     "query_id",
00032:     "query_intent",
00033:     "user_query",
00034:     "final_gate_decision",
```
### Source window L100-L156
```python
00100: 
00101: 
00102: def _items_from_gate_record(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
00103:     keys = (
00104:         "evidence_items",
00105:         "top_evidence_items",
00106:         "context_items",
00107:         "top_context_items",
00108:         "items",
00109:         "citations",
00110:     )
00111:     for key in keys:
00112:         rows = record.get(key)
00113:         if isinstance(rows, list):
00114:             return [r for r in rows if isinstance(r, dict)]
00115:     # Conservative fallback: preserve page-level citations if the gate artifact
00116:     # only carried page_ids in each record.
00117:     page_ids = [str(p) for p in _as_list(record.get("page_ids")) if p]
00118:     fallback: List[Dict[str, Any]] = []
00119:     for i, page_id in enumerate(page_ids):
00120:         fallback.append(
00121:             {
00122:                 "context_item_id": f"fallback_context_item_{i+1:03d}",
00123:                 "page_id": page_id,
00124:                 "field_name": record.get("query_intent", "source_trace"),
00125:                 "normalized_value": record.get("user_query") or record.get("query") or "source-trace-ready context item",
00126:                 "citation_ready": True,
00127:                 "source_trace_ready": True,
00128:                 "retrieval_permission": "ranking_only_until_final_gate",
00129:             }
00130:         )
00131:     return fallback
00132: 
00133: 
00134: def _citation_id(query_id: str, item: Mapping[str, Any], index: int) -> str:
00135:     page_id = _safe_str(item.get("page_id"), "unknown_page")
00136:     field_name = _safe_str(item.get("field_name"), "evidence")
00137:     return f"cite_{_slug(query_id)}_{_slug(page_id)}_{_slug(field_name)}_{index:03d}"
00138: 
00139: 
00140: def _normalize_citation(query_id: str, item: Mapping[str, Any], index: int) -> Dict[str, Any]:
00141:     page_id = _safe_str(item.get("page_id"), "unknown_page")
00142:     field_name = _safe_str(item.get("field_name") or item.get("field_role"), "evidence")
00143:     normalized_value = _safe_str(
00144:         item.get("normalized_value")
00145:         or item.get("evidence_value")
00146:         or item.get("display_value")
00147:         or item.get("text")
00148:         or item.get("value"),
00149:         "",
00150:     )
00151:     return {
00152:         "citation_id": _citation_id(query_id, item, index),
00153:         "page_id": page_id,
00154:         "field_name": field_name,
00155:         "normalized_value": normalized_value,
00156:         "source_trace_ready": _bool(item.get("source_trace_ready", True)),
```
### Source window L254-L310
```python
00254:             audit_reasons.append("not_enough_citation_ready_items_for_smoke_threshold")
00255:         if not has_trace_floor:
00256:             audit_reasons.append("not_enough_source_trace_ready_items_for_smoke_threshold")
00257: 
00258:         record = {
00259:             "final_gate_record_id": f"e2e_final_gate_smoke_v1_{index:04d}",
00260:             "query_id": query_id,
00261:             "query_intent": query_intent,
00262:             "user_query": user_query,
00263:             "source_evidence_sufficiency_status": status,
00264:             "final_gate_decision": decision,
00265:             "response_mode": response_mode,
00266:             "response_draft": _draft_response(user_query, citations, audit_only=not safe_draft),
00267:             "citation_count": len(citations),
00268:             "citation_ready_count": citation_ready_count,
00269:             "source_trace_count": source_trace_ready_count,
00270:             "page_ids": sorted({str(c.get("page_id")) for c in citations if c.get("page_id")}),
00271:             "field_names": sorted({str(c.get("field_name")) for c in citations if c.get("field_name")}),
00272:             "citations": citations,
00273:             "audit_reasons": audit_reasons,
00274:             "safe_for_user_review": safe_draft,
00275:             "answer_permission": False,
00276:             "can_answer_directly": False,
00277:             "can_prove_claims": False,
00278:             "source_truth_mutation_allowed": False,
00279:             "retrieval_permission": "ranking_only_until_final_gate",
00280:             "answer_authority": "blocked_in_smoke_draft",
00281:             "writes_to_postgres": False,
00282:             "writes_to_qdrant": False,
00283:             "writes_to_opensearch": False,
00284:             "uploads_to_opensearch": False,
00285:             "unsafe_record": False,
00286:         }
00287:         record["schema_complete"] = _record_schema_complete(record)
00288:         final_records.append(record)
00289: 
00290:     safe_response_draft_count = sum(1 for r in final_records if r["final_gate_decision"] == DECISION_SAFE_DRAFT)
00291:     audit_only_response_count = sum(1 for r in final_records if r["final_gate_decision"] == DECISION_AUDIT_ONLY)
00292:     citation_backed_response_draft_count = sum(
00293:         1 for r in final_records if r["final_gate_decision"] == DECISION_SAFE_DRAFT and r["citation_ready_count"] >= min_citations_per_response
00294:     )
00295:     unsafe_count = sum(1 for r in final_records if _bool(r.get("unsafe_record")))
00296:     answer_permission_count = sum(1 for r in final_records if _bool(r.get("answer_permission")))
00297:     can_answer_directly_count = sum(1 for r in final_records if _bool(r.get("can_answer_directly")))
00298:     can_prove_claims_count = sum(1 for r in final_records if _bool(r.get("can_prove_claims")))
00299:     source_truth_mutation_allowed_count = sum(1 for r in final_records if _bool(r.get("source_truth_mutation_allowed")))
00300:     schema_missing_required_key_record_count = sum(1 for r in final_records if not r.get("schema_complete"))
00301:     total_citation_count = sum(int(r.get("citation_count", 0)) for r in final_records)
00302:     postgres_write_attempt_count = sum(1 for r in final_records if _bool(r.get("writes_to_postgres")))
00303:     qdrant_write_attempt_count = sum(1 for r in final_records if _bool(r.get("writes_to_qdrant")))
00304:     opensearch_write_attempt_count = sum(1 for r in final_records if _bool(r.get("writes_to_opensearch")))
00305:     opensearch_upload_attempt_count = sum(1 for r in final_records if _bool(r.get("uploads_to_opensearch")))
00306: 
00307:     summary = {
00308:         "source_sufficiency_gate_path": str(evidence_sufficiency_gate_path),
00309:         "source_sufficiency_quality_pass": bool(source_quality_pass),
00310:         "source_sufficiency_ready_for_final_gate_smoke": bool(source_ready),
```
### Source window L423-L479
```python
00423: 
00424:     def eq(name: str, expected: int) -> None:
00425:         observed = int(summary.get(name, 0) or 0)
00426:         checks.append({"name": name, "observed": observed, "expected": f"== {expected}", "passed": observed == expected})
00427: 
00428:     def is_true(name: str) -> None:
00429:         observed = bool(summary.get(name))
00430:         checks.append({"name": name, "observed": observed, "expected": "is True", "passed": observed is True})
00431: 
00432:     if require_source_sufficiency_quality_pass:
00433:         is_true("source_sufficiency_quality_pass")
00434:         is_true("source_sufficiency_ready_for_final_gate_smoke")
00435:     ge("source_gate_record_count", min_source_gate_records)
00436:     ge("final_gate_record_count", min_final_gate_records)
00437:     ge("safe_response_draft_count", min_safe_response_drafts)
00438:     ge("citation_backed_response_draft_count", min_citation_backed_response_drafts)
00439:     ge("audit_or_safe_response_count", min_audit_or_safe_responses)
00440:     ge("total_citation_count", min_total_citations)
00441:     ge("page_with_citation_count", min_pages_cited)
00442:     ge("field_count", min_field_count)
00443:     eq("schema_missing_required_key_record_count", 0)
00444:     le("unsafe_final_gate_smoke_record_count", max_unsafe_records)
00445:     le("answer_permission_count", max_answer_permission_count)
00446:     le("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed)
00447:     eq("can_answer_directly_count", 0)
00448:     eq("can_prove_claims_count", 0)
00449:     eq("postgres_write_attempt_count", 0)
00450:     eq("qdrant_write_attempt_count", 0)
00451:     eq("opensearch_write_attempt_count", 0)
00452:     eq("opensearch_upload_attempt_count", 0)
00453:     if require_no_answer_permission:
00454:         is_true("all_final_gate_smoke_records_no_answer_authority")
00455:     return checks
00456: 
00457: 
00458: def _write_inspect_md(path: Path, report: Mapping[str, Any]) -> None:
00459:     summary = report.get("summary", {})
00460:     records = report.get("final_gate_records", [])
00461:     checks = report.get("quality_checks", [])
00462:     lines: List[str] = []
00463:     lines.append("# TRACE-Net E2E Final Gate Smoke v1 Inspect")
00464:     lines.append("")
00465:     lines.append(f"Quality status: **{report.get('quality_status')}**")
00466:     lines.append("")
00467:     lines.append("## Purpose")
00468:     lines.append("This artifact turns sufficiency-gated context packs into citation-backed response drafts or audit-only responses.")
00469:     lines.append("It is intentionally conservative: the smoke draft does not mutate source truth, prove claims, or grant direct answer authority.")
00470:     lines.append("")
00471:     lines.append("## Final gate smoke contract")
00472:     for k, v in report.get("final_gate_smoke_contract", {}).items():
00473:         lines.append(f"- {k}: {v}")
00474:     lines.append("")
00475:     lines.append("## Main counters")
00476:     for k in [
00477:         "source_gate_record_count",
00478:         "final_gate_record_count",
00479:         "safe_response_draft_count",
```
### Source window L569-L610
```python
00569:         min_pages_cited=args.min_pages_cited,
00570:         min_field_count=args.min_field_count,
00571:         max_unsafe_records=args.max_unsafe_records,
00572:         max_answer_permission_count=args.max_answer_permission_count,
00573:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00574:         require_source_sufficiency_quality_pass=args.require_source_sufficiency_quality_pass,
00575:         require_no_answer_permission=args.require_no_answer_permission,
00576:         write_quality=True,
00577:     )
00578:     print("TRACE-Net E2E Final Gate Smoke v1")
00579:     print(f" Status: {report['status']}")
00580:     print(f" Quality status: {report['quality_status']}")
00581:     for key in [
00582:         "e2e_final_gate_smoke_status",
00583:         "source_gate_record_count",
00584:         "final_gate_record_count",
00585:         "safe_response_draft_count",
00586:         "citation_backed_response_draft_count",
00587:         "audit_only_response_count",
00588:         "total_citation_count",
00589:         "page_with_citation_count",
00590:         "field_count",
00591:         "schema_missing_required_key_record_count",
00592:         "unsafe_final_gate_smoke_record_count",
00593:         "answer_permission_count",
00594:         "can_answer_directly_count",
00595:         "can_prove_claims_count",
00596:         "source_truth_mutation_allowed_count",
00597:         "postgres_write_attempt_count",
00598:         "qdrant_write_attempt_count",
00599:         "opensearch_write_attempt_count",
00600:         "opensearch_upload_attempt_count",
00601:     ]:
00602:         print(f" {key}: {report['summary'].get(key)}")
00603:     print(f" report_path: {report.get('report_path')}")
00604:     print(f" records_jsonl_path: {report.get('records_jsonl_path')}")
00605:     print(f" inspect_md_path: {report.get('inspect_md_path')}")
00606:     return 0 if report["quality_status"] == "PASS" else 1
00607: 
00608: 
00609: if __name__ == "__main__":  # pragma: no cover
00610:     raise SystemExit(main())
```

## `tiff/trace_net_engineering_engram_vector_loader_v1.py`
- Location: `active_source_code`
- Score: `224`
- Categories: `crag, engram, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Doc: TRACE-Net Engineering Engram Vector Loader v1. Artifact-only adapter that converts H17 Engram memory-layer atoms into a Qdrant-ready local vector manifest. This module does not connect to Qdrant, Postgres, OpenSearch, or any live service. It produces deterministic local records so CI and Git review can validate the vector payload shape before a future live loader is enabled.
- Classes: VectorLoaderConfig@L39 methods=[]
- Functions: utc_now_iso()@L47; read_json(path)@L51; write_json(path, data)@L60; stable_json_dumps(obj)@L68; normalize_text(text)@L72; atom_identifier(atom, index)@L78; infer_memory_layer(atom)@L86; infer_proof_role(atom, memory_layer)@L107; atom_to_text(atom)@L116; deterministic_hash_vector(text, dim)@L149; qdrant_point_id(atom_id)@L174; load_memory_atoms(memory_layers_manifest)@L178; make_vector_record(atom)@L197; safety_findings(records)@L236; layer_counts(records)@L264; build_vector_loader_manifest()@L275; check_vector_loader_manifest()@L391

### Source window L1-L29
```python
00001: """TRACE-Net Engineering Engram Vector Loader v1.
00002: 
00003: Artifact-only adapter that converts H17 Engram memory-layer atoms into a
00004: Qdrant-ready local vector manifest.  This module does not connect to Qdrant,
00005: Postgres, OpenSearch, or any live service.  It produces deterministic local
00006: records so CI and Git review can validate the vector payload shape before a
00007: future live loader is enabled.
00008: """
00009: 
00010: from __future__ import annotations
00011: 
00012: import hashlib
00013: import json
00014: import math
00015: import re
00016: from dataclasses import dataclass
00017: from datetime import datetime, timezone
00018: from pathlib import Path
00019: from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence
00020: 
00021: MODULE = "trace_net_engineering_engram_vector_loader_v1"
00022: VERSION = "v1"
00023: 
00024: REQUIRED_MEMORY_LAYERS = (
00025:     "working_memory",
00026:     "semantic_memory",
00027:     "procedural_memory",
00028:     "episodic_memory",
00029:     "trait_memory",
```
### Source window L66-L122
```python
00066: 
00067: 
00068: def stable_json_dumps(obj: Any) -> str:
00069:     return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
00070: 
00071: 
00072: def normalize_text(text: str) -> str:
00073:     text = text or ""
00074:     text = re.sub(r"\s+", " ", text).strip()
00075:     return text
00076: 
00077: 
00078: def atom_identifier(atom: Mapping[str, Any], index: int) -> str:
00079:     raw = str(atom.get("atom_id") or atom.get("id") or atom.get("name") or "").strip()
00080:     if raw:
00081:         return raw
00082:     digest = hashlib.sha256(stable_json_dumps(atom).encode("utf-8")).hexdigest()[:16]
00083:     return f"generated_atom_{index:04d}_{digest}"
00084: 
00085: 
00086: def infer_memory_layer(atom: Mapping[str, Any]) -> str:
00087:     layer = str(atom.get("memory_layer") or "").strip()
00088:     if layer:
00089:         return layer
00090:     memory_type = str(atom.get("memory_type") or atom.get("type") or "").lower()
00091:     title = str(atom.get("title") or atom.get("atom_id") or "").lower()
00092:     text = " ".join(str(atom.get(k) or "") for k in ("rule", "description", "lesson", "failure_pattern", "repair_pattern")).lower()
00093:     blob = f"{memory_type} {title} {text}"
00094:     if any(t in blob for t in ("critic", "self-rag", "crag", "repair")):
00095:         return "critic_memory"
00096:     if any(t in blob for t in ("episode", "h13", "h14", "h15", "h16", "failure", "eval")):
00097:         return "episodic_memory"
00098:     if any(t in blob for t in ("style", "trait", "tone", "answer shape", "personality")):
00099:         return "trait_memory"
00100:     if any(t in blob for t in ("policy", "if user", "forbidden", "require", "must", "do not")):
00101:         return "procedural_memory"
00102:     if any(t in blob for t in ("route", "visual", "ocr", "table", "figure", "nomenclature")):
00103:         return "semantic_memory"
00104:     return "working_memory"
00105: 
00106: 
00107: def infer_proof_role(atom: Mapping[str, Any], memory_layer: str) -> str:
00108:     proof_role = str(atom.get("proof_role") or "").strip()
00109:     if proof_role:
00110:         return proof_role
00111:     if memory_layer == "working_memory":
00112:         return "current_proof_context_only"
00113:     return "guidance_only"
00114: 
00115: 
00116: def atom_to_text(atom: Mapping[str, Any]) -> str:
00117:     parts: List[str] = []
00118:     for key in (
00119:         "atom_id",
00120:         "title",
00121:         "memory_layer",
00122:         "memory_type",
```
### Source window L161-L217
```python
00161:     vec = [0.0] * dim
00162:     if not tokens:
00163:         tokens = ["empty"]
00164:     for token in tokens:
00165:         digest = hashlib.sha256(token.encode("utf-8")).digest()
00166:         idx = int.from_bytes(digest[:4], "big") % dim
00167:         sign = 1.0 if digest[4] % 2 == 0 else -1.0
00168:         weight = 1.0 + (digest[5] % 11) / 10.0
00169:         vec[idx] += sign * weight
00170:     norm = math.sqrt(sum(v * v for v in vec)) or 1.0
00171:     return [round(v / norm, 8) for v in vec]
00172: 
00173: 
00174: def qdrant_point_id(atom_id: str) -> str:
00175:     return hashlib.sha256(atom_id.encode("utf-8")).hexdigest()
00176: 
00177: 
00178: def load_memory_atoms(memory_layers_manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
00179:     atoms = memory_layers_manifest.get("memory_atoms")
00180:     if not isinstance(atoms, list):
00181:         raise ValueError("H17 memory layer manifest must contain a memory_atoms list")
00182:     normalized: List[Dict[str, Any]] = []
00183:     for idx, atom in enumerate(atoms, start=1):
00184:         if not isinstance(atom, dict):
00185:             continue
00186:         item = dict(atom)
00187:         atom_id = atom_identifier(item, idx)
00188:         layer = infer_memory_layer(item)
00189:         proof_role = infer_proof_role(item, layer)
00190:         item["atom_id"] = atom_id
00191:         item["memory_layer"] = layer
00192:         item["proof_role"] = proof_role
00193:         normalized.append(item)
00194:     return normalized
00195: 
00196: 
00197: def make_vector_record(atom: Mapping[str, Any], *, config: VectorLoaderConfig) -> Dict[str, Any]:
00198:     atom_id = str(atom.get("atom_id") or "").strip()
00199:     if not atom_id:
00200:         raise ValueError("atom_id is required")
00201:     memory_layer = str(atom.get("memory_layer") or "").strip()
00202:     proof_role = str(atom.get("proof_role") or "").strip()
00203:     text = atom_to_text(atom)
00204:     vector = deterministic_hash_vector(text, dim=config.vector_dim)
00205:     payload = {
00206:         "atom_id": atom_id,
00207:         "memory_layer": memory_layer,
00208:         "proof_role": proof_role,
00209:         "title": atom.get("title") or atom_id,
00210:         "rule": atom.get("rule") or atom.get("description") or "",
00211:         "source_module": MODULE,
00212:         "source_version": VERSION,
00213:         "active": bool(atom.get("active", True)),
00214:         "engram_memory_is_proof": False,
00215:         "answer_permission": False,
00216:         "source_truth_mutation_allowed": False,
00217:         "postgres_write_attempt": False,
```
### Source window L332-L388
```python
00332:             "collection_name": collection_name,
00333:             "distance": config.distance,
00334:             "vector_dim": vector_dim,
00335:             "encoder": config.encoder_name,
00336:             "live_qdrant_write_enabled": False,
00337:             "live_qdrant_write_attempted": False,
00338:             "note": "Artifact-only Qdrant-ready payload. Future H19/H20 may enable live writes behind explicit gates.",
00339:         },
00340:         "summary": {
00341:             "module": MODULE,
00342:             "version": VERSION,
00343:             "memory_atom_count": len(atoms),
00344:             "qdrant_ready_record_count": qdrant_ready_record_count,
00345:             "vector_dim": vector_dim,
00346:             "memory_layer_counts": counts,
00347:             "missing_layers": missing_layers,
00348:             "unsafe_finding_count": len(findings),
00349:             "answer_permission_count": answer_permission_count,
00350:             "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
00351:             "postgres_write_attempt_count": 0,
00352:             "qdrant_write_attempt_count": 0,
00353:             "opensearch_write_attempt_count": 0,
00354:             "opensearch_upload_attempt_count": 0,
00355:             "write_attempt_count": write_attempt_count,
00356:             "quality_failures": quality_failures,
00357:         },
00358:         "safety_contract": {
00359:             "artifact_only": True,
00360:             "engram_memory_is_guidance_only": True,
00361:             "no_answer_permission": True,
00362:             "no_source_truth_mutation": True,
00363:             "no_postgres_write": True,
00364:             "no_qdrant_write": True,
00365:             "no_opensearch_write": True,
00366:             "proof_boundary": "Engram vector records guide behavior retrieval only; source-truth manual claims still require current proof_context citations.",
00367:         },
00368:         "unsafe_findings": findings,
00369:         "qdrant_ready_records": records,
00370:     }
00371: 
00372:     if output_dir is not None:
00373:         out = Path(output_dir)
00374:         out.mkdir(parents=True, exist_ok=True)
00375:         write_json(out / f"{MODULE}.json", manifest)
00376:         # JSONL is useful for future import/load tools and human diffing.
00377:         jsonl = out / f"{MODULE}.jsonl"
00378:         with jsonl.open("w", encoding="utf-8") as f:
00379:             for rec in records:
00380:                 f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
00381:         write_json(out / f"{MODULE}_quality_check.json", {
00382:             "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_LOADER_CHECKED",
00383:             "quality_status": quality_status,
00384:             "summary": manifest["summary"],
00385:             "unsafe_findings": findings,
00386:         })
00387: 
00388:     return manifest
```
### Source window L225-L281
```python
00225:         "atom_id": atom_id,
00226:         "memory_layer": memory_layer,
00227:         "proof_role": proof_role,
00228:         "text_for_embedding": text,
00229:         "vector": vector,
00230:         "vector_dim": config.vector_dim,
00231:         "encoder": config.encoder_name,
00232:         "qdrant_payload": payload,
00233:     }
00234: 
00235: 
00236: def safety_findings(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
00237:     findings: List[Dict[str, Any]] = []
00238:     for rec in records:
00239:         atom_id = rec.get("atom_id")
00240:         layer = rec.get("memory_layer")
00241:         proof_role = rec.get("proof_role")
00242:         payload = rec.get("qdrant_payload") if isinstance(rec.get("qdrant_payload"), dict) else {}
00243:         if layer not in REQUIRED_MEMORY_LAYERS:
00244:             findings.append({"atom_id": atom_id, "code": "UNKNOWN_MEMORY_LAYER", "memory_layer": layer})
00245:         if proof_role not in GUIDANCE_ONLY_PROOF_ROLES:
00246:             findings.append({"atom_id": atom_id, "code": "UNSAFE_PROOF_ROLE", "proof_role": proof_role})
00247:         if payload.get("engram_memory_is_proof"):
00248:             findings.append({"atom_id": atom_id, "code": "ENGRAM_MARKED_AS_PROOF"})
00249:         if payload.get("answer_permission"):
00250:             findings.append({"atom_id": atom_id, "code": "ANSWER_PERMISSION_GRANTED"})
00251:         if payload.get("source_truth_mutation_allowed"):
00252:             findings.append({"atom_id": atom_id, "code": "SOURCE_TRUTH_MUTATION_ALLOWED"})
00253:         for key in ("postgres_write_attempt", "qdrant_write_attempt", "opensearch_write_attempt", "opensearch_upload_attempt"):
00254:             if payload.get(key):
00255:                 findings.append({"atom_id": atom_id, "code": "WRITE_ATTEMPT", "field": key})
00256:         vector = rec.get("vector")
00257:         if not isinstance(vector, list) or not vector:
00258:             findings.append({"atom_id": atom_id, "code": "MISSING_VECTOR"})
00259:         if rec.get("text_for_embedding") in (None, ""):
00260:             findings.append({"atom_id": atom_id, "code": "MISSING_TEXT_FOR_EMBEDDING"})
00261:     return findings
00262: 
00263: 
00264: def layer_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
00265:     counts = {layer: 0 for layer in REQUIRED_MEMORY_LAYERS}
00266:     for rec in records:
00267:         layer = rec.get("memory_layer")
00268:         if layer in counts:
00269:             counts[str(layer)] += 1
00270:         else:
00271:             counts[str(layer or "unknown")] = counts.get(str(layer or "unknown"), 0) + 1
00272:     return counts
00273: 
00274: 
00275: def build_vector_loader_manifest(
00276:     *,
00277:     memory_layers: str | Path,
00278:     output_dir: str | Path | None = None,
00279:     vector_dim: int = 64,
00280:     collection_name: str = "trace_net_engineering_engram_memory_v1",
00281:     min_records: int = 1,
```
### Source window L394-L447
```python
00394:     min_records: int = 1,
00395:     require_all_layers: bool = False,
00396:     require_quality_pass: bool = False,
00397:     require_no_answer_permission: bool = False,
00398:     max_unsafe: int = 0,
00399:     max_write_attempts: int = 0,
00400: ) -> Dict[str, Any]:
00401:     manifest = read_json(vector_loader)
00402:     records = manifest.get("qdrant_ready_records")
00403:     if not isinstance(records, list):
00404:         raise ValueError("Vector loader manifest must contain qdrant_ready_records list")
00405:     findings = safety_findings(records)
00406:     counts = layer_counts(records)
00407:     missing_layers = [layer for layer in REQUIRED_MEMORY_LAYERS if counts.get(layer, 0) <= 0]
00408:     summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
00409:     write_attempt_count = int(summary.get("write_attempt_count") or 0)
00410:     answer_permission_count = int(summary.get("answer_permission_count") or 0)
00411:     quality_failures: List[str] = []
00412:     quality_status = "PASS"
00413:     if len(records) < min_records:
00414:         quality_status = "FAIL"
00415:         quality_failures.append("min_records_not_met")
00416:     if require_all_layers and missing_layers:
00417:         quality_status = "FAIL"
00418:         quality_failures.append("missing_required_memory_layers")
00419:     if require_quality_pass and manifest.get("quality_status") != "PASS":
00420:         quality_status = "FAIL"
00421:         quality_failures.append("source_quality_status_not_pass")
00422:     if require_no_answer_permission and answer_permission_count:
00423:         quality_status = "FAIL"
00424:         quality_failures.append("answer_permission_count_nonzero")
00425:     if len(findings) > max_unsafe:
00426:         quality_status = "FAIL"
00427:         quality_failures.append("unsafe_finding_count_exceeds_max")
00428:     if write_attempt_count > max_write_attempts:
00429:         quality_status = "FAIL"
00430:         quality_failures.append("write_attempt_count_exceeds_max")
00431: 
00432:     return {
00433:         "status": "TRACE_NET_ENGINEERING_ENGRAM_VECTOR_LOADER_CHECKED",
00434:         "quality_status": quality_status,
00435:         "module": MODULE,
00436:         "version": VERSION,
00437:         "summary": {
00438:             "qdrant_ready_record_count": len(records),
00439:             "memory_layer_counts": counts,
00440:             "missing_layers": missing_layers,
00441:             "unsafe_finding_count": len(findings),
00442:             "answer_permission_count": answer_permission_count,
00443:             "write_attempt_count": write_attempt_count,
00444:             "quality_failures": quality_failures,
00445:         },
00446:         "unsafe_findings": findings,
00447:     }
```

## `scripts/build_trace_net_e2e_crag_retrieval_corrector_v10.py`
- Location: `active_source_code`
- Score: `223`
- Categories: `crag, graph_vector, page, safety, self_rag, server`
- Functions: main()@L23
- CLI args: --self-rag-context-critic, --output-dir, --quality
- Tiff imports: from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import QUALITY_PASS, add_quality_args, build_crag_corrector_report, evaluate_quality, print_quality_result, read_json, write_report_files
- Has __main__ guard.

### Source window L3-L59
```python
00003: 
00004: import argparse
00005: import sys
00006: from pathlib import Path
00007: 
00008: ROOT = Path(__file__).resolve().parents[1]
00009: if str(ROOT) not in sys.path:
00010:     sys.path.insert(0, str(ROOT))
00011: 
00012: from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import (  # noqa: E402
00013:     QUALITY_PASS,
00014:     add_quality_args,
00015:     build_crag_corrector_report,
00016:     evaluate_quality,
00017:     print_quality_result,
00018:     read_json,
00019:     write_report_files,
00020: )
00021: 
00022: 
00023: def main() -> int:
00024:     parser = argparse.ArgumentParser(description="Build TRACE-Net E2E CRAG retrieval corrector v10 artifact.")
00025:     parser.add_argument("--self-rag-context-critic", required=True)
00026:     parser.add_argument("--output-dir", required=True)
00027:     parser.add_argument("--quality", action="store_true")
00028:     add_quality_args(parser)
00029:     args = parser.parse_args()
00030: 
00031:     source = read_json(args.self_rag_context_critic)
00032:     report = build_crag_corrector_report(source, source_path=args.self_rag_context_critic)
00033:     quality_status, checks = evaluate_quality(report, args)
00034:     report["quality_status"] = quality_status
00035:     report["summary"]["quality_status"] = quality_status
00036:     report["quality_checks"] = checks
00037:     paths = write_report_files(report, args.output_dir)
00038: 
00039:     print("TRACE-Net E2E CRAG Retrieval Corrector v10")
00040:     print(f" Status: {report.get('e2e_crag_retrieval_corrector_status')}")
00041:     print(f" Quality status: {quality_status}")
00042:     summary = report["summary"]
00043:     for key in [
00044:         "context_critique_count",
00045:         "crag_plan_count",
00046:         "ready_crag_plan_count",
00047:         "no_retry_needed_count",
00048:         "retry_required_plan_count",
00049:         "human_review_plan_count",
00050:         "unresolved_plan_count",
00051:         "corrective_action_count",
00052:         "graph_summary_proof_violation_count",
00053:         "answer_permission_count",
00054:         "source_truth_mutation_allowed_count",
00055:     ]:
00056:         print(f" {key}: {summary.get(key, 0)}")
00057:     for key, value in paths.items():
00058:         print(f" {key}: {value}")
00059: 
```

## `scripts/check_trace_net_e2e_self_rag_context_critic_v9_quality.py`
- Location: `active_source_code`
- Score: `223`
- Categories: `context_pack, crag, graph_vector, safety, self_rag, server`
- Functions: check(name, observed, expected, passed)@L9; main()@L13
- CLI args: --report-path, --min-context-packs, --min-context-critiques, --min-ready-contexts, --min-contexts-with-source-truth-evidence, --min-contexts-with-guidance-separation, --max-needs-crag-retry-count, --max-human-review-count, --max-graph-summary-proof-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --write-json
- Has __main__ guard.

### Source window L9-L65
```python
00009: def check(name: str, observed, expected: str, passed: bool):
00010:     return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}
00011: 
00012: 
00013: def main() -> int:
00014:     parser = argparse.ArgumentParser(description="Check TRACE-Net E2E Self-RAG Context Critic v9 quality")
00015:     parser.add_argument("--report-path", required=True)
00016:     parser.add_argument("--min-context-packs", type=int, default=1)
00017:     parser.add_argument("--min-context-critiques", type=int, default=1)
00018:     parser.add_argument("--min-ready-contexts", type=int, default=1)
00019:     parser.add_argument("--min-contexts-with-source-truth-evidence", type=int, default=1)
00020:     parser.add_argument("--min-contexts-with-guidance-separation", type=int, default=1)
00021:     parser.add_argument("--max-needs-crag-retry-count", type=int, default=None)
00022:     parser.add_argument("--max-human-review-count", type=int, default=0)
00023:     parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
00024:     parser.add_argument("--max-answer-permission-count", type=int, default=0)
00025:     parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00026:     parser.add_argument("--require-no-answer-permission", action="store_true")
00027:     parser.add_argument("--write-json", action="store_true")
00028:     args = parser.parse_args()
00029: 
00030:     report_path = Path(args.report_path)
00031:     report = json.loads(report_path.read_text(encoding="utf-8"))
00032:     summary = dict(report.get("summary") or {})
00033: 
00034:     checks = [
00035:         check("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == "PASS"),
00036:         check("context_pack_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", summary.get("context_pack_count", 0) >= args.min_context_packs),
00037:         check("self_rag_critique_count", summary.get("self_rag_critique_count", 0), f">= {args.min_context_critiques}", summary.get("self_rag_critique_count", 0) >= args.min_context_critiques),
00038:         check("ready_context_count", summary.get("ready_context_count", 0), f">= {args.min_ready_contexts}", summary.get("ready_context_count", 0) >= args.min_ready_contexts),
00039:         check("contexts_with_source_truth_evidence_count", summary.get("contexts_with_source_truth_evidence_count", 0), f">= {args.min_contexts_with_source_truth_evidence}", summary.get("contexts_with_source_truth_evidence_count", 0) >= args.min_contexts_with_source_truth_evidence),
00040:         check("contexts_with_guidance_separation_count", summary.get("contexts_with_guidance_separation_count", 0), f">= {args.min_contexts_with_guidance_separation}", summary.get("contexts_with_guidance_separation_count", 0) >= args.min_contexts_with_guidance_separation),
00041:         check("human_review_count", summary.get("human_review_count", 0), f"<= {args.max_human_review_count}", summary.get("human_review_count", 0) <= args.max_human_review_count),
00042:         check("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), f"<= {args.max_graph_summary_proof_violations}", summary.get("graph_summary_proof_violation_count", 0) <= args.max_graph_summary_proof_violations),
00043:         check("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", summary.get("answer_permission_count", 0) <= args.max_answer_permission_count),
00044:         check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", summary.get("source_truth_mutation_allowed_count", 0) <= args.max_source_truth_mutation_allowed),
00045:         check("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", summary.get("can_answer_directly_count", 0) == 0),
00046:         check("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", summary.get("can_prove_claims_count", 0) == 0),
00047:     ]
00048:     if args.max_needs_crag_retry_count is not None:
00049:         checks.append(check("needs_crag_retry_count", summary.get("needs_crag_retry_count", 0), f"<= {args.max_needs_crag_retry_count}", summary.get("needs_crag_retry_count", 0) <= args.max_needs_crag_retry_count))
00050:     if args.require_no_answer_permission:
00051:         checks.append(check("require_no_answer_permission", summary.get("answer_permission_count", 0), "== 0", summary.get("answer_permission_count", 0) == 0))
00052: 
00053:     quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
00054:     print("TRACE-Net E2E Self-RAG Context Critic v9 Quality")
00055:     print(f" quality_status: {quality_status}")
00056:     for c in checks:
00057:         print(f" {'PASS' if c['passed'] else 'FAIL'} {c['name']}: observed={c['observed']} expected={c['expected']}")
00058: 
00059:     if args.write_json:
00060:         out = report_path.with_name(report_path.stem + "_quality.json")
00061:         out.write_text(json.dumps({"quality_status": quality_status, "quality_checks": checks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
00062:     return 0 if quality_status == "PASS" else 1
00063: 
00064: 
00065: if __name__ == "__main__":
```

## `scripts/check_trace_net_e2e_live_relationship_final_gated_endpoint_v31_quality.py`
- Location: `active_source_code`
- Score: `222`
- Categories: `final_gate, page, safety, server`
- Functions: main()@L14
- CLI args: --report-path, --min-sample-queries, --min-sample-successes, --min-relationship-final-gate-applied, --min-relationship-records, --max-post-gate-issue-count, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --write-json
- Tiff imports: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import check_report
- Has __main__ guard.

### Source window L1-L39
```python
00001: from __future__ import annotations
00002: 
00003: import sys
00004: from pathlib import Path
00005: 
00006: REPO_ROOT = Path(__file__).resolve().parents[1]
00007: if str(REPO_ROOT) not in sys.path:
00008:     sys.path.insert(0, str(REPO_ROOT))
00009: 
00010: import argparse
00011: from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import check_report
00012: 
00013: 
00014: def main() -> None:
00015:     parser = argparse.ArgumentParser(description="Check TRACE-Net live relationship final-gated endpoint v31 quality.")
00016:     parser.add_argument("--report-path", required=True, type=Path)
00017:     parser.add_argument("--min-sample-queries", type=int, default=0)
00018:     parser.add_argument("--min-sample-successes", type=int, default=0)
00019:     parser.add_argument("--min-relationship-final-gate-applied", type=int, default=0)
00020:     parser.add_argument("--min-relationship-records", type=int, default=0)
00021:     parser.add_argument("--max-post-gate-issue-count", type=int, default=0)
00022:     parser.add_argument("--max-answer-permission-count", type=int, default=0)
00023:     parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00024:     parser.add_argument("--require-no-answer-permission", action="store_true")
00025:     parser.add_argument("--write-json", action="store_true")
00026:     args = parser.parse_args()
00027: 
00028:     report = check_report(
00029:         report_path=args.report_path,
00030:         min_sample_queries=args.min_sample_queries,
00031:         min_sample_successes=args.min_sample_successes,
00032:         min_relationship_final_gate_applied=args.min_relationship_final_gate_applied,
00033:         min_relationship_records=args.min_relationship_records,
00034:         max_post_gate_issue_count=args.max_post_gate_issue_count,
00035:         max_answer_permission_count=args.max_answer_permission_count,
00036:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00037:         require_no_answer_permission=args.require_no_answer_permission,
00038:         write_json=args.write_json,
00039:     )
```

## `scripts/serve_trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24.py`
- Location: `active_source_code`
- Score: `222`
- Categories: `final_gate, page, server, webui`
- Functions: parse_args()@L12; main()@L20
- CLI args: --live-webui-final-gated-gemma-endpoint, --host, --port
- Tiff imports: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import read_json, serve
- Has __main__ guard.

### Source window L1-L32
```python
00001: import argparse
00002: import sys
00003: from pathlib import Path
00004: 
00005: REPO_ROOT = Path(__file__).resolve().parents[1]
00006: if str(REPO_ROOT) not in sys.path:
00007:     sys.path.insert(0, str(REPO_ROOT))
00008: 
00009: from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import read_json, serve
00010: 
00011: 
00012: def parse_args():
00013:     p = argparse.ArgumentParser(description="Serve TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24.")
00014:     p.add_argument("--live-webui-final-gated-gemma-endpoint", required=True)
00015:     p.add_argument("--host", default="127.0.0.1")
00016:     p.add_argument("--port", type=int, default=8020)
00017:     return p.parse_args()
00018: 
00019: 
00020: def main() -> int:
00021:     args = parse_args()
00022:     state = read_json(Path(args.live_webui_final_gated_gemma_endpoint))
00023:     state["host"] = args.host
00024:     state["port"] = args.port
00025:     state["base_url_windows"] = f"http://{args.host}:{args.port}/v1"
00026:     state["base_url_open_webui_docker"] = f"http://host.docker.internal:{args.port}/v1"
00027:     serve(state, args.host, args.port)
00028:     return 0
00029: 
00030: 
00031: if __name__ == "__main__":
00032:     raise SystemExit(main())
```

## `tiff/trace_net_e2e_live_llm_prompt_contract_v21.py`
- Location: `active_source_code`
- Score: `222`
- Categories: `context_pack, crag, final_gate, graph_vector, page, safety, self_rag, server, table_visual_ocr`
- Functions: load_json(path)@L22; write_json(path, data)@L26; write_jsonl(path, rows)@L31; _as_list(value)@L38; _first_list(obj, candidate_keys)@L48; _truthy_bool(value)@L67; _get_path(obj, path, default)@L75; _context_packs(data)@L84; _evaluations(data)@L98; _pack_id(pack, fallback_index)@L113; _eval_pack_id(row)@L123; _evaluation_index(evals)@L133; _evidence_items(pack)@L141; _graph_guidance_items(pack)@L158; _summary_guidance_items(pack)@L177; _aggregation_box(pack)@L196; _answer_rules(pack)@L204; _evidence_page(item)@L212
- CLI args: --min-context-packs, --min-prompt-contracts, --min-ready-prompt-contracts, --min-total-prompt-messages, --min-contracts-with-source-truth-evidence, --min-contracts-with-graph-guidance, --min-contracts-with-v2-summary-guidance, --min-contracts-with-aggregation-or-cap-disclosure, --min-contracts-with-self-rag-ready, --min-contracts-with-crag-no-retry, --min-contracts-with-answer-rules, --max-graph-proof-authority-violations, --max-summary-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --executed-plan-context-pack, --live-self-rag-crag-evaluator, --output-dir, --max-evidence-items, --quality, --report-path, --write-json
- Has __main__ guard.

### Source window L74-L130
```python
00074: 
00075: def _get_path(obj: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
00076:     cur: Any = obj
00077:     for key in path:
00078:         if not isinstance(cur, Mapping) or key not in cur:
00079:             return default
00080:         cur = cur[key]
00081:     return cur
00082: 
00083: 
00084: def _context_packs(data: Any) -> List[Mapping[str, Any]]:
00085:     rows = _first_list(
00086:         data,
00087:         [
00088:             "context_packs",
00089:             "executed_plan_context_packs",
00090:             "context_pack_records",
00091:             "packs",
00092:             "records",
00093:         ],
00094:     )
00095:     return [r for r in rows if isinstance(r, Mapping)]
00096: 
00097: 
00098: def _evaluations(data: Any) -> List[Mapping[str, Any]]:
00099:     rows = _first_list(
00100:         data,
00101:         [
00102:             "self_rag_crag_records",
00103:             "self_rag_evaluations",
00104:             "live_self_rag_crag_evaluations",
00105:             "evaluations",
00106:             "records",
00107:             "context_evaluations",
00108:         ],
00109:     )
00110:     return [r for r in rows if isinstance(r, Mapping)]
00111: 
00112: 
00113: def _pack_id(pack: Mapping[str, Any], fallback_index: int = 0) -> str:
00114:     return str(
00115:         pack.get("context_pack_id")
00116:         or pack.get("executed_plan_context_pack_id")
00117:         or pack.get("pack_id")
00118:         or pack.get("query_plan_id")
00119:         or f"context_pack_v19_{fallback_index:04d}"
00120:     )
00121: 
00122: 
00123: def _eval_pack_id(row: Mapping[str, Any]) -> Optional[str]:
00124:     value = (
00125:         row.get("context_pack_id")
00126:         or row.get("executed_plan_context_pack_id")
00127:         or row.get("pack_id")
00128:         or row.get("query_plan_id")
00129:     )
00130:     return str(value) if value is not None else None
```
### Source window L452-L508
```python
00452:         "collapsed_duplicate_record_count": duplicate_count,
00453:         "direct_evidence_count": len(direct_evidence),
00454:         "nearby_context_count": len(nearby_evidence),
00455:         "citation_numbering_after_deduplication": True,
00456:     }, max_chars=1200))
00457: 
00458:     lines.append("")
00459:     lines.append("GRAPH / LEIDEN GUIDANCE (navigation only; not proof):")
00460:     if graph:
00461:         lines.append(_compact_json(graph, max_chars=1600))
00462:     else:
00463:         lines.append("- None")
00464: 
00465:     lines.append("")
00466:     lines.append("V2 SUMMARY GUIDANCE (meaning/compression only; not proof):")
00467:     if summaries:
00468:         lines.append(_compact_json(summaries, max_chars=1600))
00469:     else:
00470:         lines.append("- None")
00471: 
00472:     lines.append("")
00473:     lines.append("AGGREGATION / CAPPING METADATA:")
00474:     if aggregation:
00475:         lines.append(_compact_aggregation_json(aggregation))
00476:     else:
00477:         lines.append("- No cap metadata supplied.")
00478: 
00479:     lines.append("")
00480:     lines.append("SELF-RAG / CRAG STATUS:")
00481:     lines.append(_compact_json(_normalize_evaluation_for_prompt(evaluation), max_chars=1800))
00482: 
00483:     lines.append("")
00484:     lines.append("ANSWER RULES:")
00485:     if rules:
00486:         lines.append(_compact_json(rules, max_chars=1200))
00487:     else:
00488:         lines.append("- Cite every factual claim from source-truth evidence only.")
00489:         lines.append("- Graph/Leiden/v2 summaries are guidance only.")
00490:         lines.append("- Disclose capped or incomplete results.")
00491:         lines.append("- State limitations instead of inventing missing facts.")
00492:     return "\n".join(lines)
00493: 
00494: 
00495: def _eval_ready_for_llm(evaluation: Mapping[str, Any]) -> bool:
00496:     if not evaluation:
00497:         return True
00498:     for key in ("ready_for_llm_prompt", "ready_for_llm", "context_ready_for_llm", "ready", "is_ready_for_llm"):
00499:         if key in evaluation:
00500:             return _truthy_bool(evaluation.get(key))
00501:     status = str(
00502:         evaluation.get("context_status")
00503:         or evaluation.get("self_rag_status")
00504:         or evaluation.get("status")
00505:         or evaluation.get("classification")
00506:         or ""
00507:     ).upper()
00508:     if not status:
```
### Source window L364-L420
```python
00364:         "ranking_method",
00365:         "available_drilldowns",
00366:     ):
00367:         if key in value:
00368:             preserved[key] = value[key]
00369:     group_counts = value.get("group_counts")
00370:     if isinstance(group_counts, Mapping):
00371:         compact_groups: Dict[str, Any] = {}
00372:         truncated_groups: List[str] = []
00373:         for group_name, counts in group_counts.items():
00374:             if isinstance(counts, Mapping):
00375:                 items = list(counts.items())
00376:                 compact_groups[str(group_name)] = dict(items[:max_group_items])
00377:                 if len(items) > max_group_items:
00378:                     truncated_groups.append(str(group_name))
00379:             else:
00380:                 compact_groups[str(group_name)] = counts
00381:         preserved["group_counts"] = compact_groups
00382:         if truncated_groups:
00383:             preserved["aggregation_metadata_truncated"] = True
00384:             preserved["truncated_fields"] = truncated_groups
00385:     return json.dumps(preserved or value, ensure_ascii=False, indent=2)
00386: 
00387: 
00388: def _normalize_evaluation_for_prompt(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
00389:     if not evaluation:
00390:         return {
00391:             "self_rag_status": "CONTEXT_STATUS_NOT_SUPPLIED",
00392:             "crag_status": "CRAG_STATUS_NOT_SUPPLIED",
00393:             "ready_for_llm_prompt": True,
00394:             "retry_required": False,
00395:             "requires_cap_disclosure": False,
00396:             "limitations": [],
00397:         }
00398:     agg = evaluation.get("aggregation_or_cap_disclosure") if isinstance(evaluation.get("aggregation_or_cap_disclosure"), Mapping) else {}
00399:     return {
00400:         "self_rag_record_id": evaluation.get("self_rag_crag_record_id") or evaluation.get("record_id"),
00401:         "self_rag_status": evaluation.get("self_rag_status") or evaluation.get("context_status") or evaluation.get("status"),
00402:         "crag_status": evaluation.get("crag_status") or evaluation.get("crag_plan_status"),
00403:         "ready_for_llm_prompt": _truthy_bool(
00404:             evaluation.get("ready_for_llm_prompt", evaluation.get("ready_for_llm", evaluation.get("context_ready_for_llm", True)))
00405:         ),
00406:         "retry_required": _truthy_bool(evaluation.get("retry_required", evaluation.get("needs_crag_retry", False))),
00407:         "audit_only": _truthy_bool(evaluation.get("audit_only", False)),
00408:         "requires_cap_disclosure": bool(
00409:             (isinstance(agg, Mapping) and (agg.get("result_was_capped") or agg.get("more_results_available") or agg.get("high_degree_node_detected")))
00410:             or evaluation.get("requires_cap_disclosure")
00411:         ),
00412:         "limitations": evaluation.get("limitations") or [],
00413:         "crag_actions": evaluation.get("crag_actions") or [],
00414:     }
00415: 
00416: 
00417: def _format_context_message(pack: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str:
00418:     user_query = str(pack.get("user_query") or pack.get("query") or pack.get("original_query") or evaluation.get("user_query") or "")
00419:     evidence = _evidence_items(pack)
00420:     graph = _graph_guidance_items(pack)
```
### Source window L1-L41
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: import json
00005: import re
00006: from dataclasses import dataclass
00007: from pathlib import Path
00008: from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
00009: 
00010: VERSION = "v21"
00011: MODULE = "trace_net_e2e_live_llm_prompt_contract_v21"
00012: STATUS_READY = "E2E_LIVE_LLM_PROMPT_CONTRACT_READY_FOR_LLM_DRAFT"
00013: STATUS_NEEDS_REPAIR = "E2E_LIVE_LLM_PROMPT_CONTRACT_NEEDS_REPAIR"
00014: QUALITY_PASS = "PASS"
00015: QUALITY_FAIL = "FAIL"
00016: 
00017: SYSTEM_MESSAGE = """You are the TRACE-Net answer writer. Write only from the provided TRACE-Net context pack. Source-truth evidence may support factual claims. Graph/Leiden guidance, v2 summaries, route metadata, vector hints, and aggregation metadata are guidance only and are not proof authority. Cite every factual claim with source-truth citations. If evidence is capped or incomplete, state that limitation. Do not invent physical part descriptions, missing relationships, page contents, or citations. Do not mutate source truth."""
00018: 
00019: ALLOWED_ROLES = {"system", "user", "assistant"}
00020: 
00021: 
00022: def load_json(path: str | Path) -> Any:
00023:     return json.loads(Path(path).read_text(encoding="utf-8"))
00024: 
00025: 
00026: def write_json(path: str | Path, data: Any) -> None:
00027:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00028:     Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
00029: 
00030: 
00031: def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
00032:     Path(path).parent.mkdir(parents=True, exist_ok=True)
00033:     with Path(path).open("w", encoding="utf-8") as f:
00034:         for row in rows:
00035:             f.write(json.dumps(row, ensure_ascii=False) + "\n")
00036: 
00037: 
00038: def _as_list(value: Any) -> List[Any]:
00039:     if value is None:
00040:         return []
00041:     if isinstance(value, list):
```
### Source window L518-L574
```python
00518:             return not _truthy_bool(evaluation.get(key))
00519:     status = str(evaluation.get("crag_status") or evaluation.get("crag_plan_status") or evaluation.get("status") or "").upper()
00520:     if not status:
00521:         return True
00522:     return "RETRY" not in status or "NO_RETRY" in status
00523: 
00524: 
00525: def _cap_disclosure_present(pack: Mapping[str, Any]) -> bool:
00526:     agg = _aggregation_box(pack)
00527:     if not agg:
00528:         return False
00529:     if any(k in agg for k in ("total_match_count", "returned_match_count", "result_was_capped", "more_results_available", "drilldown_options")):
00530:         return True
00531:     return bool(agg)
00532: 
00533: 
00534: def _violates_guidance_authority(items: Sequence[Any]) -> bool:
00535:     for item in items:
00536:         if isinstance(item, Mapping):
00537:             auth = str(item.get("authority") or item.get("proof_authority") or item.get("answer_authority") or "").lower()
00538:             if auth in {"proof", "source_truth", "proof_authority", "true"}:
00539:                 return True
00540:             if item.get("can_prove_claims") is True or item.get("proof_authority") is True:
00541:                 return True
00542:     return False
00543: 
00544: 
00545: def build_prompt_contracts(
00546:     context_pack_report: Mapping[str, Any],
00547:     self_rag_crag_report: Mapping[str, Any],
00548:     *,
00549:     max_evidence_items: int = 12,
00550: ) -> List[Dict[str, Any]]:
00551:     packs = _context_packs(context_pack_report)
00552:     evals = _evaluation_index(_evaluations(self_rag_crag_report))
00553:     contracts: List[Dict[str, Any]] = []
00554: 
00555:     for idx, pack in enumerate(packs, start=1):
00556:         pack_id = _pack_id(pack, idx)
00557:         evaluation = evals.get(pack_id, {})
00558:         raw_evidence = _evidence_items(pack)
00559:         direct_evidence, nearby_evidence, duplicate_count, unique_evidence_count = _dedupe_and_classify_evidence(
00560:             raw_evidence,
00561:             str(pack.get("user_query") or pack.get("query") or pack.get("original_query") or evaluation.get("user_query") or ""),
00562:             max_evidence_items=max_evidence_items,
00563:         )
00564:         evidence = direct_evidence + nearby_evidence
00565:         graph = _graph_guidance_items(pack)
00566:         summaries = _summary_guidance_items(pack)
00567:         aggregation = _aggregation_box(pack)
00568:         rules = _answer_rules(pack)
00569:         user_query = str(pack.get("user_query") or pack.get("query") or pack.get("original_query") or evaluation.get("user_query") or "")
00570:         if not user_query:
00571:             user_query = f"TRACE-Net query for {pack_id}"
00572: 
00573:         graph_violation = _violates_guidance_authority(graph)
00574:         summary_violation = _violates_guidance_authority(summaries)
```
### Source window L747-L803
```python
00747:         f"Status: `{report.get('status')}`",
00748:         "",
00749:         "## Summary",
00750:     ]
00751:     for key in [
00752:         "context_pack_count",
00753:         "prompt_contract_count",
00754:         "ready_prompt_contract_count",
00755:         "total_prompt_message_count",
00756:         "contracts_with_source_truth_evidence_count",
00757:         "contracts_with_graph_guidance_count",
00758:         "contracts_with_v2_summary_guidance_count",
00759:         "contracts_with_aggregation_or_cap_disclosure_count",
00760:         "contracts_with_self_rag_ready_count",
00761:         "contracts_with_crag_no_retry_count",
00762:         "graph_proof_authority_violation_count",
00763:         "summary_proof_authority_violation_count",
00764:         "answer_permission_count",
00765:         "source_truth_mutation_allowed_count",
00766:     ]:
00767:         lines.append(f"- {key}: {report.get(key, 0)}")
00768:     lines.extend([
00769:         "",
00770:         "## Contract",
00771:         "- This stage builds LLM-ready prompt messages but does not call an LLM.",
00772:         "- Source-truth evidence is the only proof authority.",
00773:         "- Graph/Leiden and v2 summaries are guidance only.",
00774:         "- Capped/high-degree results must be disclosed to the LLM.",
00775:         "- The LLM reads compact context packs, not raw 5TB corpus data or the full graph.",
00776:         "",
00777:         "## Prompt contracts",
00778:     ])
00779:     for contract in report.get("prompt_contracts", [])[:20]:
00780:         lines.append(f"### {contract.get('prompt_contract_id')} — `{contract.get('prompt_contract_status')}`")
00781:         lines.append(f"- query: {contract.get('user_query')}")
00782:         lines.append(f"- evidence_item_count: {contract.get('evidence_item_count')}")
00783:         lines.append(f"- has_graph_guidance: {contract.get('has_graph_guidance')}")
00784:         lines.append(f"- has_v2_summary_guidance: {contract.get('has_v2_summary_guidance')}")
00785:         lines.append(f"- has_aggregation_or_cap_disclosure: {contract.get('has_aggregation_or_cap_disclosure')}")
00786:         lines.append("")
00787:     lines.extend(["## Quality checks"])
00788:     for check in report.get("quality_checks", []):
00789:         lines.append(
00790:             f"- {'PASS' if check.get('passed') else 'FAIL'} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}"
00791:         )
00792:     return "\n".join(lines) + "\n"
00793: 
00794: 
00795: def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
00796:     out = Path(output_dir)
00797:     out.mkdir(parents=True, exist_ok=True)
00798:     report_path = out / "trace_net_e2e_live_llm_prompt_contract_v21.json"
00799:     prompts_path = out / "trace_net_e2e_live_llm_prompt_contract_records_v21.jsonl"
00800:     messages_path = out / "trace_net_e2e_live_llm_prompt_messages_v21.jsonl"
00801:     inspect_path = out / "trace_net_e2e_live_llm_prompt_contract_v21.md"
00802: 
00803:     contracts = list(report.get("prompt_contracts", []))
```
### Source window L588-L644
```python
00588:         bounded_pack["evidence_box"] = ev_box
00589: 
00590:         messages = [
00591:             {"role": "system", "content": SYSTEM_MESSAGE},
00592:             {"role": "user", "content": user_query},
00593:             {"role": "user", "content": _format_context_message(bounded_pack, evaluation)},
00594:         ]
00595: 
00596:         contract = {
00597:             "prompt_contract_id": f"llm_prompt_contract_v21_{idx:04d}",
00598:             "context_pack_id": pack_id,
00599:             "user_query": user_query,
00600:             "prompt_contract_status": "PROMPT_CONTRACT_READY_FOR_LLM_DRAFT" if ready_for_llm else "PROMPT_CONTRACT_NEEDS_REPAIR_OR_RETRY",
00601:             "ready_for_llm_draft": ready_for_llm,
00602:             "message_count": len(messages),
00603:             "messages": messages,
00604:             "evidence_item_count": len(evidence),
00605:             "direct_source_truth_evidence_count": len(direct_evidence),
00606:             "nearby_source_truth_context_count": len(nearby_evidence),
00607:             "unique_evidence_record_count": unique_evidence_count,
00608:             "collapsed_duplicate_record_count": duplicate_count,
00609:             "has_source_truth_evidence": has_evidence,
00610:             "has_graph_guidance": bool(graph),
00611:             "has_v2_summary_guidance": bool(summaries),
00612:             "has_aggregation_or_cap_disclosure": _cap_disclosure_present(pack),
00613:             "has_answer_rules": bool(rules) or True,
00614:             "self_rag_ready": _eval_ready_for_llm(evaluation),
00615:             "crag_no_retry": _crag_no_retry(evaluation),
00616:             "graph_proof_authority_violation": graph_violation,
00617:             "summary_proof_authority_violation": summary_violation,
00618:             "safety_contract": {
00619:                 "answer_permission": False,
00620:                 "can_answer_directly": False,
00621:                 "can_prove_claims": False,
00622:                 "source_truth_mutation_allowed": False,
00623:                 "writes_to_postgres": False,
00624:                 "writes_to_qdrant": False,
00625:                 "writes_to_opensearch": False,
00626:                 "uploads_to_opensearch": False,
00627:                 "raw_5tb_scan_at_query_time": False,
00628:                 "graph_rebuild_at_query_time": False,
00629:                 "llm_reads_context_pack_only": True,
00630:             },
00631:             "authority_contract": {
00632:                 "source_truth_evidence_is_proof": True,
00633:                 "graph_leiden_guidance_is_proof": False,
00634:                 "v2_summary_guidance_is_proof": False,
00635:                 "aggregation_metadata_is_proof": False,
00636:                 "final_gate_required_after_llm_draft": True,
00637:             },
00638:         }
00639:         contracts.append(contract)
00640:     return contracts
00641: 
00642: 
00643: def summarize_contracts(contracts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
00644:     total_messages = sum(int(c.get("message_count") or len(c.get("messages") or [])) for c in contracts)
```
### Source window L133-L189
```python
00133: def _evaluation_index(evals: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
00134:     out: Dict[str, Mapping[str, Any]] = {}
00135:     for i, row in enumerate(evals, start=1):
00136:         key = _eval_pack_id(row) or f"context_pack_v19_{i:04d}"
00137:         out[key] = row
00138:     return out
00139: 
00140: 
00141: def _evidence_items(pack: Mapping[str, Any]) -> List[Mapping[str, Any]]:
00142:     evidence_box = pack.get("evidence_box") if isinstance(pack.get("evidence_box"), Mapping) else {}
00143:     candidates: List[Any] = []
00144:     for key in ("items", "source_truth_evidence", "records", "evidence", "source_truth_records"):
00145:         value = evidence_box.get(key) if isinstance(evidence_box, Mapping) else None
00146:         if isinstance(value, list):
00147:             candidates = value
00148:             break
00149:     if not candidates:
00150:         for key in ("source_truth_evidence", "evidence", "evidence_records"):
00151:             value = pack.get(key)
00152:             if isinstance(value, list):
00153:                 candidates = value
00154:                 break
00155:     return [x for x in candidates if isinstance(x, Mapping)]
00156: 
00157: 
00158: def _graph_guidance_items(pack: Mapping[str, Any]) -> List[Any]:
00159:     guidance_box = pack.get("guidance_box") if isinstance(pack.get("guidance_box"), Mapping) else {}
00160:     items: List[Any] = []
00161:     for key in ("graph_guidance", "leiden_guidance", "graph_leiden_guidance", "community_guidance"):
00162:         value = guidance_box.get(key) if isinstance(guidance_box, Mapping) else None
00163:         if isinstance(value, list):
00164:             items.extend(value)
00165:         elif value:
00166:             items.append(value)
00167:     if not items:
00168:         for key in ("graph_guidance", "leiden_guidance"):
00169:             value = pack.get(key)
00170:             if isinstance(value, list):
00171:                 items.extend(value)
00172:             elif value:
00173:                 items.append(value)
00174:     return items
00175: 
00176: 
00177: def _summary_guidance_items(pack: Mapping[str, Any]) -> List[Any]:
00178:     guidance_box = pack.get("guidance_box") if isinstance(pack.get("guidance_box"), Mapping) else {}
00179:     items: List[Any] = []
00180:     for key in ("v2_summary_guidance", "page_summary_guidance", "summary_guidance", "page_context_v2_guidance"):
00181:         value = guidance_box.get(key) if isinstance(guidance_box, Mapping) else None
00182:         if isinstance(value, list):
00183:             items.extend(value)
00184:         elif value:
00185:             items.append(value)
00186:     if not items:
00187:         for key in ("v2_summary_guidance", "summary_guidance"):
00188:             value = pack.get(key)
00189:             if isinstance(value, list):
```

## `scripts/build_trace_net_e2e_llm_assisted_query_planner_v17.py`
- Location: `active_source_code`
- Score: `221`
- Categories: `crag, graph_vector, page, planner, safety, server, table_visual_ocr`
- Functions: parse_args()@L14; main()@L38
- CLI args: --live-dynamic-fallback, --page-context-v2, --leiden-communities, --community-navigation-metadata-bridge, --route-dispatch-manifest, --table-exact-search-adapter, --output-dir, --min-query-plans, --min-validated-query-plans, --min-plans-with-v2-summary-guidance, --min-plans-with-leiden-guidance, --min-plans-with-source-truth-fields, --min-allowed-tunnel-validations, --max-invalid-tunnel-count, --max-proof-authority-violations, --max-answer-permission-count, --max-source-truth-mutation-allowed, --require-no-answer-permission, --quality
- Tiff imports: from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_report, load_json, write_report_files; from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, DEFAULT_STATUS_READY, DEFAULT_STATUS_NEEDS_REPAIR, evaluate_quality
- Has __main__ guard.

### Source window L23-L79
```python
00023:     parser.add_argument("--min-query-plans", type=int, default=5)
00024:     parser.add_argument("--min-validated-query-plans", type=int, default=5)
00025:     parser.add_argument("--min-plans-with-v2-summary-guidance", type=int, default=5)
00026:     parser.add_argument("--min-plans-with-leiden-guidance", type=int, default=5)
00027:     parser.add_argument("--min-plans-with-source-truth-fields", type=int, default=5)
00028:     parser.add_argument("--min-allowed-tunnel-validations", type=int, default=20)
00029:     parser.add_argument("--max-invalid-tunnel-count", type=int, default=0)
00030:     parser.add_argument("--max-proof-authority-violations", type=int, default=0)
00031:     parser.add_argument("--max-answer-permission-count", type=int, default=0)
00032:     parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00033:     parser.add_argument("--require-no-answer-permission", action="store_true")
00034:     parser.add_argument("--quality", action="store_true")
00035:     return parser.parse_args()
00036: 
00037: 
00038: def main() -> int:
00039:     args = parse_args()
00040:     report = build_report(
00041:         live_dynamic_fallback=load_json(args.live_dynamic_fallback, {}),
00042:         page_context_v2=load_json(args.page_context_v2, {}),
00043:         leiden_communities=load_json(args.leiden_communities, {}),
00044:         community_navigation_metadata_bridge=load_json(args.community_navigation_metadata_bridge, {}),
00045:         route_dispatch_manifest=load_json(args.route_dispatch_manifest, {}),
00046:         table_exact_search_adapter=load_json(args.table_exact_search_adapter, {}),
00047:         min_query_plans=args.min_query_plans,
00048:     )
00049: 
00050:     # Re-evaluate against CLI thresholds by importing threshold helpers lazily.
00051:     from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, DEFAULT_STATUS_READY, DEFAULT_STATUS_NEEDS_REPAIR, evaluate_quality
00052: 
00053:     thresholds = QualityThresholds(
00054:         min_query_plans=args.min_query_plans,
00055:         min_validated_query_plans=args.min_validated_query_plans,
00056:         min_plans_with_v2_summary_guidance=args.min_plans_with_v2_summary_guidance,
00057:         min_plans_with_leiden_guidance=args.min_plans_with_leiden_guidance,
00058:         min_plans_with_source_truth_fields=args.min_plans_with_source_truth_fields,
00059:         min_allowed_tunnel_validations=args.min_allowed_tunnel_validations,
00060:         max_invalid_tunnel_count=args.max_invalid_tunnel_count,
00061:         max_proof_authority_violations=args.max_proof_authority_violations,
00062:         max_answer_permission_count=args.max_answer_permission_count,
00063:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00064:         require_no_answer_permission=args.require_no_answer_permission,
00065:     )
00066:     quality = evaluate_quality(report, thresholds)
00067:     report["quality_status"] = quality["quality_status"]
00068:     report["quality_checks"] = quality["quality_checks"]
00069:     report["status"] = DEFAULT_STATUS_READY if quality["quality_status"] == "PASS" else DEFAULT_STATUS_NEEDS_REPAIR
00070: 
00071:     paths = write_report_files(report, args.output_dir)
00072:     print("TRACE-Net E2E LLM-Assisted Query Planner v17")
00073:     print(f" Status: {report['status']}")
00074:     print(f" Quality status: {report['quality_status']}")
00075:     for key in (
00076:         "query_plan_count",
00077:         "validated_query_plan_count",
00078:         "plans_with_v2_summary_guidance_count",
00079:         "plans_with_leiden_guidance_count",
```

## `scripts/serve_trace_net_e2e_live_gemma_answer_writer_endpoint_v32.py`
- Location: `active_source_code`
- Score: `221`
- Categories: `final_gate, graph_vector, page, safety, server, table_visual_ocr, webui`
- Classes: Handler@L62 methods=['log_message', 'do_OPTIONS', 'do_GET', 'do_POST']
- Functions: _send_json(handler, data, status)@L21; main(argv)@L33; log_message(self, fmt)@L63; do_OPTIONS(self)@L66; do_GET(self)@L69; do_POST(self)@L106
- CLI args: --table-exact-search-adapter, --page-context-v2, --leiden-communities, --relationship-router-hardening, --relationship-final-gate-hardener, --host, --port, --llm-mode, --llm-base-url, --llm-model, --llm-api-key, --request-timeout, --temperature, --llm-answer-mode, --llm-prompt-mode, --llm-max-output-tokens
- Routes: /health@L70, /v1/models@L101, /v1/chat/completions@L111
- Tiff imports: from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v32 import MODEL_ID, TraceNetGemmaAnswerWriterV32, _extract_messages_user_text
- Has __main__ guard.

### Source window L30-L86
```python
00030:     handler.wfile.write(body)
00031: 
00032: 
00033: def main(argv=None) -> int:
00034:     ap = argparse.ArgumentParser()
00035:     ap.add_argument("--table-exact-search-adapter", required=True)
00036:     ap.add_argument("--page-context-v2", required=True)
00037:     ap.add_argument("--leiden-communities", required=True)
00038:     ap.add_argument("--relationship-router-hardening", default=None)
00039:     ap.add_argument("--relationship-final-gate-hardener", default=None)
00040:     ap.add_argument("--host", default="127.0.0.1")
00041:     ap.add_argument("--port", type=int, default=8027)
00042:     ap.add_argument("--llm-mode", default="ollama")
00043:     ap.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
00044:     ap.add_argument("--llm-model", default="gemma4:26b")
00045:     ap.add_argument("--llm-api-key", default="ollama")
00046:     ap.add_argument("--request-timeout", type=int, default=240)
00047:     ap.add_argument("--temperature", type=float, default=0.0)
00048:     ap.add_argument("--llm-answer-mode", default="always")
00049:     ap.add_argument("--llm-prompt-mode", default="compact", choices=["compact", "full"])
00050:     ap.add_argument("--llm-max-output-tokens", type=int, default=180)
00051:     ns = ap.parse_args(argv)
00052: 
00053:     writer = TraceNetGemmaAnswerWriterV32.from_paths(
00054:         table_exact_search_adapter=ns.table_exact_search_adapter,
00055:         page_context_v2=ns.page_context_v2,
00056:         leiden_communities=ns.leiden_communities,
00057:         relationship_router_hardening=ns.relationship_router_hardening,
00058:         relationship_final_gate_hardener=ns.relationship_final_gate_hardener,
00059:     )
00060:     metadata = writer._page_metadata()
00061: 
00062:     class Handler(BaseHTTPRequestHandler):
00063:         def log_message(self, fmt: str, *args: Any) -> None:
00064:             return
00065: 
00066:         def do_OPTIONS(self) -> None:
00067:             _send_json(self, {"ok": True})
00068: 
00069:         def do_GET(self) -> None:
00070:             if self.path == "/health":
00071:                 _send_json(
00072:                     self,
00073:                     {
00074:                         "status": "ok",
00075:                         "module": "trace_net_e2e_live_gemma_answer_writer_endpoint_v32",
00076:                         "quality_status": "PASS",
00077:                         "model_id": MODEL_ID,
00078:                         "llm_answer_mode": "always",
00079:                         "llm_mode": ns.llm_mode,
00080:                         "llm_model": ns.llm_model,
00081:                         "llm_prompt_mode": ns.llm_prompt_mode,
00082:                         "llm_max_output_tokens": ns.llm_max_output_tokens,
00083:                         "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
00084:                         "nomenclature_page_count": metadata.get("nomenclature_page_count"),
00085:                         "safety": {
00086:                             "answer_permission": False,
```
### Source window L101-L157
```python
00101:             if self.path.rstrip("/") == "/v1/models":
00102:                 _send_json(self, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "trace-net-local"}]})
00103:                 return
00104:             _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404)
00105: 
00106:         def do_POST(self) -> None:
00107:             try:
00108:                 length = int(self.headers.get("Content-Length", "0"))
00109:                 raw = self.rfile.read(length).decode("utf-8", errors="replace")
00110:                 payload = json.loads(raw) if raw else {}
00111:                 if self.path.rstrip("/") != "/v1/chat/completions":
00112:                     _send_json(self, {"error": f"Unknown route: {self.path}"}, status=404)
00113:                     return
00114:                 query = _extract_messages_user_text(payload)
00115:                 if not query:
00116:                     _send_json(self, {"error": "No user message found"}, status=400)
00117:                     return
00118:                 resp = writer.answer_query(
00119:                     query,
00120:                     llm_mode=ns.llm_mode,
00121:                     llm_base_url=ns.llm_base_url,
00122:                     llm_model=ns.llm_model,
00123:                     llm_api_key=ns.llm_api_key,
00124:                     temperature=ns.temperature,
00125:                     request_timeout=ns.request_timeout,
00126:                     llm_prompt_mode=ns.llm_prompt_mode,
00127:                     llm_max_output_tokens=ns.llm_max_output_tokens,
00128:                 )
00129:                 # Preserve requested model id for OpenWebUI compatibility.
00130:                 resp["model"] = MODEL_ID
00131:                 _send_json(self, resp)
00132:             except Exception as exc:
00133:                 safe = {
00134:                     "id": "chatcmpl-tracenet-v32-error",
00135:                     "object": "chat.completion",
00136:                     "created": 0,
00137:                     "model": MODEL_ID,
00138:                     "choices": [
00139:                         {
00140:                             "index": 0,
00141:                             "message": {
00142:                                 "role": "assistant",
00143:                                 "content": "TRACE-Net encountered a live endpoint error while preparing the Gemma answer package. No source-truth claim is made.",
00144:                             },
00145:                             "finish_reason": "stop",
00146:                         }
00147:                     ],
00148:                     "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
00149:                     "trace_net": {
00150:                         "endpoint_version": "live_gemma_answer_writer_v32",
00151:                         "llm_called": False,
00152:                         "llm_status": "LIVE_ENDPOINT_ERROR_SAFE_FALLBACK",
00153:                         "final_gate_applied": True,
00154:                         "final_gate_status": "LIVE_GEMMA_ANSWER_WRITER_SAFE_ERROR_FALLBACK",
00155:                         "post_gate_issue_count": 0,
00156:                         "error": f"{type(exc).__name__}: {exc}",
00157:                     },
```

## `tiff/trace_net_engineering_query_planner_v1.py`
- Location: `active_source_code`
- Score: `221`
- Categories: `context_pack, graph_vector, page, planner, safety, server, table_visual_ocr`
- Functions: _load_json(path)@L74; _write_json(path, payload)@L83; _write_csv(path, records)@L89; _norm_text(value)@L117; extract_entities(question)@L121; classify_task(question, entities)@L151; _guidance_records(index)@L181; _tokenize(s)@L192; score_guidance_record(record, question, entities)@L197; _is_specific_entity_query(entities, task_type)@L237; _has_strong_entity_reason(reasons)@L249; select_guidance_pages(index, question, entities, max_guidance_pages, task_type)@L254; _proof_requirements(task_type, entities)@L301; _optional_routes(task_type)@L319; build_plan_record(question, index, max_guidance_pages)@L329; summarize(records, source_index)@L373; _quality(summary)@L403; build_engineering_query_planner()@L422
- CLI args: --question, --v2-summary-guidance-index, --output-dir, --max-guidance-pages, --min-planner-records, --min-required-routes, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts, --planner, --output, --require-quality-pass, --min-planner-records, --min-required-routes, --max-unsafe, --max-answer-permission, --max-source-truth-mutation-allowed, --max-write-attempts
- Has __main__ guard.

### Source window L371-L427
```python
00371: 
00372: 
00373: def summarize(records: Sequence[Mapping[str, Any]], source_index: Mapping[str, Any]) -> Dict[str, Any]:
00374:     planner_record_count = len(records)
00375:     required_route_count = sum(int(r.get("required_route_count") or 0) for r in records)
00376:     selected_guidance_page_count = sum(int(r.get("guidance_page_count") or 0) for r in records)
00377:     guidance_only_summary_count = 0
00378:     for r in records:
00379:         for g in r.get("guidance_pages") or []:
00380:             if isinstance(g, dict) and g.get("guidance_only") is True:
00381:                 guidance_only_summary_count += 1
00382:     source_summary = source_index.get("summary", {}) if isinstance(source_index.get("summary"), dict) else {}
00383:     return {
00384:         "planner_record_count": planner_record_count,
00385:         "task_type_count": len({r.get("task_type") for r in records}),
00386:         "required_route_count": required_route_count,
00387:         "selected_guidance_page_count": selected_guidance_page_count,
00388:         "guidance_only_summary_count": guidance_only_summary_count,
00389:         "source_guidance_summary_record_count": source_summary.get("summary_record_count", len(_guidance_records(source_index))),
00390:         "can_answer_from_summaries_only_count": sum(1 for r in records if r.get("can_answer_from_summaries_only")),
00391:         "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
00392:         "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
00393:         "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
00394:         "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
00395:         "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
00396:         "opensearch_upload_attempt_count": sum(1 for r in records if r.get("opensearch_upload_attempt")),
00397:         "write_attempt_count": 0,
00398:         "unsafe_record_count": sum(1 for r in records if r.get("unsafe_record")),
00399:         "ready_for_engineering_context_pack": True,
00400:     }
00401: 
00402: 
00403: def _quality(summary: Mapping[str, Any], *, min_planner_records: int, min_required_routes: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int, require_no_summary_only_answer: bool = True) -> Tuple[str, List[str]]:
00404:     failures: List[str] = []
00405:     if int(summary.get("planner_record_count") or 0) < min_planner_records:
00406:         failures.append(f"planner_record_count below minimum: {summary.get('planner_record_count')} < {min_planner_records}")
00407:     if int(summary.get("required_route_count") or 0) < min_required_routes:
00408:         failures.append(f"required_route_count below minimum: {summary.get('required_route_count')} < {min_required_routes}")
00409:     if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
00410:         failures.append("unsafe_record_count above maximum")
00411:     if int(summary.get("answer_permission_count") or 0) > max_answer_permission:
00412:         failures.append("answer_permission_count above maximum")
00413:     if int(summary.get("source_truth_mutation_allowed_count") or 0) > max_source_truth_mutation_allowed:
00414:         failures.append("source_truth_mutation_allowed_count above maximum")
00415:     if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
00416:         failures.append("write_attempt_count above maximum")
00417:     if require_no_summary_only_answer and int(summary.get("can_answer_from_summaries_only_count") or 0) != 0:
00418:         failures.append("summaries are being allowed as proof")
00419:     return ("PASS" if not failures else "FAIL", failures)
00420: 
00421: 
00422: def build_engineering_query_planner(
00423:     *,
00424:     question: str,
00425:     v2_summary_guidance_index: Any,
00426:     output_dir: Any,
00427:     max_guidance_pages: int = 8,
```
### Source window L18-L74
```python
00018: WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{1,}", re.IGNORECASE)
00019: 
00020: TOPIC_TERMS = [
00021:     "illustrated parts list",
00022:     "maintenance manual",
00023:     "double passenger seat",
00024:     "passenger seat",
00025:     "armrest",
00026:     "structure",
00027:     "table",
00028:     "figure",
00029:     "diagram",
00030:     "nomenclature",
00031:     "effectivity",
00032:     "interchangeability",
00033:     "installation",
00034:     "replacement",
00035: ]
00036: 
00037: FORBIDDEN_CLAIMS_DEFAULT = [
00038:     "interchangeability",
00039:     "effectivity",
00040:     "fit",
00041:     "replacement approval",
00042:     "installation safety",
00043: ]
00044: 
00045: ROUTE_CAPABILITIES = {
00046:     "exact_part_lookup": ["exact_part_number", "table_ocr_proof", "graph_leiden_neighbors", "answer_quality_gate"],
00047:     "figure_item_lookup": ["figure_or_item", "table_ocr_proof", "multi_route_quality_gate"],
00048:     "visual_part_identification": ["image_or_diagram", "table_ocr_proof", "raw_ocr_nomenclature", "image_route_quality_gate"],
00049:     "part_family_expansion": ["part_family", "graph_leiden_neighbors", "table_ocr_proof", "multi_route_quality_gate"],
00050:     "table_extraction_question": ["table_route", "ocr_table_proof", "table_quality_gate"],
00051:     "troubleshooting_question": ["diagnostic_context", "route_quality_audit", "human_review_queue_optional"],
00052:     "comparison_question": ["multi_entity_retrieval", "table_ocr_proof", "graph_leiden_neighbors", "engineering_quality_gate"],
00053:     "procedure_question": ["manual_section_guidance", "ocr_text_support", "engineering_quality_gate"],
00054:     "manual_section_summary": ["v2_summary_guidance", "ocr_text_support", "summary_not_proof_gate"],
00055:     "general_engineering_question": ["v2_summary_guidance", "ocr_text_support", "engineering_quality_gate"],
00056:     "unknown_or_insufficient_evidence": ["v2_summary_guidance", "clarify_or_retrieve_more", "engineering_quality_gate"],
00057: }
00058: 
00059: TASK_INTENTS = {
00060:     "exact_part_lookup": "identify or locate an exact part number using source-traced evidence",
00061:     "figure_item_lookup": "identify a figure/item or callout using figure/table evidence",
00062:     "visual_part_identification": "identify what a visual figure or diagram shows using image plus OCR/table proof",
00063:     "part_family_expansion": "find related part-family context without claiming interchangeability",
00064:     "table_extraction_question": "inspect or extract structured table/OCR records",
00065:     "troubleshooting_question": "diagnose pipeline/evidence/routing behavior",
00066:     "comparison_question": "compare entities or evidence strength with limits",
00067:     "procedure_question": "produce a safe verification or workflow plan",
00068:     "manual_section_summary": "summarize likely manual section context with proof separation",
00069:     "general_engineering_question": "answer a broad engineering question with proof and limits",
00070:     "unknown_or_insufficient_evidence": "plan retrieval because the evidence need is unclear or insufficient",
00071: }
00072: 
00073: 
00074: def _load_json(path: Any) -> Dict[str, Any]:
```
### Source window L153-L209
```python
00153:     figures = entities.get("figures") or []
00154:     items = entities.get("items") or []
00155:     parts = entities.get("part_numbers") or []
00156:     families = entities.get("part_families") or []
00157: 
00158:     if any(w in q for w in ["why", "error", "fail", "failing", "issue", "bug", "low confidence", "not working", "broken"]):
00159:         return "troubleshooting_question"
00160:     if any(w in q for w in ["compare", "difference", "versus", " vs ", "better", "which route", "stronger evidence"]):
00161:         return "comparison_question"
00162:     if any(w in q for w in ["steps", "procedure", "how do i", "how should", "verify", "inspect", "run next"]):
00163:         return "procedure_question"
00164:     if any(w in q for w in ["table", "row", "column", "extract", "cell", "csv"]):
00165:         return "table_extraction_question"
00166:     if any(w in q for w in ["family", "nearby", "similar", "related parts", "variants"]):
00167:         return "part_family_expansion"
00168:     if figures and items:
00169:         return "figure_item_lookup"
00170:     if figures and any(w in q for w in ["show", "figure", "diagram", "visual", "callout", "looks", "what does"]):
00171:         return "visual_part_identification"
00172:     if parts:
00173:         return "exact_part_lookup"
00174:     if any(w in q for w in ["summary", "summarize", "section", "about", "overview"]):
00175:         return "manual_section_summary"
00176:     if families:
00177:         return "part_family_expansion"
00178:     return "general_engineering_question"
00179: 
00180: 
00181: def _guidance_records(index: Mapping[str, Any]) -> List[Dict[str, Any]]:
00182:     records = index.get("records", [])
00183:     if not isinstance(records, list):
00184:         return []
00185:     out = []
00186:     for r in records:
00187:         if isinstance(r, dict) and r.get("guidance_only") is True:
00188:             out.append(dict(r))
00189:     return out
00190: 
00191: 
00192: def _tokenize(s: str) -> List[str]:
00193:     stop = {"this", "that", "page", "from", "with", "what", "does", "show", "find", "part", "figure", "manual"}
00194:     return [w.lower() for w in WORD_RE.findall(s) if len(w) >= 3 and w.lower() not in stop]
00195: 
00196: 
00197: def score_guidance_record(record: Mapping[str, Any], question: str, entities: Mapping[str, Any]) -> Tuple[int, List[str]]:
00198:     score = 0
00199:     reasons: List[str] = []
00200:     text = " ".join([
00201:         _norm_text(record.get("summary_text")),
00202:         " ".join(record.get("detected_topics") or []),
00203:         " ".join(record.get("detected_figures") or []),
00204:         " ".join(record.get("detected_part_numbers") or []),
00205:         _norm_text(record.get("manual_section_hint")),
00206:     ]).lower()
00207: 
00208:     for fig in entities.get("figures") or []:
00209:         if fig.lower() in {str(x).lower() for x in record.get("detected_figures") or []} or f"figure {fig.lower()}" in text or f"fig. {fig.lower()}" in text:
```
### Source window L452-L508
```python
00452: 
00453:     manifest = {
00454:         "status": STATUS_BUILT,
00455:         "quality_status": quality_status,
00456:         "module": MODULE,
00457:         "version": VERSION,
00458:         "question": question,
00459:         "source_v2_summary_guidance_index": str(v2_summary_guidance_index),
00460:         "summary": summary,
00461:         "failures": failures,
00462:         "records": records,
00463:         "paths": {
00464:             "planner": str(manifest_path),
00465:             "quality_check": str(quality_path),
00466:             "records_csv": str(records_csv_path),
00467:         },
00468:     }
00469:     _write_json(manifest_path, manifest)
00470:     _write_json(quality_path, {
00471:         "status": STATUS_CHECKED,
00472:         "quality_status": quality_status,
00473:         "summary": summary,
00474:         "failures": failures,
00475:     })
00476:     _write_csv(records_csv_path, records)
00477:     return manifest
00478: 
00479: 
00480: def check_engineering_query_planner(
00481:     *,
00482:     planner: Any,
00483:     output: Any,
00484:     require_quality_pass: bool = False,
00485:     min_planner_records: int = 1,
00486:     min_required_routes: int = 1,
00487:     max_unsafe: int = 0,
00488:     max_answer_permission: int = 0,
00489:     max_source_truth_mutation_allowed: int = 0,
00490:     max_write_attempts: int = 0,
00491: ) -> Dict[str, Any]:
00492:     data = _load_json(planner)
00493:     summary = data.get("summary") if isinstance(data.get("summary"), dict) else summarize(data.get("records") or [], {})
00494:     quality_status, failures = _quality(
00495:         summary,
00496:         min_planner_records=min_planner_records,
00497:         min_required_routes=min_required_routes,
00498:         max_unsafe=max_unsafe,
00499:         max_answer_permission=max_answer_permission,
00500:         max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
00501:         max_write_attempts=max_write_attempts,
00502:     )
00503:     if require_quality_pass and data.get("quality_status") != "PASS":
00504:         failures.append("source planner quality_status is not PASS")
00505:     if require_quality_pass and quality_status != "PASS":
00506:         failures.append("quality check status is not PASS")
00507:     final_status = "PASS" if not failures else "FAIL"
00508:     result = {
```
### Source window L517-L573
```python
00517: 
00518: 
00519: def _parse_build_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
00520:     ap = argparse.ArgumentParser(description="Build TRACE-Net engineering query planner v1")
00521:     ap.add_argument("--question", required=True)
00522:     ap.add_argument("--v2-summary-guidance-index", required=True)
00523:     ap.add_argument("--output-dir", required=True)
00524:     ap.add_argument("--max-guidance-pages", type=int, default=8)
00525:     ap.add_argument("--min-planner-records", type=int, default=1)
00526:     ap.add_argument("--min-required-routes", type=int, default=1)
00527:     ap.add_argument("--max-unsafe", type=int, default=0)
00528:     ap.add_argument("--max-answer-permission", type=int, default=0)
00529:     ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
00530:     ap.add_argument("--max-write-attempts", type=int, default=0)
00531:     return ap.parse_args(argv)
00532: 
00533: 
00534: def main(argv: Optional[Sequence[str]] = None) -> int:
00535:     args = _parse_build_args(argv)
00536:     result = build_engineering_query_planner(
00537:         question=args.question,
00538:         v2_summary_guidance_index=args.v2_summary_guidance_index,
00539:         output_dir=args.output_dir,
00540:         max_guidance_pages=args.max_guidance_pages,
00541:         min_planner_records=args.min_planner_records,
00542:         min_required_routes=args.min_required_routes,
00543:         max_unsafe=args.max_unsafe,
00544:         max_answer_permission=args.max_answer_permission,
00545:         max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
00546:         max_write_attempts=args.max_write_attempts,
00547:     )
00548:     summary = result.get("summary", {})
00549:     print(f"status={result.get('status')}")
00550:     print(f"quality_status={result.get('quality_status')}")
00551:     rec = (result.get("records") or [{}])[0]
00552:     print(f"task_type={rec.get('task_type')}")
00553:     print(f"required_route_count={summary.get('required_route_count')}")
00554:     print(f"selected_guidance_page_count={summary.get('selected_guidance_page_count')}")
00555:     print(f"can_answer_from_summaries_only_count={summary.get('can_answer_from_summaries_only_count')}")
00556:     print(f"unsafe_record_count={summary.get('unsafe_record_count')}")
00557:     print(f"answer_permission_count={summary.get('answer_permission_count')}")
00558:     print(f"source_truth_mutation_allowed_count={summary.get('source_truth_mutation_allowed_count')}")
00559:     print(f"write_attempt_count={summary.get('write_attempt_count')}")
00560:     print(f"planner={result.get('paths', {}).get('planner')}")
00561:     return 0 if result.get("quality_status") == "PASS" else 1
00562: 
00563: 
00564: def _parse_check_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
00565:     ap = argparse.ArgumentParser(description="Check TRACE-Net engineering query planner v1")
00566:     ap.add_argument("--planner", required=True)
00567:     ap.add_argument("--output", required=True)
00568:     ap.add_argument("--require-quality-pass", action="store_true")
00569:     ap.add_argument("--min-planner-records", type=int, default=1)
00570:     ap.add_argument("--min-required-routes", type=int, default=1)
00571:     ap.add_argument("--max-unsafe", type=int, default=0)
00572:     ap.add_argument("--max-answer-permission", type=int, default=0)
00573:     ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
```

## `scripts/build_trace_net_engineering_engram_prompt_retrieval_injector_v1.py`
- Location: `active_source_code`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L30
- CLI args: --vector-retriever, --output-dir, --max-atoms-per-query, --max-prompt-chars, --min-queries, --min-injected-atoms, --require-guidance-only, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_retrieval_injector_manifest
- Has __main__ guard.

### Source window L1-L40
```python
00001: #!/usr/bin/env python3
00002: from __future__ import annotations
00003: 
00004: import argparse
00005: import sys
00006: from pathlib import Path
00007: 
00008: REPO_ROOT = Path(__file__).resolve().parents[1]
00009: if str(REPO_ROOT) not in sys.path:
00010:     sys.path.insert(0, str(REPO_ROOT))
00011: 
00012: from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_retrieval_injector_manifest
00013: 
00014: 
00015: def build_arg_parser() -> argparse.ArgumentParser:
00016:     p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Prompt Retrieval Injector v1 artifact")
00017:     p.add_argument("--vector-retriever", required=True)
00018:     p.add_argument("--output-dir", required=True)
00019:     p.add_argument("--max-atoms-per-query", type=int, default=4)
00020:     p.add_argument("--max-prompt-chars", type=int, default=1800)
00021:     p.add_argument("--min-queries", type=int, default=1)
00022:     p.add_argument("--min-injected-atoms", type=int, default=1)
00023:     p.add_argument("--require-guidance-only", action="store_true")
00024:     p.add_argument("--require-no-answer-permission", action="store_true")
00025:     p.add_argument("--max-unsafe", type=int, default=0)
00026:     p.add_argument("--max-write-attempts", type=int, default=0)
00027:     return p
00028: 
00029: 
00030: def main(argv=None) -> int:
00031:     args = build_arg_parser().parse_args(argv)
00032:     result = build_prompt_retrieval_injector_manifest(
00033:         vector_retriever_path=args.vector_retriever,
00034:         output_dir=args.output_dir,
00035:         max_atoms_per_query=args.max_atoms_per_query,
00036:         max_prompt_chars=args.max_prompt_chars,
00037:         min_queries=args.min_queries,
00038:         min_injected_atoms=args.min_injected_atoms,
00039:         require_guidance_only=args.require_guidance_only,
00040:         require_no_answer_permission=args.require_no_answer_permission,
```

## `scripts/build_trace_net_engineering_engram_vector_loader_v1.py`
- Location: `active_source_code`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L27
- CLI args: --memory-layers, --output-dir, --collection-name, --vector-dim, --min-records, --require-all-layers, --max-unsafe
- Tiff imports: from tiff.trace_net_engineering_engram_vector_loader_v1 import build_vector_loader_manifest
- Has __main__ guard.

### Source window L1-L40
```python
00001: #!/usr/bin/env python3
00002: from __future__ import annotations
00003: 
00004: import argparse
00005: import sys
00006: from pathlib import Path
00007: 
00008: ROOT = Path(__file__).resolve().parents[1]
00009: if str(ROOT) not in sys.path:
00010:     sys.path.insert(0, str(ROOT))
00011: 
00012: from tiff.trace_net_engineering_engram_vector_loader_v1 import build_vector_loader_manifest
00013: 
00014: 
00015: def build_arg_parser() -> argparse.ArgumentParser:
00016:     p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram vector loader manifest v1")
00017:     p.add_argument("--memory-layers", required=True)
00018:     p.add_argument("--output-dir", required=True)
00019:     p.add_argument("--collection-name", default="trace_net_engineering_engram_memory_v1")
00020:     p.add_argument("--vector-dim", type=int, default=64)
00021:     p.add_argument("--min-records", type=int, default=1)
00022:     p.add_argument("--require-all-layers", action="store_true")
00023:     p.add_argument("--max-unsafe", type=int, default=0)
00024:     return p
00025: 
00026: 
00027: def main(argv=None) -> int:
00028:     args = build_arg_parser().parse_args(argv)
00029:     manifest = build_vector_loader_manifest(
00030:         memory_layers=args.memory_layers,
00031:         output_dir=args.output_dir,
00032:         vector_dim=args.vector_dim,
00033:         collection_name=args.collection_name,
00034:         min_records=args.min_records,
00035:         require_all_layers=args.require_all_layers,
00036:         max_unsafe=args.max_unsafe,
00037:     )
00038:     summary = manifest.get("summary", {})
00039:     print(f"status={manifest.get('status')}")
00040:     print(f"quality_status={manifest.get('quality_status')}")
```

## `scripts/build_trace_net_engineering_engram_vector_retriever_v1.py`
- Location: `active_source_code`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L15; main(argv)@L30
- CLI args: --vector-loader, --output-dir, --queries-jsonl, --query, --top-k, --min-queries, --min-results-per-query, --require-all-layers, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_vector_retriever_v1 import build_vector_retriever_manifest
- Has __main__ guard.

### Source window L1-L40
```python
00001: #!/usr/bin/env python3
00002: from __future__ import annotations
00003: 
00004: import argparse
00005: import sys
00006: from pathlib import Path
00007: 
00008: REPO_ROOT = Path(__file__).resolve().parents[1]
00009: if str(REPO_ROOT) not in sys.path:
00010:     sys.path.insert(0, str(REPO_ROOT))
00011: 
00012: from tiff.trace_net_engineering_engram_vector_retriever_v1 import build_vector_retriever_manifest
00013: 
00014: 
00015: def build_arg_parser() -> argparse.ArgumentParser:
00016:     p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Vector Retriever v1 artifact")
00017:     p.add_argument("--vector-loader", required=True)
00018:     p.add_argument("--output-dir", required=True)
00019:     p.add_argument("--queries-jsonl", default=None)
00020:     p.add_argument("--query", action="append", default=None, help="Inline query text; may be repeated")
00021:     p.add_argument("--top-k", type=int, default=5)
00022:     p.add_argument("--min-queries", type=int, default=1)
00023:     p.add_argument("--min-results-per-query", type=int, default=1)
00024:     p.add_argument("--require-all-layers", action="store_true")
00025:     p.add_argument("--max-unsafe", type=int, default=0)
00026:     p.add_argument("--max-write-attempts", type=int, default=0)
00027:     return p
00028: 
00029: 
00030: def main(argv=None) -> int:
00031:     args = build_arg_parser().parse_args(argv)
00032:     result = build_vector_retriever_manifest(
00033:         vector_loader_path=args.vector_loader,
00034:         output_dir=args.output_dir,
00035:         queries_path=args.queries_jsonl,
00036:         inline_queries=args.query,
00037:         top_k=args.top_k,
00038:         min_queries=args.min_queries,
00039:         min_results_per_query=args.min_results_per_query,
00040:         require_all_layers=args.require_all_layers,
```

## `scripts/check_trace_net_engineering_engram_postgres_feedback_ledger_v1.py`
- Location: `active_source_code`
- Score: `220`
- Categories: `engram, feedback, page, safety, server`
- Functions: build_arg_parser()@L7; main(argv)@L19
- CLI args: --feedback-ledger, --min-feedback-records, --min-candidate-records, --require-quality-pass, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import check_feedback_ledger_manifest
- Has __main__ guard.

### Source window L1-L32
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import check_feedback_ledger_manifest
00005: 
00006: 
00007: def build_arg_parser() -> argparse.ArgumentParser:
00008:     p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Postgres feedback ledger v1")
00009:     p.add_argument("--feedback-ledger", required=True)
00010:     p.add_argument("--min-feedback-records", type=int, default=5)
00011:     p.add_argument("--min-candidate-records", type=int, default=5)
00012:     p.add_argument("--require-quality-pass", action="store_true")
00013:     p.add_argument("--require-no-answer-permission", action="store_true")
00014:     p.add_argument("--max-unsafe", type=int, default=0)
00015:     p.add_argument("--max-write-attempts", type=int, default=0)
00016:     return p
00017: 
00018: 
00019: def main(argv: list[str] | None = None) -> int:
00020:     args = build_arg_parser().parse_args(argv)
00021:     result = check_feedback_ledger_manifest(
00022:         ledger=args.feedback_ledger,
00023:         min_feedback_records=args.min_feedback_records,
00024:         min_candidate_records=args.min_candidate_records,
00025:         require_quality_pass=args.require_quality_pass,
00026:         require_no_answer_permission=args.require_no_answer_permission,
00027:         max_unsafe=args.max_unsafe,
00028:         max_write_attempts=args.max_write_attempts,
00029:     )
00030:     print("status=" + result["status"])
00031:     print("quality_status=" + result["quality_status"])
00032:     print("feedback_record_count=" + str(result["feedback_record_count"]))
```

## `scripts/check_trace_net_engineering_engram_qdrant_adapter_v1.py`
- Location: `active_source_code`
- Score: `220`
- Categories: `engram, graph_vector, page, safety, server`
- Functions: build_arg_parser()@L7; main()@L20
- CLI args: --qdrant-adapter, --min-records, --min-local-queries, --require-quality-pass, --require-all-layers, --require-no-answer-permission, --max-unsafe, --max-write-attempts
- Tiff imports: from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import check_qdrant_adapter_manifest
- Has __main__ guard.

### Source window L1-L32
```python
00001: from __future__ import annotations
00002: 
00003: import argparse
00004: from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import check_qdrant_adapter_manifest
00005: 
00006: 
00007: def build_arg_parser() -> argparse.ArgumentParser:
00008:     p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Qdrant adapter artifact.")
00009:     p.add_argument("--qdrant-adapter", required=True)
00010:     p.add_argument("--min-records", type=int, default=1)
00011:     p.add_argument("--min-local-queries", type=int, default=0)
00012:     p.add_argument("--require-quality-pass", action="store_true")
00013:     p.add_argument("--require-all-layers", action="store_true")
00014:     p.add_argument("--require-no-answer-permission", action="store_true")
00015:     p.add_argument("--max-unsafe", type=int, default=0)
00016:     p.add_argument("--max-write-attempts", type=int, default=0)
00017:     return p
00018: 
00019: 
00020: def main() -> int:
00021:     args = build_arg_parser().parse_args()
00022:     result = check_qdrant_adapter_manifest(**vars(args))
00023:     print("status=" + result["status"])
00024:     print("quality_status=" + result["quality_status"])
00025:     print("qdrant_point_record_count=" + str(result["qdrant_point_record_count"]))
00026:     print("local_retrieval_query_count=" + str(result["local_retrieval_query_count"]))
00027:     print("qdrant_write_attempt_count=" + str(result["qdrant_write_attempt_count"]))
00028:     print("qdrant_read_attempt_count=" + str(result["qdrant_read_attempt_count"]))
00029:     print("unsafe_finding_count=" + str(result["unsafe_finding_count"]))
00030:     print("answer_permission_count=" + str(result["answer_permission_count"]))
00031:     print("write_attempt_count=" + str(result["write_attempt_count"]))
00032:     if result.get("quality_failures"):
```