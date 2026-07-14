# TRACE-Net H30 Cognitive Routes v1

## Purpose

H30 turns the existing normal, guided, and visual services into shared retrieval tunnels behind one query planner. It does not weaken the existing citation and authority gates.

The live canary stack is:

```text
OpenWebUI
  -> 172.17.0.1:8131 cognitive streaming bridge
      -> 127.0.0.1:8128 validated Gemma writer
          -> 127.0.0.1:8118 cognitive router
              -> existing unified route 127.0.0.1:8117
              -> existing guided route 127.0.0.1:8116
                  -> existing normal/source truth, visual, Qdrant,
                     graph/Leiden, V2/V3 summaries, and Engram paths
```

The existing port 8130 stack is left unchanged during canary testing.

## Route registry

| Route | Primary purpose | Fail-closed behavior |
|---|---|---|
| `safe_general_chat` | Greetings and usage help | Narrow allow-list; no technical claims |
| `exact_identifier_lookup` | Exact part/page/manual identifiers | Cross-route recovery; exact identifier fidelity |
| `guided_part_discovery` | Prefix, suffix, contains, or uncertain part clues | Candidates only; never final identification |
| `ata_system_discovery` | ATA chapter or system clues | ATA clue cannot become part-number prefix |
| `nomenclature_function_search` | Component name, function, or assembly context | Separates direct evidence from candidates/guidance |
| `exact_table_ipl_lookup` | IPL/table/item/row questions | Requires source-resolved table evidence |
| `visual_figure_callout_lookup` | Figures, diagrams, drawings, callouts | Visual guidance is not source truth |
| `procedure_task_lookup` | Removal, installation, and task steps | Requires direct procedure context |
| `warning_caution_note_lookup` | Warnings, cautions, notes, precautions | Must preserve task and condition context |
| `authority_eligibility_verification` | Approval, effectivity, interchangeability, eligibility | No authority claim without explicit authority fields |
| `document_page_navigation` | Find pages and source locations | Navigation guidance is not factual proof |
| `graph_relationship_reasoning` | Typed entity and assembly relationships | Graph results must resolve back to source evidence |
| `semantic_discovery` | Topical/vague page discovery | Qdrant is guidance, never proof |
| `cross_source_comparison` | Compare manuals or revisions | Sources remain separated |
| `contradiction_resolution` | Investigate conflicting evidence | Conflicts are surfaced, not silently resolved |
| `ocr_scan_recovery` | Blurry or difficult scanned content | OCR uncertainty remains explicit |
| `high_degree_entity_aggregation` | Broad cross-document coverage | Reports coverage/capping rather than hiding it |
| `multi_question_research` | Compound technical questions | Decomposes into bounded subqueries and claim-level gates |
| `clarification_no_evidence` | Insufficient clues or exhausted repair | Asks for the highest-value missing clue |

## Hallucination-minimization controls

1. Query atoms are extracted deterministically before retrieval.
2. ATA, part number, figure, table, page, authority, and conversational clues are entity-bound.
3. Every route emits one evidence envelope with direct, candidate, semantic, visual, authority, uncertainty, and contradiction sections.
4. Self-RAG checks route correctness, clue fidelity, citation readiness, authority, metadata consistency, and safety.
5. CRAG has a maximum of two bounded repairs and chooses a repair based on the failure type.
6. Exact-part failure triggers cross-route exact candidate and table/visual recovery instead of returning immediately.
7. Candidate filtering rejects navigation labels such as `25-LIST`, `25-Vendors`, `25-Numerical`, `25-LEP`, and ATA/page-shaped identifiers.
8. Qdrant, graph, summary, visual, and guided evidence is guidance until source-resolved.
9. Candidate-only and no-evidence answers are deterministic. Gemma does not rewrite them.
10. Gemma writes only when direct citation-ready evidence exists.
11. Gemma output is rejected when it introduces an unsupported part, ATA reference, page ID, citation, or safety-critical authority claim.
12. Rejected Gemma output falls back to the deterministic safe answer.
13. All services remain read-only and keep answer/source-mutation permission flags false.

## OpenWebUI connection

```text
Base URL: http://172.17.0.1:8131/v1
API key: trace-net-openwebui-cognitive
Model: trace-net-gemma4-cognitive-rag-v1
```

The launcher detects the actual `docker0` host address and prints the final Base URL.

## Critical expected behavior

| Query | Expected route/behavior |
|---|---|
| `hello` | Friendly `safe_general_chat` response |
| `ATA number starts with 25` | `ata_system_discovery`; `part_prefix` remains null |
| `Find part 120-41824-003` | Exact lookup plus guided/visual cross-route recovery |
| `The P/N contains 41824` | Only candidates satisfying `41824` |
| `Find the locking ring near the seat` | Nomenclature/function route using multiple tunnels |
| `Is this an approved replacement?` | Explicit authority required or fail closed |

## Relationship to the existing Engram Self-RAG and CRAG modules

The repository's existing Engineering Engram Self-RAG critic and CRAG repair modules are artifact/smoke evaluators. H30 preserves their proof-boundary policies and adds a live request-time critic and bounded retrieval-repair controller. The artifact modules remain useful for offline regression, feedback promotion, and commit gates; they are not treated as source evidence.
